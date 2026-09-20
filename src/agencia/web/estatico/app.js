"use strict";

let PARAMS = null;
let OPCIONES = [];
let OPERACIONES = [];
let MAYORISTAS = [];
let ARCHIVOS = [];

const $ = (s) => document.querySelector(s);
const $$ = (s) => Array.from(document.querySelectorAll(s));
const uid = () => "id" + Math.random().toString(36).slice(2, 9);
const num = (v) => { const n = parseFloat(v); return isFinite(n) ? n : 0; };

const fmt = (v) =>
  num(v).toLocaleString("es-AR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const usd = (v) => "US$ " + fmt(v);
const ars = (v) => "$ " + fmt(v);

const esc = (t) =>
  String(t ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

async function api(ruta, datos, metodo = "POST") {
  const opciones = { method: metodo, headers: { "Content-Type": "application/json" } };
  if (datos !== undefined) opciones.body = JSON.stringify(datos);
  const r = await fetch(ruta, opciones);
  const tipo = r.headers.get("Content-Type") || "";
  if (!r.ok) {
    const detalle = tipo.includes("json") ? (await r.json()).error : await r.text();
    throw new Error(detalle || `Error ${r.status}`);
  }
  return tipo.includes("json") ? r.json() : r.text();
}

function error(contenedor, mensaje) {
  $(contenedor).innerHTML =
    `<div class="avisos error"><strong>No se pudo completar</strong><br>${esc(mensaje)}</div>`;
}

const tarjeta = (rotulo, valor, nota = "", clase = "") =>
  `<div class="tarjeta"><div class="rotulo">${esc(rotulo)}</div>
   <div class="valor ${clase}">${valor}</div>
   ${nota ? `<div class="nota">${esc(nota)}</div>` : ""}</div>`;

const bloqueAvisos = (avisos) =>
  avisos && avisos.length
    ? `<div class="avisos"><strong>Para revisar</strong><ul>${
        avisos.map((a) => `<li>${esc(a)}</li>`).join("")}</ul></div>`
    : "";

async function abrirHtml(ruta, datos) {
  try {
    const html = await api(ruta, datos);
    const v = window.open("", "_blank");
    if (!v) throw new Error("El navegador bloqueó la ventana emergente.");
    v.document.write(html);
    v.document.close();
  } catch (e) { alert(e.message); }
}

// ------------------------------------------------------------- navegación
$$("nav button").forEach((b) => {
  b.onclick = () => {
    $$("nav button").forEach((x) => x.classList.remove("activo"));
    $$(".vista").forEach((v) => v.classList.remove("activa"));
    b.classList.add("activo");
    $(`#vista-${b.dataset.vista}`).classList.add("activa");
  };
});

// ================================================================ COTIZADOR

function nuevoServicio() {
  return { id: uid(), tipo: "Aereo", mayorista: "", descripcion: "",
           tarifa: 0, comision_pct: 0, gastos_admin_pct: 1.5 };
}

function nuevaOpcion() {
  return {
    id: uid(),
    nombre: "Opción " + (OPCIONES.length + 1),
    nombre_cliente: "",
    modalidad: "desglosado",
    servicios: [nuevoServicio()],
    impuestos_pct: 21,
    paquete: { mayorista: "", descripcion: "", tarifa: 0,
               comisionable_pct: 14, impuestos: 0, gastos_admin_pct: 1.5 },
    precio_por_pax_override: "",
    notas_cliente: "",
  };
}

function listaMayoristas() {
  return MAYORISTAS.map((m) => `<option value="${esc(m.nombre)}">`).join("");
}

function pintarOpciones() {
  $("#opciones").innerHTML = OPCIONES.map((o, i) => `
    <div class="opcion-card" data-op="${i}">
      <div class="opcion-head">
        <input class="opcion-nombre" data-campo="nombre" value="${esc(o.nombre)}">
        <div class="opcion-acciones">
          <select data-campo="modalidad" style="width:auto">
            <option value="desglosado"${o.modalidad === "desglosado" ? " selected" : ""}>Desglosado</option>
            <option value="paquete"${o.modalidad === "paquete" ? " selected" : ""}>Paquete cerrado</option>
          </select>
          <button class="btn-ghost" data-accion="duplicar">Duplicar</button>
          <button class="btn-icon" data-accion="borrar">✕</button>
        </div>
      </div>
      ${o.modalidad === "paquete" ? pintarPaquete(o) : pintarServicios(o)}
      <div class="opcion-row">
        <label>Precio por pasajero (opcional)
          <input type="number" step="0.01" data-campo="precio_por_pax_override"
                 value="${o.precio_por_pax_override ?? ""}" placeholder="Dejar vacío para el calculado"></label>
        <label>Nota para el cliente
          <input data-campo="notas_cliente" value="${esc(o.notas_cliente)}"></label>
      </div>
    </div>`).join("");
  enlazarOpciones();
}

function pintarServicios(o) {
  const tipos = (PARAMS?.tipos_servicio || []).map((t) => t.nombre);
  const filas = o.servicios.map((s, j) => `
    <tr data-srv="${j}">
      <td><select data-campo="tipo">${tipos.map((t) =>
        `<option${t === s.tipo ? " selected" : ""}>${esc(t)}</option>`).join("")}</select></td>
      <td><input data-campo="mayorista" list="lista-mayoristas" value="${esc(s.mayorista)}"></td>
      <td><input data-campo="descripcion" value="${esc(s.descripcion)}" placeholder="Detalle"></td>
      <td><input type="number" step="0.01" data-campo="tarifa" value="${s.tarifa}"></td>
      <td><input type="number" step="0.01" data-campo="comision_pct" value="${s.comision_pct}"></td>
      <td><input type="number" step="0.01" data-campo="gastos_admin_pct" value="${s.gastos_admin_pct}"></td>
      <td><button class="btn-icon" data-accion="borrar-servicio">✕</button></td>
    </tr>`).join("");
  return `
    <div class="table-scroll" style="margin-bottom:12px">
      <table class="compacta"><thead><tr>
        <th style="width:15%">Tipo</th><th style="width:15%">Mayorista</th>
        <th style="width:26%">Descripción</th><th class="num" style="width:14%">Tarifa USD</th>
        <th class="num" style="width:11%">% com.</th><th class="num" style="width:12%">% gastos adm.</th><th></th>
      </tr></thead><tbody>${filas}</tbody></table>
    </div>
    <div class="opcion-row">
      <label>Impuestos sobre comisión y gastos %
        <input type="number" step="0.01" data-campo="impuestos_pct" value="${o.impuestos_pct}"></label>
      <div style="display:flex;align-items:flex-end">
        <button class="btn-ghost" data-accion="agregar-servicio">+ Servicio</button></div>
    </div>`;
}

function pintarPaquete(o) {
  const p = o.paquete;
  return `
    <div class="opcion-row">
      <label>Mayorista<input data-paquete="mayorista" list="lista-mayoristas" value="${esc(p.mayorista)}"></label>
      <label>Descripción<input data-paquete="descripcion" value="${esc(p.descripcion)}"
             placeholder="Aéreo + hotel + traslados"></label>
    </div>
    <div class="opcion-row">
      <label>Tarifa USD<input type="number" step="0.01" data-paquete="tarifa" value="${p.tarifa}"></label>
      <label>% comisionable<input type="number" step="0.01" data-paquete="comisionable_pct" value="${p.comisionable_pct}"></label>
    </div>
    <div class="opcion-row">
      <label>Impuestos USD<input type="number" step="0.01" data-paquete="impuestos" value="${p.impuestos}"></label>
      <label>% gastos administrativos<input type="number" step="0.01" data-paquete="gastos_admin_pct" value="${p.gastos_admin_pct}"></label>
    </div>`;
}

function enlazarOpciones() {
  $$("#opciones .opcion-card").forEach((card) => {
    const i = +card.dataset.op;
    card.querySelectorAll("[data-campo]").forEach((el) => {
      if (el.closest("[data-srv]")) return;
      el.oninput = () => {
        const campo = el.dataset.campo;
        OPCIONES[i][campo] = ["impuestos_pct"].includes(campo) ? num(el.value) : el.value;
        if (campo === "modalidad") pintarOpciones();
      };
    });
    card.querySelectorAll("[data-paquete]").forEach((el) => {
      el.oninput = () => {
        const campo = el.dataset.paquete;
        OPCIONES[i].paquete[campo] =
          ["mayorista", "descripcion"].includes(campo) ? el.value : num(el.value);
      };
    });
    card.querySelectorAll("[data-srv]").forEach((fila) => {
      const j = +fila.dataset.srv;
      fila.querySelectorAll("[data-campo]").forEach((el) => {
        el.oninput = () => {
          const campo = el.dataset.campo;
          OPCIONES[i].servicios[j][campo] =
            ["tipo", "mayorista", "descripcion"].includes(campo) ? el.value : num(el.value);
        };
      });
      const borrar = fila.querySelector("[data-accion=borrar-servicio]");
      if (borrar) borrar.onclick = () => {
        OPCIONES[i].servicios.splice(j, 1);
        if (!OPCIONES[i].servicios.length) OPCIONES[i].servicios.push(nuevoServicio());
        pintarOpciones();
      };
    });
    const acciones = {
      "agregar-servicio": () => { OPCIONES[i].servicios.push(nuevoServicio()); pintarOpciones(); },
      duplicar: () => {
        const copia = JSON.parse(JSON.stringify(OPCIONES[i]));
        copia.id = uid();
        copia.nombre += " (copia)";
        copia.servicios.forEach((s) => (s.id = uid()));
        OPCIONES.splice(i + 1, 0, copia);
        pintarOpciones();
      },
      borrar: () => { OPCIONES.splice(i, 1); pintarOpciones(); },
    };
    card.querySelectorAll("[data-accion]").forEach((b) => {
      const fn = acciones[b.dataset.accion];
      if (fn && !b.closest("[data-srv]")) b.onclick = fn;
    });
  });
}

function leerCotizacion() {
  return {
    general: {
      cliente: $("#g-cliente").value, contacto: $("#g-contacto").value,
      destino: $("#g-destino").value, fecha_viaje: $("#g-fechas").value,
      pax: num($("#g-pax").value) || 1, vendedor: $("#g-vendedor").value,
      fecha_cotizacion: $("#g-fecha").value, validez_dias: num($("#g-validez").value),
      tipo_cambio: num($("#g-tc").value),
    },
    opciones: OPCIONES.map((o) => ({
      ...o,
      precio_por_pax_override:
        o.precio_por_pax_override === "" || o.precio_por_pax_override === null
          ? null : num(o.precio_por_pax_override),
    })),
  };
}

function pintarCotizacion(d) {
  const filas = d.opciones.map((o) => {
    const marcas =
      (d.mas_barata === o.id ? ' <span class="tag tag-barata">mejor precio</span>' : "") +
      (d.mas_rentable === o.id ? ' <span class="tag tag-rentable">más rentable</span>' : "");
    const f = o.fiscal || {};
    return `<tr>
      <td>${esc(o.nombre)}${marcas}<span class="detalle">${esc(o.mayoristas.join(", ") || o.modalidad)}</span></td>
      <td class="num">${usd(o.base)}</td><td class="num">${usd(o.comision)}</td>
      <td class="num">${usd(o.gastos_admin)}</td><td class="num">${usd(o.impuestos)}</td>
      <td class="num">${usd(o.por_pax)}</td><td class="num">${usd(o.final)}</td>
      <td class="num" style="color:var(--ok);font-weight:600">${usd(o.ganancia)}</td>
      <td class="num">${f.calculado ? ars(f.carga_total) : "—"}</td></tr>`;
  }).join("");

  $("#resultado-cotizacion").innerHTML = `
    <section class="panel"><h2>Comparativo</h2>
      <div class="table-scroll"><table><thead><tr>
        <th>Opción</th><th class="num">Tarifa</th><th class="num">Comisión</th>
        <th class="num">Gastos adm.</th><th class="num">Impuestos</th>
        <th class="num">Por pax</th><th class="num">Total</th>
        <th class="num">Ganancia</th><th class="num">Carga fiscal real</th>
      </tr></thead><tbody>${filas}</tbody></table></div>
      <p class="hint">La carga fiscal real aplica el tratamiento que corresponde a cada
        tipo de servicio: la comisión de un aéreo internacional, por ejemplo, no lleva IVA.</p>
    </section>
    ${bloqueAvisos(d.avisos)}`;
}

$("#nueva-opcion").onclick = () => { OPCIONES.push(nuevaOpcion()); pintarOpciones(); };

$("#calcular-cotizacion").onclick = async () => {
  $("#resultado-cotizacion").innerHTML = '<p class="cargando">Calculando...</p>';
  try { pintarCotizacion(await api("/api/cotizacion", leerCotizacion())); }
  catch (e) { error("#resultado-cotizacion", e.message); }
};
$("#ver-cliente").onclick = () =>
  abrirHtml("/api/cotizacion/html", { ...leerCotizacion(), vista: "cliente" });
$("#ver-agencia").onclick = () =>
  abrirHtml("/api/cotizacion/html", { ...leerCotizacion(), vista: "agencia" });

// ============================================================== LIQUIDACIÓN

const zona = $("#zona");
zona.onclick = () => $("#archivos").click();
zona.ondragover = (e) => { e.preventDefault(); zona.classList.add("encima"); };
zona.ondragleave = () => zona.classList.remove("encima");
zona.ondrop = (e) => {
  e.preventDefault(); zona.classList.remove("encima");
  sumarArchivos(e.dataTransfer.files);
};
$("#archivos").onchange = (e) => sumarArchivos(e.target.files);

function sumarArchivos(lista) {
  Array.from(lista).forEach((f) => ARCHIVOS.push(f));
  $("#lista-archivos").innerHTML = ARCHIVOS.map((f, i) =>
    `<div class="archivo-item"><span>${esc(f.name)}</span>
     <span class="estado">${(f.size / 1024).toFixed(0)} KB
     <button class="btn-icon" data-quitar="${i}">✕</button></span></div>`).join("");
  $$("#lista-archivos [data-quitar]").forEach((b) => {
    b.onclick = () => { ARCHIVOS.splice(+b.dataset.quitar, 1); sumarArchivos([]); };
  });
  $("#procesar").disabled = ARCHIVOS.length === 0;
}

const leerBase64 = (archivo) =>
  new Promise((ok, mal) => {
    const lector = new FileReader();
    lector.onload = () => ok(lector.result.split(",")[1]);
    lector.onerror = () => mal(new Error("No se pudo leer " + archivo.name));
    lector.readAsDataURL(archivo);
  });

$("#procesar").onclick = async () => {
  const boton = $("#procesar");
  boton.disabled = true;
  boton.textContent = "Leyendo...";
  try {
    const archivos = await Promise.all(
      ARCHIVOS.map(async (f) => ({ nombre: f.name, contenido: await leerBase64(f) })));
    const r = await api("/api/facturas", {
      archivos, cuit_agencia: $("#a-cuit").value, servicio_propio_pct: 0,
    });
    r.operaciones.forEach((o) => OPERACIONES.push({ ...o, id: o.id || uid() }));
    ARCHIVOS = [];
    $("#lista-archivos").innerHTML = "";
    if (r.errores.length) {
      $("#avisos-operaciones").innerHTML =
        `<div class="avisos error"><strong>Archivos que no se pudieron leer</strong><ul>${
          r.errores.map((e) => `<li><strong>${esc(e.archivo)}</strong>: ${esc(e.error)}</li>`)
          .join("")}</ul></div>`;
    }
    await recalcular();
  } catch (e) {
    $("#avisos-operaciones").innerHTML =
      `<div class="avisos error">${esc(e.message)}</div>`;
  } finally {
    boton.disabled = ARCHIVOS.length === 0;
    boton.textContent = "Leer facturas";
  }
};

$("#agregar-fila").onclick = async () => {
  OPERACIONES.push({
    id: uid(), fecha: "", cliente: "", mayorista: MAYORISTAS[0]?.nombre || "",
    comisionable: 0, no_comisionable: 0,
    comision_pct: MAYORISTAS[0]?.comision_pct || 0, iva_pct: 21,
    servicio_propio_pct: 0, moneda: "ARS", tipo_cambio: 0, credito_fiscal: 0,
    referencia: "", comprobante: "", origen: "manual", avisos: [],
  });
  await recalcular();
};

$("#limpiar").onclick = async () => {
  if (OPERACIONES.length && !confirm("¿Vaciar todas las operaciones del período?")) return;
  OPERACIONES = [];
  $("#avisos-operaciones").innerHTML = "";
  await recalcular();
};

function leerPeriodo() {
  return {
    periodo: $("#l-periodo").value,
    operaciones: OPERACIONES,
    credito_fiscal_extra: num($("#credito-extra").value),
    computa_credito_de_mayoristas: $("#computa-credito").checked,
    alicuota_iibb: num($("#iibb-alicuota").value),
    jurisdiccion: $("#iibb-jurisdiccion").value,
    retenciones_iibb_sufridas: num($("#iibb-retenciones").value),
  };
}

async function recalcular() {
  try {
    pintarPeriodo(await api("/api/periodo", leerPeriodo()));
  } catch (e) {
    $("#avisos-operaciones").innerHTML = `<div class="avisos error">${esc(e.message)}</div>`;
  }
}

function pintarPeriodo(d) {
  const opciones = MAYORISTAS.map((m) => `<option value="${esc(m.nombre)}">`).join("");
  $("#operaciones").innerHTML = d.operaciones.map((o, i) => {
    const sinTc = o.moneda !== "ARS" && num(o.tipo_cambio) <= 0;
    return `<tr data-op="${i}"${sinTc ? ' style="background:var(--gold-soft)"' : ""}>
      <td><input type="date" data-c="fecha" value="${esc(o.fecha_iso || "")}" style="width:130px"></td>
      <td><input data-c="cliente" value="${esc(o.cliente)}" style="min-width:130px">
          ${o.comprobante ? `<span class="detalle">${esc(o.comprobante)}</span>` : ""}</td>
      <td><input data-c="mayorista" list="lista-mayoristas" value="${esc(o.mayorista)}" style="min-width:95px"></td>
      <td><select data-c="moneda" style="width:70px">
        ${["ARS", "USD", "EUR"].map((m) => `<option${m === o.moneda ? " selected" : ""}>${m}</option>`).join("")}
      </select></td>
      <td><input type="number" step="0.01" data-c="tipo_cambio" value="${o.tipo_cambio}" style="width:85px"></td>
      <td><input type="number" step="0.01" data-c="comisionable" value="${o.comisionable}" style="width:110px"></td>
      <td><input type="number" step="0.01" data-c="no_comisionable" value="${o.no_comisionable}" style="width:100px"></td>
      <td class="num calc">${fmt(o.total_viaje)}</td>
      <td><input type="number" step="0.01" data-c="comision_pct" value="${o.comision_pct}" style="width:70px"></td>
      <td class="num calc">${fmt(o.comision_ganada)}</td>
      <td class="num calc">${fmt(o.gravado)}</td>
      <td class="num calc">${fmt(o.iva_comision)}</td>
      <td><input type="number" step="0.01" data-c="servicio_propio_pct" value="${o.servicio_propio_pct}" style="width:70px"></td>
      <td class="num calc">${fmt(o.servicio_propio)}</td>
      <td class="num calc">${fmt(o.iva_servicio)}</td>
      <td><button class="btn-icon" data-borrar="${i}">✕</button></td></tr>`;
  }).join("") || '<tr><td colspan="16" class="vacio">Subí las facturas o cargá una operación a mano.</td></tr>';

  const t = d.totales;
  $("#totales-operaciones").innerHTML = d.operaciones.length ? `
    <td colspan="5">Totales en pesos</td>
    <td class="num">${fmt(t.comisionable)}</td><td class="num">${fmt(t.no_comisionable)}</td>
    <td class="num">${fmt(t.total_viaje)}</td><td></td>
    <td class="num">${fmt(t.comision_ganada)}</td><td class="num">${fmt(t.gravado)}</td>
    <td class="num">${fmt(t.iva_comision)}</td><td></td>
    <td class="num">${fmt(t.servicio_propio)}</td><td class="num">${fmt(t.iva_servicio)}</td><td></td>` : "";

  $$("#operaciones [data-op]").forEach((fila) => {
    const i = +fila.dataset.op;
    fila.querySelectorAll("[data-c]").forEach((el) => {
      el.onchange = async () => {
        const campo = el.dataset.c;
        OPERACIONES[i][campo] =
          ["fecha", "cliente", "mayorista", "moneda"].includes(campo) ? el.value : num(el.value);
        if (campo === "mayorista") {
          const m = MAYORISTAS.find((x) => x.nombre === el.value);
          if (m) {
            OPERACIONES[i].comision_pct = num(m.comision_pct);
            OPERACIONES[i].iva_pct = num(m.iva_pct);
          }
        }
        await recalcular();
      };
    });
    const b = fila.querySelector("[data-borrar]");
    if (b) b.onclick = async () => { OPERACIONES.splice(i, 1); await recalcular(); };
  });

  $("#iva-debito").value = ars(d.iva.debito_fiscal);
  $("#iibb-base").value = ars(d.iibb.base);

  const resultado = num(d.iva.resultado);
  const caja = $("#resultado-iva");
  caja.className = "resultado " + (resultado >= 0 ? "pagar" : "favor");
  caja.querySelector(".rotulo").textContent =
    resultado >= 0 ? "IVA a pagar" : "Saldo técnico a favor";
  caja.querySelector(".monto").textContent = ars(Math.abs(resultado));
  $("#resultado-iibb").querySelector(".monto").textContent = ars(d.iibb.a_pagar);

  $("#tarjetas-liquidacion").innerHTML =
    tarjeta("Operaciones", d.totales.operaciones) +
    tarjeta("Comisión ganada", ars(d.totales.comision_ganada)) +
    tarjeta("Carga impositiva", ars(d.resumen.carga_total), "IVA + Ingresos Brutos") +
    tarjeta("Ganancia neta", ars(d.resumen.ganancia_neta), "después de IIBB", "ok");

  const avisosFilas = d.operaciones.flatMap((o) =>
    (o.avisos || []).map((a) => `${o.comprobante || o.mayorista}: ${a}`));
  const previo = $("#avisos-operaciones").querySelector(".avisos.error")?.outerHTML || "";
  $("#avisos-operaciones").innerHTML = previo + bloqueAvisos([...d.avisos, ...avisosFilas]);
}

["credito-extra", "iibb-alicuota", "iibb-retenciones", "iibb-jurisdiccion", "l-periodo"]
  .forEach((id) => { $("#" + id).onchange = recalcular; });
$("#computa-credito").onchange = recalcular;
$("#ver-liquidacion").onclick = () => abrirHtml("/api/periodo/html", leerPeriodo());

// =============================================================== MAYORISTAS

function pintarMayoristas() {
  $("#tabla-mayoristas").innerHTML = MAYORISTAS.map((m, i) => `
    <tr data-m="${i}">
      <td><input data-c="nombre" value="${esc(m.nombre)}"></td>
      <td><input type="number" step="0.01" data-c="comision_pct" value="${m.comision_pct}" style="width:90px"></td>
      <td><input type="number" step="0.01" data-c="iva_pct" value="${m.iva_pct}" style="width:80px"></td>
      <td><input data-c="cuit" value="${esc(m.cuit)}" placeholder="30-12345678-9"></td>
      <td><input data-c="alias" value="${esc((m.alias || []).join(", "))}"
                 placeholder="Como figura en la factura"></td>
      <td><button class="btn-icon" data-borrar="${i}">✕</button></td></tr>`).join("");

  $$("#tabla-mayoristas [data-m]").forEach((fila) => {
    const i = +fila.dataset.m;
    fila.querySelectorAll("[data-c]").forEach((el) => {
      el.oninput = () => {
        const campo = el.dataset.c;
        if (campo === "alias") {
          MAYORISTAS[i].alias = el.value.split(",").map((s) => s.trim()).filter(Boolean);
        } else {
          MAYORISTAS[i][campo] = el.value;
        }
      };
    });
    fila.querySelector("[data-borrar]").onclick = () => {
      MAYORISTAS.splice(i, 1); pintarMayoristas();
    };
  });
  const lista = $("#lista-mayoristas");
  if (lista) lista.innerHTML = listaMayoristas();
}

$("#nuevo-mayorista").onclick = () => {
  MAYORISTAS.push({ nombre: "Nuevo mayorista", comision_pct: "3.00", iva_pct: "21.00", cuit: "", alias: [] });
  pintarMayoristas();
};

$("#guardar-mayoristas").onclick = async () => {
  const estado = $("#estado-mayoristas");
  estado.textContent = "Guardando...";
  try {
    const d = await api("/api/mayoristas", {
      agencia: {
        razon_social: $("#a-razon").value, cuit: $("#a-cuit").value,
        jurisdiccion: $("#a-jurisdiccion").value,
        alicuota_iibb: num($("#a-alicuota").value),
      },
      mayoristas: MAYORISTAS,
    });
    MAYORISTAS = d.mayoristas;
    pintarMayoristas();
    estado.textContent = "Guardado.";
    setTimeout(() => (estado.textContent = ""), 2500);
  } catch (e) { estado.textContent = "No se pudo guardar: " + e.message; }
};

// ================================================================== ARRANQUE

async function iniciar() {
  try {
    PARAMS = await api("/api/parametros", undefined, "GET");
  } catch (e) {
    document.body.insertAdjacentHTML("afterbegin",
      `<div class="avisos error">No se pudieron cargar los parámetros: ${esc(e.message)}</div>`);
    return;
  }

  MAYORISTAS = PARAMS.mayoristas || [];
  const a = PARAMS.agencia || {};
  $("#a-razon").value = a.razon_social || "";
  $("#a-cuit").value = a.cuit || "";
  $("#a-jurisdiccion").value = a.jurisdiccion || "LA_PAMPA";
  $("#a-alicuota").value = a.alicuota_iibb || "3.5";
  $("#iibb-alicuota").value = a.alicuota_iibb || "3.5";
  $("#g-fecha").value = new Date().toISOString().slice(0, 10);

  const hoy = new Date();
  $("#l-periodo").value =
    String(hoy.getMonth() + 1).padStart(2, "0") + "/" + hoy.getFullYear();

  document.body.insertAdjacentHTML("beforeend",
    `<datalist id="lista-mayoristas">${listaMayoristas()}</datalist>`);

  $("#tabla-fiscal").innerHTML = `<div class="table-scroll"><table><thead><tr>
    <th>Tipo en el cotizador</th><th>Tratamiento fiscal</th></tr></thead><tbody>
    ${(PARAMS.tipos_servicio || []).map((t) => {
      const f = (PARAMS.servicios_fiscales || []).find((s) => s.codigo === t.fiscal);
      return `<tr><td>${esc(t.nombre)}</td><td>${esc(f ? f.etiqueta : t.fiscal)}
        ${f && f.nota ? `<span class="detalle">${esc(f.nota)}</span>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div>
    ${bloqueAvisos(PARAMS.advertencias)}
    <div class="avisos">${esc(PARAMS.aviso || "")}</div>`;

  OPCIONES = [nuevaOpcion()];
  pintarOpciones();
  pintarMayoristas();
  await recalcular();
}

iniciar();
