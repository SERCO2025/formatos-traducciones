# -*- coding: utf-8 -*-
from shared.fdt import cargar_fdt
from shared.renderer import renderizar_formato
from shared.validators import validar_respuesta


def capturar_respuestas(formato):
    respuestas = {}

    for campo in formato.fields:
        while True:
            respuesta = input(campo.question + ": ")

            valido, mensaje = validar_respuesta(campo, respuesta)

            if valido:
                respuestas[campo.field_id] = respuesta
                break

            print("Error: " + mensaje)

    return respuestas


def main():
    formato = cargar_fdt("formato_prueba.fdt")
    respuestas = capturar_respuestas(formato)

    # Los campos de imagen esperan que respuestas[field_id] contenga
    # la ruta de la imagen seleccionada por el usuario.
    plantilla = input("Ruta de la plantilla: ").strip()
    formato.template.path = plantilla

    salida = renderizar_formato(
        formato,
        respuestas,
        "resultado.jpg",
    )

    print("Resultado generado: %s" % salida)


if __name__ == "__main__":
    main()
