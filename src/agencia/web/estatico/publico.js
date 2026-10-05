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
  // Escape cierra el menu y devuelve el foco al disparador.
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape" || !nav.classList.contains("abierto")) return;
    nav.classList.remove("abierto");
    disparador.setAttribute("aria-expanded", "false");
    disparador.focus();
  });
  nav.querySelectorAll("a").forEach((enlace) => {
    enlace.addEventListener("click", () => {
      nav.classList.remove("abierto");
      disparador.setAttribute("aria-expanded", "false");
    });
  });
}

// --- formulario de contacto -------------------------------------------------
// Se manda al backend (/api/contacto), que lo envia por correo a la agencia.
// Si todavia no hay SMTP configurado en el servidor, o la peticion falla por
// conexion, se cae al mailto: de siempre para no perder la consulta.
const formulario = $("#formulario-contacto");
if (formulario) {
  const nota = formulario.querySelector(".form-nota");
  const boton = formulario.querySelector("button[type=submit]");

  function mailtoDeRespaldo({ nombre, email, telefono, destino, mensaje }) {
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
    window.location.href = `mailto:${destinatario}?subject=${encodeURIComponent(asunto)}&body=${encodeURIComponent(cuerpo)}`;
  }

  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const datos = new FormData(formulario);
    const consulta = {
      nombre: (datos.get("nombre") || "").toString().trim(),
      email: (datos.get("email") || "").toString().trim(),
      telefono: (datos.get("telefono") || "").toString().trim(),
      destino: (datos.get("destino") || "").toString().trim(),
      mensaje: (datos.get("mensaje") || "").toString().trim(),
    };

    if (boton) boton.disabled = true;
    if (nota) nota.textContent = "Enviando tu consulta...";

    let enviado = false;
    try {
      const respuesta = await fetch("/api/contacto", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(consulta),
      });
      const resultado = await respuesta.json();
      enviado = respuesta.ok && resultado.enviado === true;
    } catch (error) {
      enviado = false;
    }

    if (enviado) {
      formulario.reset();
      if (nota) nota.textContent = "¡Gracias! Te vamos a contactar a la brevedad.";
      return;
    }

    mailtoDeRespaldo(consulta);
    if (boton) boton.disabled = false;
    if (nota) nota.textContent = "Se abrió tu programa de correo con la consulta ya redactada.";
  });
}
