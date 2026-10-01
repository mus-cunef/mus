# Contexto del proyecto para Claude

Este archivo es la **memoria compartida del equipo**. Claude lo lee al abrir el repo, sea cual sea
el ordenador o la cuenta. Todo lo que Claude necesite saber para trabajar igual con cualquiera del
equipo tiene que estar aquí o en `docs/`, no en la memoria local de un ordenador. Cuando se tome
una decisión importante o cambie el estado del proyecto, **actualiza este archivo en la misma PR**.

## Qué es
**Mus Arena**: proyecto de la asignatura Inteligencia Artificial (CUNEF, 2026/2027).
Mus de 4 jugadores por parejas en Python, con interfaz web, API para bots y torneo automático.
Repo: https://github.com/mus-cunef/mus

**Equipo:** Pablo, Sara e Inés. Revisan el código juntos, así que una PR se puede fusionar en
cuanto la CI está en verde y quien trabaja lo pide; no hace falta esperar a otra revisión.
Todos tienen que poder **defender oralmente** cualquier parte del proyecto, así que explica
siempre el porqué de las decisiones.

## Documentos que hay que respetar
- `docs/reglas.md`: **reglas oficiales del juego**. Son la fuente de verdad. Si el código y este
  documento no coinciden, manda el documento. **Pregunta antes de cambiarlo.**
- `docs/bots.md`: cómo funcionan los bots `random`, `basico` y `reglas`, y cómo escribir uno.
- `docs/inteligente.md`: plan del bot inteligente, experimentos y resultados medidos. Es el
  cuaderno de laboratorio: cada experimento nuevo se apunta ahí con sus números.
- La rúbrica de la asignatura valora:
  - una librería Python instalable con la que se pueda jugar una partida completa desde código;
  - que no se puedan hacer jugadas ilegales, que el juego sea robusto y que cada jugador reciba
    solo su información;
  - un API público de bots que no obligue a tocar el motor;
  - tests automáticos en cada Pull Request;
  - ramas + PRs y un repo ordenado.

## Arquitectura
```
src/musarena/
  cards.py      Carta, Palo, Baraja (40 cartas, 8 reyes; mazo + pila de descartes)
  hands.py      evaluación de grande, chica, pares, juego y punto
  actions.py    acciones (Mus, NoHayMus, Descarte, Paso, Envido(n), Quiero, NoQuiero, Ordago…)
  state.py      estado completo de la mano / vaca / partida (copiable con State.copiar)
  engine.py     reglas: legal_actions(state), apply(state, action) -> nuevo estado
  observation.py  vista parcial de un asiento: sus cartas, sus descartes aún en la pila
                (mis_descartes) e información pública
  chat.py       chat abierto de la mesa
  player.py     clase abstracta Player: choose_action(observation, legal_actions) -> Action;
                Bot (Player con rng propio y `tipo` para el registro)
  players/      HumanTerminalPlayer, RandomBot ("random"), BasicBot ("basico"), HeuristicBot
                ("reglas", con estilos), SmartBot ("inteligente", admite
                "inteligente:ruta.npz") y el registro TIPOS / crear_jugador(tipo)
  fuerza.py     probabilidad exacta de ganar a una mano al azar en cada lance
  estrategia/   análisis compartido por los bots (numpy), solo a partir de la Observation:
    tipos.py      los 330 tipos de mano (el palo no importa) y tablas por tipo
    valor.py      valor y percentil de una mano; valor esperado tras un descarte
    descartes.py  tabla MEDIDA de cómo queda una mano tras descartarse de n cartas
                  (tras_descarte.npz; se regenera con python -m musarena.estrategia.descartes)
    creencias.py  creencias bayesianas sobre la mano de cada uno (declaraciones, descartes,
                  mus, apuestas)
    evaluacion.py probabilidad de ganar cada lance y la vaca
    lectura.py    lectura de rivales (cuánto farolea cada uno)
  ia/           bot inteligente (ver docs/inteligente.md):
    acciones.py     catálogo fijo de 40 acciones + máscara de legales
    codificacion.py Observation -> vector de 163 números, relativo a quien decide
    red.py          la red en numpy (para jugar no hace falta PyTorch)
    modelos/        el modelo elegido (inteligente.npz), que viaja con el paquete
    entrenamiento/  datos.py (partidas -> ejemplos), imitacion.py y refuerzo.py (PPO);
                    necesitan el extra [ia] (PyTorch)
  match.py      Match: orquesta una partida (mejor de 3 o de 5 vacas) con 4 Player;
                `al_decidir` recibe cada Decision (para grabar partidas y entrenar)
  arena.py      enfrenta dos bots en muchas partidas con repartos duplicados (`mus-arena`)
  cli.py        punto de entrada `mus-play` (humanos y bots en cualquier asiento)
tests/          pytest (helpers.py tiene utilidades comunes)
```

Principios:
- El **motor no sabe** si un asiento es humano o bot: solo llama a `Player.choose_action`.
- Un jugador **solo recibe su `Observation`**, nunca el `State` completo. Hay tests que
  comprueban que no se filtra ninguna carta ajena, tampoco a la red.
- Toda acción se valida: una acción ilegal lanza `IllegalActionError`, sin corromper el estado.
- Aleatoriedad con `random.Random(seed)` inyectable, para que tests y experimentos sean
  reproducibles.
- Código con type hints, docstrings en español y nombres claros.

## Convenciones
- Python ≥ 3.10, layout `src/`, `pyproject.toml`. Instalación: `pip install -e ".[dev]"`, y
  `pip install -e ".[dev,ia]"` para entrenar (PyTorch de CPU: no tenemos GPU NVIDIA).
- Tests con `pytest`; lint con `ruff check src tests`. Los dos tienen que pasar antes de cada
  commit. La CI de GitHub los pasa en cada PR.
- Cada cambio en una rama (`feature/...`) creada desde `main` actualizado, y Pull Request.
  **Nunca hacer push directo a `main`.** Antes de hacer push, confirmar con quien trabaja.
- Commits pequeños con mensajes en español.
- Tras fusionar una PR: actualizar `main` local y borrar la rama (en GitHub y en local).
- Si no está instalado `gh`, las PR se crean y se fusionan con la API de GitHub usando la
  credencial de git (`git credential fill`).
- Windows: la terminal es PowerShell. `Set-Content` añade BOM (mejor escribir con Python o con
  las herramientas de edición), y el paralelismo usa `ProcessPoolExecutor` (las funciones que
  se envían a otros procesos tienen que estar a nivel de módulo, no pueden ser lambdas).

## Cómo trabajamos
- **Se mide todo.** Una idea nueva para un bot solo se queda si gana en la arena con muchas
  partidas y repartos duplicados. Los márgenes de error al 95 % son de unos ±2 % con 2.000
  partidas y de ±1,5 % con 4.000; una diferencia menor que eso no demuestra nada.
- **Un cambio cada vez**, con el resto igual (misma semilla, mismos rivales) para compararlo.
- Los resultados de cada experimento se apuntan en `docs/inteligente.md` (o `docs/bots.md`).
- Explica las decisiones para que el equipo las pueda defender.

## Decisiones tomadas (y por qué)
- **Bot inteligente: el más fuerte posible y que juegue como un humano; si chocan, manda la
  fuerza.** Solo CPU (sin GPU), PyTorch para entrenar y numpy para jugar.
- **El conocimiento de mus lo aprende el bot inteligente**, no se programa en `reglas`. El
  heurístico se mantiene simple. Si alguien aporta una observación de experto (por ejemplo,
  "al descartarse la gente se queda reyes, o rey y caballo"), no se añade como regla: se
  comprueba si la red ya lo hace y, si no, cómo lo puede aprender (refuerzo o partidas
  humanas). Excepción: la tabla medida de descartes en las creencias.
- **Descartes**: solo importa de cuántas cartas se descarta cada uno. La posición y la ronda no
  aportan información (medido). La red ve el número de cartas y puede afinar lo demás.
- **Regla de la baraja**: los descartes se apartan y no se barajan mientras quede mazo. Si el
  mazo se acaba a mitad de un robo, se barajan todos los descartes, también los que acaba de
  tirar ese jugador (`docs/reglas.md`, punto 3.4).
- **Mano corrida** en la primera mano de la partida: se sortea quién empieza y la mano se corre
  (pedir mus es pasar la mano) hasta que alguien corta, que es la mano. Si pasan los cuatro hay
  mus y la mano corre un puesto más (`docs/reglas.md`, punto 3.6). `nueva_partida()` lo hace por
  defecto; con `nueva_partida(mano=k)` la mano queda fijada (útil en tests). No cambia las
  probabilidades, así que los bots no se tocaron.
- **Recompensa del refuerzo**: `vaca+farol` con premio 0,2. Es la que más gana, también
  entre bots de refuerzo. Las recompensas densas (`tantos`, `potencial`) no aportaron nada.
- **Lección del heurístico**: calcular el valor esperado con un modelo de "qué hará el rival"
  empeora el bot. Funcionan mejor los umbrales sobre una probabilidad propia bien calibrada.

## Estado actual (2026-10-01)
- En `main`: motor completo, bots `random`, `basico`, `reglas` (con estilos) e `inteligente`,
  arena en paralelo, imitación y refuerzo (PPO) con liga de rivales, y tabla de descartes en las
  creencias.
- Bot inteligente: semana 1 (imitación, 49 % contra `reglas`) y semana 2 (refuerzo) hechas.
  El modelo del paquete (`ia/modelos/inteligente.npz`) es el **v3**: el v2 más 500
  iteraciones de refuerzo, confirmado con 2.000 partidas. Gana el 81,0 % contra `reglas`, el
  83,8 % contra `reglas:agresivo` y el 81,5 % contra `reglas:conservador`, y el **56,9 % cara a
  cara contra el v2**. Contra `reglas` ya no se nota la mejora (el v2 sacaba lo mismo): desde
  ahora el progreso se mide **cara a cara contra la mejor versión anterior**. Detalles en
  `docs/inteligente.md`.
- `datos/` y `checkpoints/` no están en git (son grandes). Solo se sube el modelo elegido, en
  `src/musarena/ia/modelos/`. Los puntos de control del v2 y el v3 están solo en el ordenador
  de Pablo (`checkpoints/v2_farol020/`, `checkpoints/v3_largo/`). Para repetir un experimento en otro ordenador, los
  comandos están en `docs/inteligente.md`: el v2 completo tarda aproximadamente 1 hora con 20
  núcleos.

## Pendiente (siguiente sesión)
1. **Medir siempre cara a cara** contra la mejor versión anterior (ahora el v3):
   `mus-arena inteligente:nuevo.npz inteligente -n 2000 -p 0`. Un modelo nuevo solo sustituye
   al anterior si le gana por más que el margen de error (±2,2 % con 2.000 partidas).
2. Seguir entrenando a partir del v3 da poco: entre las iteraciones 325 y 500 del v3 ya
   empatan. Para mejorar hay que cambiar algo (los puntos siguientes).
3. Probar una red más grande (`--ocultas` en la imitación) y más partidas por iteración.
4. **Semana 3**: búsqueda al decidir (simular manos posibles de los rivales según las
   creencias) y un bot cazador que busque debilidades del nuestro.
5. **Semana 4**: grabar partidas humanas (con `Match(al_decidir=...)`), regenerar la tabla de
   descartes con ellas y medir contra personas. Más adelante, la web con torneos y
   clasificaciones.

## Comandos frecuentes
```bash
pytest -q                                   # tests
ruff check src tests                        # lint
mus-play                                    # jugar en la terminal (humanos y bots)
mus-arena inteligente reglas -n 2000 -p 0   # medir bots (-p 0: todos los núcleos)
mus-arena inteligente:checkpoints/x.npz reglas -n 2000 -p 0   # medir un modelo concreto
python -m musarena.ia.entrenamiento.refuerzo --help           # entrenar
```
