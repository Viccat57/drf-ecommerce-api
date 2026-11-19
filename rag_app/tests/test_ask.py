from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from unittest.mock import patch


class AskFlagTests(APITestCase):
    @override_settings(AI_ENABLED=False)
    def test_503_con_flag_apagado(self):
        r = self.client.post(reverse('ia-ask'), {"query": "hola"}, format="json")
        self.assertEqual(r.status_code, 503)

    @override_settings(AI_ENABLED=True)
    def test_400_sin_query(self):
        r = self.client.post(reverse('ia-ask'), {}, format="json")
        self.assertEqual(r.status_code, 400)
    
    @override_settings(AI_ENABLED=True)
    @patch("rag_app.views.generate_response")
    @patch("rag_app.views.search_products", return_value=[])
    def test_sin_resultados_no_llama_al_llm(self, search, gen):
        r = self.client.post(reverse("ia-ask"), {"query": "algo raro"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["products"], [])
        gen.assert_not_called()    