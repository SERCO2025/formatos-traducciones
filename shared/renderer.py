# -*- coding: utf-8 -*-
from pathlib import Path
import re

from PIL import Image, ImageDraw, ImageFont


def _normalizar_nombre_fuente(valor):
    import os
    texto = str(valor or "").strip().lower()
    texto = os.path.basename(texto)
    texto = os.path.splitext(texto)[0]
    texto = re.sub(r"\s*\((true ?type|opentype|truetype)\)\s*$", "", texto)
    texto = re.sub(r"\s+(bold\s+italic|italic|bold|negrita|cursiva)\s*$", "", texto)
    return texto.strip()


def _buscar_fuente_instalada(font_family):
    import os

    solicitado = str(font_family or "").strip()
    if not solicitado:
        return None

    if os.path.isfile(solicitado):
        return solicitado

    objetivo = _normalizar_nombre_fuente(solicitado)
    if not objetivo:
        return None

    candidatos = []

    # Registro de Windows: primero por nombre de familia y después por archivo.
    try:
        import winreg
        claves = (
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
        )
        for hive, subkey in claves:
            try:
                key = winreg.OpenKey(hive, subkey)
            except OSError:
                continue
            try:
                for i in range(winreg.QueryInfoKey(key)[1]):
                    try:
                        nombre, archivo, _ = winreg.EnumValue(key, i)
                    except OSError:
                        continue

                    archivo = os.path.expandvars(str(archivo))
                    if not os.path.isabs(archivo):
                        archivo = os.path.join(
                            os.environ.get("WINDIR", r"C:\Windows"),
                            "Fonts",
                            archivo,
                        )
                    archivo = os.path.normpath(archivo)
                    if not os.path.isfile(archivo):
                        continue

                    nombre_normalizado = _normalizar_nombre_fuente(nombre)
                    archivo_normalizado = _normalizar_nombre_fuente(archivo)
                    if objetivo == nombre_normalizado or objetivo == archivo_normalizado:
                        return archivo

                    candidatos.append(archivo)
            finally:
                winreg.CloseKey(key)
    except Exception:
        pass

    # Último intento: recorrer las carpetas estándar de fuentes de Windows.
    carpetas = [
        os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
    ]
    for carpeta in carpetas:
        if not carpeta or not os.path.isdir(carpeta):
            continue
        try:
            for raiz, _, archivos in os.walk(carpeta):
                for archivo in archivos:
                    ruta = os.path.join(raiz, archivo)
                    if _normalizar_nombre_fuente(ruta) == objetivo:
                        return ruta
        except OSError:
            pass

    return candidatos[0] if len(candidatos) == 1 else None


def _cargar_fuente(font_family, font_size, bold=False, italic=False):
    import os

    try:
        font_size = int(font_size)
    except (TypeError, ValueError):
        font_size = 24
    font_size = max(1, font_size)

    solicitado = str(font_family or "").strip()
    candidatos = []

    # Los FDT nuevos contienen la ruta física de la fuente extraída.
    if solicitado and os.path.isfile(solicitado):
        candidatos.append(solicitado)

    fuente_resuelta = _buscar_fuente_instalada(solicitado)
    if fuente_resuelta and fuente_resuelta not in candidatos:
        candidatos.append(fuente_resuelta)

    # Compatibilidad con FDT antiguos que almacenaban directamente una ruta
    # o el nombre de familia.
    if solicitado:
        base, ext = os.path.splitext(solicitado)
        variantes = []
        if ext:
            if bold and italic:
                variantes.extend([base + "-BoldItalic" + ext, base + " Bold Italic" + ext])
            elif bold:
                variantes.extend([base + "-Bold" + ext, base + " Bold" + ext])
            elif italic:
                variantes.extend([base + "-Italic" + ext, base + " Italic" + ext])
        variantes.append(solicitado)
        for variante in variantes:
            if variante not in candidatos:
                candidatos.append(variante)

    for ruta in candidatos:
        try:
            fuente = ImageFont.truetype(ruta, font_size)

            # Pillow recibe el tamaño de una fuente en píxeles, pero ese
            # parámetro corresponde al tamaño tipográfico interno, no a la
            # altura visible de las letras. Para que el valor configurado en
            # el FDT sea una medida visual coherente en píxeles, calibramos
            # contra un conjunto representativo de glifos.
            muestra = "HgjÁy"
            caja = fuente.getbbox(muestra)
            alto_visible = max(1, caja[3] - caja[1])
            if alto_visible != font_size:
                tamano_calibrado = max(
                    1,
                    int(round(font_size * float(font_size) / float(alto_visible)))
                )
                fuente_calibrada = ImageFont.truetype(ruta, tamano_calibrado)
                caja_calibrada = fuente_calibrada.getbbox(muestra)
                alto_calibrado = max(1, caja_calibrada[3] - caja_calibrada[1])

                # Una segunda corrección elimina el pequeño error de redondeo
                # que puede quedar en tamaños pequeños.
                if alto_calibrado != font_size:
                    tamano_calibrado = max(
                        1,
                        int(round(tamano_calibrado * float(font_size) / float(alto_calibrado)))
                    )
                    fuente_calibrada = ImageFont.truetype(ruta, tamano_calibrado)

                return fuente_calibrada

            return fuente
        except (OSError, IOError, ValueError):
            continue

    raise FileNotFoundError(
        "No se pudo cargar la tipografía '%s'. "
        "El formato conserva el tamaño de %d px, pero la fuente no está disponible."
        % (solicitado or "(sin fuente)", font_size)
    )

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
            anchor = "mt"
        elif estilo.alignment == "right":
            xy = (posicion.x + posicion.width, posicion.y)
            anchor = "rt"
        else:
            xy = (posicion.x, posicion.y)
            anchor = "lt"

        if "\n" in texto:
            dibujo.multiline_text(
                xy,
                texto,
                fill=color,
                font=fuente,
                anchor=anchor,
                align="center" if estilo.alignment == "center" else (
                    "right" if estilo.alignment == "right" else "left"
                ),
            )
        else:
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
