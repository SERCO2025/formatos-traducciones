# -*- coding: utf-8 -*-
import json
from pathlib import Path

from .models import Formato

FDT_VERSION = 1


def guardar_fdt(formato: Formato, ruta):
    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)

    data = formato.to_dict()
    data["version"] = FDT_VERSION

    with ruta.open("w", encoding="utf-8") as archivo:
        json.dump(data, archivo, ensure_ascii=False, indent=2)


def cargar_fdt(ruta):
    ruta = Path(ruta)

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

    for campo in formato.fields:
        if not campo.field_id.strip():
            errores.append("Existe un campo sin ID.")

        if campo.field_id in ids:
            errores.append("Hay IDs de campo duplicados: %s" % campo.field_id)

        ids.add(campo.field_id)

    if errores:
        raise ValueError("\n".join(errores))

    return True
