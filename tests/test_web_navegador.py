"""Pruebas de la web en un navegador de verdad (Chrome, con Playwright).

Juegan partidas completas haciendo clic, como una persona, y comprueban que no hay errores de
JavaScript y que nunca aparecen en pantalla las cartas de los demás. Se saltan si no están
Playwright y Chrome (en la CI no se instalan; se pasan en local antes de cada PR de la web):

    pip install playwright      # usa el Chrome ya instalado
    pytest tests/test_web_navegador.py
"""

import socket
import threading
import time

import pytest

pytest.importorskip("fastapi")
playwright = pytest.importorskip("playwright.sync_api")
uvicorn = pytest.importorskip("uvicorn")

from musarena.web.app import crear_app  # noqa: E402
from musarena.web.config import Config  # noqa: E402
from musarena.web.mesas import GestorMesas  # noqa: E402
from musarena.web.torneos import GestorTorneos  # noqa: E402


def _puerto_libre() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def servidor(tmp_path_factory):
    carpeta = tmp_path_factory.mktemp("partidas")
    config = Config(pausa_bots=0.02, carpeta_partidas=str(carpeta), procesos_torneo=1,
                    max_partidas_torneo=20)
    mesas = GestorMesas(config)
    app = crear_app(config, mesas, GestorTorneos(config))
    puerto = _puerto_libre()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=puerto, log_level="error"))
    hilo = threading.Thread(target=server.run, daemon=True)
    hilo.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{puerto}", mesas, carpeta
    server.should_exit = True
    hilo.join(5)


@pytest.fixture(scope="module")
def navegador():
    with playwright.sync_playwright() as p:
        try:
            b = p.chromium.launch(channel="chrome", headless=True)
        except Exception as e:  # sin Chrome instalado
            pytest.skip(f"No se puede abrir Chrome: {e}")
        yield b
        b.close()


@pytest.fixture
def pagina(navegador):
    contexto = navegador.new_context()
    pagina = contexto.new_page()
    errores = []
    pagina.on("pageerror", lambda e: errores.append(str(e)))
    pagina.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)
    pagina.errores = errores
    yield pagina
    contexto.close()


def _cartas_en_pantalla(pagina) -> set[str]:
    """Las cartas boca arriba que se ven en la mesa (sin contar el resumen de la mano)."""
    return set(pagina.eval_on_selector_all(
        "#tapete .carta:not(.reverso)", "els => els.map(e => e.getAttribute('title'))"))


CONTRA_INTELIGENTE = ("humano", "inteligente", "inteligente", "inteligente")


def _jugar_partida(pagina, mesas, url, asientos=CONTRA_INTELIGENTE, pedir_mus=False):
    pagina.goto(url + "/")
    pagina.wait_for_selector("#asiento-0 option", state="attached")
    for a, tipo in enumerate(asientos):
        pagina.select_option(f"#asiento-{a}", tipo)
        # La casilla del nombre solo aparece en los asientos de humanos.
        assert pagina.is_visible(f"#nombre-{a}") == (tipo == "humano")
    pagina.fill("#nombre-0", "Pablo")
    pagina.click("#form-mesa button[type=submit]")
    pagina.wait_for_url("**/#/mesa/**")
    pagina.wait_for_selector("text=Tú (Pablo)")
    mesa_id = pagina.url.split("#/mesa/")[1].split("/")[0]
    mesa = mesas.obtener(mesa_id)
    clics = 0
    limite = time.time() + 240
    while time.time() < limite:
        if pagina.is_visible("text=Jugar otra partida"):
            return mesa, clics
        if pagina.is_visible("#resumen-mano"):
            pagina.click("#resumen-mano button", timeout=3000)
            continue
        # Los otros tres asientos solo pintan cartas boca abajo, y boca arriba solo hay 4 (las
        # tuyas). Que el servidor no manda cartas ajenas lo comprueba test_web.py.
        assert pagina.eval_on_selector_all(
            ".asiento-mesa:not(.abajo) .carta:not(.reverso)", "els => els.length") == 0
        assert len(_cartas_en_pantalla(pagina)) <= 4
        assert not pagina.query_selector(".nombre-figura")  # las cartas no llevan etiquetas
        palabras = pagina.evaluate("() => document.body.innerText.split(/\\s+/)")
        assert "null" not in palabras and "undefined" not in palabras, "hueco vacío pintado"
        boton = pagina.query_selector("#acciones button:not([disabled])")
        if pedir_mus:
            mus = pagina.query_selector("#acciones button:has-text('Mus')")
            if mus is not None and mus.is_enabled():
                boton = mus
        if boton is None:
            cartas = pagina.query_selector_all("#tapete button.carta.seleccionable")
            if cartas:  # descarte: elegir la última carta y descartar
                try:
                    cartas[-1].click(timeout=2000)
                except playwright.Error:
                    pass
                continue
            pagina.wait_for_timeout(30)
            continue
        try:
            boton.click(timeout=2000)
        except playwright.Error:  # justo se abrió el resumen de la mano: se cierra y se sigue
            continue
        clics += 1
        pagina.wait_for_timeout(10)
    raise AssertionError("La partida no ha terminado a tiempo")


def test_partida_completa_en_el_navegador(servidor, pagina):
    url, mesas, carpeta = servidor
    mesa, clics = _jugar_partida(pagina, mesas, url)
    assert mesa.match.terminada, "la partida no ha terminado"
    # Pocos clics bastan si se acepta un órdago pronto: lo importante es que llegue al final.
    assert clics >= 1, "el humano no ha jugado"
    assert pagina.errores == [], pagina.errores
    assert list(carpeta.glob("*.json"))  # la partida queda grabada


def test_partida_con_reglas_y_basico(servidor, pagina):
    url, mesas, _ = servidor
    mesa, _ = _jugar_partida(pagina, mesas, url, ("humano", "reglas:agresivo", "basico", "random"))
    assert mesa.match.terminada and pagina.errores == []


def test_descartes_con_clics(servidor, pagina):
    """Pidiendo siempre mus contra bots que también lo piden con mala mano, hay rondas de
    descarte: se eligen cartas con clics y el motor recibe el descarte. (Con bots aleatorios
    casi no hay descartes: echan y aceptan órdagos al azar y las vacas duran dos manos.)"""
    url, mesas, _ = servidor
    mesa, _ = _jugar_partida(pagina, mesas, url, ("humano", "basico", "basico", "basico"),
                             pedir_mus=True)
    propios = [datos for asiento, datos in mesa.grabador.partida.acciones
               if asiento == 0 and datos["tipo"] == "Descarte"]
    assert propios, "el humano no llegó a descartarse"
    assert pagina.errores == [], pagina.errores


def test_dos_humanos_reciben_sus_enlaces(servidor, pagina):
    url, _, _ = servidor
    pagina.goto(url + "/")
    pagina.wait_for_selector("#asiento-0 option", state="attached")
    pagina.select_option("#asiento-2", "humano")
    pagina.click("#form-mesa button[type=submit]")
    pagina.wait_for_selector("#enlaces:not([hidden])")
    enlaces = pagina.eval_on_selector_all("#lista-enlaces code",
                                          "els => els.map(e => e.textContent)")
    assert len(enlaces) == 2 and enlaces[0] != enlaces[1] and all("#/mesa/" in e for e in enlaces)
    pagina.click("#lista-enlaces a >> nth=1")
    pagina.wait_for_selector("text=Tú (Jugador 3)")
    assert pagina.errores == [], pagina.errores


def test_un_enlace_falso_no_entra(servidor, pagina):
    url, _, _ = servidor
    pagina.goto(url + "/#/mesa/inventada/codigo")
    pagina.wait_for_selector("text=Mesa no disponible")
    assert not pagina.query_selector_all("#tapete .carta:not(.reverso)")


def test_torneo_clasificacion_y_reglas(servidor, pagina):
    url, _, _ = servidor
    pagina.goto(url + "/#/torneo")
    pagina.wait_for_selector("#participantes input", state="attached")
    for casilla in pagina.query_selector_all("#participantes input"):
        if casilla.get_attribute("value") not in ("random", "basico", "bots/prudente.py"):
            casilla.uncheck()
    pagina.fill("#partidas-torneo", "4")
    pagina.click("#lanzar-torneo")
    pagina.wait_for_selector("#resultado-torneo table.datos", timeout=60000)
    filas = pagina.query_selector_all("#resultado-torneo table.datos:not(.cruces) tbody tr")
    assert len(filas) == 3
    pagina.goto(url + "/#/clasificacion")
    pagina.wait_for_selector("#clasificacion table.datos")
    pagina.goto(url + "/#/reglas")
    pagina.wait_for_selector("#reglas h1")
    assert pagina.errores == [], pagina.errores


# --- Torneos privados ---


def _nueva_persona(navegador, url, nombre, errores):
    """Un navegador aparte (su propia cookie de sesión) con una cuenta recién creada."""
    contexto = navegador.new_context()
    p = contexto.new_page()
    p.on("pageerror", lambda e: errores.append(str(e)))
    p.on("dialog", lambda d: d.accept())  # confirmaciones ("¿Sortear…?")
    p.goto(url)
    p.wait_for_selector("#form-registro", state="visible")
    p.fill("#registro-nombre", nombre)
    p.fill("#registro-clave", "clave-larga-1")
    p.click("#form-registro button[type=submit]")
    p.wait_for_selector(f"#cuenta-barra .quien-soy:has-text('{nombre}')")
    return p


def test_torneo_privado_de_principio_a_fin(servidor, navegador):
    url, _, _ = servidor
    errores = []
    org = _nueva_persona(navegador, url + "/#/torneos", "Organiza", errores)
    org.wait_for_selector("#form-privado", state="visible")
    org.fill("#privado-nombre", "Torneo de prueba")
    org.check("#opciones-formato input[value=grupos]")
    assert org.is_visible("#privado-tam-grupo")  # opciones de grupos solo con grupos
    org.fill("#privado-parejas", "32")
    org.wait_for_selector("#vista-previa:has-text('8 grupos de 4')")
    org.check("#opciones-formato input[value=eliminatoria]")
    assert not org.is_visible("#privado-tam-grupo")
    org.click("#form-privado button[type=submit]")
    enlace = org.inner_text(".invitacion code")
    assert "#/t/" in enlace
    # Dos parejas se inscriben desde el enlace: sin cuenta, el enlace lleva a crearla y vuelve.
    jugadores = []
    for i in range(2):
        a = _nueva_persona(navegador, enlace, f"Ana{i}", errores)
        b = _nueva_persona(navegador, enlace, f"Bea{i}", errores)
        a.wait_for_selector("#form-pareja")
        a.fill("#pareja-nombre", f"Pareja {i}")
        a.fill("#pareja-companero", f"Bea{i}")
        a.click("#form-pareja button[type=submit]")
        a.wait_for_selector("text=Falta que")
        b.reload()
        b.click("button:has-text('Aceptar')")
        b.wait_for_selector("text=Estás inscrito")
        jugadores += [a, b]
    org.reload()
    org.click("button:has-text('Sortear y empezar ahora')")
    org.wait_for_selector(".cuadro h3:has-text('Final')")
    # Cada uno le da a «Empezar»; hasta que no le da el cuarto, nadie entra en la mesa.
    for i, p in enumerate(jugadores):
        p.reload()
        p.click(".partido.mio button:has-text('Empezar')")
        if i < 3:
            p.wait_for_selector(".partido.mio .listo-ok")
            p.wait_for_selector(f".partido.mio .sala:has-text('{i + 1}/4 listos')")
            assert "/#/t/" in p.url
    # Con el último, los cuatro entran solos en la misma mesa, cada uno en su asiento.
    mesas = set()
    for p in jugadores:
        p.wait_for_url("**/#/mesa/**", timeout=10000)
        nombre = p.inner_text("#cuenta-barra .quien-soy")
        p.wait_for_selector(f"text=Tú ({nombre})")
        mesas.add(p.url.split("#/mesa/")[1].split("/")[0])
        assert p.eval_on_selector_all(".asiento-mesa:not(.abajo) .carta:not(.reverso)",
                                      "els => els.length") == 0
    assert len(mesas) == 1
    # Una pareja no se presenta: el organizador da la final por ganada.
    org.reload()
    org.click("details.dar-ganador summary")
    org.click("details.dar-ganador[open] button >> nth=0")
    org.wait_for_selector(".campeon")
    jugadores[0].wait_for_selector("text=Volver al torneo", timeout=10000)
    jugadores[0].click("text=Volver al torneo")
    jugadores[0].wait_for_selector(".campeon")
    assert errores == [], errores


def test_aviso_de_version_nueva(servidor, pagina):
    """Si se publica una versión nueva con la pestaña abierta, la página avisa para recargar."""
    url, *_ = servidor
    pagina.goto(url)
    pagina.wait_for_selector("#vista-inicio")
    assert pagina.locator("#version-nueva").count() == 0  # misma versión: sin aviso

    def otra_version(ruta):
        respuesta = ruta.fetch()
        ruta.fulfill(response=respuesta, headers={**respuesta.headers, "x-mus-version": "nueva"})

    pagina.route("**/api/**", otra_version)
    pagina.goto(url + "/#/reglas")  # cualquier llamada al API
    pagina.wait_for_selector("#version-nueva")
    pagina.unroute("**/api/**")
    pagina.get_by_role("button", name="Recargar").click()
    pagina.wait_for_load_state()
    pagina.wait_for_selector("#vista-inicio", state="attached")
    assert pagina.locator("#version-nueva").count() == 0
    assert not pagina.errores, pagina.errores
