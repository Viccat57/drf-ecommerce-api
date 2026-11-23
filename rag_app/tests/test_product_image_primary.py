from datetime import timedelta
from django.utils import timezone
from rag_app.models import ProductImage
from .base import BaseAPITestCase, make_image_file


class ProductImagePrimaryTests(BaseAPITestCase):
    url = "/api/product-images"

    def setUp(self):
        super().setUp()
        self.autenticar()
        self.producto = self.crear_producto()

    def subir(self, **extra):
        datos = {
            "product": self.producto.pk,
            "image": make_image_file(),
        }
        datos.update(extra)

        response = self.client.post(
            self.url,
            datos,
            format="multipart",
        )
        self.assertEqual(response.status_code, 201, response.data)

        return ProductImage.objects.get(pk=response.data["id"])

    def actualizar(self, imagen, datos):
        return self.client.patch(
            f"{self.url}/{imagen.pk}",
            datos,
            format="json",
        )

    def comprobar_principal(self, esperada):
        principales = list(
            ProductImage.objects
            .filter(product=self.producto, is_primary=True)
            .values_list("pk", flat=True)
        )
        self.assertEqual(principales, [esperada.pk])

    def test_primera_imagen_es_principal_sin_enviar_bandera(self):
        primera = self.subir()

        self.assertTrue(primera.is_primary)
        self.comprobar_principal(primera)

    def test_primera_imagen_es_principal_aunque_se_envie_false(self):
        primera = self.subir(is_primary=False)

        self.assertTrue(primera.is_primary)
        self.comprobar_principal(primera)

    def test_segunda_imagen_sin_bandera_es_secundaria(self):
        primera = self.subir()
        segunda = self.subir()

        self.assertFalse(segunda.is_primary)
        self.comprobar_principal(primera)

    def test_crear_nueva_principal_desmarca_la_anterior(self):
        primera = self.subir()
        segunda = self.subir(is_primary=True)

        primera.refresh_from_db()

        self.assertFalse(primera.is_primary)
        self.comprobar_principal(segunda)

    def test_marcar_secundaria_como_principal(self):
        primera = self.subir()
        segunda = self.subir()

        response = self.actualizar(segunda, {"is_primary": True})

        self.assertEqual(response.status_code, 200, response.data)
        primera.refresh_from_db()
        self.assertFalse(primera.is_primary)
        self.comprobar_principal(segunda)

    def test_desmarcar_principal_promueve_por_fecha_y_pk(self):
        primera = self.subir()
        segunda = self.subir()
        tercera = self.subir()

        fecha_antigua = timezone.now() - timedelta(days=1)

        ProductImage.objects.filter(
            pk__in=[segunda.pk, tercera.pk],
        ).update(created_at=fecha_antigua)

        response = self.actualizar(primera, {"is_primary": False})

        self.assertEqual(response.status_code, 200, response.data)
        primera.refresh_from_db()
        self.assertFalse(primera.is_primary)
        self.comprobar_principal(segunda)

    def test_desmarcar_unica_principal_devuelve_400(self):
        primera = self.subir()

        response = self.actualizar(primera, {"is_primary": False})

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn("is_primary", response.data)
        self.comprobar_principal(primera)

    def test_borrar_principal_promueve_la_mas_antigua_restante(self):
        primera = self.subir()
        segunda = self.subir()
        tercera = self.subir()

        ProductImage.objects.filter(pk=tercera.pk).update(
            created_at=timezone.now() - timedelta(days=1),
        )

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                f"{self.url}/{primera.pk}"
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ProductImage.objects.filter(pk=primera.pk).exists()
        )
        self.comprobar_principal(tercera)
        segunda.refresh_from_db()
        self.assertFalse(segunda.is_primary)

    def test_borrar_ultima_imagen_esta_permitido(self):
        primera = self.subir()
        storage = primera.image.storage
        nombre = primera.image.name

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                f"{self.url}/{primera.pk}"
            )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(
            ProductImage.objects.filter(product=self.producto).exists()
        )
        self.assertFalse(storage.exists(nombre))

    def test_no_permite_mover_imagen_por_patch_ni_put(self):
        primera = self.subir()
        otro_producto = self.crear_producto(sku="otro-producto")

        response_patch = self.actualizar(
            primera,
            {"product": otro_producto.pk},
        )

        self.assertEqual(
            response_patch.status_code,
            400,
            response_patch.data,
        )
        self.assertIn("product", response_patch.data)

        response_put = self.client.put(
            f"{self.url}/{primera.pk}",
            {
                "product": otro_producto.pk,
                "image": make_image_file("otra.png"),
                "is_primary": True,
            },
            format="multipart",
        )

        self.assertEqual(
            response_put.status_code,
            400,
            response_put.data,
        )
        self.assertIn("product", response_put.data)

        primera.refresh_from_db()
        self.assertEqual(primera.product_id, self.producto.pk)
        self.comprobar_principal(primera)

    def test_reenviar_mismo_producto_y_principal_no_cambia_estado(self):
        primera = self.subir()
        segunda = self.subir()

        response = self.actualizar(
            primera,
            {
                "product": self.producto.pk,
                "is_primary": True,
            },
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.comprobar_principal(primera)
        segunda.refresh_from_db()
        self.assertFalse(segunda.is_primary)

    def test_borrar_secundaria_conserva_principal(self):
        primera = self.subir()
        segunda = self.subir()

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.delete(
                f"{self.url}/{segunda.pk}"
            )

        self.assertEqual(response.status_code, 204)
        self.comprobar_principal(primera)