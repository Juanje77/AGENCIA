"""Envio del formulario de contacto del sitio publico por correo.

El servidor no tiene disco persistente en Vercel, asi que la consulta no se
guarda: se manda por correo a la agencia ahi mismo, usando SMTP configurado
por variables de entorno (ver README). Si todavia no estan cargadas, se
avisa en la respuesta en vez de fallar, para que el frontend pueda caer de
nuevo al mailto: que ya tenia.
"""

from __future__ import annotations

import os
import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from .mapeo import DatosInvalidos

_EMAIL_VALIDO = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DESTINATARIO_POR_DEFECTO = "hola@esplora.com.ar"

# Mismos limites que los maxlength de estatico/contacto.html.
_LIMITES = {"nombre": 100, "email": 254, "telefono": 40, "destino": 120, "mensaje": 1000}


@dataclass
class ConsultaContacto:
    nombre: str
    email: str
    telefono: str = ""
    destino: str = ""
    mensaje: str = ""


def consulta_desde_dict(datos: dict) -> ConsultaContacto:
    if not isinstance(datos, dict):
        raise DatosInvalidos("Se esperaba un objeto con los datos de la consulta.")

    nombre = str(datos.get("nombre") or "").strip()
    email = str(datos.get("email") or "").strip()
    if not nombre:
        raise DatosInvalidos("Falta el nombre.")
    if not email or not _EMAIL_VALIDO.match(email):
        raise DatosInvalidos("El email no es valido.")

    consulta = ConsultaContacto(
        nombre=nombre,
        email=email,
        telefono=str(datos.get("telefono") or "").strip(),
        destino=str(datos.get("destino") or "").strip(),
        mensaje=str(datos.get("mensaje") or "").strip(),
    )
    for campo, maximo in _LIMITES.items():
        if len(getattr(consulta, campo)) > maximo:
            raise DatosInvalidos(f"El campo {campo} supera los {maximo} caracteres.")
    return consulta


def _config_smtp() -> dict | None:
    host = os.environ.get("SMTP_HOST", "").strip()
    if not host:
        return None
    return {
        "host": host,
        "puerto": int(os.environ.get("SMTP_PUERTO", "587")),
        "usuario": os.environ.get("SMTP_USUARIO", "").strip(),
        "clave": os.environ.get("SMTP_CLAVE", "").strip(),
        "destino": os.environ.get("CONTACTO_EMAIL", "").strip() or DESTINATARIO_POR_DEFECTO,
    }


def hay_envio_de_correo() -> bool:
    return _config_smtp() is not None


def _mensaje_de(consulta: ConsultaContacto, config: dict) -> EmailMessage:
    mensaje = EmailMessage()
    mensaje["Subject"] = (
        f"Consulta de viaje · {consulta.destino}" if consulta.destino else "Consulta de viaje"
    )
    mensaje["From"] = config["usuario"] or config["destino"]
    mensaje["To"] = config["destino"]
    mensaje["Reply-To"] = consulta.email

    cuerpo = [f"Nombre: {consulta.nombre}", f"Email: {consulta.email}"]
    if consulta.telefono:
        cuerpo.append(f"Telefono: {consulta.telefono}")
    if consulta.destino:
        cuerpo.append(f"Destino de interes: {consulta.destino}")
    cuerpo.append("")
    cuerpo.append(consulta.mensaje or "(sin mensaje adicional)")
    mensaje.set_content("\n".join(cuerpo))
    return mensaje


def enviar_consulta(consulta: ConsultaContacto) -> dict:
    """Manda la consulta por correo. Si no hay SMTP configurado, no la manda."""
    config = _config_smtp()
    if config is None:
        return {
            "enviado": False,
            "aviso": "El envio de correo no esta configurado todavia (falta SMTP_HOST).",
        }

    mensaje = _mensaje_de(consulta, config)
    with smtplib.SMTP(config["host"], config["puerto"], timeout=10) as servidor:
        servidor.starttls()
        if config["usuario"]:
            servidor.login(config["usuario"], config["clave"])
        servidor.send_message(mensaje)

    return {"enviado": True, "aviso": None}
