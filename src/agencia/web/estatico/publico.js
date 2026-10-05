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

// --- modo claro / oscuro ---------------------------------------------------
// El <head> de cada pagina ya aplico el tema guardado (si habia uno) antes
// del primer render, para evitar el parpadeo. Aca solo faltan el click del
// boton y guardar la eleccion.
const CLAVE_TEMA = "esplora-tema";
const disparadorTema = $("#disparador-tema");

function aplicarTema(tema) {
  document.documentElement.setAttribute("data-theme", tema);
  if (disparadorTema) {
    const esClaro = tema === "light";
    const etiqueta = esClaro ? "Cambiar a modo oscuro" : "Cambiar a modo claro";
    disparadorTema.setAttribute("aria-label", etiqueta);
    disparadorTema.title = etiqueta;
  }
}

if (disparadorTema) {
  aplicarTema(document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark");
  disparadorTema.addEventListener("click", () => {
    const actual = document.documentElement.getAttribute("data-theme") === "light" ? "light" : "dark";
    const siguiente = actual === "light" ? "dark" : "light";
    aplicarTema(siguiente);
    try {
      localStorage.setItem(CLAVE_TEMA, siguiente);
    } catch (error) {
      // Sin acceso a localStorage (navegacion privada, etc.): el cambio
      // sigue andando, solo que no se recuerda en la proxima visita.
    }
  });
}

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

// --- cotizacion del dolar ---------------------------------------------------
// Pide /api/dolar (cacheado 5 min del lado del servidor) y completa la
// franja del header. Si no esta disponible -sin red, API caida- la franja
// se queda oculta en vez de mostrar guiones sueltos.
const franjaDolar = $("#franja-dolar");
if (franjaDolar) {
  const formatoPeso = new Intl.NumberFormat("es-AR", { maximumFractionDigits: 0 });
  fetch("/api/dolar")
    .then((respuesta) => respuesta.json())
    .then((datos) => {
      if (!datos.disponible) return;
      let completo = true;
      franjaDolar.querySelectorAll("[data-dolar]").forEach((item) => {
        const cotizacion = datos.cotizaciones[item.dataset.dolar];
        const valor = item.querySelector(".franja-dolar-valor");
        if (cotizacion && cotizacion.venta && valor) {
          valor.textContent = "$" + formatoPeso.format(cotizacion.venta);
        } else {
          completo = false;
        }
      });
      if (completo) franjaDolar.hidden = false;
    })
    .catch(() => {
      // Sin red o API caida: la franja se queda oculta, no rompe la pagina.
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
