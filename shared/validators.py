# -*- coding: utf-8 -*-


def validar_respuesta(campo, respuesta):
    respuesta = "" if respuesta is None else str(respuesta)

    if campo.required and not respuesta.strip():
        return False, "Este campo es obligatorio."

    if campo.validation.numeric_only and respuesta.strip():
        if not respuesta.strip().isdigit():
            return False, "Este campo solo permite números."

    return True, ""


def validar_todas_las_respuestas(formato, respuestas):
    errores = {}

    for campo in formato.fields:
        respuesta = respuestas.get(campo.field_id, "")
        valido, mensaje = validar_respuesta(campo, respuesta)

        if not valido:
            errores[campo.field_id] = mensaje

    return errores
