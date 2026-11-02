# -*- coding: utf-8 -*-
"""Validaciones comunes para contenedores de avance FTC."""

import os
import re


def validar_entradas_ftc(paquete):
    """Comprueba estructura mínima y unicidad de los nombres del ZIP FTC."""
    entradas = paquete.infolist()
    nombres_lista = [entrada.filename for entrada in entradas]
    nombres = set(nombres_lista)
    if len(nombres) != len(nombres_lista):
        raise ValueError("El avance contiene nombres de archivo duplicados.")
    if "formato.fdt" not in nombres or "captura.json" not in nombres:
        raise ValueError("El archivo no contiene formato.fdt y captura.json; no es un avance FTC válido.")
    return nombres


def normalizar_ruta_imagen_ftc(interno):
    """Valida una ruta de imagen FTC y devuelve su ruta ZIP normalizada."""
    interno = str(interno).replace("\\", "/")
    partes = interno.split("/")
    if (
        len(partes) != 2
        or partes[0] != "imagenes"
        or partes[1] in ("", ".", "..")
        or ":" in partes[1]
        or partes[1].startswith("/")
        or os.path.basename(partes[1]) != partes[1]
    ):
        raise ValueError("El avance contiene una ruta de imagen no válida.")
    return interno


def construir_ruta_imagen_ftc(field_id, extension, imagenes):
    """Genera un nombre interno único aunque varios IDs se saniticen igual."""
    seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", str(field_id)) or "imagen"
    interno = "imagenes/%s%s" % (seguro, extension)
    sufijo = 1
    while interno in imagenes.values():
        interno = "imagenes/%s_%d%s" % (seguro, sufijo, extension)
        sufijo += 1
    return interno
