from django.conf import settings
from django.core.management.base import BaseCommand
from rag_app.ai import (
    embedding_hash,
    generate_embedding,
    product_embedding_text,)
from rag_app.models import Product


class Command(BaseCommand):
    help = "Genera embeddings de productos activos nuevos o modificados."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Regenera los embeddings aunque el texto y el modelo no hayan cambiado.",
        )

    def handle(self, *args, **options):
        if not settings.AI_ENABLED:
            self.stderr.write("AI_ENABLED=0: no se generan embeddings.")
            return

        products = (
            Product.objects
            .filter(active=True)
            .select_related("category")
            .order_by("pk")
        )

        total = products.count()
        generated = 0
        skipped = 0

        self.stdout.write(f"Procesando {total} productos...")

        for i, product in enumerate(products, 1):
            text = product_embedding_text(product)
            current_hash = embedding_hash(text)

            if (
                not options["force"]
                and product.embedding is not None
                and product.embedding_hash == current_hash
            ):
                skipped += 1
                self.stdout.write(f"[{i}/{total}] Sin cambios: {product.name}")
                continue

            product.embedding = generate_embedding(text)
            product.embedding_hash = current_hash
            product.save(update_fields=["embedding", "embedding_hash"])

            generated += 1
            self.stdout.write(f"[{i}/{total}] Generado: {product.name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"Listo. Generados: {generated}. Saltados: {skipped}."
            )
        )