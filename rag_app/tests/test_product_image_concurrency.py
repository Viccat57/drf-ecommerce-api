import threading
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import connections, transaction
from rest_framework.test import APIClient, APITransactionTestCase

from rag_app.models import Brand, Category, Product, ProductImage

from .base import make_image_file


class ProductImageConcurrencyTests(APITransactionTestCase):
    url = "/api/product-images"

    def setUp(self):
        super().setUp()
        self.usuario = get_user_model().objects.create_user(
            username="usuario-concurrencia",
            password="clave-solo-tests",
        )
        self.marca = Brand.objects.create(name="Marca concurrente")
        self.categoria = Category.objects.create(
            name="Categoria concurrente",
            slug="categoria-concurrente",
        )

    def cliente(self):
        cliente = APIClient()
        cliente.force_authenticate(user=self.usuario)
        return cliente

    def crear_producto(self, sku):
        return Product.objects.create(
            name="Producto concurrente",
            sku=sku,
            description="Producto para pruebas de concurrencia",
            price=Decimal("1.00"),
            brand=self.marca,
            category=self.categoria,
        )

    def crear_imagen(self, producto, nombre, principal=False):
        return ProductImage.objects.create(
            product=producto,
            image=make_image_file(nombre),
            is_primary=principal,
        )

    def crear_producto_con_tres_imagenes(self, sku):
        producto = self.crear_producto(sku)
        a1 = self.crear_imagen(producto, "a1.png", principal=True)
        a2 = self.crear_imagen(producto, "a2.png")
        a3 = self.crear_imagen(producto, "a3.png")
        return producto, a1, a2, a3

    def subir(self, cliente, producto, nombre, **extra):
        datos = {
            "product": producto.pk,
            "image": make_image_file(nombre),
        }
        datos.update(extra)
        return cliente.post(self.url, datos, format="multipart")

    def principal_unica(self, producto):
        imagenes = ProductImage.objects.filter(product=producto)
        principales = list(
            imagenes.filter(is_primary=True).values_list("pk", flat=True)
        )

        if imagenes.exists():
            self.assertEqual(len(principales), 1, principales)
            return principales[0]

        self.assertEqual(principales, [])
        return None

    def ejecutar_concurrente(self, tareas):
        barrera = threading.Barrier(len(tareas))
        resultados = [None] * len(tareas)
        errores = []

        def trabajador(indice, tarea):
            try:
                cliente = self.cliente()
                barrera.wait(timeout=10)
                resultados[indice] = tarea(cliente)
            except BaseException as exc:
                errores.append(repr(exc))
                barrera.abort()
            finally:
                connections.close_all()

        hilos = [
            threading.Thread(target=trabajador, args=(indice, tarea))
            for indice, tarea in enumerate(tareas)
        ]

        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join(timeout=30)

        self.assertFalse(any(hilo.is_alive() for hilo in hilos))
        self.assertEqual(errores, [])
        return resultados

    def con_producto_bloqueado(self, producto, tarea, cambios=None):
        resultado = {}

        def trabajador():
            try:
                resultado["response"] = tarea(self.cliente())
            except BaseException as exc:
                resultado["error"] = repr(exc)
            finally:
                connections.close_all()

        hilo = threading.Thread(target=trabajador)

        try:
            with transaction.atomic():
                Product.objects.select_for_update().get(pk=producto.pk)
                hilo.start()

                if cambios is not None:
                    cambios()

                hilo.join(timeout=0.5)
                self.assertTrue(
                    hilo.is_alive(),
                    "La petición terminó sin esperar el bloqueo del producto.",
                )
        finally:
            if hilo.is_alive() or hilo.ident is not None:
                hilo.join(timeout=15)

        self.assertFalse(hilo.is_alive())
        self.assertNotIn("error", resultado, resultado.get("error"))
        return resultado["response"]

    def test_subida_espera_el_bloqueo_y_respeta_el_estado_confirmado(self):
        producto = self.crear_producto("lock-subida")
        existente = {}

        def cambios():
            existente["imagen"] = self.crear_imagen(
                producto, "existente.png", principal=True
            )

        response = self.con_producto_bloqueado(
            producto,
            lambda cliente: self.subir(cliente, producto, "nueva.png"),
            cambios,
        )

        self.assertEqual(response.status_code, 201, response.data)
        self.assertFalse(response.data["is_primary"])
        self.assertEqual(ProductImage.objects.count(), 2)
        self.assertEqual(
            self.principal_unica(producto), existente["imagen"].pk
        )

    def test_borrado_espera_y_relee_si_ya_no_era_principal(self):
        producto, a1, a2, a3 = self.crear_producto_con_tres_imagenes(
            "lock-borrado"
        )

        def cambios():
            ProductImage.objects.filter(pk=a1.pk).update(is_primary=False)
            ProductImage.objects.filter(pk=a3.pk).update(is_primary=True)

        response = self.con_producto_bloqueado(
            producto,
            lambda cliente: cliente.delete(f"{self.url}/{a1.pk}"),
            cambios,
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(ProductImage.objects.filter(pk=a1.pk).exists())
        self.assertEqual(self.principal_unica(producto), a3.pk)

    def test_desmarcar_espera_y_relee_si_ya_no_era_principal(self):
        producto, a1, a2, a3 = self.crear_producto_con_tres_imagenes(
            "lock-desmarcar"
        )

        def cambios():
            ProductImage.objects.filter(pk=a1.pk).update(is_primary=False)
            ProductImage.objects.filter(pk=a3.pk).update(is_primary=True)

        response = self.con_producto_bloqueado(
            producto,
            lambda cliente: cliente.patch(
                f"{self.url}/{a1.pk}",
                {"is_primary": False},
                format="json",
            ),
            cambios,
        )

        self.assertEqual(response.status_code, 200, response.data)
        a1.refresh_from_db()
        self.assertFalse(a1.is_primary)
        self.assertEqual(self.principal_unica(producto), a3.pk)

    def test_actualizar_imagen_borrada_mientras_espera_devuelve_404(self):
        producto = self.crear_producto("lock-404")
        a1 = self.crear_imagen(producto, "a1.png", principal=True)
        a2 = self.crear_imagen(producto, "a2.png")

        response = self.con_producto_bloqueado(
            producto,
            lambda cliente: cliente.patch(
                f"{self.url}/{a2.pk}",
                {"is_primary": True},
                format="json",
            ),
            lambda: a2.delete(),
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ProductImage.objects.filter(pk=a2.pk).exists())
        self.assertEqual(self.principal_unica(producto), a1.pk)

    def test_primeras_subidas_simultaneas_dejan_una_sola_principal(self):
        for ronda in range(3):
            with self.subTest(ronda=ronda):
                producto = self.crear_producto(f"primeras-{ronda}")
                tareas = [
                    (
                        lambda cliente, indice=indice: self.subir(
                            cliente, producto, f"primera-{indice}.png"
                        )
                    )
                    for indice in range(3)
                ]

                respuestas = self.ejecutar_concurrente(tareas)

                self.assertEqual(
                    [r.status_code for r in respuestas], [201, 201, 201]
                )
                self.assertEqual(
                    ProductImage.objects.filter(product=producto).count(), 3
                )
                self.principal_unica(producto)

    def test_subidas_simultaneas_como_principal_dejan_una_sola(self):
        producto = self.crear_producto("subidas-principal")
        self.crear_imagen(producto, "inicial.png", principal=True)
        tareas = [
            (
                lambda cliente, indice=indice: self.subir(
                    cliente,
                    producto,
                    f"principal-{indice}.png",
                    is_primary=True,
                )
            )
            for indice in range(4)
        ]

        respuestas = self.ejecutar_concurrente(tareas)

        self.assertEqual(
            [r.status_code for r in respuestas], [201, 201, 201, 201]
        )
        self.assertEqual(
            ProductImage.objects.filter(product=producto).count(), 5
        )
        self.principal_unica(producto)

    def test_marcados_simultaneos_dejan_una_sola_principal(self):
        producto, a1, a2, a3 = self.crear_producto_con_tres_imagenes(
            "marcados"
        )
        tareas = [
            (
                lambda cliente, imagen=imagen: cliente.patch(
                    f"{self.url}/{imagen.pk}",
                    {"is_primary": True},
                    format="json",
                )
            )
            for imagen in (a2, a3)
        ]

        respuestas = self.ejecutar_concurrente(tareas)

        self.assertEqual([r.status_code for r in respuestas], [200, 200])
        self.assertIn(self.principal_unica(producto), {a2.pk, a3.pk})

    def test_borrar_principal_y_marcar_otra_simultaneamente(self):
        producto, a1, a2, a3 = self.crear_producto_con_tres_imagenes(
            "borrar-y-marcar"
        )
        tareas = [
            lambda cliente: cliente.delete(f"{self.url}/{a1.pk}"),
            lambda cliente: cliente.patch(
                f"{self.url}/{a2.pk}",
                {"is_primary": True},
                format="json",
            ),
        ]

        borrado, marcado = self.ejecutar_concurrente(tareas)

        self.assertEqual(borrado.status_code, 204)
        self.assertEqual(marcado.status_code, 200)
        self.assertFalse(ProductImage.objects.filter(pk=a1.pk).exists())
        self.assertEqual(self.principal_unica(producto), a2.pk)

    def test_desmarcar_y_borrar_la_misma_principal_simultaneamente(self):
        producto, a1, a2, a3 = self.crear_producto_con_tres_imagenes(
            "desmarcar-y-borrar"
        )
        tareas = [
            lambda cliente: cliente.patch(
                f"{self.url}/{a1.pk}",
                {"is_primary": False},
                format="json",
            ),
            lambda cliente: cliente.delete(f"{self.url}/{a1.pk}"),
        ]

        desmarcado, borrado = self.ejecutar_concurrente(tareas)

        self.assertIn(desmarcado.status_code, {200, 404})
        self.assertEqual(borrado.status_code, 204)
        self.assertFalse(ProductImage.objects.filter(pk=a1.pk).exists())
        self.assertEqual(self.principal_unica(producto), a2.pk)