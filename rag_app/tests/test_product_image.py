from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rag_app.models import ProductImage
from .base import BaseAPITestCase, make_image_file


class ProductImageValidationTests(BaseAPITestCase):
    url = "/api/product-images"

    def setUp(self):
        super().setUp()
        self.autenticar()
        self.producto = self.crear_producto()

    def subir(self, archivo):
        return self.client.post(
            self.url,
            {"product": self.producto.pk, "image": archivo},
            format="multipart",
        )

    def test_acepta_formatos_permitidos(self):
        casos = [("a.png", "PNG"), ("a.jpg", "JPEG"), ("a.webp", "WEBP")]
        for nombre, formato in casos:
            with self.subTest(formato=formato):
                response = self.subir(make_image_file(nombre, formato))
                self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(ProductImage.objects.count(), 3)

    def test_rechaza_archivo_que_no_es_imagen(self):
        falso = SimpleUploadedFile(
            "falso.jpg", b"esto no es una imagen", content_type="image/jpeg"
        )
        response = self.subir(falso)
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.data)
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_rechaza_formato_no_permitido(self):
        response = self.subir(make_image_file("a.gif", "GIF"))
        self.assertEqual(response.status_code, 400)
        self.assertIn("GIF", str(response.data["image"]))
        self.assertEqual(ProductImage.objects.count(), 0)

    @override_settings(IMAGE_MAX_BYTES=1)
    def test_rechaza_archivo_que_supera_el_limite_de_bytes(self):
        response = self.subir(make_image_file())
        self.assertEqual(response.status_code, 400)
        self.assertIn("tamaño", str(response.data["image"]))
        self.assertEqual(ProductImage.objects.count(), 0)

    @override_settings(IMAGE_MAX_PIXELS=50)
    def test_rechaza_imagen_con_demasiados_pixeles(self):
        response = self.subir(make_image_file(size=(10, 10)))
        self.assertEqual(response.status_code, 400)
        self.assertIn("píxeles", str(response.data["image"]))
        self.assertEqual(ProductImage.objects.count(), 0)

    def test_patch_sin_archivo_no_dispara_la_validacion(self):
        imagen = ProductImage.objects.create(
            product=self.producto, image=make_image_file()
        )
        with override_settings(IMAGE_MAX_BYTES=1, IMAGE_MAX_PIXELS=1):
            response = self.client.patch(
                f"{self.url}/{imagen.pk}",
                {"is_primary": True},
                format="json",
            )
        self.assertEqual(response.status_code, 200, response.data)
        imagen.refresh_from_db()
        self.assertTrue(imagen.is_primary)

    def test_subida_anonima_devuelve_401(self):
        self.client.force_authenticate(user=None)
        response = self.subir(make_image_file())
        self.assertEqual(response.status_code, 401)
        self.assertEqual(ProductImage.objects.count(), 0)