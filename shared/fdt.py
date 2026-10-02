# -*- coding: utf-8 -*-
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path

from .models import (
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
    Formato,
)

FDT_VERSION = 3
FIELD_TYPES = {
    FIELD_TYPE_TEXT,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
}

_EXTRACTED_DIRS = []


def _is_zip_fdt(ruta):
    try:
        with open(ruta, "rb") as archivo:
            return archivo.read(4) == b"PK\x03\x04"
    except (OSError, IOError):
        return False


def guardar_fdt(formato: Formato, ruta):
    """
    Guarda un FDT autocontenido como ZIP con extension .fdt.
    Incluye el JSON del formato, la plantilla y el directorio resources/
    para que el formato no dependa de archivos externos.
    """
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    formato.ordenar_campos()
    data = formato.to_dict()
    data["version"] = FDT_VERSION

    template_path = Path(formato.template.path)
    if not template_path.exists() or not template_path.is_file():
        raise FileNotFoundError(
            "No se encontró la imagen de plantilla: %s" % template_path
        )

    # La ruta almacenada dentro del FDT es interna al contenedor.
    data["template"]["path"] = "template/" + template_path.name

    temp_path = ruta.with_suffix(ruta.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    try:
        with zipfile.ZipFile(
            str(temp_path), "w", compression=zipfile.ZIP_DEFLATED
        ) as paquete:
            paquete.writestr(
                "format.json",
                json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
            )
            paquete.write(
                str(template_path),
                "template/" + template_path.name,
            )

            # Si existe una carpeta de recursos con el mismo nombre base
            # de la plantilla, se integra completa al FDT.
            recursos = template_path.parent / (template_path.stem + "_assets")
            if recursos.is_dir():
                for archivo in recursos.rglob("*"):
                    if archivo.is_file():
                        relativo = archivo.relative_to(recursos).as_posix()
                        paquete.write(str(archivo), "resources/" + relativo)

            paquete.writestr(
                "MANIFEST.txt",
                (
                    "Formatos Traducidos FDT\n"
                    "Contenedor autocontenido.\n"
                    "format.json = configuración del formato\n"
                    "template/ = imagen de plantilla\n"
                    "resources/ = archivos adicionales del formato\n"
                ).encode("utf-8"),
            )

        if ruta.exists():
            ruta.unlink()
        temp_path.replace(ruta)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def cargar_fdt(ruta):
    ruta = Path(ruta)

    if _is_zip_fdt(ruta):
        directorio = Path(tempfile.mkdtemp(prefix="formatos_traducidos_fdt_"))
        _EXTRACTED_DIRS.append(str(directorio))
        try:
            with zipfile.ZipFile(str(ruta), "r") as paquete:
                nombres = paquete.namelist()
                if "format.json" not in nombres:
                    raise ValueError("El FDT no contiene format.json.")

                paquete.extractall(str(directorio))

            with (directorio / "format.json").open("r", encoding="utf-8") as archivo:
                data = json.load(archivo)

            template_dir = directorio / "template"
            imagenes = [
                p for p in template_dir.iterdir()
                if p.is_file()
            ] if template_dir.exists() else []

            if not imagenes:
                raise ValueError("El FDT no contiene la imagen de plantilla.")

            plantilla = imagenes[0]
            data.setdefault("template", {})["path"] = str(plantilla)
            formato = Formato.from_dict(data)
            validar_fdt(formato)
            return formato
        except Exception:
            shutil.rmtree(str(directorio), ignore_errors=True)
            if str(directorio) in _EXTRACTED_DIRS:
                _EXTRACTED_DIRS.remove(str(directorio))
            raise

    # Compatibilidad con los FDT JSON anteriores.
    with ruta.open("r", encoding="utf-8") as archivo:
        data = json.load(archivo)

    formato = Formato.from_dict(data)
    validar_fdt(formato)
    return formato


def validar_fdt(formato: Formato):
    errores = []

    if not formato.name.strip():
        errores.append("El formato debe tener nombre.")

    if formato.template.width <= 0 or formato.template.height <= 0:
        errores.append("Las dimensiones de la plantilla deben ser mayores que cero.")

    if formato.template.dpi <= 0:
        errores.append("El DPI de la plantilla debe ser mayor que cero.")

    if formato.template.mode.upper() != "RGB":
        errores.append("La plantilla debe trabajar en modo RGB.")

    ids = set()
    ordenes = set()

    for campo in formato.fields:
        if not campo.field_id.strip():
            errores.append("Existe un campo sin ID.")

        if campo.field_id in ids:
            errores.append("Hay IDs de campo duplicados: %s" % campo.field_id)
        ids.add(campo.field_id)

        if campo.field_type not in FIELD_TYPES:
            errores.append(
                "Tipo de campo no válido en %s: %s"
                % (campo.field_id or "(sin ID)", campo.field_type)
            )

        if campo.order <= 0:
            errores.append(
                "El campo %s debe tener un orden de pregunta mayor que cero."
                % (campo.field_id or "(sin ID)")
            )
        elif campo.order in ordenes:
            errores.append(
                "Hay órdenes de pregunta duplicados: %s" % campo.order
            )
        ordenes.add(campo.order)

        if campo.position.width < 0 or campo.position.height < 0:
            errores.append(
                "El área del campo %s no puede tener dimensiones negativas."
                % (campo.field_id or "(sin ID)")
            )

        if campo.field_type == FIELD_TYPE_NUMBER:
            campo.validation.numeric_only = True
            campo.validation.alphanumeric_only = False
        elif campo.field_type == FIELD_TYPE_ALPHANUMERIC:
            campo.validation.numeric_only = False
            campo.validation.alphanumeric_only = True
        else:
            campo.validation.numeric_only = False
            campo.validation.alphanumeric_only = False

    if errores:
        raise ValueError("\n".join(errores))

    return True
