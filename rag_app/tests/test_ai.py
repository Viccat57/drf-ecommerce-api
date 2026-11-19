from unittest.mock import patch
from django.test import override_settings
from rag_app.ai import search_products
from .base import BaseAPITestCase, vec


@override_settings(AI_MIN_SIMILARITY=0.5)
class SearchProductsTests(BaseAPITestCase):
    @patch("rag_app.ai.generate_embedding", return_value=vec(1, 0))
    def test_umbral_descarta_irrelevantes(self, _):
        cerca = self.crear_producto(sku="a", stock=1, embedding=vec(1, 0))
        self.crear_producto(sku="b", stock=1, embedding=vec(0, 1))
        ids = [p.id for p in search_products("x")]
        self.assertEqual(ids, [cerca.id])

    @patch("rag_app.ai.generate_embedding", return_value=vec(1, 0))
    def test_ignora_productos_sin_embedding(self, _):
        self.crear_producto(sku="a", stock=1, embedding=None)
        self.assertEqual(search_products("x", min_similarity=-1), [])

    @patch("rag_app.ai.generate_embedding", return_value=vec(1, 0))
    def test_ignora_inactivos_y_sin_stock(self, _):
        self.crear_producto(sku="a", stock=1, active=False, embedding=vec(1, 0))
        self.crear_producto(sku="b", stock=0, embedding=vec(1, 0))
        self.assertEqual(search_products("x"), [])

    @patch("rag_app.ai.generate_embedding", return_value=vec(1, 0))
    def test_respeta_el_limite(self, _):
        for i in range(3):
            self.crear_producto(sku=f"s{i}", stock=1, embedding=vec(1, 0))
        self.assertEqual(len(search_products("x", limit=2)), 2)