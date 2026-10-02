# -*- coding: utf-8 -*-
import os
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from shared.fdt import cargar_fdt
from shared.renderer import renderizar_formato
from shared.validators import validar_respuesta, validar_todas_las_respuestas
from shared.models import FIELD_TYPE_IMAGE


class CapturadorApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Formatos Traducidos - Capturador")
        self.root.geometry("760x480")
        self.root.minsize(620, 400)

        self.formato = None
        self.respuestas = {}
        self.indice = 0

        self._crear_interfaz()
        self._mostrar_inicio()

    def _crear_interfaz(self):
        principal = tk.Frame(self.root, bg="#202020")
        principal.pack(fill="both", expand=True)

        encabezado = tk.Frame(principal, bg="#202020")
        encabezado.pack(fill="x", padx=24, pady=(22, 10))

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
        cuerpo.pack(fill="both", expand=True, padx=24, pady=12)

        self.tarjeta = tk.Frame(cuerpo, bg="#303030", bd=0)
        self.tarjeta.pack(fill="both", expand=True)

        self.pregunta = tk.Label(
            self.tarjeta,
            text="",
            bg="#303030",
            fg="white",
            font=("Segoe UI", 16, "bold"),
            wraplength=680,
            justify="left",
        )
        self.pregunta.pack(anchor="w", padx=28, pady=(32, 14))

        self.entrada = tk.Text(
            self.tarjeta,
            height=6,
            bg="#404040",
            fg="white",
            insertbackground="white",
            relief="flat",
            font=("Segoe UI", 13),
            wrap="word",
        )
        self.entrada.pack(fill="x", padx=28, pady=10)

        self.archivo_imagen = tk.Label(
            self.tarjeta,
            text="",
            bg="#303030",
            fg="#d0d0d0",
            font=("Segoe UI", 10),
            wraplength=680,
        )
        self.archivo_imagen.pack(anchor="w", padx=28)

        controles = tk.Frame(principal, bg="#202020")
        controles.pack(fill="x", padx=24, pady=(4, 22))

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
                text=("Imagen seleccionada: " + ruta) if ruta else "No se ha seleccionado imagen."
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
                    mensajes.append("%s: %s" % (campo.question or campo.field_id, errores[campo.field_id]))
            messagebox.showwarning("Revisar respuestas", "\n".join(mensajes))
            return

        self._generar_resultado()

    def anterior(self):
        if not self.formato or self.indice <= 0:
            return

        if not self._guardar_respuesta_actual():
            return

        self.indice -= 1
        self._mostrar_campo()

    def _generar_resultado(self):
        plantilla = Path(self.formato.template.path)

        if not plantilla.exists():
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
                return
            self.formato.template.path = nueva

        salida = filedialog.asksaveasfilename(
            title="Guardar resultado",
            defaultextension=".jpg",
            filetypes=[("Imagen JPEG", "*.jpg")],
            initialfile="resultado.jpg",
        )
        if not salida:
            return

        try:
            resultado = renderizar_formato(
                self.formato,
                self.respuestas,
                salida,
            )
        except Exception as exc:
            messagebox.showerror(
                "No se pudo generar el resultado",
                "Ocurrió un error al generar el documento.\n\n%s" % exc,
            )
            return

        messagebox.showinfo(
            "Proceso terminado",
            "El documento fue generado correctamente.\n\n%s" % resultado,
        )


def main():
    root = tk.Tk()
    app = CapturadorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
