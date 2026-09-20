"""Extraccion de texto de PDF con varios motores.

Ninguna libreria de PDF esta garantizada en todos los entornos, asi que se
prueban por orden de calidad y se usa la primera que funcione. Cuando el motor
da las coordenadas de cada palabra, las lineas se reconstruyen por posicion:
en una factura, lo que esta a la misma altura pertenece al mismo renglon,
aunque el PDF lo guarde en bloques separados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .base import ErrorDeLectura

TOLERANCIA_RENGLON = 3.0  # puntos de diferencia vertical para seguir en la misma linea
TOLERANCIA_RENGLON_OCR = 12.0


@dataclass
class Palabra:
    texto: str
    x: float
    y: float


@dataclass
class PaginaPDF:
    numero: int
    texto: str = ""
    renglones: list[list[Palabra]] = field(default_factory=list)

    def lineas(self) -> list[str]:
        """Cada renglon como una linea de texto, respetando el orden horizontal."""
        if self.renglones:
            return [
                " ".join(p.texto for p in sorted(renglon, key=lambda p: p.x))
                for renglon in self.renglones
            ]
        return [l for l in self.texto.splitlines() if l.strip()]


@dataclass
class DocumentoPDF:
    paginas: list[PaginaPDF] = field(default_factory=list)
    motor: str = ""
    avisos: list[str] = field(default_factory=list)

    @property
    def texto(self) -> str:
        return "\n".join(p.texto for p in self.paginas)

    def lineas(self) -> list[str]:
        lineas: list[str] = []
        for pagina in self.paginas:
            lineas.extend(pagina.lineas())
        return lineas


def extraer(ruta: str | Path) -> DocumentoPDF:
    """Devuelve el contenido del PDF con el primer motor disponible."""
    ruta = Path(ruta)
    if not ruta.exists():
        raise ErrorDeLectura(f"No existe el archivo {ruta}")

    intentos: list[str] = []
    for nombre, funcion in (
        ("pymupdf", _con_pymupdf),
        ("pdfplumber", _con_pdfplumber),
        ("pdfminer", _con_pdfminer),
        ("pypdf2", _con_pypdf2),
    ):
        try:
            documento = funcion(ruta)
        except ImportError:
            intentos.append(f"{nombre}: no instalado")
            continue
        except (KeyboardInterrupt, SystemExit):
            raise
        except BaseException as exc:
            # Algunas librerias de PDF fallan con errores nativos que no heredan
            # de Exception y se llevarian puesto el proceso entero.
            intentos.append(f"{nombre}: {type(exc).__name__}")
            continue
        if documento.texto.strip():
            documento.motor = nombre
            return documento
        intentos.append(f"{nombre}: no devolvio texto")

    if _parece_escaneado(ruta):
        texto_ocr = _intentar_ocr(ruta)
        if texto_ocr is not None:
            return texto_ocr
        raise ErrorDeLectura(
            f"El PDF {ruta.name} es una imagen escaneada: no tiene texto que leer.\n"
            "Opciones:\n"
            "  1. Pedile al mayorista el PDF original (el que emite el sistema de "
            "facturacion ya trae el texto adentro).\n"
            "  2. Instalar OCR para leerlo igual:\n"
            "       pip install pytesseract pymupdf\n"
            "       y el motor Tesseract del sistema "
            "(apt install tesseract-ocr tesseract-ocr-spa).\n"
            "  3. Cargar los datos a mano en la pantalla de liquidaciones."
        )

    raise ErrorDeLectura(
        f"No se pudo extraer texto de {ruta.name}.\n"
        "Motores probados: " + "; ".join(intentos) + "\n"
        "Instala uno con: pip install pymupdf"
    )


def _parece_escaneado(ruta: Path) -> bool:
    """Un PDF con imagenes y sin texto es un escaneo."""
    try:
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        with pymupdf.open(ruta) as pdf:
            for pagina in pdf:
                if pagina.get_images():
                    return True
    except BaseException:
        pass
    return False


def _intentar_ocr(ruta: Path) -> DocumentoPDF | None:
    """Lee el PDF con OCR si estan pytesseract y Tesseract disponibles."""
    try:
        import pytesseract
        try:
            import pymupdf
        except ImportError:
            import fitz as pymupdf
        from PIL import Image
    except ImportError:
        return None

    try:
        documento = DocumentoPDF(motor="ocr")
        with pymupdf.open(ruta) as pdf:
            for numero, pagina in enumerate(pdf, start=1):
                # 300 dpi: por debajo, los importes chicos se leen mal.
                pixmap = pagina.get_pixmap(dpi=300)
                imagen = Image.frombytes(
                    "RGB", (pixmap.width, pixmap.height), pixmap.samples
                )
                datos = pytesseract.image_to_data(
                    imagen, lang="spa+eng", output_type=pytesseract.Output.DICT
                )
                palabras = [
                    Palabra(texto=t, x=float(datos["left"][i]), y=float(datos["top"][i]))
                    for i, t in enumerate(datos["text"])
                    if t.strip()
                ]
                documento.paginas.append(
                    PaginaPDF(
                        numero=numero,
                        texto=" ".join(p.texto for p in palabras),
                        renglones=_agrupar_en_renglones(
                            palabras, TOLERANCIA_RENGLON_OCR
                        ),
                    )
                )
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:
        return None

    if not documento.texto.strip():
        return None
    documento.avisos.append(
        "El PDF se leyo con OCR porque venia escaneado. Revisa los importes "
        "contra el papel antes de usarlos para liquidar."
    )
    return documento


def _agrupar_en_renglones(
    palabras: list[Palabra], tolerancia: float = TOLERANCIA_RENGLON
) -> list[list[Palabra]]:
    """Junta las palabras que estan a la misma altura."""
    if not palabras:
        return []
    renglones: list[list[Palabra]] = []
    for palabra in sorted(palabras, key=lambda p: (p.y, p.x)):
        if renglones and abs(renglones[-1][0].y - palabra.y) <= tolerancia:
            renglones[-1].append(palabra)
        else:
            renglones.append([palabra])
    return renglones


def _con_pymupdf(ruta: Path) -> DocumentoPDF:
    try:
        import pymupdf
    except ImportError:
        import fitz as pymupdf  # versiones anteriores

    documento = DocumentoPDF()
    with pymupdf.open(ruta) as pdf:
        for numero, pagina in enumerate(pdf, start=1):
            palabras = [
                Palabra(texto=p[4], x=float(p[0]), y=float(p[1]))
                for p in pagina.get_text("words")
            ]
            documento.paginas.append(
                PaginaPDF(
                    numero=numero,
                    texto=pagina.get_text() or "",
                    renglones=_agrupar_en_renglones(palabras),
                )
            )
    return documento


def _con_pdfplumber(ruta: Path) -> DocumentoPDF:
    import pdfplumber

    documento = DocumentoPDF()
    with pdfplumber.open(ruta) as pdf:
        for numero, pagina in enumerate(pdf.pages, start=1):
            palabras = [
                Palabra(texto=p["text"], x=float(p["x0"]), y=float(p["top"]))
                for p in pagina.extract_words()
            ]
            documento.paginas.append(
                PaginaPDF(
                    numero=numero,
                    texto=pagina.extract_text() or "",
                    renglones=_agrupar_en_renglones(palabras),
                )
            )
    return documento


def _con_pdfminer(ruta: Path) -> DocumentoPDF:
    from pdfminer.high_level import extract_pages
    from pdfminer.layout import LTTextContainer

    documento = DocumentoPDF()
    for numero, disposicion in enumerate(extract_pages(str(ruta)), start=1):
        partes: list[str] = []
        palabras: list[Palabra] = []
        alto = float(disposicion.height)
        for elemento in disposicion:
            if not isinstance(elemento, LTTextContainer):
                continue
            texto = elemento.get_text()
            partes.append(texto)
            for renglon in texto.splitlines():
                if renglon.strip():
                    palabras.append(
                        Palabra(
                            texto=renglon.strip(),
                            x=float(elemento.x0),
                            # pdfminer mide desde abajo: se invierte para ordenar.
                            y=alto - float(elemento.y1),
                        )
                    )
        documento.paginas.append(
            PaginaPDF(
                numero=numero,
                texto="".join(partes),
                renglones=_agrupar_en_renglones(palabras),
            )
        )
    return documento


def _con_pypdf2(ruta: Path) -> DocumentoPDF:
    from PyPDF2 import PdfReader

    lector = PdfReader(str(ruta))
    documento = DocumentoPDF()
    for numero, pagina in enumerate(lector.pages, start=1):
        documento.paginas.append(
            PaginaPDF(numero=numero, texto=pagina.extract_text() or "")
        )
    documento.avisos.append(
        "PyPDF2 no informa la posicion del texto: el detalle de la factura puede "
        "leerse incompleto. Instala pymupdf para mejor precision."
    )
    return documento
