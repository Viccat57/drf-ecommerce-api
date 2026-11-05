from decimal import Decimal
from rest_framework.test import APITestCase
from rag_app.models import Brand, Category, Product


class BaseAPITestCase(APITestCase):
    def crear_producto(self, marca=None, categoria=None, sku="sku-1", **extra):
        marca = marca or Brand.objects.get_or_create(name="MarcaBase")[0]
        categoria = categoria or Category.objects.get_or_create(
            slug="categoria-base", defaults={"name": "CategoriaBase"}
        )[0]
        return Product.objects.create(
            name="Test_product", sku=sku, description="test product",
            price=Decimal("1.01"), brand=marca, category=categoria, **extra,
        )