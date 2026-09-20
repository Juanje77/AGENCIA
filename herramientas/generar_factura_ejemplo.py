"""Genera facturas PDF de ejemplo para probar el lector.

No es parte del sistema: sirve para tener material de prueba parecido al que
manda un mayorista, sin usar facturas reales de la agencia.

    python herramientas/generar_factura_ejemplo.py ejemplos/
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import pymupdf
except ImportError:  # versiones viejas exponen el modulo como fitz
    try:
        import fitz as pymupdf
    except ImportError:
        print("Hace falta PyMuPDF: pip install pymupdf")
        raise SystemExit(1)


FACTURAS = [
    {
        "archivo": "factura_ola_A_00012345.pdf",
        "tipo": "A",
        "codigo": "01",
        "emisor": "OLA MAYORISTA S.A.",
        "domicilio_emisor": "Av. Corrientes 880 Piso 4 - CABA",
        "cuit_emisor": "30-58720345-1",
        "ingresos_brutos": "901-234567-8",
        "inicio_actividades": "01/03/1998",
        "punto_venta": "0003",
        "numero": "00012345",
        "fecha": "30/09/2026",
        "receptor": "VIAJES ALTA PAMPA S.R.L.",
        "cuit_receptor": "30-71234567-9",
        "domicilio_receptor": "Av. San Martin 250 - Santa Rosa, La Pampa",
        "condicion_iva_receptor": "IVA Responsable Inscripto",
        "condicion_venta": "Cuenta Corriente",
        "periodo": "01/09/2026 al 30/09/2026",
        "items": [
            ("F-102345", "Comision s/ venta aereo internacional EZE-MAD-EZE", "160.950,00"),
            ("F-102346", "Comision s/ paquete Cancun 7 noches", "417.600,00"),
            ("F-102350", "Comision s/ aereo cabotaje AEP-BRC", "30.800,00"),
        ],
        "neto_gravado": "448.400,00",
        "iva_21": "94.164,00",
        "no_gravado": "160.950,00",
        "percepcion_iibb": "8.968,00",
        "total": "712.482,00",
        "cae": "76234598712345",
        "vto_cae": "10/10/2026",
    },
    {
        "archivo": "factura_toselli_A_00004521.pdf",
        "tipo": "A",
        "codigo": "01",
        "emisor": "TOSELLI VIAJES S.A.",
        "domicilio_emisor": "Bv. Chacabuco 1120 - Cordoba",
        "cuit_emisor": "30-61234890-4",
        "ingresos_brutos": "904-888111-2",
        "inicio_actividades": "15/07/1992",
        "punto_venta": "0007",
        "numero": "00004521",
        "fecha": "30/09/2026",
        "receptor": "VIAJES ALTA PAMPA S.R.L.",
        "cuit_receptor": "30-71234567-9",
        "domicilio_receptor": "Av. San Martin 250 - Santa Rosa, La Pampa",
        "condicion_iva_receptor": "IVA Responsable Inscripto",
        "condicion_venta": "Contado",
        "periodo": "01/09/2026 al 30/09/2026",
        "items": [
            ("R-88120", "Comision 2,70% s/ Perez - Cancun", "233.550,00"),
            ("R-88134", "Comision 2,70% s/ Familia Diaz - Brasil", "98.400,00"),
        ],
        "neto_gravado": "331.950,00",
        "iva_21": "69.709,50",
        "no_gravado": "0,00",
        "percepcion_iibb": "6.639,00",
        "total": "408.298,50",
        "cae": "76234511998877",
        "vto_cae": "10/10/2026",
    },
]


def dibujar(factura: dict, destino: Path) -> Path:
    documento = pymupdf.open()
    pagina = documento.new_page(width=595, height=842)  # A4

    negro = (0, 0, 0)
    gris = (0.35, 0.35, 0.35)

    def texto(x, y, contenido, tamano=8.5, negrita=False, color=negro):
        pagina.insert_text(
            (x, y), contenido, fontsize=tamano,
            fontname="hebo" if negrita else "helv", color=color,
        )

    def linea(y, x0=40, x1=555):
        pagina.draw_line(pymupdf.Point(x0, y), pymupdf.Point(x1, y), color=gris, width=0.6)

    def recuadro(x0, y0, x1, y1):
        pagina.draw_rect(pymupdf.Rect(x0, y0, x1, y1), color=gris, width=0.6)

    # --- Encabezado con el recuadro del tipo de comprobante ---
    recuadro(40, 40, 555, 140)
    pagina.draw_line(pymupdf.Point(297, 40), pymupdf.Point(297, 140), color=gris, width=0.6)
    recuadro(283, 35, 312, 70)
    texto(292, 58, factura["tipo"], 18, True)
    texto(285, 66, f"COD. {factura['codigo']}", 5.5)

    texto(50, 58, factura["emisor"], 12, True)
    texto(50, 72, factura["domicilio_emisor"], 8)
    texto(50, 84, "Razon Social: " + factura["emisor"], 7.5)
    texto(50, 95, "Condicion frente al IVA: IVA Responsable Inscripto", 7.5)
    texto(50, 106, f"Ingresos Brutos: {factura['ingresos_brutos']}", 7.5)
    texto(50, 117, f"Inicio de Actividades: {factura['inicio_actividades']}", 7.5)

    texto(310, 58, "FACTURA", 13, True)
    texto(310, 76, f"Punto de Venta: {factura['punto_venta']}", 8.5)
    texto(420, 76, f"Comp. Nro: {factura['numero']}", 8.5)
    texto(310, 90, f"Fecha de Emision: {factura['fecha']}", 8.5)
    texto(310, 104, f"CUIT: {factura['cuit_emisor']}", 8.5)
    texto(310, 118, f"Periodo Facturado Desde: {factura['periodo']}", 7.5)

    # --- Datos del receptor ---
    recuadro(40, 148, 555, 205)
    texto(50, 162, f"CUIT: {factura['cuit_receptor']}", 8.5)
    texto(200, 162, f"Apellido y Nombre / Razon Social: {factura['receptor']}", 8.5)
    texto(50, 176, f"Condicion frente al IVA: {factura['condicion_iva_receptor']}", 8.5)
    texto(50, 190, f"Domicilio: {factura['domicilio_receptor']}", 8.5)
    texto(380, 190, f"Condicion de venta: {factura['condicion_venta']}", 8.5)

    # --- Detalle ---
    y = 225
    texto(50, y, "Codigo", 7.5, True)
    texto(110, y, "Producto / Servicio", 7.5, True)
    texto(470, y, "Subtotal", 7.5, True)
    linea(y + 5)

    y += 20
    for codigo, descripcion, importe in factura["items"]:
        texto(50, y, codigo, 8)
        texto(110, y, descripcion, 8)
        texto(470, y, importe, 8)
        y += 16

    linea(y + 4)
    y += 24

    # --- Totales ---
    etiquetas = [
        ("Importe Neto Gravado: $", factura["neto_gravado"]),
        ("IVA 21%: $", factura["iva_21"]),
        ("Importe Otros Tributos: $", factura["percepcion_iibb"]),
        ("Importe Neto No Gravado: $", factura["no_gravado"]),
    ]
    for etiqueta, valor in etiquetas:
        texto(330, y, etiqueta, 8.5)
        texto(470, y, valor, 8.5)
        y += 15

    texto(330, y + 4, "Importe Total: $", 10, True)
    texto(470, y + 4, factura["total"], 10, True)

    # --- Percepcion detallada ---
    y += 34
    texto(50, y, "Otros Tributos", 7.5, True)
    linea(y + 4)
    texto(50, y + 18, "Percepcion de Ingresos Brutos - La Pampa", 8)
    texto(470, y + 18, factura["percepcion_iibb"], 8)

    # --- Pie con CAE ---
    texto(330, 790, f"CAE N: {factura['cae']}", 9, True)
    texto(330, 804, f"Fecha de Vto. de CAE: {factura['vto_cae']}", 8.5)
    texto(50, 804, "Comprobante Autorizado", 7.5, color=gris)

    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.save(destino)
    documento.close()
    return destino


PIE_HORIZONTAL = {
    "archivo": "factura_pie_horizontal_USD.pdf",
    "emisor": "OPERADOR MAYORISTA DEMO S.A.",
    "cuit_emisor": "30-61111111-7",
    "receptor": "AGENCIA DEMO",
    "cuit_receptor": "27-12345678-9",
    "punto_venta": "0022",
    "numero": "00099887",
    "fecha": "30/09/2026",
    "moneda": "USD",
    "tipo_cambio": "1512,00",
    "columnas": ["Exento", "No Gravado", "Gravado 21%", "Gravado 10.5%",
                 "Perc RG/ZK", "Perc IIBB COR"],
    "valores": ["2.418,50", "29,01", "0,00", "0,00", "0,00", "0,00"],
    "columnas2": ["I.V.A. 21%", "I.V.A. 10,5%", "Impuesto PAIS:", "RG 4815/5617:",
                  "RG 5272:", "Total"],
    "valores2": ["0,00", "0,00", "0,00", "0,00", "0,00", "2.447,51"],
    "cae": "86350571038437",
    "vto_cae": "09/09/2026",
}


def dibujar_pie_horizontal(factura: dict, destino: Path) -> Path:
    """Factura con el pie de totales en columnas, como la emiten varios mayoristas."""
    documento = pymupdf.open()
    pagina = documento.new_page(width=595, height=842)

    def texto(x, y, contenido, tamano=8.5, negrita=False):
        pagina.insert_text(
            (x, y), contenido, fontsize=tamano,
            fontname="hebo" if negrita else "helv", color=(0, 0, 0),
        )

    texto(40, 55, "A", 16, True)
    texto(40, 68, "Codigo 1", 6)
    texto(70, 55, factura["emisor"], 12, True)
    texto(70, 70, f"C.U.I.T.: {factura['cuit_emisor']}", 8)
    texto(360, 55, f"Factura: {factura['punto_venta']}-{factura['numero']}", 10, True)
    texto(360, 70, f"FECHA: {factura['fecha']}", 8.5)
    texto(360, 84, f"Moneda: {factura['moneda']}", 8.5)
    texto(360, 98, f"Tipo de Cambio: {factura['tipo_cambio']}", 8.5)

    texto(40, 120, f"Sr./Sres {factura['receptor']}", 9)
    texto(40, 134, f"CUIT: {factura['cuit_receptor']}", 8.5)
    texto(40, 148, "Negocio: 2539121 DEMO / PASAJERO x2", 8.5)

    texto(40, 180, "Detalle de servicios facturados:", 9, True)
    texto(40, 198, "Servicios Salida/In Out", 8)
    texto(40, 214, "PASAJERO/DEMO Ruta: AEP/GRU/AEP Cia:AR", 8)

    # Pie en dos bloques de columnas.
    y = 300
    for columnas, valores in (
        (factura["columnas"], factura["valores"]),
        (factura["columnas2"], factura["valores2"]),
    ):
        x = 45
        for etiqueta in columnas:
            texto(x, y, etiqueta, 7.5)
            x += 85
        x = 45
        for valor in valores:
            texto(x, y + 14, valor, 8)
            x += 85
        y += 42

    texto(40, 790, f"CAE: {factura['cae']}", 9, True)
    texto(40, 804, f"Fecha Vto. CAE: {factura['vto_cae']}", 8.5)

    destino.parent.mkdir(parents=True, exist_ok=True)
    documento.save(destino)
    documento.close()
    return destino


def main() -> int:
    carpeta = Path(sys.argv[1] if len(sys.argv) > 1 else "ejemplos")
    for factura in FACTURAS:
        ruta = dibujar(factura, carpeta / factura["archivo"])
        print(f"generada: {ruta}")
    ruta = dibujar_pie_horizontal(PIE_HORIZONTAL, carpeta / PIE_HORIZONTAL["archivo"])
    print(f"generada: {ruta}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
