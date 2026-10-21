# -*- coding: utf-8 -*-
import json
import os
import re
import tempfile
import time
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk

from shared.fdt import cargar_fdt
from shared.models import FIELD_TYPE_IMAGE
from shared.renderer import (
    construir_nombre_archivo,
    renderizar_formato,
    renderizar_imagen,
)
from shared.validators import validar_respuesta, validar_todas_las_respuestas


class CapturadorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Formatos Traducidos - Capturador")
        self.root.geometry("1100x660")
        self.root.minsize(850, 560)

        self.formato = None
        self.respuestas = {}
        self.indice = 0
        self._preview_after_id = None
        self._preview_photo = None
        self._final_preview_photo = None
        self._fdt_path = None
        self._draft_dirs = []
        self._output_folder = ""
        self._retention_days = 7
        self._auto_cleanup_enabled = True
        self._generated_files = {}
        base_config = Path(os.environ.get("APPDATA") or str(Path.home()))
        self._settings_dir = base_config / "FormatosTraducidos"
        self._settings_file = self._settings_dir / "capturador_settings.json"
        self._cargar_configuracion_salida()

        self._crear_interfaz()
        self._mostrar_inicio()
        self.root.after(1500, self._limpiar_archivos_vencidos)

    def _crear_interfaz(self):
        principal = tk.Frame(self.root, bg="#202020")
        principal.pack(fill="both", expand=True)

        encabezado = tk.Frame(principal, bg="#202020")
        encabezado.pack(fill="x", padx=24, pady=(18, 8))

        self.btn_salir = tk.Button(
            encabezado, text="Salir", command=self._confirmar_salida,
            bg="#8b0000", fg="white", activebackground="#b00000",
            activeforeground="white", font=("Segoe UI", 5, "bold"),
            relief="raised", bd=2, padx=11, pady=2,
        )
        self.btn_salir.pack(side="right", anchor="ne")

        self.btn_configuracion = ttk.Button(
            encabezado, text="Configuración", command=self._mostrar_configuracion
        )
        self.btn_configuracion.pack(side="right", padx=(0, 8), anchor="ne")

        self.titulo = tk.Label(
            encabezado,
            text="Formatos Traducidos",
            bg="#202020",
            fg="white",
            font=("Segoe UI", 20, "bold"),
        )
        self.titulo.pack(anchor="w")

        self.estado = tk.Label(
            encabezado,
            text="Seleccione un formato .fdt para comenzar.",
            bg="#202020",
            fg="#d0d0d0",
            font=("Segoe UI", 10),
        )
        self.estado.pack(anchor="w", pady=(4, 0))

        cuerpo = tk.Frame(principal, bg="#202020")
        cuerpo.pack(fill="both", expand=True, padx=24, pady=10)

        cuerpo.columnconfigure(0, weight=1)
        cuerpo.columnconfigure(1, weight=1)
        cuerpo.rowconfigure(0, weight=1)

        captura = tk.Frame(cuerpo, bg="#303030")
        captura.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        tk.Label(
            captura,
            text="Captura de datos",
            bg="#303030",
            fg="#d0d0d0",
            font=("Segoe UI", 10, "bold"),
        ).pack(anchor="w", padx=24, pady=(18, 4))

        self.pregunta = tk.Label(
            captura,
            text="",
            bg="#303030",
            fg="white",
            font=("Segoe UI", 16, "bold"),
            wraplength=470,
            justify="left",
        )
        self.pregunta.pack(anchor="w", padx=24, pady=(4, 14))

        self.entrada = tk.Text(
            captura,
            height=7,
            bg="#404040",
            fg="white",
            insertbackground="white",
            relief="flat",
            font=("Segoe UI", 13),
            wrap="word",
        )
        self.entrada.pack(fill="x", padx=24, pady=10)
        self.entrada.bind("<KeyRelease>", self._entrada_cambio)

        self.archivo_imagen = tk.Label(
            captura,
            text="",
            bg="#303030",
            fg="#d0d0d0",
            font=("Segoe UI", 10),
            wraplength=470,
            justify="left",
        )
        self.archivo_imagen.pack(anchor="w", padx=24, pady=(2, 8))

        vista = tk.Frame(cuerpo, bg="#181818")
        vista.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        vista.rowconfigure(1, weight=1)
        vista.columnconfigure(0, weight=1)

        tk.Label(
            vista,
            text="Vista previa del campo",
            bg="#181818",
            fg="#d0d0d0",
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, sticky="w", padx=12, pady=10)

        self.preview_label = tk.Label(
            vista,
            text="",
            bg="#101010",
            fg="#777777",
            anchor="center",
        )
        self.preview_label.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 10))
        self.preview_label.bind("<Configure>", lambda event: self._actualizar_preview())

        controles = tk.Frame(principal, bg="#202020")
        controles.pack(fill="x", padx=24, pady=(4, 30))

        self.btn_abrir = ttk.Button(
            controles, text="Abrir formato", command=self.abrir_formato
        )
        self.btn_abrir.pack(side="left")

        self.btn_abrir_avance = ttk.Button(
            controles, text="Abrir avance FTC", command=self.abrir_avance
        )
        self.btn_abrir_avance.pack(side="left", padx=8)

        self.btn_guardar_avance = ttk.Button(
            controles, text="Guardar avance FTC", command=self.guardar_avance,
            state="disabled",
        )
        self.btn_guardar_avance.pack(side="left", padx=4)

        self.btn_atras = ttk.Button(
            controles, text="Atrás", command=self.anterior, state="disabled"
        )
        self.btn_atras.pack(side="left", padx=8)

        self.btn_imagen = ttk.Button(
            controles, text="Seleccionar imagen", command=self.seleccionar_imagen
        )

        self.btn_siguiente = ttk.Button(
            controles, text="Continuar", command=self.siguiente, state="disabled"
        )
        self.btn_siguiente.pack(side="right")

        # El botón Salir está aislado en la esquina superior derecha.

    def _cargar_configuracion_salida(self):
        try:
            with open(self._settings_file, "r", encoding="utf-8") as archivo:
                datos = json.load(archivo) or {}
        except (OSError, ValueError, TypeError):
            datos = {}
        self._output_folder = str(datos.get("output_folder") or "")
        try:
            self._retention_days = max(1, min(365, int(datos.get("retention_days", 7))))
        except (TypeError, ValueError):
            self._retention_days = 7
        self._auto_cleanup_enabled = bool(datos.get("auto_cleanup_enabled", True))
        registros = datos.get("generated_files", {})
        self._generated_files = registros if isinstance(registros, dict) else {}

    def _guardar_configuracion_salida(self):
        self._settings_dir.mkdir(parents=True, exist_ok=True)
        datos = {
            "output_folder": self._output_folder,
            "retention_days": self._retention_days,
            "auto_cleanup_enabled": self._auto_cleanup_enabled,
            "generated_files": self._generated_files,
        }
        temporal = str(self._settings_file) + ".tmp"
        with open(temporal, "w", encoding="utf-8") as archivo:
            json.dump(datos, archivo, ensure_ascii=False, indent=2)
        os.replace(temporal, self._settings_file)

    def _mostrar_configuracion(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Configuración del capturador")
        dialog.configure(bg="#202020")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.geometry("590x330")
        dialog.grab_set()

        tk.Label(dialog, text="Carpeta de destino para los JPEG", bg="#202020", fg="white").pack(anchor="w", padx=16, pady=(16, 5))
        carpeta_var = tk.StringVar(value=self._output_folder)
        fila = tk.Frame(dialog, bg="#202020")
        fila.pack(fill="x", padx=16)
        ttk.Entry(fila, textvariable=carpeta_var).pack(side="left", fill="x", expand=True)

        def elegir_carpeta():
            seleccion = filedialog.askdirectory(title="Seleccione la carpeta de destino", parent=dialog, initialdir=carpeta_var.get() or str(Path.home()))
            if seleccion:
                carpeta_var.set(seleccion)
        ttk.Button(fila, text="Examinar...", command=elegir_carpeta).pack(side="left", padx=(6, 0))

        limpieza_var = tk.BooleanVar(value=self._auto_cleanup_enabled)
        ttk.Checkbutton(dialog, text="Activar limpieza automática de JPEG antiguos", variable=limpieza_var).pack(anchor="w", padx=16, pady=(18, 8))
        tk.Label(dialog, text="Días de conservación (1 a 365)", bg="#202020", fg="white").pack(anchor="w", padx=16)
        dias_var = tk.StringVar(value=str(self._retention_days))
        dias = ttk.Spinbox(dialog, from_=1, to=365, textvariable=dias_var, width=8)
        dias.pack(anchor="w", padx=16, pady=(4, 8))
        def estado_dias(*_):
            dias.configure(state="normal" if limpieza_var.get() else "disabled")
        limpieza_var.trace_add("write", estado_dias)
        estado_dias()
        tk.Label(dialog, text="Solo se eliminan JPEG generados por esta aplicación que sigan en la carpeta configurada.", bg="#202020", fg="#c8c8c8", wraplength=550, justify="left").pack(anchor="w", padx=16, pady=8)
        botones = tk.Frame(dialog, bg="#202020")
        botones.pack(fill="x", padx=16, pady=12)

        def guardar():
            carpeta = carpeta_var.get().strip()
            if not carpeta or not os.path.isdir(carpeta):
                messagebox.showwarning("Carpeta requerida", "Selecciona una carpeta de destino válida.", parent=dialog)
                return
            try:
                dias_nuevo = int(dias_var.get())
            except (TypeError, ValueError):
                dias_nuevo = 0
            if limpieza_var.get() and not 1 <= dias_nuevo <= 365:
                messagebox.showwarning("Días no válidos", "Indica un número entero entre 1 y 365.", parent=dialog)
                return
            self._output_folder = os.path.abspath(carpeta)
            if limpieza_var.get():
                self._retention_days = dias_nuevo
            self._auto_cleanup_enabled = bool(limpieza_var.get())
            self._guardar_configuracion_salida()
            dialog.destroy()
            if self._auto_cleanup_enabled:
                self._limpiar_archivos_vencidos()
            messagebox.showinfo("Configuración guardada", "Los ajustes se guardaron correctamente.")

        ttk.Button(botones, text="Cerrar", command=dialog.destroy).pack(side="left")
        ttk.Button(botones, text="Guardar ajustes", command=guardar).pack(side="right")

    def _registrar_jpeg_generado(self, ruta):
        ruta = os.path.abspath(str(ruta))
        self._generated_files[ruta] = {"created_at": time.time()}
        self._guardar_configuracion_salida()

    def _limpiar_archivos_vencidos(self):
        if not self._auto_cleanup_enabled or not self._output_folder or not os.path.isdir(self._output_folder):
            return
        carpeta = os.path.abspath(self._output_folder)
        ahora = time.time()
        cambios = False
        for registrada, datos in list(self._generated_files.items()):
            ruta = os.path.abspath(registrada)
            if os.path.dirname(ruta) != carpeta:
                self._generated_files.pop(registrada, None)
                cambios = True
                continue
            if not os.path.isfile(ruta):
                self._generated_files.pop(registrada, None)
                cambios = True
                continue
            if not ruta.lower().endswith((".jpg", ".jpeg")):
                continue
            try:
                creado = float(datos.get("created_at", ahora))
            except (TypeError, ValueError, AttributeError):
                creado = ahora
            if ahora - creado >= self._retention_days * 86400:
                try:
                    os.remove(ruta)
                    self._generated_files.pop(registrada, None)
                    cambios = True
                except OSError:
                    pass
        if cambios:
            self._guardar_configuracion_salida()

    def _confirmar_salida(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirmar salida")
        dialog.configure(bg="black")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.protocol("WM_DELETE_WINDOW", dialog.destroy)
        ancho, alto = 560, 300
        self.root.update_idletasks()
        x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - ancho) // 2)
        y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - alto) // 2)
        dialog.geometry("%dx%d+%d+%d" % (ancho, alto, x, y))

        tk.Label(
            dialog, text="Confirma para salir", bg="black", fg="#ffff00",
            font=("Segoe UI", 24, "bold"),
        ).pack(pady=(24, 10))
        tk.Label(
            dialog, text="Recuerda grabar los avances o se perdera toda la informacion capturada",
            bg="black", fg="white", font=("Segoe UI", 11), wraplength=510,
        ).pack(pady=(0, 8))
        tk.Label(
            dialog, text="para cerrar presione el boton rojo",
            bg="black", fg="white", font=("Segoe UI", 11),
        ).pack(pady=(0, 18))

        # Botón dibujado para lograr el degradado y el relieve 3D.
        boton = tk.Canvas(dialog, width=220, height=62, bg="black",
                          highlightthickness=0, bd=0, cursor="hand2")
        boton.pack()
        estado = {"presionado": False}

        def dibujar(presionado=False):
            boton.delete("all")
            desplazamiento = 4 if presionado else 0
            # Sombra exterior y bisel cambian de orientación al presionar.
            if presionado:
                boton.create_rectangle(8, 5, 212, 58, fill="#430000", outline="#300000", width=2)
                top, bottom = 9, 55
            else:
                boton.create_rectangle(8, 8, 212, 61, fill="#310000", outline="#220000", width=2)
                top, bottom = 4, 51
            colores = ["#ff5555", "#f04444", "#df2929", "#c91616", "#a90000", "#850000"]
            alto_banda = max(1, (bottom - top) // len(colores))
            for i, color in enumerate(colores):
                y1 = top + i * alto_banda
                y2 = bottom if i == len(colores) - 1 else top + (i + 1) * alto_banda
                boton.create_rectangle(12, y1, 208, y2, fill=color, outline=color)
            if not presionado:
                boton.create_line(14, top + 2, 206, top + 2, fill="#ffaaaa", width=2)
                boton.create_line(14, bottom - 1, 206, bottom - 1, fill="#690000", width=3)
            else:
                boton.create_line(14, top + 1, 206, top + 1, fill="#690000", width=3)
                boton.create_line(14, bottom - 1, 206, bottom - 1, fill="#ff7777", width=2)
            boton.create_text(110, (top + bottom) // 2, text="Salir",
                              fill="white", font=("Segoe UI", 18, "bold"))

        def presionar(event):
            estado["presionado"] = True
            dibujar(True)

        def soltar(event):
            estaba_dentro = 0 <= event.x <= 220 and 0 <= event.y <= 62
            estado["presionado"] = False
            dibujar(False)
            if estaba_dentro:
                dialog.destroy()
                self.root.destroy()

        boton.bind("<ButtonPress-1>", presionar)
        boton.bind("<ButtonRelease-1>", soltar)
        dibujar(False)
        dialog.grab_set()
        dialog.focus_force()

    def _mostrar_inicio(self):
        self.pregunta.config(text="Abra un formato .fdt para comenzar.")
        self.entrada.config(state="disabled")
        self.archivo_imagen.config(text="")
        self.btn_imagen.pack_forget()
        self.preview_label.config(image="", text="Vista previa")
        self._preview_photo = None

    def abrir_formato(self):
        ruta = filedialog.askopenfilename(
            title="Abrir formato",
            filetypes=[("Formato traducido", "*.fdt"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return

        try:
            formato = cargar_fdt(ruta)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo abrir el formato",
                "El archivo .fdt no pudo cargarse correctamente.\n\n%s" % exc,
            )
            return

        self.formato = formato
        self._fdt_path = os.path.abspath(ruta)
        self.respuestas = {campo.field_id: "" for campo in formato.fields}
        self.indice = 0
        self.titulo.config(text=formato.name)
        self.btn_guardar_avance.config(state="normal")
        self._mostrar_campo()

    def abrir_avance(self):
        ruta = filedialog.askopenfilename(
            title="Abrir avance de captura",
            filetypes=[("Avance de Formatos Traducidos", "*.ftc"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return

        directorio = None
        try:
            with zipfile.ZipFile(ruta, "r") as paquete:
                nombres = set(paquete.namelist())
                if "formato.fdt" not in nombres or "captura.json" not in nombres:
                    raise ValueError("El archivo no contiene formato.fdt y captura.json; no es un avance FTC válido.")

                directorio = tempfile.mkdtemp(prefix="formatos_traducidos_avance_")
                ruta_fdt = os.path.join(directorio, "formato.fdt")
                with open(ruta_fdt, "wb") as destino:
                    destino.write(paquete.read("formato.fdt"))

                ruta_json = os.path.join(directorio, "captura.json")
                with open(ruta_json, "wb") as destino:
                    destino.write(paquete.read("captura.json"))

                with open(ruta_json, "r", encoding="utf-8") as archivo:
                    datos = json.load(archivo)

                # Extraer únicamente imágenes declaradas en captura.json y dentro de
                # la carpeta interna "imagenes/", evitando rutas externas al avance.
                imagenes = datos.get("imagenes", {}) or {}
                for campo_id, interno in imagenes.items():
                    interno = str(interno).replace("\\\\", "/")
                    partes = interno.split("/")
                    if len(partes) != 2 or partes[0] != "imagenes" or partes[1] in ("", ".", ".."):
                        raise ValueError("El avance contiene una ruta de imagen no válida.")
                    if interno not in nombres:
                        continue
                    destino = os.path.join(directorio, "imagenes", partes[1])
                    os.makedirs(os.path.dirname(destino), exist_ok=True)
                    with open(destino, "wb") as archivo_imagen:
                        archivo_imagen.write(paquete.read(interno))

            formato = cargar_fdt(ruta_fdt)
            respuestas = {campo.field_id: "" for campo in formato.fields}
            respuestas.update(datos.get("respuestas", {}) or {})
            for campo_id, interno in (datos.get("imagenes", {}) or {}).items():
                ruta_imagen = os.path.join(directorio, *str(interno).replace("\\\\", "/").split("/"))
                if os.path.isfile(ruta_imagen):
                    respuestas[campo_id] = ruta_imagen

            self.formato = formato
            self._fdt_path = ruta_fdt
            self._draft_dirs.append(directorio)
            directorio = None
            self.respuestas = respuestas
            try:
                self.indice = max(0, min(int(datos.get("indice", 0)), len(formato.fields) - 1))
            except (TypeError, ValueError):
                self.indice = 0
            self.titulo.config(text=formato.name)
            self.btn_guardar_avance.config(state="normal")
            self._mostrar_campo()
            if formato.fields:
                messagebox.showinfo(
                    "Avance abierto",
                    "Se recuperaron las respuestas guardadas. Puedes continuar desde el campo %d de %d."
                    % (self.indice + 1, len(formato.fields)),
                )
        except Exception as exc:
            messagebox.showerror(
                "No se pudo abrir el avance",
                "El archivo FTC no pudo cargarse correctamente.\\n\\n%s" % exc,
            )
        finally:
            if directorio and os.path.isdir(directorio):
                import shutil
                shutil.rmtree(directorio, ignore_errors=True)

    def guardar_avance(self):
        if not self.formato or not self._fdt_path or not os.path.isfile(self._fdt_path):
            messagebox.showwarning(
                "Sin captura",
                "Primero abre un formato .FDT o un archivo de avance FTC.",
            )
            return

        # Como en Android, guardar un avance no exige completar ni validar todos
        # los campos; conserva también el texto que siga en el cuadro actual.
        if self.formato.fields:
            campo_actual = self.formato.fields[self.indice]
            if campo_actual.field_type != FIELD_TYPE_IMAGE:
                valor = self.entrada.get("1.0", "end-1c")
                if getattr(campo_actual, "uppercase", False):
                    valor = valor.upper()
                self.respuestas[campo_actual.field_id] = valor

        base = os.path.splitext(construir_nombre_archivo(self.formato, self.respuestas))[0]
        base = re.sub(r'[\\\\/:*?"<>|]+', "_", base).strip(" ._") or "captura_pendiente"
        ruta = filedialog.asksaveasfilename(
            title="Guardar avance de captura",
            defaultextension=".ftc",
            initialfile=base + ".ftc",
            filetypes=[("Avance de Formatos Traducidos", "*.ftc"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return
        if not ruta.lower().endswith(".ftc"):
            ruta += ".ftc"

        datos = {"version": 1, "indice": self.indice, "respuestas": {}, "imagenes": {}}
        try:
            with zipfile.ZipFile(ruta, "w", compression=zipfile.ZIP_DEFLATED) as paquete:
                paquete.write(self._fdt_path, "formato.fdt")
                for campo in self.formato.fields:
                    valor = self.respuestas.get(campo.field_id, "")
                    if campo.field_type == FIELD_TYPE_IMAGE and valor:
                        imagen_path = str(valor)
                        if os.path.isfile(imagen_path):
                            extension = os.path.splitext(imagen_path)[1].lower()
                            if extension not in (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"):
                                extension = ".jpg"
                            seguro = re.sub(r"[^A-Za-z0-9_-]+", "_", campo.field_id) or "imagen"
                            interno = "imagenes/%s%s" % (seguro, extension)
                            # Evitar que campos distintos con el mismo ID sanitizado
                            # colisionen al guardar sus imágenes.
                            if interno in datos["imagenes"].values():
                                interno = "imagenes/%s_%d%s" % (seguro, len(datos["imagenes"]), extension)
                            datos["imagenes"][campo.field_id] = interno
                            datos["respuestas"][campo.field_id] = ""
                            paquete.write(imagen_path, interno)
                        else:
                            datos["respuestas"][campo.field_id] = ""
                    else:
                        datos["respuestas"][campo.field_id] = "" if valor is None else str(valor)
                paquete.writestr(
                    "captura.json",
                    json.dumps(datos, ensure_ascii=False, indent=2).encode("utf-8"),
                )
            messagebox.showinfo(
                "Avance guardado",
                "La captura pendiente se guardó correctamente como:\\n%s\\n\\nPuedes abrirla después con «Abrir avance FTC»."
                % ruta,
            )
        except Exception as exc:
            messagebox.showerror(
                "No se pudo guardar el avance",
                "Ocurrió un error al guardar el archivo FTC.\\n\\n%s" % exc,
            )

    def _respuestas_para_preview(self):
        respuestas = dict(self.respuestas)
        if self.formato and self.formato.fields:
            campo = self.formato.fields[self.indice]
            if campo.field_type != FIELD_TYPE_IMAGE and self.entrada.cget("state") != "disabled":
                respuestas[campo.field_id] = self.entrada.get("1.0", "end-1c")
        return respuestas

    def _entrada_cambio(self, event=None):
        if self._preview_after_id is not None:
            try:
                self.root.after_cancel(self._preview_after_id)
            except Exception:
                pass
        self._preview_after_id = self.root.after(80, self._actualizar_preview)

    def _actualizar_preview(self):
        self._preview_after_id = None
        if not self.formato or not self.formato.fields:
            return
        try:
            imagen = renderizar_imagen(self.formato, self._respuestas_para_preview())
            campo = self.formato.fields[self.indice]
            p = campo.position
            margen = max(20, min(100, int(max(p.width, p.height) * 0.20)))
            izquierda = max(0, p.x - margen)
            arriba = max(0, p.y - margen)
            derecha = min(imagen.width, p.x + p.width + margen)
            abajo = min(imagen.height, p.y + p.height + margen)
            vista_campo = imagen.crop((izquierda, arriba, derecha, abajo))
            self._mostrar_imagen_en_label(
                self.preview_label,
                vista_campo,
                "_preview_photo",
            )
        except Exception as exc:
            # Conservar la última vista previa válida si ocurre un error temporal.
            self.estado.config(text="Vista previa: %s" % exc)

    def _mostrar_imagen_en_label(self, label, imagen, atributo):
        ancho = max(120, label.winfo_width() - 20)
        alto = max(120, label.winfo_height() - 20)
        copia = imagen.copy()
        copia.thumbnail((ancho, alto), Image.Resampling.LANCZOS)
        foto = ImageTk.PhotoImage(copia)
        setattr(self, atributo, foto)
        label.config(image=foto, text="")

    def _mostrar_campo(self):
        if not self.formato or not self.formato.fields:
            self.pregunta.config(text="El formato no contiene campos para capturar.")
            self.entrada.config(state="disabled")
            self.btn_siguiente.config(state="disabled")
            self.btn_atras.config(state="disabled")
            self.btn_imagen.pack_forget()
            return

        campo = self.formato.fields[self.indice]
        numero = self.indice + 1
        total = len(self.formato.fields)
        self.estado.config(text="Campo %d de %d" % (numero, total))

        texto_pregunta = campo.question.strip() or campo.field_id
        self.pregunta.config(text=texto_pregunta)

        self.entrada.config(state="normal")
        self.entrada.delete("1.0", "end")
        self.entrada.insert("1.0", self.respuestas.get(campo.field_id, ""))

        if campo.field_type == FIELD_TYPE_IMAGE:
            self.entrada.config(state="disabled")
            self.btn_imagen.pack(side="left", padx=8)
            ruta = self.respuestas.get(campo.field_id, "")
            self.archivo_imagen.config(
                text=("Imagen seleccionada: " + ruta)
                if ruta else "No se ha seleccionado imagen."
            )
        else:
            self.btn_imagen.pack_forget()
            self.archivo_imagen.config(text="")
            self.entrada.focus_set()

        self.btn_atras.config(
            state="normal" if self.indice > 0 else "disabled"
        )
        self.btn_siguiente.config(state="normal")
        self.btn_siguiente.config(
            text="Finalizar" if self.indice == total - 1 else "Continuar"
        )
        self._actualizar_preview()

    def _guardar_respuesta_actual(self):
        if not self.formato:
            return True

        campo = self.formato.fields[self.indice]
        if campo.field_type == FIELD_TYPE_IMAGE:
            return True

        respuesta = self.entrada.get("1.0", "end-1c")
        if getattr(campo, "uppercase", False):
            respuesta = respuesta.upper()
            self.entrada.delete("1.0", "end")
            self.entrada.insert("1.0", respuesta)
        valido, mensaje = validar_respuesta(campo, respuesta)

        if not valido:
            messagebox.showwarning("Respuesta no válida", mensaje)
            return False

        self.respuestas[campo.field_id] = respuesta
        return True

    def seleccionar_imagen(self):
        if not self.formato:
            return
        ruta = filedialog.askopenfilename(
            title="Seleccionar imagen",
            filetypes=[
                ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if ruta:
            self.respuestas[self.formato.fields[self.indice].field_id] = ruta
            self.archivo_imagen.config(text="Imagen seleccionada: " + ruta)
            self._actualizar_preview()

    def siguiente(self):
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
                    mensajes.append(
                        "%s: %s"
                        % (campo.question or campo.field_id, errores[campo.field_id])
                    )
            messagebox.showwarning("Revisar respuestas", "\n".join(mensajes))
            return

        self._mostrar_previsualizacion_final()

    def anterior(self):
        if not self.formato or self.indice <= 0:
            return

        if not self._guardar_respuesta_actual():
            return

        self.indice -= 1
        self._mostrar_campo()

    def _cargar_plantilla_si_es_necesario(self):
        plantilla = Path(self.formato.template.path)
        if plantilla.exists():
            return True

        messagebox.showwarning(
            "Plantilla no encontrada",
            "La plantilla indicada por el formato no se encuentra en este equipo.\n\n"
            "Seleccione la plantilla original para continuar.",
        )
        nueva = filedialog.askopenfilename(
            title="Seleccionar plantilla original",
            filetypes=[
                ("Imágenes", "*.jpg *.jpeg *.png *.bmp *.tif *.tiff"),
                ("Todos los archivos", "*.*"),
            ],
        )
        if not nueva:
            return False
        self.formato.template.path = nueva
        return True

    def _mostrar_previsualizacion_final(self):
        if not self._cargar_plantilla_si_es_necesario():
            return

        try:
            imagen = renderizar_imagen(self.formato, self.respuestas)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo generar la previsualización",
                "Ocurrió un error al generar el documento.\n\n%s" % exc,
            )
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Previsualización del archivo terminado")
        dialog.configure(bg="#202020")
        dialog.transient(self.root)
        dialog.geometry("1000x720")
        dialog.minsize(760, 560)

        area = tk.Frame(dialog, bg="#101010")
        area.pack(fill="both", expand=True, padx=12, pady=(12, 6))

        barra_y = tk.Scrollbar(area, orient="vertical")
        barra_x = tk.Scrollbar(area, orient="horizontal")
        vista = tk.Canvas(
            area, bg="#101010", highlightthickness=0,
            xscrollcommand=barra_x.set, yscrollcommand=barra_y.set,
        )
        barra_y.config(command=vista.yview)
        barra_x.config(command=vista.xview)
        barra_y.pack(side="right", fill="y")
        barra_x.pack(side="bottom", fill="x")
        vista.pack(side="left", fill="both", expand=True)

        foto_id = vista.create_image(0, 0, anchor="nw")
        zoom = {"valor": 1.0, "inicializado": False, "manual": False}

        def mostrar(event=None, factor=None, ajustar=False):
            ancho = max(1, vista.winfo_width() - 8)
            alto = max(1, vista.winfo_height() - 8)
            zoom_anterior = zoom["valor"]
            if not zoom["inicializado"] and (ancho <= 50 or alto <= 50):
                return
            if ajustar or not zoom["inicializado"]:
                zoom["valor"] = min(1.0, ancho / float(imagen.width), alto / float(imagen.height))
                zoom["inicializado"] = True
            elif factor is not None:
                zoom["valor"] = max(0.02, min(2.0, zoom["valor"] * factor))
                zoom["manual"] = True

            nuevo_ancho = max(1, int(round(imagen.width * zoom["valor"])))
            nuevo_alto = max(1, int(round(imagen.height * zoom["valor"])))
            copia = imagen.resize((nuevo_ancho, nuevo_alto), Image.Resampling.LANCZOS)
            foto = ImageTk.PhotoImage(copia)
            self._final_preview_photo = foto

            x = y = 0
            if event is not None and factor is not None:
                px = vista.canvasx(event.x)
                py = vista.canvasy(event.y)
                anterior_x, anterior_y = vista.coords(foto_id)
                proporcion = zoom["valor"] / zoom_anterior
                x = px - (px - anterior_x) * proporcion
                y = py - (py - anterior_y) * proporcion
            vista.itemconfigure(foto_id, image=foto)
            vista.coords(foto_id, x, y)
            vista.configure(scrollregion=(0, 0, max(ancho, x + nuevo_ancho), max(alto, y + nuevo_alto)))

        def actualizar_region():
            caja = vista.bbox(foto_id)
            if caja:
                ancho = max(1, vista.winfo_width() - 8)
                alto = max(1, vista.winfo_height() - 8)
                vista.configure(scrollregion=(
                    min(0, caja[0]), min(0, caja[1]),
                    max(ancho, caja[2]), max(alto, caja[3]),
                ))

        def rueda(event):
            mostrar(event=event, factor=1.15 if event.delta > 0 else 1 / 1.15)
            return "break"

        # Clic izquierdo sin arrastre: acercar. Arrastre izquierdo: desplazar.
        # Esto también admite touchpads que emiten eventos de arrastre de Tkinter.
        arrastre = {"x": 0, "y": 0, "imagen_x": 0, "imagen_y": 0, "movido": False}

        def iniciar_arrastre(event):
            arrastre["x"] = event.x
            arrastre["y"] = event.y
            arrastre["imagen_x"], arrastre["imagen_y"] = vista.coords(foto_id)
            arrastre["movido"] = False
            vista.configure(cursor="fleur")

        def mover_arrastre(event):
            dx = event.x - arrastre["x"]
            dy = event.y - arrastre["y"]
            if not arrastre["movido"] and (abs(dx) > 3 or abs(dy) > 3):
                arrastre["movido"] = True
            if arrastre["movido"]:
                vista.coords(
                    foto_id,
                    arrastre["imagen_x"] + dx,
                    arrastre["imagen_y"] + dy,
                )
                actualizar_region()

        def terminar_arrastre(event):
            vista.configure(cursor="")
            if not arrastre["movido"]:
                mostrar(event=event, factor=1.15)
            else:
                actualizar_region()
            return "break"

        def alejar(event):
            mostrar(event=event, factor=1 / 1.15)
            return "break"

        vista.bind("<Configure>", lambda event: mostrar(ajustar=not zoom["inicializado"]))
        vista.bind("<MouseWheel>", rueda)
        vista.bind("<Button-1>", iniciar_arrastre)
        vista.bind("<B1-Motion>", mover_arrastre)
        vista.bind("<ButtonRelease-1>", terminar_arrastre)
        vista.bind("<Button-3>", alejar)
        vista.bind("<Button-4>", lambda event: (mostrar(event=event, factor=1.15), "break")[1])
        vista.bind("<Button-5>", lambda event: (mostrar(event=event, factor=1 / 1.15), "break")[1])
        dialog.after(150, lambda: mostrar(ajustar=not zoom["inicializado"]))

        nombre = construir_nombre_archivo(self.formato, self.respuestas)
        papel, _ = self._seleccionar_papel(imagen)

        info = tk.Label(
            dialog,
            text="Nombre previsto: %s    |    Papel de impresión: %s" % (nombre, papel),
            bg="#202020", fg="#d0d0d0",
            anchor="w",
        )
        info.pack(fill="x", padx=12, pady=4)

        botones = tk.Frame(dialog, bg="#202020")
        botones.pack(fill="x", padx=12, pady=(4, 12))

        tk.Button(
            botones, text="Cerrar", command=dialog.destroy,
            bg="#303030", fg="white", relief="flat",
        ).pack(side="left")

        tk.Button(
            botones, text="Imprimir",
            command=lambda: self._imprimir(imagen),
            bg="#005f73", fg="white", relief="flat",
        ).pack(side="right", padx=4)

        tk.Button(
            botones, text="Guardar",
            command=lambda: self._guardar_desde_preview(imagen, nombre, dialog),
            bg="#005f73", fg="white", relief="flat",
        ).pack(side="right", padx=4)

    def _guardar_desde_preview(self, imagen, nombre, dialog):
        if not self._output_folder or not os.path.isdir(self._output_folder):
            messagebox.showwarning(
                "Configura la carpeta",
                "Antes de guardar, configura la carpeta de destino.",
                parent=dialog,
            )
            self._mostrar_configuracion()
            return

        salida = Path(self._output_folder) / nombre
        if salida.exists():
            if not messagebox.askyesno(
                "Confirmar reemplazo",
                "El archivo ya existe. ¿Desea reemplazarlo?",
                parent=dialog,
            ):
                return

        try:
            renderizar_formato(self.formato, self.respuestas, salida)
            self._registrar_jpeg_generado(salida)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo guardar",
                "Ocurrió un error al guardar el documento.\n\n%s" % exc,
                parent=dialog,
            )
            return

        messagebox.showinfo(
            "Archivo guardado",
            "El documento fue guardado correctamente como:\n\n%s" % salida,
            parent=dialog,
        )
        dialog.destroy()

    def _seleccionar_papel(self, imagen):
        dpi = float(self.formato.template.dpi or 300)
        ancho_px, alto_px = imagen.size

        carta = (round(8.5 * dpi), round(11 * dpi), "carta")
        oficio = (round(8.5 * dpi), round(14 * dpi), "oficio")

        opciones = []
        for pw, ph, nombre in (carta, oficio):
            for orientacion, page_w, page_h in (
                ("vertical", pw, ph),
                ("horizontal", ph, pw),
            ):
                escala = max(ancho_px / float(page_w), alto_px / float(page_h), 1.0)
                if escala <= 1.0:
                    sobrante = (page_w - ancho_px) + (page_h - alto_px)
                    puntaje = (0, sobrante)
                else:
                    puntaje = (1, escala)
                opciones.append((puntaje, nombre, page_w, page_h, orientacion))

        _, nombre, page_w, page_h, orientacion = min(opciones, key=lambda item: item[0])
        return nombre, (page_w, page_h, orientacion)

    def _crear_archivo_para_impresion(self, imagen):
        papel, datos = self._seleccionar_papel(imagen)
        page_w, page_h, _ = datos
        pagina = Image.new("RGB", (page_w, page_h), "white")

        escala = min(
            1.0,
            page_w / float(imagen.width),
            page_h / float(imagen.height),
        )
        if escala < 1.0:
            nuevo = (
                max(1, int(round(imagen.width * escala))),
                max(1, int(round(imagen.height * escala))),
            )
            imagen_impresa = imagen.resize(nuevo, Image.Resampling.LANCZOS)
        else:
            imagen_impresa = imagen

        x = max(0, (page_w - imagen_impresa.width) // 2)
        y = max(0, (page_h - imagen_impresa.height) // 2)
        pagina.paste(imagen_impresa, (x, y))

        ruta = Path(tempfile.gettempdir()) / (
            "formatos_traducidos_impresion_%s.jpg" % os.getpid()
        )
        pagina.save(
            ruta,
            format="JPEG",
            quality=100,
            subsampling=0,
            dpi=(self.formato.template.dpi, self.formato.template.dpi),
        )
        return papel, ruta

    def _imprimir(self, imagen):
        try:
            papel, ruta = self._crear_archivo_para_impresion(imagen)
        except Exception as exc:
            messagebox.showerror(
                "No se pudo preparar la impresión",
                "Ocurrió un error al preparar la hoja.\n\n%s" % exc,
            )
            return

        confirmar = messagebox.askokcancel(
            "Preparar impresión",
            'Asegúrese de que la impresora tenga hojas tamaño "%s".\n\n'
            "El formato será centrado en la hoja seleccionada."
            % papel,
        )
        if not confirmar:
            return

        try:
            if hasattr(os, "startfile"):
                os.startfile(str(ruta), "print")
            else:
                raise RuntimeError(
                    "La impresión directa está disponible en Windows."
                )
        except Exception as exc:
            messagebox.showerror(
                "No se pudo iniciar la impresión",
                "Windows no pudo enviar el archivo a la impresora.\n\n%s" % exc,
            )


def main():
    try:
        root = tk.Tk()
        app = CapturadorApp(root)
        root.mainloop()
    except Exception as exc:
        try:
            messagebox.showerror(
                "Error al iniciar el Capturador",
                "La aplicación no pudo iniciar correctamente.\n\n%s" % exc,
            )
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
