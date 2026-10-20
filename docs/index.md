# Mus Arena

El **mus de 4 jugadores por parejas** en Python: un motor que no permite jugadas ilegales, una
web para jugar contra bots, un API para programar bots propios y un torneo automático con su
clasificación. Proyecto de la asignatura Inteligencia Artificial (CUNEF, 2026/2027).

<div class="grid cards" markdown>

- **Jugar ahora:** [mus-81o1.onrender.com](https://mus-81o1.onrender.com), sin instalar nada.
  Si nadie la ha usado en un rato, tarda unos segundos en despertar.
- **Programar un bot:** [tutorial de principio a fin](tutorial-bot.md).
- **Clasificación:** [torneo de todos los bots](clasificacion.md), actualizado automáticamente.
- **Reglas:** [las reglas que implementa el motor](reglas.md).

</div>

## Instalar la librería

```bash
pip install git+https://github.com/mus-cunef/mus      # o, desde el repositorio: pip install -e .
```

Una partida completa desde código, sin interfaz:

```python
from musarena.match import Match
from musarena.players import crear_jugador

mesa = [crear_jugador(t, seed=i) for i, t in enumerate(["inteligente", "reglas", "inteligente", "reglas"])]
partida = Match(mesa, mejor_de=3, seed=7)
ganadora = partida.play()
print("Gana la pareja", "A" if ganadora == 0 else "B", partida.state.vacas)
```

## Comandos

| Comando | Qué hace |
| --- | --- |
| `mus-play` | Jugar en la terminal (humanos y bots en cualquier asiento) |
| `mus-web` | La web en tu ordenador (`--red` para jugar desde el móvil) |
| `mus-arena A B -n 200` | Enfrentar dos bots en muchas partidas, con repartos duplicados |
| `mus-torneo` | Torneo de todos los bots y su clasificación |

## Los bots

| Bot | Cómo juega |
| --- | --- |
| `random` | Al azar entre las jugadas legales |
| `basico` | Unas pocas reglas según la fuerza de su mano |
| `reglas` | Heurístico con probabilidades exactas y creencias bayesianas (3 estilos) |
| `inteligente` | Red neuronal: imitación y aprendizaje por refuerzo (PPO) con liga y cazadores |
| `bots/*.py` | Los que programa cualquiera ([tutorial](tutorial-bot.md)) |

Código: [github.com/mus-cunef/mus](https://github.com/mus-cunef/mus).
