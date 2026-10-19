/* Mus Arena en el navegador.
 *
 * Todo lo que llega del servidor se pinta con textContent (nunca como HTML), así que nadie
 * puede colar código en la página de otro jugador a través del chat o de un nombre.
 * El código secreto de cada asiento va detrás del "#" del enlace (#/mesa/<id>/<código>):
 * esa parte nunca se manda a ningún servidor; aquí se envía en la cabecera X-Token.
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
  const opciones = { method: metodo, headers: {} };
  if (datos !== undefined) {
    opciones.headers["Content-Type"] = "application/json";
    opciones.body = JSON.stringify(datos);
  }
  if (token) opciones.headers["X-Token"] = token;
  const respuesta = await fetch(ruta, opciones);
  const tipo = respuesta.headers.get("Content-Type") || "";
  const cuerpo = tipo.includes("application/json") ? await respuesta.json() : await respuesta.text();
  if (!respuesta.ok) {
    const error = new Error(explicarError(cuerpo, respuesta.status));
    error.codigo = respuesta.status;
    throw error;
  }
  return cuerpo;
}

function explicarError(cuerpo, codigo) {
  if (cuerpo && typeof cuerpo === "object") {
    if (typeof cuerpo.detalle === "string") return cuerpo.detalle;
    if (Array.isArray(cuerpo.detail)) return "Datos no válidos";
  }
  return codigo >= 500 ? "Error del servidor; inténtalo otra vez" : `Error ${codigo}`;
}

const NOMBRE_JUGADOR = (a) => `Jugador ${a + 1}`;
const PAREJA = (p) => (p === 0 ? "A" : "B");
const LANCES = { grande: "Grande", chica: "Chica", pares: "Pares", juego: "Juego", punto: "Punto" };
// A 8 reyes, el 3 vale como un rey y el 2 como un as: se avisa en la propia carta.
const FIGURAS = { 10: "Sota", 11: "Caballo", 12: "Rey", 3: "vale rey", 2: "vale as" };

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
    FIGURAS[c.numero] ? el("span", { class: "nombre-figura" }, FIGURAS[c.numero]) : null,
    el("span", { class: "num abajo" }, c.numero));
  return nodo;
}

// replaceChildren escribiría "null" como texto: se quitan antes los huecos vacíos.
const poner = (caja, ...hijos) => caja.replaceChildren(...hijos.flat().filter((h) => h !== null && h !== undefined && h !== false));

const reverso = (pequena) => el("div", { class: `carta reverso${pequena ? " pequena" : ""}`, "aria-hidden": "true" });

// --- Navegación -----------------------------------------------------------------------

const VISTAS = ["inicio", "mesa", "torneo", "clasificacion", "reglas"];

function ruta() {
  const partes = location.hash.replace(/^#\/?/, "").split("/").filter(Boolean);
  return { nombre: partes[0] || "inicio", partes: partes.slice(1) };
}

function mostrar() {
  const { nombre, partes } = ruta();
  const vista = VISTAS.includes(nombre) ? nombre : "inicio";
  for (const v of VISTAS) $(`#vista-${v}`).hidden = v !== vista;
  for (const a of document.querySelectorAll(".barra nav a")) {
    a.classList.toggle("activa", a.dataset.ruta === (vista === "mesa" ? "inicio" : vista));
  }
  if (vista !== "mesa") Mesa.parar();
  if (vista === "inicio") Inicio.abrir();
  if (vista === "mesa") Mesa.abrir(partes[0], partes[1]);
  if (vista === "torneo") Torneo.abrir();
  if (vista === "clasificacion") Clasificacion.abrir();
  if (vista === "reglas") Reglas.abrir();
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
    }
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
        asientos, mejor_de: Number($("#mejor-de").value), velocidad: $("#velocidad").value });
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
          el("strong", {}, `${NOMBRE_JUGADOR(a.asiento)} (pareja ${PAREJA(a.asiento % 2)})`), codigo,
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
    const base = NOMBRE_JUGADOR(asiento);
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
    $("#centro").replaceChildren(el("p", { class: "lance" }, "Mesa no disponible"), el("p", {}, texto),
      el("a", { class: "boton principal", href: "#/" }, "Crear otra mesa"));
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
      hijos.push(el("p", { class: "lance" }, ganamos ? "¡Habéis ganado!" : "Han ganado los rivales"),
        el("p", {}, `Vacas: ${v.vacas[v.pareja]} a ${v.vacas[1 - v.pareja]}`),
        el("a", { class: "boton principal", href: "#/" }, "Jugar otra partida"));
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
      : el("li", {}, el("b", {}, `${NOMBRE_JUGADOR(e.asiento)}: `), e.texto)));
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
      el("th", {}, "Victorias"), el("th", {}, "Partidas"), el("th", {}, "% (± 95 %)"))),
    el("tbody", {}, r.clasificacion.map((f) => el("tr", { class: f.puesto === 1 ? "primero" : null },
      el("td", {}, f.puesto), el("td", { class: "izq" }, f.nombre), el("td", {}, Math.round(f.elo)),
      el("td", {}, f.victorias), el("td", {}, f.partidas), el("td", {}, `${pct(f.porcentaje)} ± ${pct(f.margen_95)}`)))));
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
    el("div", { class: "tabla" }, cruces));
}

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
window.addEventListener("hashchange", mostrar);
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !$("#resumen-mano").hidden) $("#resumen-mano button").click();
});
mostrar();
