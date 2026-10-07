# -*- coding: utf-8 -*-
import copy
import os
import uuid

from kivy.app import App
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.image import Image as KivyImage
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

try:
    from android import activity
    from jnius import autoclass
    ANDROID_AVAILABLE = True
except Exception:
    activity = None
    ANDROID_AVAILABLE = False

from shared.fdt import cargar_fdt, guardar_fdt, validar_fdt
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
    def __init__(self, campo, editor, **kwargs):
        super().__init__(**kwargs)
        self.campo = campo
        self.editor = editor
        self.size_hint = (None, None)
        self.actualizar()

    def actualizar(self):
        p = self.campo.position
        self.size = (p.width * self.editor.scale, p.height * self.editor.scale)
        tw = self.editor.template_widget
        if tw is not None:
            self.pos = (
                tw.x + p.x * self.editor.scale,
                tw.y + tw.height - (p.y + p.height) * self.editor.scale,
            )

        self.canvas.before.clear()
        with self.canvas.before:
            Color(0, 0, 0, 1)
            Line(rectangle=(0, 0, self.width, self.height), width=2.0)
            if self.editor.seleccionado is self.campo:
                Color(0.0, 0.75, 1.0, 1)
                Line(rectangle=(0, 0, self.width, self.height), width=3.0)

        self.canvas.after.clear()
        if self.editor.seleccionado is self.campo:
            with self.canvas.after:
                Color(0.0, 0.75, 1.0, 1)
                s = min(dp(12), max(dp(7), min(self.width, self.height) / 5.0))
                points = [
                    (0, 0), (self.width / 2, 0), (self.width, 0),
                    (0, self.height / 2), (self.width, self.height / 2),
                    (0, self.height), (self.width / 2, self.height),
                    (self.width, self.height / 2), (self.width, self.height),
                ]
                for x, y in points:
                    Line(points=(x - s/2, y, x + s/2, y), width=2)
                    Line(points=(x, y - s/2, x, y + s/2), width=2)

        self.clear_widgets()
        if self.campo.field_type == FIELD_TYPE_IMAGE:
            texto = "%d  IMAGEN" % self.campo.order
        else:
            texto = self.campo.text or ("%d  %s" % (self.campo.order, self.campo.field_type))
        etiqueta = Label(
            text=texto,
            size_hint=(1, 1),
            color=(
                self.campo.text_style.color.r / 255.0,
                self.campo.text_style.color.g / 255.0,
                self.campo.text_style.color.b / 255.0,
                1,
            ),
            font_size=max(dp(9), self.campo.text_style.font_size_px * self.editor.scale),
            halign=self.campo.text_style.alignment if self.campo.text_style.alignment in ("left", "center", "right") else "left",
            valign="middle",
        )
        etiqueta.bind(size=lambda inst, value: setattr(inst, "text_size", value))
        if self.campo.text_style.font_family and os.path.isfile(self.campo.text_style.font_family):
            etiqueta.font_name = self.campo.text_style.font_family
        self.add_widget(etiqueta)

    def _handle_at(self, x, y):
        if self.editor.seleccionado is not self.campo:
            return None
        s = min(dp(18), max(dp(10), min(self.width, self.height) / 4.0))
        left = abs(x) <= s
        right = abs(x - self.width) <= s
        bottom = abs(y) <= s
        top = abs(y - self.height) <= s
        if left and bottom:
            return "sw"
        if right and bottom:
            return "se"
        if left and top:
            return "nw"
        if right and top:
            return "ne"
        if abs(x - self.width / 2) <= s and bottom:
            return "s"
        if abs(x - self.width / 2) <= s and top:
            return "n"
        if left and abs(y - self.height / 2) <= s:
            return "w"
        if right and abs(y - self.height / 2) <= s:
            return "e"
        return None

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return super().on_touch_down(touch)
        if self.editor.app.tool == "select":
            local = self.to_widget(*touch.pos)
            handle = self._handle_at(*local)
            self.editor.begin_field_interaction(self.campo, touch, handle)
            return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.editor.active_field_touch is touch:
            self.editor.update_field_interaction(touch)
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.editor.active_field_touch is touch:
            self.editor.end_field_interaction(touch)
            return True
        return super().on_touch_up(touch)


class CanvasEditor(FloatLayout):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.template_widget = None
        self.start_touch = None
        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self.pan_start = None
        self.pan_template_pos = None

    def cargar_plantilla(self, ruta):
        self.clear_widgets()
        self.template_widget = KivyImage(
            source=ruta,
            allow_stretch=True,
            keep_ratio=True,
            size_hint=(None, None),
        )
        self.template_widget.size = (
            self.app.formato.template.width * self.app.scale,
            self.app.formato.template.height * self.app.scale,
        )
        self.template_widget.pos = self.app.template_position()
        self.add_widget(self.template_widget)

        for campo in sorted(self.app.formato.fields, key=lambda c: c.order):
            self.add_widget(CampoWidget(campo, self))

        if self.start_touch:
            self.start_touch = None

    def refresh_fields(self):
        if self.template_widget is None:
            return
        for widget in self.children:
            if isinstance(widget, CampoWidget):
                widget.actualizar()

    def _document_point(self, touch):
        if not self.template_widget or not self.app.formato:
            return 0, 0
        x = (touch.x - self.template_widget.x) / self.app.scale
        y_bottom = (touch.y - self.template_widget.y) / self.app.scale
        y = self.app.formato.template.height - y_bottom
        x = max(0, min(self.app.formato.template.width, x))
        y = max(0, min(self.app.formato.template.height, y))
        return int(round(x)), int(round(y))

    def _inside_template(self, touch):
        return self.template_widget is not None and self.template_widget.collide_point(*touch.pos)

    def on_touch_down(self, touch):
        if not self.collide_point(*touch.pos):
            return False

        tool = self.app.tool

        if tool == "zoom":
            factor = 0.8 if touch.button == "right" else 1.2
            self.app.set_zoom(self.app.scale * factor)
            return True

        if tool == "hand":
            self.pan_start = touch.pos
            self.pan_template_pos = self.template_widget.pos if self.template_widget else None
            return True

        if tool in (FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_ALPHANUMERIC, FIELD_TYPE_IMAGE):
            if self._inside_template(touch):
                self.start_touch = self._document_point(touch)
                self.app.estado.text = "Dibujando campo..."
                return True

        if tool == "select" and self._inside_template(touch):
            self.app.seleccionar(None)
            return True

        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if self.pan_start and self.app.tool == "hand" and self.template_widget:
            dx = touch.x - self.pan_start[0]
            dy = touch.y - self.pan_start[1]
            self.template_widget.pos = (
                self.pan_template_pos[0] + dx,
                self.pan_template_pos[1] + dy,
            )
            self.refresh_fields()
            return True

        if self.start_touch and self.app.tool in (
            FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_ALPHANUMERIC, FIELD_TYPE_IMAGE
        ):
            self.app.redraw_drawing_preview(self.start_touch, self._document_point(touch))
            return True

        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.pan_start:
            self.pan_start = None
            self.pan_template_pos = None
            return True

        if not self.start_touch:
            return super().on_touch_up(touch)

        tool = self.app.tool
        if tool not in (FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_ALPHANUMERIC, FIELD_TYPE_IMAGE):
            self.start_touch = None
            self.app.clear_drawing_preview()
            return super().on_touch_up(touch)

        x0, y0 = self.start_touch
        x1, y1 = self._document_point(touch)
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        width = max(2, right - left)
        height = max(2, bottom - top)
        self.start_touch = None
        self.app.clear_drawing_preview()

        if width < 4 or height < 4:
            self.app.estado.text = "Área demasiado pequeña."
            return True

        self.app.push_undo()
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

    def begin_field_interaction(self, campo, touch, handle):
        self.app.seleccionar(campo)
        self.active_field_touch = touch
        self.active_field = campo
        self.active_handle = handle
        self.initial_position = copy.deepcopy(campo.position)
        self.app._interaction_changed = False
        if handle is None:
            self.app.estado.text = "Moviendo campo..."
        else:
            self.app.estado.text = "Redimensionando campo..."

    def update_field_interaction(self, touch):
        if self.active_field is None or self.initial_position is None:
            return
        x, y = self._document_point(touch)
        start = getattr(self, "_interaction_start_doc", None)
        if start is None:
            start = self._document_point(self.active_field_touch)
            self._interaction_start_doc = start
        dx = x - start[0]
        dy = y - start[1]
        p0 = self.initial_position
        p = self.active_field.position

        if self.active_handle is None:
            p.x = max(0, min(self.app.formato.template.width - p.width, p0.x + dx))
            p.y = max(0, min(self.app.formato.template.height - p.height, p0.y + dy))
        else:
            nx, ny, nw, nh = p0.x, p0.y, p0.width, p0.height
            if "w" in self.active_handle:
                nx = p0.x + dx
                nw = p0.width - dx
            if "e" in self.active_handle:
                nw = p0.width + dx
            if "n" in self.active_handle:
                ny = p0.y + dy
                nh = p0.height - dy
            if "s" in self.active_handle:
                nh = p0.height + dy
            min_size = 4
            if nw < min_size:
                nw = min_size
                if "w" in self.active_handle:
                    nx = p0.x + p0.width - min_size
            if nh < min_size:
                nh = min_size
                if "n" in self.active_handle:
                    ny = p0.y + p0.height - min_size
            nx = max(0, min(self.app.formato.template.width - nw, nx))
            ny = max(0, min(self.app.formato.template.height - nh, ny))
            p.x, p.y, p.width, p.height = int(nx), int(ny), int(nw), int(nh)

        self.app._interaction_changed = True
        self.refresh_fields()

    def end_field_interaction(self, touch):
        if self.app._interaction_changed:
            self.app.push_undo_from_initial(self.active_field, self.initial_position)
        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self._interaction_start_doc = None
        self.app.estado.text = "Campo actualizado."

    def redraw_preview(self):
        self.app.clear_drawing_preview()
        if self.start_touch:
            pass


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
        self.estado_menu = None
        self.zoom_label = None
        self._visual_template_path = None
        self._android_callback = None
        self._undo = []
        self._redo = []
        self._interaction_changed = False
        self._drawing_widget = None
        if ANDROID_AVAILABLE:
            activity.bind(on_activity_result=self._on_android_activity_result)

    def build(self):
        root = BoxLayout(orientation="vertical")
        barra = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6), padding=(dp(6), dp(5)))
        barra.add_widget(Button(text="☰", size_hint_x=None, width=dp(58), font_size="28sp", on_release=lambda _: self.abrir_menu()))
        titulo = Label(text="Configurador de Formatos", halign="left", valign="middle", font_size="17sp")
        titulo.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        barra.add_widget(titulo)
        self.estado_menu = Label(text="Listo", size_hint_x=None, width=dp(82), font_size="12sp", halign="right", valign="middle")
        self.estado_menu.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        barra.add_widget(self.estado_menu)
        root.add_widget(barra)

        tools = BoxLayout(size_hint_y=None, height=dp(58), spacing=dp(3), padding=dp(3))
        for simbolo, tool in TOOLS:
            tools.add_widget(Button(text=simbolo, on_release=lambda _, t=tool: self.set_tool(t)))
        tools.add_widget(Button(text="−", on_release=lambda _: self.set_zoom(self.scale * 0.8)))
        self.zoom_label = Label(text="100 %", size_hint_x=None, width=dp(70))
        tools.add_widget(self.zoom_label)
        tools.add_widget(Button(text="+", on_release=lambda _: self.set_zoom(self.scale * 1.25)))
        root.add_widget(tools)

        self.editor = CanvasEditor(self)
        root.add_widget(self.editor)

        self.estado = Label(text="Listo. Importe una plantilla para comenzar.", size_hint_y=None, height=dp(32), halign="left")
        root.add_widget(self.estado)
        return root

    def abrir_menu(self):
        panel = ModalView(
            size_hint=(0.86, 1),
            pos_hint={"x": 0, "y": 0},
            auto_dismiss=True,
            background_color=(0.05, 0.05, 0.05, 0.98),
            background="",
        )
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        encabezado = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        encabezado.add_widget(Label(text="MENÚ", font_size="20sp", halign="left", valign="middle"))
        encabezado.add_widget(Button(text="×", size_hint_x=None, width=dp(48), font_size="24sp", on_release=lambda _: panel.dismiss()))
        contenido.add_widget(encabezado)

        def seccion(texto):
            contenido.add_widget(Label(text=texto, size_hint_y=None, height=dp(28), halign="left", font_size="13sp"))

        def opcion(texto, accion):
            b = Button(text=texto, size_hint_y=None, height=dp(46), font_size="15sp")
            b.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - dp(20), val[1])))
            b.bind(on_release=lambda _: (panel.dismiss(), accion()))
            contenido.add_widget(b)

        seccion("ARCHIVO")
        opcion("Nuevo formato", self.nuevo)
        opcion("Abrir formato FDT", self.abrir)
        opcion("Importar plantilla", self.importar)
        opcion("Guardar", self.guardar)
        opcion("Guardar como FDT", self.guardar_como_fdt)

        seccion("EDITAR")
        opcion("Deshacer", self.deshacer)
        opcion("Rehacer", self.rehacer)
        opcion("Eliminar campo", self.eliminar_campo)
        opcion("Propiedades del campo", lambda: self.mostrar_propiedades(self.seleccionado) if self.seleccionado else self._aviso("Seleccione un campo."))

        seccion("HERRAMIENTAS")
        opcion("Seleccionar / mover", lambda: self.set_tool("select"))
        opcion("Desplazar", lambda: self.set_tool("hand"))
        opcion("Texto", lambda: self.set_tool(FIELD_TYPE_TEXT))
        opcion("Número", lambda: self.set_tool(FIELD_TYPE_NUMBER))
        opcion("Alfanumérico", lambda: self.set_tool(FIELD_TYPE_ALPHANUMERIC))
        opcion("Imagen", lambda: self.set_tool(FIELD_TYPE_IMAGE))
        opcion("Lupa", lambda: self.set_tool("zoom"))
        opcion("Lista de campos", self.mostrar_lista_campos)
        opcion("Archivo terminado", self.editar_salida)

        seccion("VISTA")
        opcion("Alejar", lambda: self.set_zoom(self.scale * 0.8))
        opcion("Acercar", lambda: self.set_zoom(self.scale * 1.25))
        opcion("Restablecer zoom", lambda: self.set_zoom(1.0))
        contenido.add_widget(Label(text="Formatos Traducidos", size_hint_y=None, height=dp(38), font_size="11sp"))
        panel.add_widget(contenido)
        panel.open()

    def set_tool(self, tool):
        self.tool = tool
        nombres = {
            "select": "Seleccionar",
            "hand": "Desplazar",
            "zoom": "Lupa",
            FIELD_TYPE_TEXT: "Texto",
            FIELD_TYPE_NUMBER: "Número",
            FIELD_TYPE_ALPHANUMERIC: "Alfanumérico",
            FIELD_TYPE_IMAGE: "Imagen",
        }
        self.estado.text = "Herramienta: " + nombres.get(tool, str(tool))
        self.estado_menu.text = nombres.get(tool, str(tool))

    def template_position(self):
        if not self.formato:
            return (dp(20), dp(20))
        ancho = self.formato.template.width * self.scale
        alto = self.formato.template.height * self.scale
        x = max(dp(10), (self.editor.width - ancho) / 2.0)
        y = max(dp(10), (self.editor.height - alto) / 2.0)
        return x, y

    def nuevo(self):
        self.push_undo() if self.formato else None
        self.formato = None
        self.seleccionado = None
        self._visual_template_path = None
        self._undo = []
        self._redo = []
        self.editor.clear_widgets()
        self.estado.text = "Nuevo formato."
        self.estado_menu.text = "Nuevo"

    def importar(self):
        if ANDROID_AVAILABLE:
            self._abrir_selector_android("image", guardar=False)
        else:
            self._file_popup("Importar plantilla", self._importar_ruta, imagenes=True)

    def abrir(self):
        if ANDROID_AVAILABLE:
            self._abrir_selector_android("fdt", guardar=False)
        else:
            self._file_popup("Abrir FDT", self._abrir_ruta)

    def _abrir_selector_android(self, tipo, guardar=False):
        try:
            Intent = autoclass("android.content.Intent")
            accion = Intent.ACTION_CREATE_DOCUMENT if guardar else Intent.ACTION_OPEN_DOCUMENT
            intent = Intent(accion)
            intent.setType("image/*" if tipo == "image" else "*/*")
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if not guardar:
                intent.addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            else:
                nombre = (self.formato.name.strip() if self.formato and self.formato.name.strip() else "formato") + ".fdt"
                intent.putExtra(Intent.EXTRA_TITLE, nombre)
            self._android_callback = (tipo, guardar)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PythonActivity.mActivity.startActivityForResult(intent, 4001)
        except Exception as exc:
            self.estado.text = "Error al abrir selector: " + str(exc)

    def _on_android_activity_result(self, request_code, result_code, intent):
        if request_code != 4001 or not self._android_callback:
            return
        tipo, guardar = self._android_callback
        self._android_callback = None
        try:
            Activity = autoclass("android.app.Activity")
            if result_code != Activity.RESULT_OK or intent is None:
                return
            uri = intent.getData()
            if uri is None:
                raise IOError("No se recibió ningún archivo.")
            if guardar:
                self._guardar_fdt_uri(uri)
            else:
                ruta = self._copiar_uri_a_cache(uri, tipo)
                self._abrir_ruta(ruta) if tipo == "fdt" else self._importar_ruta(ruta)
        except Exception as exc:
            self.estado.text = "Error al seleccionar archivo: " + str(exc)

    def _nombre_display_uri(self, resolver, uri):
        try:
            OpenableColumns = autoclass("android.provider.OpenableColumns")
            cursor = resolver.query(uri, None, None, None, None)
            if cursor is None:
                return ""
            try:
                indice = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                return str(cursor.getString(indice)) if indice >= 0 and cursor.moveToFirst() else ""
            finally:
                cursor.close()
        except Exception:
            return ""

    def _copiar_uri_a_cache(self, uri, tipo):
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()
        flujo = resolver.openInputStream(uri)
        if flujo is None:
            raise IOError("Android no pudo abrir el archivo seleccionado.")
        try:
            nombre = self._nombre_display_uri(resolver, uri)
            extension = os.path.splitext(nombre)[1].lower()
            if tipo == "image" and not extension:
                extension = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/bmp": ".bmp",
                    "image/webp": ".webp",
                    "image/tiff": ".tif",
                }.get(str(resolver.getType(uri) or "").lower(), ".jpg")
            if tipo == "fdt":
                extension = ".fdt"
            extension = extension or ".bin"
            ruta = os.path.join(
                PythonActivity.mActivity.getCacheDir().getAbsolutePath(),
                "archivo_importado_" + uuid.uuid4().hex + extension,
            )
            from jnius import jarray
            buffer = jarray("b", [0] * 65536)
            FileOutputStream = autoclass("java.io.FileOutputStream")
            salida = FileOutputStream(ruta)
            try:
                while True:
                    cantidad = flujo.read(buffer)
                    if cantidad <= 0:
                        break
                    salida.write(buffer, 0, cantidad)
                salida.flush()
            finally:
                salida.close()
            if not os.path.isfile(ruta) or os.path.getsize(ruta) <= 0:
                raise IOError("El archivo seleccionado está vacío.")
            return ruta
        finally:
            flujo.close()

    def _crear_imagen_visual(self, ruta, imagen):
        visual = os.path.join(os.path.dirname(ruta), "vista_" + uuid.uuid4().hex + ".png")
        imagen.save(visual, format="PNG")
        if not os.path.isfile(visual) or os.path.getsize(visual) <= 0:
            raise IOError("No se pudo crear la imagen de vista previa.")
        return visual

    def _importar_ruta(self, ruta):
        try:
            from PIL import Image
            imagen = Image.open(ruta).convert("RGB")
            visual = self._crear_imagen_visual(ruta, imagen)
            self.formato = Formato(
                name=os.path.splitext(os.path.basename(ruta))[0],
                template=TemplateInfo(path=ruta, width=imagen.width, height=imagen.height, dpi=300, mode="RGB"),
            )
            self.scale = self._calcular_zoom_inicial(imagen.width, imagen.height)
            self._visual_template_path = visual
            self.seleccionado = None
            self._undo = []
            self._redo = []
            self.editor.scale = self.scale
            self.editor.cargar_plantilla(visual)
            self.actualizar_zoom()
            self.estado.text = "Plantilla importada: %d × %d px" % (imagen.width, imagen.height)
        except Exception as exc:
            self.estado.text = "Error al importar: " + str(exc)

    def _abrir_ruta(self, ruta):
        try:
            formato = cargar_fdt(ruta)
            from PIL import Image
            imagen = Image.open(formato.template.path).convert("RGB")
            if imagen.width != formato.template.width or imagen.height != formato.template.height:
                raise ValueError("Las dimensiones reales de la plantilla no coinciden con el FDT.")
            self.formato = formato
            self._visual_template_path = self._crear_imagen_visual(formato.template.path, imagen)
            self.scale = self._calcular_zoom_inicial(imagen.width, imagen.height)
            self.seleccionado = None
            self._undo = []
            self._redo = []
            self.editor.scale = self.scale
            self.editor.cargar_plantilla(self._visual_template_path)
            self.actualizar_zoom()
            self.estado.text = "FDT abierto. %d campo(s)." % len(self.formato.fields)
        except Exception as exc:
            self.estado.text = "Error al abrir: " + str(exc)

    def _calcular_zoom_inicial(self, width, height):
        ancho_disponible = max(dp(100), self.width - dp(40))
        alto_disponible = max(dp(100), self.height - dp(150))
        return max(0.05, min(1.0, 0.82 * min(ancho_disponible / float(width), alto_disponible / float(height))))

    def guardar(self):
        self.guardar_como_fdt()

    def guardar_como_fdt(self):
        if not self.formato:
            self._aviso("Primero importe una plantilla.")
            return
        if ANDROID_AVAILABLE:
            self._abrir_selector_android("fdt", guardar=True)
        else:
            self._file_popup("Guardar FDT", self._guardar_ruta, guardar=True)

    def _guardar_fdt_uri(self, uri):
        if not self.formato:
            self._aviso("Primero importe una plantilla.")
            return
        temporal = None
        try:
            validar_fdt(self.formato)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            actividad = PythonActivity.mActivity
            resolver = actividad.getContentResolver()
            temporal = os.path.join(actividad.getCacheDir().getAbsolutePath(), "fdt_" + uuid.uuid4().hex + ".fdt")
            guardar_fdt(self.formato, temporal)
            entrada = open(temporal, "rb")
            salida = resolver.openOutputStream(uri)
            if salida is None:
                raise IOError("Android no pudo abrir el destino.")
            try:
                from jnius import jarray
                while True:
                    datos = entrada.read(65536)
                    if not datos:
                        break
                    salida.write(jarray("b", datos))
                salida.flush()
            finally:
                entrada.close()
                salida.close()
            self.estado.text = "FDT guardado correctamente."
        finally:
            if temporal and os.path.exists(temporal):
                try:
                    os.remove(temporal)
                except OSError:
                    pass

    def _guardar_ruta(self, ruta):
        try:
            validar_fdt(self.formato)
            guardar_fdt(self.formato, ruta)
            self.estado.text = "FDT guardado."
        except Exception as exc:
            self.estado.text = "Error al guardar: " + str(exc)

    def _file_popup(self, titulo, callback, imagenes=False, guardar=False):
        layout = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
        chooser = FileChooserListView(path="/storage/emulated/0", dirselect=False)
        if not guardar:
            chooser.filters = ["*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"] if imagenes else ["*.fdt"]
            layout.add_widget(chooser)
            def confirmar(_):
                if chooser.selection:
                    popup.dismiss()
                    callback(chooser.selection[0])
            layout.add_widget(Button(text="Abrir", size_hint_y=None, height=dp(45), on_release=confirmar))
        else:
            layout.add_widget(chooser)
            nombre = TextInput(text="formato.fdt", size_hint_y=None, height=dp(42))
            layout.add_widget(nombre)
            def confirmar(_):
                ruta = os.path.join(chooser.path, nombre.text.strip() or "formato.fdt")
                if not ruta.lower().endswith(".fdt"):
                    ruta += ".fdt"
                popup.dismiss()
                callback(ruta)
            layout.add_widget(Button(text="Guardar", size_hint_y=None, height=dp(45), on_release=confirmar))
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
        if self.editor:
            self.editor.refresh_fields()
        if campo:
            self.estado.text = "Campo %d — %s" % (campo.order, campo.field_id)

    def push_undo(self):
        if not self.formato:
            return
        self._undo.append(copy.deepcopy(self.formato))
        if len(self._undo) > 30:
            self._undo.pop(0)
        self._redo = []

    def push_undo_from_initial(self, campo, initial_position):
        if not self.formato or not self._interaction_changed:
            return
        actual = copy.deepcopy(self.formato)
        for c in actual.fields:
            if c.field_id == campo.field_id:
                c.position = copy.deepcopy(initial_position)
                break
        self._undo.append(actual)
        if len(self._undo) > 30:
            self._undo.pop(0)
        self._redo = []

    def _restore(self, formato):
        self.formato = copy.deepcopy(formato)
        self.seleccionado = None
        self.editor.scale = self.scale
        if self._visual_template_path and self.formato:
            self.editor.cargar_plantilla(self._visual_template_path)
        self.actualizar_lista_estado()

    def deshacer(self):
        if not self.formato or not self._undo:
            self.estado.text = "No hay acciones para deshacer."
            return
        self._redo.append(copy.deepcopy(self.formato))
        self._restore(self._undo.pop())
        self.estado.text = "Deshacer."

    def rehacer(self):
        if not self.formato or not self._redo:
            self.estado.text = "No hay acciones para rehacer."
            return
        self._undo.append(copy.deepcopy(self.formato))
        self._restore(self._redo.pop())
        self.estado.text = "Rehacer."

    def eliminar_campo(self):
        if not self.formato or not self.seleccionado:
            self._aviso("Seleccione un campo.")
            return
        self.push_undo()
        eliminado = self.seleccionado.field_id
        self.formato.fields = [c for c in self.formato.fields if c.field_id != eliminado]
        self.formato.ordenar_campos()
        self.seleccionado = None
        self.editor.cargar_plantilla(self._visual_template_path)
        self.estado.text = "Campo eliminado."

    def mostrar_lista_campos(self):
        if not self.formato:
            self._aviso("Primero importe una plantilla.")
            return
        panel = ModalView(size_hint=(0.92, 0.9), background_color=(0.05, 0.05, 0.05, 0.98), background="")
        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        encabezado = BoxLayout(size_hint_y=None, height=dp(50))
        encabezado.add_widget(Label(text="LISTA DE CAMPOS", font_size="19sp"))
        encabezado.add_widget(Button(text="×", size_hint_x=None, width=dp(48), on_release=lambda _: panel.dismiss()))
        root.add_widget(encabezado)
        scroll = ScrollView()
        lista = GridLayout(cols=1, spacing=dp(4), size_hint_y=None)
        lista.bind(minimum_height=lista.setter("height"))
        for campo in sorted(self.formato.fields, key=lambda c: c.order):
            b = Button(
                text="%02d   %s   —   %s" % (campo.order, campo.field_id, campo.question or "(sin pregunta)"),
                size_hint_y=None,
                height=dp(52),
                halign="left",
            )
            b.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - dp(15), val[1])))
            b.bind(on_release=lambda _, c=campo: (panel.dismiss(), self.seleccionar(c)))
            lista.add_widget(b)
        scroll.add_widget(lista)
        root.add_widget(scroll)
        root.add_widget(Button(text="Cerrar", size_hint_y=None, height=dp(46), on_release=lambda _: panel.dismiss()))
        panel.add_widget(root)
        panel.open()
        self.estado.text = "%d campo(s)." % len(self.formato.fields)

    def mostrar_propiedades(self, campo):
        if not campo:
            self._aviso("Seleccione un campo.")
            return

        contenido = BoxLayout(orientation="vertical", spacing=dp(5), padding=dp(8))
        scroll = ScrollView()
        form = GridLayout(cols=1, spacing=dp(5), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        def campo_texto(titulo, valor, multiline=False):
            form.add_widget(Label(text=titulo, size_hint_y=None, height=dp(25), halign="left"))
            entrada = TextInput(text=str(valor), multiline=multiline, size_hint_y=None, height=dp(42 if not multiline else 70))
            form.add_widget(entrada)
            return entrada

        id_input = campo_texto("ID", campo.field_id)
        pregunta = campo_texto("Pregunta para el capturador", campo.question, True)
        requerido = campo_texto("Obligatorio (si/no)", "si" if campo.required else "no")
        x_in = campo_texto("X", campo.position.x)
        y_in = campo_texto("Y", campo.position.y)
        w_in = campo_texto("Ancho", campo.position.width)
        h_in = campo_texto("Alto", campo.position.height)

        fuente = None
        tamano = None
        color_r = color_g = color_b = None
        alineacion = orientacion = None
        negrita = cursiva = None
        if campo.field_type != FIELD_TYPE_IMAGE:
            fuente = campo_texto("Tipografía (nombre o ruta .ttf/.otf)", campo.text_style.font_family)
            tamano = campo_texto("Tamaño en px", campo.text_style.font_size_px)
            color_r = campo_texto("Color R", campo.text_style.color.r)
            color_g = campo_texto("Color G", campo.text_style.color.g)
            color_b = campo_texto("Color B", campo.text_style.color.b)
            alineacion = campo_texto("Alineación", campo.text_style.alignment)
            orientacion = campo_texto("Orientación", campo.text_style.orientation)
            negrita = campo_texto("Negrita (si/no)", "si" if campo.text_style.bold else "no")
            cursiva = campo_texto("Cursiva (si/no)", "si" if campo.text_style.italic else "no")

        scroll.add_widget(form)
        contenido.add_widget(scroll)
        botones = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))

        def entero(entrada, actual):
            try:
                return int(float(entrada.text))
            except Exception:
                return actual

        def aceptar(_):
            nuevo_id = id_input.text.strip() or campo.field_id
            if any(c is not campo and c.field_id == nuevo_id for c in self.formato.fields):
                self._aviso("El ID ya existe.")
                return
            self.push_undo()
            campo.field_id = nuevo_id
            campo.question = pregunta.text.strip()
            campo.required = requerido.text.strip().lower() in ("si", "sí", "yes", "1", "true")
            campo.position.x = max(0, entero(x_in, campo.position.x))
            campo.position.y = max(0, entero(y_in, campo.position.y))
            campo.position.width = max(2, entero(w_in, campo.position.width))
            campo.position.height = max(2, entero(h_in, campo.position.height))
            campo.position.width = min(campo.position.width, self.formato.template.width - campo.position.x)
            campo.position.height = min(campo.position.height, self.formato.template.height - campo.position.y)

            if campo.field_type == FIELD_TYPE_NUMBER:
                campo.validation.numeric_only = True
                campo.validation.alphanumeric_only = False
            elif campo.field_type == FIELD_TYPE_ALPHANUMERIC:
                campo.validation.numeric_only = False
                campo.validation.alphanumeric_only = True

            if campo.field_type != FIELD_TYPE_IMAGE:
                campo.text_style.font_family = fuente.text.strip()
                campo.text_style.font_size_px = max(1, entero(tamano, campo.text_style.font_size_px))
                campo.text_style.color = FieldColor(
                    max(0, min(255, entero(color_r, campo.text_style.color.r))),
                    max(0, min(255, entero(color_g, campo.text_style.color.g))),
                    max(0, min(255, entero(color_b, campo.text_style.color.b))),
                )
                if alineacion.text.strip() in ("left", "center", "right", "justify"):
                    campo.text_style.alignment = alineacion.text.strip()
                campo.text_style.orientation = orientacion.text.strip() or "horizontal"
                campo.text_style.bold = negrita.text.strip().lower() in ("si", "sí", "yes", "1", "true")
                campo.text_style.italic = cursiva.text.strip().lower() in ("si", "sí", "yes", "1", "true")

            self.formato.ordenar_campos()
            self.seleccionado = campo
            self.editor.cargar_plantilla(self._visual_template_path)
            popup.dismiss()
            self.estado.text = "Campo %d configurado." % campo.order

        botones.add_widget(Button(text="Cancelar", on_release=lambda _: popup.dismiss()))
        botones.add_widget(Button(text="Aceptar", on_release=aceptar))
        contenido.add_widget(botones)
        popup = Popup(title="Propiedades del campo", content=contenido, size_hint=(0.94, 0.94))
        popup.open()

    def editar_salida(self):
        if not self.formato:
            self._aviso("Primero importe una plantilla.")
            return
        actual = self.formato.output_naming
        layout = BoxLayout(orientation="vertical", spacing=dp(7), padding=dp(10))
        nombre = TextInput(text=actual.name_text, hint_text="Texto fijo para el nombre", multiline=False, size_hint_y=None, height=dp(42))
        layout.add_widget(Label(text="Texto fijo del nombre"))
        layout.add_widget(nombre)
        for i in range(4):
            campo_actual = actual.field_ids[i] if i < len(actual.field_ids) else ""
            selector = TextInput(text=campo_actual, hint_text="ID de campo (opcional)", multiline=False, size_hint_y=None, height=dp(42))
            layout.add_widget(Label(text="Campo %d del nombre" % (i + 1)))
            layout.add_widget(selector)
            if i == 0:
                s1 = selector
            elif i == 1:
                s2 = selector
            elif i == 2:
                s3 = selector
            else:
                s4 = selector
        def aceptar(_):
            self.push_undo()
            actual.name_text = nombre.text.strip()
            actual.field_ids = [s.text.strip() for s in (s1, s2, s3, s4) if s.text.strip()]
            popup.dismiss()
            self.estado.text = "Reglas de nombre actualizadas."
        botones = BoxLayout(size_hint_y=None, height=dp(45), spacing=dp(6))
        botones.add_widget(Button(text="Cancelar", on_release=lambda _: popup.dismiss()))
        botones.add_widget(Button(text="Aceptar", on_release=aceptar))
        layout.add_widget(botones)
        popup = Popup(title="Archivo terminado", content=layout, size_hint=(0.92, 0.78))
        popup.open()

    def redraw_drawing_preview(self, start, end):
        self.clear_drawing_preview()
        if not self.editor.template_widget:
            return
        x0, y0 = start
        x1, y1 = end
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        tw = self.editor.template_widget
        x = tw.x + left * self.scale
        y = tw.y + tw.height - bottom * self.scale
        w = max(1, (right - left) * self.scale)
        h = max(1, (bottom - top) * self.scale)
        widget = FloatLayout(size_hint=(None, None), size=(w, h), pos=(x, y))
        with widget.canvas:
            Color(0, 0, 0, 1)
            Line(rectangle=(0, 0, w, h), width=3)
        self._drawing_widget = widget
        self.editor.add_widget(widget)

    def clear_drawing_preview(self):
        if self._drawing_widget and self._drawing_widget.parent:
            self._drawing_widget.parent.remove_widget(self._drawing_widget)
        self._drawing_widget = None

    def set_zoom(self, value):
        if not self.formato:
            return
        self.scale = max(0.05, min(5.0, value))
        self.editor.scale = self.scale
        self.editor.cargar_plantilla(self._visual_template_path)
        self.actualizar_zoom()

    def actualizar_zoom(self):
        if self.zoom_label:
            self.zoom_label.text = "%d %%" % int(round(self.scale * 100))

    def actualizar_lista_estado(self):
        if self.formato:
            self.estado.text = "%d campo(s)." % len(self.formato.fields)
        else:
            self.estado.text = "Listo."

    def _aviso(self, mensaje):
        Popup(title="Formatos Traducidos", content=Label(text=mensaje), size_hint=(0.8, 0.3)).open()


if __name__ == "__main__":
    ConfiguradorApp().run()
