# -*- coding: utf-8 -*-
"""Operaciones geométricas de alineación y distribución para el configurador.

Las guías son referencias visuales temporales. Este módulo solo modifica las
coordenadas reales de los campos; no almacena ni serializa líneas guía.
"""


def alinear_campos(campos, orientacion_guia, posicion_guia, modo):
    """Alinea campos sobre una guía horizontal o vertical.

    orientacion_guia:
        "horizontal": la guía fija Y; los modos son top, center y bottom.
        "vertical": la guía fija X; los modos son left, center y right.
    """
    if not campos or orientacion_guia not in ("horizontal", "vertical"):
        return False

    if orientacion_guia == "horizontal":
        atributos = {
            "top": ("y", 0),
            "center": ("y", 0.5),
            "bottom": ("y", 1),
        }
        if modo not in atributos:
            return False
        atributo, proporcion = atributos[modo]
        for campo in campos:
            posicion = campo.position
            if proporcion == 0:
                nueva = posicion_guia
            elif proporcion == 0.5:
                nueva = posicion_guia - posicion.height / 2.0
            else:
                nueva = posicion_guia - posicion.height
            setattr(posicion, atributo, int(round(nueva)))
        return True

    atributos = {
        "left": ("x", 0),
        "center": ("x", 0.5),
        "right": ("x", 1),
    }
    if modo not in atributos:
        return False
    atributo, proporcion = atributos[modo]
    for campo in campos:
        posicion = campo.position
        if proporcion == 0:
            nueva = posicion_guia
        elif proporcion == 0.5:
            nueva = posicion_guia - posicion.width / 2.0
        else:
            nueva = posicion_guia - posicion.width
        setattr(posicion, atributo, int(round(nueva)))
    return True


def distribuir_campos(campos, orientacion_guia):
    """Distribuye campos con espacios libres iguales en el eje perpendicular.

    Una guía horizontal distribuye en X; una guía vertical distribuye en Y.
    Se conservan fijos los extremos del conjunto. La dimensión de cada campo
    se descuenta antes de calcular el espacio libre entre sus bordes.
    """
    if len(campos) < 2 or orientacion_guia not in ("horizontal", "vertical"):
        return False

    atributo = "x" if orientacion_guia == "horizontal" else "y"
    dimension = "width" if orientacion_guia == "horizontal" else "height"
    ordenados = sorted(
        campos,
        key=lambda campo: (
            getattr(campo.position, atributo),
            getattr(campo, "order", 0),
        ),
    )
    primero = ordenados[0].position
    ultimo = ordenados[-1].position
    inicio = getattr(primero, atributo)
    fin = getattr(ultimo, atributo) + getattr(ultimo, dimension)
    longitud_campos = sum(getattr(campo.position, dimension) for campo in ordenados)
    espacio_libre = fin - inicio - longitud_campos
    if espacio_libre < 0:
        return False

    separacion = espacio_libre / float(len(ordenados) - 1)
    cursor = float(inicio)
    for indice, campo in enumerate(ordenados):
        posicion = campo.position
        setattr(posicion, atributo, int(round(cursor)))
        cursor += getattr(posicion, dimension)
        if indice < len(ordenados) - 1:
            cursor += separacion
    return True
