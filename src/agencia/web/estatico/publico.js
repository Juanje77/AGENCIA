"use strict";

/* Sitio publico de Esplora. Sin dependencia del panel interno: no llama a
   la API del sistema, es una pagina estatica pensada para clientes. */

const $ = (sel) => document.querySelector(sel);

// --- año del pie de pagina ---------------------------------------------
const anio = $("#anio-actual");
if (anio) anio.textContent = new Date().getFullYear();

// --- encabezado solido al scrollear --------------------------------------
const encabezado = $("#encabezado");
function actualizarEncabezado() {
  if (!encabezado) return;
  encabezado.classList.toggle("con-fondo", window.scrollY > 60);
}
window.addEventListener("scroll", actualizarEncabezado, { passive: true });
actualizarEncabezado();

// --- menu movil -----------------------------------------------------------
const disparador = $("#disparador-menu");
const nav = $("#nav-principal");
if (disparador && nav) {
  disparador.addEventListener("click", () => {
    const abierto = nav.classList.toggle("abierto");
    disparador.setAttribute("aria-expanded", String(abierto));
  });
  nav.querySelectorAll("a").forEach((enlace) => {
    enlace.addEventListener("click", () => {
      nav.classList.remove("abierto");
      disparador.setAttribute("aria-expanded", "false");
    });
  });
}

// --- formulario de contacto -> mailto --------------------------------------
// Todavia no hay un servicio de envio de correo conectado: se arma un
// mailto: con lo que la persona cargo, para que lo mande desde su propio
// correo. El dia que haya un backend de mail, esto se reemplaza por un
// fetch a un endpoint propio sin tocar el resto del formulario.
const formulario = $("#formulario-contacto");
if (formulario) {
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    const datos = new FormData(formulario);
    const nombre = (datos.get("nombre") || "").toString().trim();
    const email = (datos.get("email") || "").toString().trim();
    const telefono = (datos.get("telefono") || "").toString().trim();
    const destino = (datos.get("destino") || "").toString().trim();
    const mensaje = (datos.get("mensaje") || "").toString().trim();

    // COMPLETAR: reemplazar por el email real de la agencia (el mismo que
    // figura en la seccion de contacto y en el pie de pagina).
    const destinatario = "hola@esplora.com.ar";

    const asunto = `Consulta de viaje${destino ? " · " + destino : ""}`;
    const cuerpo = [
      `Nombre: ${nombre}`,
      `Email: ${email}`,
      telefono ? `Teléfono: ${telefono}` : "",
      destino ? `Destino de interés: ${destino}` : "",
      "",
      mensaje || "(sin mensaje adicional)",
    ]
      .filter(Boolean)
      .join("\n");

    const enlace = `mailto:${destinatario}?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(cuerpo)}`;
    window.location.href = enlace;
  });
}
