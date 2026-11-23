from unittest.mock import patch
from django.db import transaction
from rag_app.models import ProductImage
from .base import BaseAPITestCase, make_image_file


class ProductImageLifecycleTests(BaseAPITestCase):
    url = "/api/product-images"

    def setUp(self):
        super().setUp()
        self.autenticar()
        self.producto = self.crear_producto()

    def crear_imagen(self, nombre="lifecycle.png"):
        return ProductImage.objects.create(
            product=self.producto,
            image=make_image_file(nombre),
        )

    def test_mismo_nombre_no_sobrescribe_archivo_anterior(self):
        primera = self.crear_imagen("repetida.png")
        storage = primera.image.storage
        nombre_anterior = primera.image.name

        with storage.open(nombre_anterior, "rb") as archivo:
            contenido_anterior = archivo.read()

        segunda = ProductImage.objects.create(
            product=self.producto,
            image=make_image_file("repetida.png", color="blue"),
        )

        self.assertNotEqual(nombre_anterior, segunda.image.name)
        self.assertTrue(storage.exists(nombre_anterior))
        self.assertTrue(storage.exists(segunda.image.name))

        with storage.open(nombre_anterior, "rb") as archivo:
            self.assertEqual(archivo.read(), contenido_anterior)

    def test_delete_api_limpia_archivo_despues_del_commit(self):
        imagen = self.crear_imagen()
        storage = imagen.image.storage
        nombre = imagen.image.name
        pk = imagen.pk

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.delete(f"{self.url}/{pk}")

            self.assertEqual(response.status_code, 204)
            self.assertFalse(ProductImage.objects.filter(pk=pk).exists())
            self.assertTrue(storage.exists(nombre))

        self.assertEqual(len(callbacks), 1)
        self.assertFalse(storage.exists(nombre))

    def test_reemplazo_api_limpia_archivo_anterior(self):
        imagen = self.crear_imagen()
        storage = imagen.image.storage
        anterior = imagen.image.name

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.patch(
                f"{self.url}/{imagen.pk}",
                {"image": make_image_file("nueva.png", color="blue")},
                format="multipart",
            )

            self.assertEqual(response.status_code, 200, response.data)
            imagen.refresh_from_db()
            nuevo = imagen.image.name

            self.assertNotEqual(anterior, nuevo)
            self.assertTrue(storage.exists(anterior))
            self.assertTrue(storage.exists(nuevo))

        self.assertEqual(len(callbacks), 1)
        self.assertFalse(storage.exists(anterior))
        self.assertTrue(storage.exists(nuevo))

    def test_patch_sin_archivo_no_programa_limpieza(self):
        imagen = self.crear_imagen()
        storage = imagen.image.storage
        nombre = imagen.image.name

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.patch(
                f"{self.url}/{imagen.pk}",
                {"is_primary": True},
                format="json",
            )

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(len(callbacks), 0)
        self.assertTrue(storage.exists(nombre))

    def test_borrado_real_de_producto_limpia_sus_archivos(self):
        primera = self.crear_imagen("primera.png")
        segunda = self.crear_imagen("segunda.png")
        storage = primera.image.storage
        nombres = [primera.image.name, segunda.image.name]

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            self.producto.delete()

            for nombre in nombres:
                self.assertTrue(storage.exists(nombre))

        self.assertEqual(len(callbacks), 2)
        self.assertEqual(ProductImage.objects.count(), 0)

        for nombre in nombres:
            self.assertFalse(storage.exists(nombre))

    def test_rollback_de_borrado_conserva_registro_y_archivo(self):
        imagen = self.crear_imagen()
        storage = imagen.image.storage
        nombre = imagen.image.name
        pk = imagen.pk

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            with self.assertRaisesMessage(RuntimeError, "revertir"):
                with transaction.atomic():
                    imagen.delete()
                    raise RuntimeError("revertir")

        self.assertEqual(len(callbacks), 0)
        self.assertTrue(ProductImage.objects.filter(pk=pk).exists())
        self.assertTrue(storage.exists(nombre))

    def test_archivo_compartido_se_borra_solo_al_quedar_sin_referencias(self):
        primera = self.crear_imagen()
        storage = primera.image.storage
        nombre = primera.image.name

        segunda = ProductImage.objects.create(
            product=self.producto,
            image=nombre,
        )

        with self.captureOnCommitCallbacks(execute=True):
            primera.delete()

        self.assertTrue(storage.exists(nombre))

        with self.captureOnCommitCallbacks(execute=True):
            segunda.delete()

        self.assertFalse(storage.exists(nombre))

    def test_fallo_de_storage_se_registra_sin_revertir_borrado(self):
        imagen = self.crear_imagen()
        storage = imagen.image.storage
        nombre = imagen.image.name
        pk = imagen.pk

        with patch.object(
            storage, "delete", side_effect=OSError("storage no disponible")
        ):
            with self.assertLogs("rag_app.signals", level="ERROR"):
                with self.captureOnCommitCallbacks(execute=True):
                    imagen.delete()

        self.assertFalse(ProductImage.objects.filter(pk=pk).exists())
        self.assertTrue(storage.exists(nombre))