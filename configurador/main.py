# -*- coding: utf-8 -*-
from shared.fdt import guardar_fdt, validar_fdt
from shared.models import (
    Color,
    Field,
    Formato,
    Position,
    TemplateInfo,
    TextStyle,
    Validation,
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
        fields=[
            Field(
                field_id="nombre",
                question="Nombre completo",
                position=Position(100, 100, 1450, 80),
                text_style=TextStyle(
                    font_family="",
                    font_size_px=32,
                    color=Color(0, 0, 0),
                    alignment="left",
                ),
            ),
            Field(
                field_id="numero",
                question="Número",
                validation=Validation(numeric_only=True),
                position=Position(100, 220, 1450, 80),
                text_style=TextStyle(
                    font_family="",
                    font_size_px=32,
                    color=Color(0, 0, 0),
                    alignment="left",
                ),
            ),
        ],
    )

    validar_fdt(formato)
    return formato


def main():
    formato = crear_formato_prueba()
    guardar_fdt(formato, "formato_prueba.fdt")
    print("FDT creado correctamente: formato_prueba.fdt")


if __name__ == "__main__":
    main()
