# -*- coding: utf-8 -*-
import os
import re
import tkinter as tk
from tkinter import colorchooser, filedialog, messagebox, simpledialog, ttk

from PIL import Image, ImageTk

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
        menubar.add_cascade(label="Herramientas", menu=herramientas)

        ayuda = tk.Menu(menubar, tearoff=0)
        ayuda.add_command(label="Acerca de", command=lambda: messagebox.showinfo(
            "Acerca de", "Formatos Traducidos - Configurador"
        ))
        menubar.add_cascade(label="Ayuda", menu=ayuda)
        self.root.config(menu=menubar)

        toolbar = tk.Frame(self.root, bg="#171717", height=52)
        toolbar.pack(side="top", fill="x")

        tools = [
            ("↖", "Selección", TOOL_SELECT),
            ("✋", "Manita", TOOL_HAND),
            ("A", "Texto", TOOL_TEXT),
            ("1", "Número", TOOL_NUMBER),
            ("A1", "Alfanumérico", TOOL_ALPHANUMERIC),
            ("IMG", "Imagen", TOOL_IMAGE),
            ("🔍", "Lupa", TOOL_ZOOM),
        ]
        for symbol, label, tool in tools:
            button = tk.Button(
                toolbar,
                text=symbol,
                command=lambda t=tool: self.set_tool(t),
                bg="#262626",
                fg="white",
                activebackground="#444444",
                activeforeground="white",
                relief="flat",
                width=7,
                height=2,
                font=("Arial", 18 if tool in (TOOL_SELECT, TOOL_HAND) else 11),
            )
            button.pack(side="left", padx=3, pady=5)
            button.bind("<Enter>", lambda e, b=button, l=label: self._set_status(l))
            button.bind("<Leave>", lambda e: self._set_status("Herramienta: " + self.tool))

        zoom_frame = tk.Frame(toolbar, bg="#171717")
        zoom_frame.pack(side="right", padx=8)
        tk.Button(zoom_frame, text="−", command=lambda: self.cambiar_zoom(0.8),
                  bg="#262626", fg="white", relief="flat", width=3).pack(side="left")
        self.zoom_label = tk.Label(zoom_frame, text="100 %", bg="#171717", fg="white", width=7)
        self.zoom_label.pack(side="left")
        tk.Button(zoom_frame, text="+", command=lambda: self.cambiar_zoom(1.25),
                  bg="#262626", fg="white", relief="flat", width=3).pack(side="left")

        body = tk.Frame(self.root, bg="black")
        body.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(
            body, bg="black", highlightthickness=0,
            scrollregion=(0, 0, 0, 0)
        )
        self.vbar = ttk.Scrollbar(body, orient="vertical", command=self.canvas.yview)
        self.hbar = ttk.Scrollbar(body, orient="horizontal", command=self.canvas.xview)
        self.canvas.configure(yscrollcommand=self.vbar.set, xscrollcommand=self.hbar.set)

        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.vbar.grid(row=0, column=1, sticky="ns")
        self.hbar.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)

        self.canvas.bind("<ButtonPress-1>", self.on_mouse_down)
        self.canvas.bind("<B1-Motion>", self.on_mouse_move)
        self.canvas.bind("<ButtonRelease-1>", self.on_mouse_up)
        self.canvas.bind("<MouseWheel>", self.on_mousewheel)
        self.canvas.bind("<Control-MouseWheel>", self.on_ctrl_wheel)
        self.canvas.bind("<ButtonPress-3>", self.on_right_down)
        self.root.bind_all("<Control-z>", lambda e: self.deshacer())
        self.root.bind_all("<Control-y>", lambda e: self.rehacer())

        status = tk.Frame(self.root, bg="#111111")
        status.pack(side="bottom", fill="x")
        self.status_label = tk.Label(status, text="", bg="#111111", fg="#dddddd", anchor="w")
        self.status_label.pack(fill="x", padx=8, pady=5)

    def _set_status(self, text):
        if hasattr(self, "status_label"):
            self.status_label.config(text=text)

    def set_tool(self, tool):
        self.tool = tool
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

    def importar_plantilla(self):
        ruta = filedialog.askopenfilename(
            title="Importar plantilla",
            filetypes=[("Imágenes", "*.jpg *.jpeg *.png *.bmp *.webp"), ("Todos", "*.*")]
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
            self.unsaved = True
            self._set_status(
                "Plantilla importada: %d × %d px" % (imagen.width, imagen.height)
            )
        except Exception as exc:
            messagebox.showerror("Error", "No se pudo importar la plantilla.\n%s" % exc)

    def abrir(self):
        ruta = filedialog.askopenfilename(
            title="Abrir formato",
            filetypes=[("Formato FDT", "*.fdt"), ("Todos", "*.*")]
        )
        if not ruta:
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
            outline=color, width=3,
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

        if self.tool == TOOL_ZOOM:
            self.cambiar_zoom(1.25)
            return

        if self.tool == TOOL_HAND:
            self._pan_last = (event.x, event.y)
            return

        if self.tool == TOOL_SELECT:
            campo = self._find_field_at(event.x, event.y)
            self.selected_field = campo
            if campo:
                self.editar_seleccionado()
            else:
                self.redraw()
            return

        self.drag_start = self._canvas_to_document(event.x, event.y)
        self.drawing_rect = None

    def on_mouse_move(self, event):
        if self.tool == TOOL_HAND and self._pan_last is not None:
            dx = event.x - self._pan_last[0]
            dy = event.y - self._pan_last[1]
            self.canvas.xview_scroll(int(-dx / 2), "units")
            self.canvas.yview_scroll(int(-dy / 2), "units")
            self._pan_last = (event.x, event.y)
            return
        if self.drag_start is None:
            return
        if self.tool not in (TOOL_TEXT, TOOL_NUMBER, TOOL_ALPHANUMERIC, TOOL_IMAGE):
            return

        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_document(event.x, event.y)
        left, right = sorted((x0, x1))
        top, bottom = sorted((y0, y1))
        if right == left:
            right += 1
        if bottom == top:
            bottom += 1

        if self.drawing_rect:
            self.canvas.delete(self.drawing_rect)

        self.drawing_rect = self.canvas.create_rectangle(
            20 + left * self.zoom,
            20 + top * self.zoom,
            20 + right * self.zoom,
            20 + bottom * self.zoom,
            outline="#00ff66",
            width=2,
            dash=(4, 2),
        )

    def on_mouse_up(self, event):
        if self.tool == TOOL_HAND:
            self._pan_last = None
            return
        if self.drag_start is None:
            return

        if self.tool not in (TOOL_TEXT, TOOL_NUMBER, TOOL_ALPHANUMERIC, TOOL_IMAGE):
            self.drag_start = None
            return

        x0, y0 = self.drag_start
        x1, y1 = self._canvas_to_document(event.x, event.y)
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
                font_family="",
                font_size_px=24,
                color=Color(0, 0, 0),
                alignment="left",
                bold=False,
                italic=False,
            ),
        )
        self.formato.agregar_campo(campo)
        self.selected_field = campo
        self.unsaved = True
        self.redraw()
        self.editar_seleccionado()

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

        font_frame = tk.Frame(dialog, bg="#202020")
        font_frame.pack(fill="x", padx=16, pady=4)

        label("Tipografía").pack(fill="x", padx=16, pady=(8, 2))
        font_var = tk.StringVar(value=campo.text_style.font_family)
        tk.Entry(dialog, textvariable=font_var, bg="#303030", fg="white", insertbackground="white").pack(fill="x", padx=16)

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
            campo.text_style.font_family = font_var.get().strip()
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
        self._set_status("Deshacer.")

    def rehacer(self):
        if not self.formato or not self._redo_stack:
            return
        self._undo_stack.append(self._snapshot())
        self.formato = self._redo_stack.pop()
        self.selected_field = None
        self.unsaved = True
        self.redraw()
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
