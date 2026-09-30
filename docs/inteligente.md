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

## Semana 2: aprendizaje por refuerzo (PPO)

La imitación solo puede llegar al nivel de su maestro. Para superarlo, la red aprende de las
**consecuencias** de sus jugadas (`ia/entrenamiento/refuerzo.py`). Cada iteración:

1. **Juega** 600 partidas en paralelo (unas 80.000 decisiones en 8-11 segundos). Nuestra
   pareja elige al azar según sus probabilidades, para explorar. Enfrente se sienta un rival de
   la **liga**:

   | Rival | Frecuencia | Para qué |
   | --- | --- | --- |
   | ella misma | 35 % | juego contra sí misma; se aprende de los cuatro asientos |
   | una versión anterior | 25 % | no olvidar cómo ganar a rivales ya superados |
   | `reglas` (tres estilos) | 40 % | no perder contra el heurístico mientras explora |

2. **Premia.** +1 si su pareja gana la vaca y -1 si la pierde, más las recompensas
   intermedias elegidas. La cabeza de valor estima cómo va la vaca y **GAE** (λ = 0,95)
   reparte el mérito entre las jugadas: la ventaja de una jugada es cuánto mejor quedó la
   situación de lo que la red esperaba.
3. **Aprende con PPO**, que sube la probabilidad de las jugadas con ventaja positiva y baja la
   de las negativas:
   - con **recorte** 0,2, para que ningún lote de partidas cambie demasiado la política;
   - con un corte si la divergencia KL pasa de 0,03;
   - con un pequeño premio de **entropía** (0,005), para que siga explorando;
   - con un **ancla** de 0,02 hacia la red de imitación, para mantener un estilo de jugador
     de mus. Es pequeña a propósito: si estilo y fuerza chocan, manda la fuerza.

### Experimento 1: qué recompensa funciona mejor

Cuatro variantes con la misma semilla, los mismos rivales y 100 iteraciones cada una (60.000
partidas, unos 15 minutos). Después, 2.000 partidas de cada una contra cada estilo de `reglas`
(± 2 %):

| Recompensa | Qué añade | `reglas` | `reglas:agresivo` | `reglas:conservador` |
| --- | --- | --- | --- | --- |
| (imitación, de partida) | | 48,7 % | 50,3 % | 52,0 % |
| `vaca` | solo el resultado de la vaca | 73,7 % | 77,8 % | 74,0 % |
| `vaca+potencial` | cambio de la probabilidad de ganar la vaca en cada mano | 74,0 % | 77,5 % | 73,9 % |
| `vaca+tantos` | diferencia de tantos en cada mano | 73,7 % | 76,8 % | 74,1 % |
| **`vaca+farol`** | premio de 0,1 por ganar con "no quiero" teniendo una mano floja | **77,1 %** | **81,0 %** | **77,7 %** |

Entre ellas (2.000 partidas por enfrentamiento), `farol` gana a `vaca` (53,1 %), a
`potencial` (53,0 %) y a `tantos` (55,5 %). Las otras tres empatan entre sí.

**Por qué gana el farol.** Contamos cómo apuesta cada modelo contra `reglas` por cada 100
manos:

| Modelo | Faroles | Faroles entre sus apuestas | Tantos cobrados / pagados por "no quiero" |
| --- | --- | --- | --- |
| imitación | 3,0 | 3 % | 92,7 / 105,8 |
| `vaca` | 20,8 | 15 % | 94,2 / 106,2 |
| `vaca+farol` | 40,9 | 25 % | 102,2 / 99,4 |

- El refuerzo sin ayudas ya descubre solo que el heurístico (y su imitación) faroleaba
  demasiado poco.
- El premio del farol le ayuda a descubrirlo antes y más a fondo.

Las recompensas densas (`potencial` y `tantos`) no aportan nada: la cabeza de valor ya reparte
bien el mérito.

**Lección:** el bot optimiza exactamente lo que se premia. Una recompensa que cambia el objetivo
(como el farol) puede ayudar si empuja a explorar en la dirección correcta, pero hay que
**medirlo**. El riesgo es que solo funcione contra rivales que se retiran demasiado; lo
comprobará el bot cazador de la semana 3.

### Reproducirlo

```bash
python -m musarena.ia.entrenamiento.refuerzo --iteraciones 100 --partidas 600 \
    --recompensa vaca+farol --salida checkpoints/exp_vaca_farol
```

`checkpoints/<experimento>/registro.jsonl` guarda las métricas de cada iteración.

## Próximos pasos

- **Semana 2 (sigue)**: ajustar el premio del farol, entrenamiento largo con la mejor
  recompensa y probar redes más grandes.
- **Semana 3**: búsqueda al decidir y bot cazador. Meta: 65 % o más contra `reglas`, sin
  debilidades fáciles de explotar.
- **Semana 4**: grabar partidas humanas, ajustar el estilo y medir contra personas.
