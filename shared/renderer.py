# -*- coding: utf-8 -*-
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def _cargar_fuente(font_family, font_size):
    if font_family:
        try:
            return ImageFont.truetype(font_family, font_size)
        except (OSError, IOError):
            pass

    return ImageFont.load_default()


def renderizar_formato(formato, respuestas, salida):
    plantilla_path = Path(formato.template.path)

    if not plantilla_path.exists():
        raise FileNotFoundError(
            "No se encontró la plantilla: %s" % plantilla_path
        )

    imagen = Image.open(plantilla_path).convert("RGB")

    if imagen.size != (
        formato.template.width,
        formato.template.height,
    ):
        raise ValueError(
            "Las dimensiones reales de la plantilla no coinciden con el FDT."
        )

    dibujo = ImageDraw.Draw(imagen)

    for campo in formato.fields:
        texto = respuestas.get(campo.field_id, "")

        if texto is None or str(texto) == "":
            continue

        texto = str(texto)
        estilo = campo.text_style
        posicion = campo.position

        fuente = _cargar_fuente(
            estilo.font_family,
            estilo.font_size_px,
        )

        color = (
            estilo.color.r,
            estilo.color.g,
            estilo.color.b,
        )

        if estilo.alignment == "center":
            xy = (posicion.x + posicion.width // 2, posicion.y)
            anchor = "ma"
        elif estilo.alignment == "right":
            xy = (posicion.x + posicion.width, posicion.y)
            anchor = "ra"
        else:
            xy = (posicion.x, posicion.y)
            anchor = "la"

        dibujo.text(
            xy,
            texto,
            fill=color,
            font=fuente,
            anchor=anchor,
        )

    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    imagen.save(
        salida,
        format="JPEG",
        quality=100,
        subsampling=0,
        dpi=(formato.template.dpi, formato.template.dpi),
    )

    return salida
