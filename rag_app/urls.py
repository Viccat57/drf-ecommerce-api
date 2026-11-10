from rest_framework.routers import DefaultRouter
from . import views
from django.urls import path

router = DefaultRouter(trailing_slash=False)
router.register('brands', views.BrandViewSet)
router.register('categories', views.CategoryViewSet)
router.register('products', views.ProductViewSet)
router.register('product-images',views.ProductImageViewSet)

urlpatterns = router.urls + [
    path('ia/ask', views.AskView.as_view(), name='ia-ask'),
]
