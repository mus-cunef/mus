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
  declaraciones, historial de la mano, chat y las cartas enseñadas en manos ya terminadas).
- Si devuelve una acción que no está en `legal_actions`, el motor lanza `IllegalActionError` y
  la partida no se corrompe.
- `self.rng` es un `random.Random(seed)` propio: con la misma semilla, el bot juega igual.
- Para poder usarlo en `mus-play` y `mus-arena`, se añade a `TIPOS` en
  `src/musarena/players/__init__.py`.

## Bots disponibles

### `random` (`RandomBot`)

Elige al azar primero el **tipo** de acción (paso, envido, órdago…) y luego una acción concreta
de ese tipo. Si eligiera directamente de la lista casi siempre envidaría, porque hay 39
cantidades de envido y un solo "paso". Sirve de rival de referencia.

### `reglas` (`HeuristicBot`)

Toma cada decisión a partir de la **fuerza** de su mano (`musarena.fuerza`): la probabilidad
exacta de ganar a una mano rival al azar en cada lance. Se calcula enumerando las 330
combinaciones de rangos posibles (a 8 reyes el 3 vale como el rey y el 2 como el as), cada una
con su número de manos reales.

| Momento | Regla |
| --- | --- |
| **Mus** | Puntúa la mano: 31 → 3, otro juego → 1, duples → 3, medias → 2, par → 0,5 (+0,5 si es de reyes), grande o chica con fuerza > 0,85 → +1 cada una. Corta si llega a **3**. |
| **Descarte** | "A reyes": se queda con los reyes y las parejas. "A chica" si lleva 2 o más ases y menos de 2 reyes: se queda con ases, cuatros y parejas. Siempre tira al menos una carta. |
| **Probabilidad de ganar el lance** | Contra *k* rivales, `p = fuerza^k`. Si el compañero también juega el lance, `p = 1 − (1 − p)·(1 − 1/(k+1))`. Si el rival ha envidado, `p = p^1,5`. |
| **Sin envite previo** | `p ≥ 0,92` y alguien cerca de 40 → órdago; `p ≥ 0,8` → envido de 2 a 10 tantos; `p ≥ 0,62` → envido; si no, paso (o farol con probabilidad 8 %). |
| **Ante un envite** | `p ≥ 0,88` → reenvido (dobla la apuesta); si no, quiere cuando `(2p − 1)·apuesta > −deje`, es decir, cuando querer vale más que perder el deje, con un 5 % de margen. |
| **Ante un órdago** | Quiere con `p ≥ 0,72`, o con `p ≥ 0,45` si el rival está a 6 tantos o menos de ganar la vaca. |

Resultados (`mus-arena`, 400 partidas al mejor de 3):

| Enfrentamiento | Victorias |
| --- | --- |
| `reglas` contra `random` | 93,5 % |
| `reglas` contra `reglas` | 50 % (control) |
| `random` contra `random` | 51,5 % (control) |

## Evaluar bots: la arena

```bash
mus-arena reglas random -n 200 --seed 1
```

Cada reparto se juega **dos veces intercambiando los asientos**, así las dos parejas reciben las
mismas cartas y la misma ventaja de ser mano, y la suerte pesa mucho menos. El resultado muestra
el porcentaje de victorias con su margen de error al 95 %.

## Preparado para el bot inteligente

- **Grabar partidas**: `Match(..., al_decidir=funcion)` recibe cada `Decision` (asiento,
  observación, acciones legales y acción elegida). Con esto se puede construir un conjunto de
  datos de partidas humanas para que el bot aprenda a imitarlas.
- **Características de entrada**: `fuerza(lance, cartas)` para los cinco lances, más el
  marcador, la fase y el historial de la `Observation`.
- **Simulación rápida**: el motor juega unas 300-350 partidas por segundo, suficiente para
  generar partidas de entrenamiento contra `reglas` o contra sí mismo.
- **Medir el progreso**: añadir el bot a `TIPOS` y enfrentarlo en la arena contra `reglas`.
