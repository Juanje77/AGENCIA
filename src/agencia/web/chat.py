"""Chat con IA del sitio publico: preguntas generales sobre Esplora.

Usa el mismo modelo y la misma credencial que la lectura de facturas con IA
(ANTHROPIC_API_KEY, ver ../liquidaciones/lectura_ia.py), pero acotado por un
system prompt a hablar solo de lo que la agencia realmente ofrece: nunca
inventa precios, fechas ni disponibilidad. Si hace falta cotizar o reservar
de verdad, siempre deriva a WhatsApp.

Sin credencial configurada, no rompe: devuelve un aviso para que el frontend
caiga al boton de WhatsApp de siempre (mismo criterio que contacto.py y
dolar.py).
"""

from __future__ import annotations

import os

from .mapeo import DatosInvalidos

MODELO_DEFAULT = "claude-opus-5-5"
MAX_TOKENS_RESPUESTA = 500
MAX_TURNOS_HISTORIAL = 8  # ultimos N mensajes (usuario+bot) que se reenvian
MAX_LARGO_MENSAJE = 1000

SYSTEM_PROMPT = """Sos el asistente virtual del sitio publico de Esplora, una
agencia de viajes de Santa Rosa, La Pampa, Argentina.

Como responder:
- Respuestas cortas (2 a 4 oraciones), en espanol rioplatense, tono cercano
  y profesional. Nada de listas largas ni de markdown.
- Contestas preguntas generales sobre destinos, tipos de servicio y como
  trabaja la agencia.
- NUNCA inventes precios, fechas, disponibilidad, nombres de hoteles o
  vuelos que no esten en esta informacion. Si preguntan un precio exacto,
  disponibilidad real o quieren reservar, derivalos a WhatsApp.
- Si no sabes algo con certeza, decilo y derivá a WhatsApp en vez de
  arriesgar una respuesta.

Servicios que ofrece la agencia, cada uno con su pagina en /servicios/<id>:
aereos, hoteles, circuitos, assist-card, cruceros, actividades, autos,
traslados, disney, universal, enjoy. Ademas: paquetes a medida (/a-medida,
sin fecha fija) y salidas grupales (/salidas-grupales, fecha fija). Para
varios de estos productos trabajan con Ola, un mayorista de turismo.

Salidas grupales con fecha fija activas ahora mismo -precio y cupo cerrado,
se paga con tarjeta o Mercado Pago-:
- Cataratas del Iguazu: 8 al 11 de octubre, $320.000 por persona.
- El Calafate: 2 al 6 de noviembre, $520.000 por persona.
- Punta Cana, Rep. Dominicana (operado por Ola): 6 al 13 de enero, U$S 1.350
  por persona.
- Viña del Mar y Valparaiso (salida propia en micro): 4 al 10 de febrero,
  $380.000 por persona.
El itinerario completo de cada una esta en /salidas-grupales/<destino>
(bariloche, iguazu, mendoza, calafate, punta-cana, vina-del-mar).

Viajes a medida de ejemplo (sin fecha fija, cotizacion en 24 horas):
Cancun desde U$S 1.200 por persona, Rio de Janeiro desde U$S 850 por
persona -son referencias, el precio final se cotiza caso por caso.

Contacto: WhatsApp +54 9 2954 44-7929 (para cotizar, reservar o hablar con
una persona, pasales este numero), email hola@esplora.com.ar. La agencia
esta en Santa Rosa, La Pampa."""


def hay_chat() -> bool:
    """Si estan la libreria y la credencial para poder usar el modelo."""
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"))


def modelo_configurado() -> str:
    return os.environ.get("AGENCIA_MODELO_IA", MODELO_DEFAULT)


def consulta_desde_dict(datos: dict) -> tuple[str, list[dict]]:
    """Valida el cuerpo de /api/chat y arma los mensajes para el modelo."""
    if not isinstance(datos, dict):
        raise DatosInvalidos("Se esperaba un objeto con el mensaje.")

    mensaje = str(datos.get("mensaje") or "").strip()
    if not mensaje:
        raise DatosInvalidos("Falta el mensaje.")
    if len(mensaje) > MAX_LARGO_MENSAJE:
        raise DatosInvalidos(f"El mensaje no puede superar los {MAX_LARGO_MENSAJE} caracteres.")

    historial = datos.get("historial")
    if historial is None:
        historial = []
    if not isinstance(historial, list):
        raise DatosInvalidos("El historial tiene que ser una lista.")

    mensajes: list[dict] = []
    for turno in historial[-MAX_TURNOS_HISTORIAL:]:
        if not isinstance(turno, dict):
            continue
        rol = turno.get("rol")
        texto = str(turno.get("texto") or "").strip()[:MAX_LARGO_MENSAJE]
        if rol == "usuario" and texto:
            mensajes.append({"role": "user", "content": texto})
        elif rol == "bot" and texto:
            mensajes.append({"role": "assistant", "content": texto})

    mensajes.append({"role": "user", "content": mensaje})
    return mensaje, mensajes


def responder(mensajes: list[dict], cliente=None) -> dict:
    """Le pregunta al modelo y devuelve la respuesta.

    Sin credencial, o si el pedido falla por el motivo que sea, devuelve
    disponible=False en vez de romper: el frontend cae al boton de
    WhatsApp de siempre.

    `cliente` es para los tests: un objeto con `.messages.create(...)` que
    simula al SDK, sin depender de que este instalado ni de la credencial
    real (mismo patron que `leer_con_ia()` en lectura_ia.py).
    """
    if cliente is None:
        if not hay_chat():
            return {
                "disponible": False,
                "respuesta": None,
                "aviso": "El chat con IA no esta configurado todavia (falta ANTHROPIC_API_KEY).",
            }
        import anthropic

        cliente = anthropic.Anthropic()

    try:
        respuesta = cliente.messages.create(
            model=modelo_configurado(),
            max_tokens=MAX_TOKENS_RESPUESTA,
            system=SYSTEM_PROMPT,
            messages=mensajes,
            output_config={"effort": "low"},
        )
    except Exception as exc:  # noqa: BLE001 - se traduce a un aviso, nunca rompe la pagina
        return {"disponible": False, "respuesta": None, "aviso": _mensaje_de_error(exc)}

    if getattr(respuesta, "stop_reason", None) == "refusal":
        return {
            "disponible": True,
            "respuesta": "Prefiero no responder eso. ¿Te ayudo con algo sobre tu viaje?",
            "aviso": None,
        }

    texto = "".join(
        bloque.text for bloque in respuesta.content if getattr(bloque, "type", None) == "text"
    ).strip()
    if not texto:
        return {"disponible": False, "respuesta": None, "aviso": "El modelo no devolvio una respuesta."}

    return {"disponible": True, "respuesta": texto, "aviso": None}


def _mensaje_de_error(exc: Exception) -> str:
    nombre = type(exc).__name__
    if "Authentication" in nombre:
        return "La credencial del modelo no es valida."
    if "RateLimit" in nombre:
        return "El chat esta recibiendo muchas consultas. Probá de nuevo en un momento."
    if "Connection" in nombre or "Timeout" in nombre:
        return "No se pudo conectar con el modelo."
    return f"No se pudo responder ({nombre})."
