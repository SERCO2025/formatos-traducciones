# -*- coding: utf-8 -*-
import unittest

from shared.models import (
    DATE_FORMATS,
    NUMERIC_MODES,
    FIELD_TYPE_NUMBER,
    Field,
    NumericConfig,
)
from android.capturador.shared.models import (
    Field as AndroidField,
    NumericConfig as AndroidNumericConfig,
)


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
