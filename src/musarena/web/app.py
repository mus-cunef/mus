"""La aplicación web: la API (JSON) y la página (HTML, CSS y JavaScript sin compilar).

API:

=======  =============================  ======================================================
Método   Ruta                           Qué hace
=======  =============================  ======================================================
GET      ``/api/opciones``              Tipos de jugador que se pueden elegir y límites
POST     ``/api/mesas``                 Crea una mesa; devuelve el código de cada humano
GET      ``/api/mesas/{id}``            Lo que ve un asiento (cabecera ``X-Token``)
POST     ``/api/mesas/{id}/jugar``      Juega una de las acciones legales
POST     ``/api/mesas/{id}/chat``       Escribe en el chat de la mesa
GET      ``/api/torneos/participantes`` Bots que pueden jugar un torneo
POST     ``/api/torneos``               Lanza un torneo (uno a la vez)
GET      ``/api/torneos/{id}``          Progreso y, al acabar, clasificación y cruces
GET      ``/api/clasificacion``         Última clasificación publicada
GET      ``/api/reglas``                Las reglas (Markdown)
=======  =============================  ======================================================

El código de cada asiento va en la cabecera ``X-Token`` y, en la página, detrás del ``#`` del
enlace (esa parte nunca se manda a ningún servidor), así no queda en registros ni se filtra.

Cuentas y torneos privados (ver :mod:`musarena.web.privados`): ``/api/cuenta`` (registro,
entrada, salida) y ``/api/privados`` (crear, ver, inscribirse, aceptar, empezar, jugar…). La
sesión va en una cookie ``HttpOnly`` y, contra peticiones falsificadas desde otras webs (CSRF),
las que cambian algo tienen que llevar la cabecera ``X-Mus`` (otra web no puede ponerla).
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Callable
from importlib import resources

from fastapi import Cookie, FastAPI, Header, Request, Response
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from musarena import __version__
from musarena.players import TIPOS
from musarena.players.externos import es_bot_externo
from musarena.web.archivo import ArchivoPartidas
from musarena.web.bd import conectar
from musarena.web.config import Config
from musarena.web.cuentas import Cuentas, Usuario
from musarena.web.formato import Formato, describir
from musarena.web.mesas import ErrorMesa, GestorMesas, etiqueta, tipos_permitidos
from musarena.web.privados import Privados
from musarena.web.torneos import GestorTorneos

#: Cookie con el código de la sesión.
COOKIE = "mus_sesion"
#: Nombre de la web publicada (el proyecto se sigue llamando Mus Arena).
NOMBRE_WEB = "millosolo-mus"

ESTATICOS = resources.files("musarena.web") / "estaticos"


class NuevaMesa(BaseModel):
    asientos: list[str] = Field(min_length=4, max_length=4)
    mejor_de: int = 3
    velocidad: str = "normal"
    nombres: list[str | None] = Field(default_factory=list, max_length=4)


class Jugada(BaseModel):
    accion: int
    version: int


class Mensaje(BaseModel):
    texto: str = Field(min_length=1, max_length=1000)


class NuevoTorneo(BaseModel):
    participantes: list[str] = Field(min_length=2, max_length=20)
    partidas: int = 100


class Credenciales(BaseModel):
    nombre: str = Field(max_length=100)
    clave: str = Field(max_length=200)


class NuevoPrivado(BaseModel):
    nombre: str = Field(max_length=200)
    formato: dict
    fecha_limite: float  # segundos desde 1970 (UTC)


class VistaPrevia(BaseModel):
    formato: dict
    parejas: int | None = None


class NuevaPareja(BaseModel):
    nombre: str = Field(max_length=200)
    companero: str = Field(max_length=100)


class Ganador(BaseModel):
    pareja: int


class Listo(BaseModel):
    listo: bool = True


def _descripcion(tipo: str) -> str:
    if tipo == "humano":
        return "Una persona desde su navegador"
    if es_bot_externo(tipo):
        return "Bot de la carpeta bots/"
    base, _, estilo = tipo.partition(":")
    texto = getattr(TIPOS[base], "descripcion", "")
    return f"{texto} (estilo {estilo})" if estilo else texto


def crear_app(config: Config | None = None, mesas: GestorMesas | None = None,
              torneos: GestorTorneos | None = None,
              reloj: Callable[[], float] = time.time) -> FastAPI:
    """Crea la aplicación (los tests le pasan una configuración y gestores a medida, y
    ``reloj`` para controlar la hora de las cuentas y los torneos privados)."""
    config = config or Config.desde_entorno()
    app = FastAPI(title=NOMBRE_WEB, version=__version__, docs_url="/api/docs",
                  redoc_url=None)
    app.state.config = config
    app.state.mesas = mesas if mesas is not None else GestorMesas(config)
    app.state.torneos = torneos if torneos is not None else GestorTorneos(config)
    motor = conectar(config.bd)
    app.state.cuentas = Cuentas(motor, reloj)
    app.state.privados = Privados(motor, app.state.cuentas, app.state.mesas, config, reloj)
    app.state.archivo = ArchivoPartidas(motor, reloj)
    app.state.mesas.al_grabar = app.state.archivo.guardar

    @app.exception_handler(ErrorMesa)
    async def error_mesa(_: Request, e: ErrorMesa) -> JSONResponse:
        return JSONResponse({"detalle": str(e)}, status_code=e.codigo)

    @app.middleware("http")
    async def cabeceras_de_seguridad(request: Request, call_next):
        protegida = request.url.path.startswith(("/api/cuenta", "/api/privados"))
        if protegida and request.method != "GET" and request.headers.get("X-Mus") != "1":
            return JSONResponse({"detalle": "Petición no permitida"}, status_code=403)
        respuesta = await call_next(request)
        if protegida:
            respuesta.headers["Cache-Control"] = "no-store"
        respuesta.headers["Referrer-Policy"] = "no-referrer"
        respuesta.headers["X-Content-Type-Options"] = "nosniff"
        respuesta.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/mesas"):
            respuesta.headers["Cache-Control"] = "no-store"
        return respuesta

    # --- Mesas ----------------------------------------------------------------------------

    @app.get("/api/opciones")
    def opciones() -> dict:
        return {
            "tipos": [{"valor": t, "nombre": etiqueta(t), "descripcion": _descripcion(t)}
                      for t in tipos_permitidos(config)],
            "max_partidas_torneo": config.max_partidas_torneo,
            "publico": config.publico,
            "version": __version__,
        }

    @app.post("/api/mesas")
    def crear_mesa(datos: NuevaMesa) -> dict:
        if any(n is not None and len(n) > 200 for n in datos.nombres):
            raise ErrorMesa("Nombre demasiado largo")
        mesa = app.state.mesas.crear(datos.asientos, datos.mejor_de, datos.velocidad,
                                     datos.nombres)
        return {"mesa": mesa.id,
                "asientos": [{"asiento": a, "tipo": etiqueta(t), "nombre": mesa.apodos[a],
                              "token": mesa.tokens.get(a)} for a, t in enumerate(mesa.tipos)]}

    @app.get("/api/mesas/{mesa_id}")
    def ver_mesa(mesa_id: str, x_token: str = Header(default="")) -> dict:
        return app.state.mesas.obtener(mesa_id).vista(x_token)

    @app.post("/api/mesas/{mesa_id}/jugar")
    def jugar(mesa_id: str, jugada: Jugada, x_token: str = Header(default="")) -> dict:
        mesa = app.state.mesas.obtener(mesa_id)
        mesa.jugar(x_token, jugada.accion, jugada.version)
        return mesa.vista(x_token)

    @app.post("/api/mesas/{mesa_id}/chat")
    def chat(mesa_id: str, mensaje: Mensaje, x_token: str = Header(default="")) -> dict:
        mesa = app.state.mesas.obtener(mesa_id)
        mesa.escribir(x_token, mensaje.texto)
        return mesa.vista(x_token)

    # --- Cuentas --------------------------------------------------------------------------

    def datos_usuario(usuario: Usuario) -> dict:
        return {"nombre": usuario.nombre,
                "organizador": app.state.privados.puede_organizar(usuario)}

    def con_sesion(respuesta: Response, usuario: Usuario, token: str) -> dict:
        respuesta.set_cookie(COOKIE, token, max_age=30 * 24 * 3600, httponly=True,
                             samesite="lax", secure=config.publico, path="/")
        return {"usuario": datos_usuario(usuario)}

    def usuario_de(token: str | None) -> Usuario:
        usuario = app.state.cuentas.usuario(token)
        if usuario is None:
            raise ErrorMesa("Tienes que iniciar sesión", 401)
        return usuario

    @app.get("/api/cuenta")
    def cuenta(mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = app.state.cuentas.usuario(mus_sesion)
        return {"usuario": datos_usuario(usuario) if usuario else None}

    @app.post("/api/cuenta/registro")
    def registro(datos: Credenciales, respuesta: Response) -> dict:
        return con_sesion(respuesta, *app.state.cuentas.registrar(datos.nombre, datos.clave))

    @app.post("/api/cuenta/entrar")
    def entrar(datos: Credenciales, respuesta: Response) -> dict:
        return con_sesion(respuesta, *app.state.cuentas.entrar(datos.nombre, datos.clave))

    @app.post("/api/cuenta/salir")
    def salir(respuesta: Response, mus_sesion: str | None = Cookie(default=None)) -> dict:
        app.state.cuentas.cerrar_sesion(mus_sesion)
        respuesta.delete_cookie(COOKIE, path="/")
        return {"usuario": None}

    # --- Torneos privados -----------------------------------------------------------------

    @app.post("/api/privados/vista-previa")
    def vista_previa(datos: VistaPrevia) -> dict:
        try:
            f = Formato.desde_dict(datos.formato)
            f.validar()
        except (TypeError, ValueError) as e:
            raise ErrorMesa(str(e) or "Formato no válido") from None
        n = datos.parejas or f.max_parejas
        return {"descripcion": describir(f, max(2, min(n, f.max_parejas)))}

    @app.get("/api/privados")
    def mis_privados(mus_sesion: str | None = Cookie(default=None)) -> dict:
        return {"torneos": app.state.privados.lista(usuario_de(mus_sesion))}

    @app.post("/api/privados")
    def crear_privado(datos: NuevoPrivado,
                      mus_sesion: str | None = Cookie(default=None)) -> dict:
        codigo = app.state.privados.crear(usuario_de(mus_sesion), datos.nombre, datos.formato,
                                          datos.fecha_limite)
        return {"codigo": codigo}

    @app.get("/api/privados/{codigo}")
    def ver_privado(codigo: str, mus_sesion: str | None = Cookie(default=None)) -> dict:
        return app.state.privados.ver(usuario_de(mus_sesion), codigo)

    @app.post("/api/privados/{codigo}/parejas")
    def inscribir(codigo: str, datos: NuevaPareja,
                  mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.inscribir(usuario, codigo, datos.nombre, datos.companero)
        return app.state.privados.ver(usuario, codigo)

    @app.post("/api/privados/{codigo}/parejas/{pareja}/aceptar")
    def aceptar(codigo: str, pareja: int,
                mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.aceptar(usuario, codigo, pareja)
        return app.state.privados.ver(usuario, codigo)

    @app.post("/api/privados/{codigo}/parejas/{pareja}/retirar")
    def retirar(codigo: str, pareja: int,
                mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.retirar(usuario, codigo, pareja)
        return app.state.privados.ver(usuario, codigo)

    @app.post("/api/privados/{codigo}/empezar")
    def empezar(codigo: str, mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.empezar(usuario, codigo)
        return app.state.privados.ver(usuario, codigo)

    @app.post("/api/privados/{codigo}/cancelar")
    def cancelar(codigo: str, mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.cancelar(usuario, codigo)
        return app.state.privados.ver(usuario, codigo)

    @app.post("/api/privados/{codigo}/partidos/{partido}/listo")
    def marcar_listo(codigo: str, partido: int, datos: Listo,
                     mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.marcar_listo(usuario, codigo, partido, datos.listo)
        return app.state.privados.ver(usuario, codigo)

    @app.post("/api/privados/{codigo}/partidos/{partido}/entrar")
    def entrar_partido(codigo: str, partido: int,
                       mus_sesion: str | None = Cookie(default=None)) -> dict:
        return app.state.privados.entrar(usuario_de(mus_sesion), codigo, partido)

    @app.post("/api/privados/{codigo}/partidos/{partido}/ganador")
    def dar_ganador(codigo: str, partido: int, datos: Ganador,
                    mus_sesion: str | None = Cookie(default=None)) -> dict:
        usuario = usuario_de(mus_sesion)
        app.state.privados.dar_ganador(usuario, codigo, partido, datos.pareja)
        return app.state.privados.ver(usuario, codigo)

    # --- Torneos y clasificación ----------------------------------------------------------

    @app.get("/api/torneos/participantes")
    def participantes() -> dict:
        return {"participantes": [{"valor": p, "nombre": etiqueta(p)}
                                  for p in app.state.torneos.participantes_posibles()],
                "max_partidas": config.max_partidas_torneo}

    @app.post("/api/torneos")
    def lanzar_torneo(datos: NuevoTorneo) -> dict:
        return app.state.torneos.lanzar(datos.participantes, datos.partidas).a_dict()

    @app.get("/api/torneos/en-marcha")
    def torneo_en_marcha() -> dict:
        estado = app.state.torneos.en_marcha()
        return {"torneo": estado.a_dict() if estado else None}

    @app.get("/api/torneos/{torneo_id}")
    def ver_torneo(torneo_id: str) -> dict:
        return app.state.torneos.obtener(torneo_id).a_dict()

    cache: dict = {"datos": None, "hora": -1e9}

    @app.get("/api/clasificacion")
    def clasificacion() -> dict:
        """La clasificación publicada (como mucho de hace 10 minutos) o, si no se puede leer,
        la del archivo del repositorio."""
        if config.clasificacion_url and time.monotonic() - cache["hora"] > 600:
            try:
                with urllib.request.urlopen(config.clasificacion_url, timeout=4) as respuesta:
                    datos = json.loads(respuesta.read().decode("utf-8"))
                if isinstance(datos, dict) and "clasificacion" in datos:
                    cache.update(datos=datos, hora=time.monotonic())
            except (OSError, ValueError):
                cache["hora"] = time.monotonic() - 540  # se reintenta en un minuto
        if cache["datos"] is not None:
            return cache["datos"]
        ruta = config.ruta("clasificacion")
        if not ruta.is_file():
            raise ErrorMesa("Todavía no hay ninguna clasificación publicada", 404)
        return json.loads(ruta.read_text(encoding="utf-8"))

    @app.get("/api/reglas", response_class=PlainTextResponse)
    def reglas() -> str:
        ruta = config.ruta("reglas")
        if not ruta.is_file():
            raise ErrorMesa("No se encuentran las reglas", 404)
        return ruta.read_text(encoding="utf-8")

    # --- Página ---------------------------------------------------------------------------

    @app.get("/", include_in_schema=False)
    def inicio() -> FileResponse:
        return FileResponse(str(ESTATICOS / "index.html"))

    app.mount("/estaticos", StaticFiles(directory=str(ESTATICOS)), name="estaticos")
    return app
