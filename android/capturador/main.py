# -*- coding: utf-8 -*-
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

class CapturadorApp(App):
    title = "Capturador de Formatos Traducidos"

    def build(self):
        layout = BoxLayout(orientation="vertical", padding=24, spacing=16)
        layout.add_widget(Label(
            text="Capturador de Formatos Traducidos",
            font_size="22sp",
            halign="center",
            valign="middle",
        ))
        layout.add_widget(Label(
            text="Base técnica de compilación.\nLa captura y el renderizador se integran en los siguientes bloques.",
            halign="center",
            valign="middle",
        ))
        return layout

if __name__ == "__main__":
    CapturadorApp().run()
