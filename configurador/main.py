# -*- coding: utf-8 -*-
"""
Configurador base del proyecto Formatos Traducidos.

Esta etapa conserva una entrada de consola para las pruebas de integracion.
La interfaz grafica 5B se construira sobre este modelo.
"""

from shared.fdt import guardar_fdt, validar_fdt
from shared.models import (
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
    Color,
    Field,
    Formato,
    Position,
    TemplateInfo,
    TextStyle,
)


def crear_formato_prueba():
    formato = Formato(
        name="Formato de prueba",
        template=TemplateInfo(
            path="plantilla.jpg",
            width=1650,
            height=2550,
            dpi=300,
            mode="RGB",
        ),
    )

    formato.agregar_campo(
        Field(
            field_id="nombre",
            question="¿Cuál es el nombre del propietario del vehículo?",
            field_type=FIELD_TYPE_TEXT,
            position=Position(100, 100, 1450, 80),
            text_style=TextStyle(
                font_family="",
                font_size_px=32,
                color=Color(0, 0, 0),
                alignment="left",
            ),
        )
    )

    formato.agregar_campo(
        Field(
            field_id="anio",
            question="¿Cuál es el año del vehículo?",
            field_type=FIELD_TYPE_NUMBER,
            position=Position(100, 220, 300, 80),
            text_style=TextStyle(
                font_family="",
                font_size_px=32,
                color=Color(0, 0, 0),
                alignment="left",
            ),
        )
    )

    formato.agregar_campo(
        Field(
            field_id="placa",
            question="¿Cuál es la placa del vehículo?",
            field_type=FIELD_TYPE_ALPHANUMERIC,
            position=Position(500, 220, 300, 80),
            text_style=TextStyle(
                font_family="",
                font_size_px=32,
                color=Color(0, 0, 0),
                alignment="left",
            ),
        )
    )

    formato.agregar_campo(
        Field(
            field_id="fotografia",
            question="Seleccione la fotografía del propietario.",
            field_type=FIELD_TYPE_IMAGE,
            position=Position(1000, 400, 500, 650),
        )
    )

    validar_fdt(formato)
    return formato


def main():
    formato = crear_formato_prueba()
    guardar_fdt(formato, "formato_prueba.fdt")
    print("FDT de prueba creado correctamente: formato_prueba.fdt")
    for campo in formato.fields:
        print(
            "%d. %s [%s]"
            % (campo.order, campo.question, campo.field_type)
        )


if __name__ == "__main__":
    main()
