from django.contrib import admin
from .models import Brand,Category,Product,ProductImage,ProductReview

admin.site.register([Brand,Category,Product,ProductReview,ProductImage])
