from decimal import Decimal
from rest_framework.pagination import PageNumberPagination
from rest_framework.test import APIRequestFactory, APITestCase
from rag_app.models import Brand, Category, Product
from rag_app.views import ProductViewSet


class QueryTestPagination(PageNumberPagination):
    page_size = 20


class ProductQueryTests(APITestCase):
    def setUp(self):
        super().setUp()
        self.factory = APIRequestFactory()

    def crear_producto(self, indice):
        marca = Brand.objects.create(
            name=f"Marca consultas {indice}"
        )
        categoria = Category.objects.create(
            name=f"Categoria consultas {indice}",
            slug=f"categoria-consultas-{indice}",
        )

        return Product.objects.create(
            brand=marca,
            category=categoria,
            name=f"Producto consultas {indice}",
            sku=f"QUERY-{indice}",
            description="Producto para medir consultas",
            price=Decimal("10.00"),
            stock=5,
        )

    def obtener_listado(self):
        vista = ProductViewSet.as_view(
            {"get": "list"},
            pagination_class=QueryTestPagination,
        )
        request = self.factory.get("/api/products")

        with self.assertNumQueries(2):
            response = vista(request)
            response.render()

        self.assertEqual(response.status_code, 200)
        return response.data

    def test_listado_mantiene_dos_consultas_al_crecer(self):
        primero = self.crear_producto(0)

        datos = self.obtener_listado()

        self.assertEqual(datos["count"], 1)
        self.assertEqual(len(datos["results"]), 1)
        self.assertEqual(datos["results"][0]["id"], primero.pk)

        for indice in range(1, 10):
            self.crear_producto(indice)

        datos = self.obtener_listado()

        self.assertEqual(datos["count"], 10)
        self.assertEqual(len(datos["results"]), 10)

        for item in datos["results"]:
            self.assertIn("name", item["brand"])
            self.assertIn("name", item["category"])

    def test_detalle_se_resuelve_con_dos_consultas(self):
        producto = self.crear_producto(0)
        vista = ProductViewSet.as_view({"get": "retrieve"})
        request = self.factory.get(
            f"/api/products/{producto.pk}"
        )

        with self.assertNumQueries(2):
            response = vista(request, pk=producto.pk)
            response.render()

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["id"], producto.pk)
        self.assertEqual(response.data["brand"], producto.brand_id)
        self.assertEqual(
            response.data["category"], producto.category_id
        )
        self.assertEqual(response.data["average_rating"], 0.0)
        self.assertEqual(response.data["reviews_count"], 0)
        self.assertEqual(response.data["images"], [])