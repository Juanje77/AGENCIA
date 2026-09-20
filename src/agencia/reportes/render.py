"""Informes HTML de liquidaciones y de posicion fiscal."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from ..dinero import CERO, dec, formato_ars
from ..liquidaciones.conciliacion import ALTA, Conciliacion
from .posicion_fiscal import PosicionFiscal

_CSS = """
:root{--tinta:#1F2D2B;--suave:#5B6B64;--linea:#D7DED7;--fondo:#EEF1EC;
--acento:#2B5E55;--ok:#0F6E5C;--alerta:#A6392D;}
*{box-sizing:border-box}
body{margin:0;padding:30px;background:var(--fondo);color:var(--tinta);
font:14px/1.5 'Inter',-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.hoja{max-width:940px;margin:0 auto;background:#fff;padding:38px;
border:1px solid var(--linea);border-radius:6px}
header{display:flex;justify-content:space-between;align-items:flex-start;
gap:22px;border-bottom:2px solid var(--tinta);padding-bottom:16px;margin-bottom:22px}
h1{font-size:23px;margin:0 0 5px}
h2{font-size:15px;margin:26px 0 10px;text-transform:uppercase;
letter-spacing:.05em;color:var(--suave)}
.meta{text-align:right;font-size:12.5px;color:var(--suave)}
.meta strong{color:var(--tinta);font-size:14px}
.datos{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:11px 22px;font-size:13.5px;margin-bottom:8px}
.datos div span{display:block;color:var(--suave);font-size:11px;
text-transform:uppercase;letter-spacing:.045em}
table{width:100%;border-collapse:collapse;font-size:13.5px;margin-bottom:8px}
th{text-align:left;font-size:11px;text-transform:uppercase;letter-spacing:.045em;
color:var(--suave);border-bottom:1px solid var(--linea);padding:8px 9px}
td{padding:9px;border-bottom:1px solid var(--linea);vertical-align:top}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
tr.total td{font-weight:700;border-top:2px solid var(--tinta);border-bottom:none;font-size:15px}
.detalle{display:block;color:var(--suave);font-size:12px;margin-top:2px}
.resaltado{background:var(--fondo);border-radius:6px;padding:15px 18px;margin:18px 0}
.avisos{border-left:3px solid var(--alerta);padding:10px 15px;margin:16px 0;
background:#FBF0DC;font-size:12.5px}
.avisos ul{margin:5px 0 0;padding-left:17px}
.pie{margin-top:26px;padding-top:15px;border-top:1px solid var(--linea);
font-size:12px;color:var(--suave)}
.positivo{color:var(--ok);font-weight:600}
@media print{body{background:#fff;padding:0}.hoja{border:none;padding:14px}}
"""

_CSS_EXTRA = """
.tarjetas{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));
gap:14px;margin:18px 0}
.tarjeta{background:var(--fondo);border:1px solid var(--linea);border-radius:9px;padding:14px 16px}
.tarjeta .rotulo{font-size:11.5px;text-transform:uppercase;letter-spacing:.05em;color:var(--suave)}
.tarjeta .valor{font-size:21px;font-weight:700;margin-top:4px;font-variant-numeric:tabular-nums}
.sev{display:inline-block;border-radius:4px;padding:1px 7px;font-size:11px;font-weight:700}
.sev-ALTA{background:#fdeceb;color:#a1231c}
.sev-MEDIA{background:#fff6e5;color:#8a5a00}
.sev-INFO{background:#eef3fb;color:#2c5282}
.neg{color:#a1231c}
tr.aviso td{background:#fffaf4}
"""


def _documento(titulo: str, cuerpo: str) -> str:
    return (
        f"<!DOCTYPE html><html lang='es'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>{escape(titulo)}</title><style>{_CSS}{_CSS_EXTRA}</style></head>"
        f"<body><div class='hoja'>{cuerpo}</div></body></html>"
    )


def _tarjeta(rotulo: str, valor: str, clase: str = "") -> str:
    return (
        f"<div class='tarjeta'><div class='rotulo'>{escape(rotulo)}</div>"
        f"<div class='valor {clase}'>{valor}</div></div>"
    )


def render_liquidacion(conciliacion: Conciliacion) -> str:
    """Informe de control de una liquidacion de mayorista."""
    liq = conciliacion.liquidacion
    totales = conciliacion.impuestos.get("totales", {})

    partes = [
        f"""<header><div><h1>Control de liquidacion</h1>
        <div style="color:#5b6875">{escape(liq.mayorista or 'Mayorista sin identificar')}
        {f' · {escape(liq.periodo)}' if liq.periodo else ''}</div></div>
        <div class="meta"><strong>{escape(liq.numero or liq.archivo_origen.split('/')[-1])}</strong><br>
        {liq.cantidad_lineas} reservas<br>Perfil: {escape(liq.perfil_usado)}</div></header>""",
        "<div class='tarjetas'>",
        _tarjeta("Comisiones (base)", formato_ars(totales.get("retribucion_bruta", CERO))),
        _tarjeta("IVA debito fiscal", formato_ars(totales.get("debito_fiscal", CERO))),
        _tarjeta("Ingresos Brutos", formato_ars(totales.get("iibb_total", CERO))),
        _tarjeta(
            "Diferencias",
            f"{len(conciliacion.diferencias)}",
            "neg" if conciliacion.diferencias_altas else "",
        ),
        "</div>",
    ]

    if conciliacion.diferencias:
        partes.append("<h2>Diferencias a revisar</h2>")
        partes.append(_tabla_diferencias(conciliacion))
    else:
        partes.append(
            "<div class='resaltado'>Sin diferencias: la liquidacion coincide con "
            "el recalculo de impuestos y retenciones.</div>"
        )

    partes.append("<h2>Retenciones del pago</h2>")
    partes.append(_tabla_retenciones(conciliacion))

    partes.append("<h2>Impuestos por reserva</h2>")
    partes.append(_tabla_lineas(conciliacion))

    partes.append("<h2>Como se leyo el archivo</h2>")
    partes.append(_tabla_columnas(liq))

    if conciliacion.avisos:
        avisos = "".join(f"<li>{escape(a)}</li>" for a in conciliacion.avisos)
        partes.append(
            f"<div class='avisos'><strong>Avisos</strong><ul>{avisos}</ul></div>"
        )

    return _documento(f"Liquidacion {liq.mayorista} {liq.periodo}", "".join(partes))


def _tabla_diferencias(conciliacion: Conciliacion) -> str:
    filas = []
    for d in sorted(conciliacion.diferencias, key=lambda x: (x.severidad != ALTA, x.fila)):
        filas.append(
            f"<tr><td><span class='sev sev-{d.severidad}'>{d.severidad}</span></td>"
            f"<td>{escape(d.referencia or '-')}"
            f"{f'<span class=detalle>fila {d.fila}</span>' if d.fila else ''}</td>"
            f"<td>{escape(d.concepto)}"
            f"{f'<span class=detalle>{escape(d.comentario)}</span>' if d.comentario else ''}</td>"
            f"<td class='num'>{formato_ars(d.informado)}</td>"
            f"<td class='num'>{formato_ars(d.esperado)}</td>"
            f"<td class='num {'neg' if d.importe > CERO else ''}'>{formato_ars(d.importe)}</td></tr>"
        )
    return (
        "<table><thead><tr><th></th><th>Reserva</th><th>Concepto</th>"
        "<th class='num'>Liquidado</th><th class='num'>Calculado</th>"
        f"<th class='num'>Diferencia</th></tr></thead><tbody>{''.join(filas)}</tbody></table>"
    )


def _tabla_retenciones(conciliacion: Conciliacion) -> str:
    filas = []
    for r in conciliacion.retenciones.get("detalle", []):
        diferencia = dec(r["diferencia"])
        motivo = str(r.get("motivo") or "")
        detalle = f"<span class='detalle'>{escape(motivo)}</span>" if motivo else ""
        clase = "neg" if diferencia != CERO else ""
        filas.append(
            f"<tr><td>{escape(str(r['etiqueta']))}{detalle}</td>"
            f"<td class='num'>{formato_ars(r['base'])}</td>"
            f"<td class='num'>{r['alicuota']}%</td>"
            f"<td class='num'>{formato_ars(r['esperado'])}</td>"
            f"<td class='num'>{formato_ars(r['informado'])}</td>"
            f"<td class='num {clase}'>{formato_ars(diferencia)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Regimen</th><th class='num'>Base</th>"
        "<th class='num'>Alic.</th><th class='num'>Calculado</th>"
        "<th class='num'>Retenido</th><th class='num'>Diferencia</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table>"
    )


def _tabla_lineas(conciliacion: Conciliacion) -> str:
    filas = []
    for c in conciliacion.lineas:
        linea = c.linea
        if c.fiscal is None:
            filas.append(
                f"<tr class='aviso'><td>{escape(linea.referencia)}"
                f"<span class='detalle'>{escape(linea.pasajero)}</span></td>"
                f"<td colspan='5'>{escape(c.motivo_omision)}</td></tr>"
            )
            continue
        f = c.fiscal
        filas.append(
            f"<tr><td>{escape(linea.referencia)}"
            f"<span class='detalle'>{escape(linea.pasajero)} · {escape(linea.destino)}</span></td>"
            f"<td>{escape(linea.tipo_servicio.replace('_', ' ').title())}"
            f"<span class='detalle'>{escape(linea.moneda.value)}"
            f"{f' @ {linea.tipo_cambio}' if linea.moneda.value != 'ARS' else ''}</span></td>"
            f"<td class='num'>{formato_ars(f.operacion.comision)}</td>"
            f"<td class='num'>{formato_ars(f.debito_fiscal)}</td>"
            f"<td class='num'>{formato_ars(f.iibb_total)}</td>"
            f"<td class='num positivo'>{formato_ars(f.margen_neto)}</td></tr>"
        )
    return (
        "<table><thead><tr><th>Reserva</th><th>Servicio</th>"
        "<th class='num'>Comision (ARS)</th><th class='num'>IVA debito</th>"
        "<th class='num'>IIBB</th><th class='num'>Margen neto</th></tr></thead>"
        f"<tbody>{''.join(filas)}</tbody></table>"
    )


def _tabla_columnas(liquidacion) -> str:
    filas = "".join(
        f"<tr><td>{escape(original)}</td><td>{escape(campo)}</td></tr>"
        for original, campo in liquidacion.columnas_detectadas.items()
    )
    ignoradas = (
        "<p style='font-size:13px;color:#5b6875'>Columnas no interpretadas: "
        + escape(", ".join(liquidacion.columnas_ignoradas))
        + "</p>"
        if liquidacion.columnas_ignoradas
        else ""
    )
    return (
        "<table><thead><tr><th>Columna del archivo</th><th>Campo del sistema</th>"
        f"</tr></thead><tbody>{filas}</tbody></table>{ignoradas}"
    )


def render_posicion(posicion: PosicionFiscal) -> str:
    """Informe de posicion de IVA e Ingresos Brutos del periodo."""
    partes = [
        f"""<header><div><h1>Posicion fiscal</h1>
        <div style="color:#5b6875">Periodo {escape(posicion.periodo or 'sin especificar')} ·
        {posicion.operaciones} operaciones</div></div>
        <div class="meta"><strong>{len(posicion.liquidaciones)} liquidacion(es)</strong><br>
        {escape(', '.join(posicion.liquidaciones[:4]))}</div></header>""",
        "<div class='tarjetas'>",
        _tarjeta("IVA a ingresar", formato_ars(posicion.iva_a_ingresar)),
        _tarjeta("Ingresos Brutos a ingresar", formato_ars(posicion.iibb_a_ingresar)),
        _tarjeta("Comisiones del periodo", formato_ars(posicion.retribucion_bruta)),
        _tarjeta("Presion fiscal", f"{posicion.presion_fiscal_pct}%"),
        "</div>",
        "<h2>Impuesto al valor agregado</h2>",
        _tabla_iva(posicion),
        "<h2>Ingresos Brutos por jurisdiccion</h2>",
        _tabla_iibb(posicion),
        "<h2>Retenciones sufridas (pagos a cuenta)</h2>",
        f"""<div class="datos">
          <div><span>IVA RG 2854</span>{formato_ars(posicion.retenciones_iva_sufridas)}</div>
          <div><span>Ingresos Brutos</span>{formato_ars(posicion.retenciones_iibb_sufridas)}</div>
          <div><span>Ganancias RG 830</span>{formato_ars(posicion.retenciones_ganancias_sufridas)}</div>
        </div>""",
    ]

    if posicion.diferencias_detectadas:
        partes.append(
            f"""<div class='avisos'><strong>Control de liquidaciones</strong>
            <ul><li>{posicion.diferencias_detectadas} diferencia(s) detectadas,
            {posicion.diferencias_altas} de severidad alta.</li>
            <li>Importe total involucrado: {formato_ars(posicion.importe_en_disputa)}</li>
            </ul></div>"""
        )

    if posicion.avisos:
        avisos = "".join(f"<li>{escape(a)}</li>" for a in posicion.avisos)
        partes.append(f"<div class='avisos'><strong>Avisos</strong><ul>{avisos}</ul></div>")

    return _documento(f"Posicion fiscal {posicion.periodo}", "".join(partes))


def _tabla_iva(posicion: PosicionFiscal) -> str:
    filas = "".join(
        f"<tr><td>{escape(tratamiento.replace('_', ' ').title())}</td>"
        f"<td class='num'>{formato_ars(valores['base'])}</td>"
        f"<td class='num'>{formato_ars(valores['impuesto'])}</td></tr>"
        for tratamiento, valores in sorted(posicion.por_tratamiento.items())
    )
    return f"""<table><thead><tr><th>Tratamiento</th><th class='num'>Base imponible</th>
    <th class='num'>Impuesto</th></tr></thead><tbody>{filas}
    <tr class='total'><td>Debito fiscal</td><td class='num'></td>
    <td class='num'>{formato_ars(posicion.debito_fiscal)}</td></tr>
    <tr><td>Credito fiscal</td><td class='num'></td>
    <td class='num'>-{formato_ars(posicion.credito_fiscal)}</td></tr>
    <tr><td>Retenciones sufridas</td><td class='num'></td>
    <td class='num'>-{formato_ars(posicion.retenciones_iva_sufridas)}</td></tr>
    <tr class='total'><td>Saldo a ingresar</td><td class='num'></td>
    <td class='num'>{formato_ars(posicion.iva_a_ingresar)}</td></tr></tbody></table>"""


def _tabla_iibb(posicion: PosicionFiscal) -> str:
    filas = "".join(
        f"<tr><td>{escape(str(valores.get('etiqueta', codigo)))}</td>"
        f"<td class='num'>{formato_ars(valores['base'])}</td>"
        f"<td class='num'>{formato_ars(valores['impuesto'])}</td></tr>"
        for codigo, valores in sorted(posicion.iibb_por_jurisdiccion.items())
    )
    return f"""<table><thead><tr><th>Jurisdiccion</th><th class='num'>Base imponible</th>
    <th class='num'>Impuesto</th></tr></thead><tbody>{filas}
    <tr class='total'><td>Determinado</td><td class='num'></td>
    <td class='num'>{formato_ars(posicion.iibb_determinado)}</td></tr>
    <tr><td>Retenciones sufridas</td><td class='num'></td>
    <td class='num'>-{formato_ars(posicion.retenciones_iibb_sufridas)}</td></tr>
    <tr class='total'><td>Saldo a ingresar</td><td class='num'></td>
    <td class='num'>{formato_ars(posicion.iibb_a_ingresar)}</td></tr></tbody></table>"""
