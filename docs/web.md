# La web de Mus Arena

Jugar al mus desde el navegador, con humanos y bots en cualquier asiento, y lanzar torneos.

## Arrancarla

```bash
pip install -e ".[web]"
mus-web                  # en este ordenador: http://localhost:8000
mus-web --red            # también desde otros dispositivos de la misma wifi
```

Con `--red` se imprime la dirección para el móvil o los otros ordenadores, por ejemplo
`http://192.168.1.20:8000`.

## Qué tiene

| Apartado | Qué se hace |
| --- | --- |
| **Jugar** | Se elige quién ocupa cada asiento (humano, `inteligente`, `reglas` y sus estilos, `basico`, `random` o los bots de `bots/`), el **nombre de cada humano** (opcional; si no, "Jugador N") y la partida al mejor de 3 o 5 vacas. Si hay un solo humano, entra directamente; si hay varios, cada uno recibe **su enlace**. |
| **La mesa** | Tus cartas abajo, el compañero arriba y los rivales a los lados. Un aviso grande de "Te toca", lo que se está jugando (lance y apuesta), un bocadillo con lo último que dijo cada uno, solo los botones de las jugadas legales, el descarte tocando las cartas, el marcador, el historial, el chat y, al final de cada mano, las cartas de los cuatro con los cobros. |
| **Torneo** | Participantes y partidas por cruce. Se juega en segundo plano con barra de progreso y al final enseña la clasificación (Elo y %) y los cruces. Usa `torneo.jugar_torneo`, el mismo que `mus-torneo`. |
| **Clasificación** | La última clasificación publicada por la Action del torneo (https://mus-cunef.github.io/mus/clasificacion.json; si no se puede leer, la del repositorio). |
| **Reglas** | `docs/reglas.md`. |

Las partidas con algún humano se **graban** en `partidas/`, igual que con `mus-play`.

## Cómo funciona

- **Servidor:** FastAPI (`musarena/web/`). Reutiliza el motor, el registro de bots, el torneo y la
  grabación. La página es HTML, CSS y JavaScript sin compilar (`musarena/web/estaticos/`).
- **Una mesa** guarda una `Match`. Cuando le toca a un bot, la mesa juega por él con una pequeña
  pausa de 0,3 s para que se vea lo que hace. Cuando le toca a un humano,
  espera a que su navegador mande la jugada.
- **El navegador pregunta** cada 0,25 s mientras juegan los bots y cada 2 s cuando le toca a la
  persona (no hace falta más). Al jugar, la respuesta ya trae la mesa actualizada.
- **Cada jugada lleva la versión** de la mesa que se veía: si no coincide (doble clic, dos
  pestañas), se rechaza en vez de aplicar otra cosa.

### Seguridad (pensada para internet)

- **Información oculta:** el servidor solo manda a cada asiento **su `Observation`**
  (`musarena/web/vista.py`). Las cartas ajenas no están ni en los datos con los que se construye
  la respuesta. `tests/test_web.py` lo comprueba en partidas enteras.
- **Códigos secretos:** cada asiento humano tiene un código aleatorio largo. En el enlace va
  detrás del `#`, una parte que el navegador nunca manda a ningún servidor, y en las peticiones
  va en la cabecera `X-Token`. Sin él no se puede ver ni jugar ese asiento.
- **Validación:** el servidor comprueba el turno, la jugada (una de las legales) y la versión, y
  el motor la vuelve a validar.
- **Chat:** se guarda como texto y la página lo pinta con `textContent`, nunca como HTML.
- **Límites:** máximo de mesas abiertas (las inactivas se cierran solas), un solo torneo a la
  vez, máximo de partidas por cruce, y desde la web solo se eligen bots de la lista del servidor
  (nunca una ruta).
- **Cabeceras:** `Referrer-Policy: no-referrer`, `X-Content-Type-Options: nosniff` y
  `X-Frame-Options: DENY`.

## Publicada en Render

La web está en **https://mus-81o1.onrender.com** (servicio gratuito de [Render](https://render.com)), conectada al
repositorio: **cada fusión en `main` la vuelve a publicar sola**. Configuración del servicio
(*Web Service*, creado a mano en el panel de Render):

| Campo | Valor |
| --- | --- |
| Language | Python 3 |
| Branch | `main` |
| Region | Frankfurt (EU Central) |
| Build Command | `pip install ".[web]"` |
| Start Command | `mus-web --red --no-abrir --puerto $PORT` |
| Instance Type | Free |
| Variables de entorno | `MUS_PUBLICO=1`, `PYTHON_VERSION=3.12.7` |

Plan gratuito: si nadie entra en 15 minutos se duerme y la siguiente visita tarda unos 30-60 s
(conviene abrirla un minuto antes de una demo). Las partidas grabadas allí se pierden en cada
reinicio o publicación.

## Modo internet

`MUS_PUBLICO=1` activa límites estrictos para que un visitante no acapare el servidor: 50 mesas
abiertas como máximo, 60 partidas por cruce en los torneos y 2 procesos por torneo. Las mesas
viven en memoria, así que la web se arranca con **un solo proceso** (`mus-web` ya lo hace).

Variables de entorno: `MUS_PUBLICO`, `MUS_MAX_MESAS`, `MUS_MINUTOS_INACTIVA`,
`MUS_MAX_PARTIDAS_TORNEO`, `MUS_PROCESOS_TORNEO`, `MUS_PARTIDAS`, `MUS_BOTS`,
`MUS_CLASIFICACION`, `MUS_CLASIFICACION_URL` y `MUS_REGLAS` (ver `musarena/web/config.py`).

## API

La documentación interactiva está en `/api/docs`. Las rutas están en la cabecera de
`musarena/web/app.py`.

## Pruebas

- `tests/test_web.py`: la API (mesas, jugadas, información oculta, límites, torneos). Corre en
  la CI.
- `tests/test_web_navegador.py`: Chrome, manejado con Playwright, juega **partidas completas
  haciendo clic**, incluidos descartes, enlaces de dos humanos, enlaces falsos, el torneo, la
  clasificación y las reglas. Comprueba que no hay errores de JavaScript ni cartas ajenas en
  pantalla. Usa el Chrome instalado: `pip install -e ".[e2e]"` y `pytest
  tests/test_web_navegador.py`. **Hay que pasarlas antes de cada PR que toque la web.**
