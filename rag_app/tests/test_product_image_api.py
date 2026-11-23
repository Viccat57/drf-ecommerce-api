from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rag_app.models import Product, ProductImage
from .base import BaseAPITestCase, make_image_file

class ProductImageAPITests(BaseAPITestCase):
    url = "/api/product-images"

    def setUp(self):
        super().setUp()
        self.autenticar()

        self.producto_a = self.crear_producto(sku="imagen-a")
        self.producto_b = self.crear_producto(sku="imagen-b")

        self.a1 = self.crear_imagen(
            self.producto_a, "a1.png", principal=True
        )
        self.a2 = self.crear_imagen(
            self.producto_a, "a2.png"
        )
        self.b1 = self.crear_imagen(
            self.producto_b, "b1.png", principal=True
        )
        self.b2 = self.crear_imagen(
            self.producto_b, "b2.png"
        )

    def crear_imagen(self, producto, nombre, principal=False):
        return ProductImage.objects.create(
            product=producto,
            image=make_image_file(nombre),
            is_primary=principal,
        )

    def estado(self, producto=None):
        queryset = ProductImage.objects.order_by("pk")

        if producto is not None:
            queryset = queryset.filter(product=producto)

        registros = []
        contenidos = {}

        for imagen in queryset:
            registros.append((
                imagen.pk,
                imagen.product_id,
                imagen.image.name,
                imagen.is_primary,
                imagen.created_at,
            ))

            with imagen.image.storage.open(
                imagen.image.name, "rb"
            ) as archivo:
                contenidos[imagen.image.name] = archivo.read()

        return registros, contenidos

    def comprobar_principal(self, producto, imagen):
        principales = list(
            ProductImage.objects.filter(
                product=producto,
                is_primary=True,
            ).values_list("pk", flat=True)
        )
        self.assertEqual(principales, [imagen.pk])

    def comprobar_listado(self, parametros, ids_esperados):
        response = self.client.get(self.url, parametros)

        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(
            response.data["count"],
            len(ids_esperados),
        )
        self.assertCountEqual(
            [item["id"] for item in response.data["results"]],
            ids_esperados,
        )

    def comprobar_rechazo_sin_cambios(
        self, imagen, datos, campo_error, metodo="patch"
    ):
        estado_anterior = self.estado()
        storage = imagen.image.storage
        peticion = getattr(self.client, metodo)

        with patch.object(
            storage, "save", wraps=storage.save
        ) as guardar:
            with self.captureOnCommitCallbacks(
                execute=True
            ) as callbacks:
                response = peticion(
                    f"{self.url}/{imagen.pk}",
                    datos,
                    format="multipart",
                )

        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn(campo_error, response.data)
        guardar.assert_not_called()
        self.assertEqual(len(callbacks), 0)
        self.assertEqual(self.estado(), estado_anterior)

    def test_listado_sin_filtro_es_publico(self):
        self.client.force_authenticate(user=None)

        self.comprobar_listado(
            {},
            [self.a1.pk, self.a2.pk, self.b1.pk, self.b2.pk],
        )

    def test_filtra_solo_las_imagenes_del_producto(self):
        self.client.force_authenticate(user=None)

        for producto, imagenes in (
            (self.producto_a, [self.a1.pk, self.a2.pk]),
            (self.producto_b, [self.b1.pk, self.b2.pk]),
        ):
            with self.subTest(producto=producto.pk):
                self.comprobar_listado(
                    {"product": producto.pk},
                    imagenes,
                )

    def test_producto_sin_imagenes_o_inexistente_devuelve_vacio(self):
        vacio = self.crear_producto(sku="sin-imagenes")

        inexistente = (
            Product.objects.order_by("-pk")
            .values_list("pk", flat=True)
            .first()
        ) + 1

        for producto_id in (vacio.pk, inexistente):
            with self.subTest(producto=producto_id):
                self.comprobar_listado(
                    {"product": producto_id},
                    [],
                )

    def test_rechaza_filtros_no_enteros_validos(self):
        for valor in ("abc", "-1", "1.5", "", "1 OR 1=1"):
            with self.subTest(valor=valor):
                response = self.client.get(
                    self.url,
                    {"product": valor},
                )

                self.assertEqual(
                    response.status_code, 400, response.data
                )

    def test_filtro_de_producto_tambien_limita_el_detalle(self):
        self.client.force_authenticate(user=None)

        correcto = self.client.get(
            f"{self.url}/{self.a1.pk}",
            {"product": self.producto_a.pk},
        )
        otro_producto = self.client.get(
            f"{self.url}/{self.a1.pk}",
            {"product": self.producto_b.pk},
        )

        self.assertEqual(correcto.status_code, 200)
        self.assertEqual(correcto.data["id"], self.a1.pk)
        self.assertEqual(otro_producto.status_code, 404)

    def test_marcar_principal_no_modifica_otro_producto(self):
        estado_b = self.estado(self.producto_b)

        response = self.client.patch(
            f"{self.url}/{self.a2.pk}",
            {"is_primary": True},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.comprobar_principal(self.producto_a, self.a2)
        self.assertEqual(self.estado(self.producto_b), estado_b)

    def test_desmarcar_principal_no_modifica_otro_producto(self):
        estado_b = self.estado(self.producto_b)

        response = self.client.patch(
            f"{self.url}/{self.a1.pk}",
            {"is_primary": False},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        self.comprobar_principal(self.producto_a, self.a2)
        self.assertEqual(self.estado(self.producto_b), estado_b)

    def test_borrar_principal_no_modifica_otro_producto(self):
        estado_b = self.estado(self.producto_b)
        storage = self.a1.image.storage
        nombre = self.a1.image.name
        pk = self.a1.pk

        with self.captureOnCommitCallbacks(
            execute=True
        ) as callbacks:
            response = self.client.delete(f"{self.url}/{pk}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(callbacks), 1)
        self.assertFalse(
            ProductImage.objects.filter(pk=pk).exists()
        )
        self.assertFalse(storage.exists(nombre))
        self.comprobar_principal(self.producto_a, self.a2)
        self.assertEqual(self.estado(self.producto_b), estado_b)

    def test_reemplazo_falso_no_cambia_archivo_ni_principal(self):
        falso = SimpleUploadedFile(
            "falso.jpg",
            b"esto no es una imagen",
            content_type="image/jpeg",
        )

        self.comprobar_rechazo_sin_cambios(
            self.a2,
            {"image": falso, "is_primary": True},
            "image",
        )

    def test_reemplazo_de_formato_rechazado_no_deja_cambios(self):
        self.comprobar_rechazo_sin_cambios(
            self.a2,
            {
                "image": make_image_file("rechazada.gif", "GIF"),
                "is_primary": True,
            },
            "image",
        )

    def test_reemplazo_que_supera_limites_no_deja_cambios(self):
        limites = (
            {"IMAGE_MAX_BYTES": 1},
            {"IMAGE_MAX_PIXELS": 1},
        )

        for ajustes in limites:
            with self.subTest(ajustes=ajustes):
                with override_settings(**ajustes):
                    self.comprobar_rechazo_sin_cambios(
                        self.a2,
                        {
                            "image": make_image_file(
                                "demasiado-grande.png"
                            ),
                            "is_primary": True,
                        },
                        "image",
                    )

    def test_mover_y_reemplazar_por_patch_o_put_no_deja_cambios(self):
        for metodo in ("patch", "put"):
            with self.subTest(metodo=metodo):
                self.comprobar_rechazo_sin_cambios(
                    self.a2,
                    {
                        "product": self.producto_b.pk,
                        "image": make_image_file(
                            "movimiento-rechazado.png",
                            color="blue",
                        ),
                        "is_primary": True,
                    },
                    "product",
                    metodo=metodo,
                )

    def test_desmarcar_unica_y_reemplazar_no_escribe_archivo(self):
        producto = self.crear_producto(sku="unica-imagen")
        unica = self.crear_imagen(
            producto,
            "unica.png",
            principal=True,
        )

        self.comprobar_rechazo_sin_cambios(
            unica,
            {
                "image": make_image_file(
                    "reemplazo-rechazado.png",
                    color="blue",
                ),
                "is_primary": False,
            },
            "is_primary",
        )