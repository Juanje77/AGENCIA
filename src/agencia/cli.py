"""Interfaz de linea de comandos.

    agencia factura facturas/*.pdf --periodo 09/2026
    agencia cotizacion ejemplos/cotizacion.json --cliente salida.html
    agencia liquidacion planilla.csv --mayorista Ola --periodo 2026-09
    agencia servidor
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from .config import cargar_parametros, perfiles_disponibles
from .dinero import dec, formato_ars
from .dominio import CondicionIVA
from .liquidaciones import ErrorDeLectura, conciliar, importar_liquidacion
from .reportes import (
    armar_posicion,
    exportar_diferencias,
    exportar_lineas,
    exportar_posicion,
    render_liquidacion,
    render_posicion,
)

ROJO, AMARILLO, VERDE, GRIS, FIN = "\033[31m", "\033[33m", "\033[32m", "\033[90m", "\033[0m"


def _color(texto: str, color: str) -> str:
    return f"{color}{texto}{FIN}" if sys.stdout.isatty() else texto


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="agencia",
        description="Presupuestador y control fiscal para agencias de viajes.",
    )
    sub = parser.add_subparsers(dest="comando", required=True)

    p_liq = sub.add_parser("liquidacion", help="Leer y controlar una liquidacion de mayorista")
    p_liq.add_argument("archivo", help="CSV, XLSX o PDF de la liquidacion")
    p_liq.add_argument("--mayorista", default="", help="Nombre del mayorista")
    p_liq.add_argument("--periodo", default="", help="Periodo, por ejemplo 2026-09")
    p_liq.add_argument("--perfil", default=None, help="Perfil de config/mayoristas/")
    p_liq.add_argument("--tc", default=None, help="Tipo de cambio si el archivo no lo trae")
    p_liq.add_argument("--html", default=None, help="Guardar el informe HTML")
    p_liq.add_argument("--csv", default=None, help="Guardar el detalle en CSV")
    p_liq.add_argument("--json", action="store_true", help="Salida JSON")

    p_fac = sub.add_parser("factura", help="Leer facturas PDF de mayoristas y liquidar")
    p_fac.add_argument("archivos", nargs="+", help="Facturas en PDF")
    p_fac.add_argument("--periodo", default="", help="Periodo, por ejemplo 09/2026")
    p_fac.add_argument("--cuit", default="", help="CUIT de la agencia")
    p_fac.add_argument("--servicio-propio", default="0", help="% de servicio propio")
    p_fac.add_argument("--alicuota-iibb", default=None, help="Alicuota de IIBB")
    p_fac.add_argument("--computar-credito", action="store_true",
                       help="Computar el IVA de las facturas como credito fiscal")
    p_fac.add_argument("--html", default=None, help="Guardar el informe")
    p_fac.add_argument("--json", action="store_true", help="Salida JSON")

    p_cot = sub.add_parser("cotizacion", help="Calcular una cotizacion desde un JSON")
    p_cot.add_argument("archivo", help="JSON con la cotizacion")
    p_cot.add_argument("--cliente", default=None, help="Guardar la propuesta del cliente")
    p_cot.add_argument("--agencia", default=None, help="Guardar el analisis interno")
    p_cot.add_argument("--json", action="store_true", help="Salida JSON")

    p_pos = sub.add_parser("posicion", help="Posicion de IVA e IIBB de un periodo")
    p_pos.add_argument("archivos", nargs="+", help="Liquidaciones del periodo")
    p_pos.add_argument("--periodo", default="", help="Periodo, por ejemplo 2026-09")
    p_pos.add_argument("--tc", default=None, help="Tipo de cambio por defecto")
    p_pos.add_argument("--html", default=None, help="Guardar el informe HTML")
    p_pos.add_argument("--csv", default=None, help="Guardar la posicion en CSV")
    p_pos.add_argument("--json", action="store_true", help="Salida JSON")

    p_srv = sub.add_parser("servidor", help="Levantar la interfaz web")
    p_srv.add_argument("--puerto", type=int, default=8000)
    p_srv.add_argument("--host", default="127.0.0.1")

    sub.add_parser("mayoristas", help="Listar los mayoristas configurados")
    sub.add_parser("perfiles", help="Listar los perfiles de planilla disponibles")
    sub.add_parser("parametros", help="Mostrar los parametros fiscales cargados")

    args = parser.parse_args(argv)

    try:
        return _despachar(args)
    except ErrorDeLectura as exc:
        print(_color(f"Error al leer el archivo: {exc}", ROJO), file=sys.stderr)
        return 2
    except (FileNotFoundError, KeyError, ValueError) as exc:
        print(_color(f"Error: {exc}", ROJO), file=sys.stderr)
        return 1


def _despachar(args) -> int:
    if args.comando == "liquidacion":
        return _cmd_liquidacion(args)
    if args.comando == "factura":
        return _cmd_factura(args)
    if args.comando == "cotizacion":
        return _cmd_cotizacion(args)
    if args.comando == "posicion":
        return _cmd_posicion(args)
    if args.comando == "servidor":
        from .web.servidor import correr

        correr(args.host, args.puerto)
        return 0
    if args.comando == "mayoristas":
        return _cmd_mayoristas()
    if args.comando == "perfiles":
        return _cmd_perfiles()
    if args.comando == "parametros":
        return _cmd_parametros()
    return 1


def _cmd_liquidacion(args) -> int:
    liquidacion = importar_liquidacion(
        args.archivo,
        perfil=args.perfil,
        mayorista=args.mayorista,
        periodo=args.periodo,
        tipo_cambio=args.tc,
    )
    conciliacion = conciliar(liquidacion)

    if args.json:
        print(json.dumps(conciliacion.a_dict(), indent=2, ensure_ascii=False))
    else:
        _imprimir_liquidacion(conciliacion)

    if args.html:
        Path(args.html).write_text(render_liquidacion(conciliacion), encoding="utf-8")
        print(f"\nInforme guardado en {args.html}")
    if args.csv:
        exportar_lineas(conciliacion, args.csv)
        diferencias = Path(args.csv).with_name(Path(args.csv).stem + "_diferencias.csv")
        exportar_diferencias(conciliacion, diferencias)
        print(f"Detalle en {args.csv} y diferencias en {diferencias}")

    return 3 if conciliacion.diferencias_altas else 0


def _imprimir_liquidacion(conciliacion) -> None:
    liq = conciliacion.liquidacion
    totales = conciliacion.impuestos.get("totales", {})

    print(f"\n{liq.mayorista or 'Liquidacion'} · {liq.periodo or 's/periodo'}")
    print(f"{liq.cantidad_lineas} reservas leidas de {Path(liq.archivo_origen).name}")
    print(_color(f"Columnas interpretadas: {len(liq.columnas_detectadas)}", GRIS))
    if liq.columnas_ignoradas:
        print(_color(f"Columnas ignoradas: {', '.join(liq.columnas_ignoradas)}", GRIS))

    print("\n--- Impuestos del periodo ---")
    print(f"  Comisiones (base)    {formato_ars(totales.get('retribucion_bruta', 0)):>18}")
    print(f"  IVA debito fiscal    {formato_ars(totales.get('debito_fiscal', 0)):>18}")
    print(f"  Ingresos Brutos      {formato_ars(totales.get('iibb_total', 0)):>18}")
    print(f"  Margen neto          {formato_ars(totales.get('margen_neto', 0)):>18}")

    for codigo, valores in sorted(conciliacion.impuestos.get("por_jurisdiccion", {}).items()):
        print(
            f"    {valores.get('etiqueta', codigo):<22} base "
            f"{formato_ars(valores['base']):>16}  impuesto {formato_ars(valores['impuesto']):>14}"
        )

    print("\n--- Retenciones del pago ---")
    for r in conciliacion.retenciones.get("detalle", []):
        marca = "" if r["diferencia"] == Decimal("0.00") else " <-- revisar"
        print(
            f"  {r['etiqueta'][:42]:<42} calc {formato_ars(r['esperado']):>14}"
            f"  ret {formato_ars(r['informado']):>14}{_color(marca, AMARILLO)}"
        )

    if conciliacion.diferencias:
        print(f"\n--- {len(conciliacion.diferencias)} diferencia(s) ---")
        for d in conciliacion.diferencias:
            color = ROJO if d.severidad == "ALTA" else AMARILLO
            etiqueta = _color(f"[{d.severidad}]", color)
            print(f"  {etiqueta} {d.referencia or '(total)'} · {d.concepto}")
            print(
                f"        liquidado {formato_ars(d.informado)} | "
                f"calculado {formato_ars(d.esperado)} | "
                f"diferencia {formato_ars(d.importe)}"
            )
            if d.comentario:
                print(_color(f"        {d.comentario}", GRIS))
    else:
        print(_color("\nSin diferencias: la liquidacion cierra con el recalculo.", VERDE))

    for aviso in conciliacion.avisos:
        print(_color(f"  aviso: {aviso}", GRIS))


def _cmd_factura(args) -> int:
    """Lee facturas de mayoristas y arma la liquidacion del periodo."""
    from .liquidaciones.factura import leer_factura
    from .liquidador import Periodo, cargar_padron, operacion_desde_comprobante
    from .web.informes import informe_periodo

    padron = cargar_padron()
    cuit = args.cuit or padron.agencia.cuit
    periodo = Periodo(
        periodo=args.periodo,
        alicuota_iibb=dec(args.alicuota_iibb or padron.agencia.alicuota_iibb),
        jurisdiccion=padron.agencia.jurisdiccion,
        computa_credito_de_mayoristas=args.computar_credito,
    )

    fallidas = 0
    for ruta in args.archivos:
        try:
            comprobante = leer_factura(ruta, cuit_agencia=cuit)
        except ErrorDeLectura as exc:
            print(_color(f"  {Path(ruta).name}: {exc}", ROJO), file=sys.stderr)
            fallidas += 1
            continue
        periodo.operaciones.append(
            operacion_desde_comprobante(comprobante, padron, args.servicio_propio)
        )

    if not periodo.operaciones:
        print(_color("No se pudo leer ninguna factura.", ROJO), file=sys.stderr)
        return 2

    datos = periodo.a_dict()
    if args.json:
        print(json.dumps(datos, indent=2, ensure_ascii=False))
    else:
        _imprimir_periodo(periodo, datos)

    if args.html:
        Path(args.html).write_text(informe_periodo(periodo), encoding="utf-8")
        print(f"\nInforme guardado en {args.html}")

    return 3 if fallidas else 0


def _imprimir_periodo(periodo, datos) -> None:
    print(f"\nLiquidacion {datos['periodo'] or 'sin periodo'} · {datos['jurisdiccion']}")
    print(f"{len(periodo.operaciones)} operacion(es)\n")
    for operacion in periodo.operaciones:
        marca = "" if operacion.convertible else _color("  (sin tipo de cambio)", AMARILLO)
        print(
            f"  {operacion.mayorista[:16]:<16} {operacion.comprobante[:24]:<24} "
            f"{operacion.moneda} comision {operacion.comision_ganada:>12}{marca}"
        )

    iva, iibb = datos["iva"], datos["iibb"]
    print("\n  IVA")
    print(f"    Debito fiscal        {formato_ars(iva['debito_fiscal']):>18}")
    print(f"    Credito fiscal       {formato_ars(iva['credito_fiscal']):>18}")
    resultado = dec(iva["resultado"])
    etiqueta = "A pagar" if resultado >= 0 else "Saldo a favor"
    print(f"    {etiqueta:<20} {formato_ars(abs(resultado)):>18}")

    print("\n  Ingresos Brutos")
    print(f"    Base imponible       {formato_ars(iibb['base']):>18}")
    print(f"    Alicuota             {iibb['alicuota']:>17}%")
    print(f"    A pagar              {formato_ars(iibb['a_pagar']):>18}")

    print(f"\n  Carga total          {formato_ars(datos['resumen']['carga_total']):>18}")
    print(f"  Ganancia neta        {formato_ars(datos['resumen']['ganancia_neta']):>18}")

    for aviso in datos["avisos"]:
        print(_color(f"\n  aviso: {aviso}", AMARILLO))


def _cmd_cotizacion(args) -> int:
    from .presupuestos import calcular_cotizacion
    from .web.informes import informe_cotizacion_agencia, informe_cotizacion_cliente
    from .web.mapeo import cotizacion_desde_dict

    datos = json.loads(Path(args.archivo).read_text(encoding="utf-8"))
    calculada = calcular_cotizacion(cotizacion_desde_dict(datos))

    if args.json:
        print(json.dumps(calculada.a_dict(), indent=2, ensure_ascii=False))
    else:
        d = calculada.cotizacion.datos
        print(f"\n{d.destino or 'Cotizacion'} · {d.pax} pasajero(s)")
        print(f"{d.numero} · valida hasta {d.vence}\n")
        for opcion in calculada.opciones:
            marcas = []
            if calculada.mas_barata and calculada.mas_barata.opcion.id == opcion.opcion.id:
                marcas.append("mejor precio")
            if calculada.mas_rentable and calculada.mas_rentable.opcion.id == opcion.opcion.id:
                marcas.append("mas rentable")
            sufijo = f"  [{', '.join(marcas)}]" if marcas else ""
            print(f"  {opcion.opcion.nombre[:38]:<38} US$ {opcion.por_pax:>10} por pax"
                  f"   ganancia US$ {opcion.ganancia:>9}{_color(sufijo, VERDE)}")
        for aviso in calculada.avisos:
            print(_color(f"  aviso: {aviso}", GRIS))

    if args.cliente:
        Path(args.cliente).write_text(informe_cotizacion_cliente(calculada), encoding="utf-8")
        print(f"\nPropuesta guardada en {args.cliente}")
    if args.agencia:
        Path(args.agencia).write_text(informe_cotizacion_agencia(calculada), encoding="utf-8")
        print(f"Analisis guardado en {args.agencia}")
    return 0


def _cmd_mayoristas() -> int:
    from .liquidador import cargar_padron

    padron = cargar_padron()
    print(f"Agencia: {padron.agencia.razon_social or '(sin nombre)'} "
          f"CUIT {padron.agencia.cuit or '(sin cargar)'}")
    print(f"Jurisdiccion {padron.agencia.jurisdiccion} · "
          f"IIBB {padron.agencia.alicuota_iibb}%\n")
    if not padron.mayoristas:
        print("No hay mayoristas cargados en config/mayoristas.json")
        return 0
    print("Mayoristas:")
    for mayorista in padron.mayoristas:
        alias = f"  ({', '.join(mayorista.alias)})" if mayorista.alias else ""
        print(f"  {mayorista.nombre:<16} comision {mayorista.comision_pct:>6}%  "
              f"IVA {mayorista.iva_pct}%  {mayorista.cuit or '':<15}{_color(alias, GRIS)}")
    return 0


def _cmd_posicion(args) -> int:
    conciliaciones = []
    for ruta in args.archivos:
        liquidacion = importar_liquidacion(ruta, periodo=args.periodo, tipo_cambio=args.tc)
        conciliaciones.append(conciliar(liquidacion))

    posicion = armar_posicion(conciliaciones, periodo=args.periodo)

    if args.json:
        print(json.dumps(posicion.a_dict(), indent=2, ensure_ascii=False))
    else:
        print(f"\nPosicion fiscal · periodo {posicion.periodo or 's/especificar'}")
        print(f"{posicion.operaciones} operaciones en {len(posicion.liquidaciones)} liquidacion(es)\n")
        print("  IVA")
        print(f"    Debito fiscal          {formato_ars(posicion.debito_fiscal):>18}")
        print(f"    Credito fiscal         {formato_ars(posicion.credito_fiscal):>18}")
        print(f"    Retenciones sufridas   {formato_ars(posicion.retenciones_iva_sufridas):>18}")
        print(f"    A ingresar             {formato_ars(posicion.iva_a_ingresar):>18}")
        print("\n  Ingresos Brutos")
        for codigo, valores in sorted(posicion.iibb_por_jurisdiccion.items()):
            print(
                f"    {valores.get('etiqueta', codigo)[:20]:<20} "
                f"{formato_ars(valores['impuesto']):>18}"
            )
        print(f"    Retenciones sufridas   {formato_ars(posicion.retenciones_iibb_sufridas):>18}")
        print(f"    A ingresar             {formato_ars(posicion.iibb_a_ingresar):>18}")
        print(f"\n  Presion fiscal sobre comisiones: {posicion.presion_fiscal_pct}%")
        if posicion.diferencias_detectadas:
            print(
                _color(
                    f"\n  {posicion.diferencias_detectadas} diferencia(s) detectadas "
                    f"({posicion.diferencias_altas} altas) por "
                    f"{formato_ars(posicion.importe_en_disputa)}",
                    AMARILLO,
                )
            )
        for aviso in posicion.avisos:
            print(_color(f"  aviso: {aviso}", GRIS))

    if args.html:
        Path(args.html).write_text(render_posicion(posicion), encoding="utf-8")
        print(f"\nInforme guardado en {args.html}")
    if args.csv:
        exportar_posicion(posicion, args.csv)
        print(f"Posicion exportada a {args.csv}")
    return 0


def _cmd_perfiles() -> int:
    perfiles = perfiles_disponibles()
    if not perfiles:
        print("No hay perfiles cargados en config/mayoristas/.")
        print("Sin perfil, las columnas igual se detectan automaticamente.")
        return 0
    print("Perfiles de mayorista disponibles:\n")
    for ruta in perfiles:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        print(f"  {ruta.stem:<24} {datos.get('nombre', '')}")
        if datos.get("descripcion"):
            print(_color(f"  {'':<24} {datos['descripcion']}", GRIS))
    return 0


def _cmd_parametros() -> int:
    params = cargar_parametros()
    print(f"Parametros fiscales version {params.version}\n")
    print(f"Jurisdiccion sede: {params.jurisdiccion_sede} · regimen {params.regimen_iibb}\n")
    print("Ingresos Brutos:")
    for codigo, j in sorted(params.jurisdicciones.items()):
        coef = f" coef {j.coeficiente_unificado}" if j.coeficiente_unificado else ""
        print(f"  {j.etiqueta:<26} {j.alicuota}%  base {j.base_default.value}{coef}")
    print("\nTratamiento por servicio:")
    for codigo, s in sorted(params.servicios.items()):
        print(f"  {s.etiqueta:<44} servicio {s.iva_servicio.value:<12} comision {s.iva_comision.value}")
    print("\nRetenciones:")
    for codigo, r in sorted(params.retenciones.items()):
        estado = "activa" if r.activo else "inactiva"
        print(f"  {r.etiqueta:<52} {r.alicuota_inscripto}% ({estado})")
    for aviso in params.advertencias_de_configuracion():
        print(_color(f"\n  {aviso}", AMARILLO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
