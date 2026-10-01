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
  entrenamiento/    datos, imitación y refuerzo con PPO (necesita PyTorch)
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

### Experimento 2: cuánto premio por farol

Con el mismo método, cuatro variantes del farol. Contra `reglas` empatan todas (entre el 76 % y
el 81 % contra los tres estilos, ± 1,8 %), pero **entre ellas gana el premio más alto (0,2)**:

| `farol 0,2` contra | Victorias (2.000 partidas) |
| --- | --- |
| farol 0,05 | 55,5 % |
| farol 0,1 | 52,2 % |
| farol 0,1 + potencial | 55,0 % |

El premio del farol no sobreajusta a `reglas`. Un bot que farolea más gana también a bots de
refuerzo que ya saben farolear. Queda por comprobar con el bot cazador y con humanos.

### Experimento 3: lo que dice un descarte

Tras el mus, las manos no son manos al azar: cada uno se queda lo bueno. Medimos 124.704
descartes de 20.000 partidas (percentil medio de la mano después; una mano al azar es 0,50):

| Se descarta de | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- |
| Percentil medio | 0,79 | 0,70 | 0,67 | 0,59 |
| Tiene pares | 100 % | 70 % | 64 % | 61 % |

¿Importan también la posición o la ronda de mus? Medimos cuánta información aporta cada factor
para adivinar la mano. Se mide en **bits**, en datos que no se usaron para medir las tablas;
menos bits significa adivinar mejor:

| Modelo | Bits | Ganancia |
| --- | --- | --- |
| Mano al azar | 7,72 | — |
| **Número de cartas** | **6,87** | **0,85** |
| Número de cartas + posición | 6,90 | 0,82 |
| Número de cartas + ronda | 6,87 | 0,85 |

- Solo importa el número de cartas.
- La posición no cambia nada (con bots; los humanos quizá sí).
- Las segundas rondas son menos del 1 % de los descartes.

**Decisión:** la tabla por número de cartas (`estrategia/descartes.py`, medida y regenerable)
entra en las creencias bayesianas. Además, cada jugador recuerda las cartas que tiró mientras
siguen en la pila (`Observation.mis_descartes`) y las descuenta de las manos posibles de los
demás. Resultados:

- **`reglas` con la tabla gana a `reglas` sin ella el 52,8 % ± 1,5 %** (4.000 partidas).
- La red de refuerzo **no lo estaba aprendiendo sola**. Cambiando solo el dato "el rival se
  descartó de 1 carta" por "de 4", apenas cambia su decisión (1,5 puntos en querer, y en
  sentido contrario).
- Lo más fino (la posición, el estilo de cada jugador) se deja a la red, que lo podrá aprender
  de partidas humanas.

Como cambian las creencias, cambia lo que ve la red. Por eso se regeneran la imitación y el
refuerzo.

### Entrenamiento largo (v2): el modelo actual

Con la tabla de descartes en las creencias:

1. Imitación del nuevo `reglas`: acierta el 87,6 % de sus jugadas.
2. 300 iteraciones de refuerzo con `vaca+farol` 0,2: 180.000 partidas, unos 45 minutos.

Victorias contra el nuevo `reglas`, midiendo cada 20 iteraciones (400 partidas, ± 4 %):

| Iteración | 20 | 60 | 100 | 140 | 180 | 220 | 260 | 300 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Victorias | 68,2 % | 72,2 % | 73,5 % | 76,2 % | 75,5 % | 77,2 % | **80,0 %** | 77,2 % |

**Interpretación:**
- Hasta la iteración 100 va como los experimentos cortos.
- Después sigue subiendo despacio, sin tocar techo, así que entrenar más tiempo compensa.
- Desde la 240 se mueve entre el 77 % y el 80 %.

**Confirmación** (2.000 partidas por fila, ± 1,7 %):

| Modelo | `reglas` | `reglas:agresivo` | `reglas:conservador` |
| --- | --- | --- | --- |
| v1 (`vaca+farol` 0,2, 100 iteraciones, sin tabla de descartes) | 75,7 % | 81,0 % | 76,9 % |
| v2, iteración 240 | 79,9 % | 82,3 % | 80,4 % |
| v2, iteración 260 | 79,8 % | 83,6 % | 81,4 % |
| v2, iteración 280 | 80,2 % | 82,4 % | 80,3 % |
| **v2, iteración 300** | **81,2 %** | **84,1 %** | **81,2 %** |

Entre ellos (2.000 partidas por enfrentamiento, ± 2,2 %), los cuatro puntos de control del v2
empatan (del 49 % al 51 %) y todos ganan al v1 (del 53,4 % al 55,9 %; la iteración 300 es la
que más le gana).

**Interpretación:**
- El ~80 % era real.
- La tabla de descartes y el entrenamiento más largo mejoran tanto contra `reglas` como cara a
  cara.
- Entre las iteraciones 240 y 300 la mejora ya es del orden del ruido, así que nos acercamos al
  techo de esta red con esta receta.

Este v2 (iteración 300) fue el modelo del paquete hasta el v3.

### Entrenamiento más largo (v3)

Se siguió entrenando el v2 (iteración 300) **500 iteraciones más**, con la misma receta y el
estilo anclado a la imitación (`--ancla checkpoints/imitacion_v2.npz`). Son 300.000 partidas
más, unos 90 minutos.

Durante el entrenamiento (400 partidas, siempre los mismos repartos; el v2 sacaba el 77,2 % en
ellos):

| Iteración | 25 | 100 | 175 | 225 | 300 | 325 | 400 | 450 | 500 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Victorias | 77,2 % | 76,0 % | 78,0 % | 80,2 % | 80,8 % | 82,2 % | 80,8 % | 78,2 % | 77,2 % |

**Confirmación** (2.000 partidas por fila, ± 1,7 %):

| Modelo | `reglas` | `reglas:agresivo` | `reglas:conservador` | Cara a cara contra el v2 |
| --- | --- | --- | --- | --- |
| v2 (iteración 300) | 81,2 % | 84,1 % | 81,2 % | — |
| v3, iteración 325 | 82,2 % | 84,7 % | 82,9 % | 55,1 % |
| v3, iteración 400 | 80,7 % | 83,2 % | 78,8 % | 55,6 % |
| **v3, iteración 500** | **81,0 %** | **83,8 %** | **81,5 %** | **56,9 %** |

Entre ellos, los tres puntos de control del v3 empatan (del 48,4 % al 50,4 %).

**Interpretación:**
- **Contra `reglas` ya no se mejora.** El v3 saca lo mismo que el v2 (un 81-84 %).
  `reglas` ha dejado de ser una buena regla de medir: el bot ya le gana casi todo lo que se le
  puede ganar con estas cartas.
- **Cara a cara, el v3 gana claramente al v2** (del 55 % al 57 %, ± 2,2 %). Ha seguido
  aprendiendo cosas que sirven contra rivales fuertes, aunque no se noten contra el
  heurístico.
- **A partir de ahora la medida principal tiene que ser el cara a cara** contra la mejor
  versión anterior, y más adelante el bot cazador y las partidas humanas.

El modelo del paquete es el **v3, iteración 500**: es el que más gana al v2 y empata con los
otros puntos de control del v3.

## Próximos pasos

- **Semana 2 (sigue)**:
  - medir el progreso cara a cara contra la mejor versión anterior (contra `reglas` ya no se
    nota);
  - probar redes más grandes y más partidas por iteración.
- **Semana 3**: búsqueda al decidir y bot cazador. Meta: 65 % o más contra `reglas`, sin
  debilidades fáciles de explotar.
- **Semana 4**: grabar partidas humanas, ajustar el estilo y medir contra personas.
