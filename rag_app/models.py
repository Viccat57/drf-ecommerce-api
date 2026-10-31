from django.db import models
from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator

# Create your models here.
class Brand(models.Model):
    name = models.CharField(max_length=100)
    active = models.BooleanField(default=True)
    def __str__(self):
        return self.name
    
class Category(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(unique=True, max_length=100)
    active = models.BooleanField(default=True)
    parent = models.ForeignKey(
    "self", null=True, blank=True,
    on_delete=models.PROTECT, related_name="children",
    )
    
    def __str__(self):
        return self.name
    
    class Meta:
        constraints =[
            models.CheckConstraint(
                condition=~models.Q(parent=models.F('id')),
                name='parent_no_puede_ser_uno_mismo',
            )
        ]
    
class Product(models.Model):
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    name = models.CharField(max_length=150)
    sku = models.CharField(max_length=20,unique=True)
    description = models.TextField()
    price = models.DecimalField(max_digits=10,decimal_places=2)
    stock = models.IntegerField(default=0)
    specifications = models.JSONField(default=dict)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'{self.name} | stock: {self.stock} | ${self.price}'
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(stock__gte=0),
                name='product_stock_gte_0',
            ),
            models.CheckConstraint(
              condition=models.Q(price__gte=0),
              name='product_price_gte_0',  
            ),
        ]
    
class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    image = models.ImageField(upload_to="products/%Y/%m/", max_length=255)
    is_primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        nombre = str(self.image)
        return nombre
    
    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['product'], 
                condition=models.Q(is_primary=True),
                name='unique_primary_photo'
            )
        ]
    
class ProductReview(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, db_index=False)           
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    rating = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f'rating: {self.rating} | comment: {self.comment}'
    
    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__range=(1,5)),
                name='review_rating_range_1_5',
            ),
            models.UniqueConstraint(
                fields=['product','user'],
                name='unique_review_per_user',
            ),
        ]