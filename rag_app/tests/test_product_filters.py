from urllib.parse import urlsplit
from decimal import Decimal
from rest_framework.test import APITestCase
from rag_app.models import Brand, Category, Product


class ProductFilterTests(APITestCase):
    url = "/api/products"

    def setUp(self):
        self.brand_a = Brand.objects.create(name="Marca Alfa")
        self.brand_b = Brand.objects.create(name="Marca Beta")

        self.parent = Category.objects.create(
            name="Tecnología",
            slug="tecnologia",
        )
        self.child = Category.objects.create(
            name="Portátiles",
            slug="portatiles",
            parent=self.parent,
        )
        self.other = Category.objects.create(
            name="Audio",
            slug="audio",
        )

        self.laptop = self.make_product(
            "laptop",
            name="Laptop ligera",
            price="100.00",
            stock=3,
            category=self.child,
        )
        self.monitor = self.make_product(
            "monitor",
            name="Monitor",
            price="200.00",
            stock=0,
            category=self.parent,
        )
        self.headphones = self.make_product(
            "headphones",
            name="Audífonos",
            price="50.00",
            stock=2,
            brand=self.brand_b,
            category=self.other,
        )
        self.inactive = self.make_product(
            "inactive",
            name="Producto oculto",
            active=False,
        )

    def make_product(self, sku, **extra):
        data = {
            "name": sku,
            "description": "Producto de prueba",
            "price": Decimal("10.00"),
            "stock": 1,
            "brand": self.brand_a,
            "category": self.child,
        }
        data.update(extra)
        return Product.objects.create(sku=sku, **data)

    def get_ids(self, **params):
        response = self.client.get(self.url, params)
        self.assertEqual(response.status_code, 200, response.data)
        return [item["id"] for item in response.data["results"]]

    def test_filter_by_brand(self):
        self.assertCountEqual(
            self.get_ids(brand=self.brand_a.pk),
            [self.laptop.pk, self.monitor.pk],
        )

    def test_parent_category_includes_descendants(self):
        self.assertCountEqual(
            self.get_ids(category=self.parent.pk),
            [self.laptop.pk, self.monitor.pk],
        )

    def test_child_category_excludes_parent_products(self):
        self.assertEqual(
            self.get_ids(category=self.child.pk),
            [self.laptop.pk],
        )

    def test_price_range(self):
        self.assertEqual(
            self.get_ids(min_price="75.00", max_price="150.00"),
            [self.laptop.pk],
        )

    def test_in_stock_true(self):
        self.assertCountEqual(
            self.get_ids(in_stock="true"),
            [self.laptop.pk, self.headphones.pk],
        )

    def test_in_stock_false(self):
        self.assertEqual(
            self.get_ids(in_stock="false"),
            [self.monitor.pk],
        )

    def test_search_by_name(self):
        self.assertEqual(
            self.get_ids(search="Laptop"),
            [self.laptop.pk],
        )

    def test_search_by_brand(self):
        self.assertEqual(
            self.get_ids(search="Beta"),
            [self.headphones.pk],
        )

    def test_price_ordering(self):
        self.assertEqual(
            self.get_ids(ordering="price"),
            [self.headphones.pk, self.laptop.pk, self.monitor.pk],
        )
        self.assertEqual(
            self.get_ids(ordering="-price"),
            [self.monitor.pk, self.laptop.pk, self.headphones.pk],
        )

    def test_filters_can_be_combined(self):
        self.assertEqual(
            self.get_ids(
                brand=self.brand_a.pk,
                category=self.parent.pk,
                in_stock="true",
                max_price="150.00",
                search="Laptop",
            ),
            [self.laptop.pk],
        )

    def test_list_excludes_inactive_products(self):
        self.assertNotIn(self.inactive.pk, self.get_ids())

    def test_invalid_filters_return_400(self):
        for params in (
            {"brand": "abc"},
            {"category": "abc"},
            {"min_price": "abc"},
            {"max_price": "abc"},
        ):
            with self.subTest(params=params):
                response = self.client.get(self.url, params)
                self.assertEqual(response.status_code, 400)

    def test_pagination_preserves_filter_and_ordering(self):
        for index in range(11):
            self.make_product(f"extra-{index}")

        response = self.client.get(
            self.url,
            {"brand": self.brand_a.pk, "ordering": "id"},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 13)
        self.assertEqual(len(response.data["results"]), 10)
        self.assertIsNotNone(response.data["next"])

        first_ids = {
            item["id"] for item in response.data["results"]
        }

        next_url = urlsplit(response.data["next"])
        page_two = self.client.get(
            f"{next_url.path}?{next_url.query}"
        )

        self.assertEqual(page_two.status_code, 200)
        self.assertEqual(len(page_two.data["results"]), 3)

        second_ids = {
            item["id"] for item in page_two.data["results"]
        }
        expected_ids = set(
            Product.objects.filter(
                brand=self.brand_a,
                active=True,
            ).values_list("pk", flat=True)
        )

        self.assertFalse(first_ids & second_ids)
        self.assertEqual(first_ids | second_ids, expected_ids)