# -*- coding: utf-8 -*-
import datetime
import re

from .models import DATE_FORMATS, NUMERIC_MODES


def _configuracion_numerica(campo):
    return getattr(campo, "numeric_config", None)


def _partes_formato_fecha(date_format):
    partes = re.split(r"([/-])", str(date_format or ""))
    return [parte for parte in partes if parte]


def _segmentos_fecha(date_format):
    return [parte for parte in _partes_formato_fecha(date_format) if parte not in ("/", "-")]


def _contiene_anio(date_format):
    return "aa" in _segmentos_fecha(date_format) or "aaaa" in _segmentos_fecha(date_format)


def _analizar_mascara_espaciado(mascara):
    tokens = []
    posiciones = 0
    profundidad = 0
    literal = []

    for caracter in str(mascara or ""):
        if caracter == "(":
            if profundidad == 0:
                if literal:
                    return None, 0, "El texto literal debe estar dentro de paréntesis."
            else:
                literal.append("(")
            profundidad += 1
            continue

        if caracter == ")":
            if profundidad == 0:
                return None, 0, "La máscara contiene un paréntesis de cierre sin apertura."
            profundidad -= 1
            if profundidad == 0:
                tokens.append(("literal", "".join(literal)))
                literal = []
            else:
                literal.append(")")
            continue

        if profundidad:
            literal.append(caracter)
        elif caracter == "#":
            tokens.append(("digit", ""))
            posiciones += 1
        else:
            return None, 0, "Fuera de paréntesis solo se permite el símbolo #."

    if profundidad:
        return None, 0, "La máscara contiene paréntesis sin cerrar."
    if posiciones <= 0:
        return None, 0, "La máscara debe contener al menos una posición #."

    return tokens, posiciones, ""


def validar_configuracion_numerica(config):
    if config is None:
        return True, ""

    modo = str(getattr(config, "mode", "number") or "number")
    if modo not in NUMERIC_MODES:
        return False, "El modo numérico configurado no es válido."

    if modo == "limit":
        maximo = str(getattr(config, "max_value", "") or "")
        if not maximo.isdigit():
            return False, "El límite máximo debe contener únicamente números."
        return True, ""

    if modo == "date":
        date_format = str(getattr(config, "date_format", "") or "")
        if date_format not in DATE_FORMATS:
            return False, "El formato de fecha configurado no es válido."
        if _contiene_anio(date_format):
            minimo = str(getattr(config, "min_year", "") or "")
            if not minimo.isdigit():
                return False, "El año mínimo es obligatorio y debe contener únicamente números."
        return True, ""

    if modo == "spacing":
        _, _, error = _analizar_mascara_espaciado(
            getattr(config, "spacing_mask", "")
        )
        if error:
            return False, error

    return True, ""


def _separar_respuesta_fecha(respuesta, date_format):
    partes_formato = _partes_formato_fecha(date_format)
    separadores = [parte for parte in partes_formato if parte in ("/", "-")]
    patrones = [parte for parte in partes_formato if parte not in ("/", "-")]
    texto = str(respuesta or "")

    if any(not (caracter.isdigit() or caracter in "/-") for caracter in texto):
        return None

    separadores_usados = [caracter for caracter in texto if caracter in "/-"]
    if separadores_usados:
        if not separadores or any(caracter != separadores[0] for caracter in separadores_usados):
            return None
        segmentos = texto.split(separadores[0])
        if len(segmentos) > len(patrones):
            return None
    else:
        digitos = texto
        segmentos = []
        cursor = 0
        for patron in patrones:
            segmentos.append(digitos[cursor:cursor + len(patron)])
            cursor += len(segmentos[-1])
        if cursor < len(digitos):
            return None

    if any(len(segmento) > len(patron) for segmento, patron in zip(segmentos, patrones)):
        return None
    segmentos.extend([""] * (len(patrones) - len(segmentos)))
    return list(zip(patrones, segmentos)), separadores


def normalizar_fecha_capturada(respuesta, date_format, confirmar=False):
    """Aplica separadores del formato y completa dd/mm de un solo dígito al confirmar."""
    analisis = _separar_respuesta_fecha(respuesta, date_format)
    if analisis is None:
        return ""
    segmentos, separadores = analisis

    resultado = []
    ultimo_segmento = max(
        (indice for indice, (_, valor) in enumerate(segmentos) if valor),
        default=-1,
    )
    for indice, (patron, valor) in enumerate(segmentos):
        if indice > ultimo_segmento:
            break
        if indice:
            resultado.append(separadores[indice - 1])
        if confirmar and patron in ("dd", "mm") and len(valor) == 1:
            valor = "0" + valor
        resultado.append(valor)
    return "".join(resultado)


def _extraer_segmentos_fecha(respuesta, date_format):
    analisis = _separar_respuesta_fecha(respuesta, date_format)
    if analisis is None:
        return None
    return analisis[0]


def _anio_completo(anio, hoy):
    if len(anio) == 4:
        return int(anio)
    valor = int(anio)
    siglo_actual = (hoy.year // 100) * 100
    candidatos = (
        siglo_actual - 100 + valor,
        siglo_actual + valor,
        siglo_actual + 100 + valor,
    )
    return min(candidatos, key=lambda candidato: abs(candidato - hoy.year))


def _validar_fecha(respuesta, config, hoy=None):
    date_format = str(config.date_format)
    segmentos = _extraer_segmentos_fecha(respuesta, date_format)
    if segmentos is None:
        return False, "La fecha contiene caracteres o separadores no válidos."

    if any(not valor.isdigit() for _, valor in segmentos):
        return False, "La fecha debe contener únicamente números y los separadores del formato."

    if any(not valor for _, valor in segmentos):
        return False, "Complete todos los segmentos del formato de fecha."

    for patron, valor in segmentos:
        longitud_valida = (
            len(valor) in (1, 2) if patron in ("dd", "mm")
            else len(valor) == len(patron)
        )
        if not longitud_valida:
            return False, "El segmento %s debe contener %d dígito(s)." % (
                patron, len(patron)
            )
        if patron == "dd" and (int(valor) < 1 or int(valor) > 31):
            return False, "El día debe estar entre 01 y 31."
        if patron == "mm" and (int(valor) < 1 or int(valor) > 12):
            return False, "El mes debe estar entre 01 y 12."
        if patron == "aaaa" and len(valor) == 4:
            if int(valor) < int(config.min_year):
                return False, "El año no puede ser anterior al año mínimo configurado."
        if patron == "aa" and len(valor) == 2 and config.min_year:
            referencia = hoy or datetime.date.today()
            if _anio_completo(valor, referencia) < int(config.min_year):
                return False, "El año no puede ser anterior al año mínimo configurado."

    valores = {patron: valor for patron, valor in segmentos}
    formato_completo = all(valores.get(patron, "") for patron, _ in segmentos)
    if formato_completo and "dd" in valores and "mm" in valores and ("aaaa" in valores or "aa" in valores):
        referencia = hoy or datetime.date.today()
        anio_texto = valores.get("aaaa") or valores.get("aa")
        anio = _anio_completo(anio_texto, referencia) if len(anio_texto) == 2 else int(anio_texto)
        try:
            fecha = datetime.date(anio, int(valores["mm"]), int(valores["dd"]))
        except ValueError:
            return False, "La fecha indicada no existe."
        if config.past_only and fecha >= referencia:
            return False, "Solo se permiten fechas anteriores a la fecha actual."

    return True, ""


def formatear_espaciado(respuesta, mascara):
    """Devuelve la representación visual; no modifica el dato numérico almacenado."""
    digitos = "".join(caracter for caracter in str(respuesta or "") if caracter.isdigit())
    if not digitos:
        return ""

    tokens, _, error = _analizar_mascara_espaciado(mascara)
    if error:
        return ""

    resultado = []
    indice = 0
    for tipo, valor in tokens:
        if tipo == "digit":
            resultado.append(digitos[indice] if indice < len(digitos) else " ")
            indice += 1
        else:
            resultado.append(valor)
    return "".join(resultado)


def formatear_respuesta_campo(campo, respuesta):
    """Prepara la representación visible sin alterar el valor almacenado."""
    if respuesta is None:
        return ""
    texto = str(respuesta)
    if not texto or campo.field_type != "number":
        return texto

    configuracion = getattr(campo, "numeric_config", None)
    modo = str(getattr(configuracion, "mode", "number") or "number")
    if modo == "spacing":
        return formatear_espaciado(
            texto,
            getattr(configuracion, "spacing_mask", "####"),
        )
    if modo == "date":
        normalizado = normalizar_fecha_capturada(
            texto,
            getattr(configuracion, "date_format", "dd/mm/aaaa"),
            confirmar=False,
        )
        return normalizado if normalizado else texto
    return texto


def indicacion_captura_numerica(campo):
    """Devuelve solo la instrucción necesaria para capturar un campo numérico."""
    if campo.field_type != "number":
        return ""
    configuracion = getattr(campo, "numeric_config", None)
    modo = str(getattr(configuracion, "mode", "number") or "number")
    if modo == "limit":
        return "Máximo permitido: %s." % getattr(configuracion, "max_value", "")
    if modo == "date":
        formato = str(getattr(configuracion, "date_format", "dd/mm/aaaa"))
        partes = re.split(r"([/-])", formato)
        tiene_anio = "aa" in partes or "aaaa" in partes
        texto = "Formato esperado: %s." % formato
        if tiene_anio:
            texto += " Año mínimo: %s." % getattr(configuracion, "min_year", "")
        if (
            getattr(configuracion, "past_only", False)
            and "dd" in partes and "mm" in partes and tiene_anio
        ):
            texto += " Solo se permiten fechas anteriores a hoy."
        return texto
    if modo == "spacing":
        texto = "Estructura: %s." % getattr(configuracion, "spacing_mask", "####")
        if getattr(configuracion, "spacing_required", False):
            texto += " Complete todas las posiciones numéricas."
        return texto
    return ""


def validar_respuesta(campo, respuesta, hoy=None):
    respuesta = "" if respuesta is None else str(respuesta)

    if campo.required and not respuesta.strip():
        return False, "Este campo es obligatorio."

    if not respuesta.strip():
        return True, ""

    if not campo.validation.numeric_only:
        return True, ""

    config = _configuracion_numerica(campo)
    modo = str(getattr(config, "mode", "number") or "number")

    if modo == "number":
        if any(caracter.isalpha() for caracter in respuesta):
            return False, "Este campo permite números, espacios y símbolos, pero no letras."
        return True, ""

    valido, mensaje = validar_configuracion_numerica(config)
    if not valido:
        return False, mensaje

    if modo == "limit":
        if not respuesta.isdigit():
            return False, "Este campo permite únicamente números."
        if int(respuesta) > int(config.max_value):
            return False, "La cantidad no puede superar el límite de %s." % config.max_value
        return True, ""

    if modo == "date":
        if any(not (caracter.isdigit() or caracter in "/-") for caracter in respuesta):
            return False, "La fecha solo permite números y los separadores configurados."
        return _validar_fecha(respuesta, config, hoy=hoy)

    if modo == "spacing":
        if not respuesta.isdigit():
            return False, "Este campo permite únicamente números."
        _, posiciones, _ = _analizar_mascara_espaciado(config.spacing_mask)
        if len(respuesta) > posiciones:
            return False, "La respuesta supera las %s posiciones numéricas disponibles." % posiciones
        if config.spacing_required and len(respuesta) != posiciones:
            return False, "Debe completar las %s posiciones numéricas." % posiciones
        return True, ""

    return False, "El modo numérico configurado no es válido."


def validar_todas_las_respuestas(formato, respuestas, hoy=None):
    errores = {}

    for campo in formato.fields:
        respuesta = respuestas.get(campo.field_id, "")
        valido, mensaje = validar_respuesta(campo, respuesta, hoy=hoy)

        if not valido:
            errores[campo.field_id] = mensaje

    return errores
