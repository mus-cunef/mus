"""Aprendizaje por imitación: la red aprende a jugar como el maestro que generó los datos.

Es aprendizaje supervisado. Para cada decisión guardada, la red recibe la observación codificada
y aprende a:

- **política**: dar la mayor probabilidad a la acción que eligió el maestro (entropía cruzada,
  solo entre las acciones legales);
- **valor**: predecir si la pareja ganará la vaca (error cuadrático).

Se guarda aparte un 5 % de los datos para medir si la red generaliza (aciertos en decisiones que
no ha visto al entrenar). Al terminar, los pesos se exportan a numpy
(:class:`~musarena.ia.red.Red`).

Uso::

    python -m musarena.ia.entrenamiento.imitacion --datos datos/reglas.npz \\
        --salida src/musarena/ia/modelos/inteligente.npz
"""

from __future__ import annotations

import argparse
import time
from collections.abc import Sequence

import numpy as np
import torch
from torch import nn

from musarena.ia.acciones import N_ACCIONES
from musarena.ia.codificacion import N_ENTRADAS
from musarena.ia.entrenamiento.datos import cargar
from musarena.ia.red import Red


class RedTorch(nn.Module):
    """La misma arquitectura que :class:`~musarena.ia.red.Red`, en PyTorch para entrenar."""

    def __init__(self, n_entradas: int = N_ENTRADAS, ocultas: Sequence[int] = (256, 256),
                 n_acciones: int = N_ACCIONES) -> None:
        super().__init__()
        tamanos = (n_entradas, *ocultas)
        self.capas = nn.ModuleList(
            nn.Linear(a, b) for a, b in zip(tamanos[:-1], tamanos[1:], strict=True)
        )
        self.politica = nn.Linear(tamanos[-1], n_acciones)
        self.valor = nn.Linear(tamanos[-1], 1)

    def forward(self, x: torch.Tensor, mascara: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        for capa in self.capas:
            x = torch.relu(capa(x))
        logits = self.politica(x).masked_fill(~mascara, -1e9)
        return logits, torch.tanh(self.valor(x)).squeeze(-1)

    def a_numpy(self, info: dict) -> Red:
        def par(capa: nn.Linear) -> tuple[np.ndarray, np.ndarray]:
            return (capa.weight.detach().T.contiguous().numpy().astype(np.float32),
                    capa.bias.detach().numpy().astype(np.float32))

        return Red([par(c) for c in self.capas], par(self.politica), par(self.valor), info)

    @classmethod
    def desde_numpy(cls, red: Red) -> RedTorch:
        ocultas = tuple(w.shape[1] for w, _ in red.capas)
        modelo = cls(red.n_entradas, ocultas, red.politica[0].shape[1])
        with torch.no_grad():
            for capa, (w, b) in zip(modelo.capas, red.capas, strict=True):
                capa.weight.copy_(torch.from_numpy(w.T))
                capa.bias.copy_(torch.from_numpy(b))
            for capa, (w, b) in ((modelo.politica, red.politica), (modelo.valor, red.valor)):
                capa.weight.copy_(torch.from_numpy(w.T))
                capa.bias.copy_(torch.from_numpy(b))
        return modelo


def entrenar(
    datos: dict[str, np.ndarray],
    ocultas: Sequence[int] = (256, 256),
    epocas: int = 8,
    lote: int = 2048,
    lr: float = 2e-3,
    peso_valor: float = 0.5,
    seed: int = 0,
    modelo: RedTorch | None = None,
    informar: bool = True,
) -> tuple[RedTorch, dict[str, float]]:
    """Entrena (o sigue entrenando ``modelo``) y devuelve la red y sus métricas finales."""
    torch.manual_seed(seed)
    n = len(datos["y"])
    rng = np.random.default_rng(seed)
    orden = rng.permutation(n)
    n_val = max(1, n // 20)
    val, ent = orden[:n_val], orden[n_val:]
    x = torch.from_numpy(datos["x"])
    m = torch.from_numpy(datos["mascara"])
    y = torch.from_numpy(datos["y"].astype(np.int64))
    v = torch.from_numpy(datos["valor"])

    modelo = modelo or RedTorch(datos["x"].shape[1], ocultas)
    optimizador = torch.optim.AdamW(modelo.parameters(), lr=lr, weight_decay=1e-4)
    pasos = epocas * (len(ent) // lote + 1)
    planificador = torch.optim.lr_scheduler.OneCycleLR(optimizador, max_lr=lr, total_steps=pasos)
    entropia = nn.CrossEntropyLoss()

    def medir(indices: np.ndarray) -> dict[str, float]:
        modelo.eval()
        with torch.no_grad():
            logits, valor = modelo(x[indices], m[indices])
            return {
                "perdida": float(entropia(logits, y[indices])),
                "aciertos": float((logits.argmax(1) == y[indices]).float().mean()),
                "error_valor": float(((valor - v[indices]) ** 2).mean()),
            }

    for epoca in range(epocas):
        t = time.perf_counter()
        modelo.train()
        for inicio in range(0, len(ent), lote):
            i = ent[inicio:inicio + lote]
            logits, valor = modelo(x[i], m[i])
            perdida = entropia(logits, y[i]) + peso_valor * ((valor - v[i]) ** 2).mean()
            optimizador.zero_grad()
            perdida.backward()
            optimizador.step()
            planificador.step()
        rng.shuffle(ent)
        metricas = medir(val)
        if informar:
            print(f"época {epoca + 1}/{epocas}: aciertos {metricas['aciertos']:.1%}, "
                  f"pérdida {metricas['perdida']:.3f}, error de valor "
                  f"{metricas['error_valor']:.3f} ({time.perf_counter() - t:.0f}s)", flush=True)
    return modelo, medir(val)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Entrena la red imitando decisiones guardadas.")
    parser.add_argument("--datos", default="datos/reglas.npz")
    parser.add_argument("--salida", default="checkpoints/imitacion.npz")
    parser.add_argument("--epocas", type=int, default=8)
    parser.add_argument("--ocultas", default="256,256")
    args = parser.parse_args(argv)
    datos = cargar(args.datos)
    ocultas = tuple(int(t) for t in args.ocultas.split(","))
    print(f"{len(datos['y'])} decisiones, red {ocultas}")
    modelo, metricas = entrenar(datos, ocultas, args.epocas)
    info = {"origen": "imitación", "datos": args.datos, "decisiones": int(len(datos["y"])),
            "ocultas": list(ocultas), **metricas}
    modelo.a_numpy(info).guardar(args.salida)
    print(f"modelo guardado en {args.salida}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
