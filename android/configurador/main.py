# -*- coding: utf-8 -*-
import os

from kivy.app import App
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage

from shared.fdt import guardar_fdt, validar_fdt
from shared.models import (
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
    Color as FieldColor,
    Field,
    Formato,
    Position,
    TemplateInfo,
    TextStyle,
)


TOOLS = [
    ("↖", "select"),
    ("A", FIELD_TYPE_TEXT),
    ("1", FIELD_TYPE_NUMBER),
    ("A1", FIELD_TYPE_ALPHANUMERIC),
    ("IMG", FIELD_TYPE_IMAGE),
    ("🔍", "zoom"),
]


class CampoWidget(FloatLayout):
    def __init__(self, campo, scale=1.0, **kwargs):
        super().__init__(**kwargs)
        self.campo = campo
        self.scale = scale
        self.size_hint = (None, None)
        self.actualizar()

    def actualizar(self):
        p = self.campo.position
        self.size = (p.width * self.scale, p.height * self.scale)
        self.pos = (p.x * self.scale, p.y * self.scale)

        self.canvas.before.clear()
        with self.canvas.before:
            Color(0.0, 0.84, 1.0, 1.0)
            Line(rectangle=(0, 0, self.width, self.height), width=1.4)

        self.clear_widgets()
        self.add_widget(
            Label(
                text="%d  %s" % (self.campo.order, self.campo.field_type),
                size_hint=(None, None),
                size=(dp(130), dp(28)),
                pos=(dp(4), max(0, self.height - dp(30))),
                color=(0.0, 0.84, 1.0, 1),
                font_size="12sp",
                halign="left",
            )
        )


class CanvasEditor(FloatLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.template_widget = None
        self.scale = 1.0
        self.start_touch = None
        self.preview_rect = None

    def cargar_plantilla(self, ruta):
        self.clear_widgets()
        self.template_widget = KivyImage(
            source=ruta,
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(None, None),
        )
        self.template_widget.size = (
            self.app.formato.template.width * self.scale,
            self.app.formato.template.height * self.scale,
        )
        self.template_widget.pos = (dp(20), dp(20))
        self.add_widget(self.template_widget)

        for campo in self.app.formato.fields:
            self.add_widget(CampoWidget(campo, self.scale))

    def _document_point(self, touch):
        if not self.template_widget:
            return 0, 0
        x = (touch.x - self.template_widget.x) / self.scale
        y = (touch.y - self.template_widget.y) / self.scale
        return int(x), int(self.app.formato.template.height - y)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False

        tool = self.app.tool
        if tool == "zoom":
            self.app.set_zoom(self.scale * 1.2)
            return True

        if tool == "select":
            return super().on_touch_down(touch)

        if tool in (
            FIELD_TYPE_TEXT,
            FIELD_TYPE_NUMBER,
            FIELD_TYPE_ALPHANUMERIC,
            FIELD_TYPE_IMAGE,
        ):
            self.start_touch = self._document_point(touch)
            return True

        return super().on_touch_down(touch)

    def on_touch_up(self, touch):
        if not self.start_touch:
            return super().on_touch_up(touch)

        tool = self.app.tool
        if tool not in (
            FIELD_TYPE_TEXT,
            FIELD_TYPE_NUMBER,
            FIELD_TYPE_ALPHANUMERIC,
            FIELD_TYPE_IMAGE,
        ):
            self.start_touch = None
            return super().on_touch_up(touch)

        x0, y0 = self.start_touch
        x1, y1 = self._document_point(touch)
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        width = max(1, right - left)
        height = max(1, bottom - top)

        self.start_touch = None

        campo = Field(
            field_id=self.app.nuevo_id(),
            question="",
            field_type=tool,
            position=Position(left, top, width, height),
            text_style=TextStyle(
                font_family="",
                font_size_px=24,
                color=FieldColor(0, 0, 0),
                alignment="left",
            ),
        )
        self.app.formato.agregar_campo(campo)
        self.app.seleccionar(campo)
        self.app.mostrar_propiedades(campo)
        return True


class ConfiguradorApp(App):
    title = "Configurador de Formatos Traducidos"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.formato = None
        self.tool = "select"
        self.scale = 1.0
        self.editor = None
        self.seleccionado = None
        self.estado = None

    def build(self):
        root = BoxLayout(orientation="vertical")
        menu = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(3), padding=dp(3))
        for texto, accion in (
            ("Nuevo", self.nuevo),
            ("Abrir", self.abrir),
            ("Guardar", self.guardar),
            ("Guardar como FDT", self.guardar_como_fdt),
            ("Importar", self.importar),
        ):
            menu.add_widget(Button(text=texto, on_release=lambda _, f=accion: f()))

        root.add_widget(menu)

        tools = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(3), padding=dp(3))
        for simbolo, tool in TOOLS:
            tools.add_widget(
                Button(
                    text=simbolo,
                    on_release=lambda _, t=tool: self.set_tool(t),
                )
            )

        tools.add_widget(Button(text="−", on_release=lambda _: self.set_zoom(self.scale * 0.8)))
        self.zoom_label = Label(text="100 %", size_hint_x=None, width=dp(70))
        tools.add_widget(self.zoom_label)
        tools.add_widget(Button(text="+", on_release=lambda _: self.set_zoom(self.scale * 1.25)))
        root.add_widget(tools)

        self.editor = CanvasEditor(self)
        root.add_widget(self.editor)

        self.estado = Label(
            text="Listo. Importe una plantilla para comenzar.",
            size_hint_y=None,
            height=dp(32),
            halign="left",
        )
        root.add_widget(self.estado)
        return root

    def set_tool(self, tool):
        self.tool = tool
        self.estado.text = "Herramienta: " + str(tool)

    def nuevo(self):
        self.formato = None
        self.seleccionado = None
        self.editor.clear_widgets()
        self.estado.text = "Nuevo formato."

    def importar(self):
        self._file_popup("Importar plantilla", self._importar_ruta, imagenes=True)

    def _importar_ruta(self, ruta):
        try:
            from PIL import Image
            imagen = Image.open(ruta).convert("RGB")
            self.formato = Formato(
                name=os.path.splitext(os.path.basename(ruta))[0],
                template=TemplateInfo(
                    path=ruta,
                    width=imagen.width,
                    height=imagen.height,
                    dpi=300,
                    mode="RGB",
                ),
            )
            self.scale = min(1.0, 0.8 * min(
                (self.width - dp(40)) / imagen.width,
                (self.height - dp(140)) / imagen.height,
            ))
            self.scale = max(0.05, self.scale)
            self.editor.scale = self.scale
            self.editor.cargar_plantilla(ruta)
            self.actualizar_zoom()
            self.estado.text = "Plantilla importada: %d × %d px" % (imagen.width, imagen.height)
        except Exception as exc:
            self.estado.text = "Error al importar: " + str(exc)

    def abrir(self):
        self._file_popup("Abrir FDT", self._abrir_ruta)

    def _abrir_ruta(self, ruta):
        try:
            from shared.fdt import cargar_fdt
            self.formato = cargar_fdt(ruta)
            self.scale = min(1.0, 0.8 * min(
                (self.width - dp(40)) / self.formato.template.width,
                (self.height - dp(140)) / self.formato.template.height,
            ))
            self.scale = max(0.05, self.scale)
            self.editor.scale = self.scale
            self.editor.cargar_plantilla(self.formato.template.path)
            self.actualizar_zoom()
            self.estado.text = "FDT abierto."
        except Exception as exc:
            self.estado.text = "Error al abrir: " + str(exc)

    def guardar(self):
        self.guardar_como_fdt()

    def guardar_como_fdt(self):
        if not self.formato:
            self.estado.text = "Primero importe una plantilla."
            return
        self._file_popup("Guardar FDT", self._guardar_ruta, guardar=True)

    def _guardar_ruta(self, ruta):
        try:
            validar_fdt(self.formato)
            guardar_fdt(self.formato, ruta)
            self.estado.text = "FDT guardado."
        except Exception as exc:
            self.estado.text = "Error al guardar: " + str(exc)

    def _file_popup(self, titulo, callback, imagenes=False, guardar=False):
        layout = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        if guardar:
            chooser = FileChooserListView(path="/storage/emulated/0", dirselect=False)
            nombre = TextInput(text="formato.fdt", size_hint_y=None, height=dp(42))
            layout.add_widget(chooser)
            layout.add_widget(nombre)

            def confirmar(_):
                ruta = os.path.join(chooser.path, nombre.text.strip() or "formato.fdt")
                if not ruta.lower().endswith(".fdt"):
                    ruta += ".fdt"
                popup.dismiss()
                callback(ruta)

            layout.add_widget(Button(text="Guardar", size_hint_y=None, height=dp(45), on_release=confirmar))
        else:
            chooser = FileChooserListView(
                path="/storage/emulated/0",
                filters=["*.jpg", "*.jpeg", "*.png", "*.bmp"] if imagenes else ["*.fdt"],
            )
            layout.add_widget(chooser)

            def confirmar(_):
                seleccion = chooser.selection
                if not seleccion:
                    return
                popup.dismiss()
                callback(seleccion[0])

            layout.add_widget(Button(text="Abrir", size_hint_y=None, height=dp(45), on_release=confirmar))

        layout.add_widget(Button(text="Cancelar", size_hint_y=None, height=dp(45), on_release=lambda _: popup.dismiss()))
        popup = Popup(title=titulo, content=layout, size_hint=(0.95, 0.9))
        popup.open()

    def nuevo_id(self):
        usados = {c.field_id for c in self.formato.fields}
        n = 1
        while "campo%d" % n in usados:
            n += 1
        return "campo%d" % n

    def seleccionar(self, campo):
        self.seleccionado = campo
        self.editor.cargar_plantilla(self.formato.template.path)

    def mostrar_propiedades(self, campo):
        layout = BoxLayout(orientation="vertical", spacing=dp(7), padding=dp(10))

        id_input = TextInput(text=campo.field_id, multiline=False, size_hint_y=None, height=dp(40))
        pregunta = TextInput(text=campo.question, hint_text="Pregunta para el capturador", size_hint_y=None, height=dp(70))
        fuente = TextInput(text=campo.text_style.font_family, hint_text="Fuente del sistema", multiline=False, size_hint_y=None, height=dp(40))
        tamano = TextInput(text=str(campo.text_style.font_size_px), multiline=False, size_hint_y=None, height=dp(40))
        alineacion = TextInput(text=campo.text_style.alignment, hint_text="left / center / right / justify", multiline=False, size_hint_y=None, height=dp(40))

        layout.add_widget(Label(text="Campo %d — %s" % (campo.order, campo.field_type), size_hint_y=None, height=dp(30)))
        layout.add_widget(Label(text="ID"))
        layout.add_widget(id_input)
        layout.add_widget(Label(text="Pregunta"))
        layout.add_widget(pregunta)

        if campo.field_type != FIELD_TYPE_IMAGE:
            layout.add_widget(Label(text="Tipografía"))
            layout.add_widget(fuente)
            layout.add_widget(Label(text="Tamaño en px"))
            layout.add_widget(tamano)
            layout.add_widget(Label(text="Alineación"))
            layout.add_widget(alineacion)

        botones = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))

        def aceptar(_):
            campo.field_id = id_input.text.strip() or campo.field_id
            campo.question = pregunta.text.strip()
            if campo.field_type != FIELD_TYPE_IMAGE:
                campo.text_style.font_family = fuente.text.strip()
                try:
                    campo.text_style.font_size_px = max(1, int(tamano.text))
                except ValueError:
                    pass
                if alineacion.text in ("left", "center", "right", "justify"):
                    campo.text_style.alignment = alineacion.text
            self.formato.ordenar_campos()
            self.editor.cargar_plantilla(self.formato.template.path)
            popup.dismiss()
            self.estado.text = "Campo %d configurado." % campo.order

        botones.add_widget(Button(text="Cancelar", on_release=lambda _: popup.dismiss()))
        botones.add_widget(Button(text="Aceptar", on_release=aceptar))
        layout.add_widget(botones)

        popup = Popup(
            title="Propiedades del campo",
            content=layout,
            size_hint=(0.92, 0.88),
        )
        popup.open()

    def set_zoom(self, value):
        if not self.formato:
            return
        self.scale = max(0.05, min(5.0, value))
        self.editor.scale = self.scale
        self.editor.cargar_plantilla(self.formato.template.path)
        self.actualizar_zoom()

    def actualizar_zoom(self):
        self.zoom_label.text = "%d %%" % int(round(self.scale * 100))


if __name__ == "__main__":
    ConfiguradorApp().run()
