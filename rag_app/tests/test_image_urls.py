from urllib.parse import parse_qs, urlsplit
from unittest.mock import Mock, patch
from django.test import SimpleTestCase, override_settings
from rag_app.storage import GarageStorage


TEST_S3_OPTIONS = {
    "access_key": "test-access-key",
    "secret_key": "test-secret-key",
    "bucket_name": "test-images",
    "region_name": "garage",
    "addressing_style": "path",
    "signature_version": "s3v4",
    "querystring_auth": True,
    "querystring_expire": 3600,
}


@override_settings(
    STORAGES={
        "image_urls": {
            "BACKEND": "storages.backends.s3.S3Storage",
            "OPTIONS": {
                **TEST_S3_OPTIONS,
                "endpoint_url": "http://127.0.0.1:3900",
            },
        },
    },
)
class ImageURLTests(SimpleTestCase):
    def crear_storage(self):
        return GarageStorage(
            **TEST_S3_OPTIONS,
            endpoint_url="http://garage:3900",
        )

    def test_url_firmada_utiliza_endpoint_del_host(self):
        storage = self.crear_storage()

        url = storage.url("products/prueba.png")
        partes = urlsplit(url)
        parametros = parse_qs(partes.query)

        self.assertEqual(partes.scheme, "http")
        self.assertEqual(partes.netloc, "127.0.0.1:3900")
        self.assertEqual(
            partes.path,
            "/test-images/products/prueba.png",
        )
        self.assertEqual(
            parametros["X-Amz-Algorithm"],
            ["AWS4-HMAC-SHA256"],
        )
        self.assertIn("X-Amz-Signature", parametros)
        self.assertEqual(parametros["X-Amz-Expires"], ["3600"])

    def test_generar_url_conserva_endpoint_interno(self):
        storage = self.crear_storage()

        storage.url("products/prueba.png")

        self.assertEqual(storage.endpoint_url, "http://garage:3900")
        self.assertEqual(
            storage.connection.meta.client.meta.endpoint_url,
            "http://garage:3900",
        )

    def test_url_delega_parametros_y_expiracion(self):
        storage = self.crear_storage()
        firmador = Mock()
        firmador.url.return_value = "http://enlace-de-prueba"

        with patch(
            "rag_app.storage.storages",
            {"image_urls": firmador},
        ):
            resultado = storage.url(
                "products/prueba.png",
                parameters={"ResponseContentType": "image/png"},
                expire=120,
                http_method="GET",
            )

        self.assertEqual(resultado, "http://enlace-de-prueba")
        firmador.url.assert_called_once_with(
            "products/prueba.png",
            parameters={"ResponseContentType": "image/png"},
            expire=120,
            http_method="GET",
        )