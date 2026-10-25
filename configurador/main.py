# -*- coding: utf-8 -*-
import io
import os
import re
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from shared.fdt import guardar_fdt, validar_fdt
from shared.renderer import _cargar_fuente
from shared.models import (
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
    Color,
    Field,
    Formato,
    Position,
    TemplateInfo,
    TextStyle,
    OutputNaming,
)


TOOL_SELECT = "select"
TOOL_TEXT = FIELD_TYPE_TEXT
TOOL_NUMBER = FIELD_TYPE_NUMBER
TOOL_IMAGE = FIELD_TYPE_IMAGE
TOOL_ZOOM = "zoom"
TOOL_HAND = "hand"


class ToolTip:
    def __init__(self, widget, text, delay=500):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.tipwindow = None
        self.after_id = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self.after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self.after_id is not None:
            try:
                self.widget.after_cancel(self.after_id)
            except Exception:
                pass
            self.after_id = None

    def _show(self):
        self.after_id = None
        if self.tipwindow is not None:
            return
        try:
            x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
            self.tipwindow = tk.Toplevel(self.widget)
            self.tipwindow.wm_overrideredirect(True)
            self.tipwindow.wm_geometry("+%d+%d" % (x, y))
            label = tk.Label(
                self.tipwindow,
                text=self.text,
                bg="#303030",
                fg="white",
                relief="solid",
                borderwidth=1,
                padx=8,
                pady=5,
                font=("Arial", 9),
            )
            label.pack()
        except tk.TclError:
            self.tipwindow = None

    def _hide(self, event=None):
        self._cancel()
        if self.tipwindow is not None:
            try:
                self.tipwindow.destroy()
            except tk.TclError:
                pass
            self.tipwindow = None


class Configurador:
    def __init__(self, root):
        self.root = root
        self.root.title("Formatos Traducidos - Configurador")
        self.root.configure(bg="black")
        self.root.geometry("1280x800")
        self.root.minsize(900, 600)

        self.formato = None
        self.template_image = None
        self.template_tk = None
        self.canvas_image_id = None
        self.zoom = 1.0
        self.tool = TOOL_SELECT
        self.selected_field = None
        self.field_items = {}
        self.drag_start = None
        self._draw_start_canvas = None
        self.drawing_rect = None
        self.current_fdt_path = None
        self.unsaved = False
        self._undo_stack = []
        self._redo_stack = []
        self._pan_last = None
        self._move_start = None
        self._move_origin = None
        self._move_changed = False
        self._font_inventory = self._obtener_fuentes_instaladas()
        self._magnifier_label = None
        self._icon_images = {}
        self._field_preview_images = {}
        # Caché rasterizada de baja resolución para las muestras de campos.
        # Se mantiene solo en memoria y no forma parte del FDT.
        self._field_preview_cache = {}
        self._template_tile_images = {}
        self._field_drag_index = None
        self._field_drop_index = None
        self._field_drop_indicator = None
        self._field_resize_start = None
        self.field_panel_visible = False
        self.toolbar_dock_side = "top"
        self.field_dock_side = "right"
        self.field_dock_min_width = 190
        self.field_dock_max_width = 700

        self._build_ui()
        self._set_status("Listo. Importe una plantilla para comenzar.")

    def _build_ui(self):
        menubar = tk.Menu(self.root)
        archivo = tk.Menu(menubar, tearoff=0)
        archivo.add_command(label="Nuevo", command=self.nuevo, accelerator="Ctrl+N")
        archivo.add_command(label="Abrir...", command=self.abrir, accelerator="Ctrl+O")
        archivo.add_command(label="Guardar", command=self.guardar, accelerator="Ctrl+S")
        archivo.add_command(label="Guardar como FDT...", command=self.guardar_como_fdt, accelerator="Ctrl+Shift+S")
        archivo.add_separator()
        archivo.add_command(label="Importar plantilla...", command=self.importar_plantilla, accelerator="I")
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.salir)
        menubar.add_cascade(label="Archivo", menu=archivo)

        editar = tk.Menu(menubar, tearoff=0)
        editar.add_command(label="Deshacer", command=self.deshacer, accelerator="Ctrl+Z")
        editar.add_command(label="Rehacer", command=self.rehacer, accelerator="Ctrl+Y")
        editar.add_separator()
        editar.add_command(label="Eliminar campo", command=self.eliminar_seleccionado, accelerator="Delete")
        editar.add_command(label="Propiedades del campo", command=self.editar_seleccionado)
        menubar.add_cascade(label="Editar", menu=editar)

        ver = tk.Menu(menubar, tearoff=0)
        ver.add_command(label="Acercar", command=lambda: self.cambiar_zoom(1.25), accelerator="+")
        ver.add_command(label="Alejar", command=lambda: self.cambiar_zoom(0.8), accelerator="-")
        ver.add_command(label="100 %", command=lambda: self.set_zoom(1.0), accelerator="*")
        menubar.add_cascade(label="Ver", menu=ver)

        herramientas = tk.Menu(menubar, tearoff=0)
        herramientas.add_command(label="Selección", command=lambda: self.set_tool(TOOL_SELECT), accelerator="S")
        herramientas.add_command(label="Desplazar", command=lambda: self.set_tool(TOOL_HAND), accelerator="D")
        herramientas.add_command(label="Texto", command=lambda: self.set_tool(TOOL_TEXT), accelerator="A")
        herramientas.add_command(label="Número", command=lambda: self.set_tool(TOOL_NUMBER), accelerator="Q")
        herramientas.add_command(label="Imagen", command=lambda: self.set_tool(TOOL_IMAGE), accelerator="W")
        herramientas.add_command(label="Lupa", command=lambda: self.set_tool(TOOL_ZOOM), accelerator="Z")
        herramientas.add_separator()
        herramientas.add_command(label="Lista de campos", command=self.toggle_field_panel, accelerator="L")
        herramientas.add_command(label="Archivo terminado", command=self.configurar_archivo_terminado, accelerator="T")
        menubar.add_cascade(label="Herramientas", menu=herramientas)

        ayuda = tk.Menu(menubar, tearoff=0)
        ayuda.add_command(label="Mapa de atajos", command=self.mostrar_mapa_atajos)
        guia = tk.Menu(ayuda, tearoff=0)
        guia.add_command(label="Selección (S)", command=lambda: self.mostrar_ayuda_herramienta(TOOL_SELECT))
        guia.add_command(label="Desplazar (D)", command=lambda: self.mostrar_ayuda_herramienta(TOOL_HAND))
        guia.add_command(label="Texto (A)", command=lambda: self.mostrar_ayuda_herramienta(TOOL_TEXT))
        guia.add_command(label="Número (Q)", command=lambda: self.mostrar_ayuda_herramienta(TOOL_NUMBER))
        guia.add_command(label="Imagen (W)", command=lambda: self.mostrar_ayuda_herramienta(TOOL_IMAGE))
        guia.add_command(label="Lupa (Z)", command=lambda: self.mostrar_ayuda_herramienta(TOOL_ZOOM))
        guia.add_separator()
        guia.add_command(label="Lista de campos (L)", command=lambda: self.mostrar_ayuda_herramienta("field_list"))
        guia.add_command(label="Archivo terminado (T)", command=lambda: self.mostrar_ayuda_herramienta("output_naming"))
        ayuda.add_cascade(label="Guía de herramientas", menu=guia)
        ayuda.add_command(label="Acerca de", command=lambda: messagebox.showinfo(
            "Acerca de", "Formatos Traducidos - Configurador"
        ))
        menubar.add_cascade(label="Ayuda", menu=ayuda)
        self.root.config(menu=menubar)

        self.toolbar_host = tk.Frame(self.root, bg="#000000", height=42)
        self.toolbar_host.pack(side="top", fill="x")
        self._toolbar_gradient_image = None
        self._toolbar_gradient_label = tk.Label(self.toolbar_host, bd=0, highlightthickness=0)
        self._toolbar_gradient_label.place(x=0, y=0, relwidth=1, relheight=1)
        self._toolbar_gradient_label.lower()
        self.toolbar_host.bind("<Configure>", self._actualizar_gradiente_barra, add="+")

        self._tool_buttons = []
        tools = [
            ("seleccionar.png", "Selección", TOOL_SELECT),
            ("desplazar.png", "Desplazar", TOOL_HAND),
            ("campo_texto.png", "Texto", TOOL_TEXT),
            ("campo_numerico.png", "Número", TOOL_NUMBER),
            ("campo_imagen.png", "Imagen", TOOL_IMAGE),
            ("zoom_mas.png", "Lupa", TOOL_ZOOM),
        ]
        for icon, label, tool in tools:
            button = tk.Button(
                self.toolbar_host,
                image=self._toolbar_png_image(icon, 24),
                command=lambda t=tool: self.set_tool(t),
                bg="#262626", fg="white",
                activebackground="#444444", activeforeground="white",
                relief="flat", width=20, height=20, padx=4, pady=4, bd=0,
            )
            button._icon_ref = self._icon_images.get(("png", icon, 24))
            button.pack(side="left", padx=2, pady=5)
            self._tool_buttons.append(button)
            shortcut = {
                TOOL_SELECT: "S", TOOL_HAND: "D", TOOL_TEXT: "A",
                TOOL_NUMBER: "Q", TOOL_IMAGE: "W", TOOL_ZOOM: "Z",
            }.get(tool)
            descripcion = {
                TOOL_SELECT: "Seleccionar, mover y cambiar el tamaño de campos",
                TOOL_HAND: "Desplazar la vista de la plantilla",
                TOOL_TEXT: "Crear campos de texto",
                TOOL_NUMBER: "Crear campos numéricos",
                TOOL_IMAGE: "Crear campos para insertar imágenes",
                TOOL_ZOOM: "Ampliar la vista haciendo clic en la plantilla",
            }.get(tool, label)
            ToolTip(button, "{} ({})".format(descripcion, shortcut))
            button.bind("<Enter>", lambda e, l=label: self._set_status(l))
            button.bind("<Leave>", lambda e: self._set_status(
                "Herramienta: " + {
                    TOOL_SELECT: "Selección", TOOL_HAND: "Desplazar",
                    TOOL_TEXT: "Texto", TOOL_NUMBER: "Número",
                    TOOL_IMAGE: "Imagen",
                    TOOL_ZOOM: "Lupa",
                }.get(self.tool, self.tool)
            ))

        zoom_frame = tk.Frame(self.toolbar_host, bg="#000000")
        zoom_frame.pack(side="right", padx=6)
        for icon, command in (
            ("minus", lambda: self.cambiar_zoom(0.8)),
        ):
            b = tk.Button(zoom_frame, image=self._icon_image(icon, 14), command=command,
                          bg="#262626", fg="white", relief="flat", bd=0,
                          width=16, height=16, padx=4, pady=4)
            b._icon_ref = self._icon_images.get((icon, 14))
            b.pack(side="left", padx=2, pady=4)
            ToolTip(b, "Alejar (-)" if icon == "minus" else "Acercar (+)")
        self.zoom_label = tk.Label(zoom_frame, text="100 %", bg="#000000", fg="white", width=6)
        ToolTip(self.zoom_label, "Nivel de zoom actual (usa * para restablecer al 100 %)")
        self.zoom_label.pack(side="left", padx=2)
        b = tk.Button(zoom_frame, text="+", command=lambda: self.cambiar_zoom(1.25),
                      bg="#262626", fg="white", relief="flat", bd=0,
                      width=2, padx=4, pady=4)
        b.pack(side="left", padx=2, pady=4)
        ToolTip(b, "Acercar (+)")

        body = tk.Frame(self.root, bg="black")
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            body, bg="black", highlightthickness=0,
            scrollregion=(0, 0, 0, 0)
        )
        self._workspace_gradient_image = None
        self._workspace_gradient_item = self.canvas.create_image(0, 0, anchor="nw", tags=("workspace_gradient",))

        self.field_dock = tk.Frame(body, bg="#181818", width=270)
        self.field_dock.grid(row=0, column=2, sticky="nsew", padx=(2, 0))
        self.field_dock.grid_propagate(False)

        field_header = tk.Frame(self.field_dock, bg="#242424", height=34)
        field_header.pack(fill="x")
        tk.Label(field_header, text="Campos", bg="#242424", fg="white",
                 font=("Arial", 10, "bold")).pack(side="left", padx=8, pady=7)
        close_btn = tk.Button(field_header, image=self._icon_image("times", 88),
                              command=self.toggle_field_panel, bg="#242424",
                              activebackground="#444444", relief="flat", bd=0)
        close_btn._icon_ref = self._icon_images.get(("times", 88))
        close_btn.pack(side="right", padx=5)
        ToolTip(close_btn, "Cerrar lista de campos")
        field_header.bind("<ButtonPress-1>", self._field_dock_start)
        field_header.bind("<B1-Motion>", self._field_dock_motion)
        field_header.bind("<ButtonRelease-1>", self._field_dock_release)

        self.field_list = tk.Listbox(
            self.field_dock, bg="#101010", fg="#eeeeee",
            selectbackground="#005f73", selectforeground="white",
            activestyle="none", borderwidth=0, highlightthickness=0,
            font=("Arial", 10)
        )
        self.field_list.pack(fill="both", expand=True, padx=4, pady=4)
        self.field_list.bind("<Double-Button-1>", self._field_list_double_click)
        self.field_list.bind("<ButtonPress-1>", self._field_list_press)
        self.field_list.bind("<B1-Motion>", self._field_list_motion)
        self.field_list.bind("<ButtonRelease-1>", self._field_list_release)
        self.field_list.bind("<<ListboxSelect>>", self._field_list_select)

        self._field_drop_indicator = tk.Frame(self.field_dock, bg="white", height=3)
        self._field_drop_indicator.place_forget()
        self._field_resize_grip = tk.Frame(self.field_dock, bg="#666666", cursor="sb_h_double_arrow", width=5)
        self._field_resize_grip.bind("<ButtonPress-1>", self._field_resize_start_event)
        self._field_resize_grip.bind("<B1-Motion>", self._field_resize_motion_event)
        self._field_resize_grip.bind("<ButtonRelease-1>", self._field_resize_end_event)

        self.field_dock.grid_remove()
        self.field_panel_visible = False
        self.vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(
            yscrollcommand=self._on_canvas_yscroll,
            xscrollcommand=self._on_canvas_xscroll,
        )

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=0)
        body.rowconfigure(0, weight=1)

        self.canvas.bind("<Configure>", self._on_canvas_configure, add="+")
        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self.on_ctrl_wheel)
        self.canvas.bind("<Motion>", self.on_canvas_motion)
        self.canvas.bind("<Double-Button-1>", self.on_double_click)
        self.canvas.bind("<ButtonPress-3>", self.on_right_down)
        self.root.bind_all("<Control-z>", lambda e: self.deshacer())
        self.root.bind_all("<Control-y>", lambda e: self.rehacer())
        self.root.bind_all("<Left>", self._mover_seleccionado_tecla)
        self.root.bind_all("<Right>", self._mover_seleccionado_tecla)
        self.root.bind_all("<Up>", self._mover_seleccionado_tecla)
        self.root.bind_all("<Down>", self._mover_seleccionado_tecla)
        # Modificadores de movimiento: flechas=1 px, Ctrl=5 px y Shift=25 px.
        for tecla in ("Left", "Right", "Up", "Down"):
            self.root.bind_all(
                "<Shift-%s>" % tecla,
                lambda event: self._mover_seleccionado_tecla(event, pasos_forzados=25),
            )
            self.root.bind_all(
                "<Control-%s>" % tecla,
                lambda event: self._mover_seleccionado_tecla(event, pasos_forzados=5),
            )
        self.root.bind_all("<Delete>", self._eliminar_con_tecla)
        # Atajos de la ventana principal; se ignoran cuando un diálogo secundario tiene el foco.
        self.root.bind_all("<KeyPress>", self._manejar_atajo_teclado, add="+")

        status = tk.Frame(self.root, bg="#111111")
        status.pack(side="bottom", fill="x")
        self.status_label = tk.Label(status, text="", bg="#111111", fg="#dddddd", anchor="w")
        self.status_label.pack(fill="x", padx=8, pady=5)

    def _icon_font_path(self):
        import glob
        import sys

        candidatos = []

        # En el EXE de PyInstaller la fuente se incluye explícitamente
        # en assets/ y se extrae bajo _MEIPASS.
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidatos.append(os.path.join(meipass, "assets", "fa-solid-900.ttf"))

        # Fallback para ejecución normal desde el entorno de desarrollo.
        site_packages = os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages")
        candidatos.extend([
            os.path.join(
                site_packages,
                "fontawesome-free",
                "static",
                "fontawesome_free",
                "js-packages",
                "@fortawesome",
                "fontawesome-free",
                "webfonts",
                "fa-solid-900.ttf",
            ),
            os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "assets",
                "fa-solid-900.ttf",
            ),
        ])

        for raiz in [site_packages]:
            if os.path.isdir(raiz):
                candidatos.extend(glob.glob(
                    os.path.join(raiz, "**", "fa-solid-900.ttf"),
                    recursive=True
                ))

        vistos = set()
        for ruta in candidatos:
            ruta = os.path.normpath(ruta)
            if ruta in vistos:
                continue
            vistos.add(ruta)
            if os.path.isfile(ruta):
                return ruta

        return None

    def _toolbar_png_image(self, filename, size=24):
        """Carga los PNG locales del configurador sin conexión."""
        clave = ("png", filename, size)
        if clave in self._icon_images:
            return self._icon_images[clave]
        import sys
        candidatos = [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "iconos", "configurador", filename),
        ]
        raiz = getattr(sys, "_MEIPASS", None)
        if raiz:
            candidatos.insert(0, os.path.join(raiz, "assets", "iconos", "configurador", filename))
        for ruta in candidatos:
            if os.path.isfile(ruta):
                with Image.open(ruta) as original:
                    imagen = original.convert("RGBA")
                    imagen.thumbnail((size, size), Image.LANCZOS)
                    resultado = ImageTk.PhotoImage(imagen)
                self._icon_images[clave] = resultado
                return resultado
        raise RuntimeError("No se encontró el icono PNG local: " + filename)

    def _icon_image(self, nombre, size=15):
        clave = (nombre, size)
        if clave in self._icon_images:
            return self._icon_images[clave]
        mapa = {
            "mouse-pointer": 0xF245, "hand-paper": 0xF256, "font": 0xF031,
            "hashtag": 0xF292, "id-card": 0xF2C2, "image": 0xF03E,
            "search-plus": 0xF00E, "arrows-alt": 0xF0B2, "minus": 0xF068, "plus": 0xF067,
            "times": 0xF00D, "list": 0xF03A, "folder-open": 0xF07C,
            "save": 0xF0C7, "undo": 0xF0E2, "redo": 0xF01E,
            "file": 0xF15B,
        }
        code = mapa.get(nombre, 0xF111)
        font_path = self._icon_font_path()
        try:
            if font_path:
                font = ImageFont.truetype(font_path, size)
                box = font.getbbox(chr(code))
                w = max(size + 4, box[2] - box[0] + 4)
                h = max(size + 4, box[3] - box[1] + 4)
                img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                draw = ImageDraw.Draw(img)
                draw.text((2 - box[0], 2 - box[1]), chr(code), font=font, fill="white")
                result = ImageTk.PhotoImage(img)
                self._icon_images[clave] = result
                return result
        except Exception:
            pass
        return None

    def toggle_field_panel(self):
        if self.field_panel_visible:
            self.field_dock.grid_remove()
            self.field_panel_visible = False
        else:
            self.field_dock.grid()
            self.field_panel_visible = True
            self._refresh_field_list()
        if self.field_panel_visible:
            self._position_field_resize_grip()
        self._set_status("Lista de campos " + ("activada." if self.field_panel_visible else "oculta."))

    def _refresh_field_list(self):
        if not hasattr(self, "field_list"):
            return
        self.field_list.delete(0, "end")
        if not self.formato:
            return
        self.formato.ordenar_campos()
        for campo in self.formato.fields:
            pregunta = campo.question.strip() or "(sin pregunta)"
            self.field_list.insert("end", "%02d  %s  —  %s" % (
                campo.order, campo.field_id, pregunta
            ))
        if self.selected_field:
            for i, campo in enumerate(self.formato.fields):
                if campo is self.selected_field:
                    self.field_list.selection_clear(0, "end")
                    self.field_list.selection_set(i)
                    self.field_list.see(i)
                    break

    def _field_list_select(self, event=None):
        if not self.formato:
            return
        sel = self.field_list.curselection()
        if not sel:
            return
        self.selected_field = self.formato.fields[sel[0]]
        self.redraw()

    def _field_list_double_click(self, event):
        self._field_list_select()
        self.editar_seleccionado()

    def _field_list_press(self, event):
        if not self.formato or not self.formato.fields:
            return
        self._field_drag_index = self.field_list.nearest(event.y)
        self._field_drop_index = self._field_drag_index
        self._show_field_drop_indicator(self._field_drop_index)

    def _field_list_motion(self, event):
        if self._field_drag_index is None or not self.formato:
            return
        count = len(self.formato.fields)
        idx = self.field_list.nearest(event.y)
        bbox = self.field_list.bbox(idx) if 0 <= idx < count else None
        if bbox:
            top, height = bbox[1], bbox[3]
            target = idx + 1 if event.y >= top + height / 2 else idx
        else:
            target = count
        target = max(0, min(count, target))
        if target == self._field_drop_index:
            return
        self._field_drop_index = target
        self._show_field_drop_indicator(target)

    def _show_field_drop_indicator(self, target):
        if not self._field_drop_indicator or not self.field_list.winfo_ismapped():
            return
        count = len(self.formato.fields) if self.formato else 0
        if count == 0:
            self._field_drop_indicator.place_forget()
            return
        if target <= 0:
            bbox = self.field_list.bbox(0)
            y = bbox[1] if bbox else 0
        elif target >= count:
            y = max(0, self.field_list.winfo_height() - 4)
        else:
            bbox = self.field_list.bbox(target)
            y = bbox[1] if bbox else 0
        self._field_drop_indicator.place(
            x=self.field_list.winfo_x() + 2,
            y=self.field_list.winfo_y() + y,
            width=max(10, self.field_list.winfo_width() - 4),
            height=3,
        )
        self._field_drop_indicator.lift()

    def _field_list_release(self, event):
        source = self._field_drag_index
        target = self._field_drop_index
        self._field_drag_index = None
        self._field_drop_index = None
        if self._field_drop_indicator:
            self._field_drop_indicator.place_forget()

        if source is None or target is None or not self.formato:
            return
        if target == source or target == source + 1:
            self._set_status("Orden de preguntas sin cambios.")
            return

        self._push_undo()
        campo = self.formato.fields.pop(source)
        if target > source:
            target -= 1
        self.formato.fields.insert(target, campo)
        self.formato.ordenar_campos()
        self.selected_field = campo
        self.unsaved = True
        self._refresh_field_list()
        self.redraw()
        self._set_status("Orden de preguntas actualizado.")

    def _dock_toolbar(self, side):
        self.toolbar_host.pack_forget()
        self.toolbar_dock_side = side

        vertical = side in ("left", "right")
        for button in getattr(self, "_tool_buttons", []):
            button.pack_forget()
            button.pack(
                side="top" if vertical else "left",
                padx=2, pady=2
            )

        self.toolbar_host.pack(
            side=side,
            fill="y" if vertical else "x"
        )

    def _dock_start(self, event):
        self._dock_dragging = True

    def _dock_motion(self, event):
        if not getattr(self, "_dock_dragging", False):
            return

    def _dock_release(self, event):
        if not getattr(self, "_dock_dragging", False):
            return
        self._dock_dragging = False
        x = event.x_root
        y = event.y_root
        left = self.root.winfo_rootx()
        top = self.root.winfo_rooty()
        right = left + self.root.winfo_width()
        bottom = top + self.root.winfo_height()
        margin = 90
        if y - top < margin:
            side = "top"
        elif bottom - y < margin:
            side = "bottom"
        elif x - left < margin:
            side = "left"
        elif right - x < margin:
            side = "right"
        else:
            side = self.toolbar_dock_side
        self._dock_toolbar(side)

    def _field_dock_start(self, event):
        self._field_dock_dragging = True

    def _field_dock_motion(self, event):
        return

    def _field_dock_release(self, event):
        if not getattr(self, "_field_dock_dragging", False):
            return
        self._field_dock_dragging = False
        x = event.x_root
        y = event.y_root
        left = self.root.winfo_rootx()
        top = self.root.winfo_rooty()
        right = left + self.root.winfo_width()
        bottom = top + self.root.winfo_height()
        margin = 90
        if y - top < margin:
            side = "top"
        elif bottom - y < margin:
            side = "bottom"
        elif x - left < margin:
            side = "left"
        elif right - x < margin:
            side = "right"
        else:
            side = self.field_dock_side
        self._dock_field_panel(side)

    def _dock_field_panel(self, side):
        self.field_dock.grid_forget()
        self.canvas.grid_forget()
        self.vbar.grid_forget()
        self.hbar.grid_forget()
        body = self.canvas.master
        self.field_dock_side = side

        for col in (0, 1, 2):
            body.columnconfigure(col, weight=0)
        for row in (0, 1, 2):
            body.rowconfigure(row, weight=0)

        if side == "left":
            self.field_dock.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 2))
            self.canvas.grid(row=0, column=1, sticky="nsew")
            self.vbar.grid(row=0, column=2, sticky="ns")
            self.hbar.grid(row=1, column=1, sticky="ew")
            body.columnconfigure(1, weight=1)
            body.rowconfigure(0, weight=1)
        elif side == "right":
            self.canvas.grid(row=0, column=0, sticky="nsew")
            self.vbar.grid(row=0, column=1, sticky="ns")
            self.field_dock.grid(row=0, column=2, rowspan=2, sticky="nsew", padx=(2, 0))
            self.hbar.grid(row=1, column=0, sticky="ew")
            body.columnconfigure(0, weight=1)
            body.rowconfigure(0, weight=1)
        elif side == "top":
            self.field_dock.grid(row=0, column=0, columnspan=3, sticky="nsew", pady=(0, 2))
            self.canvas.grid(row=1, column=0, sticky="nsew")
            self.vbar.grid(row=1, column=1, sticky="ns")
            self.hbar.grid(row=2, column=0, sticky="ew")
            body.columnconfigure(0, weight=1)
            body.rowconfigure(1, weight=1)
        else:
            self.canvas.grid(row=0, column=0, sticky="nsew")
            self.vbar.grid(row=0, column=1, sticky="ns")
            self.hbar.grid(row=1, column=0, sticky="ew")
            self.field_dock.grid(row=2, column=0, columnspan=3, sticky="nsew", pady=(2, 0))
            body.columnconfigure(0, weight=1)
            body.rowconfigure(0, weight=1)

        self._position_field_resize_grip()
        self._refresh_field_list()

    def _position_field_resize_grip(self):
        if not hasattr(self, "_field_resize_grip"):
            return
        self._field_resize_grip.place_forget()
        if self.field_dock_side == "right":
            self._field_resize_grip.config(cursor="sb_h_double_arrow")
            self._field_resize_grip.place(x=0, y=0, width=5, relheight=1.0)
        elif self.field_dock_side == "left":
            self._field_resize_grip.config(cursor="sb_h_double_arrow")
            self._field_resize_grip.place(relx=1.0, x=-5, y=0, width=5, relheight=1.0)
        elif self.field_dock_side == "top":
            self._field_resize_grip.config(cursor="sb_v_double_arrow")
            self._field_resize_grip.place(x=0, rely=1.0, y=-5, relwidth=1.0, height=5)
        else:
            self._field_resize_grip.config(cursor="sb_v_double_arrow")
            self._field_resize_grip.place(x=0, y=0, relwidth=1.0, height=5)

    def _field_resize_start_event(self, event):
        self._field_resize_start = (
            event.x_root, event.y_root,
            self.field_dock.winfo_width(), self.field_dock.winfo_height()
        )

    def _field_resize_motion_event(self, event):
        if not self._field_resize_start:
            return
        sx, sy, sw, sh = self._field_resize_start
        body = self.field_dock.master
        if self.field_dock_side == "right":
            width = max(self.field_dock_min_width, min(self.field_dock_max_width, sw - (event.x_root - sx)))
            self.field_dock.config(width=width)
        elif self.field_dock_side == "left":
            width = max(self.field_dock_min_width, min(self.field_dock_max_width, sw + (event.x_root - sx)))
            self.field_dock.config(width=width)
        elif self.field_dock_side == "top":
            height = max(120, min(650, sh + (event.y_root - sy)))
            self.field_dock.config(height=height)
        else:
            height = max(120, min(650, sh - (event.y_root - sy)))
            self.field_dock.config(height=height)
        body.update_idletasks()
        self._position_field_resize_grip()

    def _field_resize_end_event(self, event):
        self._field_resize_start = None

    def _obtener_fuentes_instaladas(self):
        fuentes = {}
        try:
            import winreg
            claves = (
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts"),
            )
            for hive, subkey in claves:
                try:
                    key = winreg.OpenKey(hive, subkey)
                except OSError:
                    continue
                try:
                    for i in range(winreg.QueryInfoKey(key)[1]):
                        try:
                            nombre, archivo, _ = winreg.EnumValue(key, i)
                        except OSError:
                            continue
                        nombre_l = str(nombre).lower()
                        familia = re.sub(
                            r"\s*\((true ?type|opentype|truetype)\)\s*$", "",
                            str(nombre), flags=re.IGNORECASE
                        ).strip()
                        familia = re.sub(
                            r"\s+(bold\s+italic|italic|bold|negrita|cursiva)\s*$", "",
                            familia, flags=re.IGNORECASE
                        ).strip()
                        archivo = os.path.expandvars(str(archivo))
                        if not os.path.isabs(archivo):
                            archivo = os.path.join(
                                os.environ.get("WINDIR", r"C:\Windows"), "Fonts", archivo
                            )
                        archivo = os.path.normpath(archivo)
                        estilo = "regular"
                        if ("bold" in nombre_l or "negrita" in nombre_l) and ("italic" in nombre_l or "cursiva" in nombre_l):
                            estilo = "bold_italic"
                        elif "bold" in nombre_l or "negrita" in nombre_l:
                            estilo = "bold"
                        elif "italic" in nombre_l or "cursiva" in nombre_l:
                            estilo = "italic"
                        else:
                            base = os.path.basename(archivo.lower())
                            if base.endswith(("bi.ttf", "bii.ttf", "bolditalic.ttf")):
                                estilo = "bold_italic"
                            elif base.endswith(("bd.ttf", "bold.ttf")):
                                estilo = "bold"
                            elif base.endswith(("i.ttf", "italic.ttf")):
                                estilo = "italic"
                        fuentes.setdefault(familia, {})[estilo] = archivo
                finally:
                    winreg.CloseKey(key)
        except Exception:
            pass
        if not fuentes:
            try:
                import tkinter.font as tkfont
                for familia in sorted(tkfont.families()):
                    fuentes.setdefault(familia, {})
            except Exception:
                pass
        return dict(sorted(fuentes.items(), key=lambda item: item[0].lower()))

    def _ruta_fuente_seleccionada(self, familia, bold=False, italic=False):
        datos = self._font_inventory.get(familia, {})
        if bold and italic:
            ruta = datos.get("bold_italic") or datos.get("bold") or datos.get("italic")
        elif bold:
            ruta = datos.get("bold")
        elif italic:
            ruta = datos.get("italic")
        else:
            ruta = datos.get("regular")
        return ruta or familia

    def _set_status(self, text):
        if hasattr(self, "status_label"):
            self.status_label.config(text=text)

    # DIAGNÓSTICO DE ATAJOS (DESACTIVADO EN USO NORMAL):
    # Este bloque registra únicamente eventos de teclado relacionados con los atajos
    # I/A/S/D/Q/W/Z y Num Lock, incluyendo tecla, estado, widget y foco, en
    # %TEMP%/formatos_traducciones_atajos.log. No registra clics de ratón ni todo
    # lo que se escribe. Si en el futuro reaparece un problema de atajos o de foco,
    # descomentar este método y las llamadas marcadas dentro de
    # _manejar_atajo_teclado() para recopilar datos de diagnóstico; volver a comentarlos
    # al terminar. Se deja apagado para evitar escrituras de log en cada evento.
    # def _diag_atajo(self, event, etapa):
    #     try:
    #         k = (getattr(event, "keysym", "") or "").lower()
    #         ch = (getattr(event, "char", "") or "").lower()
    #         if k not in ("i", "a", "s", "d", "q", "w", "z", "num_lock") and ch not in ("i", "a", "s", "d", "q", "w", "z"):
    #             return
    #         import tempfile
    #         foco = self.root.focus_get()
    #         with open(os.path.join(tempfile.gettempdir(), "formatos_traducciones_atajos.log"), "a", encoding="utf-8") as f:
    #             f.write("{} keysym={!r} char={!r} keycode={!r} state={!r} widget={!r} foco={!r}\n".format(
    #                 etapa, getattr(event, "keysym", None), getattr(event, "char", None),
    #                 getattr(event, "keycode", None), getattr(event, "state", None),
    #                 getattr(event, "widget", None), foco))
    #     except Exception:
    #         pass
    def _atajos_habilitados_en_ventana_principal(self):
        try:
            widget = self.root.focus_get()
            return widget is None or widget.winfo_toplevel() is self.root
        except Exception:
            return False

    def _alt_presionado(self, event):
        # En Windows, Tk puede incluir el estado de Num Lock en el mismo
        # bit que este código interpretaba como Alt. Consultar el estado
        # físico de Alt evita descartar los atajos cuando Num Lock está activo.
        try:
            import sys
            if sys.platform.startswith("win"):
                import ctypes
                return bool(ctypes.windll.user32.GetKeyState(0x12) & 0x8000)
        except Exception:
            pass
        return bool(getattr(event, "state", 0) & 0x0008)

    def _manejar_atajo_teclado(self, event):
        # Para reactivar el diagnóstico temporal, descomentar las llamadas siguientes
        # y el método _diag_atajo() comentado más arriba.
        # self._diag_atajo(event, 'entrada')
        if not self._atajos_habilitados_en_ventana_principal():
            # self._diag_atajo(event, 'descartado_por_foco')
            return None
        teclas = (event.keysym or "").lower()
        caracter = (getattr(event, "char", "") or "").lower()
        # Normalizar operadores y navegación del teclado numérico, independiente de Num Lock.
        teclas = {
            # Las teclas del pad numérico cambian de nombre con Num Lock.
            "kp_left": "left", "kp_4": "left", "kp4": "left", "numpad4": "left",
            "kp_right": "right", "kp_6": "right", "kp6": "right", "numpad6": "right",
            "kp_up": "up", "kp_8": "up", "kp8": "up", "numpad8": "up",
            "kp_down": "down", "kp_2": "down", "kp2": "down", "numpad2": "down",
            "kp_home": "home", "kp_7": "home", "kp7": "home", "numpad7": "home",
            "kp_end": "end", "kp_1": "end", "kp1": "end", "numpad1": "end",
            "kp_prior": "prior", "kp_9": "prior", "kp9": "prior", "numpad9": "prior",
            "kp_next": "next", "kp_3": "next", "kp3": "next", "numpad3": "next",
            "kp_insert": "insert", "kp_0": "insert", "kp0": "insert", "numpad0": "insert",
            "kp_delete": "delete", "kp_decimal": "delete", "numpaddecimal": "delete",
            "kp_add": "plus", "kp_subtract": "minus",
            "kp_multiply": "asterisk", "kp_divide": "slash",
        }.get(teclas, teclas)
        control = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        alt = self._alt_presionado(event)
        if control:
            if alt:
                return None
            if teclas == "n":
                self.nuevo()
            elif teclas == "o":
                self.abrir(solo_fdt=True)
            elif teclas == "s":
                self.guardar_como_fdt() if shift else self.guardar()
            elif teclas == "w":
                # Ctrl+W cierra la aplicación y confirma cambios sin guardar.
                self.salir()
            else:
                return None
            return "break"
        if alt:
            return None
        # Los atajos de letras no distinguen mayúsculas/minúsculas:
        # keysym y char se normalizan arriba, incluso con Shift o Caps Lock.
        herramientas = {"a": TOOL_TEXT, "s": TOOL_SELECT, "d": TOOL_HAND,
                        "z": TOOL_ZOOM, "q": TOOL_NUMBER, "w": TOOL_IMAGE}
        tecla_atajo = teclas if teclas in herramientas else caracter
        if tecla_atajo in herramientas:
            self.set_tool(herramientas[tecla_atajo])
        elif teclas == "l":
            self.toggle_field_panel()
        elif teclas == "t":
            self.configurar_archivo_terminado()
        elif teclas == "i":
            self.importar_plantilla()
        elif teclas in ("plus", "kp_add") or caracter == "+":
            self.cambiar_zoom(1.25)
        elif teclas in ("minus", "kp_subtract") or caracter == "-":
            self.cambiar_zoom(0.8)
        elif teclas in ("asterisk", "kp_multiply") or caracter == "*":
            self.set_zoom(1.0)
        else:
            return None
        return "break"

    def set_tool(self, tool):
        # Evitar que un gesto de desplazamiento anterior quede activo al
        # cambiar de herramienta mientras el ratón aún está presionado.
        self._pan_last = None
        self.tool = tool
        if tool != TOOL_ZOOM:
            self._ocultar_lupa()
        self.canvas.config(cursor="crosshair" if tool == TOOL_ZOOM else "")
        nombres = {
            TOOL_SELECT: "Selección", TOOL_HAND: "Desplazar",
            TOOL_TEXT: "Texto", TOOL_NUMBER: "Número",
            TOOL_IMAGE: "Imagen",
            TOOL_ZOOM: "Lupa",
        }
        self._set_status("Herramienta: " + nombres.get(tool, tool))

    def nuevo(self):
        if not self._confirm_unsaved():
            return
        self.formato = None
        self.template_image = None
        self.current_fdt_path = None
        self.selected_field = None
        self.field_items.clear()
        self.canvas.delete("all")
        self.canvas.configure(scrollregion=(0, 0, 0, 0))
        self.zoom = 1.0
        self._update_zoom_label()
        self.unsaved = False
        self._set_status("Nuevo formato.")

    def importar_plantilla(self, ruta=None):
        if not ruta:
            ruta = filedialog.askopenfilename(
                title="Importar plantilla",
                filetypes=[
                    ("Todos los archivos", "*.*"),
                    ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.jfif"),
                ]
            )
        if not ruta:
            return

        try:
            imagen = Image.open(ruta).convert("RGB")
            self.template_image = imagen.copy()
            self.formato = Formato(
                name=os.path.splitext(os.path.basename(ruta))[0],
                template=TemplateInfo(
                    path=os.path.abspath(ruta),
                    width=imagen.width,
                    height=imagen.height,
                    dpi=300,
                    mode="RGB",
                ),
            )
            self.current_fdt_path = None
            self.selected_field = None
            self.field_items.clear()
            self.zoom = min(
                1.0,
                max(
                    0.1,
                    min(
                        (self.canvas.winfo_width() - 40) / imagen.width,
                        (self.canvas.winfo_height() - 40) / imagen.height,
                    )
                )
            )
            if self.zoom <= 0:
                self.zoom = 0.25
            self.redraw()
            self._refresh_field_list()
            self.unsaved = True
            self._set_status(
                "Plantilla importada: %d × %d px" % (imagen.width, imagen.height)
            )
        except Exception as exc:
            messagebox.showerror("Error", "No se pudo importar la plantilla.\n%s" % exc)

    def abrir(self, solo_fdt=False):
        tipos_archivo = (
            [("Formato FDT", "*.fdt")]
            if solo_fdt else [
                ("Todos los archivos", "*.*"),
                ("Formato FDT", "*.fdt"),
                ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.jfif"),
            ]
        )
        ruta = filedialog.askopenfilename(
            title="Abrir formato FDT" if solo_fdt else "Abrir formato o plantilla",
            filetypes=tipos_archivo,
        )
        if not ruta:
            return
        if os.path.splitext(ruta)[1].lower() != ".fdt":
            if solo_fdt:
                return
            self.importar_plantilla(ruta)
            return
        try:
            from shared.fdt import cargar_fdt
            formato = cargar_fdt(ruta)
            plantilla = Image.open(formato.template.path).convert("RGB")
            if plantilla.size != (formato.template.width, formato.template.height):
                raise ValueError("Las dimensiones de la plantilla no coinciden con el FDT.")
            self.formato = formato
            self.template_image = plantilla.copy()
            self.current_fdt_path = ruta
            self.selected_field = None
            self.field_items.clear()
            self.zoom = min(1.0, max(0.1, min(
                (self.canvas.winfo_width() - 40) / plantilla.width,
                (self.canvas.winfo_height() - 40) / plantilla.height,
            )))
            self.redraw()
            self._refresh_field_list()
            self.unsaved = False
            self._set_status("Formato abierto: " + os.path.basename(ruta))
            # Reproducir un clic de Selección en el píxel (1, 1) de la plantilla,
            # en la esquina superior izquierda, y después activar Desplazar.
            # Se agenda tras abrir para que Tkinter termine de actualizar el lienzo.
            self.root.after_idle(self._activar_desplazar_al_abrir)
        except Exception as exc:
            messagebox.showerror("Error al abrir", str(exc))

    def _activar_desplazar_al_abrir(self):
        if self.template_image is None or not self.formato:
            return
        # La plantilla se dibuja con un margen de 20 px y escala según el zoom.
        # Llevar la vista al origen garantiza que el punto (1, 1) esté visible.
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self.canvas.update_idletasks()
        x = int(round(20 + self.zoom))
        y = int(round(20 + self.zoom))
        # Usar los mismos eventos del lienzo que un clic real con Selección.
        self.set_tool(TOOL_SELECT)
        self.canvas.event_generate("<ButtonPress-1>", x=x, y=y)
        self.canvas.event_generate("<ButtonRelease-1>", x=x, y=y)
        self.set_tool(TOOL_HAND)

    def guardar(self):
        if not self.formato:
            return self.guardar_como_fdt()
        if not self.current_fdt_path:
            return self.guardar_como_fdt()
        try:
            validar_fdt(self.formato)
            guardar_fdt(self.formato, self.current_fdt_path)
            self.unsaved = False
            self._set_status("Formato guardado.")
        except Exception as exc:
            messagebox.showerror("Error al guardar", str(exc))

    def guardar_como_fdt(self):
        if not self.formato:
            messagebox.showwarning("Guardar", "Primero importe una plantilla.")
            return
        ruta = filedialog.asksaveasfilename(
            title="Guardar como FDT",
            defaultextension=".fdt",
            filetypes=[("Formato FDT", "*.fdt")],
        )
        if not ruta:
            return
        # Algunos cuadros de diálogo no aplican defaultextension si el usuario
        # escribe el nombre sin extensión; garantizar .fdt explícitamente.
        if not ruta.lower().endswith(".fdt"):
            ruta += ".fdt"
        try:
            validar_fdt(self.formato)
            guardar_fdt(self.formato, ruta)
            self.current_fdt_path = ruta
            self.unsaved = False
            self._set_status("FDT guardado.")
        except Exception as exc:
            messagebox.showerror("Error al guardar", str(exc))

    def redraw(self):
        self.canvas.delete("all")
        self.field_items.clear()
        self._field_preview_images.clear()
        self.template_tk = None
        if self.template_image is None:
            self.canvas.configure(scrollregion=(0, 0, 0, 0))
            return

        # El área lógica conserva el tamaño completo según el zoom, pero solo
        # se rasterizan mosaicos de la zona visible. Así no se crea una copia
        # de cientos de megapíxeles al ampliar una plantilla completa.
        w = max(1, int(round(self.template_image.width * self.zoom)))
        h = max(1, int(round(self.template_image.height * self.zoom)))
        self.canvas.configure(scrollregion=(0, 0, w + 40, h + 40))
        self._refresh_visible_template_tiles()

        if self.formato:
            ids_validos = {campo.field_id for campo in self.formato.fields}
            self._field_preview_cache = {
                field_id: entry for field_id, entry in self._field_preview_cache.items()
                if field_id in ids_validos
            }
            for campo in self.formato.fields:
                self._draw_field(campo)

        self._update_zoom_label()

    def _actualizar_gradiente_barra(self, event=None):
        if not hasattr(self, "toolbar_host") or not hasattr(self, "_toolbar_gradient_label"): return
        w, h = max(1, self.toolbar_host.winfo_width()), max(1, self.toolbar_host.winfo_height())
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for y in range(h):
            v = round(128 * y / max(1, h - 1))
            draw.line((0, y, w, y), fill=(v, v, v))
        self._toolbar_gradient_image = ImageTk.PhotoImage(img)
        self._toolbar_gradient_label.configure(image=self._toolbar_gradient_image)

    def _actualizar_gradiente_area(self):
        if not hasattr(self, "canvas") or not self.canvas.winfo_exists(): return
        w, h = max(1, self.canvas.winfo_width()), max(1, self.canvas.winfo_height())
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        for x in range(w):
            v = round(128 * (1 - abs(2 * x / max(1, w - 1) - 1)))
            draw.line((x, 0, x, h), fill=(v, v, v))
        self._workspace_gradient_image = ImageTk.PhotoImage(img)
        self.canvas.itemconfigure(self._workspace_gradient_item, image=self._workspace_gradient_image)
        self.canvas.coords(self._workspace_gradient_item, self.canvas.canvasx(0), self.canvas.canvasy(0))
        self.canvas.tag_lower(self._workspace_gradient_item)

    def _on_canvas_xscroll(self, first, last):
        self.hbar.set(first, last)
        self.root.after_idle(self._actualizar_gradiente_area)
        self.root.after_idle(self._refresh_visible_template_tiles)

    def _on_canvas_yscroll(self, first, last):
        self.vbar.set(first, last)
        self.root.after_idle(self._actualizar_gradiente_area)
        self.root.after_idle(self._refresh_visible_template_tiles)

    def _on_canvas_configure(self, event=None):
        self.root.after_idle(self._actualizar_gradiente_area)
        self.root.after_idle(self._refresh_visible_template_tiles)

    def _refresh_visible_template_tiles(self):
        """Dibuja únicamente mosaicos de la plantilla que intersectan la vista."""
        if self.template_image is None or not hasattr(self, "canvas"):
            return
        self.canvas.delete("template_tile")
        # Las imágenes de los mosaicos anteriores ya no están en el lienzo.
        self._template_tile_images.clear()
        canvas_width = max(1, self.canvas.winfo_width())
        canvas_height = max(1, self.canvas.winfo_height())
        left = max(0.0, self.canvas.canvasx(0) - 20)
        top = max(0.0, self.canvas.canvasy(0) - 20)
        right = min(
            self.template_image.width * self.zoom,
            self.canvas.canvasx(canvas_width) - 20,
        )
        bottom = min(
            self.template_image.height * self.zoom,
            self.canvas.canvasy(canvas_height) - 20,
        )
        if right <= left or bottom <= top:
            return

        # Cada mosaico queda limitado aproximadamente a 512x512 píxeles
        # en pantalla, incluso cuando el zoom es elevado.
        tile_source = max(1, int(512 / self.zoom))
        sx0 = max(0, int(left // self.zoom))
        sy0 = max(0, int(top // self.zoom))
        sx1 = min(self.template_image.width, int(right / self.zoom) + 1)
        sy1 = min(self.template_image.height, int(bottom / self.zoom) + 1)
        start_x = (sx0 // tile_source) * tile_source
        start_y = (sy0 // tile_source) * tile_source
        for sy in range(start_y, sy1, tile_source):
            for sx in range(start_x, sx1, tile_source):
                crop = self.template_image.crop((
                    sx, sy,
                    min(self.template_image.width, sx + tile_source),
                    min(self.template_image.height, sy + tile_source),
                ))
                out_w = max(1, int(round(crop.width * self.zoom)))
                out_h = max(1, int(round(crop.height * self.zoom)))
                tile = crop.resize((out_w, out_h), Image.Resampling.NEAREST)
                photo = ImageTk.PhotoImage(tile)
                self._template_tile_images[(sx, sy)] = photo
                self.canvas.create_image(
                    20 + sx * self.zoom, 20 + sy * self.zoom,
                    image=photo, anchor="nw", tags=("template_tile",),
                )

        # Los mosaicos se reconstruyen al desplazarse; deben quedar siempre
        # detrás de los campos para que Desplazar no los oculte visualmente.
        self.canvas.tag_lower("template_tile")

    def _redraw_fields_only(self):
        """Actualiza campos sin volver a escalar ni reconstruir la plantilla."""
        if self.template_image is None:
            return
        self.canvas.delete("field")
        self.canvas.delete("field_preview")
        self.canvas.delete("resize_handle")
        self.field_items.clear()
        self._field_preview_images.clear()
        if self.formato:
            for campo in self.formato.fields:
                self._draw_field(campo)

    def _field_preview_signature(self, campo):
        """Propiedades que cambian el contenido de la muestra rasterizada."""
        p = campo.position
        s = campo.text_style
        c = s.color
        return (
            campo.field_type, campo.question, bool(getattr(campo, "uppercase", False)),
            s.font_family, s.font_size_px, s.bold, s.italic, s.alignment,
            s.orientation, c.r, c.g, c.b, p.width, p.height,
        )

    def _crear_preview_comprimido(self, campo):
        """Devuelve JPEG al 50 % más una máscara alpha, sin reducir dimensiones."""
        p = campo.position
        ancho = max(1, int(round(p.width)))
        alto = max(1, int(round(p.height)))
        capa = Image.new("RGBA", (ancho, alto), (0, 0, 0, 0))
        capa_draw = ImageDraw.Draw(capa)

        if campo.text_style.font_family:
            fuente = _cargar_fuente(
                campo.text_style.font_family,
                max(1, int(round(campo.text_style.font_size_px))),
                campo.text_style.bold,
                campo.text_style.italic,
            )
        else:
            try:
                fuente = ImageFont.load_default(
                    size=max(1, int(round(campo.text_style.font_size_px)))
                )
            except TypeError:
                fuente = ImageFont.load_default()

        muestra = {
            FIELD_TYPE_IMAGE: "IMAGEN",
            FIELD_TYPE_NUMBER: "123456",
        }.get(campo.field_type, "Texto")
        if getattr(campo, "uppercase", False):
            muestra = muestra.upper()

        color_rgb = (
            campo.text_style.color.r,
            campo.text_style.color.g,
            campo.text_style.color.b,
            255,
        )
        alineacion = campo.text_style.alignment
        y_muestra = min(5, max(0, alto - 1))
        if alineacion == "center":
            xy, anchor = (ancho // 2, y_muestra), "mt"
        elif alineacion == "right":
            xy, anchor = (ancho, y_muestra), "rt"
        else:
            xy, anchor = (0, y_muestra), "lt"
        capa_draw.text(xy, muestra, fill=color_rgb, font=fuente, anchor=anchor)
        capa_draw.rectangle(
            (0, 0, max(0, ancho - 1), max(0, alto - 1)),
            outline=(0, 0, 0, 255),
            width=min(3, ancho, alto),
        )

        # JPEG no admite transparencia: se conserva el canal alpha por separado.
        jpeg_buffer = io.BytesIO()
        capa.convert("RGB").save(
            jpeg_buffer, format="JPEG", quality=50, optimize=True
        )
        alpha_buffer = io.BytesIO()
        capa.getchannel("A").save(
            alpha_buffer, format="PNG", optimize=True
        )
        return jpeg_buffer.getvalue(), alpha_buffer.getvalue()

    def _draw_field(self, campo):
        p = campo.position
        x1 = 20 + p.x * self.zoom
        y1 = 20 + p.y * self.zoom
        x2 = x1 + p.width * self.zoom
        y2 = y1 + p.height * self.zoom

        color = "#00d7ff" if campo is self.selected_field else "#ffcc00"
        # El contorno visible se rasteriza junto con la muestra; este
        # rectángulo sin trazo conserva la zona interactiva.
        rect = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="", width=0,
            tags=("field", campo.field_id)
        )

        objetos = [rect]

        # La muestra orientativa conserva las dimensiones del campo. Se cachea
        # como JPEG quality=50 más máscara alpha; el zoom usa NEAREST. Esta caché
        # solo pertenece al configurador y no afecta la salida del capturador.
        if campo.field_type in (
            FIELD_TYPE_IMAGE, FIELD_TYPE_TEXT, FIELD_TYPE_NUMBER
        ):
            try:
                firma = self._field_preview_signature(campo)
                entrada = self._field_preview_cache.get(campo.field_id)
                if entrada is None or entrada[0] != firma:
                    comprimido = self._crear_preview_comprimido(campo)
                    self._field_preview_cache[campo.field_id] = (firma, comprimido)
                else:
                    comprimido = entrada[1]

                # Reconstruir la capa solo para dibujarla; los bytes comprimidos
                # permanecen en caché para reducir el consumo de memoria.
                jpeg_buffer = io.BytesIO(comprimido[0])
                alpha_buffer = io.BytesIO(comprimido[1])
                with Image.open(jpeg_buffer) as imagen_rgb:
                    base_rgb = imagen_rgb.convert("RGB")
                with Image.open(alpha_buffer) as imagen_alpha:
                    mascara_alpha = imagen_alpha.convert("L")
                base_rgb.putalpha(mascara_alpha)
                ancho_vista = max(1, int(round(p.width * self.zoom)))
                alto_vista = max(1, int(round(p.height * self.zoom)))
                visible_capa = base_rgb.resize(
                    (ancho_vista, alto_vista),
                    Image.Resampling.NEAREST,
                )
                preview = ImageTk.PhotoImage(visible_capa)
                self._field_preview_images[campo.field_id] = preview
                image_id = self.canvas.create_image(
                    x1, y1, image=preview, anchor="nw",
                    tags=("field_preview", campo.field_id),
                )
                objetos.append(image_id)
            except Exception:
                pass

        label = self.canvas.create_text(
            x1 + 4, y1 + 4,
            text="%d  %s" % (campo.order, campo.field_type),
            fill=color, anchor="nw",
            tags=("field", campo.field_id)
        )
        objetos.append(label)
        self.field_items[campo.field_id] = tuple(objetos)

        if campo is self.selected_field:
            self._draw_resize_handles(campo, x1, y1, x2, y2)

    def _draw_resize_handles(self, campo, x1, y1, x2, y2):
        size = 8
        puntos = (
            ("nw", x1, y1), ("n", (x1 + x2) / 2, y1),
            ("ne", x2, y1), ("e", x2, (y1 + y2) / 2),
            ("se", x2, y2), ("s", (x1 + x2) / 2, y2),
            ("sw", x1, y2), ("w", x1, (y1 + y2) / 2),
        )
        for nombre, cx, cy in puntos:
            self.canvas.create_rectangle(
                cx - size / 2, cy - size / 2,
                cx + size / 2, cy + size / 2,
                fill="white", outline="black", width=1,
                tags=("resize_handle", campo.field_id, nombre),
            )

    def _hit_resize_handle(self, campo, cx, cy):
        p = campo.position
        puntos = {
            "nw": (p.x, p.y), "n": (p.x + p.width / 2, p.y),
            "ne": (p.x + p.width, p.y), "e": (p.x + p.width, p.y + p.height / 2),
            "se": (p.x + p.width, p.y + p.height), "s": (p.x + p.width / 2, p.y + p.height),
            "sw": (p.x, p.y + p.height), "w": (p.x, p.y + p.height / 2),
        }
        dx, dy = self._canvas_to_document(cx, cy)
        tolerancia = max(6, int(round(10 / max(self.zoom, 0.01))))
        for nombre, (hx, hy) in puntos.items():
            if abs(dx - hx) <= tolerancia and abs(dy - hy) <= tolerancia:
                return nombre
        return None

    def _resize_selected_field(self, dx, dy):
        campo = self.selected_field
        origen = self._field_resize_origin
        if not campo or not origen:
            return
        x, y, w, h = origen
        handle = self._field_resize_handle

        if "w" in handle:
            x += dx
            w -= dx
        if "e" in handle:
            w += dx
        if "n" in handle:
            y += dy
            h -= dy
        if "s" in handle:
            h += dy

        w = max(1, w)
        h = max(1, h)
        if "w" in handle:
            x = origen[0] + origen[2] - w
        if "n" in handle:
            y = origen[1] + origen[3] - h

        x = max(0, x)
        y = max(0, y)
        if x + w > self.template_image.width:
            w = self.template_image.width - x
        if y + h > self.template_image.height:
            h = self.template_image.height - y
        if w <= 0 or h <= 0:
            return

        campo.position = Position(int(x), int(y), int(w), int(h))
        self.unsaved = True
        self.redraw()

    def _canvas_to_document(self, x, y):
        return (
            max(0, int(round((x - 20) / self.zoom))),
            max(0, int(round((y - 20) / self.zoom))),
        )

    def _event_to_canvas(self, event):
        return self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)

    def _find_field_at(self, x, y):
        if not self.formato:
            return None
        dx, dy = self._canvas_to_document(x, y)
        for campo in reversed(self.formato.fields):
            p = campo.position
            if p.x <= dx <= p.x + p.width and p.y <= dy <= p.y + p.height:
                return campo
        return None

    def on_mouse_down(self, event):
        self.canvas.focus_set()
        if not self.formato or self.template_image is None:
            return
        cx, cy = self._event_to_canvas(event)
        self._move_changed = False

        if self.tool == TOOL_ZOOM:
            self.cambiar_zoom(1.25, event=event)
            return
        if self.tool == TOOL_HAND:
            # Usar el mecanismo nativo del Canvas para iniciar el paneo.
            # Tkinter conserva correctamente la referencia aunque el zoom
            # haya reconstruido la región desplazable.
            self.canvas.scan_mark(event.x, event.y)
            self._pan_last = (event.x, event.y)
            return
        if self.tool == TOOL_SELECT:
            # Primero comprobar los controles del campo seleccionado. Esto permite
            # redimensionar desde los cuadrados incluso si el puntero cae justo
            # fuera del borde geométrico del campo.
            if self.selected_field:
                handle = self._hit_resize_handle(self.selected_field, cx, cy)
                if handle:
                    self._field_resize_handle = handle
                    self._field_resize_origin = (
                        self.selected_field.position.x,
                        self.selected_field.position.y,
                        self.selected_field.position.width,
                        self.selected_field.position.height,
                    )
                    self._field_resize_start = (cx, cy)
                    self._move_start = None
                    self._move_origin = None
                    self._push_undo()
                    return
            campo = self._find_field_at(cx, cy)
            seleccionado_antes = self.selected_field
            self.selected_field = campo
            self._field_resize_handle = None
            self._field_resize_start = None
            self._field_resize_origin = None
            if campo:
                self._move_start = (cx, cy)
                self._move_origin = (campo.position.x, campo.position.y)
            else:
                self._move_start = None
                self._move_origin = None
            if campo is not seleccionado_antes:
                self._redraw_fields_only()
            return

        self.drag_start = self._canvas_to_document(cx, cy)
        self._draw_start_canvas = (cx, cy)
        doc_x, doc_y = self.drag_start
        px, py = 20 + doc_x * self.zoom, 20 + doc_y * self.zoom
        self.drawing_rect = self.canvas.create_rectangle(
            px, py, px, py, outline="black", width=3
        )

    def on_mouse_move(self, event):
        cx, cy = self._event_to_canvas(event)
        if self.tool == TOOL_ZOOM:
            self._mostrar_lupa(event)
        elif self._magnifier_label is not None:
            self._ocultar_lupa()

        if self._field_resize_handle and self._field_resize_start and self.tool == TOOL_SELECT:
            dx = int(round((cx - self._field_resize_start[0]) / self.zoom))
            dy = int(round((cy - self._field_resize_start[1]) / self.zoom))
            self._resize_selected_field(dx, dy)
            return

        if self.tool == TOOL_HAND and self._pan_last is not None:
            # Desplazar la vista según el movimiento del puntero desde el clic.
            self.canvas.scan_dragto(event.x, event.y, gain=1)
            self._pan_last = (event.x, event.y)
            return

        if self.tool == TOOL_SELECT and self.selected_field and self._move_start is not None:
            dx = int(round((cx - self._move_start[0]) / self.zoom))
            dy = int(round((cy - self._move_start[1]) / self.zoom))
            if dx or dy:
                if not self._move_changed:
                    self._push_undo()
                    self._move_changed = True
                campo = self.selected_field
                max_x = max(0, self.template_image.width - campo.position.width)
                max_y = max(0, self.template_image.height - campo.position.height)
                campo.position = Position(
                    max(0, min(max_x, self._move_origin[0] + dx)),
                    max(0, min(max_y, self._move_origin[1] + dy)),
                    campo.position.width,
                    campo.position.height,
                )
                self.unsaved = True
                self._redraw_fields_only()
            return

        if self.drag_start is None or self.tool not in (TOOL_TEXT, TOOL_NUMBER, TOOL_IMAGE):
            return
        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_document(cx, cy)
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        if right == left: right += 1
        if bottom == top: bottom += 1
        if self.drawing_rect:
            self.canvas.coords(
                self.drawing_rect,
                20 + left * self.zoom, 20 + top * self.zoom,
                20 + right * self.zoom, 20 + bottom * self.zoom
            )

    def on_mouse_up(self, event):
        if self.tool == TOOL_HAND:
            self._pan_last = None
            return
        if self.tool == TOOL_SELECT and self._field_resize_handle:
            self._field_resize_handle = None
            self._field_resize_start = None
            self._field_resize_origin = None
            return
        if self.tool == TOOL_SELECT:
            if self._move_changed:
                self._move_changed = False
                self._set_status("Campo movido.")
            self._move_start = None
            self._move_origin = None
            return
        if self.drag_start is None:
            return
        if self.tool not in (TOOL_TEXT, TOOL_NUMBER, TOOL_IMAGE):
            self.drag_start = None
            return

        cx, cy = self._event_to_canvas(event)
        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_document(cx, cy)
        inicio_canvas = self._draw_start_canvas or (cx, cy)
        arrastro = abs(cx - inicio_canvas[0]) > 4 or abs(cy - inicio_canvas[1]) > 4

        if not arrastro and self.formato.fields:
            anterior = max(self.formato.fields, key=lambda item: item.order)
            width = min(anterior.position.width, self.template_image.width)
            height = min(anterior.position.height, self.template_image.height)
            left = max(0, min(x0, self.template_image.width - width))
            top = max(0, min(y0, self.template_image.height - height))
        else:
            left, right = sorted((x0, x1))
            top, bottom = sorted((y0, y1))
            width = max(1, right - left)
            height = max(1, bottom - top)

        if self.drawing_rect:
            self.canvas.delete(self.drawing_rect)
            self.drawing_rect = None
        self.drag_start = None
        self._draw_start_canvas = None

        # Guardar el historial anterior para que Cancelar no consuma una acción de deshacer.
        undo_antes_creacion = list(self._undo_stack)
        redo_antes_creacion = list(self._redo_stack)
        seleccionado_antes_creacion = self.selected_field
        unsaved_antes_creacion = self.unsaved
        self._push_undo()
        import copy
        if self.formato.fields:
            estilo_anterior = copy.deepcopy(self.formato.fields[-1].text_style)
        else:
            estilo_anterior = TextStyle(
                font_family="", font_size_px=24, color=Color(0, 0, 0),
                alignment="left", bold=False, italic=False,
            )
        mayusculas_anteriores = next(
            (
                bool(getattr(c, "uppercase", False))
                for c in reversed(self.formato.fields)
                if c.field_type != TOOL_IMAGE
            ),
            False,
        )
        campo = Field(
            field_id=self._nuevo_id(),
            question="",
            field_type=self.tool,
            position=Position(left, top, width, height),
            text_style=estilo_anterior,
            uppercase=mayusculas_anteriores,
        )
        self.formato.agregar_campo(campo)
        self.selected_field = campo
        self.unsaved = True
        self.redraw()
        self._refresh_field_list()
        self.editar_seleccionado(
            es_nuevo=True,
            undo_antes=undo_antes_creacion,
            redo_antes=redo_antes_creacion,
            seleccionado_antes=seleccionado_antes_creacion,
            unsaved_antes=unsaved_antes_creacion,
        )

    def on_double_click(self, event):
        if self.tool != TOOL_SELECT or not self.formato:
            return
        cx, cy = self._event_to_canvas(event)
        campo = self._find_field_at(cx, cy)
        if campo:
            self.selected_field = campo
            self._redraw_fields_only()
            self.editar_seleccionado()

    def _mover_seleccionado_tecla(self, event, pasos_forzados=None):
        # Los atajos de edición solo actúan cuando el lienzo tiene el foco,
        # para no interceptar flechas dentro de entradas o cuadros de diálogo.
        if self.root.focus_get() not in (self.canvas, self.root):
            return
        if not self.formato or not self.selected_field:
            return
        estado = int(getattr(event, "state", 0) or 0)
        shift = bool(estado & 0x0001)
        pasos = pasos_forzados if pasos_forzados is not None else (25 if shift else 1)
        tecla = (event.keysym or "").lower()
        tecla = {
            "kp_left": "left", "kp_4": "left", "kp4": "left", "numpad4": "left",
            "kp_right": "right", "kp_6": "right", "kp6": "right", "numpad6": "right",
            "kp_up": "up", "kp_8": "up", "kp8": "up", "numpad8": "up",
            "kp_down": "down", "kp_2": "down", "kp2": "down", "numpad2": "down",
        }.get(tecla, tecla)
        dx = -pasos if tecla == "left" else pasos if tecla == "right" else 0
        dy = pasos if tecla == "down" else -pasos if tecla == "up" else 0
        campo = self.selected_field
        max_x = max(0, self.template_image.width - campo.position.width)
        max_y = max(0, self.template_image.height - campo.position.height)
        nx = max(0, min(max_x, campo.position.x + dx))
        ny = max(0, min(max_y, campo.position.y + dy))
        if (nx, ny) == (campo.position.x, campo.position.y):
            return "break"
        self._push_undo()
        campo.position = Position(nx, ny, campo.position.width, campo.position.height)
        self.unsaved = True
        self._redraw_fields_only()
        self._refresh_field_list()
        return "break"

    def _eliminar_con_tecla(self, event):
        if self.root.focus_get() not in (self.canvas, self.root):
            return
        if self.selected_field:
            self.eliminar_seleccionado()
            return "break"

    def on_canvas_motion(self, event):
        if self.tool == TOOL_ZOOM:
            self._mostrar_lupa(event)
        elif self._magnifier_label is not None:
            self._ocultar_lupa()

    def _mostrar_lupa(self, event):
        if self._magnifier_label is None:
            self._magnifier_label = tk.Label(
                self.root, text="🔍", bg="black", fg="white",
                font=("Segoe UI Symbol", 18), bd=0, padx=1, pady=0
            )
        x = event.x_root - self.root.winfo_rootx() + 8
        y = event.y_root - self.root.winfo_rooty() + 8
        self._magnifier_label.place(x=x, y=y)
        self._magnifier_label.lift()

    def _ocultar_lupa(self):
        if self._magnifier_label is not None:
            self._magnifier_label.place_forget()

    def configurar_archivo_terminado(self):
        if not self.formato:
            messagebox.showwarning("Archivo terminado", "Primero importe una plantilla.")
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Archivo terminado")
        dialog.configure(bg="#202020")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("560x390")
        dialog.resizable(False, False)

        tk.Label(
            dialog,
            text="Configuración del nombre del archivo resultante",
            bg="#202020", fg="white",
            font=("Arial", 12, "bold"),
        ).pack(anchor="w", padx=18, pady=(18, 12))

        tk.Label(dialog, text="Nombre base del archivo",
                 bg="#202020", fg="white").pack(anchor="w", padx=18)
        name_var = tk.StringVar(
            value=getattr(self.formato.output_naming, "name_text", "")
        )
        tk.Entry(
            dialog, textvariable=name_var,
            bg="#303030", fg="white", insertbackground="white",
        ).pack(fill="x", padx=18, pady=(4, 12))

        fields = ["<nada>"] + [
            "%02d — %s — %s" % (
                campo.order,
                campo.field_id,
                campo.question.strip() or "(sin pregunta)",
            )
            for campo in self.formato.fields
        ]
        ids = [""] + [campo.field_id for campo in self.formato.fields]

        tk.Label(
            dialog,
            text="Campos que se incorporarán al nombre (máximo 4)",
            bg="#202020", fg="white",
        ).pack(anchor="w", padx=18, pady=(4, 6))

        variables = []
        for numero in range(4):
            fila = tk.Frame(dialog, bg="#202020")
            fila.pack(fill="x", padx=18, pady=3)
            tk.Label(
                fila, text="Parte %d" % (numero + 1),
                width=9, anchor="w", bg="#202020", fg="white",
            ).pack(side="left")
            var = tk.StringVar(value="<nada>")
            combo = ttk.Combobox(
                fila, textvariable=var, values=fields,
                state="readonly", width=58,
            )
            combo.pack(side="left", fill="x", expand=True)
            variables.append((var, ids))
            stored_id = self.formato.output_naming.field_ids[numero] if numero < len(self.formato.output_naming.field_ids) else ""
            if stored_id:
                for indice, campo in enumerate(self.formato.fields, start=1):
                    if campo.field_id == stored_id:
                        combo.current(indice)
                        break

        def aceptar():
            seleccionados = []
            for var, mapping in variables:
                valor = var.get()
                if valor == "<nada>" or not valor:
                    seleccionados.append("")
                    continue
                indice = fields.index(valor)
                seleccionados.append(mapping[indice])

            self.formato.output_naming = OutputNaming(
                name_text=name_var.get().strip(),
                field_ids=seleccionados,
            )
            self.unsaved = True
            dialog.destroy()
            self._set_status("Configuración de archivo terminado guardada.")

        botones = tk.Frame(dialog, bg="#202020")
        botones.pack(side="bottom", fill="x", padx=18, pady=16)
        tk.Button(
            botones, text="Cancelar", command=dialog.destroy,
            bg="#303030", fg="white", relief="flat",
        ).pack(side="right", padx=4)
        tk.Button(
            botones, text="Aceptar", command=aceptar,
            bg="#005f73", fg="white", relief="flat",
        ).pack(side="right", padx=4)

    def _nuevo_id(self):
        base = "campo"
        usados = {campo.field_id for campo in self.formato.fields}
        numero = 1
        while base + str(numero) in usados:
            numero += 1
        return base + str(numero)

    def editar_seleccionado(
        self, es_nuevo=False, undo_antes=None, redo_antes=None,
        seleccionado_antes=None, unsaved_antes=None,
    ):
        if not self.selected_field:
            return

        campo = self.selected_field
        dialog = tk.Toplevel(self.root)
        dialog.title("Propiedades del campo %d" % campo.order)
        dialog.configure(bg="#202020")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("430x690")
        dialog.resizable(False, False)

        def label(text):
            return tk.Label(dialog, text=text, bg="#202020", fg="white", anchor="w")

        label("Campo / orden").pack(fill="x", padx=16, pady=(14, 2))
        tk.Label(dialog, text="%d — %s" % (campo.order, campo.field_type),
                 bg="#202020", fg="#00d7ff", anchor="w").pack(fill="x", padx=16)

        label("ID del campo").pack(fill="x", padx=16, pady=(12, 2))
        id_var = tk.StringVar(value=campo.field_id)
        tk.Entry(dialog, textvariable=id_var, bg="#303030", fg="white", insertbackground="white").pack(fill="x", padx=16)

        label("Pregunta que verá el capturador").pack(fill="x", padx=16, pady=(12, 2))
        question = tk.Text(dialog, height=4, bg="#303030", fg="white", insertbackground="white")
        question.pack(fill="x", padx=16)
        question.insert("1.0", campo.question)

        # Al abrir las propiedades, dejar el cursor en la pregunta para escribir
        # inmediatamente con el teclado físico, sin tener que seleccionar el cuadro.
        def enfocar_pregunta():
            question.focus_set()
            question.mark_set("insert", "end")
            question.see("insert")
        dialog.after(100, enfocar_pregunta)

        required_var = tk.BooleanVar(value=campo.required)
        tk.Checkbutton(dialog, text="Respuesta obligatoria", variable=required_var,
                       bg="#202020", fg="white", selectcolor="#303030",
                       activebackground="#202020", activeforeground="white").pack(anchor="w", padx=16, pady=8)

        uppercase_var = tk.BooleanVar(value=bool(getattr(campo, "uppercase", False)))
        uppercase_row = tk.Frame(dialog, bg="#202020")
        uppercase_row.pack(fill="x", padx=16, pady=(0, 6))
        uppercase_button = tk.Button(
            uppercase_row, text="A" if uppercase_var.get() else "a", width=3,
            command=lambda: (
                uppercase_var.set(not uppercase_var.get()),
                uppercase_button.config(
                    text="A" if uppercase_var.get() else "a",
                    bg="#005f73" if uppercase_var.get() else "#303030",
                ),
            ),
            bg="#005f73" if uppercase_var.get() else "#303030",
            fg="white", activebackground="#006f83", relief="flat",
        )
        uppercase_button.pack(side="left")
        tk.Label(uppercase_row, text="Convertir captura a MAYÚSCULAS",
                 bg="#202020", fg="white").pack(side="left", padx=10)

        label("Tipografía").pack(fill="x", padx=16, pady=(8, 2))
        font_names = list(self._font_inventory.keys())
        stored_font = campo.text_style.font_family or ""
        initial_family = stored_font
        for familia, datos in self._font_inventory.items():
            if stored_font in datos.values():
                initial_family = familia
                break
        font_var = tk.StringVar(value=initial_family)
        fila_fuente = tk.Frame(dialog, bg="#202020")
        fila_fuente.pack(fill="x", padx=16)
        font_combo = ttk.Combobox(
            fila_fuente, textvariable=font_var, values=font_names,
            state="readonly" if font_names else "normal", height=18
        )
        font_combo.pack(side="left", fill="x", expand=True)
        if not initial_family and font_names:
            font_combo.current(0)

        def importar_tipografia():
            ruta = filedialog.askopenfilename(
                title="Seleccionar archivo de tipografía",
                parent=dialog,
                filetypes=[
                    ("Archivos de tipografía", "*.ttf *.otf *.ttc"),
                    ("Todos los archivos", "*.*"),
                ],
            )
            if not ruta:
                return
            extension = os.path.splitext(ruta)[1].lower()
            if extension not in (".ttf", ".otf", ".ttc"):
                messagebox.showwarning(
                    "Tipografía no válida",
                    "Selecciona un archivo .ttf, .otf o .ttc.",
                    parent=dialog,
                )
                return
            try:
                # Verifica que Pillow pueda abrir el archivo antes de agregarlo.
                ImageFont.truetype(ruta, size=20)
            except Exception as exc:
                messagebox.showerror(
                    "No se pudo abrir la tipografía",
                    "El archivo seleccionado no se pudo leer como fuente.\\n\\n%s" % exc,
                    parent=dialog,
                )
                return

            nombre_base = os.path.basename(ruta)
            familia_importada = nombre_base
            sufijo = 2
            while familia_importada in self._font_inventory:
                existente = self._font_inventory[familia_importada]
                if ruta in existente.values():
                    break
                familia_importada = "%s (%d)" % (nombre_base, sufijo)
                sufijo += 1

            if familia_importada not in self._font_inventory:
                self._font_inventory[familia_importada] = {
                    "regular": ruta,
                    "bold": ruta,
                    "italic": ruta,
                    "bold_italic": ruta,
                }
            elif ruta not in self._font_inventory[familia_importada].values():
                self._font_inventory[familia_importada] = {
                    "regular": ruta,
                    "bold": ruta,
                    "italic": ruta,
                    "bold_italic": ruta,
                }
            valores = list(font_combo.cget("values"))
            if familia_importada not in valores:
                valores.append(familia_importada)
                valores.sort(key=lambda item: item.lower())
                font_combo.configure(values=valores)
            font_var.set(familia_importada)
            self._set_status("Tipografía importada. Se incluirá en el FDT al guardar el formato.")

        tk.Button(
            fila_fuente, text="＋ Fuente", command=importar_tipografia,
            bg="#005f73", fg="white", activebackground="#087f8c",
            activeforeground="white", relief="flat", padx=10,
        ).pack(side="left", padx=(8, 0))

        row = tk.Frame(dialog, bg="#202020")
        row.pack(fill="x", padx=16, pady=8)

        tk.Label(row, text="Tamaño px", bg="#202020", fg="white").pack(side="left")
        size_var = tk.StringVar(value=str(campo.text_style.font_size_px))
        tk.Entry(row, textvariable=size_var, width=8, bg="#303030", fg="white", insertbackground="white").pack(side="left", padx=8)

        style_row = tk.Frame(dialog, bg="#202020")
        style_row.pack(fill="x", padx=16, pady=4)
        bold_var = tk.BooleanVar(value=campo.text_style.bold)
        italic_var = tk.BooleanVar(value=campo.text_style.italic)
        tk.Checkbutton(style_row, text="Negrita", variable=bold_var, bg="#202020", fg="white", selectcolor="#303030").pack(side="left")
        tk.Checkbutton(style_row, text="Cursiva", variable=italic_var, bg="#202020", fg="white", selectcolor="#303030").pack(side="left", padx=14)

        align_var = tk.StringVar(value=campo.text_style.alignment)
        tk.Label(row, text="Alineación", bg="#202020", fg="white").pack(side="left", padx=(12, 4))
        ttk.Combobox(row, textvariable=align_var, values=("left", "center", "right", "justify"),
                     state="readonly", width=9).pack(side="left")

        orient_var = tk.StringVar(value=campo.text_style.orientation)
        row2 = tk.Frame(dialog, bg="#202020")
        row2.pack(fill="x", padx=16, pady=4)
        tk.Label(row2, text="Orientación", bg="#202020", fg="white").pack(side="left")
        ttk.Combobox(row2, textvariable=orient_var, values=("horizontal", "vertical"),
                     state="readonly", width=12).pack(side="left", padx=10)

        color = {"value": campo.text_style.color}

        def choose_color():
            rgb, _ = colorchooser.askcolor(
                initialcolor="#%02x%02x%02x" % (
                    color["value"].r, color["value"].g, color["value"].b
                ),
                parent=dialog,
            )
            if rgb:
                color["value"] = Color(int(rgb[0]), int(rgb[1]), int(rgb[2]))
                color_button.config(
                    bg="#%02x%02x%02x" % (
                        color["value"].r, color["value"].g, color["value"].b
                    )
                )

        tk.Label(dialog, text="Color", bg="#202020", fg="white").pack(anchor="w", padx=16, pady=(8, 2))
        color_button = tk.Button(
            dialog, text="Seleccionar color", command=choose_color,
            bg="#%02x%02x%02x" % (color["value"].r, color["value"].g, color["value"].b),
            fg="white", relief="flat"
        )
        color_button.pack(anchor="w", padx=16)

        p = campo.position
        geometry_frame = tk.LabelFrame(dialog, text="Área del campo (px)", bg="#202020", fg="white")
        geometry_frame.pack(fill="x", padx=16, pady=12)
        vars_geo = {}
        for nombre, valor in (("X", p.x), ("Y", p.y), ("Ancho", p.width), ("Alto", p.height)):
            line = tk.Frame(geometry_frame, bg="#202020")
            line.pack(side="left", padx=6, pady=8)
            tk.Label(line, text=nombre, bg="#202020", fg="white").pack()
            var = tk.StringVar(value=str(valor))
            vars_geo[nombre] = var
            tk.Entry(line, textvariable=var, width=7, bg="#303030", fg="white", insertbackground="white").pack()

        def aceptar():
            nuevo_id = id_var.get().strip()
            if not nuevo_id:
                messagebox.showwarning("Propiedades", "El ID no puede estar vacío.", parent=dialog)
                return
            if any(x is not campo and x.field_id == nuevo_id for x in self.formato.fields):
                messagebox.showwarning("Propiedades", "Ese ID ya existe.", parent=dialog)
                return
            try:
                size = int(size_var.get())
                x = int(vars_geo["X"].get())
                y = int(vars_geo["Y"].get())
                width = int(vars_geo["Ancho"].get())
                height = int(vars_geo["Alto"].get())
                if size <= 0 or width <= 0 or height <= 0:
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Propiedades", "Tamaño y área deben ser números positivos.", parent=dialog)
                return

            campo.field_id = nuevo_id
            campo.question = question.get("1.0", "end-1c").strip()
            campo.required = required_var.get()
            campo.uppercase = uppercase_var.get()
            familia_fuente = font_var.get().strip()
            campo.text_style.font_family = self._ruta_fuente_seleccionada(
                familia_fuente, bold_var.get(), italic_var.get()
            )
            campo.text_style.font_size_px = size
            campo.text_style.alignment = align_var.get()
            campo.text_style.orientation = orient_var.get()
            campo.text_style.bold = bold_var.get()
            campo.text_style.italic = italic_var.get()
            campo.text_style.color = color["value"]
            campo.position = Position(x, y, width, height)
            # Las propiedades cambiaron: regenerar ahora la caché comprimida.
            self._field_preview_cache.pop(campo.field_id, None)
            self._field_preview_cache[campo.field_id] = (
                self._field_preview_signature(campo),
                self._crear_preview_comprimido(campo),
            )

            if campo.field_type == FIELD_TYPE_NUMBER:
                campo.validation.numeric_only = True
                campo.validation.alphanumeric_only = False

            self.formato.ordenar_campos()
            self.unsaved = True
            dialog.destroy()
            self.redraw()
            self._refresh_field_list()
            if es_nuevo:
                self.set_tool(TOOL_HAND)

        def cancelar():
            if es_nuevo:
                self.formato.fields = [
                    item for item in self.formato.fields if item is not campo
                ]
                self.formato.ordenar_campos()
                if undo_antes is not None:
                    self._undo_stack = list(undo_antes)
                if redo_antes is not None:
                    self._redo_stack = list(redo_antes)
                self.selected_field = (
                    seleccionado_antes
                    if any(item is seleccionado_antes for item in self.formato.fields)
                    else None
                )
                if unsaved_antes is not None:
                    self.unsaved = unsaved_antes
                self.redraw()
                self._refresh_field_list()
                self._set_status("Creación de campo cancelada.")
            dialog.destroy()

        # Cerrar la ventana con la X tiene el mismo efecto que Cancelar.
        dialog.protocol("WM_DELETE_WINDOW", cancelar)
        buttons = tk.Frame(dialog, bg="#202020")
        buttons.pack(side="bottom", fill="x", padx=16, pady=16)
        tk.Button(buttons, text="Cancelar", command=cancelar,
                  bg="#303030", fg="white", relief="flat").pack(side="right", padx=4)
        tk.Button(buttons, text="OK", command=aceptar,
                  bg="#005f73", fg="white", relief="flat").pack(side="right", padx=4)

    def eliminar_seleccionado(self):
        if not self.formato or not self.selected_field:
            return
        campo = self.selected_field
        self._push_undo()
        self.formato.fields.remove(campo)
        self.formato.ordenar_campos()
        self.selected_field = None
        self.unsaved = True
        self._redraw_fields_only()
        self._refresh_field_list()
        self._set_status("Campo eliminado.")

    def _snapshot(self):
        import copy
        return copy.deepcopy(self.formato)

    def _push_undo(self):
        if self.formato is not None:
            self._undo_stack.append(self._snapshot())
            if len(self._undo_stack) > 50:
                self._undo_stack.pop(0)
            self._redo_stack.clear()

    def deshacer(self):
        if not self.formato or not self._undo_stack:
            return
        self._redo_stack.append(self._snapshot())
        self.formato = self._undo_stack.pop()
        self.selected_field = None
        self.unsaved = True
        self.redraw()
        self._refresh_field_list()
        self._set_status("Deshacer.")

    def rehacer(self):
        if not self.formato or not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self.formato = self._redo_stack.pop()
        self.selected_field = None
        self.unsaved = True
        self.redraw()
        self._refresh_field_list()
        self._set_status("Rehacer.")

    def cambiar_zoom(self, factor, event=None):
        self.set_zoom(self.zoom * factor, event=event)

    def set_zoom(self, value, event=None):
        if not self.template_image:
            return

        # Si el zoom viene del mouse, conservar bajo el cursor el mismo punto
        # de la imagen. Los controles de la barra usan el centro de la vista.
        if event is not None:
            anchor_x = self.canvas.canvasx(event.x)
            anchor_y = self.canvas.canvasy(event.y)
            screen_x, screen_y = event.x, event.y
        else:
            screen_x = max(1, self.canvas.winfo_width()) / 2
            screen_y = max(1, self.canvas.winfo_height()) / 2
            anchor_x = self.canvas.canvasx(screen_x)
            anchor_y = self.canvas.canvasy(screen_y)

        doc_x = (anchor_x - 20) / max(self.zoom, 0.01)
        doc_y = (anchor_y - 20) / max(self.zoom, 0.01)
        self.zoom = max(0.05, min(5.0, float(value)))
        self.redraw()
        self.canvas.update_idletasks()

        # Reubicar la vista para que ese punto de la plantilla permanezca
        # en las mismas coordenadas de pantalla tras el cambio de escala.
        target_x = max(0.0, 20 + doc_x * self.zoom - screen_x)
        target_y = max(0.0, 20 + doc_y * self.zoom - screen_y)
        region = self.canvas.cget("scrollregion").split()
        if len(region) == 4:
            region_w = max(1.0, float(region[2]) - float(region[0]))
            region_h = max(1.0, float(region[3]) - float(region[1]))
            self.canvas.xview_moveto(min(1.0, target_x / max(1.0, region_w)))
            self.canvas.yview_moveto(min(1.0, target_y / max(1.0, region_h)))

    def _update_zoom_label(self):
        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text="%d %%" % int(round(self.zoom * 100)))

    def on_mousewheel(self, event):
        # En touchpads de precisión, el pellizco suele llegar como rueda
        # con Ctrl; el desplazamiento con dos dedos llega como rueda normal.
        if self.tool == TOOL_ZOOM or (event.state & 0x0004):
            self.cambiar_zoom(1.15 if event.delta > 0 else 0.87, event=event)
            return

        # El desplazamiento horizontal de dos dedos suele exponerse como
        # Shift + rueda. Invertimos el desplazamiento de la vista para que
        # la plantilla se mueva en el sentido opuesto al gesto de los dedos.
        if event.state & 0x0001:
            unidades = max(1, int(abs(event.delta) / 120))
            self.canvas.xview_scroll(unidades if event.delta > 0 else -unidades, "units")
            return

        # Incluye touchpads que envían deltas pequeños, no múltiplos de 120.
        unidades = max(1, int(abs(event.delta) / 120))
        self.canvas.yview_scroll(-unidades if event.delta > 0 else unidades, "units")

    def on_ctrl_wheel(self, event):
        self.cambiar_zoom(1.15 if event.delta > 0 else 0.87, event=event)

    def on_right_down(self, event):
        if self.tool == TOOL_ZOOM and self.formato and self.template_image is not None:
            self.cambiar_zoom(0.87, event=event)

    def mostrar_mapa_atajos(self):
        titulo = "Mapa de atajos del configurador"
        contenido = """MAPA DE ATAJOS — CONFIGURADOR.EXE

Los atajos de letras funcionan con mayúsculas o minúsculas, y con Bloq Mayús activado o desactivado. Los atajos globales de esta lista actúan cuando la ventana principal está activa; no deben interferir con la escritura dentro de los cuadros de propiedades o de otros diálogos.

ARCHIVO
Ctrl+N        Nuevo formato. Inicia un formato nuevo; si hay cambios sin guardar, pregunta qué hacer.
Ctrl+O        Abrir un archivo FDT existente.
Ctrl+S        Guardar el FDT actual. Si todavía no tiene ruta, abre Guardar como.
Ctrl+Shift+S  Guardar como FDT con otro nombre o ubicación.
Ctrl+W        Cerrar la aplicación. Si hay cambios sin guardar, pregunta si desea guardarlos.
I             Importar una plantilla de imagen.

EDICIÓN
Ctrl+Z        Deshacer la última operación registrada.
Ctrl+Y        Rehacer una operación que se deshizo.
Delete        Eliminar el campo seleccionado. Para evitar borrar texto por accidente, funciona cuando el lienzo o la ventana principal tiene el foco.
Flechas       Mover el campo seleccionado 1 píxel por pulsación.
Ctrl+Flechas  Mover el campo seleccionado 5 píxeles por pulsación.
Shift+Flechas Mover el campo seleccionado 25 píxeles por pulsación.
Nota: selecciona primero el campo y asegúrate de que el lienzo tenga el foco. Ya no se necesita Alt para el ajuste fino.

HERRAMIENTAS
S             Activar Selección.
D             Activar Desplazar.
A             Activar Texto.
Q             Activar Número.
W             Activar Imagen.
Z             Activar Lupa.
L             Mostrar u ocultar la Lista de campos.
T             Abrir la configuración de Archivo terminado.

ZOOM
+             Acercar la vista (multiplica el zoom actual por 1,25).
-             Alejar la vista (multiplica el zoom actual por 0,8).
*             Restablecer el zoom al 100 %.
Rueda del ratón con la herramienta Lupa activa: acercar o alejar según la dirección de la rueda.
Ctrl+rueda    Acercar o alejar la vista.
Rueda normal  Desplazar verticalmente la vista.
Shift+rueda   Desplazar horizontalmente la vista.
Los botones − y + de la barra superior también alejan y acercan. La lupa admite clic izquierdo para acercar y clic derecho para alejar.

GESTOS DEL RATÓN
Clic en un campo con Selección: seleccionar ese campo.
Arrastrar un campo seleccionado: moverlo sobre la plantilla.
Arrastrar los controles de sus bordes o esquinas: cambiar su ancho y/o alto.
Doble clic en un campo con Selección: abrir sus propiedades.
Arrastrar sobre la plantilla con Texto, Número o Imagen: crear un campo nuevo con el tamaño dibujado.
Clic sin arrastrar con Texto, Número o Imagen: crear un campo con el tamaño del último campo, si existe; después se abren sus propiedades.
Arrastrar con Desplazar: mover la vista de la plantilla sin mover los campos.
Clic con Lupa: acercar un nivel. Clic derecho con Lupa: alejar un nivel.

CONSEJOS
• La vista previa de los campos es orientativa; no es el texto final que producirá el capturador.
• Las posiciones y dimensiones de los campos se expresan en píxeles de la plantilla, no en píxeles de pantalla.
• Guarda el formato en FDT después de hacer cambios.
• Para conocer una herramienta en detalle, abre Ayuda > Guía de herramientas y selecciona su nombre.
"""
        self._mostrar_ventana_ayuda(titulo, contenido, geometry="760x650")

    def mostrar_ayuda_herramienta(self, herramienta):
        guias = {
            TOOL_SELECT: (
                "Herramienta Selección (S)",
                """PARA QUÉ SIRVE
Selecciona campos ya creados para poder moverlos, cambiarles el tamaño, revisar sus propiedades o eliminarlos. Es la herramienta que debes usar para editar la distribución de los campos después de crearlos.

SELECCIONAR UN CAMPO
1. Activa Selección haciendo clic en su botón, desde Herramientas o pulsando S.
2. Haz clic dentro del rectángulo de un campo. El campo queda seleccionado y sus controles de ajuste aparecen en pantalla.
3. Si haces clic en una zona vacía de la plantilla, se quita la selección actual.

MOVER UN CAMPO CON EL RATÓN
1. Selecciona el campo.
2. Mantén presionado el botón izquierdo dentro del campo y arrástralo a la nueva posición.
3. Suelta el botón. El campo permanece dentro de los límites de la plantilla; no se desplaza fuera de ella.
El movimiento cambia las coordenadas del campo, no las dimensiones de la imagen plantilla.

MOVER UN CAMPO CON EL TECLADO
Selecciona el campo y asegúrate de que el lienzo tenga el foco:
• Flechas sin modificadores: 1 píxel por pulsación, para ajustes finos.
• Ctrl+Flechas: 5 píxeles por pulsación.
• Shift+Flechas: 25 píxeles por pulsación, para desplazamientos rápidos.
Las distancias se miden en píxeles de la plantilla, no en píxeles de pantalla. El movimiento queda limitado a los bordes de la plantilla.

CAMBIAR EL TAMAÑO
1. Selecciona el campo.
2. Localiza los pequeños controles de ajuste que aparecen en sus bordes o esquinas.
3. Arrastra el control correspondiente para modificar el ancho, el alto o ambos, según el control utilizado.
4. Suelta el ratón cuando el campo tenga el tamaño deseado.
El redimensionamiento cambia el área donde se captura o muestra la respuesta; no cambia el tamaño de la plantilla original. También puedes introducir X, Y, Ancho y Alto numéricamente en Propiedades del campo.

ABRIR LAS PROPIEDADES
Haz doble clic sobre el campo mientras Selección está activa, o selecciónalo y usa Editar > Propiedades del campo. En esa ventana puedes modificar:
• ID del campo, que debe ser único y no puede quedar vacío.
• Pregunta que verá el usuario en el capturador.
• Si la respuesta es obligatoria.
• Si la captura se convierte a MAYÚSCULAS.
• Tipografía, tamaño en píxeles, negrita, cursiva, alineación, orientación y color.
• Coordenadas X/Y y ancho/alto del campo.
• En campos de tipo Número, se aplica la validación numérica correspondiente.
Pulsa OK para aplicar los cambios. Pulsa Cancelar para descartar los cambios de esa ventana. Si estás creando un campo nuevo, cancelar elimina ese campo recién creado; si editas uno existente, cancelar conserva sus propiedades anteriores.

ORDEN DE LAS PREGUNTAS
La numeración de los campos determina el orden en que el capturador solicitará las respuestas. Usa la Lista de campos para revisar el orden y arrastra una fila hacia arriba o abajo para cambiarlo.

ELIMINAR
Selecciona el campo y pulsa Delete, o utiliza Editar > Eliminar campo. La eliminación modifica el formato y puede deshacerse con Ctrl+Z.

DESHACER Y REHACER
Ctrl+Z deshace una operación registrada; Ctrl+Y la vuelve a aplicar. El historial conserva hasta 50 estados. Guarda el FDT para conservar permanentemente los cambios."""
            ),
            TOOL_HAND: (
                "Herramienta Desplazar (D)",
                """PARA QUÉ SIRVE
Mueve la vista que estás viendo de la plantilla, sin mover ni redimensionar los campos del documento. Es útil cuando la plantilla es grande o está ampliada y quieres inspeccionar otra zona.

CÓMO SE UTILIZA
1. Activa Desplazar con el botón de la mano, desde Herramientas o pulsando D.
2. Coloca el puntero sobre la plantilla.
3. Mantén presionado el botón izquierdo y arrastra la vista en la dirección que necesites.
4. Suelta el botón para detener el desplazamiento.

DIFERENCIA CON SELECCIÓN
Desplazar cambia qué zona de la plantilla aparece en pantalla. No cambia las coordenadas de ningún campo. Para mover un campo real, activa Selección (S).

OTRAS FORMAS DE DESPLAZARSE
• La rueda del ratón desplaza verticalmente la vista.
• Shift+rueda desplaza horizontalmente la vista en los dispositivos compatibles.
• En touchpads, el gesto de dos dedos puede desplazar la vista.
• Ctrl+rueda cambia el zoom en lugar de desplazar verticalmente.

CUÁNDO USARLA
Úsala después de acercarte con la Lupa, cuando necesites revisar una esquina o zona de la plantilla que queda fuera de la pantalla. Tras aceptar o cancelar las propiedades de un campo recién creado, la herramienta Desplazar queda activada."""
            ),
            TOOL_TEXT: (
                "Herramienta Texto (A)",
                """PARA QUÉ SIRVE
Crea un campo destinado a una respuesta de texto. El usuario del capturador escribirá en ese campo la respuesta que corresponda al documento.

CREAR UN CAMPO
1. Activa Texto desde la barra, el menú Herramientas o pulsando A.
2. Coloca el puntero donde debe comenzar el área de respuesta.
3. Mantén presionado el botón izquierdo y arrastra para dibujar el rectángulo.
4. Suelta el botón. Se crea el campo y se abre automáticamente la ventana Propiedades del campo.

TAMAÑO DEL CAMPO
Al arrastrar, el rectángulo define el área en la plantilla y se convierte a coordenadas del documento. Si haces un clic sin arrastrar, el programa reutiliza el ancho y alto del último campo existente, cuando lo hay; puedes ajustar después esos valores en Propiedades.

CONFIGURAR LA PREGUNTA Y LA RESPUESTA
En Propiedades, escribe la pregunta que verá el usuario, configura si la respuesta es obligatoria y ajusta tipografía, tamaño, estilo, alineación, orientación, color y posición. El botón A/a permite decidir si el capturador convierte la respuesta a mayúsculas. El tipo Texto admite texto, números y símbolos; no está limitado a letras.

PREVIEW Y RESULTADO FINAL
El texto visible dentro del campo en el configurador es una muestra orientativa para identificar el área. No representa la respuesta real ni determina la calidad del texto final. El capturador utilizará las propiedades del campo y la respuesta escrita por el usuario.

CANCELAR
Si cancelas las propiedades de un campo recién creado, el campo se elimina. Si editas un campo existente y cancelas, se conservan los valores que tenía antes."""
            ),
            TOOL_NUMBER: (
                "Herramienta Número (Q)",
                """PARA QUÉ SIRVE
Crea un campo pensado para capturar un dato numérico, como una edad, cantidad, folio o número de identificación.

CÓMO CREARLO
1. Activa Número desde la barra, el menú Herramientas o pulsando Q.
2. Haz clic y arrastra sobre la zona de la plantilla donde debe aparecer el dato.
3. Suelta el botón para crear el rectángulo y abrir Propiedades.
4. Escribe una pregunta clara y configura el área, la tipografía y las demás propiedades necesarias.

TAMAÑO
Arrastrar define el ancho y el alto del campo. Un clic sin arrastrar reutiliza el tamaño del último campo existente cuando hay uno; luego puedes corregirlo en Propiedades.

VALIDACIÓN
Este tipo de campo aplica la validación numérica del formato. Si necesitas texto libre, letras o símbolos como contenido general, utiliza Texto (A) en lugar de Número.

PROPIEDADES COMUNES
Puedes establecer ID único, pregunta, obligatoriedad, conversión a mayúsculas cuando sea aplicable, tipografía, tamaño en píxeles, negrita, cursiva, alineación, orientación, color y coordenadas X/Y con ancho/alto.

EDICIÓN POSTERIOR
Activa Selección (S) para mover o redimensionar el campo. Haz doble clic sobre él para abrir sus propiedades. El preview del configurador es orientativo; la salida final la genera el capturador."""
            ),
            TOOL_IMAGE: (
                "Herramienta Imagen (W)",
                """PARA QUÉ SIRVE
Crea un rectángulo reservado para una imagen que el usuario seleccionará al capturar el formato. No inserta la fotografía definitiva en el FDT: define el lugar y el tamaño del área de imagen.

CÓMO CREAR EL ÁREA
1. Activa Imagen desde la barra, el menú Herramientas o pulsando W.
2. Haz clic y arrastra para dibujar el rectángulo donde debe quedar la imagen.
3. Suelta el botón. Se crea el campo y se abre Propiedades para asignarle su ID y pregunta, y ajustar su geometría.
4. Si haces clic sin arrastrar, se reutiliza el tamaño del último campo existente cuando lo hay.

QUÉ OCURRE EN EL CAPTURADOR
El capturador solicitará o permitirá seleccionar una imagen para ese campo y la ajustará al área definida, de acuerdo con el comportamiento de colocación de imágenes de la aplicación. El rectángulo no debe salirse del documento. El campo de imagen no necesita una muestra de texto como los campos de texto o número.

AJUSTAR O MOVER
Usa Selección (S), arrastra el campo para cambiar su posición o arrastra sus controles para cambiar ancho y alto. También puedes escribir X, Y, Ancho y Alto en Propiedades.

IMPORTANTE
La herramienta Imagen define el área de destino; no cambia las dimensiones ni la resolución de la plantilla original."""
            ),
            TOOL_ZOOM: (
                "Herramienta Lupa (Z)",
                """PARA QUÉ SIRVE
Acerca o aleja la visualización de la plantilla para inspeccionar detalles y colocar campos con mayor precisión. El zoom solo cambia la vista en pantalla: no modifica las dimensiones ni los metadatos de la imagen plantilla.

ACERCAR
1. Activa Lupa desde la barra, el menú Herramientas o pulsando Z.
2. Haz clic con el botón izquierdo sobre la plantilla para acercar la vista.
3. También puedes usar la rueda del ratón mientras Lupa está activa.

ALEJAR
Haz clic con el botón derecho sobre la plantilla mientras Lupa está activa, o utiliza la rueda en sentido contrario. Los botones − y + de la barra superior también permiten alejar y acercar.

ATAJOS
• + aumenta el zoom multiplicándolo por 1,25.
• - lo reduce multiplicándolo por 0,8.
• * devuelve el zoom al 100 %.
• Ctrl+rueda también acerca o aleja.
El zoom se limita al intervalo del 5 % al 500 %.

MOVERSE CON LA VISTA AMPLIADA
Después de acercar, activa Desplazar (D) y arrastra para inspeccionar otras partes de la plantilla. No uses Selección para arrastrar si tu intención es mover el campo en sí.

CALIDAD Y ARCHIVO
La vista ampliada puede verse pixelada intencionalmente. La operación de zoom no cambia la imagen fuente guardada dentro del FDT ni la calidad de la salida final del capturador."""
            ),
            "field_list": (
                "Lista de campos (L)",
                """PARA QUÉ SIRVE
Muestra los campos del formato en el orden en que se han registrado. Cada fila identifica el orden, el ID y la pregunta del campo.

MOSTRAR U OCULTAR
Pulsa L o abre Herramientas > Lista de campos. La lista puede cerrarse con el botón de cierre de su encabezado.

SELECCIONAR Y EDITAR
Haz clic en una fila para seleccionar el campo correspondiente en la plantilla. Haz doble clic en una fila para abrir sus propiedades.

REORDENAR PREGUNTAS
Mantén presionado el botón izquierdo sobre una fila, arrástrala hacia la posición deseada y suelta. La lista cambia el orden de los campos y, por tanto, el orden en que el capturador solicita las respuestas.

TAMAÑO Y POSICIÓN DEL PANEL
El panel puede moverse arrastrando su encabezado y cambiar de tamaño desde el borde de ajuste. Si necesitas más espacio para revisar la plantilla, puedes ocultarlo y volverlo a abrir cuando lo necesites."""
            ),
            "output_naming": (
                "Archivo terminado (T)",
                """PARA QUÉ SIRVE
Configura cómo se construirá el nombre del archivo final cuando el capturador guarde un documento completado. Puedes combinar un texto fijo con valores obtenidos de las respuestas capturadas.

CÓMO ABRIRLO
Pulsa T o ve a Herramientas > Archivo terminado. Debe haber una plantilla/formato cargado; si no lo hay, el programa mostrará un aviso.

NOMBRE BASE DEL ARCHIVO
En “Nombre base del archivo” escribe el texto fijo que quieras incluir en el nombre. Puede servir, por ejemplo, para identificar el tipo de documento o el trámite. El texto se conserva como parte de la configuración del formato.

INCORPORAR RESPUESTAS AL NOMBRE
Hay cuatro partes opcionales que pueden añadirse al nombre:
1. En cada selector, elige <nada> si no quieres añadir nada en esa posición.
2. O elige uno de los campos de la lista. Se muestran su orden, ID y pregunta para ayudarte a identificarlo.
3. Puedes combinar hasta cuatro campos en el orden deseado. Los valores seleccionados se usarán para formar el nombre final junto al texto base.
4. Si no necesitas una parte, déjala en <nada>. No es obligatorio utilizar las cuatro.

GUARDAR LOS CAMBIOS
Pulsa el botón de aceptación de la ventana para aplicar la configuración al formato. La operación marca el FDT como modificado; después guarda el formato con Ctrl+S o desde Archivo > Guardar para conservarla.

IMPORTANTE
Esta ventana configura el nombre del archivo resultante; no modifica el nombre del archivo FDT que estás editando ni cambia las dimensiones de la plantilla."""
            ),
        }
        if herramienta not in guias:
            return
        titulo, contenido = guias[herramienta]
        self._mostrar_ventana_ayuda(titulo, contenido, geometry="760x600")

    def _mostrar_ventana_ayuda(self, titulo, contenido, geometry="760x600"):
        ventana = tk.Toplevel(self.root)
        ventana.title(titulo)
        ventana.configure(bg="#202020")
        ventana.transient(self.root)
        ventana.geometry(geometry)
        ventana.minsize(560, 400)

        contenedor = tk.Frame(ventana, bg="#202020")
        contenedor.pack(fill="both", expand=True, padx=12, pady=12)
        barra = tk.Scrollbar(contenedor)
        barra.pack(side="right", fill="y")
        texto = tk.Text(
            contenedor, wrap="word", yscrollcommand=barra.set,
            bg="#181818", fg="#eeeeee", insertbackground="white",
            font=("Segoe UI", 10), padx=12, pady=10, spacing1=2,
            spacing3=5, relief="flat", borderwidth=0,
        )
        texto.pack(side="left", fill="both", expand=True)
        barra.config(command=texto.yview)
        texto.insert("1.0", contenido)
        texto.config(state="disabled")
        boton = tk.Button(
            ventana, text="Cerrar", command=ventana.destroy,
            bg="#005f73", fg="white", activebackground="#087f8c",
            relief="flat", padx=18, pady=5,
        )
        boton.pack(side="bottom", pady=(0, 12))
        ventana.bind("<Escape>", lambda event: ventana.destroy())
        ventana.bind("<Control-w>", lambda event: ventana.destroy())
        ventana.bind("<Control-W>", lambda event: ventana.destroy())
        ventana.focus_set()

    def _confirm_unsaved(self):
        if not self.unsaved:
            return True
        respuesta = messagebox.askyesnocancel(
            "Cambios sin guardar",
            "Hay cambios sin guardar. ¿Desea guardarlos?"
        )
        if respuesta is None:
            return False
        if respuesta:
            return bool(self.guardar())
        return True

    def salir(self):
        if self._confirm_unsaved():
            self.root.destroy()


def main():
    root = tk.Tk()
    app = Configurador(root)
    root.protocol("WM_DELETE_WINDOW", app.salir)
    root.mainloop()


if __name__ == "__main__":
    main()
