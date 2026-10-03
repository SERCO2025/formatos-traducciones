# -*- coding: utf-8 -*-
import os
import uuid

from kivy.app import App
from kivy.graphics import Color, Line, Rectangle
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.filechooser import FileChooserListView
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.label import Label
from kivy.uix.modalview import ModalView
from kivy.uix.popup import Popup
from kivy.uix.textinput import TextInput
from kivy.uix.image import Image as KivyImage

try:
    from android import activity
    from jnius import autoclass
    ANDROID_AVAILABLE = True
except Exception:
    activity = None
    ANDROID_AVAILABLE = False

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
    def __init__(self, campo, scale=1.0, template_widget=None, **kwargs):
        super().__init__(**kwargs)
        self.campo = campo
        self.scale = scale
        self.template_widget = template_widget
        self.size_hint = (None, None)
        self.actualizar()

    def actualizar(self):
        p = self.campo.position
        self.size = (p.width * self.scale, p.height * self.scale)

        if self.template_widget is not None:
            # El modelo FDT usa coordenadas con origen arriba-izquierda.
            # Kivy usa origen abajo-izquierda, por lo que hay que invertir
            # el eje Y y respetar la posicion real de la plantilla.
            x = self.template_widget.x + p.x * self.scale
            y = self.template_widget.y + self.template_widget.height - (p.y + p.height) * self.scale
            self.pos = (x, y)
        else:
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
            self.add_widget(CampoWidget(campo, self.scale, self.template_widget))

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
        self._visual_template_path = None
        self._android_callback = None
        if ANDROID_AVAILABLE:
            activity.bind(on_activity_result=self._on_android_activity_result)

    def build(self):
        root = BoxLayout(orientation="vertical")

        barra = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6), padding=(dp(6), dp(5)))
        barra.add_widget(Button(text="☰", size_hint_x=None, width=dp(58), font_size="28sp", on_release=lambda _: self.abrir_menu()))
        titulo = Label(text="Configurador de Formatos", halign="left", valign="middle", font_size="17sp")
        titulo.bind(size=lambda instancia, valor: setattr(instancia, "text_size", valor))
        barra.add_widget(titulo)
        self.estado_menu = Label(text="Listo", size_hint_x=None, width=dp(72), font_size="12sp", halign="right", valign="middle")
        self.estado_menu.bind(size=lambda instancia, valor: setattr(instancia, "text_size", valor))
        barra.add_widget(self.estado_menu)
        root.add_widget(barra)

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

    def abrir_menu(self):
        panel = ModalView(size_hint=(0.86, 1), pos_hint={"x": 0, "y": 0}, auto_dismiss=True, background_color=(0.05, 0.05, 0.05, 0.98), background="")
        contenido = BoxLayout(orientation="vertical", spacing=dp(7), padding=dp(10))
        encabezado = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        encabezado.add_widget(Label(text="MENÚ", font_size="20sp", halign="left", valign="middle"))
        encabezado.add_widget(Button(text="×", size_hint_x=None, width=dp(48), font_size="24sp", on_release=lambda _: panel.dismiss()))
        contenido.add_widget(encabezado)

        def seccion(texto):
            contenido.add_widget(Label(text=texto, size_hint_y=None, height=dp(30), halign="left", valign="middle", font_size="13sp"))

        def opcion(texto, accion):
            boton = Button(text=texto, size_hint_y=None, height=dp(48), halign="left", valign="middle", font_size="15sp")
            boton.bind(size=lambda instancia, valor: setattr(instancia, "text_size", (valor[0] - dp(20), valor[1])))
            boton.bind(on_release=lambda _: (panel.dismiss(), accion()))
            contenido.add_widget(boton)

        seccion("ARCHIVO")
        opcion("Nuevo formato", self.nuevo)
        opcion("Abrir formato FDT", self.abrir)
        opcion("Importar plantilla", self.importar)
        opcion("Guardar", self.guardar)
        opcion("Guardar como FDT", self.guardar_como_fdt)
        seccion("HERRAMIENTAS")
        opcion("Seleccionar", lambda: self.set_tool("select"))
        opcion("Texto", lambda: self.set_tool(FIELD_TYPE_TEXT))
        opcion("Número", lambda: self.set_tool(FIELD_TYPE_NUMBER))
        opcion("Alfanumérico", lambda: self.set_tool(FIELD_TYPE_ALPHANUMERIC))
        opcion("Imagen", lambda: self.set_tool(FIELD_TYPE_IMAGE))
        opcion("Zoom", lambda: self.set_tool("zoom"))
        seccion("VISTA")
        opcion("Alejar", lambda: self.set_zoom(self.scale * 0.8))
        opcion("Acercar", lambda: self.set_zoom(self.scale * 1.25))
        opcion("Restablecer zoom", lambda: self.set_zoom(1.0))
        contenido.add_widget(Label(text="Configurador de Formatos Traducidos", size_hint_y=None, height=dp(38), font_size="11sp"))
        panel.add_widget(contenido)
        panel.open()

    def mostrar_lista_campos(self):
        self.estado.text = "Lista de campos: función disponible en la siguiente actualización."
        self.estado_menu.text = "Campos"

    def deshacer(self):
        self.estado.text = "Deshacer: función disponible en la siguiente actualización."
        self.estado_menu.text = "Editar"

    def rehacer(self):
        self.estado.text = "Rehacer: función disponible en la siguiente actualización."
        self.estado_menu.text = "Editar"

    def set_tool(self, tool):
        self.tool = tool
        self.estado.text = "Herramienta: " + str(tool)
        self.estado_menu.text = str(tool)

    def nuevo(self):
        self.formato = None
        self.seleccionado = None
        self._visual_template_path = None
        self.editor.clear_widgets()
        self.estado.text = "Nuevo formato."

    def importar(self):
        if ANDROID_AVAILABLE:
            self._abrir_selector_android("image", guardar=False)
        else:
            self._file_popup("Importar plantilla", self._importar_ruta, imagenes=True)

    def _abrir_selector_android(self, tipo, guardar=False):
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(
                Intent.ACTION_CREATE_DOCUMENT if guardar else Intent.ACTION_OPEN_DOCUMENT
            )
            if tipo == "image":
                intent.setType("image/*")
            else:
                # Los FDT son contenedores ZIP con extension .fdt. No todos
                # los gestores de archivos Android registran ese MIME, por
                # lo que se usa */* para no ocultar los archivos.
                intent.setType("*/*")

            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if not guardar:
                intent.addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            else:
                nombre = "formato.fdt"
                if self.formato and self.formato.name.strip():
                    nombre = self.formato.name.strip() + ".fdt"
                intent.putExtra(Intent.EXTRA_TITLE, nombre)

            self._android_callback = (tipo, guardar)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            actividad = PythonActivity.mActivity
            actividad.startActivityForResult(intent, 4001)
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
                self.estado.text = "No se recibió ningún archivo del selector de Android."
                return

            if guardar:
                self._guardar_fdt_uri(uri)
                return

            ruta = self._copiar_uri_a_cache(uri, tipo)
            if tipo == "image":
                self._importar_ruta(ruta)
            elif tipo == "fdt":
                self._abrir_ruta(ruta)
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
                if indice >= 0 and cursor.moveToFirst():
                    valor = cursor.getString(indice)
                    return str(valor or "")
            finally:
                cursor.close()
        except Exception:
            return ""
        return ""

    def _copiar_uri_a_cache(self, uri, tipo):
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        actividad = PythonActivity.mActivity
        resolver = actividad.getContentResolver()
        flujo = resolver.openInputStream(uri)
        if flujo is None:
            raise IOError("Android no pudo abrir el archivo seleccionado.")

        try:
            nombre_original = self._nombre_display_uri(resolver, uri)
            extension = os.path.splitext(nombre_original)[1].lower()

            if tipo == "image" and not extension:
                mime = resolver.getType(uri)
                extensiones = {
                    "image/jpeg": ".jpg",
                    "image/png": ".png",
                    "image/bmp": ".bmp",
                    "image/webp": ".webp",
                    "image/tiff": ".tif",
                }
                extension = extensiones.get(str(mime or "").lower(), ".jpg")
            elif tipo == "fdt":
                extension = ".fdt"

            if not extension:
                extension = ".bin"

            nombre = "archivo_importado_" + uuid.uuid4().hex + extension
            ruta = os.path.join(
                actividad.getCacheDir().getAbsolutePath(),
                nombre,
            )

            # Usamos un byte[] Java real para evitar problemas de conversion
            # entre bytearray de Python y java.io.InputStream en distintos
            # dispositivos/versiones de Android.
            from jnius import jarray
            buffer = jarray("b", [0] * 65536)
            salida = open(ruta, "wb")
            try:
                while True:
                    cantidad = flujo.read(buffer)
                    if cantidad <= 0:
                        break
                    salida.write(bytes(buffer[:cantidad]))
            finally:
                salida.close()

            if not os.path.isfile(ruta) or os.path.getsize(ruta) <= 0:
                raise IOError("El archivo seleccionado está vacío o no pudo copiarse.")
            return ruta
        finally:
            flujo.close()

    def _guardar_fdt_uri(self, uri):
        if not self.formato:
            self.estado.text = "Primero importe una plantilla."
            return

        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        actividad = PythonActivity.mActivity
        resolver = actividad.getContentResolver()
        temporal = os.path.join(
            actividad.getCacheDir().getAbsolutePath(),
            "fdt_guardado_" + uuid.uuid4().hex + ".fdt",
        )

        try:
            validar_fdt(self.formato)
            guardar_fdt(self.formato, temporal)

            entrada = open(temporal, "rb")
            salida = resolver.openOutputStream(uri)
            if salida is None:
                raise IOError("Android no pudo abrir el destino para guardar el FDT.")

            try:
                from jnius import jarray
                buffer = jarray("b", [0] * 65536)
                while True:
                    datos = entrada.read(65536)
                    if not datos:
                        break
                    salida.write(jarray("b", datos))
            finally:
                entrada.close()
                salida.close()

            self.estado.text = "FDT guardado correctamente en el archivo seleccionado."
        finally:
            try:
                if os.path.exists(temporal):
                    os.remove(temporal)
            except OSError:
                pass

    def _crear_imagen_visual(self, ruta, imagen):
        """
        Crea una copia PNG RGB exclusivamente para la vista de Kivy.
        El archivo original sigue siendo la plantilla real del FDT.
        Esto evita problemas de decodificacion de JPG/PNG desde algunos
        proveedores de documentos de Android.
        """
        visual = os.path.join(
            os.path.dirname(ruta),
            "vista_" + uuid.uuid4().hex + ".png",
        )
        imagen.save(visual, format="PNG")
        if not os.path.isfile(visual) or os.path.getsize(visual) <= 0:
            raise IOError("No se pudo crear la imagen de vista previa.")
        return visual

    def _importar_ruta(self, ruta):
        try:
            from PIL import Image

            imagen = Image.open(ruta).convert("RGB")
            visual_ruta = self._crear_imagen_visual(ruta, imagen)

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
            self._visual_template_path = visual_ruta
            self.editor.cargar_plantilla(self._visual_template_path)
            self.actualizar_zoom()
            self.estado.text = "Plantilla importada: %d × %d px" % (imagen.width, imagen.height)
        except Exception as exc:
            self.estado.text = "Error al importar: " + str(exc)

    def abrir(self):
        if ANDROID_AVAILABLE:
            self._abrir_selector_android("fdt", guardar=False)
        else:
            self._file_popup("Abrir FDT", self._abrir_ruta)

    def _abrir_ruta(self, ruta):
        try:
            from shared.fdt import cargar_fdt
            self.formato = cargar_fdt(ruta)
            from PIL import Image
            imagen = Image.open(self.formato.template.path).convert("RGB")
            self._visual_template_path = self._crear_imagen_visual(self.formato.template.path, imagen)
            self.scale = min(1.0, 0.8 * min(
                (self.width - dp(40)) / self.formato.template.width,
                (self.height - dp(140)) / self.formato.template.height,
            ))
            self.scale = max(0.05, self.scale)
            self.editor.scale = self.scale
            self.editor.cargar_plantilla(self._visual_template_path or self.formato.template.path)
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
        if ANDROID_AVAILABLE:
            self._abrir_selector_android("fdt", guardar=True)
        else:
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
