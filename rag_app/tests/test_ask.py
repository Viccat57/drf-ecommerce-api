from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase


class AskFlagTests(APITestCase):
    @override_settings(AI_ENABLED=False)
    def test_503_con_flag_apagado(self):
        r = self.client.post(reverse('ia-ask'), {"query": "hola"}, format="json")
        self.assertEqual(r.status_code, 503)

    @override_settings(AI_ENABLED=True)
    def test_400_sin_query(self):
        r = self.client.post(reverse('ia-ask'), {}, format="json")
        self.assertEqual(r.status_code, 400)