"""Cotizacion por opciones, como la arma la agencia en el mostrador.

Cada opcion es una alternativa que se le ofrece al pasajero y puede cargarse
de dos maneras:

  * desglosada: servicio por servicio (aereo, hotel, traslado, asistencia),
    cada uno con su comision y sus gastos administrativos;
  * en paquete: el mayorista pasa un precio cerrado con una parte comisionable.

Reglas de calculo, que son las que usa la agencia:
  * la comision ya viene adentro de la tarifa, asi que no se le suma al pasajero;
  * los gastos administrativos si se suman, y no son ganancia de la agencia;
  * los impuestos sobre la comision se trasladan al precio y salen de la ganancia.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from ..config import ParametrosFiscales, cargar_parametros
from ..dinero import CERO, dec, pct, redondear
from ..dominio import Moneda, RolAgencia
from ..impuestos import OperacionGravada, ResultadoFiscal, calcular_operacion, consolidar

DESGLOSADO = "desglosado"
PAQUETE = "paquete"

# Tipos que se ofrecen en el mostrador y su tratamiento fiscal por defecto.
TIPOS_SERVICIO = {
    "Aereo": "AEREO_INTERNACIONAL",
    "Aereo cabotaje": "AEREO_CABOTAJE",
    "Hotel": "HOTELERIA_EXTERIOR",
    "Hotel en el pais": "HOTELERIA_NACIONAL",
    "Traslado/Transfer": "EXCURSION_EXTERIOR",
    "Asistencia al viajero": "ASISTENCIA_VIAJERO",
    "Excursion": "EXCURSION_EXTERIOR",
    "Seguro": "SEGURO",
    "Crucero": "CRUCERO",
    "Alquiler de auto": "ALQUILER_AUTO_EXTERIOR",
    "Paquete": "PAQUETE_EXTERIOR",
    "Otro": "OTRO",
}


def _uid() -> str:
    return uuid.uuid4().hex[:8]


@dataclass
class ServicioCotizado:
    tipo: str = "Aereo"
    mayorista: str = ""
    tarifa: Decimal = CERO
    comision_pct: Decimal = CERO
    gastos_admin_pct: Decimal = CERO
    descripcion: str = ""
    tipo_fiscal: str | None = None
    id: str = field(default_factory=_uid)

    def __post_init__(self) -> None:
        self.tarifa = dec(self.tarifa)
        self.comision_pct = dec(self.comision_pct)
        self.gastos_admin_pct = dec(self.gastos_admin_pct)

    @property
    def servicio_fiscal(self) -> str:
        return self.tipo_fiscal or TIPOS_SERVICIO.get(self.tipo, "OTRO")

    @property
    def comision(self) -> Decimal:
        return pct(self.tarifa, self.comision_pct)

    @property
    def neto(self) -> Decimal:
        """Lo que queda para el proveedor una vez descontada la comision."""
        return redondear(self.tarifa - self.comision)

    @property
    def gastos_admin(self) -> Decimal:
        """Se calculan sobre el neto, no sobre la tarifa."""
        return pct(self.neto, self.gastos_admin_pct)

    @property
    def subtotal(self) -> Decimal:
        return redondear(self.tarifa + self.gastos_admin)


@dataclass
class PaqueteCotizado:
    mayorista: str = ""
    descripcion: str = ""
    tarifa: Decimal = CERO
    comisionable_pct: Decimal = CERO
    impuestos: Decimal = CERO
    gastos_admin_pct: Decimal = CERO
    tipo_fiscal: str = "PAQUETE_EXTERIOR"

    def __post_init__(self) -> None:
        for campo in ("tarifa", "comisionable_pct", "impuestos", "gastos_admin_pct"):
            setattr(self, campo, dec(getattr(self, campo)))

    @property
    def comision(self) -> Decimal:
        return pct(self.tarifa, self.comisionable_pct)

    @property
    def gastos_admin(self) -> Decimal:
        return pct(redondear(self.tarifa - self.comision), self.gastos_admin_pct)


@dataclass
class OpcionCotizada:
    nombre: str = "Opcion"
    nombre_cliente: str = ""
    modalidad: str = DESGLOSADO
    servicios: list[ServicioCotizado] = field(default_factory=list)
    impuestos_pct: Decimal = Decimal("21")
    paquete: PaqueteCotizado = field(default_factory=PaqueteCotizado)
    precio_por_pax_override: Decimal | None = None
    notas_cliente: str = ""
    id: str = field(default_factory=_uid)

    def __post_init__(self) -> None:
        self.impuestos_pct = dec(self.impuestos_pct)
        if self.precio_por_pax_override is not None:
            self.precio_por_pax_override = dec(self.precio_por_pax_override)

    @property
    def titulo_cliente(self) -> str:
        return self.nombre_cliente or self.nombre

    @property
    def mayoristas(self) -> list[str]:
        if self.modalidad == PAQUETE:
            return [self.paquete.mayorista] if self.paquete.mayorista else []
        vistos: list[str] = []
        for s in self.servicios:
            if s.mayorista and s.mayorista not in vistos:
                vistos.append(s.mayorista)
        return vistos


@dataclass
class DatosCotizacion:
    cliente: str = ""
    contacto: str = ""
    destino: str = ""
    fecha_viaje: str = ""
    pax: int = 2
    vendedor: str = ""
    fecha_cotizacion: str = field(default_factory=lambda: date.today().isoformat())
    validez_dias: int = 5
    moneda: Moneda = Moneda.USD
    tipo_cambio: Decimal = CERO
    """Cotizacion del dolar, solo para estimar los impuestos en pesos."""
    numero: str = field(default_factory=lambda: f"COT-{uuid.uuid4().hex[:6].upper()}")

    def __post_init__(self) -> None:
        self.pax = max(1, int(self.pax or 1))
        self.validez_dias = int(self.validez_dias or 0)
        self.tipo_cambio = dec(self.tipo_cambio)
        if isinstance(self.moneda, str):
            self.moneda = Moneda(self.moneda)

    @property
    def vence(self) -> str:
        try:
            base = date.fromisoformat(self.fecha_cotizacion)
        except ValueError:
            return ""
        return (base + timedelta(days=self.validez_dias)).isoformat()


@dataclass
class Cotizacion:
    datos: DatosCotizacion = field(default_factory=DatosCotizacion)
    opciones: list[OpcionCotizada] = field(default_factory=list)


# --- resultado ---------------------------------------------------------------


@dataclass
class OpcionCalculada:
    opcion: OpcionCotizada
    base: Decimal = CERO
    comision: Decimal = CERO
    gastos_admin: Decimal = CERO
    impuestos: Decimal = CERO
    extra: Decimal = CERO
    final: Decimal = CERO
    por_pax: Decimal = CERO
    ganancia: Decimal = CERO
    neto_operacion: Decimal = CERO
    fiscal: dict = field(default_factory=dict)
    resultados_fiscales: list[ResultadoFiscal] = field(default_factory=list)

    @property
    def margen_pct(self) -> Decimal:
        if self.final == CERO:
            return CERO
        return redondear(self.ganancia / self.final * 100)

    def a_dict(self) -> dict:
        opcion = self.opcion
        servicios = [
            {
                "tipo": s.tipo,
                "mayorista": s.mayorista,
                "descripcion": s.descripcion,
                "tarifa": str(s.tarifa),
                "comision_pct": str(s.comision_pct),
                "comision": str(s.comision),
                "gastos_admin_pct": str(s.gastos_admin_pct),
                "gastos_admin": str(s.gastos_admin),
                "neto": str(s.neto),
                "subtotal": str(s.subtotal),
                "tipo_fiscal": s.servicio_fiscal,
            }
            for s in opcion.servicios
        ]
        return {
            "id": opcion.id,
            "nombre": opcion.nombre,
            "nombre_cliente": opcion.titulo_cliente,
            "modalidad": opcion.modalidad,
            "mayoristas": opcion.mayoristas,
            "notas_cliente": opcion.notas_cliente,
            "servicios": servicios,
            "paquete": {
                "mayorista": opcion.paquete.mayorista,
                "descripcion": opcion.paquete.descripcion,
                "tarifa": str(opcion.paquete.tarifa),
                "comisionable_pct": str(opcion.paquete.comisionable_pct),
                "comision": str(opcion.paquete.comision),
                "impuestos": str(opcion.paquete.impuestos),
                "gastos_admin_pct": str(opcion.paquete.gastos_admin_pct),
                "gastos_admin": str(opcion.paquete.gastos_admin),
            },
            "base": str(self.base),
            "comision": str(self.comision),
            "gastos_admin": str(self.gastos_admin),
            "impuestos": str(self.impuestos),
            "extra": str(self.extra),
            "final": str(self.final),
            "por_pax": str(self.por_pax),
            "ganancia": str(self.ganancia),
            "margen_pct": str(self.margen_pct),
            "neto_operacion": str(self.neto_operacion),
            "fiscal": self.fiscal,
        }


@dataclass
class CotizacionCalculada:
    cotizacion: Cotizacion
    opciones: list[OpcionCalculada] = field(default_factory=list)
    avisos: list[str] = field(default_factory=list)

    @property
    def mas_barata(self) -> OpcionCalculada | None:
        candidatas = [o for o in self.opciones if o.final > CERO]
        return min(candidatas, key=lambda o: o.por_pax) if candidatas else None

    @property
    def mas_rentable(self) -> OpcionCalculada | None:
        return max(self.opciones, key=lambda o: o.ganancia) if self.opciones else None

    def a_dict(self) -> dict:
        d = self.cotizacion.datos
        return {
            "numero": d.numero,
            "cliente": d.cliente,
            "contacto": d.contacto,
            "destino": d.destino,
            "fecha_viaje": d.fecha_viaje,
            "pax": d.pax,
            "vendedor": d.vendedor,
            "fecha_cotizacion": d.fecha_cotizacion,
            "validez_dias": d.validez_dias,
            "vence": d.vence,
            "moneda": d.moneda.value,
            "tipo_cambio": str(d.tipo_cambio),
            "opciones": [o.a_dict() for o in self.opciones],
            "mas_barata": self.mas_barata.opcion.id if self.mas_barata else None,
            "mas_rentable": self.mas_rentable.opcion.id if self.mas_rentable else None,
            "avisos": self.avisos,
        }


# --- calculo -----------------------------------------------------------------


def calcular_cotizacion(
    cotizacion: Cotizacion, params: ParametrosFiscales | None = None
) -> CotizacionCalculada:
    params = params or cargar_parametros()
    resultado = CotizacionCalculada(cotizacion=cotizacion)

    for opcion in cotizacion.opciones:
        resultado.opciones.append(
            _calcular_opcion(opcion, cotizacion.datos, params)
        )

    if not cotizacion.opciones:
        resultado.avisos.append("La cotizacion no tiene opciones cargadas.")
    if cotizacion.datos.tipo_cambio <= CERO:
        resultado.avisos.append(
            "Sin cotizacion del dolar no se puede estimar el IVA e Ingresos Brutos "
            "en pesos. Cargala para ver la carga fiscal real de cada opcion."
        )
    resultado.avisos.extend(params.advertencias_de_configuracion())
    return resultado


def _calcular_opcion(
    opcion: OpcionCotizada, datos: DatosCotizacion, params: ParametrosFiscales
) -> OpcionCalculada:
    calculada = OpcionCalculada(opcion=opcion)
    pax = datos.pax

    if opcion.modalidad == PAQUETE:
        paquete = opcion.paquete
        calculada.base = paquete.tarifa
        calculada.comision = paquete.comision
        calculada.gastos_admin = paquete.gastos_admin
        calculada.impuestos = paquete.impuestos
        sin_extra = redondear(paquete.tarifa + paquete.impuestos + paquete.gastos_admin)
    else:
        calculada.base = redondear(sum((s.tarifa for s in opcion.servicios), CERO))
        calculada.comision = redondear(sum((s.comision for s in opcion.servicios), CERO))
        calculada.gastos_admin = redondear(
            sum((s.gastos_admin for s in opcion.servicios), CERO)
        )
        calculada.neto_operacion = redondear(
            sum((s.neto + s.gastos_admin for s in opcion.servicios), CERO)
        )
        # Los impuestos se trasladan al precio: salen de la comision y los gastos.
        calculada.impuestos = pct(
            redondear(calculada.comision + calculada.gastos_admin), opcion.impuestos_pct
        )
        # La comision ya esta dentro de la tarifa: no se suma de nuevo.
        sin_extra = redondear(
            calculada.base + calculada.gastos_admin + calculada.impuestos
        )

    if opcion.precio_por_pax_override is not None:
        calculada.final = redondear(opcion.precio_por_pax_override * pax)
        calculada.extra = redondear(calculada.final - sin_extra)
    else:
        calculada.final = sin_extra

    calculada.por_pax = redondear(calculada.final / pax)

    # Los gastos administrativos no son ganancia: se cobran y se gastan.
    if opcion.modalidad == PAQUETE:
        calculada.ganancia = redondear(calculada.comision + calculada.extra)
    else:
        calculada.ganancia = redondear(
            calculada.comision - calculada.impuestos + calculada.extra
        )

    calculada.fiscal, calculada.resultados_fiscales = _carga_fiscal(
        opcion, calculada, datos, params
    )
    return calculada


def _carga_fiscal(
    opcion: OpcionCotizada,
    calculada: OpcionCalculada,
    datos: DatosCotizacion,
    params: ParametrosFiscales,
) -> tuple[dict, list[ResultadoFiscal]]:
    """Calcula IVA e Ingresos Brutos reales segun el tratamiento de cada servicio.

    El porcentaje de impuestos que se carga al presupuesto es un estimado plano.
    Esto lo contrasta con el tratamiento que corresponde a cada tipo de servicio:
    la comision de un aereo internacional, por ejemplo, no lleva IVA.
    """
    factor = datos.tipo_cambio
    if factor <= CERO:
        return {"calculado": False, "motivo": "Falta la cotizacion del dolar."}, []

    operaciones: list[OperacionGravada] = []
    if opcion.modalidad == PAQUETE:
        paquete = opcion.paquete
        operaciones.append(
            OperacionGravada(
                tipo_servicio=paquete.tipo_fiscal,
                rol=RolAgencia.INTERMEDIARIO,
                costo_neto=redondear((paquete.tarifa - paquete.comision) * factor),
                comision=redondear(paquete.comision * factor),
                descripcion=paquete.descripcion or "Paquete",
            )
        )
    else:
        for servicio in opcion.servicios:
            if servicio.tarifa == CERO:
                continue
            operaciones.append(
                OperacionGravada(
                    tipo_servicio=servicio.servicio_fiscal,
                    rol=RolAgencia.INTERMEDIARIO,
                    costo_neto=redondear(servicio.neto * factor),
                    comision=redondear(servicio.comision * factor),
                    descripcion=servicio.descripcion or servicio.tipo,
                )
            )

    if calculada.extra > CERO:
        # El sobreprecio es retribucion propia de la agencia.
        operaciones.append(
            OperacionGravada(
                tipo_servicio="FEE_AGENCIA",
                rol=RolAgencia.INTERMEDIARIO,
                fee=redondear(calculada.extra * factor),
                descripcion="Diferencia por precio ajustado",
            )
        )

    resultados = [
        calcular_operacion(o, params, con_retenciones=False) for o in operaciones
    ]
    totales = consolidar(resultados)["totales"]

    iva = totales["debito_fiscal"]
    iibb = totales["iibb_total"]
    carga = redondear(iva + iibb)
    comision_pesos = redondear(calculada.comision * factor)
    extra_pesos = redondear(calculada.extra * factor)
    bruto = redondear(comision_pesos + extra_pesos)

    estimado = redondear(calculada.impuestos * factor)

    return (
        {
            "calculado": True,
            "tipo_cambio": str(factor),
            "comision_pesos": str(comision_pesos),
            "iva_debito": str(iva),
            "iibb": str(iibb),
            "carga_total": str(carga),
            "ganancia_neta_pesos": str(redondear(bruto - carga)),
            "impuestos_cargados_al_precio": str(estimado),
            "diferencia_contra_lo_cargado": str(redondear(estimado - carga)),
            "detalle": [
                {
                    "descripcion": r.operacion.descripcion,
                    "tipo_servicio": r.operacion.tipo_servicio,
                    "tratamiento": "+".join(
                        sorted({d.tratamiento.value for d in r.desglose_iva})
                    ),
                    "iva": str(r.debito_fiscal),
                    "iibb": str(r.iibb_total),
                }
                for r in resultados
            ],
        },
        resultados,
    )
