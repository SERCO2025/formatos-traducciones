# -*- coding: utf-8 -*-
import os
import tempfile
import tkinter as tk
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
        self.root.geometry("1100x700")
        self.root.minsize(850, 560)

        self.formato = None
        self.respuestas = {}
        self.indice = 0
        self._preview_after_id = None
        self._preview_photo = None
        self._final_preview_photo = None

        self._crear_interfaz()
        self._mostrar_inicio()

    def _crear_interfaz(self):
        principal = tk.Frame(self.root, bg="#202020")
        principal.pack(fill="both", expand=True)

        encabezado = tk.Frame(principal, bg="#202020")
        encabezado.pack(fill="x", padx=24, pady=(18, 8))

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
        controles.pack(fill="x", padx=24, pady=(4, 18))

        self.btn_abrir = ttk.Button(
            controles, text="Abrir formato", command=self.abrir_formato
        )
        self.btn_abrir.pack(side="left")

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
        self.respuestas = {campo.field_id: "" for campo in formato.fields}
        self.indice = 0
        self.titulo.config(text=formato.name)
        self._mostrar_campo()

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
            self.preview_label.config(image="", text="Vista previa no disponible")
            self._preview_photo = None
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

        etiqueta = tk.Label(area, bg="#101010")
        etiqueta.pack(fill="both", expand=True)

        def mostrar():
            ancho = max(300, etiqueta.winfo_width() - 20)
            alto = max(300, etiqueta.winfo_height() - 20)
            copia = imagen.copy()
            copia.thumbnail((ancho, alto), Image.Resampling.LANCZOS)
            foto = ImageTk.PhotoImage(copia)
            self._final_preview_photo = foto
            etiqueta.config(image=foto)

        etiqueta.bind("<Configure>", lambda event: mostrar())
        dialog.after(100, mostrar)

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
        carpeta = filedialog.askdirectory(title="Seleccione la carpeta donde guardar el archivo")
        if not carpeta:
            return

        salida = Path(carpeta) / nombre
        if salida.exists():
            if not messagebox.askyesno(
                "Confirmar reemplazo",
                "El archivo ya existe. ¿Desea reemplazarlo?",
                parent=dialog,
            ):
                return

        try:
            renderizar_formato(self.formato, self.respuestas, salida)
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
