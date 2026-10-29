# La web de Mus Arena (millosolo-mus)

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
  pausa de 0,6 s (velocidad media) para que se entienda lo que hace. Cuando le toca a un humano,
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

## Cuentas y torneos privados

En **Torneos** se organiza un torneo para jugar con los amigos. Por defecto puede crearlo
cualquiera con cuenta; con la variable `MUS_ORGANIZADORES` (nombres de usuario separados por
comas) solo pueden crearlos esos usuarios, y los demás solo se inscriben con el enlace:

1. **Crear.** Se elige el nombre, el número máximo de parejas (de 2 a 64), la fecha límite de
   inscripción y el **formato**:
   - *Automático* (el recomendado): con más de 16 parejas, fase de grupos de 4 de los que pasan 2;
     con 16 o menos, cuadro directo (octavos si son 16, cuartos si son 8, semifinales si son 4).
   - *Eliminatoria*: cuadro directo.
   - *Grupos y cuadro*: se eligen las parejas por grupo y cuántas pasan.
   - *Liga*: todos contra todos.

   También se eligen las vacas de cada partido y de la final y si hay partido por el tercer
   puesto. Mientras se rellena, la página explica cómo quedaría el torneo lleno.
2. **Invitar.** Al crearlo sale el **enlace de invitación** (`/#/t/<código>`). Sin él, el torneo
   no se ve. Quien lo abre sin cuenta va a crearla y vuelve solo al torneo.
3. **Inscribirse.** Un jugador inscribe la pareja con el nombre de usuario de su compañero, y
   el compañero la **acepta** desde el mismo enlace. Nadie puede estar en dos parejas.
4. **Sorteo.** Al llegar la fecha límite se sortea solo con las parejas confirmadas (hacen falta
   al menos 2). El organizador puede sortear antes. Si el número de parejas no es potencia de
   2, las mejores cabezas de serie pasan directamente a la segunda ronda (con 12 parejas, el
   cuadro es de 16 con 4 pases). Después de los grupos, los primeros se cruzan con segundos de
   otros grupos y, si se puede, nunca con uno de su grupo en la primera ronda.
5. **Jugar.** Cada jugador ve sus partidos con un botón **Empezar**. La página dice quién está
   listo y a quién se espera. La partida empieza cuando le da **el cuarto**, y en ese momento
   los cuatro entran solos en la misma mesa con su cuenta (la pareja A en los asientos 1 y 3).
   Quien se haya equivocado puede echarse atrás («Aún no») mientras falte alguien. El resultado lo apunta la web al
   terminar la partida, y el ganador avanza solo. Si una pareja no se presenta, el organizador
   da el partido por ganado.
6. **Seguirlo.** Tablas de grupos o de liga (desempates: partidos ganados, diferencia de vacas y
   de tantos), cuadro, campeón y **estadísticas por pareja**: partidos y % de victorias, vacas,
   tantos, manos ganadas, envites y órdagos.

Cómo está hecho (`musarena/web/`):

- `formato.py`: la lógica de los formatos (grupos, cabezas de serie, pases, ligas y
  clasificaciones), sin web ni base de datos. `tests/test_formato.py` la prueba con todos los
  tamaños de 2 a 64 parejas.
- `cuentas.py`: las contraseñas se guardan con **scrypt** (lento a propósito, con sal) y nunca
  en claro. La sesión es un código aleatorio en una cookie `HttpOnly` y `SameSite=Lax` (`Secure`
  en internet), y en la base de datos solo se guarda su hash. Tras 8 fallos seguidos, la cuenta
  se bloquea 15 minutos. Las peticiones que cambian algo llevan la cabecera `X-Mus`, que otra
  web no puede poner (protección contra CSRF).
- `privados.py`: inscripción, sorteo, avance del cuadro y estadísticas. **Cada jugada de un
  partido se guarda en la base de datos**: si el servidor se reinicia, la mesa se reconstruye
  con la semilla y las jugadas (`GestorMesas.restaurador`), exactamente igual.
- `bd.py`: las tablas (SQLAlchemy). En local es un archivo SQLite (`mus_web.db`). En internet,
  una base de datos **PostgreSQL** externa (variable `MUS_BD`), porque el disco de Render se
  borra en cada reinicio.

## Partidas guardadas para entrenar al bot

El bot **no aprende solo** mientras se juega: el modelo publicado está congelado y solo se
cambia si uno nuevo gana en la arena (ver `docs/inteligente.md`). Pero las partidas con humanos
se guardan para poder entrenarlo más adelante con ellas (`musarena/web/archivo.py`):

- **Mesas normales:** al acabar cada mano, al terminar la partida y al cerrar la mesa, en la
  tabla `partidas_web` de la base de datos. Si el servidor se duerme a mitad de partida, queda
  guardada hasta la última mano.
- **Torneos privados:** ya se guardan jugada a jugada en `partidos`.
- Solo se guarda la semilla, qué hay en cada asiento (`humano`, `inteligente`…) y las jugadas:
  **ni nombres ni cuentas**. Si la base de datos falla, la partida sigue igual (solo se apunta
  el error).

Para usarlas, se exportan a archivos como los de `mus-play` (en PowerShell, con la cadena de
Neon, que es secreta y no se escribe en ningún archivo del repositorio):

```powershell
$env:MUS_BD = "postgresql://..."
python -m musarena.web.archivo partidas/web
```

Luego, `musarena.ia.entrenamiento.datos.de_partidas(...)` las convierte en ejemplos (las
decisiones de los humanos). Para que reentrenar merezca la pena hacen falta varios cientos de
partidas.

## Publicada en Render

La primera versión estaba en `mus-81o1.onrender.com`; la actual (con la base de datos de Neon)
es el servicio `millosolo-mus`.

La web está en **https://millosolo-mus.onrender.com** (servicio gratuito de [Render](https://render.com)), conectada al
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
| Name | `millosolo-mus` |
| Variables de entorno | `MUS_PUBLICO=1`, `PYTHON_VERSION=3.12.7`, `MUS_BD` (base de Neon, ver abajo) y `MUS_ORGANIZADORES` (quién crea torneos privados) |

Plan gratuito: si nadie entra en 15 minutos se duerme y la siguiente visita tarda unos 30-60 s
(conviene abrirla un minuto antes de una demo). Las partidas grabadas allí se pierden en cada
reinicio o publicación.

**Versiones nuevas sin recargar a mano.** El JS y el CSS se piden con la versión en la dirección
(`/estaticos/app.js?v=<huella>`, la huella de los archivos de la página) y la página principal
va con `Cache-Control: no-cache`, así que el navegador nunca mezcla una página nueva con un
`app.js` viejo de su caché. Además, cada respuesta del API lleva la cabecera `X-Mus-Version`: si
alguien tiene la pestaña abierta mientras se publica una versión nueva, le sale el aviso «Hay
una versión nueva de la web» con un botón para recargar (la partida y la sesión siguen, porque
están en el servidor y en el enlace).

**Base de datos de las cuentas y los torneos privados.** Sin `MUS_BD`, Render usaría un SQLite
en su disco, que se borra al reiniciar: se perderían cuentas y torneos. Se usa una base
PostgreSQL gratuita de [Neon](https://neon.tech) (no caduca; la de Render sí, a los 30 días):

1. Crear una cuenta en Neon y un proyecto (región Frankfurt, la misma que Render).
2. Copiar la *connection string* (`postgresql://usuario:clave@...neon.tech/neondb?sslmode=require`).
3. En Render, *Environment*: añadir `MUS_BD` con esa cadena. Es un secreto: va solo ahí, nunca
   en el repositorio ni en un chat.

Las tablas se crean solas al arrancar.

## Modo internet

`MUS_PUBLICO=1` activa límites estrictos para que un visitante no acapare el servidor: 50 mesas
abiertas como máximo, 60 partidas por cruce en los torneos y 2 procesos por torneo. Las mesas
viven en memoria, así que la web se arranca con **un solo proceso** (`mus-web` ya lo hace).

Variables de entorno: `MUS_PUBLICO`, `MUS_MAX_MESAS`, `MUS_MINUTOS_INACTIVA`,
`MUS_MAX_PARTIDAS_TORNEO`, `MUS_PROCESOS_TORNEO`, `MUS_PARTIDAS`, `MUS_BOTS`,
`MUS_CLASIFICACION`, `MUS_CLASIFICACION_URL`, `MUS_REGLAS`, `MUS_BD` y `MUS_ORGANIZADORES`
(ver `musarena/web/config.py`).

## API

La documentación interactiva está en `/api/docs`. Las rutas están en la cabecera de
`musarena/web/app.py`.

## Pruebas

- `tests/test_web.py`: la API (mesas, jugadas, información oculta, límites, torneos). Corre en
  la CI.
- `tests/test_privados.py` y `tests/test_formato.py`: cuentas (contraseñas, bloqueos, CSRF),
  inscripción, sorteos con grupos, pases y liga, **partidos completos jugados por la API** por
  cuatro cuentas, avance del cuadro, estadísticas y la reconstrucción de una mesa tras un
  reinicio. Corren en la CI.
- `tests/test_web_navegador.py`: Chrome, manejado con Playwright, juega **partidas completas
  haciendo clic**, incluidos descartes, enlaces de dos humanos, enlaces falsos, el torneo, la
  clasificación, las reglas y un **torneo privado entero** (cinco cuentas en navegadores
  distintos: crear con formato, invitar, inscribirse, aceptar, sortear, entrar en la mesa y
  campeón). Comprueba que no hay errores de JavaScript ni cartas ajenas en
  pantalla. Usa el Chrome instalado: `pip install -e ".[e2e]"` y `pytest
  tests/test_web_navegador.py`. **Hay que pasarlas antes de cada PR que toque la web.**
