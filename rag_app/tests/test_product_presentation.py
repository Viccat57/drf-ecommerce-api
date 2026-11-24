from datetime import timedelta
from django.contrib.auth import get_user_model
from django.utils import timezone
from rag_app.models import ProductImage, ProductReview
from .base import BaseAPITestCase, make_image_file


class ProductPresentationTests(BaseAPITestCase):
    url = "/api/products"

    def setUp(self):
        super().setUp()
        self.usuario = self.autenticar()
        self.producto = self.crear_producto()
        self.otro_producto = self.crear_producto(sku="otro-producto")

    def crear_resena(self, rating, indice, producto=None):
        usuario = get_user_model().objects.create_user(
            username=f"resenador-{indice}",
            password="clave-solo-tests",
        )
        return ProductReview.objects.create(
            product=producto or self.producto,
            user=usuario,
            rating=rating,
            comment=f"Comentario {indice}",
        )

    def crear_imagen(self, nombre, principal=False, producto=None):
        return ProductImage.objects.create(
            product=producto or self.producto,
            image=make_image_file(nombre),
            is_primary=principal,
        )

    def detalle(self, producto=None):
        producto = producto or self.producto
        response = self.client.get(f"{self.url}/{producto.pk}")
        self.assertEqual(response.status_code, 200, response.data)
        return response.data

    def comprobar_metricas(self, datos, promedio, cantidad):
        self.assertAlmostEqual(datos["average_rating"], promedio)
        self.assertEqual(datos["reviews_count"], cantidad)

    def test_sin_resenas_ni_imagenes_devuelve_ceros_y_lista_vacia(self):
        self.client.force_authenticate(user=None)

        detalle = self.detalle()
        self.comprobar_metricas(detalle, 0.0, 0)
        self.assertEqual(detalle["images"], [])
        self.assertNotIn("reviews", detalle)
        self.assertNotIn("embedding", detalle)
        self.assertNotIn("embedding_hash", detalle)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        for item in response.data["results"]:
            self.comprobar_metricas(item, 0.0, 0)
            self.assertNotIn("images", item)
            self.assertNotIn("reviews", item)

    def test_metricas_aisladas_y_sin_duplicacion_por_imagenes(self):
        for indice, rating in enumerate((5, 5, 2)):
            self.crear_resena(rating, indice)

        self.crear_resena(
            1, "otro", producto=self.otro_producto
        )
        self.crear_imagen("principal.png", principal=True)
        self.crear_imagen("secundaria.png")

        detalle = self.detalle()
        self.comprobar_metricas(detalle, 4.0, 3)
        self.assertEqual(len(detalle["images"]), 2)

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        items = {
            item["id"]: item
            for item in response.data["results"]
        }

        self.comprobar_metricas(
            items[self.producto.pk], 4.0, 3
        )
        self.comprobar_metricas(
            items[self.otro_producto.pk], 1.0, 1
        )

    def test_metricas_se_actualizan_al_editar_y_borrar_resenas(self):
        resena = ProductReview.objects.create(
            product=self.producto,
            user=self.usuario,
            rating=2,
            comment="Mi reseña",
        )
        self.comprobar_metricas(self.detalle(), 2.0, 1)

        actualizado = self.client.patch(
            f"/api/product-reviews/{resena.pk}",
            {"rating": 5},
            format="json",
        )
        self.assertEqual(
            actualizado.status_code, 200, actualizado.data
        )
        self.comprobar_metricas(self.detalle(), 5.0, 1)

        borrado = self.client.delete(
            f"/api/product-reviews/{resena.pk}"
        )
        self.assertEqual(borrado.status_code, 204)
        self.comprobar_metricas(self.detalle(), 0.0, 0)

    def test_imagenes_ordenadas_y_solo_del_producto_consultado(self):
        primera = self.crear_imagen("primera.png")
        segunda = self.crear_imagen("segunda.png")
        principal = self.crear_imagen(
            "principal.png", principal=True
        )
        self.crear_imagen(
            "ajena.png",
            principal=True,
            producto=self.otro_producto,
        )

        fecha = timezone.now() - timedelta(days=1)
        ProductImage.objects.filter(
            pk__in=[primera.pk, segunda.pk]
        ).update(created_at=fecha)

        datos = self.detalle()

        self.assertEqual(
            [imagen["id"] for imagen in datos["images"]],
            [principal.pk, primera.pk, segunda.pk],
        )
        for imagen in datos["images"]:
            self.assertEqual(
                imagen["product"], self.producto.pk
            )
            self.assertTrue(imagen["image"])
            self.assertEqual(
                set(imagen),
                {
                    "id", "product", "image",
                    "is_primary", "created_at",
                },
            )

    def test_metricas_e_imagenes_no_se_escriben_desde_product(self):
        resena = self.crear_resena(4, 0)
        imagen = self.crear_imagen(
            "conservada.png", principal=True
        )
        nombre = imagen.image.name

        response = self.client.patch(
            f"{self.url}/{self.producto.pk}",
            {
                "stock": 8,
                "average_rating": 1.0,
                "reviews_count": 999,
                "images": [],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.comprobar_metricas(response.data, 4.0, 1)
        self.assertEqual(
            [item["id"] for item in response.data["images"]],
            [imagen.pk],
        )

        self.producto.refresh_from_db()
        resena.refresh_from_db()
        imagen.refresh_from_db()

        self.assertEqual(self.producto.stock, 8)
        self.assertEqual(resena.rating, 4)
        self.assertEqual(imagen.image.name, nombre)
        self.assertTrue(imagen.image.storage.exists(nombre))