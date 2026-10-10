# -*- coding: utf-8 -*-
import os
import copy
import traceback
from math import hypot

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.textinput import TextInput
from kivy.uix.scrollview import ScrollView
from kivy.uix.gridlayout import GridLayout
from kivy.uix.popup import Popup
from kivy.uix.modalview import ModalView
from kivy.uix.stencilview import StencilView
from kivy.uix.widget import Widget
from kivy.core.image import Image as CoreImage
from kivy.uix.image import Image as KivyImage
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.graphics.transformation import Matrix

from shared.models import (
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
    Field,
    Formato,
    Position,
    TemplateInfo,
    TextStyle,
    OutputNaming,
    Validation,
)

# Colores y modelos específicos para Kivy
class FieldColor:
    def __init__(self, r, g, b):
        self.r = r
        self.g = g
        self.b = b

TOOLS = [
    ("👆", "select"),
    ("✋", "hand"),
    ("🔍", "zoom"),
    ("A", FIELD_TYPE_TEXT),
    ("1", FIELD_TYPE_NUMBER),
    ("A1", FIELD_TYPE_ALPHANUMERIC),
    ("🖼️", FIELD_TYPE_IMAGE),
]

class CampoWidget(Widget):
    def __init__(self, campo, canvas_editor, **kwargs):
        super().__init__(**kwargs)
        self.campo = campo
        self.canvas_editor = canvas_editor
        self.size_hint = (None, None)
        self.bind(pos=self.actualizar, size=self.actualizar)
        self.actualizar()

    def actualizar(self, *args):
        tw = self.canvas_editor.template_widget
        if tw is None or not self.canvas_editor.app.formato:
            return
        
        p = self.campo.position
        scale = self.canvas_editor.app.scale
        
        self.size = (p.width * scale, p.height * scale)
        # Posición relativa a la plantilla
        self.pos = (
            tw.x + p.x * scale,
            tw.y + tw.height - (p.y + p.height) * scale
        )
        
        self.canvas.clear()
        with self.canvas:
            from kivy.graphics import Color, Line, Rectangle
            is_selected = (self.canvas_editor.seleccionado == self.campo)
            color = (0, 0.84, 1, 1) if is_selected else (1, 0.8, 0, 1)
            Color(*color)
            Line(rectangle=(0, 0, self.width, self.height), width=3 if is_selected else 2)
            
            if is_selected:
                Color(1, 1, 1, 1)
                size = 8
                handles = [
                    (0, 0), (self.width/2, 0), (self.width, 0),
                    (self.width, self.height/2), (self.width, self.height),
                    (self.width/2, self.height), (0, self.height), (0, self.height/2)
                ]
                for hx, hy in handles:
                    Rectangle(pos=(hx - size/2, hy - size/2), size=(size, size))

    def on_touch_down(self, touch):
        if not self.collide_point(touch.x - self.x, touch.y - self.y):
            return False
        
        if self.canvas_editor.app.tool == "select":
            handle = self._hit_handle(touch)
            self.canvas_editor.begin_field_interaction(self.campo, touch, handle)
            return True
        return super().on_touch_down(touch)

    def _hit_handle(self, touch):
        if self.canvas_editor.seleccionado != self.campo:
            return None
        local_x = touch.x - self.x
        local_y = touch.y - self.y
        tol = 15
        w, h = self.width, self.height
        
        if abs(local_x) <= tol and abs(local_y) <= tol: return "nw"
        if abs(local_x - w/2) <= tol and abs(local_y) <= tol: return "n"
        if abs(local_x - w) <= tol and abs(local_y) <= tol: return "ne"
        if abs(local_x - w) <= tol and abs(local_y - h/2) <= tol: return "e"
        if abs(local_x - w) <= tol and abs(local_y - h) <= tol: return "se"
        if abs(local_x - w/2) <= tol and abs(local_y - h) <= tol: return "s"
        if abs(local_x) <= tol and abs(local_y - h) <= tol: return "sw"
        if abs(local_x) <= tol and abs(local_y - h/2) <= tol: return "w"
        return None

class CanvasEditor(StencilView):
    def __init__(self, app, **kwargs):
        super().__init__(**kwargs)
        self.app = app
        self.template_widget = None
        self._template_core_image = None
        self.start_touch = None
        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self.pan_start = None
        self.pan_template_pos = None
        self._touches = {}
        self._pinch_active = False
        self._pinch_start_distance = 0.0
        self._pinch_start_scale = 1.0
        self._pinch_anchor = None
        self._pinch_start_template_pos = None
        self._pinch_last_midpoint = None
        self._drawing_widget = None
        self.bind(pos=self._viewport_changed, size=self._viewport_changed)

    @property
    def seleccionado(self):
        return getattr(self.app, "seleccionado", None)

    @seleccionado.setter
    def seleccionado(self, campo):
        self.app.seleccionado = campo

    def _viewport_changed(self, *_args):
        if self.template_widget is not None:
            self.constrain_template_position()
            self.refresh_fields()

    def constrain_template_position(self, pos=None):
        tw = self.template_widget
        if tw is None:
            return
        x, y = tw.pos if pos is None else pos
        if tw.width <= self.width:
            x = (self.width - tw.width) / 2.0
        else:
            x = min(0, max(self.width - tw.width, x))
        if tw.height <= self.height:
            y = (self.height - tw.height) / 2.0
        else:
            y = min(0, max(self.height - tw.height, y))
        tw.pos = (x, y)

    def _touch_inside_template(self, touch):
        if self.template_widget is None:
            return False
        # Convertir toque de ventana a local del editor
        lx, ly = self.to_local(touch.x, touch.y)
        return self.template_widget.collide_point(lx, ly)

    def _start_pinch(self):
        if len(self._touches) < 2 or not self.template_widget:
            return False
        a, b = list(self._touches.values())[:2]
        self._pinch_start_distance = max(1.0, hypot(b.x - a.x, b.y - a.y))
        self._pinch_start_scale = self.app.scale
        self._pinch_anchor = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)
        self._pinch_start_template_pos = self.template_widget.pos
        self._pinch_last_midpoint = self._pinch_anchor
        self._pinch_active = True

        self.active_field_touch = None
        self.active_field = None
        self.active_handle = None
        self.initial_position = None
        self.app._interaction_changed = False

        self.pan_start = None
        self.pan_template_pos = None
        self.start_touch = None
        self.app.clear_drawing_preview()
        self.app.estado.text = "Zoom táctil"
        return True

    def _update_pinch(self):
        if not self._pinch_active or len(self._touches) < 2:
            return False
        a, b = list(self._touches.values())[:2]
        distancia = max(1.0, hypot(b.x - a.x, b.y - a.y))
        factor = distancia / self._pinch_start_distance
        midpoint = ((a.x + b.x) / 2.0, (a.y + b.y) / 2.0)

        self.app.set_zoom(self._pinch_start_scale * factor, anchor=self._pinch_anchor)

        if self.template_widget is not None:
            dx = midpoint[0] - self._pinch_anchor[0]
            dy = midpoint[1] - self._pinch_anchor[1]
            self.template_widget.pos = (
                self.template_widget.x + dx,
                self.template_widget.y + dy,
            )
            self.constrain_template_position()
            self.refresh_fields()

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
            raise IOError("Kivy NO pudo crear la textura de la imagen.")

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

    def _document_point(self, touch):
        """
        CORRECCIÓN DEFINITIVA: Convierte un toque de ventana a píxeles del documento.
        Usa to_local para obtener coordenadas relativas al Editor, luego ajusta
        respecto a la plantilla y su escala/inversión Y.
        """
        tw = self.template_widget
        if tw is None or not self.app.formato:
            return 0, 0

        # 1. Convertir coordenadas de ventana (touch.x,y) a coordenadas locales del CanvasEditor
        # to_local maneja automáticamente la posición del widget en la jerarquía
        local_x, local_y = self.to_local(touch.x, touch.y)

        # 2. Calcular posición relativa a la esquina SUPERIOR IZQUIERDA de la plantilla
        # En Kivy, Y crece hacia arriba. La plantilla tiene su origen (0,0) en ABajo-Izquierda.
        # Queremos coordenadas de documento donde (0,0) es ARRIBA-Izquierda.
        
        # X relativo al borde izquierdo de la plantilla
        rel_x = local_x - tw.x
        
        # Y relativo al borde SUPERIOR de la plantilla
        # Altura total de la plantilla visualizada = tw.height
        # Distancia desde abajo = local_y - tw.y
        # Distancia desde arriba = tw.height - (local_y - tw.y) => tw.y + tw.height - local_y
        rel_y_from_top = (tw.y + tw.height) - local_y

        # 3. Escalar de vuelta a píxeles reales del documento original
        doc_x = rel_x / self.app.scale
        doc_y = rel_y_from_top / self.app.scale

        # 4. Clampear límites
        doc_x = max(0, min(self.app.formato.template.width, doc_x))
        doc_y = max(0, min(self.app.formato.template.height, doc_y))

        return int(round(doc_x)), int(round(doc_y))

    def _inside_template(self, touch):
        return self._touch_inside_template(touch)

    def on_touch_down(self, touch):
        # Verificar si el toque cae dentro del área visible del editor
        if not self.collide_point(*touch.pos):
             # Usamos touch.pos porque collide_point espera coords locales del padre directo 
             # pero en StencilView a veces es mejor verificar manualmente o dejar que propague
             pass 
        
        # Para mayor seguridad en Android, verificamos contra la ventana directamente
        wx, wy = self.to_window(0, 0)
        lx = touch.x - wx
        ly = touch.y - wy
        if not (0 <= lx <= self.width and 0 <= ly <= self.height):
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

        if tool in (FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_ALPHANUMERIC, FIELD_TYPE_IMAGE):
            if self._inside_template(touch):
                self.start_touch = self._document_point(touch)
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
            return self._update_pinch()

        if self.pan_start and self.app.tool == "hand" and self.template_widget:
            point = touch.pos
            dx = point[0] - self.pan_start[0]
            dy = point[1] - self.pan_start[1]
            self.template_widget.pos = (
                self.template_widget.x + dx,
                self.template_widget.y + dy,
            )
            self.constrain_template_position()
            self.pan_start = point
            self.refresh_fields()
            return True

        if self.start_touch and self.app.tool in (
            FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER, FIELD_TYPE_ALPHANUMERIC, FIELD_TYPE_IMAGE
        ):
            self.app.redraw_drawing_preview(self.start_touch, self._document_point(touch))
            return True

        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        self._touches.pop(touch.uid, None)

        if self._pinch_active:
            if len(self._touches) < 2:
                self._pinch_active = False
                self._pinch_anchor = None
                self._pinch_start_distance = 0.0
                self._pinch_start_template_pos = None
                self._pinch_last_midpoint = None
                self.app.estado.text = "Zoom finalizado."
            return True

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


class HamburgerButton(Button):
    def __init__(self, **kwargs):
        super().__init__(text="☰", size_hint_x=None, width=dp(48), **kwargs)


class ConfiguradorApp(App):
    title = "Configurador de Formatos Traducidos"

    def build(self):
        self.formato = None
        self.seleccionado = None
        self.tool = "select"
        self.scale = 1.0
        self._visual_template_path = None
        self._undo = []
        self._redo = []
        self._interaction_changed = False
        self._drawing_widget = None

        root = BoxLayout(orientation="vertical")
        barra = BoxLayout(size_hint_y=None, height=dp(54), spacing=dp(6), padding=(dp(6), dp(5)))
        barra.add_widget(HamburgerButton(on_release=lambda _: self.abrir_menu()))
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

    def template_position(self):
        if not self.formato:
            return (0, 0)
        return (0, 0)

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

    def nuevo_id(self):
        if not self.formato:
            return "campo1"
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
            negrita = campo_texto("Negrita (si/no)", "si" if getattr(campo.text_style, 'bold', False) else "no")
            cursiva = campo_texto("Cursiva (si/no)", "si" if getattr(campo.text_style, 'italic', False) else "no")

        scroll.add_widget(form)
        contenido.add_widget(scroll)
        botones = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(5))

        def entero(entrada, actual):
            try:
                return int(float(entrada.text))
            except Exception:
                return actual

        def aceptar(_):
            campo_id_original = campo.field_id
            formato_anterior = copy.deepcopy(self.formato)
            longitud_undo = len(self._undo)
            try:
                nuevo_id = id_input.text.strip() or campo.field_id
                if any(c is not campo and c.field_id == nuevo_id for c in self.formato.fields):
                    self._aviso("El ID ya existe.")
                    return
                self.push_undo()
                campo.field_id = nuevo_id
                campo.question = pregunta.text.strip()
                campo.required = requerido.text.strip().lower() in ("si", "sí", "yes", "1", "true")
                campo.position.x = min(max(0, entero(x_in, campo.position.x)), max(0, self.formato.template.width - 2))
                campo.position.y = min(max(0, entero(y_in, campo.position.y)), max(0, self.formato.template.height - 2))
                campo.position.width = max(2, entero(w_in, campo.position.width))
                campo.position.height = max(2, entero(h_in, campo.position.height))
                campo.position.width = min(campo.position.width, self.formato.template.width - campo.position.x)
                campo.position.height = min(campo.position.height, self.formato.template.height - campo.position.y)
    
                if campo.field_type == FIELD_TYPE_NUMBER:
                    if not hasattr(campo, 'validation'):
                        campo.validation = Validation()
                    campo.validation.numeric_only = True
                    campo.validation.alphanumeric_only = False
                elif campo.field_type == FIELD_TYPE_ALPHANUMERIC:
                    if not hasattr(campo, 'validation'):
                        campo.validation = Validation()
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
    
            except Exception as exc:
                self.formato = formato_anterior
                self.seleccionado = next(
                    (c for c in self.formato.fields if c.field_id == campo_id_original),
                    None,
                )
                del self._undo[longitud_undo:]
                try:
                    self.editor.cargar_plantilla(self._visual_template_path)
                except Exception:
                    pass
                self._mostrar_error_tecnico("Error al aceptar las propiedades del campo", exc)

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

        widget = Widget(size_hint=(None, None), size=(w, h), pos=(x, y))
        with widget.canvas:
            from kivy.graphics import Color, Line
            Color(0, 0, 0, 1)
            Line(rectangle=(0, 0, w, h), width=3)

        self._drawing_widget = widget
        self.editor.add_widget(widget)

    def clear_drawing_preview(self):
        if self._drawing_widget and self._drawing_widget.parent:
            self._drawing_widget.parent.remove_widget(self._drawing_widget)
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
            # Centro del viewport
            anchor_local = (self.editor.width / 2.0, self.editor.height / 2.0)
        else:
            # CORRECCIÓN CRÍTICA PARA ANDROID:
            # Convertir coordenadas de ventana del ancla a locales del editor
            anchor_local = self.editor.to_local(*anchor)

        # Punto en el documento (coordenadas originales de la plantilla) que está bajo el ancla
        # Esto asegura que ese punto específico permanezca bajo el dedo al hacer zoom
        doc_x = (anchor_local[0] - tw.x) / viejo_scale
        doc_y_bottom = (anchor_local[1] - tw.y) / viejo_scale

        self.scale = nuevo_scale
        self.editor.scale = self.scale

        # Recalcular tamaño de la plantilla
        new_w = self.formato.template.width * self.scale
        new_h = self.formato.template.height * self.scale
        tw.size = (new_w, new_h)

        # Recalcular posición para mantener el ancla fija
        # Nuevas coordenadas locales del punto doc_x/doc_y_bottom deben ser anchor_local
        # anchor_local[0] = new_tw.x + doc_x * new_scale  => new_tw.x = anchor_local[0] - doc_x * new_scale
        # anchor_local[1] = new_tw.y + doc_y_bottom * new_scale => new_tw.y = anchor_local[1] - doc_y_bottom * new_scale
        
        tw.pos = (
            anchor_local[0] - doc_x * self.scale,
            anchor_local[1] - doc_y_bottom * self.scale,
        )
        
        self.editor.constrain_template_position()
        self.editor.refresh_fields()
        self.actualizar_zoom()

    def actualizar_zoom(self):
        if self.zoom_label:
            self.zoom_label.text = "%d %%" % int(round(self.scale * 100))

    def actualizar_lista_estado(self):
        if self.formato:
            self.estado.text = "%d campo(s)." % len(self.formato.fields)
        else:
            self.estado.text = "Listo."

    def _mostrar_error_tecnico(self, titulo, exc):
        detalle = traceback.format_exc()
        if not detalle or detalle.strip() == "NoneType: None":
            detalle = str(exc)
        texto = "ETAPA: " + titulo + "\n\nERROR: " + str(exc) + "\n\nDETALLE TÉCNICO:\n" + detalle
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

    def abrir_menu(self):
        panel = ModalView(size_hint=(0.8, 0.7), background_color=(0.05, 0.05, 0.05, 0.98), background="")
        root = BoxLayout(orientation="vertical", spacing=dp(6), padding=dp(8))
        encabezado = BoxLayout(size_hint_y=None, height=dp(50))
        encabezado.add_widget(Label(text="MENÚ", font_size="19sp"))
        encabezado.add_widget(Button(text="X", size_hint_x=None, width=dp(48), on_release=lambda _: panel.dismiss()))
        root.add_widget(encabezado)
        
        def accion(ruta):
            panel.dismiss()
            self._visual_template_path = ruta
            # Cargar imagen primero para obtener dimensiones correctas
            img = CoreImage(ruta)
            self.formato = Formato(
                name=os.path.splitext(os.path.basename(ruta))[0],
                template=TemplateInfo(
                    path=ruta,
                    width=img.width,
                    height=img.height,
                    dpi=300,
                    mode="RGB",
                ),
            )
            self.editor.cargar_plantilla(ruta)
            self.estado.text = "Plantilla cargada."

        from kivy.uix.filechooser import FileChooserListView
        fc = FileChooserListView(path=os.path.expanduser("~"))
        fc.bind(on_submit=lambda x, y: accion(y[0]) if y else None)
        root.add_widget(fc)
        panel.add_widget(root)
        panel.open()

if __name__ == "__main__":
    ConfiguradorApp().run()