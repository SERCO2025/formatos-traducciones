# -*- coding: utf-8 -*-
import os
import re
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageDraw, ImageFont, ImageTk

from shared.fdt import guardar_fdt, validar_fdt
from shared.models import (
    FIELD_TYPE_ALPHANUMERIC,
    FIELD_TYPE_IMAGE,
    FIELD_TYPE_NUMBER,
    FIELD_TYPE_TEXT,
    Color,
    Field,
    Formato,
    Position,
    TemplateInfo,
    TextStyle,
)


TOOL_SELECT = "select"
TOOL_TEXT = FIELD_TYPE_TEXT
TOOL_NUMBER = FIELD_TYPE_NUMBER
TOOL_ALPHANUMERIC = FIELD_TYPE_ALPHANUMERIC
TOOL_IMAGE = FIELD_TYPE_IMAGE
TOOL_ZOOM = "zoom"
TOOL_HAND = "hand"


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
        self._field_drag_index = None
        self.field_panel_visible = False
        self.toolbar_dock_side = "top"
        self.field_dock_side = "right"

        self._build_ui()
        self._set_status("Listo. Importe una plantilla para comenzar.")

    def _build_ui(self):
        menubar = tk.Menu(self.root)
        archivo = tk.Menu(menubar, tearoff=0)
        archivo.add_command(label="Nuevo", command=self.nuevo)
        archivo.add_command(label="Abrir...", command=self.abrir)
        archivo.add_command(label="Guardar", command=self.guardar)
        archivo.add_command(label="Guardar como FDT...", command=self.guardar_como_fdt)
        archivo.add_separator()
        archivo.add_command(label="Importar plantilla...", command=self.importar_plantilla)
        archivo.add_separator()
        archivo.add_command(label="Salir", command=self.salir)
        menubar.add_cascade(label="Archivo", menu=archivo)

        editar = tk.Menu(menubar, tearoff=0)
        editar.add_command(label="Deshacer", command=self.deshacer, accelerator="Ctrl+Z")
        editar.add_command(label="Rehacer", command=self.rehacer, accelerator="Ctrl+Y")
        editar.add_separator()
        editar.add_command(label="Eliminar campo", command=self.eliminar_seleccionado)
        editar.add_command(label="Propiedades del campo", command=self.editar_seleccionado)
        menubar.add_cascade(label="Editar", menu=editar)

        ver = tk.Menu(menubar, tearoff=0)
        ver.add_command(label="Acercar", command=lambda: self.cambiar_zoom(1.25))
        ver.add_command(label="Alejar", command=lambda: self.cambiar_zoom(0.8))
        ver.add_command(label="100 %", command=lambda: self.set_zoom(1.0))
        menubar.add_cascade(label="Ver", menu=ver)

        herramientas = tk.Menu(menubar, tearoff=0)
        herramientas.add_command(label="Selección", command=lambda: self.set_tool(TOOL_SELECT))
        herramientas.add_command(label="Manita", command=lambda: self.set_tool(TOOL_HAND))
        herramientas.add_command(label="Texto (A)", command=lambda: self.set_tool(TOOL_TEXT))
        herramientas.add_command(label="Número (1)", command=lambda: self.set_tool(TOOL_NUMBER))
        herramientas.add_command(label="Alfanumérico (A1)", command=lambda: self.set_tool(TOOL_ALPHANUMERIC))
        herramientas.add_command(label="Imagen", command=lambda: self.set_tool(TOOL_IMAGE))
        herramientas.add_command(label="Lupa", command=lambda: self.set_tool(TOOL_ZOOM))
        herramientas.add_separator()
        herramientas.add_command(label="Lista de campos", command=self.toggle_field_panel)
        herramientas.add_command(label="Acoplar herramientas arriba", command=lambda: self._dock_toolbar("top"))
        herramientas.add_command(label="Acoplar herramientas abajo", command=lambda: self._dock_toolbar("bottom"))
        herramientas.add_command(label="Acoplar herramientas izquierda", command=lambda: self._dock_toolbar("left"))
        herramientas.add_command(label="Acoplar herramientas derecha", command=lambda: self._dock_toolbar("right"))
        menubar.add_cascade(label="Herramientas", menu=herramientas)

        ayuda = tk.Menu(menubar, tearoff=0)
        ayuda.add_command(label="Acerca de", command=lambda: messagebox.showinfo(
            "Acerca de", "Formatos Traducidos - Configurador"
        ))
        menubar.add_cascade(label="Ayuda", menu=ayuda)
        self.root.config(menu=menubar)

        self.toolbar_host = tk.Frame(self.root, bg="#171717", height=42)
        self.toolbar_host.pack(side="top", fill="x")

        grip = tk.Label(self.toolbar_host, text="⋮⋮", bg="#171717", fg="#888888",
                        font=("Arial", 11), cursor="fleur")
        grip.pack(side="left", padx=(4, 2))
        grip.bind("<ButtonPress-1>", self._dock_start)
        grip.bind("<B1-Motion>", self._dock_motion)
        grip.bind("<ButtonRelease-1>", self._dock_release)

        self._tool_buttons = []
        tools = [
            ("mouse-pointer", "Selección", TOOL_SELECT),
            ("hand-paper", "Manita", TOOL_HAND),
            ("font", "Texto", TOOL_TEXT),
            ("hashtag", "Número", TOOL_NUMBER),
            ("id-card", "Alfanumérico", TOOL_ALPHANUMERIC),
            ("image", "Imagen", TOOL_IMAGE),
            ("search-plus", "Lupa", TOOL_ZOOM),
        ]
        for icon, label, tool in tools:
            button = tk.Button(
                self.toolbar_host,
                image=self._icon_image(icon, 120),
                command=lambda t=tool: self.set_tool(t),
                bg="#262626", fg="white",
                activebackground="#444444", activeforeground="white",
                relief="flat", width=20, height=20, padx=14, pady=14, bd=0,
            )
            button._icon_ref = self._icon_images.get((icon, 120))
            button.pack(side="left", padx=2, pady=5)
            self._tool_buttons.append(button)
            button.bind("<Enter>", lambda e, l=label: self._set_status(l))
            button.bind("<Leave>", lambda e: self._set_status("Herramienta: " + self.tool))

        zoom_frame = tk.Frame(self.toolbar_host, bg="#171717")
        zoom_frame.pack(side="right", padx=6)
        for icon, command in (
            ("minus", lambda: self.cambiar_zoom(0.8)),
            ("plus", lambda: self.cambiar_zoom(1.25)),
        ):
            b = tk.Button(zoom_frame, image=self._icon_image(icon, 104), command=command,
                          bg="#262626", fg="white", relief="flat", bd=0,
                          width=20, height=20, padx=14, pady=14)
            b._icon_ref = self._icon_images.get((icon, 104))
            b.pack(side="left", padx=2, pady=4)
        self.zoom_label = tk.Label(zoom_frame, text="100 %", bg="#171717", fg="white", width=6)
        self.zoom_label.pack(side="left", padx=2)

        body = tk.Frame(self.root, bg="black")
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            body, bg="black", highlightthickness=0,
            scrollregion=(0, 0, 0, 0)
        )

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

        self.field_dock.grid_remove()
        self.field_panel_visible = False
        self.vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=0)
        body.columnconfigure(2, weight=0)
        body.rowconfigure(0, weight=1)

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

    def _icon_image(self, nombre, size=15):
        clave = (nombre, size)
        if clave in self._icon_images:
            return self._icon_images[clave]
        mapa = {
            "mouse-pointer": 0xF245, "hand-paper": 0xF256, "font": 0xF031,
            "hashtag": 0xF292, "id-card": 0xF2C2, "image": 0xF03E,
            "search-plus": 0xF00E, "minus": 0xF068, "plus": 0xF067,
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
        self._field_drag_index = self.field_list.nearest(event.y)

    def _field_list_motion(self, event):
        if self._field_drag_index is None or not self.formato:
            return
        nuevo = self.field_list.nearest(event.y)
        if nuevo < 0 or nuevo >= len(self.formato.fields) or nuevo == self._field_drag_index:
            return
        self._push_undo()
        campo = self.formato.fields.pop(self._field_drag_index)
        self.formato.fields.insert(nuevo, campo)
        self.formato.ordenar_campos()
        self._field_drag_index = nuevo
        self.unsaved = True
        self._refresh_field_list()
        self.field_list.selection_set(nuevo)
        self.redraw()

    def _field_list_release(self, event):
        self._field_drag_index = None
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

        self._refresh_field_list()

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

    def set_tool(self, tool):
        self.tool = tool
        if tool != TOOL_ZOOM:
            self._ocultar_lupa()
        self.canvas.config(cursor="crosshair" if tool == TOOL_ZOOM else "")
        self._set_status("Herramienta: " + tool)

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

    def abrir(self):
        ruta = filedialog.askopenfilename(
            title="Abrir formato o plantilla",
            filetypes=[
                ("Todos los archivos", "*.*"),
                ("Formato FDT", "*.fdt"),
                ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp *.tif *.tiff *.jfif"),
            ]
        )
        if not ruta:
            return
        if os.path.splitext(ruta)[1].lower() != ".fdt":
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
        except Exception as exc:
            messagebox.showerror("Error al abrir", str(exc))

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
        if self.template_image is None:
            return

        w = max(1, int(round(self.template_image.width * self.zoom)))
        h = max(1, int(round(self.template_image.height * self.zoom)))
        visible = self.template_image.resize((w, h), Image.Resampling.LANCZOS)
        self.template_tk = ImageTk.PhotoImage(visible)

        self.canvas_image_id = self.canvas.create_image(20, 20, image=self.template_tk, anchor="nw")
        self.canvas.configure(scrollregion=(0, 0, w + 40, h + 40))

        if self.formato:
            for campo in self.formato.fields:
                self._draw_field(campo)

        self._update_zoom_label()

    def _draw_field(self, campo):
        p = campo.position
        x1 = 20 + p.x * self.zoom
        y1 = 20 + p.y * self.zoom
        x2 = x1 + p.width * self.zoom
        y2 = y1 + p.height * self.zoom

        color = "#00d7ff" if campo is self.selected_field else "#ffcc00"
        rect = self.canvas.create_rectangle(
            x1, y1, x2, y2,
            outline="black", width=3,
            tags=("field", campo.field_id)
        )
        label = self.canvas.create_text(
            x1 + 4, y1 + 4,
            text="%d  %s" % (campo.order, campo.field_type),
            fill=color, anchor="nw",
            tags=("field", campo.field_id)
        )
        self.field_items[campo.field_id] = (rect, label)

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
        if not self.formato or self.template_image is None:
            return
        cx, cy = self._event_to_canvas(event)
        self._move_changed = False

        if self.tool == TOOL_ZOOM:
            self.cambiar_zoom(1.25)
            return
        if self.tool == TOOL_HAND:
            self._pan_last = (event.x, event.y)
            return
        if self.tool == TOOL_SELECT:
            campo = self._find_field_at(cx, cy)
            self.selected_field = campo
            if campo:
                self._move_start = (cx, cy)
                self._move_origin = (campo.position.x, campo.position.y)
                self.redraw()
            else:
                self._move_start = None
                self._move_origin = None
                self.redraw()
            return

        self.drag_start = self._canvas_to_document(cx, cy)
        self.drawing_rect = self.canvas.create_rectangle(
            cx, cy, cx, cy, outline="black", width=3
        )

    def on_mouse_move(self, event):
        cx, cy = self._event_to_canvas(event)
        if self.tool == TOOL_ZOOM:
            self._mostrar_lupa(event)
        elif self._magnifier_label is not None:
            self._ocultar_lupa()

        if self.tool == TOOL_HAND and self._pan_last is not None:
            dx = event.x - self._pan_last[0]
            dy = event.y - self._pan_last[1]
            self.canvas.xview_scroll(int(-dx / 2), "units")
            self.canvas.yview_scroll(int(-dy / 2), "units")
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
                self.redraw()
            return

        if self.drag_start is None or self.tool not in (TOOL_TEXT, TOOL_NUMBER, TOOL_ALPHANUMERIC, TOOL_IMAGE):
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
        if self.tool == TOOL_SELECT:
            if self._move_changed:
                self._move_changed = False
                self._set_status("Campo movido.")
            self._move_start = None
            self._move_origin = None
            return
        if self.drag_start is None:
            return
        if self.tool not in (TOOL_TEXT, TOOL_NUMBER, TOOL_ALPHANUMERIC, TOOL_IMAGE):
            self.drag_start = None
            return

        cx, cy = self._event_to_canvas(event)
        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_document(cx, cy)
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        width = max(1, right - left)
        height = max(1, bottom - top)

        if self.drawing_rect:
            self.canvas.delete(self.drawing_rect)
            self.drawing_rect = None
        self.drag_start = None

        self._push_undo()
        campo = Field(
            field_id=self._nuevo_id(),
            question="",
            field_type=self.tool,
            position=Position(left, top, width, height),
            text_style=TextStyle(
                font_family="", font_size_px=24, color=Color(0, 0, 0),
                alignment="left", bold=False, italic=False,
            ),
        )
        self.formato.agregar_campo(campo)
        self.selected_field = campo
        self.unsaved = True
        self.redraw()
        self._refresh_field_list()
        self.editar_seleccionado()

    def on_double_click(self, event):
        if self.tool != TOOL_SELECT or not self.formato:
            return
        cx, cy = self._event_to_canvas(event)
        campo = self._find_field_at(cx, cy)
        if campo:
            self.selected_field = campo
            self.editar_seleccionado()

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

    def _nuevo_id(self):
        base = "campo"
        usados = {campo.field_id for campo in self.formato.fields}
        numero = 1
        while base + str(numero) in usados:
            numero += 1
        return base + str(numero)

    def editar_seleccionado(self):
        if not self.selected_field:
            return

        campo = self.selected_field
        dialog = tk.Toplevel(self.root)
        dialog.title("Propiedades del campo %d" % campo.order)
        dialog.configure(bg="#202020")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.geometry("430x650")
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

        required_var = tk.BooleanVar(value=campo.required)
        tk.Checkbutton(dialog, text="Respuesta obligatoria", variable=required_var,
                       bg="#202020", fg="white", selectcolor="#303030",
                       activebackground="#202020", activeforeground="white").pack(anchor="w", padx=16, pady=8)

        label("Tipografía").pack(fill="x", padx=16, pady=(8, 2))
        font_names = list(self._font_inventory.keys())
        stored_font = campo.text_style.font_family or ""
        initial_family = stored_font
        for familia, datos in self._font_inventory.items():
            if stored_font in datos.values():
                initial_family = familia
                break
        font_var = tk.StringVar(value=initial_family)
        font_combo = ttk.Combobox(
            dialog, textvariable=font_var, values=font_names,
            state="readonly" if font_names else "normal", height=18
        )
        font_combo.pack(fill="x", padx=16)
        if not initial_family and font_names:
            font_combo.current(0)

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

            if campo.field_type == FIELD_TYPE_NUMBER:
                campo.validation.numeric_only = True
                campo.validation.alphanumeric_only = False
            elif campo.field_type == FIELD_TYPE_ALPHANUMERIC:
                campo.validation.numeric_only = False
                campo.validation.alphanumeric_only = True

            self.formato.ordenar_campos()
            self.unsaved = True
            dialog.destroy()
            self.redraw()
            self._refresh_field_list()

        buttons = tk.Frame(dialog, bg="#202020")
        buttons.pack(side="bottom", fill="x", padx=16, pady=16)
        tk.Button(buttons, text="Cancelar", command=dialog.destroy,
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
        self.redraw()
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

    def cambiar_zoom(self, factor):
        self.set_zoom(self.zoom * factor)

    def set_zoom(self, value):
        if not self.template_image:
            return
        self.zoom = max(0.05, min(5.0, float(value)))
        self.redraw()

    def _update_zoom_label(self):
        if hasattr(self, "zoom_label"):
            self.zoom_label.config(text="%d %%" % int(round(self.zoom * 100)))

    def on_mousewheel(self, event):
        if self.tool == TOOL_ZOOM or (event.state & 0x0004):
            self.cambiar_zoom(1.15 if event.delta > 0 else 0.87)
            return
        self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def on_ctrl_wheel(self, event):
        self.cambiar_zoom(1.15 if event.delta > 0 else 0.87)

    def on_right_down(self, event):
        if self.tool == TOOL_ZOOM and self.formato and self.template_image is not None:
            self.cambiar_zoom(0.87)

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
