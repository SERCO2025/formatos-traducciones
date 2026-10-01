# -*- coding: utf-8 -*-
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

from shared.models import (
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
)


class ConfiguradorApp(App):
    title = "Configurador de Formatos Traducidos"

    def build(self):
        layout = BoxLayout(
            orientation="vertical",
            padding=24,
            spacing=16,
        )

        layout.add_widget(
            Label(
                text="Configurador de Formatos Traducidos",
                font_size="22sp",
                halign="center",
                valign="middle",
            )
        )

        layout.add_widget(
            Label(
                text=(
                    "Base tecnica 5B.\n"
                    "Herramientas previstas: A, 1, A1, imagen y lupa.\n"
                    "Los campos se enumeran automaticamente."
                ),
                halign="center",
                valign="middle",
            )
        )

        return layout


if __name__ == "__main__":
    ConfiguradorApp().run()
