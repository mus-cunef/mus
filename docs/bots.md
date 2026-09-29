# Bots de Mus Arena

## Cómo se programa un bot

Un bot es una clase que hereda de `Bot` (o de `Player`) e implementa un único método:

```python
from musarena.player import Bot

class MiBot(Bot):
    tipo = "mibot"
    descripcion = "Siempre pide mus y nunca quiere"

    def choose_action(self, observation, legal_actions):
        # observation: lo que ve este jugador (sus cartas + información pública)
        # legal_actions: lista de acciones legales; hay que devolver una de ellas
        return legal_actions[0]
```

- El bot **nunca** ve el estado completo: solo su `Observation` (sus cartas, marcador, apuestas,
  declaraciones, historial de la mano, chat y las manos ya terminadas, con sus cartas y acciones).
- Si devuelve una acción que no está en `legal_actions`, el motor lanza `IllegalActionError` y
  la partida no se corrompe.
- `self.rng` es un `random.Random(seed)` propio: con la misma semilla, el bot juega igual.
- `on_hand_end(observation)` es opcional: sirve para aprender de cada mano terminada.
- Para poder usarlo en `mus-play` y `mus-arena`, se añade a `TIPOS` en
  `src/musarena/players/__init__.py`.

## Bots disponibles

| Tipo | Clase | Qué hace |
| --- | --- | --- |
| `random` | `RandomBot` | Elige al azar el tipo de acción y luego una concreta. |
| `basico` | `BasicBot` | Primera versión del heurístico: reglas fijas sobre la fuerza de su mano, sin mirar la mesa. Se conserva como referencia. |
| `reglas` | `HeuristicBot` | Heurístico avanzado: lee la mesa, calcula probabilidades exactas, decide según el marcador y aprende de cada rival. Tiene tres estilos: `equilibrado`, `agresivo` y `conservador`. |

### Resultados

2.000 partidas al mejor de 3 por enfrentamiento; margen de error de ±1-2 puntos.

| Enfrentamiento | Victorias del primero |
| --- | --- |
| `reglas` contra `basico` | **72,7 %** |
| `reglas` contra `random` | 91,8 % |
| `basico` contra `random` | 94,5 % |
| `reglas:conservador` contra `basico` | 75,5 % |
| `reglas:agresivo` contra `basico` | 67,7 % |
| `reglas` contra `reglas:agresivo` | 48,6 % |
| `reglas` contra `reglas:conservador` | 52,9 % |
| `reglas` contra `reglas` | 49,6 % (control) |

Los tres estilos tienen una fuerza parecida entre sí pero juegan distinto, así que dan
variedad para los torneos. `basico` gana al aleatorio algo más que `reglas` porque envida mucho
y el aleatorio quiere casi siempre; contra rivales que juegan con cabeza, `reglas` es muy
superior.

## Cómo piensa el bot `reglas`

El análisis está en `src/musarena/estrategia/`, separado del bot para que lo pueda usar
también el bot inteligente.

### 1. Los 330 tipos de mano (`estrategia/tipos.py`)

A 8 reyes, lo único que importa de una mano son los **rangos** de sus cartas (el 3 vale como el
rey y el 2 como el as). Las 91.390 manos posibles se agrupan en **330 tipos**, y de cada uno se
precalcula todo: su posición en cada lance, sus pares, su juego y su **fuerza** (probabilidad de
ganar a una mano al azar). Así el análisis es **exacto y rápido**.

### 2. Qué mano puede tener cada uno (`estrategia/creencias.py`)

Para cada uno de los otros tres jugadores, el bot guarda una probabilidad para cada tipo de
mano y la actualiza con **inferencia bayesiana** (multiplicar por la verosimilitud de lo visto
y normalizar):

| Lo que ve | Cómo lo usa |
| --- | --- |
| Sus propias cartas | Esas cartas no las tiene nadie más. |
| Declaración de pares y de juego | Elimina los tipos incompatibles (declarar es obligatorio y verdadero). |
| Quién cortó el mus y quién pidió | Quien corta suele llevar buena mano; quien pide mus, mala. |
| Envites, reenvidos, órdagos | Hacen más probables las manos fuertes en ese lance. |
| Pasos y "no quiero" | Hacen más probables las manos flojas. |
| "Quiero" | Manos medianas o fuertes; más fuertes cuanto mayor era la apuesta. |

Como hay faroles, las señales se tratan como **suaves**: una curva logística de la fuerza con un
suelo de farol (parámetros en `ModeloRival`).

### 3. Probabilidad de ganar el lance (`estrategia/evaluacion.py`)

Con esas creencias calcula la probabilidad **exacta** de que su pareja gane el lance, incluidos
los empates, que gana el más cercano a la mano. Un test lo compara con una simulación de
miles de repartos reales y coinciden con un error menor del 3 %. Además, cuando dice "gano con
el 70 %", gana alrededor del 70 % de las veces (probabilidades **calibradas**).

### 4. Decidir pensando en la vaca

`prob_vaca(propios, rivales)` estima la probabilidad de ganar la vaca desde el marcador. Para
querer o no querer, el bot compara cómo quedaría esa probabilidad en cada caso. Por eso un mismo
envite se quiere o no según el marcador: si un "no quiero" le hace perder la vaca, quiere con
cualquier mano.

### 5. Aprender de cada rival (`estrategia/lectura.py`)

Al final de cada mano se ven las cartas de todos, así que el bot comprueba con qué mano apostó o
quiso cada uno y estima su **tasa de farol**. Al rival que va de farol se le quiere más y al que
nunca farolea se le respetan los envites.

### Las reglas de decisión

| Momento | Regla (estilo `equilibrado`) |
| --- | --- |
| **Mus** | Corta si la mano está en el percentil 62 o más (siendo mano, 59). Si los rivales han pedido mus corta antes; si su compañero ha pedido mus, después. Con la 31 corta siempre. |
| **Descarte** | Prueba los 15 descartes posibles y elige el que deja la mejor mano media tras robar. |
| **Sin envite previo** | Envida si su pareja gana el lance con 66 % o más, más tantos cuanta más mano (de 2 a 10). Con 85 % o más, a veces **pasa para querer**, si detrás habla un rival. Si no envida, a veces va de **farol**, sobre todo si habla el último. |
| **Ante un envite** | Reenvida con 82 % o más. Si no, quiere cuando queriendo le queda más probabilidad de vaca que no queriendo. Si su compañero habla después, **decide solo con su mano**: si el compañero tiene mano, ya querrá él. |
| **Órdago** | Con la vaca igualada, a partir de 95 %; el umbral baja cuanto peor va la vaca (hasta 50 %). Ante un órdago rival, quiere si su probabilidad de ganar el lance supera la de ganar la vaca sin arriesgar. |

Cada decisión deja su explicación en `bot.razon`, por ejemplo: *"no quiero: yo solo gano solo
con 12 % (vaca 34 % queriendo, 48 % sin querer)"*.

## Lo que se probó (y lo que aprendimos)

Todo se midió con la arena, con miles de partidas por variante:

1. **Modelo de respuesta fijo del rival → 15 % contra `basico`.** La primera versión decidía
   reenvidos y órdagos suponiendo que el rival acepta con una probabilidad fija. Reenvidaba
   casi siempre.
2. **Respuesta del rival según su mano → 57 %.** Pero envidaba 40 en la chica porque creía que
   se lo querían manos cualquiera.
3. **Umbrales sobre la probabilidad propia (calibrada) → 73 %.** Para envidar, reenvidar y el
   órdago, umbrales; para querer, la comparación de la probabilidad de vaca.
4. **Elegir la cantidad con el modelo del rival → 67 %.** Peor, así que se descartó.

**Lección**: la probabilidad de ganar el lance es fiable; los modelos de *qué hará el rival*,
no tanto, y usarlos para decisiones arriesgadas amplifica sus errores. Es justo lo que el bot
entrenado puede aprender mejor a partir de partidas reales.

Otras mediciones: quitar "decidir solo con mi mano si mi compañero habla después" hace perder
unos 4 puntos. Los demás parámetros están cerca de su óptimo, porque cambiarlos mueve menos de
±2 puntos.

## Evaluar bots: la arena

```bash
mus-arena reglas basico -n 400 --seed 1
mus-arena reglas:agresivo reglas:conservador -n 400
```

Cada reparto se juega **dos veces intercambiando los asientos**, así las dos parejas reciben las
mismas cartas y la misma ventaja de ser mano, y la suerte pesa mucho menos. El resultado muestra
el porcentaje de victorias con su margen de error al 95 %. Desde Python, `enfrentar` también
acepta funciones `seed -> Player`, para probar bots con parámetros a medida:

```python
from musarena.arena import enfrentar
from musarena.players.heuristic_bot import HeuristicBot, estilo_con

prueba = lambda seed: HeuristicBot(seed=seed, estilo=estilo_con(corte=0.7))
print(enfrentar(prueba, "reglas", partidas=1000))
```

## Preparado para el bot inteligente

- **Grabar partidas**: `Match(..., al_decidir=funcion)` recibe cada `Decision` (asiento,
  observación, acciones legales y acción elegida), y cada `ResumenMano` guarda las cartas y
  todas las acciones de la mano. Con esto se construye un conjunto de datos de partidas humanas
  para que el bot aprenda a imitarlas.
- **Características de entrada** ya calculadas en `estrategia`:
  - la probabilidad de ganar cada lance con las creencias;
  - el percentil y el valor de la mano;
  - la fuerza en cada lance;
  - la probabilidad de vaca;
  - la tasa de farol de cada rival;
  - la respuesta esperada del rival (`respuesta_rival`).
- **Un rival de nivel** contra el que entrenar y medirse: `reglas`, con tres estilos distintos.
- **Velocidad**: el análisis usa numpy. Una partida entre bots `reglas` tarda unos 0,1 s por
  núcleo, y la arena puede repartirse entre varios procesos.
- **Punto de partida para ajustar**: todos los umbrales del heurístico están en `Estilo` y todos
  los del modelo de rival en `ModeloRival`, así que se pueden optimizar automáticamente.
