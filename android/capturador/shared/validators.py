# -*- coding: utf-8 -*-


def validar_respuesta(campo, respuesta):
    respuesta = "" if respuesta is None else str(respuesta)

    if campo.required and not respuesta.strip():
        return False, "Este campo es obligatorio."

    # Los campos numéricos aceptan dígitos, espacios y símbolos (por ejemplo:
    # 123-45, +52 664, 10/12/2026). Se rechazan únicamente las letras.
    if campo.validation.numeric_only and respuesta.strip():
        if any(caracter.isalpha() for caracter in respuesta):
            return False, "Este campo permite números, espacios y símbolos, pero no letras."

    # Los campos alfanuméricos y de texto aceptan letras, números, espacios
    # y símbolos sin restricciones adicionales.

    return True, ""


def validar_todas_las_respuestas(formato, respuestas):
    errores = {}

    for campo in formato.fields:
        respuesta = respuestas.get(campo.field_id, "")
        valido, mensaje = validar_respuesta(campo, respuesta)

        if not valido:
            errores[campo.field_id] = mensaje

    return errores
