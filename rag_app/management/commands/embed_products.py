from django.core.management.base import BaseCommand
from rag_app.models import Product
from rag_app.ai import generate_embedding

class Command(BaseCommand):
    help = 'Genera y guarda embeddings para todos los productos activos'

    def handle(self, *args, **options):
        products = Product.objects.filter(active=True)
        total = products.count()
        self.stdout.write(f'Procesando {total} productos...')
        for i, product in enumerate(products, 1):
            text = f"{product.name}. {product.description}. {product.specifications}"
            embedding = generate_embedding(text)
            product.embedding = embedding
            product.save(update_fields=['embedding'])
            self.stdout.write(f'[{i}/{total}] {product.name}')
        self.stdout.write(self.style.SUCCESS('Listo.'))