# -*- coding: utf-8 -*-
from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label

class ConfiguradorApp(App):
    title = "Configurador de Formatos Traducidos"

    def build(self):
        layout = BoxLayout(orientation="vertical", padding=24, spacing=16)
        layout.add_widget(Label(
            text="Configurador de Formatos Traducidos",
            font_size="22sp",
            halign="center",
            valign="middle",
        ))
        layout.add_widget(Label(
            text="Base técnica de compilación.\nLa interfaz funcional se integra en los siguientes bloques.",
            halign="center",
            valign="middle",
        ))
        return layout

if __name__ == "__main__":
    ConfiguradorApp().run()
