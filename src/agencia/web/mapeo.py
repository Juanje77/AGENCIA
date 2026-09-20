"""Traduccion entre el JSON de la interfaz y los objetos del dominio."""

from __future__ import annotations

from typing import Any

from ..dinero import dec
from ..liquidador import Mayorista, Operacion, Padron, Periodo
from ..presupuestos.cotizacion import (
    DESGLOSADO,
    PAQUETE,
    Cotizacion,
    DatosCotizacion,
    OpcionCotizada,
    PaqueteCotizado,
    ServicioCotizado,
)


class DatosInvalidos(ValueError):
    """Los datos recibidos no alcanzan para armar el objeto."""


def _texto(datos: dict, clave: str, default: str = "") -> str:
    valor = datos.get(clave)
    return str(valor).strip() if valor not in (None, "") else default


def cotizacion_desde_dict(datos: dict[str, Any]) -> Cotizacion:
    if not isinstance(datos, dict):
        raise DatosInvalidos("Se esperaba un objeto con los datos de la cotizacion.")

    general = datos.get("general") or datos
    try:
        pax = int(general.get("pax") or 1)
    except (TypeError, ValueError):
        raise DatosInvalidos("La cantidad de pasajeros tiene que ser un numero.") from None

    cotizacion = Cotizacion(
        datos=DatosCotizacion(
            cliente=_texto(general, "cliente"),
            contacto=_texto(general, "contacto"),
            destino=_texto(general, "destino"),
            fecha_viaje=_texto(general, "fecha_viaje"),
            pax=pax,
            vendedor=_texto(general, "vendedor"),
            fecha_cotizacion=_texto(general, "fecha_cotizacion")
            or DatosCotizacion().fecha_cotizacion,
            validez_dias=int(general.get("validez_dias") or 5),
            tipo_cambio=dec(general.get("tipo_cambio") or 0),
        )
    )
    if general.get("numero"):
        cotizacion.datos.numero = str(general["numero"])

    for indice, cruda in enumerate(datos.get("opciones") or [], start=1):
        cotizacion.opciones.append(_opcion(cruda, indice))
    return cotizacion


def _opcion(datos: dict[str, Any], indice: int) -> OpcionCotizada:
    if not isinstance(datos, dict):
        raise DatosInvalidos(f"La opcion {indice} no es un objeto.")

    modalidad = _texto(datos, "modalidad", DESGLOSADO).lower()
    if modalidad not in (DESGLOSADO, PAQUETE):
        raise DatosInvalidos(
            f"Modalidad invalida en la opcion {indice}: {modalidad!r}. "
            f"Tiene que ser {DESGLOSADO} o {PAQUETE}."
        )

    paquete_crudo = datos.get("paquete") or {}
    opcion = OpcionCotizada(
        nombre=_texto(datos, "nombre", f"Opcion {indice}"),
        nombre_cliente=_texto(datos, "nombre_cliente"),
        modalidad=modalidad,
        impuestos_pct=dec(datos.get("impuestos_pct") or 0),
        notas_cliente=_texto(datos, "notas_cliente"),
        paquete=PaqueteCotizado(
            mayorista=_texto(paquete_crudo, "mayorista"),
            descripcion=_texto(paquete_crudo, "descripcion"),
            tarifa=dec(paquete_crudo.get("tarifa") or 0),
            comisionable_pct=dec(paquete_crudo.get("comisionable_pct") or 0),
            impuestos=dec(paquete_crudo.get("impuestos") or 0),
            gastos_admin_pct=dec(paquete_crudo.get("gastos_admin_pct") or 0),
            tipo_fiscal=_texto(paquete_crudo, "tipo_fiscal", "PAQUETE_EXTERIOR"),
        ),
        servicios=[
            ServicioCotizado(
                tipo=_texto(s, "tipo", "Aereo"),
                mayorista=_texto(s, "mayorista"),
                descripcion=_texto(s, "descripcion"),
                tarifa=dec(s.get("tarifa") or 0),
                comision_pct=dec(s.get("comision_pct") or 0),
                gastos_admin_pct=dec(s.get("gastos_admin_pct") or 0),
                tipo_fiscal=s.get("tipo_fiscal") or None,
            )
            for s in (datos.get("servicios") or [])
            if isinstance(s, dict)
        ],
    )
    if datos.get("id"):
        opcion.id = str(datos["id"])

    override = datos.get("precio_por_pax_override")
    if override not in (None, ""):
        opcion.precio_por_pax_override = dec(override)
    return opcion


def periodo_desde_dict(datos: dict[str, Any]) -> Periodo:
    if not isinstance(datos, dict):
        raise DatosInvalidos("Se esperaba un objeto con los datos del periodo.")

    periodo = Periodo(
        periodo=_texto(datos, "periodo"),
        credito_fiscal_extra=dec(datos.get("credito_fiscal_extra") or 0),
        computa_credito_de_mayoristas=bool(datos.get("computa_credito_de_mayoristas")),
        alicuota_iibb=dec(datos.get("alicuota_iibb") or "3.5"),
        jurisdiccion=_texto(datos, "jurisdiccion", "La Pampa"),
        retenciones_iibb_sufridas=dec(datos.get("retenciones_iibb_sufridas") or 0),
    )
    for cruda in datos.get("operaciones") or []:
        periodo.operaciones.append(operacion_desde_dict(cruda))
    return periodo


def operacion_desde_dict(datos: dict[str, Any]) -> Operacion:
    if not isinstance(datos, dict):
        raise DatosInvalidos("Cada operacion tiene que ser un objeto.")
    return Operacion(
        id=_texto(datos, "id"),
        fecha=_texto(datos, "fecha"),
        cliente=_texto(datos, "cliente"),
        mayorista=_texto(datos, "mayorista"),
        referencia=_texto(datos, "referencia"),
        comprobante=_texto(datos, "comprobante"),
        origen=_texto(datos, "origen", "manual"),
        comisionable=dec(datos.get("comisionable") or 0),
        no_comisionable=dec(datos.get("no_comisionable") or 0),
        comision_pct=dec(datos.get("comision_pct") or 0),
        iva_pct=dec(datos.get("iva_pct") or 21),
        servicio_propio_pct=dec(datos.get("servicio_propio_pct") or 0),
        moneda=_texto(datos, "moneda", "ARS").upper(),
        tipo_cambio=dec(datos.get("tipo_cambio") or 0),
        credito_fiscal=dec(datos.get("credito_fiscal") or 0),
        avisos=list(datos.get("avisos") or []),
    )


def padron_desde_dict(datos: dict[str, Any]) -> Padron:
    padron = Padron()
    agencia = datos.get("agencia") or {}
    padron.agencia.razon_social = _texto(agencia, "razon_social")
    padron.agencia.cuit = _texto(agencia, "cuit")
    padron.agencia.condicion_iva = _texto(
        agencia, "condicion_iva", "RESPONSABLE_INSCRIPTO"
    )
    padron.agencia.jurisdiccion = _texto(agencia, "jurisdiccion", "LA_PAMPA")
    padron.agencia.alicuota_iibb = dec(agencia.get("alicuota_iibb") or "3.5")

    for crudo in datos.get("mayoristas") or []:
        nombre = _texto(crudo, "nombre")
        if not nombre:
            continue
        padron.mayoristas.append(
            Mayorista(
                nombre=nombre,
                comision_pct=dec(crudo.get("comision_pct") or 0),
                iva_pct=dec(crudo.get("iva_pct") or 21),
                cuit=_texto(crudo, "cuit"),
                alias=[str(a) for a in (crudo.get("alias") or []) if str(a).strip()],
            )
        )
    return padron
