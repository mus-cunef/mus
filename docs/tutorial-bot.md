# Tutorial: tu primer bot, de principio a fin

En este tutorial programas un bot de mus, lo pruebas, juegas contra él y lo envías al
repositorio para que participe en el torneo. **No hace falta tocar el código del juego.**

## 1. Prepara el entorno

Necesitas Python 3.10 o superior y git.

```bash
git clone https://github.com/mus-cunef/mus
cd mus
python -m venv .venv
.venv\Scripts\activate          # Windows  (en Linux o macOS: source .venv/bin/activate)
pip install -e ".[dev]"
```

Comprueba que todo funciona jugando una partida entre bots:

```bash
mus-arena reglas random -n 20
```

## 2. Lo que recibe un bot

Un bot es una clase que hereda de [`Bot`](api/jugadores.md) y programa **un solo método**:

```python
def choose_action(self, observation, legal_actions):
    ...
    return una_de_las_acciones_de_legal_actions
```

- **`observation`** ([`Observation`](api/observacion.md)) es todo lo que sabe tu jugador, y
  solo eso:
  - sus cartas (`observation.cartas`);
  - la fase (`mus`, `descarte` o `lance`) y el lance en juego (`grande`, `chica`, `pares`,
    `juego` o `punto`);
  - quién es mano y la apuesta en curso;
  - el marcador (tantos y vacas);
  - las declaraciones de pares y juego, y el historial público de la mano.

  **Nunca** recibe las cartas de los demás.

- **`legal_actions`** es la lista de jugadas permitidas en ese momento ([acciones](api/acciones.md)):
  `Mus`, `NoHayMus`, `Descarte(cartas)`, `Paso`, `Envido(n)`, `Reenvido(n)`, `Ordago`, `Quiero`
  y `NoQuiero`. Tu bot **tiene que devolver una de ellas**.

Si devuelve otra cosa, lanza un error o tarda más de 5 segundos, **pierde la partida**, pero el
torneo sigue.

## 3. Escribe el bot

Crea el archivo `bots/mi_bot.py`. Este ejemplo corta el mus con buena mano, se queda las
figuras al descartarse y envida solo con manos fuertes. Usa las tablas de la librería
([estrategia](api/estrategia.md)), que dan la fuerza de cualquier mano en cada lance:

```python
from musarena.actions import Descarte, Envido, Mus, NoHayMus, NoQuiero, Paso, Quiero
from musarena.estrategia.tipos import FUERZA, indice_de
from musarena.estrategia.valor import PERCENTIL
from musarena.player import Bot


class MiBot(Bot):
    tipo = "mi_bot"          # el nombre con el que aparece en el torneo
    descripcion = "Mi primer bot de mus"

    def choose_action(self, observation, legal_actions):
        tipo = indice_de(observation.cartas)        # cuál de los 330 tipos de mano tengo

        if Mus() in legal_actions:                    # fase de mus
            return NoHayMus() if PERCENTIL[tipo] > 0.6 else Mus()

        if isinstance(legal_actions[0], Descarte):    # fase de descarte
            tirar = [c for c in observation.cartas if c.rango < 10]
            return Descarte(frozenset(tirar or observation.cartas))

        fuerza = FUERZA[observation.lance][tipo]      # 0 = la peor mano, 1 = la mejor
        if Quiero() in legal_actions:                 # me han envidado
            return Quiero() if fuerza > 0.75 else NoQuiero()
        if fuerza > 0.85 and Envido() in legal_actions:
            return Envido()
        return Paso()
```

Consejos:

- Si tu bot usa el azar, usa **`self.rng`** (el generador del `Bot`), no el módulo `random`: así
  las partidas se pueden repetir con la misma semilla.
- `print(observation)` te enseña todo lo que ves en cada momento.
- [`bots/prudente.py`](https://github.com/mus-cunef/mus/blob/main/bots/prudente.py) es otro
  ejemplo completo.

## 4. Pruébalo

```bash
mus-arena bots/mi_bot.py random -n 200 -p 0     # contra el aleatorio: debería ganar casi siempre
mus-arena bots/mi_bot.py reglas -n 200 -p 0     # contra el heurístico
mus-torneo -n 50                                # el torneo completo, con tu bot dentro
pytest tests/test_bots_nuevos.py                # el examen que pasará en la CI
```

El examen automático comprueba que tu bot:

- se carga y tiene un `tipo` propio;
- juega partidas completas contra `random` y `reglas` **sin faltas** (sin errores, sin jugadas
  ilegales y sin tardar más de 2 segundos por jugada);
- es reproducible con la misma semilla.

## 5. Juega contra él

```bash
mus-play --jugadores humano,bots/mi_bot.py,reglas,bots/mi_bot.py
```

En la [web](web.md) también puedes elegirlo en cualquier asiento, una vez fusionado en el
repositorio.

## 6. Envíalo por Pull Request

1. Haz un *fork* del repositorio en GitHub (o una rama, si eres del equipo).
2. Crea una rama, añade tu archivo y súbela:

   ```bash
   git checkout -b bot/mi-bot
   git add bots/mi_bot.py
   git commit -m "Añade el bot mi_bot"
   git push -u origin bot/mi-bot
   ```

3. Abre la **Pull Request** contra `main`. La CI pasa todos los tests, también el examen de tu
   bot. Si algo falla, verás en la PR qué ha sido.
4. Cuando la CI está en verde y el equipo la revisa, se fusiona. Desde ese momento tu bot
   **juega solo en el torneo** y aparece en la [clasificación](clasificacion.md), que se
   actualiza automáticamente.

## 7. Para ir más lejos

- Lee cómo piensan [los bots incluidos](bots.md): el heurístico `reglas` usa probabilidades
  exactas y creencias bayesianas sobre las manos de los demás.
- El [bot inteligente](inteligente.md) es una red neuronal entrenada con aprendizaje por
  refuerzo: es el rival a batir.
- Toda la referencia del API está en la sección **Referencia del API**.
