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
- **Enunciado oficial de la práctica:** `IA_MAT_2627_practicas.pdf` (Javier Paris; no está en el
  repo, lo tiene cada miembro). Proyecto de ejemplo del profesor: https://github.com/jparisu/nim-arena
  y su guía técnica: https://nim-arena.readthedocs.io/en/latest/guide/. Se evalúa **por
  requisitos** y solo cuentan los que se **defienden** oralmente (ver el apartado "Requisitos
  oficiales" más abajo).

## Requisitos oficiales (enunciado) y estado

| Req | Requisito | Puntos | Estado |
| --- | --- | --- | --- |
| — | Juego por turnos **de 2 jugadores, validado por el profesor** | condición | Mus = 2 parejas: **confirmar que el profesor lo validó** |
| 1.1 | Lógica en librería Python instalable; partida completa desde código | 1.5 | Hecho |
| 1.2 | Interfaz web: una persona juega una partida completa contra un bot | 1.0 | Hecho (`mus-web`) |
| 1.3 | Web publicada en URL pública, sin instalar nada | 0.5 | Hecho: https://mus-81o1.onrender.com |
| 2.1 | API público en Python: un bot se escribe sin tocar el juego | 1.0 | Hecho (`Player`, `bots/`) |
| 2.2 | Tests automáticos que comprueban los bots nuevos antes de incluirlos | 0.5 | **Falta** un test que valide cada bot de `bots/` |
| 2.3 | Documentación **publicada online** con referencia del API y tutorial de principio a fin | 0.5 | **Falta** (MkDocs + ReadTheDocs o GitHub Pages) |
| 3.1 | Bot propio (0.5 × dificultad) | ≤ 5 | Hecho (`inteligente`, `reglas`) |
| 3.2 | Bot para el juego de **otro equipo**, por PR | 0.5 × dif. | **Falta** |
| 3.3 | Bot externo recibido por PR, revisado y fusionado | 0.25/bot | **Falta** (pedirlo a otros equipos) |
| 4.1 | Torneo de todos los bots; un bot que **falla, se cuelga o juega ilegal pierde la partida pero no rompe el torneo** | 1.0 | Torneo hecho; **falta** la robustez (hoy un bot que falla rompe el torneo) |
| 4.2 | Clasificación publicada y actualizada automáticamente | 0.5 | Parcial: la Action la publica en su resumen; **mejor en una página** (web/docs) |
| C.1 | Repo público y ordenado (README, LICENSE, .gitignore) | 0.5 | Hecho |
| C.2 | Ramas y PRs, y **`main` protegida** | 0.5 | Ramas y PRs sí; **`main` no está protegida** |
| C.3 | Tests automáticos en cada PR | 0.5 | Hecho |

Uso de IA (enunciado, 5.8): permitido para código, tests y documentación, **solo con herramientas
gratuitas o con licencia de la universidad**; todo tiene que poder explicarse en la defensa.

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
                players/externos.py: bots en archivos .py aparte ("bots/mi_bot.py")
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
  torneo.py     torneo todos contra todos (`mus-torneo`): clasificación por Elo (Bradley-Terry)
                y %; jugar_torneo(..., al_progreso=) y ResultadoTorneo.a_dict() para la web
  grabacion.py  grabar partidas (semilla + acciones, JSON en partidas/) y reproducirlas para
                reconstruir cada observación; mus-play graba sola si juega algún humano
  cli.py        punto de entrada `mus-play` (humanos y bots en cualquier asiento)
  web/          la web (`mus-web`, extra [web]; ver docs/web.md): config.py (límites, modo
                internet con MUS_PUBLICO=1), vista.py (lo que ve cada asiento: solo su
                Observation), mesas.py (mesas con humanos y bots), torneos.py (torneos en
                segundo plano), app.py (FastAPI), estaticos/ (HTML, CSS y JS sin compilar)
bots/           bots externos: cada .py entra solo en el torneo (prudente.py es el ejemplo)
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
- **Partidas humanas**: `mus-play` graba sola cada partida con algún humano en `partidas/`, y
  **se suben a GitHub** en PRs para juntar las de todo el equipo (pesan pocos KB).
- **Cazadores**: para medir lo explotable que es el bot se entrena un cazador contra él
  (`--contra`); las debilidades que encuentre se tapan metiéndolo en la liga (`--cazadores`).
- **Torneo**: todos contra todos con repartos duplicados, clasificación por Elo (Bradley-Terry,
  que tiene en cuenta contra quién se gana) y por %. La misma función (`torneo.jugar_torneo`)
  sirve para la terminal, para GitHub Actions (`.github/workflows/torneo.yml`, que publica la
  clasificación en el resumen de la ejecución) y para la **web**, donde será un apartado propio.
- **Web:** FastAPI y una página sin herramientas de compilación, **pensada para internet desde
  el principio**: solo se manda la `Observation` de cada asiento, códigos secretos detrás del
  `#`, versión en cada jugada, chat como texto y límites (modo `MUS_PUBLICO=1`). Varios humanos
  desde distintos dispositivos, cada uno con su enlace. Tiene que ser **rápida e intuitiva y
  sin fallos**: cada cambio en la web se prueba también en el navegador
  (`tests/test_web_navegador.py`, con Playwright y el Chrome instalado) y se revisa con capturas.
- **Recompensa del refuerzo**: `vaca+farol` con premio 0,2. Es la que más gana, también
  entre bots de refuerzo. Las recompensas densas (`tantos`, `potencial`) no aportaron nada.
- **Lección del heurístico**: calcular el valor esperado con un modelo de "qué hará el rival"
  empeora el bot. Funcionan mejor los umbrales sobre una probabilidad propia bien calibrada.

## Estado actual (2026-10-19): bot cerrado
- En `main`: motor completo, bots `random`, `basico`, `reglas` (con estilos) e `inteligente`,
  arena en paralelo, imitación y refuerzo (PPO) con liga de rivales, y tabla de descartes en las
  creencias.
- Bot inteligente: semana 1 (imitación, 49 % contra `reglas`) y semana 2 (refuerzo) hechas.
  El modelo del paquete (`ia/modelos/inteligente.npz`) es el **v4**: el v3 entrenado con
  **cazadores en la liga**, confirmado con 2.000 partidas. Gana el 81,7 % contra `reglas`, el
  84,4 % contra `reglas:agresivo` y el 81,4 % contra `reglas:conservador`, empata cara a cara
  con el v3 (48,1 % ± 2,2) y gana el **88,5 % al cazador**, que ganaba el 92,5 % al v3. El v3
  tenía una debilidad: casi nunca aceptaba un órdago, y el cazador lo explotaba echando órdagos
  de farol. Detalles en `docs/inteligente.md` (semana 3).
- **El bot está cerrado: el v4 es el modelo final** (congelado). Un cazador nuevo le gana el 79 %,
  porque se retira demasiado ante la agresividad. El intento de taparlo (v5, con tres
  cazadores) se defendía mejor (+10 puntos contra el cazador), pero perdía de 2 a 4 puntos
  contra `reglas`, así que no sustituyó al v4. La temperatura tampoco lo arregla. Detalles en
  `docs/inteligente.md` (semana 3).
- `datos/` y `checkpoints/` no están en git (son grandes). Solo se sube el modelo elegido, en
  `src/musarena/ia/modelos/`. Los puntos de control del v2, v3, v4 y los cazadores están solo
  en el ordenador de Pablo (`checkpoints/`). Para repetir un experimento en otro ordenador, los
  comandos están en `docs/inteligente.md`: el v2 completo tarda aproximadamente 1 hora con 20
  núcleos.

## Pendiente (siguiente sesión)
1. **El bot está cerrado.** No cambiar `ia/modelos/inteligente.npz` salvo que un modelo nuevo
   cumpla el criterio: no perder fuerza (contra `reglas` y cara a cara contra el anterior,
   **con los mismos repartos** y dentro del margen de error: ±1,7 % y ±2,2 % con 2.000 partidas)
   y mejorar en algo medible (cara a cara o contra el cazador). Medir con
   `mus-arena inteligente:nuevo.npz inteligente -n 2000 -p 0 --seed 77`.
2. **Lo que falta del proyecto**: ver la tabla de "Requisitos oficiales" (lo marcado como
   **Falta**). La web ya está publicada en https://mus-81o1.onrender.com (Render, se publica
   sola al fusionar en `main`; configuración en `docs/web.md`).
3. **Entrega y defensa:** limpiar el README (quitar los "próximamente"), versión 1.0 etiquetada,
   demo preparada (partida contra el bot, torneo, la historia del cazador) y repartir la defensa.
4. **Mejoras del bot para más adelante** (opcionales): partidas humanas (imitación con
   `datos.de_partidas`, tabla de descartes humana, medir contra personas), más ciclos de
   cazadores, búsqueda al decidir y una red más grande. Las tareas en segundo plano se cortan
   pasada aproximadamente una hora: entrenar en tramos de 150 iteraciones.

## Comandos frecuentes
```bash
pytest -q                                   # tests
ruff check src tests                        # lint
mus-play                                    # jugar en la terminal (humanos y bots)
mus-arena inteligente reglas -n 2000 -p 0   # medir bots (-p 0: todos los núcleos)
mus-arena inteligente:checkpoints/x.npz reglas -n 2000 -p 0   # medir un modelo concreto
mus-torneo -n 200                           # torneo de todos los bots (y los de bots/)
mus-web --red                               # la web (también desde el móvil)
pytest tests/test_web_navegador.py          # la web en Chrome (antes de cada PR de la web)
python -m musarena.ia.entrenamiento.refuerzo --help           # entrenar
```
