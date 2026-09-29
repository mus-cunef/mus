# Mus Arena

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Proyecto de la asignatura **Inteligencia Artificial** (3º MAT, CUNEF Universidad, 2026/2027).
El **mus clásico de 4 jugadores por parejas**: motor en Python, interfaz web para jugar entre humanos
o contra bots, y una arena donde compiten inteligencias artificiales.

**Jugar:** próximamente · **Documentación:** próximamente · **Clasificación:** próximamente

## ¿Qué es esto?

- **Librería Python instalable** (`musarena`): reglas del mus, estado de la partida y validación de jugadas.
- **Mesas flexibles**: cada uno de los 4 asientos puede ocuparlo un humano o un bot.
  - 4 humanos
  - 2 humanos contra 2 bots
  - un humano con un bot de compañero contra 2 bots
  - 4 bots
- **Varios bots** de distinto nivel: desde uno aleatorio hasta uno que aprende a envidar y a echarse faroles.
- **API de jugadores**: cualquiera puede escribir su propio bot heredando de `Player`, sin tocar el motor.
- **Interfaz web** para jugar desde el navegador sin instalar nada.
- **Torneo automático** (GitHub Actions) que enfrenta a parejas de bots y publica una clasificación.

El mus tiene **información oculta** (no ves las cartas de los demás, ni las de tu compañero) y **faroles**.
Por eso cada jugador solo recibe **su observación**, nunca el estado completo de la mesa.

## El juego

- **4 jugadores** en **2 parejas**; los compañeros se sientan enfrente.
- **Baraja española de 40 cartas**, 4 cartas por jugador.
- **Fase de mus**: si todos dicen "mus", se descartan y roban; si alguien corta, empiezan los lances.
- **Lances**, en este orden:
  1. **Grande**: gana la jugada más alta.
  2. **Chica**: gana la jugada más baja.
  3. **Pares**: pares, medias o duples.
  4. **Juego** (31 o más), o **Punto** si nadie tiene juego.
- **Apuestas**: envite, *quiero*, *no quiero*, subir la apuesta y **órdago**.
- Cada **vaca** se gana al llegar a **40 tantos** (o con un órdago).
- La partida se juega **al mejor de 3 vacas** o **al mejor de 5 vacas**.
- **Chat abierto**: todos los jugadores de la mesa pueden escribir y leer mensajes.

Las reglas detalladas (8 reyes, desempates por mano, apuestas, recuento…) están en
[`docs/reglas.md`](docs/reglas.md).

## Tipos de jugador

| Jugador       | Descripción                                                        | Estado        |
| ------------- | ------------------------------------------------------------------ | ------------- |
| `humano`      | Juega una persona desde la terminal (y más adelante desde la web)  | listo         |
| `random`      | Elige una jugada legal al azar                                     | listo         |
| `reglas`      | Heurísticas: corta y envida según la fuerza de su mano, con faroles | listo         |
| `inteligente` | Entrenado para jugar como un humano                                | próximamente  |

Cómo funcionan los bots y cómo programar uno nuevo: [`docs/bots.md`](docs/bots.md).

## Instalación

```bash
git clone https://github.com/mus-cunef/mus
cd mus
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Jugar

```bash
mus-play                                            # pregunta quién ocupa cada asiento
mus-play --jugadores humano,reglas,reglas,reglas    # tú contra tres bots
mus-play --jugadores reglas,random,reglas,random    # solo bots, para mirar
mus-arena reglas random -n 200                      # enfrenta dos bots en 200 partidas
```

## Estructura

```
src/musarena/          motor del juego, API Player, arena
src/musarena/players/  jugadores: humano en terminal y bots
tests/            tests (pytest)
web/              interfaz web
docs/             documentación
```

## Contribuir

1. Crea una rama: `git checkout -b feature/<tarea>`
2. Haz commits pequeños y claros.
3. Abre una Pull Request; otro miembro del equipo la revisa.
4. Solo se fusiona si los tests pasan.

## Equipo

- Pablo Noelle
- Sara Trapero
- Ines Perales

## Licencia

[MIT](LICENSE)
