# Contexto del proyecto para Claude

## Qué es
**Mus Arena**: proyecto de la asignatura Inteligencia Artificial (CUNEF, 2026/2027).
Mus de 4 jugadores por parejas en Python, con interfaz web, API para bots y torneo automático.
Equipo de 3 personas. Repo: https://github.com/mus-cunef/mus

## Documentos que hay que respetar
- `docs/reglas.md`: **reglas oficiales del juego**. Son la fuente de verdad. Si el código y este documento
  no coinciden, manda el documento; pregunta antes de cambiarlo.
- La rúbrica de la asignatura valora:
  - una librería Python instalable con la que se pueda jugar una partida completa desde código;
  - que no se puedan hacer jugadas ilegales, que el juego sea robusto y que cada jugador reciba solo
    su información;
  - un API público de bots que no obligue a tocar el motor;
  - tests automáticos en cada Pull Request;
  - ramas + PRs y un repo ordenado.

## Arquitectura
```
src/musarena/
  cards.py      Carta, Palo, Baraja (40 cartas, 8 reyes)
  hands.py      evaluación de grande, chica, pares, juego y punto
  actions.py    acciones (Mus, NoHayMus, Descarte, Paso, Envido(n), Quiero, NoQuiero, Ordago…)
  state.py      estado completo de la mano / vaca / partida (inmutable o copiable)
  engine.py     reglas: legal_actions(state), apply(state, action) -> nuevo estado
  observation.py  vista parcial de un asiento (solo sus cartas + información pública)
  chat.py       chat abierto de la mesa
  player.py     clase abstracta Player: choose_action(observation, legal_actions) -> Action;
                Bot (Player con rng propio y `tipo` para el registro)
  players/      HumanTerminalPlayer, RandomBot ("random"), BasicBot ("basico"), HeuristicBot
                ("reglas", con estilos) y el registro TIPOS / crear_jugador(tipo) que usan la
                CLI, la arena y (más adelante) la web
  fuerza.py     probabilidad exacta de ganar a una mano al azar en cada lance
  estrategia/   análisis compartido por los bots (numpy): 330 tipos de mano, valor y
                descartes, creencias bayesianas sobre las manos ajenas, probabilidad de ganar
                cada lance y la vaca, lectura de rivales. Solo usa la Observation.
  ia/           bot inteligente: catálogo de 40 acciones, codificación de la Observation,
                red en numpy (jugar) y entrenamiento con PyTorch (extra [ia]); pesos en
                ia/modelos/. Plan y resultados en docs/inteligente.md
  match.py      Match: orquesta una partida (mejor de 3 o de 5 vacas) con 4 Player;
                `al_decidir` recibe cada Decision (para grabar partidas y entrenar)
  arena.py      enfrenta dos tipos de bot en muchas partidas (`mus-arena`)
  cli.py        punto de entrada `mus-play` (humanos y bots en cualquier asiento)
tests/          pytest
```

Principios:
- El **motor no sabe** si un asiento es humano o bot: solo llama a `Player.choose_action`.
- Un jugador **solo recibe su `Observation`**, nunca el `State` completo.
- Toda acción se valida: una acción ilegal lanza `IllegalActionError`, sin corromper el estado.
- Aleatoriedad con `random.Random(seed)` inyectable, para que los tests sean reproducibles.
- Código con type hints, docstrings en español y nombres claros.

## Convenciones
- Python ≥ 3.10, layout `src/`, `pyproject.toml`, instalable con `pip install -e ".[dev]"`.
- Tests con `pytest`; lint con `ruff`.
- Cada cambio en una rama (`feature/...`) y Pull Request. **Nunca hacer push directo a `main`.**
- Commits pequeños con mensajes en español.
- Explica las decisiones de diseño: el equipo tiene que poder defenderlas oralmente.
