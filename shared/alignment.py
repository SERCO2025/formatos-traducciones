# -*- coding: utf-8 -*-
"""Operaciones geométricas de alineación y distribución para el configurador.

Las guías son referencias visuales temporales. Este módulo solo modifica las
coordenadas reales de los campos; no almacena ni serializa líneas guía.
"""

DPI_REGLA = 300


def pixeles_a_pulgadas(pixeles):
    """Convierte píxeles del documento a pulgadas usando la escala fija de 300 DPI."""
    return float(pixeles) / float(DPI_REGLA)


def pulgadas_a_pixeles(pulgadas):
    """Convierte pulgadas a píxeles del documento usando la escala fija de 300 DPI."""
    return int(round(float(pulgadas) * DPI_REGLA))


def alinear_campos(campos, orientacion_guia, posicion_guia, modo):
    """Alinea campos sobre una guía horizontal o vertical.

    Las coordenadas del modelo usan origen en la esquina superior izquierda:
    X crece hacia la derecha y Y crece hacia abajo.

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
    Se conservan fijos los bordes exteriores del conjunto. La dimensión de
    cada campo se descuenta antes de calcular el espacio libre entre bordes.

    Devuelve False si no hay al menos dos campos, la orientación no es válida
    o el conjunto no cabe en el intervalo sin superposición.
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

    # No se presupone que el campo que comienza más a la derecha sea el que
    # tenga el borde final máximo: un campo anterior podría ser más ancho.
    inicio = min(getattr(campo.position, atributo) for campo in ordenados)
    fin = max(
        getattr(campo.position, atributo) + getattr(campo.position, dimension)
        for campo in ordenados
    )
    longitud_campos = sum(
        getattr(campo.position, dimension) for campo in ordenados
    )
    espacio_libre = fin - inicio - longitud_campos
    if espacio_libre < 0:
        return False

    intervalos = len(ordenados) - 1
    separacion_base, sobrante = divmod(int(espacio_libre), intervalos)
    cursor = int(inicio)
    for indice, campo in enumerate(ordenados):
        posicion = campo.position
        setattr(posicion, atributo, cursor)
        cursor += getattr(posicion, dimension)
        if indice < intervalos:
            # Repartir los píxeles sobrantes entre los primeros intervalos.
            # Así los espacios difieren como máximo 1 px y el último borde
            # coincide exactamente con el extremo exterior original.
            cursor += separacion_base + (1 if indice < sobrante else 0)
    return True
