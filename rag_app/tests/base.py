from decimal import Decimal
from django.contrib.auth import get_user_model
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

    def autenticar(self):
        user = get_user_model().objects.create_user(
            username="usuario-pruebas",
            password="clave-solo-tests",
        )
        self.client.force_authenticate(user=user)
        return user

DIM = Product._meta.get_field("embedding").dimensions

def vec(*head):
    v = [0.0] * DIM
    for i, x in enumerate(head):
        v[i] = float(x)
    return v