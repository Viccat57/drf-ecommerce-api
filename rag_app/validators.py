from django.conf import settings
from django.core.exceptions import ValidationError
from PIL import Image


def validate_product_image(file):
    if file.size > settings.IMAGE_MAX_BYTES:
        raise ValidationError(
            "La imagen supera el tamaño máximo permitido "
            f"de {settings.IMAGE_MAX_BYTES} bytes."
        )

    try:
        file.seek(0)
        with Image.open(file) as img:
            image_format = img.format
            width, height = img.size
            img.verify()
    except (OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValidationError("El archivo no es una imagen válida.")
    finally:
        file.seek(0)

    if image_format not in settings.IMAGE_ALLOWED_FORMATS:
        permitidos = ", ".join(sorted(settings.IMAGE_ALLOWED_FORMATS))
        raise ValidationError(
            f"Formato no permitido ({image_format}). Usa: {permitidos}."
        )

    if width * height > settings.IMAGE_MAX_PIXELS:
        raise ValidationError("La imagen tiene demasiados píxeles.")