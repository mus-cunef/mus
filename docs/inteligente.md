# Bot inteligente

Objetivo: el bot de mus más fuerte que podamos construir y que, además, juegue como un humano.
Cuando las dos cosas choquen, **manda la fuerza**.

Metas medibles:

1. Ganar al menos el **65 %** de las partidas contra `reglas`, el heurístico avanzado.
2. **No ser explotable**: un bot "cazador" entrenado solo para ganarle no debe sacarle mucha
   ventaja.
3. **Ganar a humanos** que juegan bien, medido con partidas reales registradas.

## El plan

El mus es un juego de información oculta, por parejas y con faroles. En juegos así (póker,
bridge, Diplomacy) lo que mejor funciona es combinar:

| Fase | Técnica | Qué aporta |
| --- | --- | --- |
| 1 | **Imitación** (aprendizaje supervisado) | Una red neuronal aprende a copiar a un buen jugador. Primero a `reglas` (millones de decisiones gratis), después a humanos. |
| 2 | **Aprendizaje por refuerzo** jugando contra sí misma y contra una liga de rivales | Mejora por encima de su maestro: descubre cuándo compensa un farol o un órdago. |
| 3 | **Búsqueda al decidir** | Antes de una decisión importante, se imagina las manos posibles de los rivales (con las creencias de `estrategia/`) y simula cómo acabaría. |
| 4 | **Estilo humano** con partidas humanas grabadas | Se parece a los humanos sin perder fuerza (la técnica de Cicero, el bot de Diplomacy). |

## Cómo está hecho

```
src/musarena/ia/
  acciones.py       catálogo fijo de 40 acciones + máscara de legales
  codificacion.py   Observation -> vector de 163 números
  red.py            la red en numpy (para jugar no hace falta PyTorch)
  modelos/          pesos entrenados que viajan con el paquete
  entrenamiento/    generación de datos e imitación (necesita PyTorch)
src/musarena/players/smart_bot.py   el bot "inteligente"
```

- **Qué ve la red** (`codificacion.py`). Recibe un vector con:
  - sus cartas y el valor de su mano;
  - la fase, el lance y su posición respecto a la mano;
  - el marcador y la apuesta en curso;
  - las declaraciones, el mus y los descartes de cada uno;
  - cómo acabaron los lances ya jugados y la última acción de cada jugador;
  - el análisis de `estrategia/`: probabilidad de ganar el lance con y sin compañero, bonus en
    juego y fuerza esperada de cada uno de los demás.

  Todo va **respecto a quien decide** (mi compañero, el rival de mi derecha…) y sale solo de su
  `Observation`. Un test comprueba que cambiar las cartas de los demás no cambia nada de lo
  que ve.
- **Qué puede elegir** (`acciones.py`). Tiene 40 acciones fijas:
  - mus o no hay mus;
  - los 15 descartes (por posición en la mano ordenada);
  - paso, envido con 10 cantidades, reenvido con 9 cantidades y órdago;
  - quiero y no quiero.

  Una máscara tapa las ilegales en cada decisión: **nunca puede hacer una jugada ilegal**.
- **La red** (`red.py`). Es un perceptrón multicapa (163 → 256 → 256) con dos salidas:
  - la **política**, que da la probabilidad de cada acción;
  - el **valor**, que estima de -1 a 1 si su pareja ganará la vaca y servirá en el aprendizaje
    por refuerzo.
- **Entrenar con PyTorch, jugar con numpy.** Al terminar, los pesos se exportan a un `.npz` de
  440 KB. Así la librería no depende de PyTorch y el bot podrá funcionar en la web.
- **Temperatura.** Con `temperatura=0` el bot elige siempre su mejor jugada. Con más de 0 elige
  al azar según sus probabilidades: es más variado y más humano.

## Semana 1: imitación de `reglas`

1. **Datos**: 10.000 partidas entre bots `reglas`, con los tres estilos mezclados en cada mesa,
   dan **1.873.334 decisiones** (2 minutos con 20 procesos).
2. **Entrenamiento**: 8 épocas en CPU (1 minuto). La red acierta la jugada del maestro en el
   **87,7 %** de las decisiones que no vio al entrenar.
3. **Resultado en la arena** (1.000 partidas por enfrentamiento):

| `inteligente` contra | Victorias |
| --- | --- |
| `reglas` (su maestro) | 49,3 % ± 3,1 |
| `basico` | 73,8 % ± 2,7 |
| `random` | 92,9 % ± 1,6 |

Juega **igual que su maestro**, que era el objetivo de la semana, y mucho más rápido: 3.000
partidas en 18 segundos. Es el punto de partida para el aprendizaje por refuerzo.

### Reproducirlo

```bash
pip install -e ".[dev,ia]"
python -m musarena.ia.entrenamiento.datos --partidas 10000 --salida datos/reglas.npz
python -m musarena.ia.entrenamiento.imitacion --datos datos/reglas.npz \
    --salida src/musarena/ia/modelos/inteligente.npz
mus-arena inteligente reglas -n 1000
```

Las carpetas `datos/` y `checkpoints/` no se suben a git. Solo se sube el modelo elegido, en
`src/musarena/ia/modelos/`.

## Próximos pasos

- **Semana 2**: aprendizaje por refuerzo (PPO) partiendo de esta red, contra sí misma, sus
  versiones anteriores y los tres estilos de `reglas`. Meta: superar claramente a `reglas`.
- **Semana 3**: búsqueda al decidir y bot cazador. Meta: 65 % o más contra `reglas`, sin
  debilidades fáciles de explotar.
- **Semana 4**: grabar partidas humanas, ajustar el estilo y medir contra personas.
