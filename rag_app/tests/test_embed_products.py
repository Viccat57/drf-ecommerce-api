from io import StringIO
from unittest.mock import patch
from django.core.management import call_command
from django.test import override_settings
from rag_app.ai import embedding_hash, product_embedding_text
from .base import BaseAPITestCase, vec

@override_settings(AI_ENABLED=True)
class EmbedProductsTests(BaseAPITestCase):
    def run_command(self, **options):
        output = StringIO()
        call_command("embed_products", stdout=output, **options)
        return output.getvalue()

    @patch(
        "rag_app.management.commands.embed_products.generate_embedding",
        return_value=vec(1, 0),
    )
    def test_genera_guarda_hash_y_salta_sin_cambios(self, generate):
        product = self.crear_producto()

        self.run_command()
        product.refresh_from_db()

        self.assertIsNotNone(product.embedding)
        self.assertEqual(
            product.embedding_hash,
            embedding_hash(product_embedding_text(product)),
        )
        generate.assert_called_once_with(product_embedding_text(product))

        output = self.run_command()

        self.assertEqual(generate.call_count, 1)
        self.assertIn("Generados: 0. Saltados: 1.", output)

    @patch(
        "rag_app.management.commands.embed_products.generate_embedding",
        return_value=vec(1, 0),
    )
    def test_force_regenera_aunque_no_haya_cambios(self, generate):
        self.crear_producto()

        self.run_command()
        self.run_command(force=True)

        self.assertEqual(generate.call_count, 2)

    @patch(
        "rag_app.management.commands.embed_products.generate_embedding",
        return_value=vec(1, 0),
    )
    def test_regenera_si_cambia_el_texto(self, generate):
        product = self.crear_producto()
        self.run_command()

        product.refresh_from_db()
        previous_hash = product.embedding_hash

        product.description = "Descripción actualizada"
        product.save(update_fields=["description"])

        self.run_command()
        product.refresh_from_db()

        self.assertEqual(generate.call_count, 2)
        self.assertNotEqual(product.embedding_hash, previous_hash)

    @patch(
        "rag_app.management.commands.embed_products.generate_embedding",
        return_value=vec(1, 0),
    )
    def test_regenera_si_falta_embedding_aunque_coincida_hash(self, generate):
        product = self.crear_producto()
        product.embedding_hash = embedding_hash(product_embedding_text(product))
        product.save(update_fields=["embedding_hash"])

        self.run_command()

        generate.assert_called_once()

    @override_settings(AI_ENABLED=False)
    @patch("rag_app.management.commands.embed_products.generate_embedding")
    def test_no_genera_con_flag_apagado(self, generate):
        self.crear_producto()
        error_output = StringIO()

        call_command("embed_products", stderr=error_output)

        generate.assert_not_called()
        self.assertIn("AI_ENABLED=0", error_output.getvalue())

    @patch(
        "rag_app.management.commands.embed_products.generate_embedding",
        return_value=vec(1, 0),
    )
    def test_regenera_si_cambia_el_modelo(self, generate):
        product = self.crear_producto()

        with patch.dict("os.environ", {"AI_EMBED_MODEL": "modelo-a"}):
            self.run_command()

        product.refresh_from_db()
        previous_hash = product.embedding_hash

        with patch.dict("os.environ", {"AI_EMBED_MODEL": "modelo-b"}):
            self.run_command()

            product.refresh_from_db()
            self.assertEqual(
                product.embedding_hash,
                embedding_hash(product_embedding_text(product)),
            )

        self.assertEqual(generate.call_count, 2)
        self.assertNotEqual(product.embedding_hash, previous_hash)