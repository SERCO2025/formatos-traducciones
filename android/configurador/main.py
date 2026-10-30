# -*- coding: utf-8 -*-
import copy
import os
import uuid
import traceback
import sys
import faulthandler
from urllib.parse import unquote
from math import hypot

from kivy.app import App
from kivy.clock import Clock
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.graphics import Color, Line, Rectangle, InstructionGroup
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
from kivy.uix.slider import Slider
from kivy.uix.spinner import Spinner
from kivy.uix.stencilview import StencilView
from kivy.uix.textinput import TextInput
from kivy.uix.widget import Widget

try:
    from android import activity
    from jnius import autoclass
    ANDROID_AVAILABLE = True
except Exception:
    activity = None
    ANDROID_AVAILABLE = False

from shared.fdt import cargar_fdt, guardar_fdt, validar_fdt, limpiar_fdt_temporales
from shared.models import (
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


class HamburgerButton(Button):
    """Botón hamburguesa dibujado con Canvas, sin depender de una fuente Unicode."""
    def __init__(self, **kwargs):
        kwargs.setdefault("size_hint_x", None)
        kwargs.setdefault("width", dp(64))
        kwargs.setdefault("font_size", "1sp")
        super().__init__(**kwargs)
        self.bind(pos=self._redraw_icon, size=self._redraw_icon)
        self._redraw_icon()

    def _redraw_icon(self, *args):
        self.canvas.after.clear()
        with self.canvas.after:
            Color(1, 1, 1, 1)
            margen = dp(16)
            y = self.height / 2.0
            separacion = dp(8)
            ancho = max(dp(24), self.width - margen * 2)
            for offset in (-separacion, 0, separacion):
                Line(points=(self.x + margen, self.y + y + offset,
                             self.x + margen + ancho, self.y + y + offset),
                     width=dp(3.0))


TOOLS = [
    ("seleccionar.png", "select"),
    ("desplazar.png", "hand"),
    ("campo_texto.png", FIELD_TYPE_TEXT),
    ("campo_numerico.png", FIELD_TYPE_NUMBER),
    ("campo_imagen.png", FIELD_TYPE_IMAGE),
    ("zoom_mas.png", "zoom"),
]


class ToolButton(Button):
    """Botón de herramienta que detecta un ratón físico sin alterar los toques."""
    def __init__(self, app, **kwargs):
        self.app = app
        super().__init__(**kwargs)

    def on_touch_down(self, touch):
        if self.collide_point(*touch.pos) and self.app._es_evento_raton(touch):
            self.app._activar_cursor_raton(touch.pos)
        return super().on_touch_down(touch)


class CampoWidget(FloatLayout):
    def __init__(self, campo, editor, **kwargs):
        super().__init__(**kwargs)
        self.campo = campo
        self.editor = editor
        self.size_hint = (None, None)
        self._borde_linea = None
        self._seleccion_linea = None
        self._manijas_rectangulos = []
        self._manijas_lineas = []
        self.actualizar()

    def actualizar(self):
        p = self.campo.position
        self.size = (p.width * self.editor.scale, p.height * self.editor.scale)
        tw = self.editor.template_widget
        if tw is not None:
            # CampoWidget y plantilla son hermanos dentro de CanvasEditor:
            # ambos deben posicionarse en las coordenadas de su padre.
            self.pos = (
                tw.x + p.x * self.editor.scale,
                tw.y + tw.height - (p.y + p.height) * self.editor.scale,
            )

        self.canvas.before.clear()
        self._borde_linea = None
        self._seleccion_linea = None
        with self.canvas.before:
            Color(0, 0, 0, 1)
            self._borde_linea = Line(
                rectangle=(self.x, self.y, self.width, self.height), width=2.0
            )
            if self.editor.app.seleccionado is self.campo:
                Color(0.0, 0.75, 1.0, 1)
                self._seleccion_linea = Line(
                    rectangle=(self.x, self.y, self.width, self.height), width=3.0
                )

        self.canvas.after.clear()
        self._manijas_rectangulos = []
        self._manijas_lineas = []
        if self.editor.app.seleccionado is self.campo:
            # Ocho controles blancos con borde oscuro: cuatro esquinas y
            # el centro de cada lado.
            with self.canvas.after:
                s = min(dp(14), max(dp(10), min(self.width, self.height) / 5.0))
                puntos = (
                    (self.x, self.y),
                    (self.x + self.width / 2, self.y),
                    (self.x + self.width, self.y),
                    (self.x + self.width, self.y + self.height / 2),
                    (self.x + self.width, self.y + self.height),
                    (self.x + self.width / 2, self.y + self.height),
                    (self.x, self.y + self.height),
                    (self.x, self.y + self.height / 2),
                )
                for x, y in puntos:
                    Color(1, 1, 1, 1)
                    rect = Rectangle(pos=(x - s / 2, y - s / 2), size=(s, s))
                    self._manijas_rectangulos.append(rect)
                    Color(0, 0, 0, 1)
                    linea = Line(rectangle=(x - s / 2, y - s / 2, s, s), width=1)
                    self._manijas_lineas.append(linea)

        self.clear_widgets()
        if self.campo.field_type == FIELD_TYPE_IMAGE:
            texto = "IMAGEN"
        elif self.campo.field_type == FIELD_TYPE_NUMBER:
            texto = "12345"
        else:
            texto = "ABCDE"
        estilo = self.campo.text_style
        if getattr(self.campo, "uppercase", False):
            texto = texto.upper()
        if estilo.bold:
            texto = "[b]" + texto + "[/b]"
        if estilo.italic:
            texto = "[i]" + texto + "[/i]"
        etiqueta = Label(
            text=texto,
            markup=True,
            size_hint=(1, 1),
            # La muestra respeta la alineación configurada y empieza a 10 px
            # del borde superior del campo, escalados con la plantilla.
            pos_hint={"x": 0, "y": 0},
            padding=(0, 10 * self.editor.scale),
            color=(
                estilo.color.r / 255.0,
                estilo.color.g / 255.0,
                estilo.color.b / 255.0,
                1,
            ),
            font_size=max(dp(7), estilo.font_size_px * self.editor.scale),
            halign=estilo.alignment if estilo.alignment in ("left", "center", "right") else "left",
            valign="top",
        )
        etiqueta.bind(size=lambda inst, value: setattr(inst, "text_size", value))
        if estilo.font_family and os.path.isfile(estilo.font_family):
            etiqueta.font_name = estilo.font_family
        self.add_widget(etiqueta)

    def actualizar_posicion(self):
        """Mueve la capa visual existente sin reconstruir canvas ni etiquetas."""
        p = self.campo.position
        self.size = (p.width * self.editor.scale, p.height * self.editor.scale)
        tw = self.editor.template_widget
        if tw is None:
            return
        self.pos = (
            tw.x + p.x * self.editor.scale,
            tw.y + tw.height - (p.y + p.height) * self.editor.scale,
        )

        rect = (self.x, self.y, self.width, self.height)
        if self._borde_linea is not None:
            self._borde_linea.rectangle = rect
        if self._seleccion_linea is not None:
            self._seleccion_linea.rectangle = rect

        if self._manijas_rectangulos:
            s = min(dp(14), max(dp(10), min(self.width, self.height) / 5.0))
            puntos = (
                (self.x, self.y),
                (self.x + self.width / 2, self.y),
                (self.x + self.width, self.y),
                (self.x + self.width, self.y + self.height / 2),
                (self.x + self.width, self.y + self.height),
                (self.x + self.width / 2, self.y + self.height),
                (self.x, self.y + self.height),
                (self.x, self.y + self.height / 2),
            )
            for (x, y), rectangulo, linea in zip(
                puntos, self._manijas_rectangulos, self._manijas_lineas
            ):
                pos = (x - s / 2, y - s / 2)
                rectangulo.pos = pos
                rectangulo.size = (s, s)
                linea.rectangle = (pos[0], pos[1], s, s)

        # FloatLayout recoloca la etiqueta ya existente; no se elimina ni recrea.
        self.do_layout()

    def _handle_at(self, x, y):
        if self.editor.app.seleccionado is not self.campo:
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
        # El evento llega en coordenadas del padre, igual que self.pos.
        # CanvasEditor es hijo directo de BoxLayout y no hay RelativeLayout/
        # ScrollView ancestro que cambie el sistema de coordenadas.
        local_x, local_y = touch.x - self.x, touch.y - self.y
        if not (0 <= local_x <= self.width and 0 <= local_y <= self.height):
            return super().on_touch_down(touch)
        if self.editor.app.tool != "select":
            # Los widgets de campo son solo una capa visual fuera de Selección.
            # Dejar que el gesto llegue a CanvasEditor (dibujar/desplazar/pellizcar).
            return False
        if getattr(touch, "is_double_tap", False):
            self.editor.app.seleccionar(self.campo)
            Clock.schedule_once(
                lambda _dt: self.editor.app.mostrar_propiedades(self.campo), 0
            )
            return True
        handle = self._handle_at(local_x, local_y)
        self.editor.begin_field_interaction(self.campo, touch, handle)
        return True

    def on_touch_move(self, touch):
        if self.editor.active_field_touch is touch:
            self.editor.update_field_interaction(touch)
            return True
        if self.editor.app.tool != "select":
            return False
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self.editor.active_field_touch is touch:
            self.editor.end_field_interaction(touch)
            return True
        if self.editor.app.tool != "select":
            return False
        return super().on_touch_up(touch)


class CanvasEditor(StencilView):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.template_widget = None
        self._template_core_image = None
        self.start_touch = None
        self.start_touch_screen = None
        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self.pan_start = None
        self.pan_template_pos = None
        self._touches = {}
        self._pinch_active = False
        self._pinch_start_distance = 0.0
        self._pinch_last_distance = 0.0
        self._pinch_last_midpoint = None
        self._pinch_start_midpoint = None
        self.bind(pos=self._viewport_changed, size=self._viewport_changed)

    @property
    def seleccionado(self):
        # La selección es propiedad del ConfiguradorApp; los widgets del
        # lienzo consultan esta propiedad para mantener una única fuente de verdad.
        return getattr(self.app, "seleccionado", None)

    @seleccionado.setter
    def seleccionado(self, campo):
        self.app.seleccionado = campo

    def _viewport_changed(self, *_args):
        if self.template_widget is not None:
            self.constrain_template_position()
            self.refresh_fields()

    def constrain_template_position(self, pos=None):
        """Centra plantillas pequeñas y limita el desplazamiento en coordenadas locales."""
        tw = self.template_widget
        if tw is None:
            return
        # Kivy mantiene las posiciones de los widgets en coordenadas de ventana.
        x, y = tw.pos if pos is None else pos
        if tw.width <= self.width:
            x = self.x + (self.width - tw.width) / 2.0
        else:
            x = min(self.x, max(self.right - tw.width, x))
        if tw.height <= self.height:
            y = self.y + (self.height - tw.height) / 2.0
        else:
            y = min(self.y, max(self.top - tw.height, y))
        tw.pos = (x, y)

    def _touch_inside_template(self, touch):
        if self.template_widget is None:
            return False
        # El toque y la plantilla usan el mismo sistema de coordenadas de ventana.
        return self.template_widget.collide_point(touch.x, touch.y)

    def cancel_active_gestures(self):
        """Limpia estados de interacción al cambiar de herramienta."""
        self._touches.clear()
        self._pinch_active = False
        self._pinch_zoom_activated = False
        self._pinch_start_distance = 0.0
        self._pinch_last_distance = 0.0
        self._pinch_last_midpoint = None
        self._pinch_start_midpoint = None
        self.pan_start = None
        self.pan_template_pos = None
        self.start_touch = None
        self.start_touch_screen = None
        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self._interaction_start_doc = None
        self.app._interaction_changed = False
        self.app.clear_drawing_preview()

    def _start_pinch(self):
        if len(self._touches) < 2 or not self.template_widget:
            return False
        a, b = list(self._touches.values())[:2]
        self._pinch_start_distance = max(1.0, hypot(b.x - a.x, b.y - a.y))
        self._pinch_last_distance = self._pinch_start_distance
        self._pinch_last_midpoint = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
        self._pinch_start_midpoint = self._pinch_last_midpoint
        self._pinch_active = True
        self._pinch_zoom_activated = False

        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self._interaction_start_doc = None
        self.app._interaction_changed = False

        self.pan_start = None
        self.pan_template_pos = None
        self.start_touch = None
        self.start_touch_screen = None
        self.app.clear_drawing_preview()
        self.app.estado.text = "Dos dedos: desplaza; acerca o separa para cambiar zoom"
        return True

    def _update_pinch(self):
        if not self._pinch_active or len(self._touches) < 2:
            return False
        a, b = list(self._touches.values())[:2]
        distancia = max(1.0, hypot(b.x - a.x, b.y - a.y))
        midpoint = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)

        # No se activa el zoom por pequeñas variaciones mientras el usuario
        # desplaza dos dedos. Primero se exige un cambio acumulado claro desde
        # el inicio del gesto; una vez identificado el pellizco, el zoom sigue
        # de forma incremental y el punto medio continúa controlando el paneo.
        cambio_desde_inicio = distancia - self._pinch_start_distance
        dx_centro = midpoint[0] - self._pinch_start_midpoint[0]
        dy_centro = midpoint[1] - self._pinch_start_midpoint[1]
        movimiento_centro = hypot(dx_centro, dy_centro)
        # El zoom solo se considera intencional cuando la separación cambia
        # claramente Y ese cambio domina el desplazamiento conjunto de dedos.
        # Así, un arrastre diagonal de dos dedos no se interpreta como pellizco.
        umbral_zoom = max(dp(32), self._pinch_start_distance * 0.20)
        zoom_intencional = (
            abs(cambio_desde_inicio) >= umbral_zoom
            and abs(cambio_desde_inicio) >= movimiento_centro * 0.75
        )
        if not getattr(self, "_pinch_zoom_activated", False):
            if zoom_intencional:
                self._pinch_zoom_activated = True
                self._pinch_last_distance = distancia
        else:
            factor = distancia / max(1.0, self._pinch_last_distance)
            if abs(distancia - self._pinch_last_distance) >= dp(1):
                self.app.set_zoom(
                    self.app.scale * factor,
                    anchor=self._pinch_last_midpoint,
                )
                self._pinch_last_distance = distancia

        if self.template_widget is not None:
            dx = midpoint[0] - self._pinch_last_midpoint[0]
            dy = midpoint[1] - self._pinch_last_midpoint[1]
            self.template_widget.pos = (
                self.template_widget.x + dx,
                self.template_widget.y + dy,
            )
            self.constrain_template_position()
            self.refresh_field_positions()

        self._pinch_last_midpoint = midpoint
        return True

    def cargar_plantilla(self, ruta):
        self.clear_widgets()
        self.template_widget = None
        self._template_core_image = None

        if not ruta or not os.path.isfile(ruta):
            raise IOError(f"La plantilla no existe o no se puede leer: {ruta}")

        self._template_core_image = CoreImage(ruta, nocache=True)
        if self._template_core_image.texture is None:
            raise IOError("Kivy NO pudo crear la textura de la imagen. El formato puede no ser soportado o el archivo está corrupto.")

        self.template_widget = KivyImage(
            texture=self._template_core_image.texture,
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

    def refresh_field_positions(self):
        """Sincroniza solo posiciones durante paneo; conserva etiquetas e instrucciones."""
        if self.template_widget is None:
            return
        for widget in self.children:
            if isinstance(widget, CampoWidget):
                widget.actualizar_posicion()

    def _document_point(self, touch):
        """Convierte un toque de ventana a píxeles del documento (origen arriba-izquierda)."""
        tw = self.template_widget
        if tw is None or not self.app.formato:
            return 0, 0

        # touch.x/y y tw.x/y ya están en coordenadas de ventana.
        rel_x = touch.x - tw.x
        rel_y_from_top = (tw.y + tw.height) - touch.y

        doc_x = rel_x / self.app.scale
        doc_y = rel_y_from_top / self.app.scale
        doc_x = max(0, min(self.app.formato.template.width, doc_x))
        doc_y = max(0, min(self.app.formato.template.height, doc_y))
        return int(round(doc_x)), int(round(doc_y))

    def _inside_template(self, touch):
        return self._touch_inside_template(touch)

    def on_touch_down(self, touch):
        # En esta jerarquía (BoxLayout -> StencilView), el toque llega en
        # coordenadas del padre, igual que collide_point y las posiciones.
        if not self.collide_point(touch.x, touch.y):
            return False

        if self._touch_inside_template(touch):
            self._touches[touch.uid] = touch

        if len(self._touches) >= 2 and self._touch_inside_template(touch):
            self._start_pinch()
            return True

        tool = self.app.tool

        if tool == "zoom":
            if touch.button in ("scrollup", "scrollright"):
                self.app.set_zoom(self.app.scale * 1.2, anchor=touch.pos)
                return True
            if touch.button in ("scrolldown", "scrollleft"):
                self.app.set_zoom(self.app.scale * 0.8, anchor=touch.pos)
                return True
            if touch.is_mouse_scrolling:
                return True
            factor = 0.8 if touch.button == "right" else 1.2
            self.app.set_zoom(self.app.scale * factor, anchor=touch.pos)
            return True

        if tool == "hand":
            if self.template_widget and self._touch_inside_template(touch):
                self.pan_start = touch.pos
                self.pan_template_pos = self.template_widget.pos
                return True

        if tool in (FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_IMAGE):
            if self._inside_template(touch):
                self.start_touch = self._document_point(touch)
                self.start_touch_screen = (touch.x, touch.y)
                self.app.estado.text = "Dibujando campo..."
                return True

        if tool == "select" and self._inside_template(touch):
            if super().on_touch_down(touch):
                return True
            self.app.seleccionar(None)
            return True

        return super().on_touch_down(touch)

    def on_touch_move(self, touch):
        if touch.uid in self._touches:
            self._touches[touch.uid] = touch

        if self._pinch_active:
            if len(self._touches) >= 2:
                return self._update_pinch()
            # No continuar aplicando zoom si queda un solo dedo activo.
            self._pinch_active = False
            self._pinch_zoom_activated = False
            self._pinch_start_distance = 0.0
            self._pinch_last_distance = 0.0
            self._pinch_last_midpoint = None

        if self.pan_start and self.app.tool == "hand" and self.template_widget:
            # Arrastre incremental en el mismo sistema local del lienzo.
            # Cada desplazamiento del dedo mueve la plantilla 1:1.
            point = touch.pos
            dx = point[0] - self.pan_start[0]
            dy = point[1] - self.pan_start[1]
            self.template_widget.pos = (
                self.template_widget.x + dx,
                self.template_widget.y + dy,
            )
            self.constrain_template_position()
            self.pan_start = point
            self.refresh_field_positions()
            return True

        if self.start_touch and self.app.tool in (
            FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_IMAGE
        ):
            self.app.redraw_drawing_preview(self.start_touch, self._document_point(touch))
            return True

        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        self._touches.pop(touch.uid, None)

        if self._pinch_active:
            if len(self._touches) < 2:
                self._pinch_active = False
                self._pinch_zoom_activated = False
                self._pinch_start_distance = 0.0
                self._pinch_last_distance = 0.0
                self._pinch_last_midpoint = None
                self.app.estado.text = "Gesto de dos dedos terminado."
            return True

        if self.pan_start:
            self.pan_start = None
            self.pan_template_pos = None
            return True

        if self.start_touch is None:
            return super().on_touch_up(touch)

        tool = self.app.tool
        if tool not in (FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_IMAGE):
            self.start_touch = None
            self.app.clear_drawing_preview()
            return super().on_touch_up(touch)

        x0, y0 = self.start_touch
        x1, y1 = self._document_point(touch)
        inicio_pantalla = self.start_touch_screen or (touch.x, touch.y)
        arrastro = (
            abs(touch.x - inicio_pantalla[0]) >= dp(8)
            or abs(touch.y - inicio_pantalla[1]) >= dp(8)
        )
        self.start_touch = None
        self.start_touch_screen = None
        self.app.clear_drawing_preview()

        if not arrastro and self.app.formato.fields:
            anterior = max(self.app.formato.fields, key=lambda item: item.order)
            width = min(anterior.position.width, self.app.formato.template.width)
            height = min(anterior.position.height, self.app.formato.template.height)
            left = max(0, min(x0, self.app.formato.template.width - width))
            top = max(0, min(y0, self.app.formato.template.height - height))
        else:
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            width = max(2, right - left)
            height = max(2, bottom - top)

        if width < 4 or height < 4:
            self.app.estado.text = "Área demasiado pequeña."
            return True

        # Guardar el historial anterior para que Cancelar sea una operación sin efectos.
        undo_antes_creacion = list(self.app._undo)
        redo_antes_creacion = list(self.app._redo)
        seleccionado_antes_creacion = self.app.seleccionado
        self.app.push_undo()
        # Los campos de texto y número comparten los últimos atributos tipográficos usados.
        estilo_anterior = next(
            (
                copy.deepcopy(c.text_style)
                for c in sorted(self.app.formato.fields, key=lambda item: item.order, reverse=True)
                if c.field_type != FIELD_TYPE_IMAGE
            ),
            TextStyle(
                font_family="",
                font_size_px=24,
                color=FieldColor(0, 0, 0),
                alignment="left",
            ),
        )
        mayusculas_anteriores = next(
            (
                bool(getattr(c, "uppercase", False))
                for c in sorted(self.app.formato.fields, key=lambda item: item.order, reverse=True)
                if c.field_type != FIELD_TYPE_IMAGE
            ),
            False,
        )
        campo = Field(
            field_id=self.app.nuevo_id(),
            question="",
            field_type=tool,
            position=Position(left, top, width, height),
            text_style=estilo_anterior,
            uppercase=mayusculas_anteriores,
        )
        self.app.formato.agregar_campo(campo)
        self.app.seleccionar(campo)
        self.app.mostrar_propiedades(
            campo,
            es_nuevo=True,
            undo_antes=undo_antes_creacion,
            redo_antes=redo_antes_creacion,
            seleccionado_antes=seleccionado_antes_creacion,
        )
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
        # Compatibilidad con llamadas antiguas; el dibujo provisional se
        # actualiza únicamente desde redraw_drawing_preview().
        self.app.clear_drawing_preview()


class ConfiguradorApp(App):
    title = "Configurador de Formatos Traducidos"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._diagnostico_crash_path = os.path.join(self.user_data_dir, "diagnostico_cierre.log")
        self._diagnostico_crash_anterior = ""
        self._diagnostico_crash_file = None
        try:
            if os.path.isfile(self._diagnostico_crash_path):
                with open(self._diagnostico_crash_path, "r", encoding="utf-8", errors="replace") as previo:
                    self._diagnostico_crash_anterior = previo.read()[-12000:]
            self._diagnostico_crash_file = open(self._diagnostico_crash_path, "w", encoding="utf-8", buffering=1)
            self._diagnostico_crash_file.write("INICIO DE SESION DE DIAGNOSTICO\n")
            faulthandler.enable(file=self._diagnostico_crash_file, all_threads=True)
            hook_anterior = sys.excepthook
            def registrar_excepcion(tipo, valor, tb):
                try:
                    self._diagnostico_crash_file.write("\nEXCEPCION NO CONTROLADA\n")
                    traceback.print_exception(tipo, valor, tb, file=self._diagnostico_crash_file)
                    self._diagnostico_crash_file.flush()
                except Exception:
                    pass
                hook_anterior(tipo, valor, tb)
            sys.excepthook = registrar_excepcion
        except Exception as exc:
            print("[FDT_CRASH_DIAG] No se pudo iniciar registro: %r" % (exc,), flush=True)
        self.formato = None
        self.tool = "select"
        self.tool_buttons = {}
        self._mouse_cursor_active = False
        self._mouse_cursor_texture_cache = {}
        self._mouse_cursor_color = None
        self._mouse_cursor_rect = None
        self.scale = 1.0
        self.editor = None
        self.seleccionado = None
        self.estado = None
        self.estado_menu = None
        self.zoom_label = None
        self._visual_template_path = None
        self._android_callback = None
        self._font_import_target = None
        self._undo = []
        self._redo = []
        self._interaction_changed = False
        self._drawing_widget = None
        self._popup_propiedades_intentos = 0
        self._propiedades_abiertas = False
        if ANDROID_AVAILABLE:
            activity.bind(on_activity_result=self._on_android_activity_result)

    def _registrar_diagnostico_popup(self, evento, popup=None, detalle=""):
        """Registra eventos del panel de propiedades para diagnosticar el cierre en Android."""
        try:
            abierto = getattr(popup, "_is_open", None) if popup is not None else None
            linea = "[FDT_POPUP_DIAG] evento=%s abierto=%s detalle=%s" % (
                evento, abierto, detalle
            )
            print(linea, flush=True)
            ruta = os.path.join(self.user_data_dir, "diagnostico_popup.log")
            with open(ruta, "a", encoding="utf-8") as archivo:
                archivo.write(linea + "\n")
        except Exception as exc:
            try:
                print("[FDT_POPUP_DIAG] no_se_pudo_guardar_log: %r" % (exc,), flush=True)
            except Exception:
                pass

    def on_resume(self):
        # Si Android devuelve el foco pero no entrega on_activity_result,
        # mostrar un diagnóstico en vez de dejar la importación aparentemente congelada.
        if self._android_callback:
            Clock.schedule_once(self._verificar_resultado_android, 1.5)

    def _verificar_resultado_android(self, _dt):
        if self._android_callback:
            tipo, guardar = self._android_callback
            self._android_callback = None
            mensaje = (
                "La aplicación volvió del selector de Android, pero no recibió "
                "el evento on_activity_result. Operación: %s; guardar=%s. "
                "Esto apunta al retorno del selector, antes de leer o mostrar la imagen."
                % (tipo, guardar)
            )
            self.estado.text = "Android no devolvió el resultado del selector."
            self._mostrar_error_tecnico(
                "Android no entregó el resultado del selector",
                RuntimeError(mensaje),
            )

    def _aplicar_gradiente(self, widget, orientacion):
        # El fondo se compone de franjas de color; no intercepta toques ni
        # modifica la jerarquía de widgets o los gestos del editor.
        franjas = 64
        instrucciones = []
        with widget.canvas.before:
            for i in range(franjas):
                t = i / max(1, franjas - 1)
                if orientacion == "vertical":
                    v = 0.25 * (1.0 - t)
                else:
                    v = 0.25 * (1.0 - abs(2.0 * t - 1.0))
                instrucciones.append((Color(v, v, v, 1), Rectangle()))
        def actualizar(*_args):
            x, y = widget.pos
            w, h = widget.size
            for i, (color, rect) in enumerate(instrucciones):
                t = i / franjas
                if orientacion == "vertical":
                    rect.pos = (x, y + h * t)
                    rect.size = (w, h / franjas + 1)
                    valor = 0.25 * (1.0 - ((i + 0.5) / franjas))
                else:
                    rect.pos = (x + w * t, y)
                    rect.size = (w / franjas + 1, h)
                    valor = 0.25 * (1.0 - abs(2.0 * ((i + 0.5) / franjas) - 1.0))
                color.r = valor
                color.g = valor
                color.b = valor
        widget.bind(pos=actualizar, size=actualizar)
        actualizar()

    def on_start(self):
        # Si la sesión anterior terminó inesperadamente, mostrar sus últimas
        # marcas/traceback para poder identificar el punto real del cierre.
        previo = getattr(self, "_diagnostico_crash_anterior", "")
        if previo.strip():
            def mostrar_diagnostico(_dt):
                contenido = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
                contenido.add_widget(Label(
                    text="Se recuperó el registro de la sesión anterior. Toma una captura de este texto.",
                    size_hint_y=None, height=dp(52),
                ))
                texto = TextInput(
                    text=previo[-9000:], readonly=True, multiline=True,
                    size_hint_y=1,
                )
                contenido.add_widget(texto)
                contenido.add_widget(Button(
                    text="Cerrar diagnóstico", size_hint_y=None, height=dp(46),
                    on_release=lambda _b: popup.dismiss(),
                ))
                popup = Popup(
                    title="Diagnóstico del cierre anterior",
                    content=contenido, size_hint=(0.96, 0.92),
                )
                popup.open()
            Clock.schedule_once(mostrar_diagnostico, 0.8)

    def _marca_diagnostico_crash(self, etapa):
        try:
            archivo = getattr(self, "_diagnostico_crash_file", None)
            if archivo:
                archivo.write("ETAPA: %s\n" % etapa)
                archivo.flush()
        except Exception:
            pass

    def build(self):
        root = BoxLayout(orientation="vertical")
        barra = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6), padding=(dp(6), dp(5)))
        self._aplicar_gradiente(barra, "vertical")
        barra.add_widget(HamburgerButton(on_release=lambda _: self.abrir_menu()))
        titulo = Label(text="Configurador de Formatos", halign="left", valign="middle", font_size="17sp")
        titulo.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        barra.add_widget(titulo)
        self.estado_menu = Label(text="Listo", size_hint_x=None, width=dp(82), font_size="12sp", halign="right", valign="middle")
        self.estado_menu.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        barra.add_widget(self.estado_menu)
        root.add_widget(barra)

        tools = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(3), padding=(dp(3), dp(2)))
        self._aplicar_gradiente(tools, "vertical")
        icon_root = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "iconos", "configurador")
        self.tool_buttons = {}
        for icon_file, tool in TOOLS:
            icon_path = os.path.join(icon_root, icon_file)
            button = ToolButton(
                self,
                text="",
                size_hint=(None, 1),
                width=dp(44),
                background_normal="",
                background_down="",
                background_color=(0.30, 0.30, 0.30, 1) if tool == self.tool else (0, 0, 0, 0),
                border=(0, 0, 0, 0),
                on_release=lambda _, t=tool: self.set_tool(t),
            )
            # Dibujar el PNG directamente en el canvas del botón evita que
            # un widget Image hijo quede mal posicionado o fuera de la barra.
            if not os.path.isfile(icon_path):
                print("ERROR: No existe el icono de herramienta: " + icon_path)
            else:
                try:
                    textura_icono = CoreImage(icon_path).texture
                    with button.canvas.after:
                        Color(1, 1, 1, 1)
                        rect_icono = Rectangle(texture=textura_icono)

                    def actualizar_icono(_inst=None, *_args, boton=button, rect=rect_icono):
                        lado = dp(32)
                        rect.pos = (
                            boton.x + (boton.width - lado) / 2.0,
                            boton.y + (boton.height - lado) / 2.0,
                        )
                        rect.size = (lado, lado)

                    button.bind(pos=actualizar_icono, size=actualizar_icono)
                    actualizar_icono()
                except Exception:
                    print("ERROR: No se pudo cargar el icono de herramienta: " + icon_path)
                    traceback.print_exc()
            self.tool_buttons[tool] = button
            tools.add_widget(button)
        tools.add_widget(Button(text="−", size_hint_x=None, width=dp(38), on_release=lambda _: self.set_zoom(self.scale * 0.8)))
        self.zoom_label = Label(text="100%", size_hint_x=None, width=dp(54))
        tools.add_widget(self.zoom_label)
        tools.add_widget(Button(text="+", size_hint_x=None, width=dp(38),
                                on_release=lambda _: self.set_zoom(self.scale * 1.25)))
        root.add_widget(tools)

        self.editor = CanvasEditor(self)
        self._aplicar_gradiente(self.editor, "horizontal")
        root.add_widget(self.editor)

        self.estado = Label(text="Listo. Importe una plantilla para comenzar.", size_hint_y=None, height=dp(32), halign="left")
        root.add_widget(self.estado)
        self._inicializar_cursor_raton()
        # En Android no se registran atajos de teclado físico.
        Window.bind(mouse_pos=self._mover_cursor_raton)
        return root

    def abrir_menu(self):
        panel = ModalView(
            size_hint=(1, 1),
            pos_hint={"x": 0, "y": 0},
            auto_dismiss=True,
            background_color=(0, 0, 0, 0),
            overlay_color=(0, 0, 0, 0.55),
        )
        contenido = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            padding=dp(10),
            size_hint=(0.88, 1),
            pos_hint={"x": 0, "y": 0},
        )
        with contenido.canvas.before:
            Color(0.05, 0.05, 0.05, 1)
            menu_background = Rectangle(pos=contenido.pos, size=contenido.size)
        contenido.bind(pos=lambda inst, value: setattr(menu_background, "pos", value))
        contenido.bind(size=lambda inst, value: setattr(menu_background, "size", value))
        encabezado = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6))
        encabezado.add_widget(Label(text="MENÚ", font_size="20sp", halign="left", valign="middle"))
        encabezado.add_widget(Button(text="X", size_hint_x=None, width=dp(48), font_size="24sp", on_release=lambda _: panel.dismiss()))
        contenido.add_widget(encabezado)

        # Las opciones van dentro de una lista desplazable; el encabezado
        # permanece fijo y el menú siempre comienza mostrando ARCHIVO.
        scroll = ScrollView(
            do_scroll_x=False,
            do_scroll_y=True,
            scroll_y=1,
        )
        lista_menu = BoxLayout(
            orientation="vertical",
            spacing=dp(6),
            size_hint_y=None,
        )
        lista_menu.bind(minimum_height=lista_menu.setter("height"))
        scroll.add_widget(lista_menu)
        contenido.add_widget(scroll)

        def seccion(texto):
            lista_menu.add_widget(Label(text=texto, size_hint_y=None, height=dp(28), halign="left", font_size="13sp"))

        def opcion(texto, accion):
            b = Button(text=texto, size_hint_y=None, height=dp(46), font_size="15sp")
            b.bind(size=lambda inst, val: setattr(inst, "text_size", (val[0] - dp(20), val[1])))
            def ejecutar_accion(_):
                panel.dismiss()
                # Esperar a que el menú termine de cerrarse antes de abrir
                # el selector nativo de archivos de Android.
                Clock.schedule_once(lambda dt: accion(), 0.15)
            b.bind(on_release=ejecutar_accion)
            lista_menu.add_widget(b)

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

    def _hay_ventana_secundaria_abierta(self):
        """Evita ejecutar atajos mientras haya un menú, diálogo o modal abierto."""
        pendientes = list(getattr(Window, "children", []) or [])
        visitados = set()
        while pendientes:
            widget = pendientes.pop()
            if id(widget) in visitados:
                continue
            visitados.add(id(widget))
            # No ejecutar atajos globales mientras se escribe. En Android, el
            # teclado virtual puede emitir eventos de tecla con un TextInput
            # enfocado aunque la detección del Popup varíe según el backend.
            if isinstance(widget, TextInput) and getattr(widget, "focus", False):
                return True
            if isinstance(widget, (Popup, ModalView)) and getattr(widget, "_is_open", False):
                return True
            pendientes.extend(list(getattr(widget, "children", []) or []))
        return False

    def _manejar_atajo_teclado(self, window, keycode, text, modifiers):
        """Atajos para teclado físico; ignora cualquier ventana/modal secundaria."""
        # Popup no siempre aparece en Window.children en Android. La bandera
        # explícita evita que el teclado virtual active atajos al editar propiedades.
        if getattr(self, "_propiedades_abiertas", False):
            return False
        if self._hay_ventana_secundaria_abierta():
            return False
        nombre = str(keycode[1] if isinstance(keycode, (tuple, list)) and len(keycode) > 1 else keycode).lower()
        texto = (text or "").lower()
        # Normalizar operadores y teclas de navegación del teclado numérico.
        # En distintos teclados Kivy reporta nombres distintos según Num Lock.
        mapa_teclado_numerico = {
            "kp_left": "left", "kp_4": "left", "kp4": "left", "numpad4": "left",
            "kp_right": "right", "kp_6": "right", "kp6": "right", "numpad6": "right",
            "kp_up": "up", "kp_8": "up", "kp8": "up", "numpad8": "up",
            "kp_down": "down", "kp_2": "down", "kp2": "down", "numpad2": "down",
            "kp_add": "plus", "kp_subtract": "minus", "kp_multiply": "asterisk",
        }
        nombre = mapa_teclado_numerico.get(nombre, nombre)
        texto = mapa_teclado_numerico.get(texto, texto)
        mods = {str(mod).lower() for mod in (modifiers or [])}
        control = "ctrl" in mods or "control" in mods
        shift = "shift" in mods
        alt = "alt" in mods
        if control:
            if alt:
                return False
            if nombre == "r":
                # Ctrl+R no está asignado a ninguna acción.
                return True
            if nombre == "n":
                self.nuevo()
            elif nombre == "o":
                self.abrir()
            elif nombre == "s":
                self.guardar_como_fdt() if shift else self.guardar()
            elif nombre == "w":
                # Ctrl+W cierra el formato actual y deja abierta la aplicación.
                self.nuevo()
            else:
                return False
            return True
        if shift or alt:
            # Shift solo se admite para producir + o * en algunos teclados.
            if texto not in ("+", "*") and nombre not in ("+", "plus", "asterisk"):
                return False
        herramientas = {"a": FIELD_TYPE_TEXT, "s": "select", "d": "hand",
                        "z": "zoom", "q": FIELD_TYPE_NUMBER, "w": FIELD_TYPE_IMAGE}
        tecla_atajo = nombre if nombre in herramientas else texto
        if tecla_atajo in herramientas and not shift and not alt:
            self.set_tool(herramientas[tecla_atajo])
        elif nombre == "l" and not shift and not alt:
            self.mostrar_lista_campos()
        elif nombre == "t" and not shift and not alt:
            self.editar_salida()
        elif nombre == "i" and not shift and not alt:
            self.importar()
        elif nombre in ("+", "plus", "equal", "kp_add") or texto == "+":
            self.set_zoom(self.scale * 1.25)
        elif nombre in ("-", "minus", "kp_subtract") or texto == "-":
            self.set_zoom(self.scale * 0.8)
        elif nombre in ("*", "asterisk", "kp_multiply") or texto == "*":
            self.set_zoom(1.0)
        else:
            return False
        return True


    def _es_evento_raton(self, touch):
        dispositivo = str(getattr(touch, "device", "") or "").lower()
        boton = str(getattr(touch, "button", "") or "").lower()
        return dispositivo == "mouse" or boton in ("left", "right", "middle") or bool(getattr(touch, "is_mouse_scrolling", False))

    def _inicializar_cursor_raton(self):
        # La capa queda invisible hasta detectar una entrada de ratón físico.
        try:
            with Window.canvas.after:
                self._mouse_cursor_color = Color(1, 1, 1, 0)
                self._mouse_cursor_rect = Rectangle(pos=(-1000, -1000), size=(dp(44), dp(44)))
        except Exception:
            self._mouse_cursor_color = None
            self._mouse_cursor_rect = None

    def _ruta_cursor_herramienta(self):
        iconos = {
            "select": ("assets", "iconos", "configurador", "seleccionar.png"),
            "hand": ("assets", "iconos", "configurador", "desplazar.png"),
            FIELD_TYPE_TEXT: ("assets", "cursores", "cursor_texto.png"),
            FIELD_TYPE_NUMBER: ("assets", "cursores", "cursor_numerico.png"),
            FIELD_TYPE_IMAGE: ("assets", "cursores", "cursor_imagen.png"),
            "zoom": ("assets", "iconos", "configurador", "zoom_mas.png"),
        }
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), *iconos.get(self.tool, iconos["select"]))

    def _activar_cursor_raton(self, posicion=None):
        if self._mouse_cursor_rect is None or self._mouse_cursor_color is None:
            return
        self._mouse_cursor_active = True
        try:
            Window.show_cursor = False
        except Exception:
            pass
        ruta = self._ruta_cursor_herramienta()
        try:
            if ruta not in self._mouse_cursor_texture_cache:
                self._mouse_cursor_texture_cache[ruta] = CoreImage(ruta).texture
            self._mouse_cursor_rect.texture = self._mouse_cursor_texture_cache[ruta]
            self._mouse_cursor_color.a = 1
            if posicion is None:
                posicion = Window.mouse_pos
            self._mover_cursor_raton(Window, posicion)
        except Exception:
            self._mouse_cursor_color.a = 0

    def _mover_cursor_raton(self, _window, posicion):
        if not self._mouse_cursor_active or self._mouse_cursor_rect is None:
            return
        ancho, alto = self._mouse_cursor_rect.size
        # El punto activo está en la esquina superior izquierda de la imagen.
        self._mouse_cursor_rect.pos = (posicion[0], posicion[1] - alto)

    def set_tool(self, tool):
        if self.editor is not None:
            self.editor.cancel_active_gestures()
        self.tool = tool
        for herramienta, boton in getattr(self, "tool_buttons", {}).items():
            boton.background_color = (0.30, 0.30, 0.30, 1) if herramienta == tool else (0, 0, 0, 0)
        if self._mouse_cursor_active:
            self._activar_cursor_raton()
        nombres = {
            "select": "Seleccionar",
            "hand": "Desplazar",
            "zoom": "Lupa",
            FIELD_TYPE_TEXT: "Texto",
            FIELD_TYPE_NUMBER: "Número",
            FIELD_TYPE_IMAGE: "Imagen",
        }
        self.estado.text = "Herramienta: " + nombres.get(tool, str(tool))
        self.estado_menu.text = nombres.get(tool, str(tool))

    def template_position(self):
        # Las coordenadas son relativas al CanvasEditor (StencilView).
        if not self.formato:
            return (dp(20), dp(20))
        ancho = self.formato.template.width * self.scale
        alto = self.formato.template.height * self.scale
        x = (self.editor.width - ancho) / 2.0
        y = (self.editor.height - alto) / 2.0
        if ancho > self.editor.width:
            x = 0
        if alto > self.editor.height:
            y = 0
        return x, y

    def nuevo(self):
        # Un formato nuevo no debe conservar widgets ni referencias a la
        # plantilla anterior. El historial anterior tampoco debe sobrevivir.
        if self.editor is not None:
            self.editor.cancel_active_gestures()
            self.editor.clear_widgets()
            self.editor.template_widget = None
            self.editor._template_core_image = None
        self.clear_drawing_preview()
        limpiar_fdt_temporales()
        self.formato = None
        self.seleccionado = None
        self._visual_template_path = None
        self._undo = []
        self._redo = []
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
            intent.setType("image/*" if tipo == "image" else ("font/*" if tipo == "font" else "*/*"))
            intent.addCategory(Intent.CATEGORY_OPENABLE)
            intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            if guardar:
                # ACTION_CREATE_DOCUMENT necesita permiso explicito de escritura.
                # Sin esta bandera, openOutputStream(uri) falla con SecurityException.
                intent.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION)
                nombre = self.formato.name.strip() if self.formato and self.formato.name.strip() else "formato"
                if not nombre.lower().endswith(".fdt"):
                    nombre += ".fdt"
                intent.putExtra(Intent.EXTRA_TITLE, nombre)
            else:
                intent.addFlags(Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION)
            self._android_callback = (tipo, guardar)
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            self.estado.text = "Esperando selección de archivo en Android..."
            PythonActivity.mActivity.startActivityForResult(intent, 4001)
        except Exception as exc:
            self.estado.text = "Error al abrir selector de Android."
            self._mostrar_error_tecnico("No se pudo abrir el selector", exc)

    def _on_android_activity_result(self, request_code, result_code, intent):
        # El callback de Android puede ejecutarse fuera del hilo gráfico de Kivy.
        # Toda operación que actualice widgets o cree instrucciones gráficas debe
        # ejecutarse en el hilo principal.
        Clock.schedule_once(
            lambda _dt: self._procesar_resultado_android(request_code, result_code, intent),
            0,
        )

    def _procesar_resultado_android(self, request_code, result_code, intent):
        if request_code != 4001 or not self._android_callback:
            return
        tipo, guardar = self._android_callback
        self._android_callback = None
        try:
            Activity = autoclass("android.app.Activity")
            if result_code != Activity.RESULT_OK or intent is None:
                self.estado.text = "Selección cancelada."
                return
            uri = intent.getData()
            if uri is None:
                raise IOError("Android devolvió un resultado sin archivo (URI nula).")
            self.estado.text = "Archivo seleccionado; leyendo contenido..."
            if guardar:
                uri = self._asegurar_extension_fdt_uri(uri)
                self._guardar_fdt_uri(uri)
            else:
                ruta = self._copiar_uri_a_cache(uri, tipo)
                if tipo == "fdt":
                    self._abrir_ruta(ruta)
                elif tipo == "font":
                    if self._font_import_target:
                        destino_fuente = self._font_import_target
                        self._font_import_target = None
                        destino_fuente(ruta)
                    else:
                        raise RuntimeError("No hay un campo esperando la tipografía importada.")
                else:
                    self._importar_ruta(ruta)
        except Exception as exc:
            self.estado.text = "Error al procesar el archivo seleccionado."
            self._mostrar_error_tecnico("Error al recibir o copiar el archivo", exc)

    def _nombre_display_uri(self, resolver, uri):
        # Primero se consulta el nombre publicado por el proveedor SAF.
        try:
            OpenableColumns = autoclass("android.provider.OpenableColumns")
            cursor = resolver.query(uri, None, None, None, None)
            if cursor is not None:
                try:
                    if cursor.moveToFirst():
                        indice = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                        if indice >= 0:
                            valor = cursor.getString(indice)
                            if valor:
                                return str(valor)
                finally:
                    cursor.close()
        except Exception:
            pass

        # Algunos proveedores no exponen DISPLAY_NAME en la consulta.
        # En esos casos, intentar recuperar el nombre del ID documental SAF.
        try:
            DocumentsContract = autoclass("android.provider.DocumentsContract")
            document_id = str(DocumentsContract.getDocumentId(uri))
            ruta_documental = unquote(document_id).replace("\\", "/")
            nombre = ruta_documental.rsplit("/", 1)[-1].strip()
            if nombre and ( "." in nombre or ":" in document_id or "/" in ruta_documental ):
                return nombre
        except Exception:
            pass
        return ""

    def _asegurar_extension_fdt_uri(self, uri):
        """Valida la extensión y añade .fdt solo cuando el nombre no tiene extensión."""
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()
        nombre = self._nombre_display_uri(resolver, uri).strip()
        if not nombre:
            raise IOError("Android no devolvió el nombre del archivo que se va a guardar.")

        extension = os.path.splitext(nombre)[1]
        if extension:
            if extension.lower() != ".fdt":
                raise IOError(
                    "La extensión del archivo no es válida. Use .fdt o escriba el nombre sin extensión."
                )
            return uri

        DocumentsContract = autoclass("android.provider.DocumentsContract")
        nuevo_nombre = nombre + ".fdt"
        try:
            uri_renombrado = DocumentsContract.renameDocument(resolver, uri, nuevo_nombre)
        except Exception as exc:
            raise IOError(
                "No se pudo añadir automáticamente la extensión .fdt al archivo. "
                "Elija una carpeta o proveedor de archivos que permita renombrar documentos."
            ) from exc
        if uri_renombrado is None:
            raise IOError(
                "Android no pudo aplicar la extensión .fdt automáticamente. "
                "Elija una carpeta o proveedor de archivos que permita renombrar documentos."
            )
        return uri_renombrado

    def _copiar_uri_a_cache(self, uri, tipo):
        PythonActivity = autoclass("org.kivy.android.PythonActivity")
        resolver = PythonActivity.mActivity.getContentResolver()
        flujo = resolver.openInputStream(uri)
        if flujo is None:
            raise IOError("Android no pudo abrir el archivo seleccionado (flujo nulo).")
        try:
            nombre = self._nombre_display_uri(resolver, uri)
            extension = os.path.splitext(nombre)[1].lower()
            
            if tipo == "image":
                mime_type = str(resolver.getType(uri) or "").lower()
                if not extension or extension not in [".jpg", ".jpeg", ".png", ".bmp", ".webp"]:
                    if "png" in mime_type:
                        extension = ".png"
                    elif "webp" in mime_type:
                        extension = ".webp"
                    else:
                        extension = ".jpg"
            
            if tipo == "fdt":
                extension = ".fdt"
            elif tipo == "font":
                if extension not in (".ttf", ".otf", ".ttc"):
                    mime_type = str(resolver.getType(uri) or "").lower()
                    if "opentype" in mime_type:
                        extension = ".otf"
                    elif "truetype" in mime_type or "font" in mime_type:
                        extension = ".ttf"
                    else:
                        raise IOError("El archivo seleccionado no parece ser una fuente .ttf, .otf o .ttc.")
            
            extension = extension if extension else ".jpg"

            ruta = os.path.join(
                PythonActivity.mActivity.getCacheDir().getAbsolutePath(),
                "plantilla_temp_" + uuid.uuid4().hex + extension,
            )
            
            # PyJNIus de esta compilación no exporta jarray; convierte bytearray a Java byte[].
            buffer = bytearray(65536)
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
                raise IOError("El archivo copiado a la caché está vacío o no se creó.")
            return ruta
        finally:
            flujo.close()

    def _crear_imagen_visual(self, ruta, imagen):
        # El empaquetado FDT normaliza la imagen al guardar. Al abrir, se
        # conserva la ruta extraída para no recomprimir una plantilla existente.
        if not os.path.isfile(ruta):
            raise IOError("No existe la imagen extraída del FDT.")
        if imagen.mode != "RGB":
            raise ValueError("La imagen de plantilla no pudo convertirse a RGB.")
        return ruta

    def _importar_ruta(self, ruta):
        try:
            if not os.path.isfile(ruta):
                raise IOError(f"El archivo no existe en la ruta: {ruta}")
            
            if os.path.getsize(ruta) == 0:
                raise IOError("El archivo copiado tiene 0 bytes. Fallo de permisos o de copia en Android.")

            from PIL import Image
            imagen = Image.open(ruta).convert("RGB")
            
            self.formato = Formato(
                name=os.path.splitext(os.path.basename(ruta))[0],
                template=TemplateInfo(path=ruta, width=imagen.width, height=imagen.height, dpi=300, mode="RGB"),
            )
            
            self.scale = self._calcular_zoom_inicial(imagen.width, imagen.height)
            self._visual_template_path = ruta
            self.seleccionado = None
            self._undo = []
            self._redo = []
            self.editor.scale = self.scale
            
            self.editor.cargar_plantilla(ruta)
            limpiar_fdt_temporales(keep_path=ruta)
            self.actualizar_zoom()
            
            self.estado.text = f"ÉXITO: Imagen {imagen.width}x{imagen.height}px cargada."
            
        except Exception as exc:
            self.estado.text = "FALLO CRÍTICO AL IMPORTAR"
            self._mostrar_error_tecnico("Fallo al abrir la imagen de plantilla", exc)

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
            try:
                self.editor.cargar_plantilla(self._visual_template_path)
            except Exception as exc:
                self._visual_template_path = None
                raise IOError("La plantilla del FDT no se pudo mostrar: " + str(exc))
            limpiar_fdt_temporales(keep_path=formato.template.path)
            self.actualizar_zoom()
            self.estado.text = "FDT abierto. %d campo(s)." % len(self.formato.fields)
        except Exception as exc:
            self.estado.text = "Error al abrir el archivo FDT."
            self._mostrar_error_tecnico("Fallo al abrir el archivo FDT", exc)

    def _calcular_zoom_inicial(self, width, height):
        # ConfiguradorApp hereda de App, no de Widget: sus dimensiones se
        # consultan en el editor ya montado o, como respaldo, en la ventana.
        editor_ancho = self.editor.width if self.editor is not None else 0
        editor_alto = self.editor.height if self.editor is not None else 0
        if editor_ancho > dp(100):
            ancho_disponible = max(dp(100), editor_ancho - dp(20))
        else:
            ancho_disponible = max(dp(100), Window.width - dp(40))
        if editor_alto > dp(100):
            alto_disponible = max(dp(100), editor_alto - dp(20))
        else:
            alto_disponible = max(dp(100), Window.height - dp(150))
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

            # Validar el nombre antes de escribir: solo se acepta .fdt o ningún sufijo.
            nombre = self._nombre_display_uri(resolver, uri).strip()
            if not nombre:
                raise IOError("Android no devolvió el nombre del archivo que se va a guardar.")
            extension = os.path.splitext(nombre)[1]
            if extension and extension.lower() != ".fdt":
                raise IOError(
                    "La extensión del archivo no es válida. Use .fdt o escriba el nombre sin extensión."
                )

            temporal = os.path.join(actividad.getCacheDir().getAbsolutePath(), "fdt_" + uuid.uuid4().hex + ".fdt")
            guardar_fdt(self.formato, temporal)
            entrada = None
            salida = None
            try:
                entrada = open(temporal, "rb")
                salida = resolver.openOutputStream(uri)
                if salida is None:
                    raise IOError("Android no pudo abrir el destino.")
                # Esta compilación de PyJNIus no incluye jarray.
                # Pasar bytearray al método Java, igual que en la copia desde URI.
                while True:
                    datos = entrada.read(65536)
                    if not datos:
                        break
                    buffer = bytearray(datos)
                    salida.write(buffer, 0, len(buffer))
                salida.flush()
            finally:
                if entrada is not None:
                    entrada.close()
                if salida is not None:
                    salida.close()

            # Escribir primero sobre la URI autorizada por el selector.
            # Renombrar después evita abrir para escritura una URI nueva sin permiso.
            self._asegurar_extension_fdt_uri(uri)
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
        encabezado.add_widget(Button(text="X", size_hint_x=None, width=dp(48), on_release=lambda _: panel.dismiss()))
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

    def _fuentes_disponibles(self, fuente_actual=""):
        """Devuelve rutas reales de fuentes utilizables y mantiene la fuente actual."""
        fuentes = []
        actual = str(fuente_actual or "").strip()
        if actual and os.path.isfile(actual):
            fuentes.append(actual)

        raices = [
            os.path.join(os.path.dirname(__file__), "fonts"),
            os.path.join(os.path.dirname(__file__), "data", "fonts"),
            "/system/fonts",
            "/usr/share/fonts",
            os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts"),
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "Windows", "Fonts"),
        ]
        try:
            from kivy.resources import resource_find
            kivy_fuente = resource_find("data/fonts/Roboto-Regular.ttf")
            if kivy_fuente and os.path.isfile(kivy_fuente):
                fuentes.append(kivy_fuente)
        except Exception:
            pass

        extensiones = (".ttf", ".otf", ".ttc")
        for raiz in raices:
            if not raiz or not os.path.isdir(raiz):
                continue
            try:
                for carpeta, _subcarpetas, archivos in os.walk(raiz):
                    for archivo in archivos:
                        if archivo.lower().endswith(extensiones):
                            ruta = os.path.join(carpeta, archivo)
                            if ruta not in fuentes:
                                fuentes.append(ruta)
                            if len(fuentes) >= 250:
                                break
                    if len(fuentes) >= 250:
                        break
            except OSError:
                continue
            if len(fuentes) >= 250:
                break

        # Si el FDT guarda una referencia legible por nombre y no por ruta, conservarla.
        if actual and actual not in fuentes and not os.path.isfile(actual):
            fuentes.insert(0, actual)
        return fuentes

    def mostrar_propiedades(
        self, campo, es_nuevo=False, undo_antes=None, redo_antes=None,
        seleccionado_antes=None,
    ):
        self._popup_propiedades_intentos += 1
        self._registrar_diagnostico_popup(
            "SOLICITUD_APERTURA",
            detalle="intento=%d campo=%s" % (
                self._popup_propiedades_intentos,
                getattr(campo, "field_id", None),
            ),
        )
        try:
            pila = "".join(traceback.format_stack(limit=6))
            self._registrar_diagnostico_popup("PILA_APERTURA", detalle=pila)
        except Exception:
            pass
        if not campo:
            self._aviso("Seleccione un campo.")
            return

        es_imagen = campo.field_type == FIELD_TYPE_IMAGE
        estilo = campo.text_style
        # Conservar la posición de la plantilla anterior a la apertura del teclado.
        posicion_plantilla_inicial = (
            tuple(self.editor.template_widget.pos)
            if self.editor and self.editor.template_widget is not None
            else None
        )
        contenido = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(10))
        # Los botones van justo debajo del título/línea azul del Popup para
        # que sigan accesibles cuando Android despliega el teclado.
        botones = BoxLayout(size_hint_y=None, height=dp(48), spacing=dp(8))
        contenido.add_widget(botones)
        scroll = ScrollView(do_scroll_x=False, do_scroll_y=True)
        form = GridLayout(cols=1, spacing=dp(7), size_hint_y=None)
        form.bind(minimum_height=form.setter("height"))

        # Primera línea: número de turno e identificador calculados por el sistema.
        identificacion = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        turno_label = Label(
            text="Turno: %02d" % campo.order,
            size_hint_x=0.42,
            halign="left",
            valign="middle",
        )
        turno_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        identificacion.add_widget(turno_label)
        id_label = Label(
            text="Identificador: %s" % campo.field_id,
            size_hint_x=0.58,
            halign="right",
            valign="middle",
        )
        id_label.bind(size=lambda inst, val: setattr(inst, "text_size", val))
        identificacion.add_widget(id_label)
        form.add_widget(identificacion)

        form.add_widget(Label(
            text="Pregunta que verá el capturador",
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        ))
        pregunta = TextInput(
            text=campo.question or "",
            hint_text="Escriba aquí la pregunta para solicitar el dato",
            multiline=True,
            size_hint_y=None,
            height=dp(76),
            padding=(dp(8), dp(8)),
        )
        form.add_widget(pregunta)

        estado_mayusculas = {"valor": bool(getattr(campo, "uppercase", False))}
        fuente_spinner = None
        tamano = None
        boton_negrita = None
        boton_cursiva = None
        alineacion = None
        color_boton = None
        color_r = color_g = color_b = None
        orientacion = None

        if not es_imagen:
            fila_mayusculas = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            boton_mayusculas = Button(
                text="A" if estado_mayusculas["valor"] else "a",
                size_hint_x=None,
                width=dp(48),
                background_normal="",
                background_color=(0.12, 0.48, 0.78, 1) if estado_mayusculas["valor"] else (0.22, 0.22, 0.22, 1),
            )
            def alternar_mayusculas(_boton):
                estado_mayusculas["valor"] = not estado_mayusculas["valor"]
                boton_mayusculas.text = "A" if estado_mayusculas["valor"] else "a"
                boton_mayusculas.background_color = (
                    (0.12, 0.48, 0.78, 1) if estado_mayusculas["valor"] else (0.22, 0.22, 0.22, 1)
                )
            boton_mayusculas.bind(on_release=alternar_mayusculas)
            fila_mayusculas.add_widget(boton_mayusculas)
            fila_mayusculas.add_widget(Label(text="Convertir captura a MAYÚSCULAS", halign="left"))
            form.add_widget(fila_mayusculas)

            form.add_widget(Label(
                text="Tipografía y tamaño",
                size_hint_y=None,
                height=dp(23),
                halign="left",
            ))
            fuentes = self._fuentes_disponibles(estilo.font_family)
            fuente_por_nombre = {}
            for ruta in fuentes:
                nombre = os.path.basename(ruta) if os.path.isfile(ruta) else ruta
                # Si hay nombres repetidos, el más reciente queda como opción visible.
                fuente_por_nombre[nombre] = ruta
            nombres = sorted(fuente_por_nombre.keys(), key=lambda item: item.lower())
            actual_nombre = (
                os.path.basename(estilo.font_family)
                if estilo.font_family and os.path.isfile(estilo.font_family)
                else estilo.font_family
            )
            if actual_nombre and actual_nombre not in nombres:
                nombres.insert(0, actual_nombre)
                fuente_por_nombre[actual_nombre] = estilo.font_family
            if not nombres:
                nombres = ["Predeterminada"]
                fuente_por_nombre["Predeterminada"] = ""

            fila_fuente = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
            fuente_spinner = Spinner(
                text=actual_nombre if actual_nombre in nombres else nombres[0],
                values=nombres,
                size_hint_x=1,
                sync_height=True,
            )
            fila_fuente.add_widget(fuente_spinner)
            importar_fuente = Button(
                text="＋ Fuente",
                size_hint_x=None,
                width=dp(104),
            )
            fila_fuente.add_widget(importar_fuente)
            form.add_widget(fila_fuente)

            fila_tamano = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
            fila_tamano.add_widget(Label(text="Tamaño (px)", size_hint_x=None, width=dp(105)))
            tamano = TextInput(
                text=str(estilo.font_size_px),
                multiline=False,
                input_filter="int",
                size_hint_x=None,
                width=dp(92),
            )
            fila_tamano.add_widget(tamano)
            fila_tamano.add_widget(Label(text="Tamaño en píxeles del documento", halign="left"))
            form.add_widget(fila_tamano)

            def abrir_fuente(_boton):
                if ANDROID_AVAILABLE:
                    self._font_import_target = lambda ruta: agregar_fuente_importada(ruta)
                    self._abrir_selector_android("font", guardar=False)
                    return
                layout_fuente = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(6))
                selector = FileChooserListView(path=os.path.expanduser("~"), dirselect=False)
                selector.filters = ["*.ttf", "*.otf", "*.ttc"]
                layout_fuente.add_widget(selector)
                ventana_fuente = Popup(
                    title="Importar tipografía",
                    content=layout_fuente,
                    size_hint=(0.94, 0.9),
                )
                botones_fuente = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
                botones_fuente.add_widget(Button(
                    text="Cancelar",
                    on_release=lambda _b: ventana_fuente.dismiss(),
                ))
                def seleccionar_fuente(_b):
                    if selector.selection:
                        ruta = selector.selection[0]
                        ventana_fuente.dismiss()
                        agregar_fuente_importada(ruta)
                botones_fuente.add_widget(Button(text="Importar", on_release=seleccionar_fuente))
                layout_fuente.add_widget(botones_fuente)
                ventana_fuente.open()

            def agregar_fuente_importada(ruta):
                if not ruta or not os.path.isfile(ruta):
                    self._aviso("No se pudo leer el archivo de tipografía seleccionado.")
                    return
                extension = os.path.splitext(ruta)[1].lower()
                if extension not in (".ttf", ".otf", ".ttc"):
                    self._aviso("Seleccione un archivo de fuente .ttf, .otf o .ttc.")
                    return
                nombre = os.path.basename(ruta)
                fuente_por_nombre[nombre] = ruta
                if nombre not in fuente_spinner.values:
                    fuente_spinner.values = tuple(list(fuente_spinner.values) + [nombre])
                fuente_spinner.text = nombre
                self.estado.text = "Tipografía seleccionada; se integrará al guardar el FDT."

            importar_fuente.bind(on_release=abrir_fuente)

            fila_estilo = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            boton_negrita = Button(
                text="N",
                size_hint_x=None,
                width=dp(42),
                bold=True,
                background_normal="",
                background_color=(0.12, 0.48, 0.78, 1) if estilo.bold else (0.22, 0.22, 0.22, 1),
            )
            boton_cursiva = Button(
                text="I",
                size_hint_x=None,
                width=dp(42),
                italic=True,
                background_normal="",
                background_color=(0.12, 0.48, 0.78, 1) if estilo.italic else (0.22, 0.22, 0.22, 1),
            )
            fila_estilo.add_widget(boton_negrita)
            fila_estilo.add_widget(boton_cursiva)
            fila_estilo.add_widget(Label(text="Alineación", halign="left"))
            alineaciones = {
                "Izquierda": "left",
                "Centro": "center",
                "Derecha": "right",
                "Justificar": "justify",
            }
            etiqueta_alineacion = next(
                (nombre for nombre, valor in alineaciones.items() if valor == estilo.alignment),
                "Izquierda",
            )
            alineacion = Spinner(
                text=etiqueta_alineacion,
                values=tuple(alineaciones.keys()),
                size_hint_x=None,
                width=dp(132),
            )
            fila_estilo.add_widget(alineacion)
            form.add_widget(fila_estilo)

            estado_negrita = {"valor": bool(estilo.bold)}
            estado_cursiva = {"valor": bool(estilo.italic)}
            def alternar_negrita(_b):
                estado_negrita["valor"] = not estado_negrita["valor"]
                boton_negrita.background_color = (
                    (0.12, 0.48, 0.78, 1) if estado_negrita["valor"] else (0.22, 0.22, 0.22, 1)
                )
            def alternar_cursiva(_b):
                estado_cursiva["valor"] = not estado_cursiva["valor"]
                boton_cursiva.background_color = (
                    (0.12, 0.48, 0.78, 1) if estado_cursiva["valor"] else (0.22, 0.22, 0.22, 1)
                )
            boton_negrita.bind(on_release=alternar_negrita)
            boton_cursiva.bind(on_release=alternar_cursiva)

            form.add_widget(Label(
                text="Color de tipografía (RGB)",
                size_hint_y=None,
                height=dp(24),
                halign="left",
            ))
            fila_color = BoxLayout(size_hint_y=None, height=dp(42), spacing=dp(8))
            color_boton = Button(
                text="",
                size_hint=(None, None),
                width=dp(42),
                height=dp(42),
                background_normal="",
                background_color=(
                    estilo.color.r / 255.0,
                    estilo.color.g / 255.0,
                    estilo.color.b / 255.0,
                    1,
                ),
            )
            fila_color.add_widget(color_boton)
            fila_color.add_widget(Label(text="R", size_hint_x=None, width=dp(18)))
            color_r = TextInput(text=str(estilo.color.r), multiline=False, input_filter="int", size_hint_x=None, width=dp(55))
            fila_color.add_widget(color_r)
            fila_color.add_widget(Label(text="G", size_hint_x=None, width=dp(18)))
            color_g = TextInput(text=str(estilo.color.g), multiline=False, input_filter="int", size_hint_x=None, width=dp(55))
            fila_color.add_widget(color_g)
            fila_color.add_widget(Label(text="B", size_hint_x=None, width=dp(18)))
            color_b = TextInput(text=str(estilo.color.b), multiline=False, input_filter="int", size_hint_x=None, width=dp(55))
            fila_color.add_widget(color_b)
            form.add_widget(fila_color)

            def actualizar_muestra_color(*_args):
                try:
                    rgb = tuple(max(0, min(255, int(entrada.text or "0"))) / 255.0 for entrada in (color_r, color_g, color_b))
                    color_boton.background_color = (rgb[0], rgb[1], rgb[2], 1)
                except Exception:
                    pass
            for entrada in (color_r, color_g, color_b):
                entrada.bind(text=actualizar_muestra_color)

            def abrir_selector_color(_boton):
                # Selector inspirado en el panel SERCO: muestra de color y paleta HSV.
                # La importación debe ocurrir antes de convertir el RGB actual;
                # de otro modo NameError cerraba la aplicación al tocar la muestra.
                from colorsys import hsv_to_rgb, rgb_to_hsv
                rgb_original = (color_r.text, color_g.text, color_b.text)
                ventana_color = ModalView(size_hint=(0.92, 0.78), background_color=(0.08, 0.08, 0.08, 1))
                raiz_color = BoxLayout(orientation="vertical", spacing=dp(8), padding=dp(10))
                raiz_color.add_widget(Label(text="Selector HSV: elija el tono y después el matiz/brillo", size_hint_y=None, height=dp(38)))

                # Muestra visible del color que se está seleccionando.
                fila_muestra_selector = BoxLayout(
                    orientation="horizontal",
                    size_hint_y=None,
                    height=dp(42),
                    spacing=dp(10),
                )
                fila_muestra_selector.add_widget(Label(
                    text="Color seleccionado:",
                    size_hint_x=1,
                    halign="left",
                    valign="middle",
                ))
                muestra_selector_color = Button(
                    text="",
                    size_hint=(None, None),
                    size=(dp(52), dp(36)),
                    background_normal="",
                    background_down="",
                    background_color=(
                        max(0, min(255, int(color_r.text or "0"))) / 255.0,
                        max(0, min(255, int(color_g.text or "0"))) / 255.0,
                        max(0, min(255, int(color_b.text or "0"))) / 255.0,
                        1,
                    ),
                )
                fila_muestra_selector.add_widget(muestra_selector_color)
                raiz_color.add_widget(fila_muestra_selector)

                tono_inicial = rgb_to_hsv(
                    max(0, min(255, int(color_r.text or "0"))) / 255.0,
                    max(0, min(255, int(color_g.text or "0"))) / 255.0,
                    max(0, min(255, int(color_b.text or "0"))) / 255.0,
                )[0]
                selector_hue = Slider(min=0, max=1, value=tono_inicial, size_hint_y=None, height=dp(35))
                # La paleta se dibuja en un lienzo 2D: saturación horizontal y valor vertical.
                from io import BytesIO
                from PIL import Image as PILImage
                class PaletaSV(Widget):
                    def __init__(self, hue, **kwargs):
                        super().__init__(**kwargs)
                        self.hue = hue
                        self._texture = None
                        self.bind(pos=self.redibujar, size=self.redibujar)
                        self.redibujar()
                    def redibujar(self, *_args):
                        ancho, alto = 160, 160
                        imagen_paleta = PILImage.new("RGB", (ancho, alto))
                        pixeles = imagen_paleta.load()
                        for py in range(alto):
                            valor = 1.0 - py / float(alto - 1)
                            for px in range(ancho):
                                saturacion = px / float(ancho - 1)
                                rr, gg, bb = hsv_to_rgb(self.hue, saturacion, valor)
                                pixeles[px, py] = (int(rr * 255), int(gg * 255), int(bb * 255))
                        memoria = BytesIO()
                        imagen_paleta.save(memoria, format="PNG")
                        memoria.seek(0)
                        self._texture = CoreImage(memoria, ext="png").texture
                        self.canvas.clear()
                        with self.canvas:
                            Color(1, 1, 1, 1)
                            Rectangle(texture=self._texture, pos=self.pos, size=self.size)
                    def on_touch_down(self, touch):
                        if self.collide_point(*touch.pos):
                            self._pick(touch)
                            return True
                        return super().on_touch_down(touch)
                    def on_touch_move(self, touch):
                        if touch.grab_current is self or self.collide_point(*touch.pos):
                            self._pick(touch)
                            return True
                        return super().on_touch_move(touch)
                    def _pick(self, touch):
                        sat = max(0.0, min(1.0, (touch.x - self.x) / max(1.0, self.width)))
                        val = max(0.0, min(1.0, (touch.y - self.y) / max(1.0, self.height)))
                        rgb = tuple(int(v * 255) for v in hsv_to_rgb(self.hue, sat, val))
                        aplicar_rgb(rgb)
                paleta = PaletaSV(tono_inicial, size_hint=(1, 1))
                raiz_color.add_widget(paleta)
                def aplicar_rgb(rgb):
                    color_r.text, color_g.text, color_b.text = (str(v) for v in rgb)
                    actualizar_muestra_color()
                    muestra_selector_color.background_color = (
                        rgb[0] / 255.0,
                        rgb[1] / 255.0,
                        rgb[2] / 255.0,
                        1,
                    )
                def actualizar_paleta(*_args):
                    paleta.hue = selector_hue.value
                    paleta.redibujar()
                selector_hue.bind(value=actualizar_paleta)
                raiz_color.add_widget(selector_hue)
                def cancelar_selector(_boton):
                    color_r.text, color_g.text, color_b.text = rgb_original
                    actualizar_muestra_color()
                    ventana_color.dismiss()
                botones_color = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(8))
                botones_color.add_widget(Button(text="Cancelar", on_release=cancelar_selector))
                botones_color.add_widget(Button(text="Usar color", on_release=lambda _b: ventana_color.dismiss()))
                raiz_color.add_widget(botones_color)
                ventana_color.add_widget(raiz_color)
                ventana_color.open()
            color_boton.bind(on_release=abrir_selector_color)

            form.add_widget(Label(
                text="Orientación del texto",
                size_hint_y=None,
                height=dp(24),
                halign="left",
            ))
            orientacion = Spinner(
                text="Vertical" if estilo.orientation == "vertical" else "Horizontal",
                values=("Horizontal", "Vertical"),
                size_hint_y=None,
                height=dp(42),
            )
            form.add_widget(orientacion)

        # Se conservan los controles de posición y obligatoriedad existentes.
        form.add_widget(Label(
            text="Ubicación y validación",
            size_hint_y=None,
            height=dp(28),
            halign="left",
        ))
        avanzado = GridLayout(cols=2, spacing=dp(5), size_hint_y=None, height=dp(132))
        entradas_posicion = {}
        for clave, titulo, valor in (
            ("x", "X", campo.position.x),
            ("y", "Y", campo.position.y),
            ("width", "Ancho", campo.position.width),
            ("height", "Alto", campo.position.height),
        ):
            avanzado.add_widget(Label(text=titulo, halign="left"))
            entrada = TextInput(text=str(valor), multiline=False, input_filter="int")
            avanzado.add_widget(entrada)
            entradas_posicion[clave] = entrada
        form.add_widget(avanzado)
        fila_requerido = BoxLayout(size_hint_y=None, height=dp(38), spacing=dp(8))
        fila_requerido.add_widget(Label(text="Dato obligatorio"))
        requerido = Spinner(
            text="Sí" if campo.required else "No",
            values=("Sí", "No"),
            size_hint_x=None,
            width=dp(100),
        )
        fila_requerido.add_widget(requerido)
        form.add_widget(fila_requerido)

        scroll.add_widget(form)
        contenido.add_widget(scroll)

        def entero(entrada, actual):
            try:
                return int(float(entrada.text))
            except Exception:
                return actual

        propiedades_aceptadas = {"valor": False}

        def aceptar(_):
            nonlocal campo
            campo_id_original = campo.field_id
            formato_anterior = copy.deepcopy(self.formato)
            longitud_undo = len(self._undo)
            try:
                nuevo_id = campo.field_id
                if any(c is not campo and c.field_id == nuevo_id for c in self.formato.fields):
                    self._aviso("El identificador del campo ya existe.")
                    return
                # La creación ya guardó el estado anterior en el historial.
                # Solo la edición de un campo existente necesita otro snapshot.
                if not es_nuevo:
                    self.push_undo()
                campo.question = pregunta.text.strip()
                campo.required = requerido.text.strip().lower() in ("sí", "si", "yes", "1", "true")
                campo.uppercase = estado_mayusculas["valor"]
                campo.position.x = min(max(0, entero(entradas_posicion["x"], campo.position.x)), max(0, self.formato.template.width - 2))
                campo.position.y = min(max(0, entero(entradas_posicion["y"], campo.position.y)), max(0, self.formato.template.height - 2))
                campo.position.width = max(2, entero(entradas_posicion["width"], campo.position.width))
                campo.position.height = max(2, entero(entradas_posicion["height"], campo.position.height))
                campo.position.width = min(campo.position.width, self.formato.template.width - campo.position.x)
                campo.position.height = min(campo.position.height, self.formato.template.height - campo.position.y)

                if campo.field_type == FIELD_TYPE_NUMBER:
                    from shared.models import Validation
                    campo.validation = Validation(numeric_only=True, alphanumeric_only=False)

                if not es_imagen:
                    seleccion_fuente = fuente_spinner.text
                    campo.text_style.font_family = fuente_por_nombre.get(seleccion_fuente, seleccion_fuente)
                    campo.text_style.font_size_px = max(1, entero(tamano, campo.text_style.font_size_px))
                    campo.text_style.color = FieldColor(
                        max(0, min(255, entero(color_r, campo.text_style.color.r))),
                        max(0, min(255, entero(color_g, campo.text_style.color.g))),
                        max(0, min(255, entero(color_b, campo.text_style.color.b))),
                    )
                    mapa_alineacion = {
                        "Izquierda": "left",
                        "Centro": "center",
                        "Derecha": "right",
                        "Justificar": "justify",
                    }
                    campo.text_style.alignment = mapa_alineacion.get(alineacion.text, "left")
                    campo.text_style.orientation = "vertical" if orientacion.text == "Vertical" else "horizontal"
                    campo.text_style.bold = estado_negrita["valor"]
                    campo.text_style.italic = estado_cursiva["valor"]

                self.formato.ordenar_campos()
                self.seleccionado = campo

                # Diagnóstico temporal: registrar el flujo real sin cambiar la posición
                # ni la distribución de los controles.
                popup.title = "DIAG: Aceptar recibido"
                self._registrar_diagnostico_popup("ACEPTAR_CALLBACK_INICIO", popup)
                # Cerrar primero el panel tras aceptar los datos. La reconstrucción
                # visual de la plantilla no debe impedir que el usuario continúe.
                propiedades_aceptadas["valor"] = True
                popup.dismiss()
                self._registrar_diagnostico_popup("ACEPTAR_DESPUES_DISMISS", popup)
                Clock.schedule_once(
                    lambda _dt: self._registrar_diagnostico_popup(
                        "ACEPTAR_ESTADO_SIGUIENTE_FRAME", popup
                    ),
                    0,
                )
                self.estado.text = "Campo %d configurado." % campo.order

                def refrescar_plantilla(_dt):
                    try:
                        self.editor.cargar_plantilla(self._visual_template_path)
                    except Exception as exc:
                        self._mostrar_error_tecnico(
                            "El campo se guardó, pero no se pudo actualizar la vista", exc
                        )
                Clock.schedule_once(refrescar_plantilla, 0)

            except Exception as exc:
                self.formato = formato_anterior
                # El rollback reemplaza los objetos del modelo por copias profundas.
                # Reasociar la referencia evita que el siguiente Aceptar edite un campo
                # desconectado del formato y que Cancelar no pueda retirar el campo nuevo.
                campo = next(
                    (c for c in self.formato.fields if c.field_id == campo_id_original),
                    None,
                )
                self.seleccionado = campo
                del self._undo[longitud_undo:]
                try:
                    self.editor.cargar_plantilla(self._visual_template_path)
                except Exception:
                    pass
                self._mostrar_error_tecnico("Error al aceptar las propiedades del campo", exc)

        def cancelar_propiedades(_boton):
            popup.title = "DIAG: Cancelar recibido"
            self._registrar_diagnostico_popup("CANCELAR_CALLBACK_INICIO", popup)
            popup.dismiss()
            self._registrar_diagnostico_popup("CANCELAR_DESPUES_DISMISS", popup)
            Clock.schedule_once(
                lambda _dt: self._registrar_diagnostico_popup(
                    "CANCELAR_ESTADO_SIGUIENTE_FRAME", popup
                ),
                0,
            )

        boton_cancelar = Button(text="Cancelar", on_release=cancelar_propiedades)
        boton_cancelar.bind(
            on_press=lambda *_: self._registrar_diagnostico_popup(
                "CANCELAR_ON_PRESS", popup
            )
        )
        boton_aceptar = Button(text="Aceptar", on_release=aceptar)
        boton_aceptar.bind(
            on_press=lambda *_: self._registrar_diagnostico_popup(
                "ACEPTAR_ON_PRESS", popup
            )
        )
        botones.add_widget(boton_cancelar)
        botones.add_widget(boton_aceptar)

        class PopupPropiedadesDiagnostico(Popup):
            def on_touch_down(popup_self, touch):
                if popup_self.collide_point(*touch.pos):
                    hits = []
                    for nombre, boton in (
                        ("Cancelar", boton_cancelar),
                        ("Aceptar", boton_aceptar),
                    ):
                        if boton.collide_point(*touch.pos):
                            hits.append(nombre)
                    self._registrar_diagnostico_popup(
                        "TOQUE_POPUP_DOWN",
                        popup_self,
                        "pos=(%.1f,%.1f) botones=%s" % (
                            touch.x, touch.y, ",".join(hits) if hits else "ninguno"
                        ),
                    )
                    if hits:
                        popup_self.title = "DIAG: toque en " + " y ".join(hits)
                return super(PopupPropiedadesDiagnostico, popup_self).on_touch_down(touch)

            def on_touch_up(popup_self, touch):
                if popup_self.collide_point(*touch.pos):
                    self._registrar_diagnostico_popup(
                        "TOQUE_POPUP_UP",
                        popup_self,
                        "pos=(%.1f,%.1f)" % (touch.x, touch.y),
                    )
                return super(PopupPropiedadesDiagnostico, popup_self).on_touch_up(touch)

        popup = PopupPropiedadesDiagnostico(
            title="Propiedades del campo",
            content=contenido,
            size_hint=(0.97, 0.96),
        )

        def restaurar_posicion_plantilla(_dt):
            if (
                posicion_plantilla_inicial is not None
                and self.editor is not None
                and self.editor.template_widget is not None
            ):
                self.editor.template_widget.pos = posicion_plantilla_inicial
                self.editor.constrain_template_position()
                self.editor.refresh_fields()

        # Registrar el evento real de cierre y mantener intacta la restauración visual.
        def registrar_cierre_popup(_popup, *args):
            self._propiedades_abiertas = False
            self._registrar_diagnostico_popup("EVENTO_ON_DISMISS", _popup)
            # Cualquier cierre sin Aceptar equivale a cancelar la creación.
            # Al editar un campo existente no se modifica el modelo en este punto.
            if es_nuevo and not propiedades_aceptadas["valor"]:
                try:
                    self.formato.fields = [
                        item for item in self.formato.fields if item is not campo
                    ]
                    self.formato.ordenar_campos()
                    if undo_antes is not None:
                        self._undo = list(undo_antes)
                    if redo_antes is not None:
                        self._redo = list(redo_antes)
                    self.seleccionado = (
                        seleccionado_antes
                        if any(item is seleccionado_antes for item in self.formato.fields)
                        else None
                    )
                    self.editor.cargar_plantilla(self._visual_template_path)
                    self.actualizar_lista_estado()
                    self.estado.text = "Creación de campo cancelada."
                except Exception as exc:
                    self._mostrar_error_tecnico(
                        "No se pudo cancelar la creación del campo", exc
                    )
            Clock.schedule_once(
                lambda _dt: self._registrar_diagnostico_popup(
                    "ESTADO_250MS_DESPUES_DE_CIERRE", _popup
                ),
                0.25,
            )
            Clock.schedule_once(restaurar_posicion_plantilla, 0.25)
            # Al cerrar las propiedades (Aceptar o Cancelar), dejar activa
            # la herramienta Desplazar para continuar moviéndose por la plantilla.
            Clock.schedule_once(lambda _dt: self.set_tool("hand"), 0.26)

        popup.bind(on_dismiss=registrar_cierre_popup)
        self._registrar_diagnostico_popup("ANTES_DE_ABRIR_POPUP", popup)
        self._marca_diagnostico_crash("ANTES_DE_ABRIR_POPUP_PROPIEDADES")
        self._propiedades_abiertas = True
        popup.open()
        self._marca_diagnostico_crash("DESPUES_DE_ABRIR_POPUP_PROPIEDADES")
        self._registrar_diagnostico_popup("DESPUES_DE_ABRIR_POPUP", popup)

        # El teclado virtual se abre al enfocar el campo de la pregunta.
        def enfocar_pregunta(_dt):
            self._marca_diagnostico_crash("ANTES_DE_FOCUS_PREGUNTA")
            pregunta.bind(focus=lambda _inst, valor: self._marca_diagnostico_crash(
                "PREGUNTA_FOCUS_%s" % bool(valor)
            ))
            pregunta.bind(text=lambda _inst, valor: self._marca_diagnostico_crash(
                "PREGUNTA_TEXTO_LONGITUD_%d" % len(valor or "")
            ))
            self._marca_diagnostico_crash("ASIGNANDO_FOCUS_PREGUNTA")
            pregunta.focus = True
            self._marca_diagnostico_crash("FOCUS_PREGUNTA_ASIGNADO")
            try:
                lineas = pregunta.text.split("\\n")
                pregunta.cursor = (len(lineas[-1]), len(lineas) - 1)
            except Exception:
                pass
        Clock.schedule_once(enfocar_pregunta, 0.25)

    def editar_salida(self):
        if not self.formato:
            self._aviso("Primero importe una plantilla.")
            return
        actual = self.formato.output_naming
        layout = BoxLayout(orientation="vertical", spacing=dp(7), padding=dp(10))
        nombre = TextInput(text=actual.name_text, hint_text="Texto fijo para el nombre", multiline=False, size_hint_y=None, height=dp(42))
        layout.add_widget(Label(text="Texto fijo del nombre"))
        layout.add_widget(nombre)
        campos_disponibles = list(self.formato.fields)
        opciones_campos = ["— Ninguno —"] + [
            "%02d — %s [%s]" % (
                campo.order,
                (campo.question.strip() or "(sin pregunta)"),
                campo.field_id,
            )
            for campo in campos_disponibles
        ]
        ids_por_opcion = [""] + [campo.field_id for campo in campos_disponibles]
        selectores = []
        for i in range(4):
            campo_actual = actual.field_ids[i] if i < len(actual.field_ids) else ""
            indice_actual = next(
                (j for j, field_id in enumerate(ids_por_opcion) if j > 0 and field_id == campo_actual),
                0,
            )
            layout.add_widget(Label(text="Campo %d del nombre (opcional)" % (i + 1)))
            selector = Spinner(
                text=opciones_campos[indice_actual],
                values=tuple(opciones_campos),
                size_hint_y=None,
                height=dp(42),
            )
            layout.add_widget(selector)
            selectores.append(selector)
        def aceptar(_):
            self.push_undo()
            actual.name_text = nombre.text.strip()
            actual.field_ids = [
                ids_por_opcion[opciones_campos.index(selector.text)]
                if selector.text in opciones_campos else ""
                for selector in selectores
            ]
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

        # Coordenadas relativas directas al CanvasEditor (StencilView)
        x = tw.x + left * self.scale
        y = tw.y + tw.height - bottom * self.scale
        w = max(1, (right - left) * self.scale)
        h = max(1, (bottom - top) * self.scale)

        # Dibujar directamente en canvas.after del editor evita el sistema de
        # coordenadas ambiguo de un widget auxiliar: x/y ya son coordenadas
        # del lienzo y no deben trasladarse ni compensarse por otra posición.
        instrucciones = InstructionGroup()
        instrucciones.add(Color(0, 0, 0, 1))
        instrucciones.add(Line(rectangle=(x, y, w, h), width=3))
        self.editor.canvas.after.add(instrucciones)
        self._drawing_widget = instrucciones

    def clear_drawing_preview(self):
        if self._drawing_widget is not None and self.editor is not None:
            try:
                self.editor.canvas.after.remove(self._drawing_widget)
            except Exception:
                pass
        self._drawing_widget = None

    def set_zoom(self, value, anchor=None):
        if not self.formato:
            return

        nuevo_scale = max(0.05, min(5.0, value))
        if self.editor is None or self.editor.template_widget is None:
            self.scale = nuevo_scale
            if self.editor:
                self.editor.scale = self.scale
            self.actualizar_zoom()
            return

        tw = self.editor.template_widget
        viejo_scale = self.scale

        if anchor is None:
            # El centro y el ancla están en coordenadas de ventana,
            # igual que la posición de la plantilla.
            anchor_local = self.editor.center
        else:
            anchor_local = anchor

        doc_x = (anchor_local[0] - tw.x) / viejo_scale
        doc_y_bottom = (anchor_local[1] - tw.y) / viejo_scale

        self.scale = nuevo_scale
        self.editor.scale = self.scale

        tw.size = (
            self.formato.template.width * self.scale,
            self.formato.template.height * self.scale,
        )
        tw.pos = (
            anchor_local[0] - doc_x * self.scale,
            anchor_local[1] - doc_y_bottom * self.scale,
        )
        self.editor.constrain_template_position()

        self.editor.refresh_fields()
        self.actualizar_zoom()

    def actualizar_zoom(self):
        if self.zoom_label:
            self.zoom_label.text = "%d%%" % int(round(self.scale * 100))

    def actualizar_lista_estado(self):
        if self.formato:
            self.estado.text = "%d campo(s)." % len(self.formato.fields)
        else:
            self.estado.text = "Listo."

    def _mostrar_error_tecnico(self, titulo, exc):
        """Programa el diagnóstico en el hilo de Kivy para que Android sí lo dibuje."""
        detalle = traceback.format_exc()
        if not detalle or detalle.strip() == "NoneType: None":
            detalle = str(exc)
        texto = "ETAPA: " + titulo + "\n\nERROR: " + str(exc) + "\n\nDETALLE TÉCNICO:\n" + detalle
        # El resultado del selector Android puede llegar desde un callback Java.
        # Los widgets Kivy deben crearse/abrirse en el hilo principal.
        Clock.schedule_once(lambda _dt: self._abrir_popup_error_tecnico(titulo, texto), 0)

    def _abrir_popup_error_tecnico(self, titulo, texto):
        contenido = ScrollView(do_scroll_x=False, do_scroll_y=True)
        etiqueta = Label(
            text=texto,
            halign="left",
            valign="top",
            size_hint_y=None,
            font_size="13sp",
            text_size=(dp(320), None),
        )
        etiqueta.bind(width=lambda inst, value: setattr(inst, "text_size", (max(dp(260), value), None)))
        etiqueta.bind(texture_size=lambda inst, value: setattr(inst, "height", value[1] + dp(20)))
        contenido.add_widget(etiqueta)
        Popup(
            title="DIAGNÓSTICO DE ERROR",
            content=contenido,
            size_hint=(0.96, 0.86),
            auto_dismiss=True,
        ).open()

    def _aviso(self, mensaje):
        Popup(title="Formatos Traducidos", content=Label(text=mensaje), size_hint=(0.8, 0.3)).open()


if __name__ == "__main__":
    ConfiguradorApp().run()