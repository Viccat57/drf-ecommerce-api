from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from rag_app.models import Brand


class AuthenticationTests(APITestCase):
    brands_url = "/api/brands"
    token_url = "/api/auth/token"

    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="usuario-auth",
            password="clave-solo-tests",
        )
        self.brand = Brand.objects.create(name="Marca existente")

    def usar_token(self):
        token = Token.objects.create(user=self.user)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token.key}"
        )
        return token

    def test_catalogo_permite_lectura_anonima(self):
        response = self.client.get(self.brands_url)
        self.assertEqual(response.status_code, 200)

    def test_creacion_anonima_devuelve_401(self):
        response = self.client.post(
            self.brands_url,
            {"name": "Marca nueva"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            Brand.objects.filter(name="Marca nueva").exists()
        )

    def test_modificacion_anonima_devuelve_401(self):
        response = self.client.patch(
            f"{self.brands_url}/{self.brand.pk}",
            {"name": "Nombre cambiado"},
            format="json",
        )

        self.assertEqual(response.status_code, 401)
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.name, "Marca existente")

    def test_borrado_anonimo_devuelve_401(self):
        response = self.client.delete(
            f"{self.brands_url}/{self.brand.pk}"
        )

        self.assertEqual(response.status_code, 401)
        self.brand.refresh_from_db()
        self.assertTrue(self.brand.active)

    def test_usuario_sin_roles_puede_crear_con_token(self):
        self.usar_token()

        response = self.client.post(
            self.brands_url,
            {"name": "Marca nueva"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(
            Brand.objects.filter(name="Marca nueva").exists()
        )

    def test_usuario_con_token_puede_modificar(self):
        self.usar_token()

        response = self.client.patch(
            f"{self.brands_url}/{self.brand.pk}",
            {"name": "Nombre cambiado"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.brand.refresh_from_db()
        self.assertEqual(self.brand.name, "Nombre cambiado")

    def test_usuario_con_token_puede_desactivar(self):
        self.usar_token()

        response = self.client.delete(
            f"{self.brands_url}/{self.brand.pk}"
        )

        self.assertEqual(response.status_code, 204)
        self.brand.refresh_from_db()
        self.assertFalse(self.brand.active)

    def test_token_invalido_devuelve_401(self):
        self.client.credentials(
            HTTP_AUTHORIZATION="Token token-invalido"
        )

        response = self.client.get(self.brands_url)

        self.assertEqual(response.status_code, 401)

    def test_credenciales_correctas_devuelven_token(self):
        response = self.client.post(
            self.token_url,
            {
                "username": "usuario-auth",
                "password": "clave-solo-tests",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["token"],
            Token.objects.get(user=self.user).key,
        )

    def test_credenciales_incorrectas_devuelven_400(self):
        response = self.client.post(
            self.token_url,
            {
                "username": "usuario-auth",
                "password": "incorrecta",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(
            Token.objects.filter(user=self.user).exists()
        )