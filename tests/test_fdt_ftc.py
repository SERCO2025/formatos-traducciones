# -*- coding: utf-8 -*-
import io
import importlib
import importlib.util
import sys
import tempfile
import unittest
import warnings
import zipfile

from shared.ftc import (
    construir_ruta_imagen_ftc,
    filtrar_respuestas_ftc,
    normalizar_ruta_imagen_ftc,
    validar_campo_imagen_ftc,
    validar_entradas_ftc,
)
from shared.fdt import cargar_fdt, validar_fdt
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
            normalizar_ruta_imagen_ftc(r"imagenes\foto.jpg"),
            "imagenes/foto.jpg",
        )

    def test_rechaza_rutas_fuera_de_imagenes(self):
        for ruta in (
            "../foto.jpg",
            "imagenes/../foto.jpg",
            r"imagenes\..\foto.jpg",
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

    def test_nombres_de_imagen_permanecen_unicos_con_sufijos_en_conflicto(self):
        rutas = {}
        for field_id in ("a!", "a__2", "a?"):
            rutas[field_id] = construir_ruta_imagen_ftc(
                field_id, ".jpg", rutas
            )
        self.assertEqual(len(set(rutas.values())), 3)

    def test_no_carga_rutas_externas_desde_respuestas_de_imagen(self):
        campos = {
            "texto": Field(field_id="texto", question="Texto"),
            "foto": Field(field_id="foto", question="Foto", field_type="image"),
        }
        respuestas = filtrar_respuestas_ftc(
            {
                "texto": "respuesta válida",
                "foto": r"C:\\datos\\privados\\foto.jpg",
                "campo_inexistente": "no cargar",
            },
            campos,
        )
        self.assertEqual(respuestas, {"texto": "respuesta válida"})

    def test_rechaza_imagen_asociada_a_campo_no_imagen(self):
        campos = {
            "texto": Field(field_id="texto", question="Texto"),
            "foto": Field(field_id="foto", question="Foto", field_type="image"),
        }
        self.assertIs(validar_campo_imagen_ftc("foto", campos), campos["foto"])
        with self.assertRaises(ValueError):
            validar_campo_imagen_ftc("texto", campos)
        with self.assertRaises(ValueError):
            validar_campo_imagen_ftc("inexistente", campos)


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

    def test_rechaza_rutas_zip_fuera_del_fdt(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = __import__("pathlib").Path(temporal) / "malicioso.fdt"
            with zipfile.ZipFile(str(ruta), "w") as paquete:
                paquete.writestr("format.json", b"{}")
                paquete.writestr("../fuera.txt", b"no debe extraerse")
            with self.assertRaisesRegex(ValueError, "ruta de archivo insegura"):
                cargar_fdt(ruta)

    def test_rechaza_entradas_duplicadas_fdt(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = __import__("pathlib").Path(temporal) / "duplicado.fdt"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(str(ruta), "w") as paquete:
                    paquete.writestr("format.json", b"{}")
                    paquete.writestr("format.json", b'{"name":"otro"}')
            with self.assertRaisesRegex(ValueError, "nombres de archivo duplicados"):
                cargar_fdt(ruta)



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

    def test_rechaza_rutas_zip_fuera_del_fdt(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = __import__("pathlib").Path(temporal) / "malicioso_android.fdt"
            with zipfile.ZipFile(str(ruta), "w") as paquete:
                paquete.writestr("format.json", b"{}")
                paquete.writestr("../fuera_android.txt", b"no debe extraerse")
            with self.assertRaisesRegex(ValueError, "ruta de archivo insegura"):
                ANDROID_FDT.cargar_fdt(ruta)

    def test_rechaza_entradas_duplicadas_fdt(self):
        with tempfile.TemporaryDirectory() as temporal:
            ruta = __import__("pathlib").Path(temporal) / "duplicado_android.fdt"
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", UserWarning)
                with zipfile.ZipFile(str(ruta), "w") as paquete:
                    paquete.writestr("format.json", b"{}")
                    paquete.writestr("format.json", b'{"name":"otro"}')
            with self.assertRaisesRegex(ValueError, "nombres de archivo duplicados"):
                ANDROID_FDT.cargar_fdt(ruta)


if __name__ == "__main__":
    unittest.main()
