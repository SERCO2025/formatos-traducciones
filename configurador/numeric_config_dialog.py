# -*- coding: utf-8 -*-
"""Diálogo de configuración de los cuatro modos numéricos del configurador Windows."""

import tkinter as tk
from tkinter import messagebox, ttk

from shared.models import DATE_FORMATS, NumericConfig
from shared.validators import validar_configuracion_numerica


def editar_configuracion_numerica(parent, configuracion):
    """Abre el diálogo y devuelve una NumericConfig o None si se cancela."""
    if isinstance(configuracion, NumericConfig):
        inicial = NumericConfig.from_dict(configuracion.to_dict())
    else:
        inicial = NumericConfig()

    resultado = {"config": None}
    dialog = tk.Toplevel(parent)
    dialog.title("Configuración del campo numérico")
    dialog.configure(bg="#202020")
    dialog.transient(parent)
    dialog.resizable(False, False)
    dialog.geometry("440x390")

    def etiqueta(contenedor, texto):
        return tk.Label(
            contenedor, text=texto, bg="#202020", fg="white", anchor="w"
        )

    tk.Label(
        dialog, text="Modo de captura", bg="#202020", fg="white",
        anchor="w", font=("Arial", 10, "bold"),
    ).pack(fill="x", padx=18, pady=(18, 5))

    nombres = {
        "Número": "number",
        "Límite": "limit",
        "Fecha": "date",
        "Espaciado": "spacing",
    }
    nombres_inversos = {valor: clave for clave, valor in nombres.items()}
    modo_var = tk.StringVar(value=nombres_inversos.get(inicial.mode, "Número"))
    modo_combo = ttk.Combobox(
        dialog, textvariable=modo_var, values=tuple(nombres.keys()),
        state="readonly", width=24,
    )
    modo_combo.pack(fill="x", padx=18)

    opciones = tk.LabelFrame(
        dialog, text="Opciones del modo", bg="#202020", fg="white",
        padx=10, pady=10,
    )
    opciones.pack(fill="both", expand=True, padx=18, pady=14)

    valores = {
        "max_value": tk.StringVar(value=inicial.max_value),
        "date_format": tk.StringVar(value=inicial.date_format),
        "past_only": tk.BooleanVar(value=inicial.past_only),
        "min_year": tk.StringVar(value=inicial.min_year),
        "spacing_mask": tk.StringVar(value=inicial.spacing_mask),
        "spacing_required": tk.BooleanVar(value=inicial.spacing_required),
    }

    def solo_digitos(propuesto):
        return propuesto == "" or propuesto.isdigit()

    validar_digitos = (dialog.register(solo_digitos), "%P")

    def actualizar_opciones(*_):
        for widget in opciones.winfo_children():
            widget.destroy()

        modo = nombres.get(modo_var.get(), "number")

        if modo == "number":
            etiqueta(
                opciones,
                "Acepta números, espacios y símbolos; no permite letras.",
            ).pack(fill="x", pady=5)
            return

        if modo == "limit":
            etiqueta(
                opciones, "Cantidad máxima permitida (solo números):"
            ).pack(fill="x", pady=(3, 5))
            tk.Entry(
                opciones, textvariable=valores["max_value"],
                validate="key", validatecommand=validar_digitos,
                bg="#303030", fg="white", insertbackground="white",
            ).pack(fill="x")
            return

        if modo == "date":
            etiqueta(opciones, "Formato de fecha:").pack(
                fill="x", pady=(2, 5)
            )
            formato_combo = ttk.Combobox(
                opciones, textvariable=valores["date_format"],
                values=DATE_FORMATS, state="readonly",
            )
            formato_combo.pack(fill="x")
            tk.Checkbutton(
                opciones, text="Permitir únicamente fechas pasadas",
                variable=valores["past_only"], bg="#202020", fg="white",
                selectcolor="#303030", activebackground="#202020",
                activeforeground="white",
            ).pack(anchor="w", pady=(10, 5))

            fila_anio = tk.Frame(opciones, bg="#202020")
            etiqueta(fila_anio, "Año mínimo (solo números):").pack(
                fill="x", pady=(3, 4)
            )
            tk.Entry(
                fila_anio, textvariable=valores["min_year"],
                validate="key", validatecommand=validar_digitos,
                bg="#303030", fg="white", insertbackground="white",
            ).pack(fill="x")

            def actualizar_anio(*_):
                formato = valores["date_format"].get()
                if "aa" in formato:
                    if not fila_anio.winfo_manager():
                        fila_anio.pack(fill="x", pady=(5, 0))
                else:
                    fila_anio.pack_forget()

            formato_combo.bind("<<ComboboxSelected>>", actualizar_anio)
            actualizar_anio()
            return

        if modo == "spacing":
            etiqueta(
                opciones,
                "Máscara: usa # para cada posición numérica. "
                "Los separadores y textos literales van entre paréntesis.",
            ).pack(fill="x", pady=(2, 7))
            tk.Entry(
                opciones, textvariable=valores["spacing_mask"],
                bg="#303030", fg="white", insertbackground="white",
            ).pack(fill="x")
            tk.Checkbutton(
                opciones, text="Es obligatorio llenar todas las posiciones",
                variable=valores["spacing_required"], bg="#202020",
                fg="white", selectcolor="#303030",
                activebackground="#202020", activeforeground="white",
                wraplength=360, justify="left",
            ).pack(anchor="w", pady=(10, 2))

    modo_combo.bind("<<ComboboxSelected>>", actualizar_opciones)
    actualizar_opciones()

    botones = tk.Frame(dialog, bg="#202020")
    botones.pack(fill="x", padx=18, pady=(0, 16))

    def cancelar():
        resultado["config"] = None
        dialog.destroy()

    def aceptar():
        modo = nombres.get(modo_var.get(), "number")
        config = NumericConfig(
            mode=modo,
            max_value=valores["max_value"].get().strip(),
            date_format=valores["date_format"].get(),
            past_only=valores["past_only"].get(),
            min_year=valores["min_year"].get().strip(),
            spacing_mask=valores["spacing_mask"].get(),
            spacing_required=valores["spacing_required"].get(),
        )
        valido, mensaje = validar_configuracion_numerica(config)
        if not valido:
            messagebox.showwarning(
                "Configuración numérica", mensaje, parent=dialog
            )
            return
        resultado["config"] = config
        dialog.destroy()

    tk.Button(
        botones, text="Cancelar", command=cancelar,
        bg="#303030", fg="white", relief="flat",
    ).pack(side="right", padx=4)
    tk.Button(
        botones, text="Aceptar", command=aceptar,
        bg="#005f73", fg="white", relief="flat",
    ).pack(side="right", padx=4)

    dialog.protocol("WM_DELETE_WINDOW", cancelar)
    dialog.grab_set()
    dialog.wait_window()
    return resultado["config"]
