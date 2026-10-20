# Bots del torneo

Cualquier archivo `.py` de esta carpeta que defina **un bot** (una clase que herede de
`musarena.player.Bot` o `Player`) **entra solo en el torneo** (`mus-torneo`). Así se programa y
se prueba un bot propio sin tocar la librería.

1. Copia [`prudente.py`](prudente.py) con otro nombre, por ejemplo `bots/mi_bot.py`.
2. Cambia el nombre de la clase y su `tipo`, y programa `choose_action(observation,
   legal_actions)`: recibe solo lo que ve el jugador y devuelve una de las acciones legales.
3. Pruébalo:

   ```bash
   mus-arena bots/mi_bot.py reglas -n 200 -p 0     # contra el heurístico
   mus-torneo                                      # el torneo completo, con tu bot
   ```

**Antes de fusionarlo**, la CI examina automáticamente cada bot de esta carpeta
(`tests/test_bots_nuevos.py`): que se cargue y tenga un `tipo` propio, que juegue partidas
completas contra `random` y `reglas` **sin ninguna falta** (sin errores, sin jugadas ilegales y
sin tardar más de 2 segundos por jugada) y que sea reproducible con la misma semilla (usa
`self.rng`, no `random`). Puedes pasarlo tú antes: `pytest tests/test_bots_nuevos.py`.

En el torneo, un bot que falla, se cuelga o juega ilegal **pierde esa partida** y aparece en la
columna de faltas, pero el torneo sigue.

Reglas: el bot no puede ver el estado completo (solo su `Observation`), y si devuelve una
acción ilegal la partida se detiene con `IllegalActionError`. Los archivos que empiezan por `_`
no participan. Si un archivo tiene varias clases de bot, se indica cuál con
`bots/mi_bot.py:MiClase`.
