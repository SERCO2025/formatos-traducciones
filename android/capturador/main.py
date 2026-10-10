# -*- coding: utf-8 -*-
"""Rellenador Android de Formatos Traducidos.

Porta el flujo funcional del capturador de PC y reutiliza el motor compartido:
FDT, modelos, validaciones y renderizado. Los archivos se seleccionan/exportan
mediante el selector de documentos de Android (Storage Access Framework).
"""
import os
import tempfile
import traceback
from pathlib import Path

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.image import Image
from kivy.uix.label import Label
from kivy.uix.popup import Popup
from kivy.uix.scrollview import ScrollView
from kivy.uix.textinput import TextInput

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

    def build(self):
        self.formato = None
        self.respuestas = {}
        self.indice = 0
        self._uri_accion = None
        self._imagen_final = None
        self._nombre_final = "resultado.jpg"
        self._preview_file = None
        self._temp_files = []

        root = BoxLayout(orientation="vertical", padding=dp(12), spacing=dp(8))
        root.add_widget(Label(
            text="Formatos Traducidos",
            size_hint_y=None, height=dp(42),
            font_size="22sp", bold=True,
        ))
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

        controls_nav = BoxLayout(size_hint_y=None, height=dp(52), spacing=dp(8))
        self.btn_atras = Button(text="Volver", font_size="17sp", disabled=True)
        self.btn_atras.bind(on_release=lambda *_: self.anterior())
        controls_nav.add_widget(self.btn_atras)
        self.btn_siguiente = Button(text="Continuar", font_size="17sp", disabled=True)
        self.btn_siguiente.bind(on_release=lambda *_: self.siguiente())
        controls_nav.add_widget(self.btn_siguiente)
        root.add_widget(controls_nav)

        if ANDROID_NATIVE:
            try:
                activity.bind(on_activity_result=self._on_activity_result)
            except Exception:
                pass
        else:
            self.estado.text = "Entorno de prueba: los selectores requieren Android."
        return root

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
                self.respuestas = {campo.field_id: "" for campo in formato.fields}
                self.indice = 0
                self._mostrar_campo()
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
        scroll = ScrollView()
        ruta_preview = os.path.join(tempfile.gettempdir(), "formatos_traducidos_final_preview.png")
        copia = imagen.copy()
        copia.thumbnail((1200, 1600), PILImage.Resampling.LANCZOS)
        copia.save(ruta_preview, format="PNG")
        vista = Image(source=ruta_preview, allow_stretch=True, keep_ratio=True, size_hint=(1, None), height=dp(420))
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
        popup.open()

    def _guardar_resultado(self):
        self._intent(self.REQUEST_SAVE_JPEG, "android.intent.action.CREATE_DOCUMENT", "image/jpeg", self._nombre_final)


if __name__ == "__main__":
    CapturadorApp().run()
