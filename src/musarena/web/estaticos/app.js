/* Mus Arena en el navegador.
 *
 * Todo lo que llega del servidor se pinta con textContent (nunca como HTML), así que nadie
 * puede colar código en la página de otro jugador a través del chat o de un nombre.
 * El código secreto de cada asiento va detrás del "#" del enlace (#/mesa/<id>/<código>):
 * esa parte nunca se manda a ningún servidor; aquí se envía en la cabecera X-Token.
 * La sesión de la cuenta va en una cookie HttpOnly (esta página no la puede leer), y cada
 * petición lleva la cabecera X-Mus, que otra web no puede poner (protección contra CSRF).
 */
"use strict";

// --- Utilidades ------------------------------------------------------------------------

const $ = (selector, raiz = document) => raiz.querySelector(selector);

function el(etiqueta, atributos = {}, ...hijos) {
  const nodo = document.createElement(etiqueta);
  for (const [clave, valor] of Object.entries(atributos)) {
    if (valor === null || valor === undefined || valor === false) continue;
    if (clave === "class") nodo.className = valor;
    else if (clave.startsWith("on")) nodo.addEventListener(clave.slice(2), valor);
    else nodo.setAttribute(clave, valor === true ? "" : valor);
  }
  for (const hijo of hijos.flat()) {
    if (hijo === null || hijo === undefined || hijo === false) continue;
    nodo.append(hijo instanceof Node ? hijo : document.createTextNode(String(hijo)));
  }
  return nodo;
}

async function api(metodo, ruta, datos, token) {
  const opciones = { method: metodo, headers: { "X-Mus": "1" } };
  if (datos !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(datos);
  }
  if (token) opciones.headers["X-Token"] = token;
  const respuesta = await fetch(ruta, opciones);
  comprobarVersion(respuesta.headers.get("X-Mus-Version"));
  const tipo = respuesta.headers.get("Content-Type") || "";
  const cuerpo = tipo.includes("application/json") ? await respuesta.json() : await respuesta.text();
  if (!respuesta.ok) {
    const error = new Error(explicarError(cuerpo, respuesta.status));
    error.codigo = respuesta.status;
    throw error;
  }
  return cuerpo;
}

// Versión de esta página. Si el servidor responde con otra, se ha publicado una versión nueva
// mientras la pestaña estaba abierta: se avisa para recargar (la partida y la sesión siguen
// igual, porque están en el servidor y en el enlace).
const VERSION = document.querySelector('meta[name="mus-version"]')?.content;

function comprobarVersion(delServidor) {
  if (!VERSION || !delServidor || delServidor === VERSION || $("#version-nueva")) return;
  document.body.append(el("div", { id: "version-nueva", class: "version-nueva", role: "status" },
    "Hay una versión nueva de la web.",
    el("button", { class: "boton principal", onclick: () => location.reload() }, "Recargar")));
}

function explicarError(cuerpo, codigo) {
  if (cuerpo && typeof cuerpo === "object") {
    if (typeof cuerpo.detalle === "string") return cuerpo.detalle;
    if (Array.isArray(cuerpo.detail)) return "Datos no válidos";
  }
  return codigo >= 500 ? "Error del servidor; inténtalo otra vez" : `Error ${codigo}`;
}

const PAREJA = (p) => (p === 0 ? "A" : "B");
const LANCES = { grande: "Grande", chica: "Chica", pares: "Pares", juego: "Juego", punto: "Punto" };

// --- Cartas ---------------------------------------------------------------------------

const SVG = "http://www.w3.org/2000/svg";
const PALOS = {
  oros: [["circle", { cx: 12, cy: 12, r: 9 }], ["circle", { cx: 12, cy: 12, r: 4.5, fill: "#fffdf7", opacity: ".55" }]],
  copas: [["path", { d: "M5.5 3h13c0 5.8-2.9 9.2-6.5 9.2S5.5 8.8 5.5 3z" }], ["path", { d: "M11 12h2v5h3.2v3H7.8v-3H11z" }]],
  espadas: [["path", { d: "M12 1.5l2.2 3.4V15H9.8V4.9z" }], ["path", { d: "M6.5 15h11v2.2h-11z" }], ["path", { d: "M10.9 17.2h2.2v5.3h-2.2z" }]],
  bastos: [["path", { d: "M10.4 2.3c1.7-.8 3.6-.2 4.3 1.2l-.9 2.3 1 2.6-.9 2.3 1 2.6-.9 2.3V21h-3.8v-5.4l-.9-2.3.9-2.6-.9-2.3.9-2.6-.9-2.3c0-.4.3-.9.7-1.2z" }]],
};

function svgPalo(palo) {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("fill", "currentColor");
  for (const [forma, atributos] of PALOS[palo] || []) {
    const nodo = document.createElementNS(SVG, forma);
    for (const [k, v] of Object.entries(atributos)) nodo.setAttribute(k, v);
    svg.append(nodo);
  }
  return svg;
}

function carta(c, opciones = {}) {
  const clases = ["carta", c.palo];
  if (opciones.pequena) clases.push("pequena");
  if (opciones.seleccionable) clases.push("seleccionable");
  if (opciones.elegida) clases.push("elegida");
  const nodo = el(opciones.seleccionable ? "button" : "div",
    { class: clases.join(" "), title: c.nombre, "aria-label": c.nombre,
      "aria-pressed": opciones.seleccionable ? String(!!opciones.elegida) : null,
      type: opciones.seleccionable ? "button" : null, onclick: opciones.onclick },
    el("span", { class: "num" }, c.numero), svgPalo(c.palo),
    el("span", { class: "num abajo" }, c.numero));
  return nodo;
}

// replaceChildren escribiría "null" como texto: se quitan antes los huecos vacíos.
const poner = (caja, ...hijos) => caja.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));

const reverso = (pequena) => el("div", { class: `carta reverso${pequena ? " pequena" : ""}`, "aria-hidden": "true" });

// --- Navegación -----------------------------------------------------------------------

const VISTAS = ["inicio", "mesa", "torneo", "clasificacion", "reglas", "entrar", "torneos", "t"];
// Pestaña de la barra que se marca en cada vista.
const PESTANA = { mesa: "inicio", t: "torneos", entrar: "torneos" };

function ruta() {
  const partes = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return { nombre: partes[0] || "inicio", partes: partes.slice(1) };
}

function mostrar() {
  const { nombre, partes } = ruta();
  const vista = VISTAS.includes(nombre) ? nombre : "inicio";
  for (const v of VISTAS) $(`#vista-${v}`).hidden = v !== vista;
  for (const a of document.querySelectorAll(".barra nav a")) {
    a.classList.toggle("activa", a.dataset.ruta === (PESTANA[vista] || vista));
  }
  if (vista !== "mesa") Mesa.parar();
  if (vista !== "t") Privado.parar();
  if (vista === "inicio") Inicio.abrir();
  if (vista === "mesa") Mesa.abrir(partes[0], partes[1]);
  if (vista === "torneo") Torneo.abrir();
  if (vista === "clasificacion") Clasificacion.abrir();
  if (vista === "reglas") Reglas.abrir();
  if (vista === "entrar") Cuenta.abrir();
  if (vista === "torneos") Privados.abrir();
  if (vista === "t") Privado.abrir(partes[0]);
}

// --- Inicio: crear una mesa -----------------------------------------------------------

const Inicio = {
  opciones: null,

  async abrir() {
    if (this.opciones) return;
    try {
      this.opciones = await api("GET", "/api/opciones");
    } catch (e) {
      this.error(e.message);
      return;
    }
    const porDefecto = ["humano", "inteligente", "inteligente", "inteligente"];
    for (let a = 0; a < 4; a++) {
      const select = $(`#asiento-${a}`);
      select.replaceChildren(...this.opciones.tipos.map((t) =>
        el("option", { value: t.valor, title: t.descripcion }, t.valor === "humano" ? "Humano" : `Bot: ${t.nombre}`)));
      select.value = porDefecto[a];
      select.addEventListener("change", () => this.mostrarNombres());
    }
    this.mostrarNombres();
  },

  mostrarNombres() {
    // La casilla del nombre solo aparece en los asientos de humanos.
    for (let a = 0; a < 4; a++) $(`#nombre-${a}`).hidden = $(`#asiento-${a}`).value !== "humano";
  },

  error(texto) {
    const p = $("#error-mesa");
    p.textContent = texto || "";
    p.hidden = !texto;
  },

  async crear(evento) {
    evento.preventDefault();
    this.error("");
    const asientos = [0, 1, 2, 3].map((a) => $(`#asiento-${a}`).value);
    if (!asientos.includes("humano")) {
      this.error("Pon al menos un humano: las partidas solo de bots se juegan en el torneo.");
      return;
    }
    const boton = $("#form-mesa button[type=submit]");
    boton.disabled = true;
    try {
      const datos = await api("POST", "/api/mesas", {
        asientos, mejor_de: Number($("#mejor-de").value),
        nombres: [0, 1, 2, 3].map((a) => (asientos[a] === "humano" && $(`#nombre-${a}`).value.trim()) || null) });
      const humanos = datos.asientos.filter((a) => a.token);
      const enlace = (a) => `${location.origin}${location.pathname}#/mesa/${datos.mesa}/${a.token}`;
      if (humanos.length === 1) {
        location.hash = `#/mesa/${datos.mesa}/${humanos[0].token}`;
        return;
      }
      $("#lista-enlaces").replaceChildren(...humanos.map((a) => {
        const url = enlace(a);
        const codigo = el("code", {}, url);
        return el("li", {},
          el("strong", {}, `${a.nombre} (pareja ${PAREJA(a.asiento % 2)})`), codigo,
          el("div", { class: "fila" },
            el("a", { class: "boton principal", href: url.slice(url.indexOf("#")) }, "Entrar en este asiento"),
            el("button", { class: "boton", type: "button", onclick: (e) => copiar(url, e.currentTarget, codigo) }, "Copiar enlace")));
      }));
      $("#enlaces").hidden = false;
    } catch (e) {
      this.error(e.message);
    } finally {
      boton.disabled = false;
    }
  },
};

async function copiar(texto, boton, alternativa) {
  try {
    await navigator.clipboard.writeText(texto);
    boton.textContent = "Copiado";
    setTimeout(() => (boton.textContent = "Copiar enlace"), 1500);
  } catch {
    const rango = document.createRange();
    rango.selectNodeContents(alternativa);
    const sel = getSelection();
    sel.removeAllRanges();
    sel.addRange(rango);
    boton.textContent = "Selecciónalo y cópialo";
  }
}

// --- La mesa --------------------------------------------------------------------------

const Mesa = {
  id: null, token: null, v: null, temporizador: null, seleccion: new Set(),
  resumenVisto: 0, enviando: false, fallos: 0,

  abrir(id, token) {
    if (!id || !token) { location.hash = "#/"; return; }
    if (this.id !== id || this.token !== token) {
      this.id = id; this.token = token; this.v = null; this.seleccion.clear(); this.resumenVisto = null;
    }
    this.parar();
    this.refrescar();
  },

  parar() {
    clearTimeout(this.temporizador);
    this.temporizador = null;
  },

  programar(ms) {
    this.parar();
    if (ruta().nombre === "mesa") this.temporizador = setTimeout(() => this.refrescar(), ms);
  },

  async refrescar() {
    try {
      const v = await api("GET", `/api/mesas/${this.id}`, undefined, this.token);
      this.fallos = 0;
      this.pintar(v);
    } catch (e) {
      this.fallos++;
      if (e.codigo === 403 || e.codigo === 404) { this.pintarError(e.message); return; }
      this.aviso(this.fallos > 2 ? "Sin conexión con el servidor; reintentando…" : "");
    }
    // Mientras juegan los bots se pregunta a menudo; si espera al humano, mucho menos.
    const v = this.v;
    const espera = !v ? 1500 : v.ganador !== null ? 4000 : v.es_mi_turno ? 2000 : 250;
    this.programar(this.fallos ? Math.min(5000, 1000 * this.fallos) : espera);
  },

  async jugar(accionId) {
    if (this.enviando || !this.v) return;
    this.enviando = true;
    this.bloquearAcciones();
    try {
      const v = await api("POST", `/api/mesas/${this.id}/jugar`, { accion: accionId, version: this.v.version }, this.token);
      this.seleccion.clear();
      this.pintar(v);
    } catch (e) {
      this.aviso(e.message);
    } finally {
      this.enviando = false;
      this.programar(150);
    }
  },

  async escribir(evento) {
    evento.preventDefault();
    const entrada = $("#texto-chat");
    const texto = entrada.value.trim();
    if (!texto || !this.id) return;
    try {
      const v = await api("POST", `/api/mesas/${this.id}/chat`, { texto }, this.token);
      entrada.value = "";
      this.pintar(v);
    } catch (e) {
      this.aviso(e.message);
    }
  },

  rel(asiento) { return (asiento - this.v.asiento + 4) % 4; },

  quien(asiento) {
    const r = this.rel(asiento);
    const base = this.v.jugadores[asiento].nombre;
    return r === 0 ? `Tú (${base})` : r === 2 ? `Compañero (${base})` : `Rival (${base})`;
  },

  pintar(v) {
    const cambio = !this.v || v.version !== this.v.version;
    this.v = v;
    if (this.resumenVisto === null) {
      // Al entrar en una mesa empezada no se enseña el resumen de una mano antigua.
      this.resumenVisto = v.manos_jugadas.length ? v.manos_jugadas[v.manos_jugadas.length - 1].numero : 0;
    }
    if (!cambio && !this.enviando) return;
    this.pintarAsientos();
    this.pintarCentro();
    this.pintarMarcador();
    this.pintarHistorial();
    this.pintarChat();
    this.pintarAcciones();
    this.pintarResumen();
  },

  pintarError(texto) {
    let volver = null;
    try { volver = sessionStorage.getItem(`volver:${this.id}`); } catch { /* sin almacenamiento */ }
    $("#centro").replaceChildren(el("p", { class: "lance" }, "Mesa no disponible"),
      el("p", {}, volver ? "Este partido ya no se juega en esta mesa (quizá el organizador lo ha dado por terminado)." : texto),
      volver ? el("a", { class: "boton principal", href: volver }, "Volver al torneo")
        : el("a", { class: "boton principal", href: "#/" }, "Crear otra mesa"));
    $("#acciones").replaceChildren();
  },

  ultimaAccion(asiento) {
    // Lo último que ha dicho este jugador en el lance o la fase en curso (para el bocadillo):
    // se para al llegar al aviso de que empezó (por ejemplo "Se juega a Grande").
    const h = this.v.historial;
    for (let i = h.length - 1; i >= 0; i--) {
      const e = h[i];
      if (e.asiento === asiento) return e.texto;
      if (e.asiento === null && /^(Se juega|Todos piden mus|Mano \d)/.test(e.texto)) break;
    }
    return "";
  },

  declaracion(asiento) {
    return this.v.declaraciones.map((d) => `${LANCES[d.lance]}: ${d.tiene[asiento] ? "sí" : "no"}`).join(" · ");
  },

  pintarAsientos() {
    const v = this.v;
    const descartando = v.fase === "descarte" && v.es_mi_turno;
    for (let r = 0; r < 4; r++) {
      const asiento = (v.asiento + r) % 4;
      const jugador = v.jugadores[asiento];
      const caja = $(`.asiento-mesa[data-rel="${r}"]`);
      caja.classList.toggle("su-turno", v.turno === asiento && v.ganador === null);
      const etiqueta = el("div", { class: "etiqueta-jugador" },
        el("span", {}, this.quien(asiento)),
        el("span", { class: "chip" }, jugador.humano ? "humano" : `bot ${jugador.tipo}`),
        v.mano === asiento ? el("span", { class: "chip mano" }, v.corrida ? "empieza" : "mano") : null,
        v.turno === asiento && v.ganador === null ? el("span", { class: "chip turno" }, r === 0 ? "te toca" : "piensa…") : null);
      let cartas;
      if (r === 0) {
        cartas = el("div", { class: "mano-cartas" }, v.cartas.map((c) => carta(c, {
          seleccionable: descartando, elegida: this.seleccion.has(c.id),
          onclick: descartando ? () => this.alternar(c.id) : null })));
      } else {
        cartas = el("div", { class: "mano-cartas" }, [0, 1, 2, 3].map(() => reverso(true)));
      }
      const decl = this.declaracion(asiento);
      caja.classList.toggle("companero", r === 2);
      caja.classList.toggle("rival", r === 1 || r === 3);
      poner(caja,
        r === 0 ? null : etiqueta,
        el("div", { class: "bocadillo", "aria-live": "polite" }, this.ultimaAccion(asiento)),
        cartas, decl ? el("small", { class: "declaracion" }, decl) : null,
        r === 0 ? etiqueta : null);
    }
  },

  alternar(id) {
    if (this.seleccion.has(id)) this.seleccion.delete(id); else this.seleccion.add(id);
    this.pintarAsientos();
    this.pintarAcciones();
  },

  textoApuesta() {
    const ap = this.v.apuesta;
    if (!ap || ap.pareja_apostadora === null) return null;
    const quien = ap.pareja_apostadora === this.v.pareja ? "Vosotros" : "Los rivales";
    return ap.ordago ? `¡Órdago! (${quien.toLowerCase()})` : `${quien} ${ap.pareja_apostadora === this.v.pareja ? "habéis apostado" : "apuestan"} ${ap.tantos} tantos`;
  },

  pintarCentro() {
    const v = this.v;
    const hijos = [];
    if (v.ganador !== null) {
      const ganamos = v.ganador === v.pareja;
      let volver = null;  // las mesas de los torneos privados vuelven al torneo
      try { volver = sessionStorage.getItem(`volver:${this.id}`); } catch { /* sin almacenamiento */ }
      hijos.push(el("p", { class: "lance" }, ganamos ? "¡Habéis ganado!" : "Han ganado los rivales"),
        el("p", {}, `Vacas: ${v.vacas[v.pareja]} a ${v.vacas[1 - v.pareja]}`),
        volver ? el("a", { class: "boton principal", href: volver }, "Volver al torneo")
          : el("a", { class: "boton principal", href: "#/" }, "Jugar otra partida"));
    } else {
      const titulo = v.fase === "mus" ? (v.corrida ? "Mano corrida" : "Mus") : v.fase === "descarte" ? "Descartes" : LANCES[v.lance] || "";
      hijos.push(el("p", { class: "lance" }, titulo));
      const apuesta = this.textoApuesta();
      if (apuesta) hijos.push(el("p", { class: "apuesta-centro" }, apuesta));
      else if (v.fase === "lance") hijos.push(el("p", { class: "apuesta-centro tenue" }, "Sin apuestas"));
      hijos.push(v.es_mi_turno ? el("p", { class: "aviso-turno" }, "Te toca")
        : el("p", { class: "espera" }, `Turno de ${this.quien(v.turno)}`));
    }
    $("#centro").replaceChildren(...hijos);
  },

  pintarMarcador() {
    const v = this.v;
    const fila = (p) => el("tr", { class: p === v.pareja ? "mia" : null },
      el("td", {}, `${p === v.pareja ? "Vosotros" : "Rivales"} · ${PAREJA(p)}`),
      el("td", {}, v.tantos[p]), el("td", {}, v.vacas[p]));
    $("#marcador").replaceChildren(
      el("h3", {}, `Mano ${v.numero_mano} · gana quien llegue a ${v.vacas_para_ganar} vacas`),
      el("table", {}, el("thead", {}, el("tr", {}, el("th", {}, "Pareja"), el("th", {}, "Tantos"), el("th", {}, "Vacas"))),
        el("tbody", {}, fila(0), fila(1))));
  },

  pintarHistorial() {
    const lista = $("#historial");
    lista.replaceChildren(...this.v.historial.map((e) => e.asiento === null
      ? el("li", { class: "sistema" }, e.texto)
      : el("li", {}, el("b", {}, `${e.quien}: `), e.texto)));
    lista.scrollTop = lista.scrollHeight;
  },

  pintarChat() {
    const lista = $("#chat");
    lista.replaceChildren(...this.v.chat.map((m) => el("li", {}, el("b", {}, `${m.quien}: `), m.texto)));
    lista.scrollTop = lista.scrollHeight;
  },

  bloquearAcciones() {
    for (const b of document.querySelectorAll("#acciones button, #acciones select")) b.disabled = true;
  },

  pintarAcciones() {
    const v = this.v;
    const caja = $("#acciones");
    if (v.ganador !== null) { caja.replaceChildren(el("span", { class: "pista" }, "Partida terminada")); return; }
    if (!v.es_mi_turno) {
      caja.replaceChildren(el("span", { class: "pista" }, `Esperando a ${this.quien(v.turno)}…`));
      return;
    }
    const acciones = v.acciones;
    const de = (tipo) => acciones.filter((a) => a.tipo === tipo);
    const boton = (a, texto, principal) => el("button",
      { class: `boton${principal ? " principal" : ""}`, type: "button", onclick: () => this.jugar(a.id) }, texto || a.texto);
    const hijos = [];

    if (v.fase === "mus") {
      hijos.push(boton(de("Mus")[0], v.corrida ? "Mus (pasar la mano)" : "Mus", true),
        boton(de("NoHayMus")[0], v.corrida ? "Cortar (ser mano)" : "No hay mus (cortar)"));
    } else if (v.fase === "descarte") {
      const elegidas = [...this.seleccion].sort();
      const descarte = de("Descarte").find((a) => a.cartas.length === elegidas.length && a.cartas.every((c, i) => c === elegidas[i]));
      hijos.push(el("span", { class: "pista" }, "Toca las cartas que quieres tirar"),
        el("button", { class: "boton principal", type: "button", disabled: !descarte, onclick: () => descarte && this.jugar(descarte.id) },
          elegidas.length ? `Descartar ${elegidas.length} carta${elegidas.length > 1 ? "s" : ""}` : "Descartar"));
    } else {
      const envidos = de("Envido");
      const reenvidos = de("Reenvido");
      for (const tipo of ["Paso", "Quiero", "NoQuiero"]) for (const a of de(tipo)) hijos.push(boton(a, null, tipo === "Quiero"));
      if (envidos.length) {
        hijos.push(boton(envidos[0], "Envido (2)"));
        if (envidos.length > 1) hijos.push(this.selectorCantidad(envidos.slice(1), "Envidar"));
      }
      if (reenvidos.length) hijos.push(this.selectorCantidad(reenvidos, "Subir"));
      for (const a of de("Ordago")) hijos.push(el("button", { class: "boton", type: "button", style: "border-color:var(--copas);color:var(--copas)", onclick: () => this.jugar(a.id) }, "Órdago"));
      const apuesta = this.textoApuesta();
      hijos.unshift(el("span", { class: "pista" }, apuesta ? `${apuesta}: ¿qué haces?` : `${LANCES[v.lance]}: ¿apuestas?`));
    }
    caja.replaceChildren(...hijos);
  },

  selectorCantidad(acciones, verbo) {
    const select = el("select", { "aria-label": `${verbo}: cantidad` },
      acciones.map((a) => el("option", { value: a.id }, `${a.tantos} tantos`)));
    return el("span", { class: "fila" }, select,
      el("button", { class: "boton", type: "button", onclick: () => this.jugar(Number(select.value)) }, verbo));
  },

  pintarResumen() {
    const v = this.v;
    const manos = v.manos_jugadas;
    const caja = $("#resumen-mano");
    if (!manos.length) { caja.hidden = true; return; }
    const ultima = manos[manos.length - 1];
    if (ultima.numero <= this.resumenVisto) return;
    if (!caja.hidden && caja.dataset.mano === String(ultima.numero)) return;  // ya está abierto: no se rehace
    caja.dataset.mano = String(ultima.numero);
    const cobros = ultima.cobros.filter((c) => c.tantos > 0 || c.motivo.startsWith("órdago"));
    const cerrar = () => { this.resumenVisto = ultima.numero; caja.hidden = true; };
    caja.replaceChildren(el("div", { class: "resumen-caja", role: "dialog", "aria-modal": "true", "aria-label": `Fin de la mano ${ultima.numero}` },
      el("h2", {}, `Fin de la mano ${ultima.numero}`),
      ultima.cartas.map((cartas, a) => el("div", { class: "jugador-resumen" },
        el("strong", {}, this.quien(a)), el("div", { class: "mano-cartas", style: "justify-content:flex-start" }, cartas.map((c) => carta(c, { pequena: true }))))),
      el("h3", {}, "Cobros"),
      cobros.length ? el("ul", { class: "cobros" }, cobros.map((c) => el("li", {},
        el("strong", { class: c.pareja === v.pareja ? "nuestro" : "suyo" },
          `${c.pareja === v.pareja ? "Vosotros" : "Rivales"} +${c.tantos}`),
        ` · ${c.lance ? `${LANCES[c.lance]}: ` : ""}${c.motivo}`))) : el("p", {}, "Nadie cobra en esta mano."),
      el("p", {}, `Tantos: vosotros ${ultima.tantos[v.pareja]}, rivales ${ultima.tantos[1 - v.pareja]}` +
        (ultima.ganador_vaca !== null ? ` · ${ultima.ganador_vaca === v.pareja ? "¡Vaca para vosotros!" : "Vaca para los rivales"}` : "")),
      el("button", { class: "boton principal", type: "button", onclick: cerrar }, "Seguir")));
    caja.hidden = false;
    $("button", caja).focus();
  },

  aviso(texto) {
    if (!texto) return;
    const caja = $("#acciones");
    caja.prepend(el("span", { class: "error" }, texto));
  },
};

// --- Torneo ---------------------------------------------------------------------------

const Torneo = {
  cargado: false, temporizador: null,

  async abrir() {
    if (!this.cargado) {
      try {
        const datos = await api("GET", "/api/torneos/participantes");
        $("#participantes").replaceChildren(...datos.participantes.map((p) =>
          el("label", {}, el("input", { type: "checkbox", value: p.valor, checked: true }), p.nombre)));
        const partidas = $("#partidas-torneo");
        partidas.max = datos.max_partidas;
        partidas.value = Math.min(40, datos.max_partidas);
        this.cargado = true;
      } catch (e) { this.error(e.message); return; }
    }
    try {
      const { torneo } = await api("GET", "/api/torneos/en-marcha");
      if (torneo) this.seguir(torneo.id);
    } catch { /* sin torneo en marcha */ }
  },

  error(texto) {
    const p = $("#error-torneo");
    p.textContent = texto || "";
    p.hidden = !texto;
  },

  async lanzar(evento) {
    evento.preventDefault();
    this.error("");
    const participantes = [...document.querySelectorAll("#participantes input:checked")].map((i) => i.value);
    if (participantes.length < 2) { this.error("Elige al menos 2 participantes."); return; }
    const partidas = Number($("#partidas-torneo").value);
    try {
      const estado = await api("POST", "/api/torneos", { participantes, partidas });
      this.seguir(estado.id);
    } catch (e) { this.error(e.message); }
  },

  seguir(id) {
    clearTimeout(this.temporizador);
    $("#lanzar-torneo").disabled = true;
    $("#progreso-torneo").hidden = false;
    $("#resultado-torneo").replaceChildren();
    const paso = async () => {
      try {
        const estado = await api("GET", `/api/torneos/${id}`);
        $("#barra-progreso").style.width = `${Math.round(estado.progreso * 100)}%`;
        $("#texto-progreso").textContent = `Jugando: ${estado.hechas} de ${estado.total} partidas`;
        if (estado.estado === "jugando") { this.temporizador = setTimeout(paso, 400); return; }
        $("#lanzar-torneo").disabled = false;
        $("#progreso-torneo").hidden = true;
        if (estado.estado === "error") { this.error(estado.error); return; }
        pintarResultado(estado.resultado, $("#resultado-torneo"));
      } catch (e) {
        this.error(e.message);
        $("#lanzar-torneo").disabled = false;
      }
    };
    paso();
  },
};

function pintarResultado(r, contenedor) {
  const orden = r.clasificacion.map((f) => f.participante);
  const nombre = Object.fromEntries(r.clasificacion.map((f) => [f.participante, f.nombre]));
  const victorias = (a, b) => {
    const c = r.cruces.find((x) => (x.a === a && x.b === b) || (x.a === b && x.b === a));
    if (!c) return null;
    return c.a === a ? c.victorias_a / c.partidas : 1 - c.victorias_a / c.partidas;
  };
  const pct = (x) => `${(100 * x).toFixed(1)} %`;
  const clasif = el("table", { class: "datos" },
    el("thead", {}, el("tr", {}, el("th", {}, "#"), el("th", { class: "izq" }, "Bot"), el("th", {}, "Elo"),
      el("th", {}, "Victorias"), el("th", {}, "Partidas"), el("th", {}, "% (± 95 %)"), el("th", {}, "Faltas"))),
    el("tbody", {}, r.clasificacion.map((f) => el("tr", { class: f.puesto === 1 ? "primero" : null },
      el("td", {}, f.puesto), el("td", { class: "izq" }, f.nombre), el("td", {}, Math.round(f.elo)),
      el("td", {}, f.victorias), el("td", {}, f.partidas), el("td", {}, `${pct(f.porcentaje)} ± ${pct(f.margen_95)}`),
      el("td", {}, f.faltas || 0)))));
  const cruces = el("table", { class: "datos cruces" },
    el("thead", {}, el("tr", {}, el("th", {}, ""), orden.map((p) => el("th", {}, nombre[p])))),
    el("tbody", {}, orden.map((a) => el("tr", {}, el("th", { class: "izq" }, nombre[a]), orden.map((b) => {
      if (a === b) return el("td", {}, "—");
      const x = victorias(a, b);
      const fuerza = Math.round(Math.abs(x - 0.5) * 140);
      const color = x >= 0.5 ? "var(--bastos)" : "var(--copas)";
      return el("td", { style: `background:color-mix(in srgb, ${color} ${fuerza}%, transparent)` }, `${Math.round(100 * x)} %`);
    })))));
  contenedor.replaceChildren(
    el("p", { class: "entradilla" }, `${r.partidas_por_cruce} partidas por cruce · ${r.fecha.replace("T", " ")} · ${r.segundos} s`),
    el("h2", {}, "Clasificación"), el("div", { class: "tabla" }, clasif),
    el("h2", {}, "Cruces"), el("p", {}, "Porcentaje de victorias del bot de la fila contra el de la columna."),
    el("div", { class: "tabla" }, cruces),
    (r.incidencias || []).length ? [
      el("h2", {}, "Faltas"),
      el("p", {}, "Partidas perdidas porque el bot falló, se colgó o jugó ilegal (el torneo sigue igualmente):"),
      el("ul", {}, r.incidencias.map((i) => el("li", {}, el("strong", {}, i.nombre), `: ${i.motivo}`)))] : []);
}

// --- Cuenta ---------------------------------------------------------------------------
// La sesión va en una cookie que el JavaScript no puede leer: aquí solo se pregunta al
// servidor quién soy. Si una página necesita sesión, se apunta a dónde volver y se va a entrar.

const Cuenta = {
  usuario: undefined,  // undefined: aún no se sabe; null: sin sesión

  async cargar() {
    try {
      this.usuario = (await api("GET", "/api/cuenta")).usuario;
    } catch {
      this.usuario = null;
    }
    this.pintarBarra();
    return this.usuario;
  },

  pintarBarra() {
    const caja = $("#cuenta-barra");
    if (this.usuario) {
      poner(caja, el("span", { class: "quien-soy" }, this.usuario.nombre),
        el("button", { class: "boton pequeno", type: "button", onclick: () => this.salir() }, "Salir"));
    } else {
      poner(caja, el("a", { class: "boton pequeno", href: "#/entrar" }, "Entrar"));
    }
  },

  // Para las páginas que necesitan sesión: si no la hay, manda a entrar y luego vuelve aquí.
  async exigir(motivo) {
    if (this.usuario === undefined) await this.cargar();
    if (this.usuario) return true;
    try { sessionStorage.setItem("destino", location.hash); } catch { /* sin almacenamiento */ }
    $("#motivo-entrar").textContent = motivo;
    location.hash = "#/entrar";
    return false;
  },

  abrir() {
    for (const f of ["#form-entrar", "#form-registro"]) $(".error", $(f)).hidden = true;
    if (this.usuario) this.volver();
  },

  volver() {
    let destino = "#/torneos";
    try {
      destino = sessionStorage.getItem("destino") || destino;
      sessionStorage.removeItem("destino");
    } catch { /* sin almacenamiento */ }
    location.hash = destino;
  },

  async enviar(evento, ruta, prefijo) {
    evento.preventDefault();
    const form = evento.currentTarget;
    const error = $(".error", form);
    error.hidden = true;
    const boton = $("button[type=submit]", form);
    boton.disabled = true;
    try {
      const datos = await api("POST", ruta, { nombre: $(`#${prefijo}-nombre`).value.trim(), clave: $(`#${prefijo}-clave`).value });
      this.usuario = datos.usuario;
      form.reset();
      this.pintarBarra();
      Privados.lista = null;
      this.volver();
    } catch (e) {
      error.textContent = e.message;
      error.hidden = false;
    } finally {
      boton.disabled = false;
    }
  },

  async salir() {
    try { await api("POST", "/api/cuenta/salir", {}); } catch { /* da igual: se borra aquí */ }
    this.usuario = null;
    this.pintarBarra();
    location.hash = "#/";
  },
};

// --- Torneos privados: lista y crear ---------------------------------------------------

const ESTADOS = { inscripcion: "Inscripción abierta", en_curso: "En juego", terminado: "Terminado", cancelado: "Cancelado" };

const fecha = (segundos) => new Date(segundos * 1000).toLocaleString("es-ES", { dateStyle: "long", timeStyle: "short" });

function falta(segundos) {
  if (segundos <= 0) return "ya ha pasado";
  const min = Math.round(segundos / 60);
  if (min < 60) return `faltan ${min} min`;
  const horas = Math.round(min / 60);
  if (horas < 48) return `faltan ${horas} h`;
  return `faltan ${Math.round(horas / 24)} días`;
}

// datetime-local trabaja en la hora del navegador: se convierte a segundos UTC para el servidor.
function aLocal(fechaJs) {
  const d = new Date(fechaJs.getTime() - fechaJs.getTimezoneOffset() * 60000);
  return d.toISOString().slice(0, 16);
}

const Privados = {
  lista: null, previa: null,

  async abrir() {
    if (!(await Cuenta.exigir("Para organizar un torneo o ver los tuyos, entra o crea una cuenta."))) return;
    $("#form-privado").hidden = !Cuenta.usuario.organizador;
    $("#sin-permiso").hidden = Cuenta.usuario.organizador;
    const fechaInput = $("#privado-fecha");
    if (!fechaInput.value) {
      const d = new Date(Date.now() + 7 * 864e5);
      d.setHours(22, 0, 0, 0);
      fechaInput.value = aLocal(d);
      fechaInput.min = aLocal(new Date());
    }
    this.ajustarFormulario();
    try {
      const { torneos } = await api("GET", "/api/privados");
      this.pintarLista(torneos);
    } catch (e) {
      poner($("#mis-torneos"), el("p", { class: "error" }, e.message));
    }
  },

  pintarLista(torneos) {
    const caja = $("#mis-torneos");
    if (!torneos.length) { caja.replaceChildren(); return; }
    poner(caja, el("div", { class: "tarjeta" }, el("h2", {}, "Tus torneos"),
      el("ul", { class: "lista-torneos" }, torneos.map((t) => el("li", {},
        el("a", { href: `#/t/${t.codigo}` }, t.nombre),
        el("span", { class: `chip-estado ${t.estado}` }, ESTADOS[t.estado]),
        el("small", {}, `${t.parejas}/${t.max_parejas} parejas${t.organizo ? " · lo organizas tú" : ""}`))))));
  },

  formato() {
    const tipo = $("#opciones-formato input:checked").value;
    return {
      tipo, max_parejas: Number($("#privado-parejas").value),
      tam_grupo: Number($("#privado-tam-grupo").value), pasan_por_grupo: Number($("#privado-pasan").value),
      mejor_de: Number($("#privado-mejor-de").value), mejor_de_final: Number($("#privado-mejor-de-final").value),
      tercer_puesto: $("#privado-tercero").checked,
    };
  },

  ajustarFormulario() {
    const tipo = $("#opciones-formato input:checked").value;
    for (const n of document.querySelectorAll("#form-privado .solo-grupos")) n.hidden = tipo !== "grupos";
    for (const n of document.querySelectorAll("#form-privado .no-liga")) n.hidden = tipo === "liga";
    $("#privado-pasan").max = Math.max(1, Number($("#privado-tam-grupo").value) - 1);
    clearTimeout(this.previa);
    this.previa = setTimeout(() => this.vistaPrevia(), 200);
  },

  async vistaPrevia() {
    const caja = $("#vista-previa");
    try {
      const { descripcion } = await api("POST", "/api/privados/vista-previa", { formato: this.formato() });
      caja.textContent = `Con el torneo lleno: ${descripcion}`;
      caja.classList.remove("error");
    } catch (e) {
      caja.textContent = e.message;
      caja.classList.add("error");
    }
  },

  async crear(evento) {
    evento.preventDefault();
    const form = evento.currentTarget;
    const error = $(".error", form);
    error.hidden = true;
    const limite = new Date($("#privado-fecha").value).getTime() / 1000;
    if (!(limite > Date.now() / 1000)) {
      error.textContent = "La fecha límite tiene que ser futura.";
      error.hidden = false;
      return;
    }
    const boton = $("button[type=submit]", form);
    boton.disabled = true;
    try {
      const { codigo } = await api("POST", "/api/privados", { nombre: $("#privado-nombre").value.trim(), formato: this.formato(), fecha_limite: limite });
      $("#privado-nombre").value = "";
      try { sessionStorage.setItem(`recien:${codigo}`, "1"); } catch { /* sin almacenamiento */ }
      location.hash = `#/t/${codigo}`;
    } catch (e) {
      error.textContent = e.message;
      error.hidden = false;
    } finally {
      boton.disabled = false;
    }
  },
};

// --- Un torneo privado ------------------------------------------------------------------

const Privado = {
  codigo: null, v: null, temporizador: null, firma: "",
  // Partidos en los que he dado a "Empezar": cuando empiezan, se entra solo en la mesa.
  esperando: new Set(),

  async abrir(codigo) {
    if (!codigo) { location.hash = "#/torneos"; return; }
    if (!(await Cuenta.exigir("Te han invitado a un torneo: entra o crea una cuenta para verlo e inscribirte."))) return;
    if (codigo !== this.codigo) {
      this.codigo = codigo; this.v = null; this.firma = ""; this.esperando.clear();
      $("#privado").replaceChildren(el("p", {}, "Cargando…"));
    }
    this.refrescar();
  },

  parar() { clearTimeout(this.temporizador); this.temporizador = null; },

  async refrescar() {
    this.parar();
    try {
      this.pintar(await api("GET", `/api/privados/${this.codigo}`));
    } catch (e) {
      if (e.codigo === 401) { Cuenta.usuario = undefined; this.abrir(this.codigo); return; }
      poner($("#privado"), el("h1", {}, "Torneo no disponible"), el("p", {}, e.message),
        el("a", { class: "boton principal", href: "#/torneos" }, "Ir a tus torneos"));
      return;
    }
    // Mientras está vivo, se mira cada pocos segundos (inscripciones, resultados, cuadro); si
    // estoy esperando a que empiece mi partido, más a menudo, para entrar enseguida.
    if (ruta().nombre === "t" && ["inscripcion", "en_curso"].includes(this.v.estado)) {
      this.temporizador = setTimeout(() => this.refrescar(), this.esperando.size ? 1500 : 5000);
    }
  },

  async accion(metodo, ruta_, datos, confirmar) {
    if (confirmar && !confirm(confirmar)) return;
    try {
      this.pintar(await api(metodo, `/api/privados/${this.codigo}${ruta_}`, datos ?? {}));
    } catch (e) {
      this.aviso(e.message);
    }
  },

  aviso(texto) {
    const caja = $("#aviso-privado");
    if (!caja) return;
    caja.textContent = texto;
    caja.hidden = !texto;
    if (texto) caja.scrollIntoView({ block: "center", behavior: "smooth" });
  },

  nombre(id) {
    if (id === null || id === undefined) return null;
    const p = this.v.parejas.find((x) => x.id === id);
    return p ? p.nombre : "?";
  },

  pareja(id) { return this.v.parejas.find((x) => x.id === id); },

  pintar(v) {
    // El último en darle a "Empezar" arranca la partida: los que esperaban entran solos.
    for (const p of v.partidos) {
      if (p.mio && p.estado === "listo" && p.estoy_listo) this.esperando.add(p.id);
      else if (p.mio && p.estado === "jugando" && this.esperando.has(p.id) && ruta().nombre === "t") {
        this.esperando.clear();
        this.jugar(p);
        return;
      } else this.esperando.delete(p.id);
    }
    // Si nada ha cambiado no se rehace la página (no se pierde lo que se está escribiendo).
    const firma = JSON.stringify({ ...v, ahora: 0 });
    this.v = v;
    if (firma === this.firma) { this.pintarPlazo(); return; }
    const escribiendo = document.activeElement && document.activeElement.closest && document.activeElement.closest("#form-pareja");
    if (escribiendo && v.estado === "inscripcion" && this.firma) return;  // se repinta al salir
    this.firma = firma;
    const partes = [
      el("p", { class: "migas" }, el("a", { href: "#/torneos" }, "Torneos"), " / "),
      el("h1", {}, v.nombre),
      el("p", { class: "entradilla" },
        el("span", { class: `chip-estado ${v.estado}` }, ESTADOS[v.estado]), ` Organiza ${v.organizador}. `,
        v.estado === "inscripcion"
          ? `Formato con el torneo lleno (${v.formato.max_parejas} parejas): ${v.descripcion_lleno.replace(/^\d+ parejas: /, "")}`
          : v.estado !== "cancelado" ? v.descripcion : ""),
      el("p", { id: "aviso-privado", class: "error", hidden: true }),
    ];
    if (v.campeon !== null) partes.push(this.campeon());
    if (v.estado === "inscripcion") partes.push(this.invitacion(), this.inscripcion());
    if (v.estado === "en_curso" && v.yo.pareja !== null) partes.push(this.misPartidos());
    if (v.grupos && v.grupos.length) partes.push(this.grupos());
    if (v.liga) partes.push(this.liga());
    if (v.cuadro) partes.push(this.cuadro());
    if (v.estado !== "inscripcion") partes.push(this.estadisticas());
    partes.push(this.listaParejas());
    if (v.organizo && (v.estado === "inscripcion" || v.estado === "en_curso")) partes.push(this.organizador());
    poner($("#privado"), partes);
    this.pintarPlazo();
  },

  pintarPlazo() {
    const caja = $("#plazo");
    if (caja && this.v) caja.textContent = `La inscripción termina el ${fecha(this.v.fecha_limite)} (${falta(this.v.fecha_limite - this.v.ahora)}).`;
  },

  campeon() {
    const p = this.pareja(this.v.campeon);
    return el("div", { class: "tarjeta campeon" }, el("p", { class: "copa", "aria-hidden": "true" }, "🏆"),
      el("div", {}, el("h2", {}, `Campeones: ${p.nombre}`), el("p", {}, p.jugadores.join(" y "))));
  },

  invitacion() {
    const url = `${location.origin}${location.pathname}#/t/${this.v.codigo}`;
    const codigo = el("code", {}, url);
    let recien = false;
    try { recien = sessionStorage.getItem(`recien:${this.v.codigo}`) === "1"; } catch { /* sin almacenamiento */ }
    return el("div", { class: `tarjeta invitacion${recien ? " destacada" : ""}` },
      el("h2", {}, recien ? "¡Torneo creado! Invita a la gente" : "Enlace de invitación"),
      el("p", {}, "Pásalo a quien quieras invitar. Cada uno entra con su cuenta y una persona de cada pareja la inscribe con el nombre de usuario de su compañero."),
      codigo,
      el("div", { class: "fila" }, el("button", { class: "boton principal", type: "button", onclick: (e) => copiar(url, e.currentTarget, codigo) }, "Copiar enlace")),
      el("p", { id: "plazo", class: "pista" }));
  },

  inscripcion() {
    const v = this.v;
    const mia = v.yo.pareja !== null ? this.pareja(v.yo.pareja) : null;
    const invitaciones = v.parejas.filter((p) => p.invitado_yo);
    const caja = el("div", { class: "tarjeta" }, el("h2", {}, "Tu inscripción"));
    for (const p of invitaciones) {
      caja.append(el("div", { class: "invitacion-pareja" },
        el("p", {}, el("strong", {}, p.jugadores[0]), ` te invita a formar la pareja «${p.nombre}».`),
        el("div", { class: "fila" },
          el("button", { class: "boton principal", type: "button", onclick: () => this.accion("POST", `/parejas/${p.id}/aceptar`) }, "Aceptar"),
          el("button", { class: "boton", type: "button", onclick: () => this.accion("POST", `/parejas/${p.id}/retirar`, {}, "¿Rechazar la invitación?") }, "Rechazar"))));
    }
    if (mia && !mia.invitado_yo) {
      const companero = mia.jugadores.find((j) => j !== v.yo.nombre);
      caja.append(el("p", {}, mia.confirmada
        ? ["Estás inscrito con ", el("strong", {}, companero), ` como «${mia.nombre}». ¡A esperar al sorteo!`]
        : ["Has inscrito a «", mia.nombre, "». Falta que ", el("strong", {}, companero), " entre con su cuenta y acepte."]),
      el("button", { class: "boton", type: "button", onclick: () => this.accion("POST", `/parejas/${mia.id}/retirar`, {}, "¿Seguro que quieres retirar la pareja?") }, "Retirar la pareja"));
    } else if (!mia) {
      const completo = v.parejas.filter((p) => p.confirmada).length >= v.formato.max_parejas;
      if (completo) caja.append(el("p", {}, "El torneo está completo."));
      else caja.append(el("form", { id: "form-pareja", class: "form-pareja", onsubmit: (e) => this.inscribir(e) },
        el("label", {}, "Nombre de la pareja", el("input", { id: "pareja-nombre", maxlength: 30, required: true, placeholder: "Los del as de oros" })),
        el("label", {}, "Usuario de tu compañero", el("input", { id: "pareja-companero", maxlength: 20, required: true, autocomplete: "off", placeholder: "Su nombre de usuario" })),
        el("button", { class: "boton principal", type: "submit" }, "Inscribir pareja"),
        el("p", { class: "pista" }, "Tu compañero tiene que tener cuenta. Le llegará la invitación aquí mismo, al abrir el enlace del torneo.")));
    }
    return caja;
  },

  async inscribir(evento) {
    evento.preventDefault();
    const boton = $("button[type=submit]", evento.currentTarget);
    boton.disabled = true;
    try {
      const v = await api("POST", `/api/privados/${this.codigo}/parejas`, { nombre: $("#pareja-nombre").value.trim(), companero: $("#pareja-companero").value.trim() });
      document.activeElement.blur();
      this.firma = "";
      this.pintar(v);
    } catch (e) {
      this.aviso(e.message);
      boton.disabled = false;
    }
  },

  listaParejas() {
    const v = this.v;
    const confirmadas = v.parejas.filter((p) => p.confirmada).length;
    const filas = v.parejas.map((p) => el("tr", { class: p.id === v.yo.pareja ? "mia" : null },
      el("td", { class: "izq" }, p.nombre), el("td", { class: "izq" }, p.jugadores.join(" y ")),
      v.estado === "inscripcion" ? el("td", { class: "izq" }, p.confirmada ? "Inscrita" : "Falta que acepte el compañero") : null,
      v.organizo && v.estado === "inscripcion"
        ? el("td", {}, el("button", { class: "boton pequeno", type: "button", onclick: () => this.accion("POST", `/parejas/${p.id}/retirar`, {}, `¿Quitar a «${p.nombre}» del torneo?`) }, "Quitar"))
        : null));
    return el("div", { class: "tarjeta" },
      el("h2", {}, `Parejas (${confirmadas}${v.estado === "inscripcion" ? ` de ${v.formato.max_parejas}` : ""})`),
      v.parejas.length
        ? el("div", { class: "tabla" }, el("table", { class: "datos" }, el("tbody", {}, filas)))
        : el("p", {}, "Todavía no se ha inscrito ninguna pareja."));
  },

  organizador() {
    const v = this.v;
    const confirmadas = v.parejas.filter((p) => p.confirmada).length;
    const hijos = [el("h2", {}, "Organización")];
    const botones = [];
    if (v.estado === "inscripcion") {
      hijos.push(el("p", {}, "Al llegar la fecha límite se sortea solo con las parejas inscritas (hacen falta al menos 2). Si ya están todas, puedes sortear antes."),
        el("p", {}, confirmadas >= 2 ? `Si sorteas ahora, con ${confirmadas} parejas: ${v.descripcion.replace(/^\d+ parejas: /, "")}`
          : `Ahora hay ${confirmadas} pareja${confirmadas === 1 ? "" : "s"} inscrita${confirmadas === 1 ? "" : "s"}.`));
      botones.push(el("button", { class: "boton principal", type: "button", disabled: confirmadas < 2,
        onclick: () => this.accion("POST", "/empezar", {}, `¿Cerrar la inscripción y sortear con ${confirmadas} parejas?`) }, "Sortear y empezar ahora"));
    } else {
      hijos.push(el("p", {}, "Si una pareja no se presenta, pulsa «No se presentan» en su partido y dalo por ganado a la otra."));
    }
    botones.push(el("button", { class: "boton peligro", type: "button", onclick: () => this.accion("POST", "/cancelar", {}, "¿Cancelar el torneo? No se puede deshacer.") }, "Cancelar el torneo"));
    hijos.push(el("div", { class: "fila" }, botones));
    return el("div", { class: "tarjeta" }, hijos);
  },

  // Un partido: las dos parejas, el resultado y, si toca, el botón para jugar.
  partido(p, opciones = {}) {
    const v = this.v;
    const lado = (id, vacas) => {
      const gana = p.estado === "terminado" && p.ganador === id && id !== null;
      return el("div", { class: `lado${gana ? " gana" : ""}${id === null ? " vacio" : ""}${id !== null && id === v.yo.pareja ? " mio" : ""}` },
        el("span", {}, id === null ? (p.pase && p.estado === "terminado" ? "pase directo" : "por decidir") : this.nombre(id)),
        p.estado === "terminado" && !p.pase ? el("b", {}, vacas) : null);
    };
    const pie = [];
    if (p.estado === "terminado" && p.pase && p.a !== null && p.b !== null) pie.push(el("small", {}, "ganado sin jugar"));
    if (p.estado === "jugando") pie.push(el("small", { class: "en-juego" }, "jugándose ahora"));
    if (p.mio && p.estado === "listo") pie.push(...this.salaDeEspera(p));
    if (p.mio && p.estado === "jugando") pie.push(el("button", { class: "boton principal pequeno", type: "button", onclick: () => this.jugar(p) }, "Ir a la mesa"));
    if (v.organizo && v.estado === "en_curso" && (p.estado === "listo" || p.estado === "jugando") && !opciones.sinOrganizar) {
      pie.push(el("details", { class: "dar-ganador" }, el("summary", {}, "No se presentan"),
        [p.a, p.b].map((id) => el("button", { class: "boton pequeno", type: "button",
          onclick: () => this.accion("POST", `/partidos/${p.id}/ganador`, { pareja: id }, `¿Dar el partido por ganado a «${this.nombre(id)}»?`) }, `Gana ${this.nombre(id)}`))));
    }
    return el("div", { class: `partido${p.mio ? " mio" : ""}` }, lado(p.a, p.vacas[0]), lado(p.b, p.vacas[1]),
      pie.length ? el("div", { class: "pie-partido" }, pie) : null);
  },

  // Antes de jugar, cada uno de los cuatro le da a "Empezar"; la partida empieza con el último.
  salaDeEspera(p) {
    const faltan = p.faltan.length;
    const estado = el("span", { class: "sala" }, el("strong", {}, `${p.listos.length}/4 listos`),
      faltan ? ` · falta${faltan > 1 ? "n" : ""} ${p.faltan.join(", ")}` : "");
    if (p.estoy_listo) {
      return [el("span", { class: "listo-ok" }, "✓ Estás listo"), estado,
        el("button", { class: "boton pequeno", type: "button", onclick: () => this.accion("POST", `/partidos/${p.id}/listo`, { listo: false }) }, "Aún no")];
    }
    return [el("button", { class: "boton principal pequeno", type: "button", onclick: () => this.empezar(p) }, "Empezar"), estado];
  },

  async empezar(p) {
    this.esperando.add(p.id);
    await this.accion("POST", `/partidos/${p.id}/listo`, {});
    this.refrescar();  // vuelve a programar las consultas, ahora más seguidas
  },

  async jugar(p) {
    try {
      const d = await api("POST", `/api/privados/${this.codigo}/partidos/${p.id}/entrar`, {});
      try { sessionStorage.setItem(`volver:${d.mesa}`, `#/t/${this.codigo}`); } catch { /* sin almacenamiento */ }
      location.hash = `#/mesa/${d.mesa}/${d.token}`;
    } catch (e) {
      this.aviso(e.message);
    }
  },

  misPartidos() {
    const mios = this.v.partidos.filter((p) => p.mio && (p.estado === "listo" || p.estado === "jugando"));
    const eliminada = !mios.length && !this.v.partidos.some((p) => p.mio && p.estado === "esperando");
    const texto = eliminada ? "No te queda ningún partido: puedes seguir el torneo desde aquí."
      : "Ahora no tienes ningún partido pendiente: espera a que se decida tu rival.";
    return el("div", { class: `tarjeta${mios.length ? " destacada" : ""}` }, el("h2", {}, "Tus partidos"),
      mios.length ? [el("p", {}, "Cuando estéis los cuatro, cada uno le da a «Empezar» desde su dispositivo. La partida empieza cuando le da el último, y entráis todos solos a la mesa."),
        el("div", { class: "partidos-lista" }, mios.map((p) => this.partido(p, { sinOrganizar: true })))] : el("p", {}, texto));
  },

  tablaClasificacion(filas, pasan) {
    const signo = (x) => (x > 0 ? `+${x}` : `${x}`);
    return el("div", { class: "tabla" }, el("table", { class: "datos" },
      el("thead", {}, el("tr", {}, el("th", {}, "#"), el("th", { class: "izq" }, "Pareja"), el("th", {}, "J"), el("th", {}, "G"), el("th", {}, "P"),
        el("th", {}, "Vacas"), el("th", {}, "Tantos"))),
      el("tbody", {}, filas.map((f, i) => el("tr", { class: [i < pasan ? "pasa" : "", f.pareja === this.v.yo.pareja ? "mia" : ""].join(" ").trim() || null },
        el("td", {}, i + 1), el("td", { class: "izq" }, this.nombre(f.pareja)), el("td", {}, f.jugados), el("td", {}, f.ganados), el("td", {}, f.perdidos),
        el("td", {}, `${f.vacas[0]}-${f.vacas[1]}`), el("td", {}, signo(f.tantos[0] - f.tantos[1])))))));
  },

  grupos() {
    const v = this.v;
    return el("div", { class: "tarjeta" }, el("h2", {}, "Fase de grupos"),
      el("p", { class: "pista" }, `Pasan las ${v.grupos[0].pasan} primeras de cada grupo (en verde). Desempates: partidos ganados, diferencia de vacas y diferencia de tantos.`),
      el("div", { class: "grupos" }, v.grupos.map((g) => el("section", { class: "grupo" }, el("h3", {}, g.nombre),
        this.tablaClasificacion(g.tabla, g.pasan),
        el("div", { class: "partidos-lista" }, v.partidos.filter((p) => p.fase === "grupos" && p.grupo === g.numero).map((p) => this.partido(p)))))));
  },

  liga() {
    const v = this.v;
    return el("div", { class: "tarjeta" }, el("h2", {}, "Liga"), this.tablaClasificacion(v.liga, 1),
      el("div", { class: "partidos-lista" }, v.partidos.filter((p) => p.fase === "liga").map((p) => this.partido(p))));
  },

  cuadro() {
    const v = this.v;
    const porId = Object.fromEntries(v.partidos.map((p) => [p.id, p]));
    const tercero = v.cuadro.tercero !== null ? porId[v.cuadro.tercero] : null;
    return el("div", { class: "tarjeta" }, el("h2", {}, "Cuadro"),
      el("div", { class: "cuadro", role: "list" }, v.cuadro.rondas.map((r) => el("div", { class: "ronda", role: "listitem" },
        el("h3", {}, r.nombre), el("div", { class: "partidos-ronda" }, r.partidos.map((id) => this.partido(porId[id])))))),
      tercero ? el("div", { class: "tercero" }, el("h3", {}, "Tercer puesto"), this.partido(tercero)) : null);
  },

  estadisticas() {
    const v = this.v;
    const filas = [...v.estadisticas].sort((a, b) => b.ganados - a.ganados || (b.vacas[0] - b.vacas[1]) - (a.vacas[0] - a.vacas[1]));
    const pct = (a, b) => (b ? `${Math.round((100 * a) / b)} %` : "—");
    return el("div", { class: "tarjeta" }, el("h2", {}, "Estadísticas"),
      el("div", { class: "tabla" }, el("table", { class: "datos" },
        el("thead", {}, el("tr", {}, el("th", { class: "izq" }, "Pareja"), el("th", {}, "Jugados"), el("th", {}, "Ganados"), el("th", {}, "% victorias"),
          el("th", {}, "Vacas"), el("th", {}, "Tantos"), el("th", {}, "Manos ganadas"), el("th", {}, "Envites"), el("th", {}, "Órdagos (ganados)"))),
        el("tbody", {}, filas.map((e) => el("tr", { class: e.pareja === v.yo.pareja ? "mia" : null },
          el("td", { class: "izq" }, this.nombre(e.pareja)), el("td", {}, e.jugados), el("td", {}, e.ganados), el("td", {}, pct(e.ganados, e.jugados)),
          el("td", {}, `${e.vacas[0]}-${e.vacas[1]}`), el("td", {}, `${e.tantos[0]}-${e.tantos[1]}`), el("td", {}, e.manos), el("td", {}, e.envites),
          el("td", {}, `${e.ordagos} (${e.ordagos_ganados})`)))))),
      el("p", { class: "pista" }, "Los partidos ganados sin jugar cuentan en partidos y vacas, pero no en tantos, manos, envites ni órdagos."));
  },
};

// --- Clasificación y reglas -----------------------------------------------------------

const Clasificacion = {
  async abrir() {
    const caja = $("#clasificacion");
    try {
      pintarResultado(await api("GET", "/api/clasificacion"), caja);
    } catch (e) {
      caja.replaceChildren(el("p", {}, e.message));
    }
  },
};

const Reglas = {
  cargadas: false,
  async abrir() {
    if (this.cargadas) return;
    const caja = $("#reglas");
    try {
      const texto = await api("GET", "/api/reglas");
      if (window.marked) caja.innerHTML = window.marked.parse(texto);  // documento propio del servidor
      else caja.replaceChildren(el("pre", { style: "white-space:pre-wrap" }, texto));
      this.cargadas = true;
    } catch (e) {
      caja.replaceChildren(el("p", {}, e.message));
    }
  },
};

// --- Arranque -------------------------------------------------------------------------

$("#form-mesa").addEventListener("submit", (e) => Inicio.crear(e));
$("#form-chat").addEventListener("submit", (e) => Mesa.escribir(e));
$("#form-torneo").addEventListener("submit", (e) => Torneo.lanzar(e));
$("#form-entrar").addEventListener("submit", (e) => Cuenta.enviar(e, "/api/cuenta/entrar", "entrar"));
$("#form-registro").addEventListener("submit", (e) => Cuenta.enviar(e, "/api/cuenta/registro", "registro"));
$("#form-privado").addEventListener("submit", (e) => Privados.crear(e));
$("#form-privado").addEventListener("input", () => Privados.ajustarFormulario());
window.addEventListener("hashchange", mostrar);
Cuenta.cargar();
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#resumen-mano").hidden) $("#resumen-mano button").click();
});
mostrar();
