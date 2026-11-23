from decimal import Decimal
from io import StringIO
from django.core.management import call_command
from django.test import TestCase
from rag_app.models import Brand, Category, Product


class SeedDemoTests(TestCase):
    def ejecutar_seed(self):
        call_command("seed_demo", stdout=StringIO())

    def estado_catalogo(self):
        return {
            "marcas": list(
                Brand.objects.order_by("pk").values()
            ),
            "categorias": list(
                Category.objects.order_by("pk").values()
            ),
            "productos": list(
                Product.objects.order_by("pk").values()
            ),
        }

    def test_crea_catalogo_y_relaciones_esperadas(self):
        self.ejecutar_seed()

        self.assertEqual(Brand.objects.count(), 6)
        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(Product.objects.count(), 15)

        laptops = Category.objects.get(slug="laptops")
        computacion = Category.objects.get(slug="computacion")
        self.assertEqual(laptops.parent_id, computacion.pk)

        producto = Product.objects.get(sku="VIVO-S16")
        self.assertEqual(producto.brand.name, "Asus")
        self.assertEqual(producto.category_id, laptops.pk)
        self.assertEqual(producto.price, Decimal("18155.32"))
        self.assertEqual(producto.stock, 38)
        self.assertEqual(producto.specifications["ram_gb"], 16)

        self.assertFalse(
            Product.objects.get(sku="THINK-T14S").active
        )
        self.assertEqual(
            Product.objects.get(sku="UGREEN-HUB").stock, 0
        )

    def test_repetir_seed_conserva_estado_e_identificadores(self):
        self.ejecutar_seed()
        anterior = self.estado_catalogo()

        self.ejecutar_seed()

        self.assertEqual(self.estado_catalogo(), anterior)

    def test_restaura_campos_demo_sin_recrear_el_producto(self):
        self.ejecutar_seed()

        producto = Product.objects.get(sku="VIVO-S16")
        pk_original = producto.pk

        Product.objects.filter(pk=pk_original).update(
            name="Nombre modificado",
            price=Decimal("1.00"),
            stock=999,
            specifications={"modificado": True},
        )
        Category.objects.filter(slug="laptops").update(
            name="Nombre modificado",
            parent=None,
        )

        self.ejecutar_seed()

        producto.refresh_from_db()
        self.assertEqual(producto.pk, pk_original)
        self.assertEqual(producto.name, "ASUS Vivobook S16")
        self.assertEqual(producto.price, Decimal("18155.32"))
        self.assertEqual(producto.stock, 38)
        self.assertEqual(producto.specifications["ram_gb"], 16)
        self.assertNotIn("modificado", producto.specifications)

        laptops = Category.objects.get(slug="laptops")
        self.assertEqual(laptops.name, "Laptops")
        self.assertEqual(laptops.parent.slug, "computacion")

        self.assertEqual(Product.objects.count(), 15)

    def test_conserva_registros_ajenos_al_catalogo_demo(self):
        marca = Brand.objects.create(name="Marca externa")
        categoria = Category.objects.create(
            name="Categoria externa",
            slug="categoria-externa",
        )
        producto = Product.objects.create(
            brand=marca,
            category=categoria,
            name="Producto externo",
            sku="EXTERNO-1",
            description="No pertenece al seed",
            price=Decimal("25.50"),
            stock=7,
            specifications={"externo": True},
            active=False,
        )

        anterior = Product.objects.values().get(pk=producto.pk)

        self.ejecutar_seed()
        self.ejecutar_seed()

        self.assertEqual(
            Product.objects.values().get(pk=producto.pk),
            anterior,
        )
        self.assertTrue(
            Brand.objects.filter(pk=marca.pk, name="Marca externa").exists()
        )
        self.assertTrue(
            Category.objects.filter(
                pk=categoria.pk,
                slug="categoria-externa",
            ).exists()
        )
        self.assertEqual(Product.objects.count(), 16)