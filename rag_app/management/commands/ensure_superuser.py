import os
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

class Command(BaseCommand):
    def handle(self, *args, **opts):
        User = get_user_model()
        name = os.environ.get("DJANGO_SUPERUSER_USERNAME", "admin")
        pw_file = os.environ.get("DJANGO_SUPERUSER_PASSWORD_FILE")
        if pw_file:
            pw = Path(pw_file).read_text().strip()
        else:
            pw = os.environ["DJANGO_SUPERUSER_PASSWORD"]
        if User.objects.filter(username=name).exists():
            self.stdout.write("Superusuario ya existe; no se modifica.")
            return
        User.objects.create_superuser(name, os.environ.get("DJANGO_SUPERUSER_EMAIL", ""), pw)
        self.stdout.write(f"Superusuario '{name}' creado.")