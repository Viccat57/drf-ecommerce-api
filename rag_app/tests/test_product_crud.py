from decimal import Decimal
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from rag_app.models import Brand, Category, Product, ProductImage
from .base import BaseAPITestCase, make_image_file


class ProductTestBase(BaseAPITestCase):
    url = "/api/products"

    def setUp(self):
        super().setUp()
        self.marca = Brand.objects.create(name="Marca activa")
        self.categoria = Category.objects.create(
            name="Categoria activa", slug="categoria-activa"
        )

    def payload(self, **extra):
        datos = {
            "brand": self.marca.pk,
            "category": self.categoria.pk,
            "name": "Monitor",
            "sku": "MON-1",
            "description": "Monitor de prueba",
            "price": "1500.50",
            "stock": 5,
            "specifications": {"pulgadas": 27},
            "active": True,
        }
        datos.update(extra)
        return datos

    def producto(self, sku="base-1", **extra):
        return self.crear_producto(
            marca=self.marca,
            categoria=self.categoria,
            sku=sku,
            **extra,
        )

    def ids_del_listado(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        return [item["id"] for item in response.data["results"]]


class ProductCreateTests(ProductTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_lectura_publica_de_listado_y_detalle(self):
        producto = self.producto()
        self.client.force_authenticate(user=None)

        self.assertEqual(self.client.get(self.url).status_code, 200)
        detalle = self.client.get(f"{self.url}/{producto.pk}")
        self.assertEqual(detalle.status_code, 200)

    def test_escritura_anonima_devuelve_401(self):
        producto = self.producto()
        self.client.force_authenticate(user=None)

        respuestas = [
            self.client.post(self.url, self.payload(), format="json"),
            self.client.patch(
                f"{self.url}/{producto.pk}", {"stock": 99}, format="json"
            ),
            self.client.delete(f"{self.url}/{producto.pk}"),
        ]

        for response in respuestas:
            self.assertEqual(response.status_code, 401)

        producto.refresh_from_db()
        self.assertTrue(producto.active)
        self.assertNotEqual(producto.stock, 99)
        self.assertEqual(Product.objects.count(), 1)

    def test_crear_producto_valido(self):
        response = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["sku"], "MON-1")
        self.assertEqual(
            Decimal(str(response.data["price"])), Decimal("1500.50")
        )
        self.assertNotIn("embedding", response.data)
        self.assertNotIn("embedding_hash", response.data)

        producto = Product.objects.get(sku="MON-1")
        self.assertEqual(producto.stock, 5)
        self.assertEqual(producto.specifications, {"pulgadas": 27})
        self.assertTrue(producto.active)

    def test_rechaza_precio_negativo(self):
        response = self.client.post(
            self.url, self.payload(price="-1.00"), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("price", response.data)
        self.assertEqual(Product.objects.count(), 0)

    def test_rechaza_stock_negativo(self):
        response = self.client.post(
            self.url, self.payload(stock=-1), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("stock", response.data)
        self.assertEqual(Product.objects.count(), 0)

    def test_rechaza_sku_duplicado(self):
        self.producto(sku="MON-1")

        response = self.client.post(self.url, self.payload(), format="json")

        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)
        self.assertEqual(Product.objects.count(), 1)

    def test_rechaza_sku_demasiado_largo(self):
        response = self.client.post(
            self.url, self.payload(sku="x" * 21), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)

    def test_rechaza_precio_con_mas_de_dos_decimales(self):
        response = self.client.post(
            self.url, self.payload(price="10.123"), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("price", response.data)

    def test_rechaza_marca_inactiva(self):
        inactiva = Brand.objects.create(name="Marca inactiva", active=False)

        response = self.client.post(
            self.url, self.payload(brand=inactiva.pk), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("brand", response.data)

    def test_rechaza_categoria_inactiva(self):
        inactiva = Category.objects.create(
            name="Categoria inactiva", slug="categoria-inactiva", active=False
        )

        response = self.client.post(
            self.url, self.payload(category=inactiva.pk), format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("category", response.data)

    def test_rechaza_campos_obligatorios_faltantes(self):
        response = self.client.post(self.url, {}, format="json")

        self.assertEqual(response.status_code, 400)
        for campo in (
            "brand", "category", "name", "sku", "description", "price"
        ):
            self.assertIn(campo, response.data)


class ProductUpdateTests(ProductTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_put_actualiza_producto(self):
        producto = self.producto()

        response = self.client.put(
            f"{self.url}/{producto.pk}",
            self.payload(sku="base-1", name="Nombre nuevo", price="20.00"),
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        producto.refresh_from_db()
        self.assertEqual(producto.name, "Nombre nuevo")
        self.assertEqual(producto.price, Decimal("20.00"))

    def test_patch_actualiza_un_campo_y_conserva_el_resto(self):
        producto = self.producto()
        precio = producto.price

        response = self.client.patch(
            f"{self.url}/{producto.pk}", {"stock": 9}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.data)
        producto.refresh_from_db()
        self.assertEqual(producto.stock, 9)
        self.assertEqual(producto.price, precio)
        self.assertEqual(producto.sku, "base-1")

    def test_patch_rechaza_sku_de_otro_producto(self):
        self.producto(sku="ocupado")
        otro = self.producto(sku="libre")

        response = self.client.patch(
            f"{self.url}/{otro.pk}", {"sku": "ocupado"}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("sku", response.data)
        otro.refresh_from_db()
        self.assertEqual(otro.sku, "libre")

    def test_patch_rechaza_cambiar_a_marca_inactiva(self):
        producto = self.producto()
        inactiva = Brand.objects.create(name="Marca inactiva", active=False)

        response = self.client.patch(
            f"{self.url}/{producto.pk}", {"brand": inactiva.pk}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("brand", response.data)
        producto.refresh_from_db()
        self.assertEqual(producto.brand_id, self.marca.pk)

    def test_reactivar_con_marca_inactiva_devuelve_400(self):
        inactiva = Brand.objects.create(name="Marca vieja", active=False)
        producto = self.crear_producto(
            marca=inactiva,
            categoria=self.categoria,
            sku="viejo-1",
            active=False,
        )

        response = self.client.patch(
            f"{self.url}/{producto.pk}", {"active": True}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.data)
        producto.refresh_from_db()
        self.assertFalse(producto.active)

    def test_reactivar_con_categoria_inactiva_devuelve_400(self):
        inactiva = Category.objects.create(
            name="Categoria vieja", slug="categoria-vieja", active=False
        )
        producto = self.crear_producto(
            marca=self.marca,
            categoria=inactiva,
            sku="viejo-2",
            active=False,
        )

        response = self.client.patch(
            f"{self.url}/{producto.pk}", {"active": True}, format="json"
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("non_field_errors", response.data)
        producto.refresh_from_db()
        self.assertFalse(producto.active)

    def test_reactivar_y_cambiar_marca_y_categoria_en_la_misma_peticion(self):
        marca_inactiva = Brand.objects.create(name="Marca vieja", active=False)
        categoria_inactiva = Category.objects.create(
            name="Categoria vieja", slug="categoria-vieja", active=False
        )
        producto = self.crear_producto(
            marca=marca_inactiva,
            categoria=categoria_inactiva,
            sku="viejo-3",
            active=False,
        )

        response = self.client.patch(
            f"{self.url}/{producto.pk}",
            {
                "active": True,
                "brand": self.marca.pk,
                "category": self.categoria.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.data)
        producto.refresh_from_db()
        self.assertTrue(producto.active)
        self.assertEqual(producto.brand_id, self.marca.pk)
        self.assertEqual(producto.category_id, self.categoria.pk)

    def test_producto_inexistente_devuelve_404(self):
        url = f"{self.url}/999999"

        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.patch(url, {"stock": 1}, format="json").status_code,
            404,
        )
        self.assertEqual(self.client.delete(url).status_code, 404)


class ProductListAndDeleteTests(ProductTestBase):
    def setUp(self):
        super().setUp()
        self.autenticar()

    def test_listado_solo_incluye_productos_activos(self):
        activo_1 = self.producto(sku="activo-1")
        activo_2 = self.producto(sku="activo-2")
        inactivo = self.producto(sku="inactivo-1", active=False)

        ids = self.ids_del_listado()

        self.assertCountEqual(ids, [activo_1.pk, activo_2.pk])
        self.assertNotIn(inactivo.pk, ids)

    def test_detalle_conserva_producto_inactivo(self):
        inactivo = self.producto(sku="inactivo-2", active=False)

        response = self.client.get(f"{self.url}/{inactivo.pk}")

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.data["active"])

    def test_delete_es_borrado_logico(self):
        producto = self.producto()

        response = self.client.delete(f"{self.url}/{producto.pk}")

        self.assertEqual(response.status_code, 204)
        self.assertTrue(Product.objects.filter(pk=producto.pk).exists())
        producto.refresh_from_db()
        self.assertFalse(producto.active)
        self.assertNotIn(producto.pk, self.ids_del_listado())
        self.assertEqual(
            self.client.get(f"{self.url}/{producto.pk}").status_code, 200
        )

    def test_borrado_logico_conserva_imagenes_y_archivos(self):
        producto = self.producto()
        imagen = ProductImage.objects.create(
            product=producto, image=make_image_file()
        )
        storage = imagen.image.storage
        nombre = imagen.image.name

        with self.captureOnCommitCallbacks(execute=True) as callbacks:
            response = self.client.delete(f"{self.url}/{producto.pk}")

        self.assertEqual(response.status_code, 204)
        self.assertEqual(len(callbacks), 0)
        self.assertTrue(ProductImage.objects.filter(pk=imagen.pk).exists())
        self.assertTrue(storage.exists(nombre))

    def test_listado_usa_el_serializer_resumido(self):
        self.producto()

        response = self.client.get(self.url)
        item = response.data["results"][0]

        self.assertEqual(
            set(item),
            {
                "id", "name", "sku", "price", "stock",
                "active", "brand", "category",
            },
        )
        self.assertEqual(
            dict(item["brand"]),
            {"id": self.marca.pk, "name": self.marca.name},
        )
        self.assertEqual(
            dict(item["category"]),
            {"id": self.categoria.pk, "name": self.categoria.name},
        )


class ProductDatabaseConstraintTests(ProductTestBase):
    def crear_directo(self, **extra):
        datos = {
            "brand": self.marca,
            "category": self.categoria,
            "name": "Directo",
            "sku": "directo-1",
            "description": "Creado desde el ORM",
            "price": Decimal("1.00"),
            "stock": 1,
        }
        datos.update(extra)
        return Product.objects.create(**datos)

    def test_base_de_datos_rechaza_stock_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_directo(stock=-1)

    def test_base_de_datos_rechaza_precio_negativo(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_directo(price=Decimal("-0.01"))

    def test_base_de_datos_rechaza_sku_duplicado(self):
        self.crear_directo(sku="duplicado")

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.crear_directo(sku="duplicado")

    def test_no_se_puede_borrar_una_marca_con_productos(self):
        self.crear_directo()

        with self.assertRaises(ProtectedError):
            self.marca.delete()

    def test_no_se_puede_borrar_una_categoria_con_productos(self):
        self.crear_directo()

        with self.assertRaises(ProtectedError):
            self.categoria.delete()