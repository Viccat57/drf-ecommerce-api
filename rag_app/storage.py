from django.core.files.storage import storages
from storages.backends.s3 import S3Storage


class GarageStorage(S3Storage):
    def url(self, name, parameters=None, expire=None, http_method=None):
        return storages["image_urls"].url(
            name,
            parameters=parameters,
            expire=expire,
            http_method=http_method,
        )