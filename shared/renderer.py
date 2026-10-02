# -*- coding: utf-8 -*-
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


def _cargar_fuente(font_family, font_size, bold=False, italic=False):
    import os
    candidatos = []
    if font_family:
        base, ext = os.path.splitext(font_family)
        if bold and italic:
            candidatos.extend([base + "-BoldItalic" + ext, base + " Bold Italic" + ext])
        elif bold:
            candidatos.extend([base + "-Bold" + ext, base + " Bold" + ext])
        elif italic:
            candidatos.extend([base + "-Italic" + ext, base + " Italic" + ext])
        candidatos.append(font_family)
    for ruta in candidatos:
        try:
            return ImageFont.truetype(ruta, font_size)
        except (OSError, IOError):
            pass
    return ImageFont.load_default()


def _renderizar_imagen(imagen, respuestas, campo):
    respuesta = respuestas.get(campo.field_id)
    if not respuesta:
        return

    ruta = Path(str(respuesta))
    if not ruta.exists():
        raise FileNotFoundError(
            "No se encontró la imagen del campo %s: %s"
            % (campo.field_id, ruta)
        )

    foto = Image.open(ruta).convert("RGB")
    posicion = campo.position
    if posicion.width <= 0 or posicion.height <= 0:
        raise ValueError(
            "El área de imagen del campo %s debe tener ancho y alto mayores que cero."
            % campo.field_id
        )

    escala = max(
        float(posicion.width) / float(foto.width),
        float(posicion.height) / float(foto.height),
    )
    nuevo_ancho = max(1, int(round(foto.width * escala)))
    nuevo_alto = max(1, int(round(foto.height * escala)))
    foto = foto.resize((nuevo_ancho, nuevo_alto), Image.Resampling.LANCZOS)

    izquierda = max(0, (nuevo_ancho - posicion.width) // 2)
    arriba = max(0, (nuevo_alto - posicion.height) // 2)
    foto = foto.crop(
        (izquierda, arriba,
         izquierda + posicion.width, arriba + posicion.height)
    )
    imagen.paste(foto, (posicion.x, posicion.y))


def renderizar_imagen(formato, respuestas):
    plantilla_path = Path(formato.template.path)
    if not plantilla_path.exists():
        raise FileNotFoundError("No se encontró la plantilla: %s" % plantilla_path)

    imagen = Image.open(plantilla_path).convert("RGB")
    if imagen.size != (formato.template.width, formato.template.height):
        raise ValueError(
            "Las dimensiones reales de la plantilla no coinciden con el FDT."
        )

    dibujo = ImageDraw.Draw(imagen)

    for campo in formato.fields:
        if campo.field_type == "image":
            _renderizar_imagen(imagen, respuestas, campo)
            continue

        texto = respuestas.get(campo.field_id, "")
        if texto is None or str(texto) == "":
            continue

        texto = str(texto)
        estilo = campo.text_style
        posicion = campo.position
        fuente = _cargar_fuente(
            estilo.font_family,
            estilo.font_size_px,
            estilo.bold,
            estilo.italic,
        )
        color = (estilo.color.r, estilo.color.g, estilo.color.b)

        if estilo.orientation == "vertical":
            caja = Image.new(
                "RGBA",
                (max(1, posicion.height), max(1, posicion.width)),
                (0, 0, 0, 0),
            )
            caja_draw = ImageDraw.Draw(caja)
            caja_draw.text(
                (0, 0),
                texto,
                fill=color,
                font=fuente,
                anchor="la",
            )
            caja = caja.rotate(90, expand=True)
            imagen.paste(caja, (posicion.x, posicion.y), caja)
            continue

        if estilo.alignment == "center":
            xy = (posicion.x + posicion.width // 2, posicion.y)
            anchor = "ma"
        elif estilo.alignment == "right":
            xy = (posicion.x + posicion.width, posicion.y)
            anchor = "ra"
        else:
            xy = (posicion.x, posicion.y)
            anchor = "la"

        dibujo.text(xy, texto, fill=color, font=fuente, anchor=anchor)

    return imagen


def renderizar_formato(formato, respuestas, salida):
    imagen = renderizar_imagen(formato, respuestas)
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


def construir_nombre_archivo(formato, respuestas):
    configuracion = getattr(formato, "output_naming", None)
    if configuracion is None:
        return "resultado.jpg"

    partes = []
    texto = str(getattr(configuracion, "name_text", "") or "").strip()
    if texto:
        partes.append(texto)

    for field_id in list(getattr(configuracion, "field_ids", []))[:4]:
        if not field_id:
            continue
        valor = respuestas.get(field_id, "")
        if valor is None:
            continue
        valor = str(valor).strip()
        if valor:
            partes.append(valor)

    nombre = "_".join(partes).strip(" ._")
    if not nombre:
        nombre = "resultado"

    nombre = re.sub(r'[\\/:*?"<>|]+', "_", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()
    return nombre + ".jpg"
