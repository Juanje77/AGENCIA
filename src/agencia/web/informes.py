"""Informes imprimibles: la cotizacion para el pasajero y para la agencia,
y la liquidacion de IVA e Ingresos Brutos del periodo."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from ..dinero import CERO, dec, redondear
from ..liquidador import Periodo
from ..presupuestos.cotizacion import PAQUETE, CotizacionCalculada, OpcionCalculada

_CSS = """
:root{--bg:#EEF1EC;--paper:#fff;--paper-alt:#FCFBF8;--ink:#1F2D2B;--ink-soft:#5B6B64;
--primary:#2B5E55;--primary-dark:#173C35;--primary-soft:#E2EDE9;--accent:#B5482A;
--gold:#A98A3D;--gold-soft:#FBF0DC;--border:#D7DED7;--border-soft:#E6EAE4;--danger:#A6392D;
--danger-soft:#F8E7E2;--font-display:'Fraunces',Georgia,serif;
--font-body:'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
--font-mono:'IBM Plex Mono',ui-monospace,monospace}
*{box-sizing:border-box}
body{margin:0;padding:30px 18px 60px;background:var(--bg);color:var(--ink);
font-family:var(--font-body);font-size:14px;line-height:1.45;-webkit-print-color-adjust:exact}
.hoja{max-width:900px;margin:0 auto;background:var(--paper);border:1px solid var(--border);
border-radius:6px;padding:38px 40px}
header{display:flex;justify-content:space-between;align-items:flex-start;gap:22px;
border-bottom:2px solid var(--primary-dark);padding-bottom:16px;margin-bottom:22px;flex-wrap:wrap}
h1{font-family:var(--font-display);font-weight:600;font-size:25px;margin:0;color:var(--primary-dark)}
h2{font-family:var(--font-display);font-weight:600;font-size:16px;margin:26px 0 11px;
color:var(--primary-dark)}
.meta{text-align:right;font-size:12.5px;color:var(--ink-soft)}
.meta strong{color:var(--ink);font-size:14px;display:block}
.datos{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:11px 20px;
font-size:13.5px;margin-bottom:6px}
.datos div span{display:block;color:var(--ink-soft);font-size:11px;text-transform:uppercase;
letter-spacing:.045em;font-weight:600}
table{width:100%;border-collapse:collapse;font-size:13px;margin-bottom:8px}
th{text-align:left;font-size:10.5px;text-transform:uppercase;letter-spacing:.045em;
color:var(--ink-soft);border-bottom:1px solid var(--border);padding:8px 9px;font-weight:600}
td{padding:8px 9px;border-bottom:1px solid var(--border-soft);vertical-align:top}
td.num,th.num{text-align:right;font-family:var(--font-mono);font-variant-numeric:tabular-nums;
white-space:nowrap}
tr.total td{font-weight:700;border-top:2px solid var(--primary-dark);border-bottom:none;font-size:15px}
.detalle{display:block;color:var(--ink-soft);font-size:11.5px;margin-top:2px}
.opcion{border:1px solid var(--border);border-radius:6px;padding:17px 19px;
margin-bottom:16px;background:var(--paper-alt)}
.opcion h3{font-family:var(--font-display);font-size:17px;margin:0 0 4px;color:var(--primary-dark)}
.precio{display:flex;justify-content:space-between;align-items:baseline;gap:12px;
margin-top:12px;padding-top:11px;border-top:1px solid var(--border)}
.precio .etiqueta{font-size:11.5px;text-transform:uppercase;letter-spacing:.045em;
color:var(--ink-soft);font-weight:600}
.precio .monto{font-family:var(--font-mono);font-size:22px;font-weight:700;color:var(--primary-dark)}
.tag{display:inline-block;border-radius:999px;padding:2px 10px;font-size:10.5px;
font-weight:700;text-transform:uppercase;letter-spacing:.04em}
.tag-barata{background:var(--primary-soft);color:var(--primary)}
.tag-rentable{background:var(--gold-soft);color:var(--gold)}
.resultado{border-radius:6px;padding:13px 16px;display:flex;justify-content:space-between;
align-items:center;margin:8px 0}
.resultado .monto{font-family:var(--font-mono);font-size:21px;font-weight:700}
.pagar{background:var(--danger-soft);color:var(--danger)}
.favor{background:var(--primary-soft);color:var(--primary)}
.avisos{border-left:3px solid var(--gold);background:var(--gold-soft);padding:11px 15px;
border-radius:0 5px 5px 0;font-size:12.5px;margin:15px 0}
.avisos ul{margin:5px 0 0;padding-left:17px}
.pie{margin-top:26px;padding-top:15px;border-top:1px solid var(--border);
font-size:11.5px;color:var(--ink-soft);line-height:1.6}
@media print{body{background:#fff;padding:0}.hoja{border:none;padding:14px}}
"""

_FUENTES = (
    "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?"
    "family=Fraunces:opsz,wght@9..144,500;9..144,600&family=Inter:wght@400;500;600;700&"
    "family=IBM+Plex+Mono:wght@400;500;600&display=swap'>"
)


def _documento(titulo: str, cuerpo: str) -> str:
    return (
        f"<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(titulo)}</title>{_FUENTES}<style>{_CSS}</style></head>"
        f"<body><div class='hoja'>{cuerpo}</div></body></html>"
    )


def _usd(valor) -> str:
    return "US$ " + _miles(dec(valor))


def _ars(valor) -> str:
    return "$ " + _miles(dec(valor))


def _miles(valor: Decimal) -> str:
    valor = redondear(valor)
    negativo = valor < CERO
    entero, _, decimales = f"{abs(valor):.2f}".partition(".")
    grupos = []
    while len(entero) > 3:
        grupos.insert(0, entero[-3:])
        entero = entero[:-3]
    grupos.insert(0, entero)
    texto = f"{'.'.join(grupos)},{decimales}"
    return f"-{texto}" if negativo else texto


# --- cotizacion --------------------------------------------------------------


def _encabezado_cotizacion(calculada: CotizacionCalculada, subtitulo: str) -> str:
    d = calculada.cotizacion.datos
    return f"""<header><div>
      <h1>{escape(d.destino or 'Propuesta de viaje')}</h1>
      <div style="color:#5B6B64;font-size:13.5px">{escape(subtitulo)}</div>
      </div><div class="meta">
      <strong>{escape(d.numero)}</strong>
      {escape(d.fecha_cotizacion)}<br>
      {f'Valida hasta {escape(d.vence)}' if d.vence else ''}
      {f'<br>{escape(d.vendedor)}' if d.vendedor else ''}
      </div></header>"""


def _datos_viaje(calculada: CotizacionCalculada) -> str:
    d = calculada.cotizacion.datos
    campos = [("Pasajeros", str(d.pax))]
    if d.cliente:
        campos.insert(0, ("Cliente", d.cliente))
    if d.fecha_viaje:
        campos.append(("Fechas", d.fecha_viaje))
    if d.contacto:
        campos.append(("Contacto", d.contacto))
    return (
        "<div class='datos'>"
        + "".join(f"<div><span>{escape(k)}</span>{escape(v)}</div>" for k, v in campos)
        + "</div>"
    )


def informe_cotizacion_cliente(calculada: CotizacionCalculada) -> str:
    """Lo que ve el pasajero: opciones y precios, sin comisiones ni margenes."""
    partes = [
        _encabezado_cotizacion(calculada, "Opciones para tu viaje"),
        _datos_viaje(calculada),
    ]
    barata = calculada.mas_barata

    for opcion in calculada.opciones:
        o = opcion.opcion
        marca = (
            " <span class='tag tag-barata'>mejor precio</span>"
            if barata and barata.opcion.id == o.id and len(calculada.opciones) > 1
            else ""
        )
        filas = ""
        if o.modalidad == PAQUETE:
            if o.paquete.descripcion:
                filas = f"<tr><td>{escape(o.paquete.descripcion)}</td></tr>"
        else:
            filas = "".join(
                f"<tr><td>{escape(s.descripcion or s.tipo)}"
                f"{f'<span class=detalle>{escape(s.mayorista)}</span>' if s.mayorista else ''}"
                f"</td></tr>"
                for s in o.servicios
                if s.tarifa > CERO
            )
        incluye = (
            f"<table><thead><tr><th>Incluye</th></tr></thead><tbody>{filas}</tbody></table>"
            if filas
            else ""
        )
        notas = (
            f"<div class='detalle' style='margin-top:8px'>{escape(o.notas_cliente)}</div>"
            if o.notas_cliente
            else ""
        )
        partes.append(
            f"""<div class="opcion"><h3>{escape(o.titulo_cliente)}{marca}</h3>
            {incluye}{notas}
            <div class="precio"><span class="etiqueta">Precio por pasajero</span>
            <span class="monto">{_usd(opcion.por_pax)}</span></div>
            <div class="precio" style="border:none;padding-top:4px">
            <span class="etiqueta">Total {calculada.cotizacion.datos.pax} pasajero(s)</span>
            <span style="font-family:var(--font-mono);font-weight:600">
            {_usd(opcion.final)}</span></div></div>"""
        )

    partes.append(
        "<div class='pie'>Valores expresados en dolares estadounidenses, sujetos a "
        "disponibilidad y a confirmacion del operador. Las tarifas pueden variar hasta "
        "la emision de los servicios.</div>"
    )
    return _documento(
        f"Cotizacion {calculada.cotizacion.datos.numero}", "".join(partes)
    )


def informe_cotizacion_agencia(calculada: CotizacionCalculada) -> str:
    """Lo que ve la agencia: comisiones, impuestos y ganancia por opcion."""
    partes = [
        _encabezado_cotizacion(calculada, "Analisis interno de la cotizacion"),
        _datos_viaje(calculada),
        "<h2>Comparativo de opciones</h2>",
        _tabla_comparativa(calculada),
    ]

    for opcion in calculada.opciones:
        partes.append(_detalle_opcion(opcion, calculada))

    if calculada.avisos:
        avisos = "".join(f"<li>{escape(a)}</li>" for a in calculada.avisos)
        partes.append(f"<div class='avisos'><strong>Para revisar</strong><ul>{avisos}</ul></div>")

    return _documento(
        f"Analisis {calculada.cotizacion.datos.numero}", "".join(partes)
    )


def _tabla_comparativa(calculada: CotizacionCalculada) -> str:
    barata = calculada.mas_barata
    rentable = calculada.mas_rentable
    filas = []
    for opcion in calculada.opciones:
        marcas = ""
        if barata and barata.opcion.id == opcion.opcion.id:
            marcas += " <span class='tag tag-barata'>mejor precio</span>"
        if rentable and rentable.opcion.id == opcion.opcion.id:
            marcas += " <span class='tag tag-rentable'>mas rentable</span>"
        filas.append(
            f"<tr><td>{escape(opcion.opcion.nombre)}{marcas}"
            f"<span class='detalle'>{escape(', '.join(opcion.opcion.mayoristas) or opcion.opcion.modalidad)}</span></td>"
            f"<td class='num'>{_usd(opcion.base)}</td>"
            f"<td class='num'>{_usd(opcion.comision)}</td>"
            f"<td class='num'>{_usd(opcion.gastos_admin)}</td>"
            f"<td class='num'>{_usd(opcion.impuestos)}</td>"
            f"<td class='num'>{_usd(opcion.por_pax)}</td>"
            f"<td class='num'>{_usd(opcion.final)}</td>"
            f"<td class='num' style='color:#2B5E55;font-weight:600'>{_usd(opcion.ganancia)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Opcion</th><th class='num'>Tarifa</th>"
        "<th class='num'>Comision</th><th class='num'>Gastos adm.</th>"
        "<th class='num'>Impuestos</th><th class='num'>Por pax</th>"
        "<th class='num'>Total</th><th class='num'>Ganancia</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table>"
    )


def _detalle_opcion(opcion: OpcionCalculada, calculada: CotizacionCalculada) -> str:
    o = opcion.opcion
    if o.modalidad == PAQUETE:
        p = o.paquete
        filas = (
            f"<tr><td>{escape(p.descripcion or 'Paquete')}"
            f"<span class='detalle'>{escape(p.mayorista)}</span></td>"
            f"<td class='num'>{_usd(p.tarifa)}</td>"
            f"<td class='num'>{p.comisionable_pct}%</td>"
            f"<td class='num'>{_usd(p.comision)}</td>"
            f"<td class='num'>{_usd(p.gastos_admin)}</td></tr>"
        )
    else:
        filas = "".join(
            f"<tr><td>{escape(s.descripcion or s.tipo)}"
            f"<span class='detalle'>{escape(s.mayorista)}</span></td>"
            f"<td class='num'>{_usd(s.tarifa)}</td>"
            f"<td class='num'>{s.comision_pct}%</td>"
            f"<td class='num'>{_usd(s.comision)}</td>"
            f"<td class='num'>{_usd(s.gastos_admin)}</td></tr>"
            for s in o.servicios
            if s.tarifa > CERO
        )

    fiscal = opcion.fiscal
    bloque_fiscal = ""
    if fiscal.get("calculado"):
        bloque_fiscal = f"""<div class="datos" style="margin-top:12px">
          <div><span>IVA debito (segun servicio)</span>{_ars(fiscal['iva_debito'])}</div>
          <div><span>Ingresos Brutos</span>{_ars(fiscal['iibb'])}</div>
          <div><span>Carga fiscal total</span>{_ars(fiscal['carga_total'])}</div>
          <div><span>Cargado al precio</span>{_ars(fiscal['impuestos_cargados_al_precio'])}</div>
          <div><span>Diferencia</span>{_ars(fiscal['diferencia_contra_lo_cargado'])}</div>
          <div><span>Ganancia neta</span>{_ars(fiscal['ganancia_neta_pesos'])}</div>
        </div>"""
    else:
        bloque_fiscal = (
            f"<div class='detalle' style='margin-top:10px'>"
            f"{escape(str(fiscal.get('motivo', '')))}</div>"
        )

    return f"""<h2>{escape(o.nombre)}</h2>
      <table><thead><tr><th>Servicio</th><th class='num'>Tarifa</th>
      <th class='num'>Com.</th><th class='num'>Comision</th>
      <th class='num'>Gastos adm.</th></tr></thead><tbody>{filas}
      <tr class='total'><td>Total</td><td class='num'>{_usd(opcion.base)}</td>
      <td class='num'></td><td class='num'>{_usd(opcion.comision)}</td>
      <td class='num'>{_usd(opcion.gastos_admin)}</td></tr></tbody></table>
      {bloque_fiscal}"""


# --- liquidacion del periodo -------------------------------------------------


def informe_periodo(periodo: Periodo) -> str:
    datos = periodo.a_dict()
    iva, iibb = datos["iva"], datos["iibb"]
    resultado = dec(iva["resultado"])

    filas = "".join(
        f"<tr><td>{escape(o['fecha'])}</td>"
        f"<td>{escape(o['cliente'] or '-')}"
        f"<span class='detalle'>{escape(o['comprobante'])}</span></td>"
        f"<td>{escape(o['mayorista'])}</td>"
        f"<td class='num'>{o['moneda']}</td>"
        f"<td class='num'>{_miles(dec(o['comisionable']))}</td>"
        f"<td class='num'>{_miles(dec(o['no_comisionable']))}</td>"
        f"<td class='num'>{o['comision_pct']}%</td>"
        f"<td class='num'>{_miles(dec(o['comision_ganada']))}</td>"
        f"<td class='num'>{_miles(dec(o['gravado']))}</td>"
        f"<td class='num'>{_miles(dec(o['iva_comision']))}</td>"
        f"<td class='num'>{_miles(dec(o['servicio_propio']))}</td>"
        f"<td class='num'>{_miles(dec(o['iva_servicio']))}</td></tr>"
        for o in datos["operaciones"]
    )
    totales = datos["totales"]

    clase_iva = "pagar" if resultado >= CERO else "favor"
    rotulo_iva = "IVA a pagar" if resultado >= CERO else "Saldo tecnico a favor"

    avisos = ""
    if datos["avisos"]:
        items = "".join(f"<li>{escape(a)}</li>" for a in datos["avisos"])
        avisos = f"<div class='avisos'><strong>Para revisar</strong><ul>{items}</ul></div>"

    return _documento(
        f"Liquidacion {datos['periodo']}",
        f"""<header><div><h1>Liquidacion de IVA e Ingresos Brutos</h1>
        <div style="color:#5B6B64;font-size:13.5px">Periodo {escape(datos['periodo'] or 'sin especificar')}
        · {escape(datos['jurisdiccion'])}</div></div>
        <div class="meta"><strong>{totales['operaciones']} operaciones</strong>
        Comision ganada {_ars(totales['comision_ganada'])}</div></header>

        <h2>Operaciones del periodo</h2>
        <table><thead><tr><th>Fecha</th><th>Cliente</th><th>Mayorista</th>
        <th class='num'>Mon.</th><th class='num'>Comisionable</th><th class='num'>No comis.</th>
        <th class='num'>% com.</th><th class='num'>Comision</th><th class='num'>Gravado</th>
        <th class='num'>IVA com.</th><th class='num'>Serv. propio</th>
        <th class='num'>IVA serv.</th></tr></thead><tbody>{filas}</tbody></table>

        <h2>Liquidacion de IVA</h2>
        <table><tbody>
        <tr><td>Debito fiscal <span class="detalle">IVA sobre comision y servicio propio</span></td>
        <td class="num">{_ars(iva['debito_fiscal'])}</td></tr>
        <tr><td>Credito fiscal <span class="detalle">IVA de compras y gastos del periodo</span></td>
        <td class="num">-{_ars(iva['credito_fiscal'])}</td></tr>
        </tbody></table>
        <div class="resultado {clase_iva}"><span>{rotulo_iva}</span>
        <span class="monto">{_ars(abs(resultado))}</span></div>

        <h2>Liquidacion de Ingresos Brutos</h2>
        <table><tbody>
        <tr><td>Base imponible <span class="detalle">Comision neta mas servicio propio</span></td>
        <td class="num">{_ars(iibb['base'])}</td></tr>
        <tr><td>Alicuota · {escape(datos['jurisdiccion'])}</td>
        <td class="num">{iibb['alicuota']}%</td></tr>
        <tr><td>Retenciones y percepciones sufridas</td>
        <td class="num">-{_ars(iibb['retenciones_sufridas'])}</td></tr>
        </tbody></table>
        <div class="resultado pagar"><span>Ingresos Brutos a pagar</span>
        <span class="monto">{_ars(iibb['a_pagar'])}</span></div>

        {avisos}
        <div class="pie">Los importes estan expresados en pesos. Las operaciones en
        moneda extranjera se convirtieron al tipo de cambio informado en cada
        comprobante. Este informe es una herramienta de gestion: validalo con tu
        contador antes de presentar la declaracion jurada.</div>""",
    )
