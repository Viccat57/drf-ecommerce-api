import logging
from functools import partial
from django.db import transaction
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver
from .models import ProductImage


logger = logging.getLogger(__name__)


def delete_unreferenced_image(storage, name, using):
    if not name:
        return

    try:
        if ProductImage.objects.using(using).filter(image=name).exists():
            return

        storage.delete(name)
    except Exception:
        logger.exception(
            "No se pudo eliminar el archivo de imagen %s del almacenamiento.",
            name,
        )


def schedule_image_deletion(storage, name, using):
    if name:
        transaction.on_commit(
            partial(delete_unreferenced_image, storage, name, using),
            using=using,
        )


@receiver(
    pre_save,
    sender=ProductImage,
    dispatch_uid="product_image_remember_previous_file",
)
def remember_previous_image(sender, instance, using, raw=False, **kwargs):
    instance._previous_image_name = None

    if raw or instance._state.adding:
        return

    instance._previous_image_name = (
        sender.objects.using(using)
        .filter(pk=instance.pk)
        .values_list("image", flat=True)
        .first()
    )


@receiver(
    post_save,
    sender=ProductImage,
    dispatch_uid="product_image_cleanup_replaced_file",
)
def cleanup_replaced_image(
    sender, instance, using, raw=False, update_fields=None, **kwargs
):
    previous_name = getattr(instance, "_previous_image_name", None)
    instance._previous_image_name = None

    if raw or (update_fields is not None and "image" not in update_fields):
        return

    if previous_name and previous_name != instance.image.name:
        schedule_image_deletion(
            instance.image.storage,
            previous_name,
            using,
        )


@receiver(
    post_delete,
    sender=ProductImage,
    dispatch_uid="product_image_cleanup_deleted_file",
)
def cleanup_deleted_image(sender, instance, using, **kwargs):
    schedule_image_deletion(
        instance.image.storage,
        instance.image.name,
        using,
    )