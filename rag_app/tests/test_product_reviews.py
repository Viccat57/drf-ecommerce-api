from types import SimpleNamespace
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rag_app.models import ProductReview
from rag_app.serializers import ProductReviewSerializer
from .base import BaseAPITestCase
from rest_framework.exceptions import ValidationError


class ProductReviewTests(BaseAPITestCase):
    url = "/api/product-reviews"

    def setUp(self):
        super().setUp()
        self.autor = self.autenticar()
        self.otro = get_user_model().objects.create_user(
            username="otro-usuario",
            password="clave-solo-tests",
        )
        self.staff = get_user_model().objects.create_user(
            username="moderador",
            password="clave-solo-tests",
            is_staff=True,
        )
        self.producto = self.crear_producto()

    def payload(self, **extra):
        datos = {
            "product": self.producto.pk,
            "rating": 4,
            "comment": "Buen producto",
        }
        datos.update(extra)
        return datos

    def crear_resena(self, **extra):
        datos = {
            "product": self.producto,
            "user": self.autor,
            "rating": 4,
            "comment": "Comentario original",
        }
        datos.update(extra)
        return ProductReview.objects.create(**datos)

    def detalle(self, resena):
        return f"{self.url}/{resena.pk}"

    def test_lectura_publica_de_listado_y_detalle(self):
        resena = self.crear_resena()
        self.client.force_authenticate(user=None)

        listado = self.client.get(self.url)
        detalle = self.client.get(self.detalle(resena))

        self.assertEqual(listado.status_code, 200)
        self.assertEqual(listado.data["count"], 1)
        self.assertEqual(
            listado.data["results"][0]["id"], resena.pk
        )
        self.assertEqual(detalle.status_code, 200)
        self.assertEqual(detalle.data["id"], resena.pk)

    def test_creacion_asigna_autor_e_ignora_usuario_enviado(self):
        response = self.client.post(
            self.url,
            self.payload(user=self.otro.pk),
            format="json",
        )

        self.assertEqual(response.status_code, 201, response.data)
        resena = ProductReview.objects.get(pk=response.data["id"])

        self.assertEqual(resena.user_id, self.autor.pk)
        self.assertEqual(resena.product_id, self.producto.pk)
        self.assertEqual(response.data["user"], str(self.autor))
        self.assertEqual(resena.rating, 4)

    def test_escrituras_anonimas_son_rechazadas_sin_cambios(self):
        resena = self.crear_resena()
        self.client.force_authenticate(user=None)

        respuestas = [
            self.client.post(
                self.url, self.payload(), format="json"
            ),
            self.client.patch(
                self.detalle(resena),
                {"rating": 1},
                format="json",
            ),
            self.client.delete(self.detalle(resena)),
        ]

        for response in respuestas:
            self.assertEqual(response.status_code, 401)

        resena.refresh_from_db()
        self.assertEqual(resena.rating, 4)
        self.assertEqual(ProductReview.objects.count(), 1)

    def test_rechaza_calificaciones_fuera_del_rango(self):
        for rating in (0, 6, -1):
            with self.subTest(rating=rating):
                response = self.client.post(
                    self.url,
                    self.payload(rating=rating),
                    format="json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("rating", response.data)

        self.assertEqual(ProductReview.objects.count(), 0)

    def test_duplicado_se_rechaza_pero_otro_autor_puede_resenar(self):
        self.crear_resena()

        duplicada = self.client.post(
            self.url, self.payload(), format="json"
        )

        self.assertEqual(duplicada.status_code, 400)
        self.assertIn(
            "Ya reseñaste este producto.", str(duplicada.data)
        )
        self.assertEqual(ProductReview.objects.count(), 1)

        self.client.force_authenticate(user=self.otro)
        permitida = self.client.post(
            self.url, self.payload(), format="json"
        )

        self.assertEqual(
            permitida.status_code, 201, permitida.data
        )
        self.assertEqual(ProductReview.objects.count(), 2)

    def test_no_permite_cambiar_producto_por_patch_o_put(self):
        resena = self.crear_resena()
        otro_producto = self.crear_producto(sku="otro-producto")

        for metodo in ("patch", "put"):
            with self.subTest(metodo=metodo):
                response = getattr(self.client, metodo)(
                    self.detalle(resena),
                    {
                        "product": otro_producto.pk,
                        "rating": 5,
                        "comment": "Cambio rechazado",
                    },
                    format="json",
                )

                self.assertEqual(response.status_code, 400)
                self.assertIn("product", response.data)

                resena.refresh_from_db()
                self.assertEqual(
                    resena.product_id, self.producto.pk
                )
                self.assertEqual(resena.rating, 4)
                self.assertEqual(
                    resena.comment, "Comentario original"
                )

    def test_otro_usuario_no_puede_editar_ni_borrar(self):
        resena = self.crear_resena()
        self.client.force_authenticate(user=self.otro)

        patch_response = self.client.patch(
            self.detalle(resena),
            {"rating": 1},
            format="json",
        )
        put_response = self.client.put(
            self.detalle(resena),
            self.payload(rating=1),
            format="json",
        )
        delete_response = self.client.delete(
            self.detalle(resena)
        )

        for response in (
            patch_response, put_response, delete_response
        ):
            self.assertEqual(response.status_code, 403)

        resena.refresh_from_db()
        self.assertEqual(resena.rating, 4)
        self.assertEqual(
            resena.comment, "Comentario original"
        )

    def test_autor_y_staff_pueden_editar_y_borrar(self):
        for usuario in (self.autor, self.staff):
            with self.subTest(usuario=usuario.username):
                resena = self.crear_resena()
                pk = resena.pk
                self.client.force_authenticate(user=usuario)

                actualizado = self.client.patch(
                    self.detalle(resena),
                    {
                        "rating": 5,
                        "comment": "Comentario actualizado",
                        "user": self.otro.pk,
                    },
                    format="json",
                )

                self.assertEqual(
                    actualizado.status_code,
                    200,
                    actualizado.data,
                )
                resena.refresh_from_db()
                self.assertEqual(resena.rating, 5)
                self.assertEqual(
                    resena.comment, "Comentario actualizado"
                )
                self.assertEqual(resena.user_id, self.autor.pk)

                borrado = self.client.delete(
                    self.detalle(resena)
                )

                self.assertEqual(borrado.status_code, 204)
                self.assertFalse(
                    ProductReview.objects.filter(pk=pk).exists()
                )

    def test_producto_inactivo_rechaza_nuevas_pero_admite_edicion_y_borrado(self):
        resena = self.crear_resena()
        self.producto.active = False
        self.producto.save(update_fields=["active"])

        self.client.force_authenticate(user=self.otro)
        nueva = self.client.post(
            self.url, self.payload(), format="json"
        )

        self.assertEqual(nueva.status_code, 400)
        self.assertIn("product", nueva.data)
        self.assertEqual(ProductReview.objects.count(), 1)

        self.client.force_authenticate(user=self.autor)

        for metodo, datos in (
            ("patch", {"rating": 5}),
            ("put", self.payload(rating=3)),
        ):
            with self.subTest(metodo=metodo):
                response = getattr(self.client, metodo)(
                    self.detalle(resena),
                    datos,
                    format="json",
                )
                self.assertEqual(
                    response.status_code, 200, response.data
                )

        resena.refresh_from_db()
        self.assertEqual(resena.rating, 3)

        self.client.force_authenticate(user=None)
        lectura = self.client.get(self.detalle(resena))
        self.assertEqual(lectura.status_code, 200)

        self.client.force_authenticate(user=self.autor)
        borrado = self.client.delete(self.detalle(resena))

        self.assertEqual(borrado.status_code, 204)
        self.assertEqual(ProductReview.objects.count(), 0)

    def test_filtrado_por_producto_y_parametros_invalidos(self):
        primera = self.crear_resena()
        otro_producto = self.crear_producto(sku="otro-producto")
        segunda = self.crear_resena(product=otro_producto)
        vacio = self.crear_producto(sku="sin-resenas")

        for producto, ids in (
            (self.producto, [primera.pk]),
            (otro_producto, [segunda.pk]),
            (vacio, []),
        ):
            with self.subTest(producto=producto.pk):
                response = self.client.get(
                    self.url, {"product": producto.pk}
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["count"], len(ids))
                self.assertCountEqual(
                    [
                        item["id"]
                        for item in response.data["results"]
                    ],
                    ids,
                )

        for valor in ("abc", "-1", "1.5", ""):
            with self.subTest(valor=valor):
                response = self.client.get(
                    self.url, {"product": valor}
                )
                self.assertEqual(response.status_code, 400)

    def test_base_de_datos_rechaza_duplicado_y_rating_invalido(self):
        self.crear_resena()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.crear_resena()

        for rating in (0, 6):
            with self.subTest(rating=rating):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        self.crear_resena(
                            user=self.otro, rating=rating
                        )

        self.assertEqual(ProductReview.objects.count(), 1)

    def test_error_de_duplicado_se_traduce_y_otros_se_propagan(self):
        for restriccion, es_duplicado in (
            ("unique_review_per_user", True),
            ("otra_restriccion", False),
            (None, False),
        ):
            with self.subTest(restriccion=restriccion):
                causa = Exception("Error de PostgreSQL simulado")
                causa.diag = SimpleNamespace(
                    constraint_name=restriccion
                )
                error = IntegrityError("Error simulado")
                error.__cause__ = causa

                serializer = ProductReviewSerializer()
                datos = {
                    "product": self.producto,
                    "user": self.autor,
                    "rating": 4,
                    "comment": "Prueba de manejo de errores",
                }

                with patch(
                    "rest_framework.serializers.ModelSerializer.create",
                    side_effect=error,
                ):
                    if es_duplicado:
                        with self.assertRaises(
                            ValidationError
                        ) as capturado:
                            serializer.create(datos)

                        self.assertIn(
                            "Ya reseñaste este producto.",
                            str(capturado.exception.detail),
                        )
                    else:
                        with self.assertRaises(
                            IntegrityError
                        ) as capturado:
                            serializer.create(datos)

                        self.assertIs(
                            capturado.exception, error
                        )

        self.assertEqual(ProductReview.objects.count(), 0)