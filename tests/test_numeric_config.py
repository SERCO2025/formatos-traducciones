# -*- coding: utf-8 -*-
import unittest

from shared.models import (
    DATE_FORMATS,
    NUMERIC_MODES,
    FIELD_TYPE_NUMBER,
    Field,
    NumericConfig,
    Validation,
    Position,
    TemplateInfo,
    Formato,
)
from shared.fdt import validar_fdt
from android.capturador.shared.fdt import validar_fdt as validar_fdt_android
from shared.validators import (
    formatear_respuesta_campo,
    formatear_espaciado,
    normalizar_fecha_capturada,
    validar_configuracion_numerica,
    validar_respuesta,
)
from android.capturador.shared.validators import (
    validar_respuesta as validar_respuesta_android,
)
from android.capturador.shared.models import (
    Field as AndroidField,
    NumericConfig as AndroidNumericConfig,
    Validation as AndroidValidation,
    Position as AndroidPosition,
    TemplateInfo as AndroidTemplateInfo,
    Formato as AndroidFormato,
)



class NumericValidationTests(unittest.TestCase):
    def crear_campo(self, config, required=False):
        return Field(
            field_id="dato",
            question="Dato",
            field_type=FIELD_TYPE_NUMBER,
            required=required,
            validation=Validation(numeric_only=True),
            numeric_config=config,
        )

    def test_number_mode_keeps_legacy_symbols_and_spaces_behavior(self):
        campo = self.crear_campo(NumericConfig(mode="number"))
        self.assertEqual(validar_respuesta(campo, "+52 664-123"), (True, ""))
        self.assertFalse(validar_respuesta(campo, "ABC")[0])

    def test_limit_mode_checks_digits_and_maximum(self):
        campo = self.crear_campo(NumericConfig(mode="limit", max_value="500"))
        self.assertTrue(validar_respuesta(campo, "500")[0])
        self.assertFalse(validar_respuesta(campo, "501")[0])
        self.assertFalse(validar_respuesta(campo, "50A")[0])

    def test_limit_configuration_must_have_numeric_maximum(self):
        config = NumericConfig(mode="limit", max_value="")
        self.assertFalse(validar_configuracion_numerica(config)[0])

    def test_date_configuration_requires_minimum_year_when_year_is_present(self):
        config = NumericConfig(mode="date", date_format="dd/mm/aaaa", min_year="")
        self.assertFalse(validar_configuracion_numerica(config)[0])
        config.min_year = "1900"
        self.assertTrue(validar_configuracion_numerica(config)[0])

    def test_date_checks_calendar_ranges_leap_year_and_minimum_year(self):
        campo = self.crear_campo(NumericConfig(
            mode="date", date_format="dd/mm/aaaa", min_year="1900"
        ))
        self.assertTrue(validar_respuesta(campo, "29/02/2024")[0])
        self.assertFalse(validar_respuesta(campo, "29/02/2023")[0])
        self.assertFalse(validar_respuesta(campo, "31/04/2024")[0])
        self.assertFalse(validar_respuesta(campo, "01/01/1899")[0])

    def test_past_only_uses_device_date_without_rewriting_two_digit_year(self):
        campo = self.crear_campo(NumericConfig(
            mode="date", date_format="dd/mm/aa",
            min_year="1900", past_only=True,
        ))
        import datetime
        hoy = datetime.date(2026, 6, 15)
        self.assertTrue(validar_respuesta(campo, "01/01/99", hoy=hoy)[0])
        self.assertFalse(validar_respuesta(campo, "16/06/26", hoy=hoy)[0])
        self.assertFalse(validar_respuesta(campo, "01/01/27", hoy=hoy)[0])
        self.assertFalse(validar_respuesta(campo, "15/06/26", hoy=hoy)[0])

    def test_partial_date_fields_do_not_get_past_date_comparison(self):
        campo = self.crear_campo(NumericConfig(
            mode="date", date_format="aaaa", min_year="1900", past_only=True
        ))
        self.assertTrue(validar_respuesta(campo, "2026")[0])

    def test_date_normalization_pads_single_digit_day_and_month_only_on_confirm(self):
        self.assertEqual(
            normalizar_fecha_capturada("1/2/2026", "dd/mm/aaaa", confirmar=False),
            "1/2/2026",
        )
        self.assertEqual(
            normalizar_fecha_capturada("1/2/2026", "dd/mm/aaaa", confirmar=True),
            "01/02/2026",
        )
        self.assertEqual(
            normalizar_fecha_capturada("26", "aa", confirmar=True),
            "26",
        )
        self.assertEqual(
            normalizar_fecha_capturada("0102", "dd/mm/aaaa", confirmar=True),
            "01/02",
        )

    def test_spacing_mask_renders_literals_and_nested_parentheses(self):
        self.assertEqual(
            formatear_espaciado("12345678", "####(-)####"),
            "1234-5678",
        )
        self.assertEqual(
            formatear_espaciado("12345678", "####(( ))####"),
            "1234( )5678",
        )
        self.assertEqual(
            formatear_espaciado("12345", "####(-)####"),
            "1234-5   ",
        )
        self.assertEqual(formatear_espaciado("", "####(-)####"), "")

    def test_renderer_formats_spacing_without_changing_stored_digits(self):
        campo = self.crear_campo(NumericConfig(
            mode="spacing", spacing_mask="####(-)####"
        ))
        respuesta_almacenada = "12345"
        self.assertEqual(
            formatear_respuesta_campo(campo, respuesta_almacenada),
            "1234-5   ",
        )
        self.assertEqual(respuesta_almacenada, "12345")

    def test_renderer_formats_date_separators_without_padding_while_typing(self):
        campo = self.crear_campo(NumericConfig(
            mode="date", date_format="dd/mm/aaaa", min_year="1900"
        ))
        self.assertEqual(
            formatear_respuesta_campo(campo, "12052026"),
            "12/05/2026",
        )
        self.assertEqual(
            formatear_respuesta_campo(campo, "1/2/2026"),
            "1/2/2026",
        )

    def test_spacing_mode_checks_capacity_and_required_positions(self):
        campo = self.crear_campo(NumericConfig(
            mode="spacing", spacing_mask="####(-)####", spacing_required=False
        ))
        self.assertTrue(validar_respuesta(campo, "12345")[0])
        self.assertFalse(validar_respuesta(campo, "123456789")[0])
        campo.numeric_config.spacing_required = True
        self.assertFalse(validar_respuesta(campo, "12345")[0])
        self.assertTrue(validar_respuesta(campo, "12345678")[0])

    def test_spacing_mask_rejects_literals_outside_parentheses(self):
        campo = self.crear_campo(NumericConfig(
            mode="spacing", spacing_mask="####-####"
        ))
        valido, mensaje = validar_respuesta(campo, "12345678")
        self.assertFalse(valido)
        self.assertIn("paréntesis", mensaje)

    def test_android_and_windows_validators_apply_same_limit_rules(self):
        config = AndroidNumericConfig(mode="limit", max_value="100")
        campo = AndroidField(
            field_id="dato",
            question="Dato",
            field_type="number",
            validation=AndroidValidation(numeric_only=True),
            numeric_config=config,
        )
        self.assertTrue(validar_respuesta_android(campo, "100")[0])
        self.assertFalse(validar_respuesta_android(campo, "101")[0])

    def test_fdt_rejects_invalid_numeric_configuration(self):
        campo = self.crear_campo(NumericConfig(mode="limit", max_value=""))
        campo.order = 1
        campo.position = Position(x=0, y=0, width=10, height=10)
        formato = Formato(
            name="Prueba",
            template=TemplateInfo(path="plantilla.png", width=100, height=100),
            fields=[campo],
        )
        with self.assertRaises(ValueError):
            validar_fdt(formato)

    def test_android_fdt_rejects_invalid_numeric_configuration(self):
        campo = AndroidField(
            field_id="dato",
            question="Dato",
            field_type="number",
            order=1,
            validation=AndroidValidation(numeric_only=True),
            position=AndroidPosition(x=0, y=0, width=10, height=10),
            numeric_config=AndroidNumericConfig(mode="limit", max_value=""),
        )
        formato = AndroidFormato(
            name="Prueba",
            template=AndroidTemplateInfo(
                path="plantilla.png", width=100, height=100
            ),
            fields=[campo],
        )
        with self.assertRaises(ValueError):
            validar_fdt_android(formato)


class NumericConfigModelTests(unittest.TestCase):
    def test_four_modes_round_trip_without_losing_settings(self):
        configurations = (
            NumericConfig(mode="number"),
            NumericConfig(mode="limit", max_value="999999"),
            NumericConfig(
                mode="date",
                date_format="dd/mm/aa",
                past_only=True,
                min_year="1950",
            ),
            NumericConfig(
                mode="spacing",
                spacing_mask="####(-)####",
                spacing_required=True,
            ),
        )

        for config in configurations:
            with self.subTest(mode=config.mode):
                original = Field(
                    field_id="numero",
                    question="Dato",
                    field_type=FIELD_TYPE_NUMBER,
                    numeric_config=config,
                )
                restored = Field.from_dict(original.to_dict())
                self.assertEqual(restored.numeric_config, config)

    def test_supported_modes_and_date_formats_are_exact(self):
        self.assertEqual(NUMERIC_MODES, ("number", "limit", "date", "spacing"))
        self.assertEqual(
            DATE_FORMATS,
            (
                "dd/mm/aa", "dd/mm/aaaa",
                "mm/dd/aa", "mm/dd/aaaa",
                "dd-mm-aa", "dd-mm-aaaa",
                "mm-dd-aa", "mm-dd-aaaa",
                "aaaa", "mm", "dd",
            ),
        )

    def test_android_capturador_model_round_trip(self):
        config = AndroidNumericConfig(
            mode="spacing",
            spacing_mask="##(/)##(/)####",
            spacing_required=True,
        )
        field = AndroidField(
            field_id="fecha",
            question="Fecha",
            field_type="number",
            numeric_config=config,
        )
        restored = AndroidField.from_dict(field.to_dict())
        self.assertEqual(restored.numeric_config, config)


    def test_legacy_field_without_numeric_config_uses_number_mode(self):
        legacy = {
            "field_id": "numero",
            "question": "Dato",
            "field_type": FIELD_TYPE_NUMBER,
        }

        restored = Field.from_dict(legacy)

        self.assertEqual(restored.numeric_config, NumericConfig())
        self.assertEqual(restored.numeric_config.mode, "number")

    def test_numeric_config_missing_optional_keys_uses_defaults(self):
        config = NumericConfig.from_dict({"mode": "date"})

        self.assertEqual(config.mode, "date")
        self.assertEqual(config.date_format, "dd/mm/aaaa")
        self.assertEqual(config.max_value, "")
        self.assertFalse(config.past_only)
        self.assertEqual(config.min_year, "")
        self.assertEqual(config.spacing_mask, "####")
        self.assertFalse(config.spacing_required)


if __name__ == "__main__":
    unittest.main()
