"""Aprendizaje por refuerzo (PPO): la red mejora jugando contra una liga de rivales.

Parte de la red de imitación y repite este ciclo:

1. **Jugar** (en paralelo, con la red en numpy). Una pareja de "aprendices" usa la red actual y
   elige cada jugada al azar según sus probabilidades, para explorar. Enfrente se sienta un
   rival de la **liga**:

   - ``yo``: la propia red actual (juego contra sí misma; se aprende de los cuatro asientos);
   - ``historico``: una versión anterior de la red, para no olvidar cómo ganar a estilos viejos;
   - los estilos de ``reglas``, para no perder contra el heurístico mientras se explora.

2. **Premiar**. La recompensa principal es +1 si su pareja ganó la vaca y -1 si la perdió.
   Se le pueden sumar recompensas intermedias al final de cada mano (ver
   :data:`RECOMPENSAS`):

   - ``tantos``: la diferencia de tantos ganados en la mano (denso, pero cambia un poco el
     objetivo: premia sumar tantos aunque no ayuden a ganar la vaca);
   - ``potencial``: cuánto sube o baja la probabilidad de ganar la vaca con el marcador
     (*potential-based shaping*: da señal en cada mano y **no cambia** cuál es la mejor
     estrategia, porque la suma de todas estas recompensas en una vaca es cero);
   - ``farol``: un premio por ganar un lance con "no quiero" teniendo una mano floja, y el
     castigo contrario a la pareja engañada. Cambia el objetivo a propósito: puede enseñar a
     farolear más de lo que conviene, por eso se mide.

   La cabeza de **valor** estima la recompensa que falta por llegar y, con GAE (*generalized
   advantage estimation*), se calcula la **ventaja** de cada jugada: cuánto mejor (o peor) fue
   la situación después de jugarla de lo que la red esperaba.

3. **Aprender** (PyTorch). PPO sube la probabilidad de las jugadas con ventaja positiva y baja
   la de las negativas, pero con un **recorte** (*clip*) para no alejarse demasiado de la
   política con la que se jugó: así el entrenamiento es estable. Además:

   - un término de **entropía** evita que la red se vuelva determinista demasiado pronto;
   - un término de **ancla** (divergencia KL con la red de imitación) mantiene el estilo de
     su maestro. Es pequeño: si chocan, manda la fuerza.

Cada cierto número de iteraciones se mide la red (eligiendo siempre su mejor jugada, como en la
arena) contra ``reglas`` y se guarda en la carpeta de puntos de control.

Uso::

    python -m musarena.ia.entrenamiento.refuerzo --iteraciones 200 \\
        --salida checkpoints/refuerzo
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from collections import Counter
from collections.abc import Sequence
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import asdict, dataclass, field
from functools import partial
from pathlib import Path

import numpy as np
import torch

from musarena.actions import Action
from musarena.arena import enfrentar
from musarena.estrategia.evaluacion import prob_vaca
from musarena.estrategia.tipos import FUERZA, indice_de
from musarena.ia import acciones
from musarena.ia.codificacion import codificar
from musarena.ia.entrenamiento.imitacion import RedTorch
from musarena.ia.red import Red
from musarena.match import Match
from musarena.observation import Observation
from musarena.player import Bot, Player
from musarena.players import SmartBot, crear_jugador
from musarena.players.smart_bot import MODELO_POR_DEFECTO
from musarena.state import TANTOS_VACA, ResumenMano, pareja

#: Rivales de la liga y con qué frecuencia se elige cada uno.
LIGA: dict[str, float] = {
    "yo": 0.35,
    "historico": 0.25,
    "reglas": 0.15,
    "reglas:agresivo": 0.125,
    "reglas:conservador": 0.125,
}


@dataclass
class Config:
    """Parámetros del entrenamiento (los valores por defecto son los que usamos)."""

    iteraciones: int = 200
    partidas: int = 400          # partidas por iteración
    mejor_de: int = 3
    procesos: int | None = None
    lr: float = 1e-4
    epocas: int = 3              # pasadas de PPO sobre los datos de cada iteración
    lote: int = 4096
    recorte: float = 0.2         # clip de PPO
    kl_maximo: float = 0.03      # si la política se aleja más, se corta la iteración
    gae_lambda: float = 0.95
    coef_valor: float = 0.5
    coef_entropia: float = 0.005
    coef_ancla: float = 0.02
    historico_cada: int = 10     # cada cuántas iteraciones se añade una versión a la liga
    evaluar_cada: int = 10
    partidas_evaluacion: int = 400
    seed: int = 0
    recompensa: str = "vaca"     # "vaca", o "vaca+tantos", "vaca+potencial+farol"...
    coef_tantos: float = 0.5     # peso de la diferencia de tantos (40 tantos = 1)
    bonus_farol: float = 0.1     # premio por farol ganado
    umbral_farol: float = 0.4    # "mano floja": probabilidad de ganar el lance menor que esto
    liga: dict[str, float] = field(default_factory=lambda: dict(LIGA))


# --- Jugar -------------------------------------------------------------------------------


class Aprendiz(Bot):
    """Juega con la red eligiendo al azar según sus probabilidades y apunta cada decisión."""

    tipo = "aprendiz"

    def __init__(self, red: Red, seed: int) -> None:
        super().__init__("aprendiz", seed)
        self.red = red
        self.azar = np.random.default_rng(seed)
        # (x, máscara, acción, log-probabilidad, valor estimado, número de vaca, de mano)
        self.registro: list[tuple[np.ndarray, np.ndarray, int, float, float, int, int]] = []

    def choose_action(self, observation: Observation, legal_actions: Sequence[Action]) -> Action:
        mascara = acciones.mascara(legal_actions, observation.cartas)
        x = codificar(observation)
        p, v = self.red.evaluar(x, mascara)
        acumulada = np.cumsum(p, dtype=np.float64)
        i = int(np.searchsorted(acumulada, self.azar.random() * acumulada[-1], side="right"))
        i = min(i, len(p) - 1)
        self.registro.append((x, mascara, i, float(np.log(p[i])), v, sum(observation.vacas),
                              len(observation.manos_jugadas)))
        return acciones.accion(i, observation.cartas)


#: Tipos de recompensa que se pueden combinar con "+" (``"vaca+potencial"``).
RECOMPENSAS: tuple[str, ...] = ("vaca", "tantos", "potencial", "farol")


def recompensas_por_mano(manos: Sequence[ResumenMano], cfg: Config
                         ) -> list[tuple[int, tuple[float, float]]]:
    """Recompensa intermedia de cada pareja en cada mano: ``(vaca, (pareja 0, pareja 1))``.

    La de ganar o perder la vaca no está aquí: se suma aparte, al final de cada vaca.
    """
    tipos = set(cfg.recompensa.split("+"))
    if not tipos <= set(RECOMPENSAS) or "vaca" not in tipos:
        raise ValueError(f"Recompensa desconocida {cfg.recompensa!r}: combina "
                         f"{', '.join(RECOMPENSAS)} con '+', siempre con 'vaca'")
    salida = []
    vaca, marcador = 0, [0, 0]
    for m in manos:
        ganados = [0, 0]
        for c in m.cobros:
            ganados[c.pareja] += c.tantos
        r0 = 0.0  # recompensa de la pareja 0; la de la pareja 1 es la contraria
        if "tantos" in tipos:
            r0 += cfg.coef_tantos * max(-1.0, min(1.0, (ganados[0] - ganados[1]) / TANTOS_VACA))
        if "potencial" in tipos:
            antes = 2 * prob_vaca(*marcador) - 1
            despues = 0.0 if m.ganador_vaca is not None else 2 * prob_vaca(
                min(TANTOS_VACA, marcador[0] + ganados[0]),
                min(TANTOS_VACA, marcador[1] + ganados[1])) - 1
            r0 += despues - antes
        if "farol" in tipos:
            for c in m.cobros:
                if c.motivo != "no quiero" or c.lance is None:
                    continue
                fuerza = max(FUERZA[c.lance][indice_de(m.cartas[s])]
                             for s in range(4) if pareja(s) == c.pareja)
                if fuerza < cfg.umbral_farol:
                    r0 += cfg.bonus_farol if c.pareja == 0 else -cfg.bonus_farol
        salida.append((vaca, (r0, -r0)))
        if m.ganador_vaca is not None:
            vaca, marcador = vaca + 1, [0, 0]
        else:
            marcador = [marcador[0] + ganados[0], marcador[1] + ganados[1]]
    return salida


def ventajas(valores: np.ndarray, recompensas: np.ndarray, lam: float
             ) -> tuple[np.ndarray, np.ndarray]:
    """GAE de las decisiones de un jugador en una vaca.

    ``recompensas[t]`` es lo que recibe entre la decisión ``t`` y la siguiente (la última
    incluye el resultado de la vaca). Devuelve (ventaja, retorno) de cada decisión. Con
    ``lam=1`` la ventaja es la recompensa que llegó menos la que esperaba la red; con ``lam``
    menor se apoya más en las estimaciones de la red (menos ruido, algo más de sesgo).
    """
    n = len(valores)
    ventaja = np.zeros(n, dtype=np.float32)
    acumulado = 0.0
    for t in range(n - 1, -1, -1):
        siguiente = valores[t + 1] if t < n - 1 else 0.0
        delta = recompensas[t] + siguiente - valores[t]
        acumulado = delta + lam * acumulado
        ventaja[t] = acumulado
    return ventaja, ventaja + valores.astype(np.float32)


def _mesa(red: Red, rival: str | Red, seed: int, aprendiz_en: int) -> list[Player]:
    """Cuatro jugadores: aprendices en la pareja ``aprendiz_en`` y el rival en la otra."""
    rng = random.Random(seed)
    mesa: list[Player] = []
    for asiento in range(4):
        s = rng.randrange(2**32)
        if pareja(asiento) == aprendiz_en or rival == "yo":
            mesa.append(Aprendiz(red, s))
        elif isinstance(rival, Red):
            mesa.append(SmartBot(seed=s, modelo=rival, temperatura=1.0))
        else:
            mesa.append(crear_jugador(rival, seed=s))
    return mesa


def jugar(args: tuple[Red, str | Red, str, int, int, Config]) -> dict:
    """Juega ``partidas`` partidas contra un rival y devuelve los ejemplos para PPO."""
    red, rival, nombre, partidas, seed, cfg = args
    rng = random.Random(seed)
    columnas: dict[str, list] = {k: [] for k in ("x", "mascara", "accion", "logp", "ventaja",
                                                 "retorno")}
    victorias = 0
    for n in range(partidas):
        aprendiz_en = n % 2
        mesa = _mesa(red, rival, rng.randrange(2**32), aprendiz_en)
        match = Match(mesa, mejor_de=cfg.mejor_de, seed=rng.randrange(2**32))
        victorias += match.play() == aprendiz_en
        manos = match.state.manos_jugadas
        ganadoras = [m.ganador_vaca for m in manos if m.ganador_vaca is not None]
        por_mano = recompensas_por_mano(manos, cfg)
        for asiento, jugador in enumerate(mesa):
            if not isinstance(jugador, Aprendiz) or not jugador.registro:
                continue
            reg = jugador.registro
            p = pareja(asiento)
            vacas = np.array([r[5] for r in reg])
            numeros = np.array([r[6] for r in reg])
            valores = np.array([r[4] for r in reg], dtype=np.float32)
            for vaca in np.unique(vacas):
                idx = np.flatnonzero(vacas == vaca)
                recompensas = np.zeros(len(idx), dtype=np.float32)
                # Lo de cada mano va a la última decisión tomada antes de que acabara.
                for h, (vaca_h, r) in enumerate(por_mano):
                    j = int(np.searchsorted(numeros[idx], h, side="right")) - 1
                    if vaca_h == vaca and j >= 0 and r[p]:
                        recompensas[j] += r[p]
                recompensas[-1] += 1.0 if ganadoras[vaca] == p else -1.0
                ventaja, retorno = ventajas(valores[idx], recompensas, cfg.gae_lambda)
                columnas["ventaja"].append(ventaja)
                columnas["retorno"].append(retorno)
            columnas["x"].extend(r[0] for r in reg)
            columnas["mascara"].extend(r[1] for r in reg)
            columnas["accion"].extend(r[2] for r in reg)
            columnas["logp"].extend(r[3] for r in reg)
    return {
        "rival": nombre,
        "partidas": partidas,
        "victorias": victorias,
        "x": np.asarray(columnas["x"], dtype=np.float32),
        "mascara": np.asarray(columnas["mascara"], dtype=bool),
        "accion": np.asarray(columnas["accion"], dtype=np.int64),
        "logp": np.asarray(columnas["logp"], dtype=np.float32),
        "ventaja": np.concatenate(columnas["ventaja"]),
        "retorno": np.concatenate(columnas["retorno"]),
    }


# --- Aprender ----------------------------------------------------------------------------


def actualizar(modelo: RedTorch, ancla: RedTorch, optimizador: torch.optim.Optimizer,
               datos: dict[str, np.ndarray], cfg: Config, rng: np.random.Generator
               ) -> dict[str, float]:
    """Una actualización de PPO con los datos de una iteración. Devuelve métricas."""
    x = torch.from_numpy(datos["x"])
    m = torch.from_numpy(datos["mascara"])
    a = torch.from_numpy(datos["accion"])
    logp_viejo = torch.from_numpy(datos["logp"])
    ventaja = torch.from_numpy(datos["ventaja"])
    ventaja = (ventaja - ventaja.mean()) / (ventaja.std() + 1e-8)
    retorno = torch.from_numpy(datos["retorno"])
    with torch.no_grad():
        logp_ancla = torch.log_softmax(ancla(x, m)[0], dim=1)

    n = len(a)
    suma: Counter[str] = Counter()
    pasos = 0
    modelo.train()
    for _ in range(cfg.epocas):
        kl_epoca = []
        orden = torch.from_numpy(rng.permutation(n))
        for inicio in range(0, n, cfg.lote):
            i = orden[inicio:inicio + cfg.lote]
            logits, valor = modelo(x[i], m[i])
            logp_todas = torch.log_softmax(logits, dim=1)
            logp = logp_todas.gather(1, a[i].unsqueeze(1)).squeeze(1)
            razon = torch.exp(logp - logp_viejo[i])
            recortada = torch.clamp(razon, 1 - cfg.recorte, 1 + cfg.recorte)
            perdida_politica = -torch.min(razon * ventaja[i], recortada * ventaja[i]).mean()
            p = torch.exp(logp_todas)
            entropia = -(p * logp_todas).sum(1).mean()
            kl_ancla = (p * (logp_todas - logp_ancla[i])).sum(1).mean()
            perdida_valor = ((valor - retorno[i]) ** 2).mean()
            perdida = (perdida_politica + cfg.coef_valor * perdida_valor
                       - cfg.coef_entropia * entropia + cfg.coef_ancla * kl_ancla)
            optimizador.zero_grad()
            perdida.backward()
            torch.nn.utils.clip_grad_norm_(modelo.parameters(), 1.0)
            optimizador.step()
            with torch.no_grad():
                kl = (logp_viejo[i] - logp).mean().item()
                kl_epoca.append(kl)
                suma.update(politica=perdida_politica.item(), valor=perdida_valor.item(),
                            entropia=entropia.item(), ancla=kl_ancla.item(), kl=kl,
                            recortes=((razon - 1).abs() > cfg.recorte).float().mean().item())
            pasos += 1
        if np.mean(kl_epoca) > cfg.kl_maximo:
            break
    return {k: v / pasos for k, v in suma.items()}


# --- Medir -------------------------------------------------------------------------------


def _jugador_red(red: Red, seed: int) -> Player:
    return SmartBot(seed=seed, modelo=red)


def _enfrentar_trozo(args: tuple[Red, str, int, int]) -> tuple[int, int]:
    red, rival, partidas, seed = args
    r = enfrentar(partial(_jugador_red, red), rival, partidas=partidas, seed=seed)
    return r.victorias_a, r.partidas


def evaluar(red: Red, rival: str, partidas: int, ex: Executor, trozos: int, seed: int = 12345
            ) -> float:
    """Porcentaje de victorias de la red (sin azar: su mejor jugada) contra ``rival``."""
    por_trozo = max(2, (partidas // trozos) // 2 * 2)  # par: cada reparto se juega dos veces
    tareas = [(red, rival, por_trozo, seed + i) for i in range(max(1, partidas // por_trozo))]
    resultados = list(ex.map(_enfrentar_trozo, tareas))
    return sum(v for v, _ in resultados) / sum(n for _, n in resultados)


# --- Bucle principal ---------------------------------------------------------------------


def entrenar(red_inicial: Red, cfg: Config, salida: str | Path, informar: bool = True,
             ancla: Red | None = None) -> Red:
    """Entrena con PPO partiendo de ``red_inicial``; guarda puntos de control en ``salida``.

    ``ancla`` es la red cuyo estilo se quiere conservar (por defecto, la inicial). Para seguir
    entrenando un modelo de refuerzo sin perder el estilo humano se ancla a la de imitación.
    """
    salida = Path(salida)
    salida.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(cfg.seed)
    rng = np.random.default_rng(cfg.seed)
    azar = random.Random(cfg.seed)
    procesos = cfg.procesos or os.cpu_count() or 1
    torch.set_num_threads(max(1, min(8, procesos)))

    modelo = RedTorch.desde_numpy(red_inicial)
    ancla_torch = RedTorch.desde_numpy(ancla or red_inicial).eval()
    optimizador = torch.optim.Adam(modelo.parameters(), lr=cfg.lr)
    historico: list[Red] = [red_inicial]
    rivales, pesos = list(cfg.liga), list(cfg.liga.values())
    mejor = -1.0
    red = red_inicial
    registro = salida / "registro.jsonl"

    with ProcessPoolExecutor(procesos) as ex:
        for it in range(1, cfg.iteraciones + 1):
            t = time.perf_counter()
            modelo.eval()
            red = modelo.a_numpy({"origen": "refuerzo", "iteracion": it - 1})
            trozos = procesos * 2
            tareas = []
            for k in range(trozos):
                nombre = azar.choices(rivales, weights=pesos)[0]
                rival: str | Red = azar.choice(historico) if nombre == "historico" else nombre
                n = cfg.partidas // trozos + (k < cfg.partidas % trozos)
                tareas.append((red, rival, nombre, n, azar.randrange(2**32), cfg))
            lotes = list(ex.map(jugar, tareas))
            datos = {k: np.concatenate([b[k] for b in lotes]) for k in
                     ("x", "mascara", "accion", "logp", "ventaja", "retorno")}
            t_jugar = time.perf_counter() - t
            metricas = actualizar(modelo, ancla_torch, optimizador, datos, cfg, rng)

            por_rival: dict[str, list[int]] = {}
            for b in lotes:
                if b["rival"] != "yo":
                    v = por_rival.setdefault(b["rival"], [0, 0])
                    v[0] += b["victorias"]
                    v[1] += b["partidas"]
            fila = {"iteracion": it, "decisiones": len(datos["accion"]),
                    "segundos": round(time.perf_counter() - t, 1),
                    "segundos_jugando": round(t_jugar, 1),
                    **{k: round(v, 4) for k, v in metricas.items()},
                    "victorias": {k: round(v / n, 3) for k, (v, n) in por_rival.items()}}

            if it % cfg.historico_cada == 0:
                historico.append(modelo.a_numpy({"origen": "refuerzo", "iteracion": it}))
            if it % cfg.evaluar_cada == 0 or it == cfg.iteraciones:
                modelo.eval()
                red = modelo.a_numpy({"origen": "refuerzo", "iteracion": it})
                pct = evaluar(red, "reglas", cfg.partidas_evaluacion, ex, procesos)
                fila["contra_reglas"] = round(pct, 4)
                red.info["contra_reglas"] = pct
                red.guardar(salida / f"iter{it:04d}.npz")
                if pct > mejor:
                    mejor = pct
                    red.guardar(salida / "mejor.npz")
            with registro.open("a", encoding="utf-8") as f:
                f.write(json.dumps(fila, ensure_ascii=False) + "\n")
            if informar:
                texto = ", ".join(f"{k} {v:.0%}" for k, v in fila["victorias"].items())
                extra = (f" | contra reglas (sin azar) {fila['contra_reglas']:.1%}"
                         if "contra_reglas" in fila else "")
                print(f"iter {it}: {fila['decisiones']} decisiones, {fila['segundos']}s, "
                      f"kl {metricas['kl']:.4f}, entropía {metricas['entropia']:.3f}, "
                      f"valor {metricas['valor']:.3f} | {texto}{extra}", flush=True)

    modelo.eval()
    return modelo.a_numpy({"origen": "refuerzo", "iteracion": cfg.iteraciones,
                           "config": asdict(cfg)})


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mejora la red con aprendizaje por refuerzo.")
    parser.add_argument("--inicial", default=str(MODELO_POR_DEFECTO))
    parser.add_argument("--ancla", default=None,
                        help="red cuyo estilo conservar (por defecto, la inicial)")
    parser.add_argument("--salida", default="checkpoints/refuerzo")
    for nombre, valor in asdict(Config()).items():
        if isinstance(valor, (int, float, str)) and not isinstance(valor, bool):
            parser.add_argument(f"--{nombre.replace('_', '-')}", type=type(valor), default=valor)
    parser.add_argument("--procesos", type=int, default=None)
    args = parser.parse_args(argv)
    cfg = Config(**{k: getattr(args, k) for k in asdict(Config()) if hasattr(args, k)})
    print(f"Configuración: {asdict(cfg)}")
    ancla = Red.cargar(args.ancla) if args.ancla else None
    red = entrenar(Red.cargar(args.inicial), cfg, args.salida, ancla=ancla)
    red.guardar(Path(args.salida) / "final.npz")
    print(f"modelo final en {Path(args.salida) / 'final.npz'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
