from rag_app.serializers import ProductDetailSerializer

from .base import BaseAPITestCase


class ProductDetailSerializerTests(BaseAPITestCase):
    def test_no_expone_campos_internos_de_embeddings(self):
        product = self.crear_producto()

        serializer = ProductDetailSerializer(product)
        data = serializer.data

        self.assertNotIn('embedding', serializer.fields)
        self.assertNotIn('embedding_hash', serializer.fields)
        self.assertNotIn('embedding', data)
        self.assertNotIn('embedding_hash', data)

        self.assertEqual(data['id'], product.id)
        self.assertEqual(data['name'], product.name)
        self.assertIn('description', data)
        self.assertIn('specifications', data)
        self.assertIn('price', data)