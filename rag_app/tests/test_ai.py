import json
from unittest.mock import patch, MagicMock
from django.test import override_settings
from rag_app.ai import search_products, build_retrieval_query, generate_response
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

class BuildRetrievalQueryTests(BaseAPITestCase):
    def test_sin_historial_devuelve_la_pregunta(self):
        self.assertEqual(
            build_retrieval_query('laptop', []),
            'laptop',
        )

    def test_con_historial_antepone_la_ultima_pregunta(self):
        history = [
            {'role': 'user', 'content': 'laptop'},
            {'role': 'assistant', 'content': 'Respuesta'},
            {'role': 'user', 'content': '¿y el más barato?'},
        ]
        self.assertEqual(
            build_retrieval_query('y la más barata?', history),
            '¿y el más barato? y la más barata?',
        )

@patch('rag_app.ai.urllib.request.urlopen')
class GenerateResponseHistoryTests(BaseAPITestCase):
    def test_envia_system_historial_y_pregunta(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(
            {'message': {'content': 'Respuesta'}}
        ).encode()
        urlopen.return_value = response

        history = [
            {'role': 'user', 'content': 'laptop'},
            {'role': 'assistant', 'content': 'Respuesta'},
        ]
        answer = generate_response('y la más barata?', [], history)

        self.assertEqual(answer, 'Respuesta')
        payload = json.loads(
            urlopen.call_args.args[0].data.decode()
        )
        roles = [m['role'] for m in payload['messages']]
        self.assertEqual(
            roles,
            ['system', 'user', 'assistant', 'user'],
        )
        self.assertIn('Contexto:', payload['messages'][-1]['content'])
        self.assertIn('y la más barata?', payload['messages'][-1]['content'])