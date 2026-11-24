from rest_framework import serializers
from .models import Brand,Category, Product, ProductImage,ProductReview
from django.db import transaction, IntegrityError
from django.shortcuts import get_object_or_404

class BrandSerializer(serializers.ModelSerializer):
    
    def validate_active(self, value):
            if value or self.instance is None:
                return value
            
            if self.instance.product_set.filter(active=True).exists():
                raise serializers.ValidationError(
                    'No se puede desactivar una marca con productos activos.'
                )
                
            return value  
        
    class Meta:
        model = Brand
        fields = '__all__'

class BrandProductSerializer(serializers.ModelSerializer):  
    class Meta:
        model = Brand
        fields = ['id','name']
        
class CategorySerializer(serializers.ModelSerializer):
    
    def validate_active(self, value):
        if value or self.instance is None:
            return value
        
        if self.instance.children.filter(active=True).exists():
            raise serializers.ValidationError(
                'No se puede desactivar una categoria con subcategorias activas.'
            )
        
        if self.instance.product_set.filter(active=True).exists():
            raise serializers.ValidationError(
                'No se puede desactivar una categoria con productos activos.'
            )    
                
        return value
    
    def validate_parent(self, value):
        if value is None or self.instance is None:
            return value
            
        actual = value
        vistos = set()
        while actual is not None:
            if actual.id in vistos:
               raise serializers.ValidationError(
                   'Bucle detectado, los datos ya estaban en un ciclo desde antes.') 
            vistos.add(actual.id)
               
            if actual == self.instance:
                raise serializers.ValidationError(
                    'Bucle detectado, no puede haber ciclos dentro de las categorías'
                )
            actual = actual.parent    
                
        return value    
    
    class Meta:
        model = Category
        fields = '__all__'
 
class CategoryProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id','name']        
    

class ProductListSerializer(serializers.ModelSerializer):
    brand = BrandProductSerializer(read_only=True)
    category = CategoryProductSerializer(read_only=True)
    average_rating = serializers.FloatField(
        read_only=True,
        default=0.0,
    )
    reviews_count = serializers.IntegerField(
        read_only=True,
        default=0,
    )

    class Meta:
        model = Product
        fields = [
            "id", "name", "sku", "price", "stock",
            "active", "brand", "category",
            "average_rating", "reviews_count",
        ]
        
class ProductDetailSerializer(serializers.ModelSerializer):
    average_rating = serializers.FloatField(
    read_only=True,
    default=0.0,
    )
    reviews_count = serializers.IntegerField(
        read_only=True,
        default=0,
    )
    images = serializers.SerializerMethodField()

    def get_images(self, obj):
        imagenes = getattr(obj, "ordered_images", None)

        if imagenes is None:
            imagenes = obj.productimage_set.order_by(
                "-is_primary", "created_at", "pk"
            )

        return ProductImageSerializer(
            imagenes,
            many=True,
            context=self.context,
        ).data
    
    def validate_price(self,value):
        if value < 0:
            raise serializers.ValidationError(
                'El precio debe ser igual o mayor a cero (0).'
            )
        return value
    
    def validate_stock(self,value):
        if value < 0:
            raise serializers.ValidationError(
                'El stock debe ser igual o mayor a cero (0).'
            ) 
        return value
    
    def validate_brand(self, value):
        if not value.active:
            raise serializers.ValidationError(
                'No puedes añadir el producto a una marca inactiva.'
            )
        return value    
    def validate_category(self, value):
        if not value.active:
            raise serializers.ValidationError(
                'No puedes añadir el producto a una categoria inactiva.'
            )
        return value  
    
    def validate(self, attrs):
        if self.instance is None:
            return attrs
                
        marca = attrs.get('brand', self.instance.brand)
        categoria = attrs.get('category', self.instance.category)
        estado = attrs.get('active', self.instance.active)
        
        if estado:
            if not marca.active:
                raise serializers.ValidationError(
                    'No puedes reactivar un producto si su marca está inactiva.'
                    )
            if not categoria.active:
                raise serializers.ValidationError(
                    'No puedes reactivar un producto si su categoría está inactiva.'
                    )    
        
        return attrs   
         
    class Meta:
        model = Product
        exclude = ['embedding', 'embedding_hash']
        
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = "__all__"
        read_only_fields = ["id", "created_at"]
        validators = []

    def validate_product(self, value):
        if self.instance is not None:
            if value.pk != self.instance.product_id:
                raise serializers.ValidationError(
                    "No se puede cambiar el producto de una imagen."
                )
        return value

    def create(self, validated_data):
        with transaction.atomic():
            producto = get_object_or_404(
                Product.objects.select_for_update(),
                pk=validated_data["product"].pk,
            )

            imagenes = ProductImage.objects.filter(product=producto)

            es_primera = not imagenes.exists()
            es_principal = (
                es_primera or validated_data.get("is_primary", False)
            )

            validated_data["product"] = producto
            validated_data["is_primary"] = es_principal

            if es_principal:
                imagenes.filter(is_primary=True).update(is_primary=False)

            return super().create(validated_data)

    def update(self, instance, validated_data):
        with transaction.atomic():
            get_object_or_404(
                Product.objects.select_for_update(),
                pk=instance.product_id,
            )

            actual = get_object_or_404(
                ProductImage,
                pk=instance.pk,
                product_id=instance.product_id,
            )

            producto_enviado = validated_data.get("product")
            if (
                producto_enviado is not None
                and producto_enviado.pk != actual.product_id
            ):
                raise serializers.ValidationError({
                    "product": (
                        "No se puede cambiar el producto de una imagen."
                    )
                })

            otras = ProductImage.objects.filter(
                product_id=actual.product_id,
            ).exclude(pk=actual.pk)

            es_principal = validated_data.get(
                "is_primary",
                actual.is_primary,
            )

            if es_principal:
                otras.filter(is_primary=True).update(is_primary=False)

            elif actual.is_primary:
                siguiente = otras.order_by("created_at", "pk").first()

                if siguiente is None:
                    raise serializers.ValidationError({
                        "is_primary": (
                            "No se puede desmarcar la única imagen principal."
                        )
                    })

                actual.is_primary = False
                actual.save(update_fields=["is_primary"])

                siguiente.is_primary = True
                siguiente.save(update_fields=["is_primary"])

            return super().update(actual, validated_data)

class ProductReviewSerializer(serializers.ModelSerializer):
    user = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = ProductReview
        fields = ["id", "product", "user", "rating", "comment", "created_at"]
        read_only_fields = ["id", "created_at"]
        validators = []

    def validate_product(self, value):
        if self.instance is None:
            if not value.active:
                raise serializers.ValidationError(
                    "No puedes reseñar un producto inactivo."
                )
        elif value.pk != self.instance.product_id:
            raise serializers.ValidationError(
                "No se puede cambiar el producto de una reseña."
            )
        return value

    def validate(self, attrs):
        if self.instance is None:
            usuario = self.context["request"].user
            if ProductReview.objects.filter(
                product=attrs["product"], user=usuario
            ).exists():
                raise serializers.ValidationError(
                    "Ya reseñaste este producto."
                )
        return attrs

    def create(self, validated_data):
        try:
            with transaction.atomic():
                return super().create(validated_data)
        except IntegrityError as exc:
            causa = exc.__cause__
            diagnostico = getattr(causa, "diag", None)
            restriccion = getattr(
                diagnostico, "constraint_name", None
            )

            if restriccion == "unique_review_per_user":
                raise serializers.ValidationError(
                    "Ya reseñaste este producto."
                ) from exc

            raise