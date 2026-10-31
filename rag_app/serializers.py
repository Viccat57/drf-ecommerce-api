from rest_framework import serializers
from .models import Brand,Category, Product, ProductImage
from django.db import transaction

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
    brand = BrandProductSerializer(read_only = True)
    category = CategoryProductSerializer(read_only = True)
    class Meta:                
        model = Product
        fields = ['id', 'name', 'sku', 'price', 'stock', 'active', 'brand', 'category']
        
class ProductDetailSerializer(serializers.ModelSerializer):
    
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
        fields = '__all__'   
        
class ProductImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductImage
        fields = '__all__'
        read_only_fields = ['id','created_at']
        validators = []
        
    def create(self, validated_data):
        with transaction.atomic():
            producto = validated_data['product']
            es_principal = validated_data.get('is_primary',False)
            
            if es_principal:
                self.clear_primary(producto)
                
            return super().create(validated_data)
    
    def update(self, instance, validated_data):
        with transaction.atomic():
            producto = validated_data.get('product',instance.product)
            es_principal = validated_data.get('is_primary',instance.is_primary)
            
            if es_principal:
                self.clear_primary(producto, pk=instance.pk)
                     
            return super().update(instance, validated_data)
    
    def clear_primary(self, producto, pk=None): 
        if pk is not None:
            imagenes = producto.productimage_set.filter(is_primary=True).exclude(pk=pk)
        else:
            imagenes = producto.productimage_set.filter(is_primary= True)
        
        imagenes.update(is_primary=False)            
                      