# -*- coding: utf-8 -*-
import io
import importlib
import importlib.util
import sys
import unittest
import warnings
import zipfile

from shared.ftc import normalizar_ruta_imagen_ftc, validar_entradas_ftc
from shared.fdt import validar_fdt
from shared.models import Field, Formato, Position, TemplateInfo


ANDROID_SHARED = __import__("pathlib").Path(__file__).resolve().parents[1] / "android" / "capturador" / "shared"
ANDROID_SPEC = importlib.util.spec_from_file_location(
    "android_shared",
    str(ANDROID_SHARED / "__init__.py"),
    submodule_search_locations=[str(ANDROID_SHARED)],
)
ANDROID_PACKAGE = importlib.util.module_from_spec(ANDROID_SPEC)
sys.modules["android_shared"] = ANDROID_PACKAGE
ANDROID_SPEC.loader.exec_module(ANDROID_PACKAGE)
ANDROID_FDT = importlib.import_module("android_shared.fdt")
ANDROID_MODELS = importlib.import_module("android_shared.models")


class ValidacionFTC(unittest.TestCase):
    def test_normaliza_separadores_windows(self):
        self.assertEqual(
            normalizar_ruta_imagen_ftc(r"imagenes\\foto.jpg"),
            "imagenes/foto.jpg",
        )

    def test_rechaza_rutas_fuera_de_imagenes(self):
        for ruta in (
            "../foto.jpg",
            "imagenes/../foto.jpg",
            "imagenes\\..\\foto.jpg",
            "imagenes/C:/foto.jpg",
            "imagenes/C:foto.jpg",
            "imagenes/subcarpeta/foto.jpg",
            "otra_carpeta/foto.jpg",
        ):
            with self.subTest(ruta=ruta):
                with self.assertRaises(ValueError):
                    normalizar_ruta_imagen_ftc(ruta)

    def test_acepta_contenedor_minimo(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as paquete:
            paquete.writestr("formato.fdt", b"fdt")
            paquete.writestr("captura.json", b"{}")
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as paquete:
            self.assertEqual(
                validar_entradas_ftc(paquete),
                {"formato.fdt", "captura.json"},
            )

    def test_rechaza_contenedor_sin_archivos_estructurales(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as paquete:
            paquete.writestr("captura.json", b"{}")
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as paquete:
            with self.assertRaises(ValueError):
                validar_entradas_ftc(paquete)

    def test_rechaza_nombres_zip_duplicados(self):
        buffer = io.BytesIO()
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            with zipfile.ZipFile(buffer, "w") as paquete:
                paquete.writestr("formato.fdt", b"primero")
                paquete.writestr("formato.fdt", b"duplicado")
                paquete.writestr("captura.json", b"{}")
        buffer.seek(0)
        with zipfile.ZipFile(buffer, "r") as paquete:
            with self.assertRaises(ValueError):
                validar_entradas_ftc(paquete)


class ValidacionFDT(unittest.TestCase):
    def crear_formato(self, posicion):
        campo = Field(
            field_id="campo_1",
            question="Dato de prueba",
            order=1,
            position=posicion,
        )
        return Formato(
            name="Formato de prueba",
            template=TemplateInfo(
                path="plantilla.jpg",
                width=100,
                height=100,
                dpi=300,
                mode="RGB",
            ),
            fields=[campo],
        )

    def test_acepta_campo_dentro_de_plantilla(self):
        formato = self.crear_formato(Position(x=10, y=10, width=30, height=20))
        self.assertTrue(validar_fdt(formato))

    def test_rechaza_campo_fuera_de_plantilla(self):
        formato = self.crear_formato(Position(x=90, y=10, width=20, height=20))
        with self.assertRaises(ValueError):
            validar_fdt(formato)

    def test_rechaza_area_de_campo_cero(self):
        formato = self.crear_formato(Position(x=10, y=10, width=0, height=20))
        with self.assertRaises(ValueError):
            validar_fdt(formato)



class ValidacionFDTAndroid(unittest.TestCase):
    def crear_formato(self, posicion):
        campo = ANDROID_MODELS.Field(
            field_id="campo_1",
            question="Dato de prueba",
            order=1,
            position=posicion,
        )
        return ANDROID_MODELS.Formato(
            name="Formato de prueba",
            template=ANDROID_MODELS.TemplateInfo(
                path="plantilla.jpg",
                width=100,
                height=100,
                dpi=300,
                mode="RGB",
            ),
            fields=[campo],
        )

    def test_acepta_campo_dentro_de_plantilla(self):
        formato = self.crear_formato(
            ANDROID_MODELS.Position(x=10, y=10, width=30, height=20)
        )
        self.assertTrue(ANDROID_FDT.validar_fdt(formato))

    def test_rechaza_campo_fuera_de_plantilla(self):
        formato = self.crear_formato(
            ANDROID_MODELS.Position(x=90, y=10, width=20, height=20)
        )
        with self.assertRaises(ValueError):
            ANDROID_FDT.validar_fdt(formato)

    def test_rechaza_area_de_campo_cero(self):
        formato = self.crear_formato(
            ANDROID_MODELS.Position(x=10, y=10, width=0, height=20)
        )
        with self.assertRaises(ValueError):
            ANDROID_FDT.validar_fdt(formato)


if __name__ == "__main__":
    unittest.main()
