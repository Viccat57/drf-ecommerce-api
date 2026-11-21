import uuid
from unittest.mock import patch
from django.test import override_settings
from django.urls import reverse
from django.contrib.auth import get_user_model
from rag_app.models import Message, Conversation
from .base import BaseAPITestCase

URL = 'ia-ask'


class AskTests(BaseAPITestCase):
    def setUp(self):
        super().setUp()
        self.user = self.autenticar()

    @override_settings(AI_ENABLED=False)
    def test_503_con_flag_apagado(self):
        r = self.client.post(
            reverse(URL),
            {'query': 'hola'},
            format='json',
        )
        self.assertEqual(r.status_code, 503)

    @override_settings(AI_ENABLED=True)
    def test_400_sin_query(self):
        r = self.client.post(reverse(URL), {}, format='json')
        self.assertEqual(r.status_code, 400)

    @override_settings(AI_ENABLED=True)
    @patch('rag_app.views.generate_response')
    @patch('rag_app.views.search_products', return_value=[])
    def test_sin_resultados_no_llama_al_llm(self, search, gen):
        r = self.client.post(
            reverse(URL),
            {'query': 'algo raro'},
            format='json',
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data['products'], [])
        gen.assert_not_called()

    @override_settings(AI_ENABLED=True)
    @patch('rag_app.views.generate_response')
    @patch('rag_app.views.search_products')
    def test_crea_conversacion_y_guarda_dos_mensajes(self, search, gen):
        producto = self.crear_producto()
        search.return_value = [producto]
        gen.return_value = 'Te recomiendo el producto.'

        r = self.client.post(
            reverse(URL),
            {'query': 'laptop'},
            format='json',
        )

        self.assertEqual(r.status_code, 200)
        conversation_id = r.data['conversation_id']
        self.assertEqual(
            Conversation.objects.get(pk=conversation_id).user_id,
            self.user.pk,
        )

        self.assertEqual(
            Message.objects.filter(
                conversation_id=conversation_id
            ).count(),
            2,
        )
        self.assertEqual(
            Message.objects.filter(
                conversation_id=conversation_id,
                role=Message.Role.USER,
            ).first().content,
            'laptop',
        )
        self.assertEqual(
            Message.objects.filter(
                conversation_id=conversation_id,
                role=Message.Role.ASSISTANT,
            ).first().product_ids,
            [producto.id],
        )

    @override_settings(AI_ENABLED=True)
    @patch('rag_app.views.generate_response')
    @patch('rag_app.views.search_products')
    def test_multiturno_envia_historial(self, search, gen):
        producto = self.crear_producto()
        search.return_value = [producto]
        gen.return_value = 'Respuesta.'

        first = self.client.post(
            reverse(URL),
            {'query': 'laptop'},
            format='json',
        )
        second = self.client.post(
            reverse(URL),
            {
                'query': 'y la más barata?',
                'conversation_id': first.data['conversation_id'],
            },
            format='json',
        )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(
            second.data['conversation_id'],
            first.data['conversation_id'],
        )

        history = gen.call_args.args[2]
        self.assertEqual(
            [m['role'] for m in history],
            ['user', 'assistant'],
        )
        self.assertEqual(history[0]['content'], 'laptop')
        self.assertEqual(history[1]['content'], 'Respuesta.')
        self.assertEqual(
            Message.objects.filter(
                conversation_id=first.data['conversation_id']
            ).count(),
            4,
        )

    @override_settings(AI_ENABLED=True)
    @patch('rag_app.views.generate_response')
    @patch('rag_app.views.search_products')
    def test_conversation_id_inexistente_da_404(self, search, gen):
        r = self.client.post(
            reverse(URL),
            {
                'query': 'hola',
                'conversation_id': str(uuid.uuid4()),
            },
            format='json',
        )

        self.assertEqual(r.status_code, 404)
        search.assert_not_called()
        gen.assert_not_called()

    @override_settings(AI_ENABLED=True)
    @patch("rag_app.views.generate_response")
    @patch("rag_app.views.search_products")
    def test_anonimo_no_puede_usar_chat(self, search, gen):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            reverse(URL),
            {"query": "hola"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(Conversation.objects.count(), 0)
        self.assertEqual(Message.objects.count(), 0)
        search.assert_not_called()
        gen.assert_not_called()


    @override_settings(AI_ENABLED=True)
    @patch("rag_app.views.generate_response")
    @patch("rag_app.views.search_products")
    def test_conversacion_ajena_devuelve_404(self, search, gen):
        other_user = get_user_model().objects.create_user(
            username="otro-usuario",
            password="clave-solo-tests",
        )
        conversation = Conversation.objects.create(user=other_user)
        message = Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content="Mensaje privado de otro usuario",
        )

        response = self.client.post(
            reverse(URL),
            {
                "query": "continúa",
                "conversation_id": str(conversation.pk),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.data,
            {"error": "conversation_id inválido"},
        )
        self.assertEqual(conversation.messages.count(), 1)
        message.refresh_from_db()
        self.assertEqual(
            message.content,
            "Mensaje privado de otro usuario",
        )
        search.assert_not_called()
        gen.assert_not_called()


    @override_settings(AI_ENABLED=True)
    @patch("rag_app.views.generate_response")
    @patch("rag_app.views.search_products")
    def test_conversacion_sin_dueno_devuelve_404(self, search, gen):
        conversation = Conversation.objects.create()

        response = self.client.post(
            reverse(URL),
            {
                "query": "continúa",
                "conversation_id": str(conversation.pk),
            },
            format="json",
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(conversation.messages.count(), 0)
        conversation.refresh_from_db()
        self.assertIsNone(conversation.user_id)
        search.assert_not_called()
        gen.assert_not_called()