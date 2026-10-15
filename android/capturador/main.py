# -*- coding: utf-8 -*-
"""Rellenador Android de Formatos Traducidos.

Porta el flujo funcional del capturador de PC y reutiliza el motor compartido:
FDT, modelos, validaciones y renderizado. Los archivos se seleccionan/exportan
mediante el selector de documentos de Android (Storage Access Framework).
"""
import json
import os
import re
import tempfile
import time
import traceback
import zipfile
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.graphics import Color, Line, Rectangle
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.checkbox import CheckBox
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput


class GradientExitButton(Button):
    """Botón rojo con degradado vertical y bisel que se invierte al presionar."""

    def __init__(self, **kwargs):
        kwargs.setdefault("text", "Salir")
        kwargs.setdefault("font_size", "22sp")
        kwargs.setdefault("bold", True)
        kwargs.setdefault("color", (1, 1, 1, 1))
        kwargs.setdefault("size_hint_y", None)
        kwargs.setdefault("height", dp(62))
        kwargs.setdefault("background_normal", "")
        kwargs.setdefault("background_down", "")
        kwargs.setdefault("background_color", (0, 0, 0, 0))
        super().__init__(**kwargs)
        self._bandas = []
        with self.canvas.before:
            for color in (
                (1.0, .30, .30, 1), (.96, .20, .20, 1),
                (.88, .09, .09, 1), (.76, .035, .035, 1),
                (.62, 0, 0, 1), (.43, 0, 0, 1),
            ):
                instruccion_color = Color(*color)
                rectangulo = Rectangle(pos=self.pos, size=self.size)
                self._bandas.append((instruccion_color, rectangulo))
            self._borde_color = Color(.30, 0, 0, 1)
            self._borde = Line(rectangle=(self.x, self.y, self.width, self.height), width=2)
            self._bisel_color = Color(1, .55, .55, 1)
            self._bisel = Line(points=[self.x, self.y, self.x + self.width, self.y], width=3)
        self.bind(pos=self._actualizar_dibujo, size=self._actualizar_dibujo, state=self._actualizar_dibujo)
        self._actualizar_dibujo()

    def _actualizar_dibujo(self, *_):
        if not self._bandas:
            return
        presionado = self.state == "down"
        alto = max(1, self.height / float(len(self._bandas)))
        for i, (color, rectangulo) in enumerate(self._bandas):
            y = self.y + ((len(self._bandas) - 1 - i) * alto if not presionado else i * alto)
            rectangulo.pos = (self.x + dp(3), y + dp(2))
            rectangulo.size = (max(1, self.width - dp(6)), alto + dp(1))
        self._borde_color.rgba = (.95, .35, .35, 1) if presionado else (.25, 0, 0, 1)
        self._borde.rectangle = (self.x + dp(2), self.y + dp(2), self.width - dp(4), self.height - dp(4))
        self._bisel_color.rgba = (.30, 0, 0, 1) if presionado else (1, .65, .65, 1)
        y_bisel = self.y + (dp(5) if presionado else self.height - dp(5))
        self._bisel.points = [self.x + dp(8), y_bisel, self.x + self.width - dp(8), y_bisel]


class PinchZoomScrollView(ScrollView):
    """ScrollView con zoom de pellizco para la vista previa final."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._zoom_image = None
        self._base_size = None
        self._zoom = 1.0
        self._pinch_touches = {}
        self._pinch_active = False
        self._pinch_start_distance = 0.0
        self._pinch_start_zoom = 1.0

    def configurar_imagen_zoom(self, image_widget, base_size):
        self._zoom_image = image_widget
        self._base_size = base_size
        self._zoom = 1.0
        self._aplicar_zoom()

    def _distancia_pellizco(self):
        if len(self._pinch_touches) < 2:
            return 0.0
        a, b = list(self._pinch_touches.values())[:2]
        return max(1.0, ((b.x - a.x) ** 2 + (b.y - a.y) ** 2) ** 0.5)

    def _aplicar_zoom(self):
        if self._zoom_image is None or self._base_size is None:
            return
        self._zoom_image.size = (
            max(1, self._base_size[0] * self._zoom),
            max(1, self._base_size[1] * self._zoom),
        )

    def on_touch_down(self, touch):
        dentro = self.collide_point(*touch.pos)
        if dentro:
            self._pinch_touches[touch.uid] = touch
            if len(self._pinch_touches) >= 2:
                self._pinch_active = True
                self._pinch_start_distance = self._distancia_pellizco()
                self._pinch_start_zoom = self._zoom
                touch.grab(self)
                return True
        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.uid in self._pinch_touches:
            self._pinch_touches[touch.uid] = touch
            if self._pinch_active and len(self._pinch_touches) >= 2:
                distancia = self._distancia_pellizco()
                if self._pinch_start_distance > 0:
                    factor = distancia / self._pinch_start_distance
                    self._zoom = max(0.25, min(5.0, self._pinch_start_zoom * factor))
                    self._aplicar_zoom()
                return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        estaba_en_pellizco = self._pinch_active
        if touch.uid in self._pinch_touches:
            self._pinch_touches.pop(touch.uid, None)
        if touch.grab_current is self:
            touch.ungrab(self)
        if estaba_en_pellizco:
            if len(self._pinch_touches) < 2:
                self._pinch_active = False
                self._pinch_start_distance = 0.0
            return True
        return super().on_touch_up(touch)

from PIL import Image as PILImage

from shared.fdt import cargar_fdt
from shared.models import FIELD_TYPE_IMAGE
from shared.renderer import construir_nombre_archivo, renderizar_imagen
from shared.validators import validar_respuesta, validar_todas_las_respuestas

try:
    from jnius import autoclass
    from android import activity
    ANDROID_NATIVE = True
except Exception:
    ANDROID_NATIVE = False


class CapturadorApp(App):
    title = "Formatos Traducidos - Capturador Android"

    REQUEST_OPEN_FDT = 731
    REQUEST_OPEN_IMAGE = 732
    REQUEST_SAVE_JPEG = 733
    REQUEST_OPEN_DRAFT = 734
    REQUEST_SAVE_JPEG_FOLDER = 735
    REQUEST_SAVE_DRAFT_FOLDER = 736
    REQUEST_CONFIG_OUTPUT_FOLDER = 737

    def build(self):
        self._popup_salida = None
        Window.bind(on_keyboard=self._manejar_tecla_android)
        self.formato = None
        self.respuestas = {}
        self.indice = 0
        self._uri_accion = None
        self._imagen_final = None
        self._nombre_final = "resultado.jpg"
        self._preview_file = None
        self._temp_files = []
        self._fdt_path = None
        self._draft_dirs = []
        self._save_jpeg_folder_uri = None
        self._retention_days = 7
        self._cleanup_enabled = True
        self._generated_files = {}
        self._settings_file = os.path.join(self.user_data_dir, "output_settings.json")
        self._legacy_save_folder_config = os.path.join(self.user_data_dir, "save_jpeg_folder.json")
        self._cargar_configuracion_salida()
        Clock.schedule_once(lambda _dt: self._limpiar_archivos_vencidos(), 2)

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        encabezado = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(6))
        encabezado.add_widget(Label(
            text="Formatos Traducidos",
            font_size="22sp", bold=True, halign="left",
        ))
        self.btn_configuracion = Button(
            text="Configuración", size_hint=(None, None),
            width=dp(104), height=dp(33), font_size="11sp",
        )
        self.btn_configuracion.bind(on_release=lambda *_: self._mostrar_configuracion())
        encabezado.add_widget(self.btn_configuracion)
        # Botón Salir en la esquina superior derecha.
        self.btn_salir = Button(
            text="Salir", size_hint=(None, None),
            width=dp(60), height=dp(33), font_size="7.5sp", bold=True,
        )
        self.btn_salir.bind(on_release=lambda *_: self._confirmar_salida())
        encabezado.add_widget(self.btn_salir)
        root.add_widget(encabezado)
        self.estado = Label(
            text="Abra un formato .fdt para comenzar.",
            size_hint_y=None, height=dp(42),
            font_size="14sp", halign="left", valign="middle",
        )
        self.estado.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        root.add_widget(self.estado)

        self.pregunta = Label(
            text="Seleccione un formato .fdt",
            size_hint_y=None, height=dp(68),
            font_size="20sp", bold=True, halign="left", valign="middle",
        )
        self.pregunta.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        root.add_widget(self.pregunta)

        self.entrada = TextInput(
            text="", multiline=True, size_hint_y=None, height=dp(115),
            font_size="18sp", hint_text="Escriba la respuesta aquí",
        )
        self.entrada.bind(text=self._entrada_cambio)
        root.add_widget(self.entrada)

        self.info_imagen = Label(
            text="", size_hint_y=None, height=dp(34),
            font_size="12sp", halign="left", valign="middle",
        )
        self.info_imagen.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        root.add_widget(self.info_imagen)

        preview_scroll = ScrollView(size_hint=(1, 1), do_scroll_x=False)
        self.preview = Image(
            allow_stretch=True, keep_ratio=True,
            size_hint=(1, None), height=dp(250),
        )
        preview_scroll.add_widget(self.preview)
        root.add_widget(preview_scroll)

        controls_open = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        self.btn_abrir = Button(text="Abrir formato .FDT", font_size="15sp")
        self.btn_abrir.bind(on_release=lambda *_: self.abrir_formato())
        controls_open.add_widget(self.btn_abrir)
        self.btn_imagen = Button(text="Elegir foto", font_size="15sp", disabled=True)
        self.btn_imagen.bind(on_release=lambda *_: self.seleccionar_imagen())
        controls_open.add_widget(self.btn_imagen)
        root.add_widget(controls_open)

        controls_draft = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        self.btn_abrir_avance = Button(text="Abrir avance", font_size="14sp")
        self.btn_abrir_avance.bind(on_release=lambda *_: self.abrir_avance())
        controls_draft.add_widget(self.btn_abrir_avance)
        self.btn_guardar_avance = Button(text="Guardar avance", font_size="14sp", disabled=True)
        self.btn_guardar_avance.bind(on_release=lambda *_: self.guardar_avance())
        controls_draft.add_widget(self.btn_guardar_avance)
        root.add_widget(controls_draft)

        controls_nav = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.btn_atras = Button(text="Volver", font_size="17sp", disabled=True)
        self.btn_atras.bind(on_release=lambda *_: self.anterior())
        controls_nav.add_widget(self.btn_atras)
        self.btn_siguiente = Button(text="Continuar", font_size="17sp", disabled=True)
        self.btn_siguiente.bind(on_release=lambda *_: self.siguiente())
        controls_nav.add_widget(self.btn_siguiente)
        root.add_widget(controls_nav)

        # El botón Salir ya está aislado en el encabezado superior derecho.

        if ANDROID_NATIVE:
            try:
                activity.bind(on_activity_result=self._on_activity_result)
            except Exception:
                pass
        else:
            self.estado.text = "Entorno de prueba: los selectores requieren Android."
        return root

    def _manejar_tecla_android(self, window, key, scancode, codepoint, modifiers):
        # El botón Atrás de Android nunca cierra la aplicación.
        # Si está abierta la confirmación, solo la descarta y vuelve al capturador.
        if key in (27, 1001):
            popup = getattr(self, "_popup_salida", None)
            if popup is not None and popup.parent is not None:
                popup.dismiss()
            return True
        return False

    def _confirmar_salida(self):
        contenido = BoxLayout(
            orientation="vertical", padding=(dp(18), dp(18)),
            spacing=dp(10),
        )
        contenido.canvas.before.clear()
        with contenido.canvas.before:
            Color(0, 0, 0, 1)
            fondo = Rectangle(pos=contenido.pos, size=contenido.size)
        contenido.bind(pos=lambda obj, value: setattr(fondo, "pos", value))
        contenido.bind(size=lambda obj, value: setattr(fondo, "size", value))

        encabezado = Label(
            text="Confirma para salir", color=(1, 1, 0, 1),
            font_size="26sp", bold=True, size_hint_y=None, height=dp(48),
            halign="center", valign="middle",
        )
        encabezado.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        contenido.add_widget(encabezado)

        aviso = Label(
            text="Recuerda grabar los avances o se perdera toda la informacion capturada",
            color=(1, 1, 1, 1), font_size="14sp",
            size_hint_y=None, height=dp(54), halign="center", valign="middle",
        )
        aviso.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        contenido.add_widget(aviso)

        instruccion = Label(
            text="para cerrar presione el boton rojo",
            color=(1, 1, 1, 1), font_size="14sp",
            size_hint_y=None, height=dp(30), halign="center", valign="middle",
        )
        instruccion.bind(size=lambda obj, size: setattr(obj, "text_size", size))
        contenido.add_widget(instruccion)

        boton = GradientExitButton()
        contenido.add_widget(boton)
        popup = Popup(
            title="", content=contenido, size_hint=(0.94, None),
            height=dp(300), auto_dismiss=True, background="",
            background_color=(0, 0, 0, 1), separator_height=0,
        )
        self._popup_salida = popup
        popup.bind(on_dismiss=lambda *_: setattr(self, "_popup_salida", None))
        def salir_confirmado(*_):
            popup.dismiss()
            App.get_running_app().stop()
        boton.bind(on_release=salir_confirmado)
        popup.open()

    def _mensaje(self, titulo, mensaje):
        # Los tracebacks largos deben poder desplazarse; el Label anterior
        # quedaba recortado y ocultaba precisamente la excepción final.
        contenido = BoxLayout(orientation="vertical", padding=dp(10), spacing=dp(8))
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True, bar_width=dp(8))
        texto = Label(
            text=str(mensaje),
            halign="left",
            valign="top",
            size_hint_y=None,
            font_size="12sp",
            text_size=(dp(320), None),
        )
        def ajustar_ancho(obj, ancho):
            obj.text_size = (max(dp(220), ancho - dp(8)), None)
        def ajustar_alto(obj, textura):
            obj.height = textura[1] + dp(16)
        texto.bind(width=ajustar_ancho, texture_size=ajustar_alto)
        scroll.add_widget(texto)
        contenido.add_widget(scroll)
        boton = Button(text="Aceptar", size_hint_y=None, height=dp(46))
        contenido.add_widget(boton)
        popup = Popup(title=titulo, content=contenido, size_hint=(0.96, 0.82), auto_dismiss=False)
        boton.bind(on_release=popup.dismiss)
        popup.open()

    def _intent(self, request_code, action, mime, title=None):
        if not ANDROID_NATIVE:
            self._mensaje("No disponible", "Esta operación requiere el selector de archivos de Android.")
            return
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(action)
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.setType(mime)
            if title:
                intent.putExtra(Intent.EXTRA_TITLE, title)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PythonActivity.mActivity.startActivityForResult(intent, request_code)
        except Exception as exc:
            self._mensaje("No se pudo abrir el selector", str(exc))

    def abrir_formato(self):
        self._intent(self.REQUEST_OPEN_FDT, "android.intent.action.OPEN_DOCUMENT", "*/*")

    def abrir_avance(self):
        self._intent(self.REQUEST_OPEN_DRAFT, "android.intent.action.OPEN_DOCUMENT", "*/*")

    def seleccionar_imagen(self):
        self._intent(self.REQUEST_OPEN_IMAGE, "android.intent.action.OPEN_DOCUMENT", "image/*")

    def _on_activity_result(self, request_code, result_code, intent):
        try:
            Activity = autoclass("android.app.Activity")
            if result_code != Activity.RESULT_OK or intent is None:
                return
            uri = intent.getData()
            if uri is None:
                self._mensaje("Error", "Android no devolvió la ubicación del archivo.")
                return
            uri_text = str(uri.toString())
            if request_code == self.REQUEST_OPEN_FDT:
                ruta = self._copiar_uri_a_cache(uri, ".fdt")
                try:
                    formato = cargar_fdt(ruta)
                except Exception as exc:
                    self._mensaje("No se pudo abrir el formato", "%s\n\n%s" % (exc, traceback.format_exc()))
                    return
                self.formato = formato
                self._fdt_path = ruta
                self.respuestas = {campo.field_id: "" for campo in formato.fields}
                self.indice = 0
                self.btn_guardar_avance.disabled = False
                self._mostrar_campo()
            elif request_code == self.REQUEST_OPEN_DRAFT:
                ruta = self._copiar_uri_a_cache(uri, ".ftc")
                self._abrir_archivo_avance(ruta)
            elif request_code == self.REQUEST_CONFIG_OUTPUT_FOLDER:
                self._recordar_carpeta_destino(uri, intent)
                self._limpiar_archivos_vencidos()
                self._mostrar_configuracion()
            elif request_code == self.REQUEST_SAVE_DRAFT_FOLDER:
                ruta_avance = self._crear_archivo_avance_temporal()
                nombre_avance = os.path.splitext(
                    construir_nombre_archivo(self.formato, self.respuestas)
                )[0] + ".ftc"
                destino = self._crear_documento_en_carpeta(uri, "application/octet-stream", nombre_avance)
                self._copiar_archivo_a_uri(ruta_avance, destino)
                self._mensaje("Avance guardado", "La captura pendiente se guardó como:\n%s\n\nPuedes abrirla después con «Abrir avance»." % (self._nombre_documento_uri(destino) or nombre_avance))
            elif request_code == self.REQUEST_OPEN_IMAGE:
                ruta = self._copiar_uri_a_cache(uri, self._extension_uri(uri_text, ".jpg"))
                if not self.formato or not self.formato.fields:
                    return
                campo = self.formato.fields[self.indice]
                if campo.field_type != FIELD_TYPE_IMAGE:
                    self._mensaje("Campo incorrecto", "La pregunta actual no corresponde a una imagen.")
                    return
                self.respuestas[campo.field_id] = ruta
                self._mostrar_campo()
            elif request_code == self.REQUEST_SAVE_JPEG:
                if self._imagen_final is not None:
                    # Algunos proveedores Android ignoran EXTRA_TITLE. Si el
                    # nombre creado no coincide, renombramos el documento antes
                    # de copiar el JPEG para conservar el nombre del cliente.
                    uri_destino = self._ajustar_nombre_destino(uri, self._nombre_final)
                    self._copiar_archivo_a_uri(self._imagen_final, uri_destino)
                    nombre_guardado = self._nombre_documento_uri(uri_destino)
                    if nombre_guardado and nombre_guardado != self._nombre_final:
                        self._mensaje(
                            "Nombre de archivo",
                            "Android guardó el archivo como:\n%s\n\nNombre solicitado:\n%s"
                            % (nombre_guardado, self._nombre_final),
                        )
                    else:
                        self._mensaje(
                            "Archivo guardado",
                            "Se guardó el JPEG como:\n%s" % self._nombre_final,
                        )
        except Exception as exc:
            self._mensaje("Error al procesar el archivo", "%s\n\n%s" % (exc, traceback.format_exc()))

    def _extension_uri(self, uri, fallback):
        try:
            resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
            tipo = str(resolver.getType(uri) or "")
            if tipo == "image/png":
                return ".png"
            if tipo == "image/jpeg":
                return ".jpg"
        except Exception:
            pass
        return fallback

    def _copiar_uri_a_cache(self, uri, extension):
        contexto = autoclass("org.kivy.android.PythonActivity").mActivity
        resolver = contexto.getContentResolver()
        flujo = resolver.openInputStream(uri)
        if flujo is None:
            raise IOError("Android no pudo abrir el archivo seleccionado.")
        ruta = os.path.join(tempfile.gettempdir(), "fdt_android_%s%s" % (len(self._temp_files), extension))
        salida = None
        try:
            FileOutputStream = autoclass("java.io.FileOutputStream")
            salida = FileOutputStream(ruta)
            buffer = bytearray(65536)
            while True:
                cantidad = flujo.read(buffer)
                if cantidad <= 0:
                    break
                salida.write(buffer, 0, cantidad)
            salida.flush()
        finally:
            try:
                flujo.close()
            except Exception:
                pass
            if salida is not None:
                salida.close()
        self._temp_files.append(ruta)
        return ruta

    def _copiar_archivo_a_uri(self, ruta, uri):
        contexto = autoclass("org.kivy.android.PythonActivity").mActivity
        resolver = contexto.getContentResolver()
        salida = resolver.openOutputStream(uri, "w")
        if salida is None:
            raise IOError("Android no pudo crear el archivo de salida.")
        try:
            with open(ruta, "rb") as archivo:
                while True:
                    datos = archivo.read(65536)
                    if not datos:
                        break
                    salida.write(bytearray(datos), 0, len(datos))
                salida.flush()
        finally:
            salida.close()

    def _nombre_documento_uri(self, uri):
        """Devuelve el nombre real asignado por el proveedor de documentos."""
        contexto = autoclass("org.kivy.android.PythonActivity").mActivity
        resolver = contexto.getContentResolver()
        cursor = None
        try:
            OpenableColumns = autoclass("android.provider.OpenableColumns")
            cursor = resolver.query(uri, [OpenableColumns.DISPLAY_NAME], None, None, None)
            if cursor is not None and cursor.moveToFirst():
                indice = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if indice >= 0:
                    return str(cursor.getString(indice))
        except Exception:
            pass
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass
        return None

    def _ajustar_nombre_destino(self, uri, nombre_deseado):
        """Asegura el nombre definido por el FDT, incluso si el selector lo ignora."""
        actual = self._nombre_documento_uri(uri)
        if actual == nombre_deseado:
            return uri

        contexto = autoclass("org.kivy.android.PythonActivity").mActivity
        resolver = contexto.getContentResolver()
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        renombrado = DocumentsContract.renameDocument(resolver, uri, nombre_deseado)
        if renombrado is None:
            raise IOError(
                "Android no permitió asignar el nombre '%s'. "
                "Selecciona una carpeta de destino que permita renombrar archivos."
                % nombre_deseado
            )
        return renombrado

    def _entrada_cambio(self, *_):
        if self.formato and self.formato.fields and self.formato.fields[self.indice].field_type != FIELD_TYPE_IMAGE:
            Clock.unschedule(self._actualizar_preview)
            Clock.schedule_once(self._actualizar_preview, 0.25)

    def _guardar_respuesta_actual(self):
        if not self.formato or not self.formato.fields:
            return True
        campo = self.formato.fields[self.indice]
        if campo.field_type == FIELD_TYPE_IMAGE:
            return True
        respuesta = self.entrada.text
        if getattr(campo, "uppercase", False):
            respuesta = respuesta.upper()
            if self.entrada.text != respuesta:
                self.entrada.text = respuesta
        valido, mensaje = validar_respuesta(campo, respuesta)
        if not valido:
            self._mensaje("Respuesta no válida", mensaje)
            return False
        self.respuestas[campo.field_id] = respuesta
        return True

    def _mostrar_campo(self):
        if not self.formato or not self.formato.fields:
            return
        campo = self.formato.fields[self.indice]
        total = len(self.formato.fields)
        self.estado.text = "%s — Campo %d de %d" % (self.formato.name, self.indice + 1, total)
        self.pregunta.text = (campo.question or "").strip() or campo.field_id
        self.entrada.text = self.respuestas.get(campo.field_id, "")
        es_imagen = campo.field_type == FIELD_TYPE_IMAGE
        self.entrada.disabled = es_imagen
        self.entrada.hint_text = "Seleccione una imagen" if es_imagen else "Escriba la respuesta aquí"
        self.btn_imagen.disabled = not es_imagen
        self.info_imagen.text = (
            "Imagen seleccionada: " + self.respuestas.get(campo.field_id, "")
            if es_imagen and self.respuestas.get(campo.field_id, "")
            else ("No se ha seleccionado imagen." if es_imagen else "")
        )
        self.btn_atras.disabled = self.indice <= 0
        self.btn_siguiente.disabled = False
        self.btn_siguiente.text = "Finalizar" if self.indice == total - 1 else "Continuar"
        self._actualizar_preview()

    def anterior(self):
        if not self.formato or self.indice <= 0:
            return
        if not self._guardar_respuesta_actual():
            return
        self.indice -= 1
        self._mostrar_campo()

    def siguiente(self):
        if not self.formato or not self.formato.fields:
            self._mensaje("Abra un formato", "Primero seleccione un archivo .fdt.")
            return
        if not self._guardar_respuesta_actual():
            return
        if self.indice < len(self.formato.fields) - 1:
            self.indice += 1
            self._mostrar_campo()
            return
        errores = validar_todas_las_respuestas(self.formato, self.respuestas)
        if errores:
            mensajes = []
            for campo in self.formato.fields:
                if campo.field_id in errores:
                    mensajes.append("%s: %s" % (campo.question or campo.field_id, errores[campo.field_id]))
            self._mensaje("Revisar respuestas", "\n".join(mensajes))
            return
        self._mostrar_previsualizacion_final()

    def _actualizar_preview(self, *_):
        if not self.formato or not self.formato.fields:
            return
        try:
            respuestas = dict(self.respuestas)
            campo = self.formato.fields[self.indice]
            if campo.field_type != FIELD_TYPE_IMAGE and not self.entrada.disabled:
                respuestas[campo.field_id] = self.entrada.text
            imagen = renderizar_imagen(self.formato, respuestas)
            p = campo.position
            margen = max(20, min(100, int(max(p.width, p.height) * 0.2)))
            izquierda = max(0, p.x - margen)
            arriba = max(0, p.y - margen)
            derecha = min(imagen.width, p.x + p.width + margen)
            abajo = min(imagen.height, p.y + p.height + margen)
            recorte = imagen.crop((izquierda, arriba, derecha, abajo))
            ruta = os.path.join(tempfile.gettempdir(), "capturador_android_preview.png")
            recorte.save(ruta, format="PNG")
            self._mostrar_imagen(ruta)
        except Exception as exc:
            self.estado.text = "Vista previa no disponible: %s" % exc

    def _mostrar_imagen(self, ruta):
        self._preview_file = ruta
        try:
            self.preview.source = ruta
            self.preview.reload()
        except Exception:
            try:
                self.preview.texture = CoreImage(ruta).texture
            except Exception:
                pass

    def _mostrar_previsualizacion_final(self):
        try:
            self._imagen_final = os.path.join(tempfile.gettempdir(), "formatos_traducidos_resultado.jpg")
            imagen = renderizar_imagen(self.formato, self.respuestas)
            imagen.save(
                self._imagen_final, format="JPEG", quality=100, subsampling=0,
                dpi=(self.formato.template.dpi, self.formato.template.dpi),
            )
            self._nombre_final = construir_nombre_archivo(self.formato, self.respuestas)
            self._popup_final(imagen)
        except Exception as exc:
            self._mensaje("No se pudo generar el documento", "%s\n\n%s" % (exc, traceback.format_exc()))

    def _popup_final(self, imagen):
        contenido = BoxLayout(orientation="vertical", padding=dp(8), spacing=dp(8))
        scroll = PinchZoomScrollView(do_scroll_x=True, do_scroll_y=True, bar_width=dp(5))
        ruta_preview = os.path.join(tempfile.gettempdir(), "formatos_traducidos_final_preview.png")
        copia = imagen.copy()
        copia.thumbnail((1200, 1600), PILImage.Resampling.LANCZOS)
        copia.save(ruta_preview, format="PNG")
        vista = Image(
            source=ruta_preview, allow_stretch=True, keep_ratio=True,
            size_hint=(None, None), size=(dp(320), dp(420)),
        )
        scroll.add_widget(vista)
        contenido.add_widget(scroll)
        contenido.add_widget(Label(
            text="Archivo: %s\nTamaño original: %d × %d px | RGB | JPEG calidad 100" %
                 (self._nombre_final, imagen.width, imagen.height),
            size_hint_y=None, height=dp(58), font_size="12sp",
        ))
        botones = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        cerrar = Button(text="Cerrar")
        guardar = Button(text="Guardar JPEG")
        botones.add_widget(cerrar)
        botones.add_widget(guardar)
        contenido.add_widget(botones)
        popup = Popup(title="Revisar documento terminado", content=contenido, size_hint=(0.96, 0.92))
        cerrar.bind(on_release=popup.dismiss)
        guardar.bind(on_release=lambda *_: (popup.dismiss(), self._guardar_resultado()))
        popup.bind(on_open=lambda *_: Clock.schedule_once(
            lambda _dt: self._ajustar_zoom_preview(scroll, vista, copia.width, copia.height), 0
        ))
        popup.open()

    def _ajustar_zoom_preview(self, scroll, vista, ancho_imagen, alto_imagen):
        ancho_disponible = max(dp(100), scroll.width - dp(12))
        alto_disponible = max(dp(100), scroll.height - dp(12))
        factor = min(ancho_disponible / float(ancho_imagen), alto_disponible / float(alto_imagen), 1.0)
        vista.allow_stretch = True
        scroll.configurar_imagen_zoom(
            vista, (max(1, ancho_imagen * factor), max(1, alto_imagen * factor))
        )

    def _seleccionar_carpeta(self, request_code):
        if not ANDROID_NATIVE:
            self._mensaje("No disponible", "Esta operación requiere Android.")
            return
        try:
            Intent = autoclass("android.content.Intent")
            intent = Intent(Intent.ACTION_OPEN_DOCUMENT_TREE)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PythonActivity.mActivity.startActivityForResult(intent, request_code)
        except Exception as exc:
            self._mensaje("No se pudo abrir el selector de carpetas", str(exc))

    def _crear_documento_en_carpeta(self, tree_uri, mime, nombre):
        """Crea directamente el archivo con el nombre calculado, sin pedirlo en un campo vacío."""
        contexto = autoclass("org.kivy.android.PythonActivity").mActivity
        resolver = contexto.getContentResolver()
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        document_id = DocumentsContract.getTreeDocumentId(tree_uri)
        carpeta = DocumentsContract.buildDocumentUriUsingTree(tree_uri, document_id)
        creado = DocumentsContract.createDocument(resolver, carpeta, mime, nombre)
        if creado is None:
            raise IOError("Android no pudo crear '%s' en la carpeta seleccionada." % nombre)
        nombre_real = self._nombre_documento_uri(creado)
        if nombre_real and nombre_real != nombre:
            renombrado = DocumentsContract.renameDocument(resolver, creado, nombre)
            if renombrado is not None:
                creado = renombrado
        return creado

    def _nombre_base_avance(self):
        base = os.path.splitext(self._nombre_final or "captura")[0]
        base = re.sub(r'[\\/:*?"<>|]+', "_", base).strip(" ._")
        return base or "captura_pendiente"

    def _crear_archivo_avance_temporal(self):
        if not self.formato or not self._fdt_path or not os.path.isfile(self._fdt_path):
            raise IOError("No se encontró el formato original para incluirlo en el archivo de avance.")
        if self.formato.fields:
            campo = self.formato.fields[self.indice]
            if campo.field_type != FIELD_TYPE_IMAGE:
                self.respuestas[campo.field_id] = self.entrada.text

        ruta = os.path.join(tempfile.gettempdir(), "captura_pendiente_%d.ftc" % len(self._temp_files))
        datos = {"version": 1, "indice": self.indice, "respuestas": {}, "imagenes": {}}
        for campo in self.formato.fields:
            valor = self.respuestas.get(campo.field_id, "")
            if campo.field_type == FIELD_TYPE_IMAGE and valor:
                imagen_path = str(valor)
                if os.path.isfile(imagen_path):
                    extension = os.path.splitext(imagen_path)[1].lower()
                    if extension not in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
                        extension = ".jpg"
                    seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", campo.field_id) or "imagen"
                    interno = "imagenes/%s%s" % (seguro, extension)
                    datos["imagenes"][campo.field_id] = interno
                    datos["respuestas"][campo.field_id] = ""
                else:
                    datos["respuestas"][campo.field_id] = ""
            else:
                datos["respuestas"][campo.field_id] = "" if valor is None else str(valor)

        with zipfile.ZipFile(ruta, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
            paquete.write(self._fdt_path, "formato.fdt")
            paquete.writestr("captura.json", json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8"))
            for campo_id, interno in datos["imagenes"].items():
                imagen_path = self.respuestas.get(campo_id, "")
                if imagen_path and os.path.isfile(str(imagen_path)):
                    paquete.write(str(imagen_path), interno)
        self._temp_files.append(ruta)
        return ruta

    def guardar_avance(self):
        if not self.formato:
            self._mensaje("Sin captura", "Primero abre un formato .fdt o un archivo de avance.")
            return
        self._seleccionar_carpeta(self.REQUEST_SAVE_DRAFT_FOLDER)

    def _abrir_archivo_avance(self, ruta):
        directorio = tempfile.mkdtemp(prefix="formatos_traducidos_avance_")
        self._draft_dirs.append(directorio)
        with zipfile.ZipFile(ruta, "r") as paquete:
            nombres = paquete.namelist()
            if "formato.fdt" not in nombres or "captura.json" not in nombres:
                raise ValueError("El archivo no es un avance válido de Formatos Traducidos.")
            paquete.extractall(directorio)
        ruta_fdt = os.path.join(directorio, "formato.fdt")
        with open(os.path.join(directorio, "captura.json"), "r", encoding="utf-8") as archivo:
            datos = json.load(archivo)
        formato = cargar_fdt(ruta_fdt)
        respuestas = {campo.field_id: "" for campo in formato.fields}
        respuestas.update(datos.get("respuestas", {}))
        for campo_id, interno in (datos.get("imagenes", {}) or {}).items():
            ruta_imagen = os.path.join(directorio, *str(interno).split("/"))
            if os.path.isfile(ruta_imagen):
                respuestas[campo_id] = ruta_imagen
        self.formato = formato
        self._fdt_path = ruta_fdt
        self.respuestas = respuestas
        try:
            self.indice = max(0, min(int(datos.get("indice", 0)), len(formato.fields) - 1))
        except (TypeError, ValueError):
            self.indice = 0
        self.btn_guardar_avance.disabled = False
        self._mostrar_campo()
        self._mensaje("Avance abierto", "Se recuperaron las respuestas guardadas. Puedes continuar desde el campo %d de %d." % (self.indice + 1, len(formato.fields)))

    def _cargar_configuracion_salida(self):
        """Carga preferencias persistentes y migra la carpeta de la versión anterior."""
        datos = {}
        try:
            with open(self._settings_file, "r", encoding="utf-8") as archivo_config:
                datos = json.load(archivo_config) or {}
        except (OSError, ValueError, TypeError):
            datos = {}
        if not datos:
            try:
                with open(self._legacy_save_folder_config, "r", encoding="utf-8") as archivo_config:
                    anterior = json.load(archivo_config) or {}
                if anterior.get("uri"):
                    datos["output_folder_uri"] = anterior.get("uri")
            except (OSError, ValueError, TypeError):
                pass
        self._save_jpeg_folder_uri = datos.get("output_folder_uri") or None
        try:
            self._retention_days = max(1, min(365, int(datos.get("retention_days", 7))))
        except (TypeError, ValueError):
            self._retention_days = 7
        self._cleanup_enabled = bool(datos.get("cleanup_enabled", True))
        archivos = datos.get("generated_files", {})
        self._generated_files = archivos if isinstance(archivos, dict) else {}
        self._guardar_configuracion_salida()

    def _guardar_configuracion_salida(self):
        datos = {
            "output_folder_uri": self._save_jpeg_folder_uri,
            "retention_days": int(self._retention_days),
            "cleanup_enabled": bool(self._cleanup_enabled),
            "generated_files": self._generated_files,
        }
        os.makedirs(self.user_data_dir, exist_ok=True)
        temporal = self._settings_file + ".tmp"
        with open(temporal, "w", encoding="utf-8") as archivo_config:
            json.dump(datos, archivo_config, ensure_ascii=False, indent=2)
        os.replace(temporal, self._settings_file)

    def _mostrar_configuracion(self):
        contenido = BoxLayout(
            orientation="vertical", padding=dp(14), spacing=dp(10),
        )
        titulo_carpeta = Label(
            text="Carpeta de documentos terminados",
            size_hint_y=None, height=dp(30), font_size="13sp",
            bold=True, halign="left", valign="middle",
        )
        titulo_carpeta.bind(size=lambda obj, size: setattr(obj, "text_size", (size[0], None)))
        contenido.add_widget(titulo_carpeta)
        ruta = self._texto_carpeta_destino()
        self._config_ruta_label = Label(
            text=ruta, size_hint_y=None, height=dp(58),
            font_size="10sp", halign="left", valign="middle",
        )
        self._config_ruta_label.bind(size=lambda obj, size: setattr(obj, "text_size", (max(1, size[0] - dp(8)), None)))
        contenido.add_widget(self._config_ruta_label)
        elegir = Button(
            text="Elegir carpeta de destino",
            size_hint_y=None, height=dp(42), font_size="12sp",
        )
        contenido.add_widget(elegir)
        fila_limpieza = BoxLayout(
            orientation="horizontal", size_hint_y=None, height=dp(46), spacing=dp(6),
        )
        limpieza = CheckBox(
            active=self._cleanup_enabled, size_hint=(None, None),
            size=(dp(38), dp(38)),
        )
        fila_limpieza.add_widget(limpieza)
        texto_limpieza = Label(
            text="Activar limpieza automática de JPEG antiguos",
            font_size="11sp", halign="left", valign="middle",
        )
        texto_limpieza.bind(size=lambda obj, size: setattr(obj, "text_size", (max(1, size[0] - dp(4)), None)))
        fila_limpieza.add_widget(texto_limpieza)
        contenido.add_widget(fila_limpieza)
        texto_dias = Label(
            text="Días que se conservará cada JPEG en esa carpeta",
            size_hint_y=None, height=dp(38), font_size="12sp",
            halign="left", valign="middle",
        )
        texto_dias.bind(size=lambda obj, size: setattr(obj, "text_size", (max(1, size[0] - dp(8)), None)))
        contenido.add_widget(texto_dias)
        dias = TextInput(
            text=str(self._retention_days), multiline=False,
            input_filter="int", size_hint_y=None, height=dp(42),
            font_size="16sp", hint_text="Días (1 a 365)",
        )
        contenido.add_widget(dias)
        dias.disabled = not limpieza.active
        limpieza.bind(active=lambda _obj, activo: setattr(dias, "disabled", not activo))
        aviso_limpieza = Label(
            text="Solo se eliminarán JPEG creados por esta aplicación que sigan en la carpeta. "
                 "Si un archivo se mueve fuera, dejará de estar sujeto a la limpieza.",
            size_hint_y=None, height=dp(62), font_size="10sp",
            halign="left", valign="middle",
        )
        aviso_limpieza.bind(size=lambda obj, size: setattr(obj, "text_size", (max(1, size[0] - dp(8)), None)))
        contenido.add_widget(aviso_limpieza)
        botones = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(8))
        cancelar = Button(text="Cerrar")
        guardar = Button(text="Guardar ajustes")
        botones.add_widget(cancelar)
        botones.add_widget(guardar)
        contenido.add_widget(botones)
        popup = Popup(
            title="Configuración", content=contenido,
            size_hint=(0.94, None), height=dp(500), auto_dismiss=False,
        )
        cancelar.bind(on_release=popup.dismiss)

        def guardar_ajustes(*_):
            texto_dias = (dias.text or "").strip()
            if limpieza.active:
                try:
                    valor = int(texto_dias)
                except ValueError:
                    valor = 0
                if valor < 1 or valor > 365:
                    self._mensaje("Valor no válido", "El plazo debe ser un número entero entre 1 y 365 días.")
                    return
                self._retention_days = valor
            self._cleanup_enabled = bool(limpieza.active)
            self._guardar_configuracion_salida()
            popup.dismiss()
            if self._cleanup_enabled:
                self._limpiar_archivos_vencidos()
            self._mensaje("Configuración guardada", "Carpeta de destino y plazo de conservación guardados.")

        def elegir_carpeta(*_):
            texto_dias = (dias.text or "").strip()
            if limpieza.active:
                try:
                    valor = int(texto_dias)
                    if 1 <= valor <= 365:
                        self._retention_days = valor
                except ValueError:
                    pass
            self._cleanup_enabled = bool(limpieza.active)
            self._guardar_configuracion_salida()
            popup.dismiss()
            self._seleccionar_carpeta(self.REQUEST_CONFIG_OUTPUT_FOLDER)

        guardar.bind(on_release=guardar_ajustes)
        elegir.bind(on_release=elegir_carpeta)
        popup.open()

    def _texto_carpeta_destino(self):
        if not self._save_jpeg_folder_uri:
            return "No configurada. Elige la carpeta donde se guardarán los JPEG finales."
        try:
            Uri = autoclass("android.net.Uri")
            nombre = self._nombre_documento_uri(Uri.parse(self._save_jpeg_folder_uri))
            return "Carpeta seleccionada: %s" % (nombre or self._save_jpeg_folder_uri)
        except Exception:
            return "Carpeta seleccionada. URI: %s" % self._save_jpeg_folder_uri

    def _recordar_carpeta_destino(self, uri, intent):
        """Conserva autorización SAF y registra la carpeta elegida en Configuración."""
        Intent = autoclass("android.content.Intent")
        permisos = intent.getFlags() & (
            Intent.FLAG_GRANT_READ_URI_PERMISSION |
            Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        )
        if not permisos:
            permisos = Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION
        resolver = autoclass("org.kivy.android.PythonActivity").mActivity.getContentResolver()
        resolver.takePersistableUriPermission(uri, permisos)
        self._save_jpeg_folder_uri = str(uri.toString())
        self._guardar_configuracion_salida()

    def _registrar_jpeg_generado(self, uri):
        DocumentsContract = autoclass("android.provider.DocumentsContract")
        document_id = str(DocumentsContract.getDocumentId(uri))
        self._generated_files[document_id] = {
            "name": self._nombre_documento_uri(uri) or self._nombre_final,
            "created_at": time.time(),
        }
        self._guardar_configuracion_salida()

    def _limpiar_archivos_vencidos(self):
        """Elimina solo JPEG registrados que sigan directamente en la carpeta configurada."""
        if not self._cleanup_enabled or not ANDROID_NATIVE or not self._save_jpeg_folder_uri:
            return
        cursor = None
        try:
            Uri = autoclass("android.net.Uri")
            DocumentsContract = autoclass("android.provider.DocumentsContract")
            Document = autoclass("android.provider.DocumentsContract$Document")
            contexto = autoclass("org.kivy.android.PythonActivity").mActivity
            resolver = contexto.getContentResolver()
            tree_uri = Uri.parse(self._save_jpeg_folder_uri)
            root_id = DocumentsContract.getTreeDocumentId(tree_uri)
            children_uri = DocumentsContract.buildChildDocumentsUriUsingTree(tree_uri, root_id)
            columnas = [
                Document.COLUMN_DOCUMENT_ID,
                Document.COLUMN_DISPLAY_NAME,
                Document.COLUMN_MIME_TYPE,
            ]
            cursor = resolver.query(children_uri, columnas, None, None, None)
            if cursor is None:
                return
            presentes = {}
            indice_id = cursor.getColumnIndex(Document.COLUMN_DOCUMENT_ID)
            indice_nombre = cursor.getColumnIndex(Document.COLUMN_DISPLAY_NAME)
            indice_mime = cursor.getColumnIndex(Document.COLUMN_MIME_TYPE)
            while cursor.moveToNext():
                doc_id = str(cursor.getString(indice_id))
                nombre = str(cursor.getString(indice_nombre)) if indice_nombre >= 0 else ""
                mime = str(cursor.getString(indice_mime)) if indice_mime >= 0 else ""
                presentes[doc_id] = {"name": nombre, "mime": mime}
            cursor.close()
            cursor = None
            ahora = time.time()
            vencimiento = self._retention_days * 86400
            cambios = False
            for doc_id, registro in list(self._generated_files.items()):
                if doc_id not in presentes:
                    # Movido, copiado fuera o eliminado: se olvida el registro.
                    self._generated_files.pop(doc_id, None)
                    cambios = True
                    continue
                elemento = presentes[doc_id]
                if not elemento["mime"].startswith("image/") or not elemento["name"].lower().endswith((".jpg", ".jpeg")):
                    continue
                try:
                    creado = float(registro.get("created_at", ahora))
                except (TypeError, ValueError):
                    creado = ahora
                if ahora - creado < vencimiento:
                    continue
                documento_uri = DocumentsContract.buildDocumentUriUsingTree(tree_uri, doc_id)
                if DocumentsContract.deleteDocument(resolver, documento_uri):
                    self._generated_files.pop(doc_id, None)
                    cambios = True
            if cambios:
                self._guardar_configuracion_salida()
        except Exception:
            # Un proveedor SAF puede no permitir listar o borrar. No se arriesga
            # a eliminar por nombre ni se borra nada si no puede verificarse.
            pass
        finally:
            if cursor is not None:
                try:
                    cursor.close()
                except Exception:
                    pass

    def _guardar_jpeg_en_carpeta(self, tree_uri):
        destino = self._crear_documento_en_carpeta(tree_uri, "image/jpeg", self._nombre_final)
        self._copiar_archivo_a_uri(self._imagen_final, destino)
        self._registrar_jpeg_generado(destino)
        self._limpiar_archivos_vencidos()
        nombre_guardado = self._nombre_documento_uri(destino) or self._nombre_final
        if nombre_guardado == self._nombre_final:
            self._mensaje("Archivo guardado", "JPEG guardado en la carpeta configurada:\n%s" % nombre_guardado)
        else:
            self._mensaje("Nombre asignado por Android", "Nombre solicitado:\n%s\n\nNombre creado por el proveedor de archivos:\n%s" % (self._nombre_final, nombre_guardado))

    def _guardar_resultado(self):
        if not self._save_jpeg_folder_uri or not ANDROID_NATIVE:
            self._mensaje(
                "Configura la carpeta de destino",
                "Antes de guardar el JPEG, abre Configuración y elige la carpeta de documentos terminados.",
            )
            self._mostrar_configuracion()
            return
        try:
            Uri = autoclass("android.net.Uri")
            tree_uri = Uri.parse(self._save_jpeg_folder_uri)
            self._guardar_jpeg_en_carpeta(tree_uri)
        except Exception as exc:
            self._mensaje(
                "No se pudo guardar el JPEG",
                "%s\n\nRevisa la carpeta configurada desde Configuración y vuelve a intentarlo." % exc,
            )




if __name__ == "__main__":
    CapturadorApp().run()
