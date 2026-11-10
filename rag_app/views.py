from rest_framework import viewsets
from .models import Brand, Category, Product, ProductImage
from .serializers import BrandSerializer, CategorySerializer, ProductDetailSerializer, ProductListSerializer, ProductImageSerializer
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rag_app.ai import search_products, generate_response

class BrandViewSet(viewsets.ModelViewSet):
    queryset = Brand.objects.all()
    serializer_class = BrandSerializer
    
    def get_queryset(self):
        qs =  super().get_queryset()
        if self.action == 'list':
            qs = qs.filter(active=True)
        return qs
    
    def perform_destroy(self,instance):
        serializer = self.get_serializer(instance, data= {'active':False},partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            qs = qs.filter(active=True)
        return qs
    
    def perform_destroy(self,instance):
        serializer = self.get_serializer(instance, data={'active':False},partial = True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
class ProductViewSet(viewsets.ModelViewSet):
    queryset = Product.objects.all()
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProductListSerializer
        return ProductDetailSerializer
    
    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == 'list':
            qs = qs.filter(active=True)
        return qs    
    
    def perform_destroy(self, instance):
        serializer = self.get_serializer(instance, data = {'active':False},partial= True)
        serializer.is_valid(raise_exception = True)
        serializer.save()

class ProductImageViewSet(viewsets.ModelViewSet):
    queryset = ProductImage.objects.all()
    serializer_class = ProductImageSerializer
    
    def get_queryset(self):
        product = self.request.query_params.get('product')
        qs = super().get_queryset()
        if product is not None:
            if not product.isdigit():
                raise ValidationError('Se necesita un ID valido para buscar un producto') 
            qs = qs.filter(product__id=product)
                
        return qs     

class AskView(APIView):
    def post(self, request):
        query = request.data.get('query')
        if not query:
            return Response({'error': 'query es requerido'}, status=status.HTTP_400_BAD_REQUEST)
        results = search_products(query)
        if not results:
            return Response({'error': 'No se encontraron productos relevantes'}, status=status.HTTP_404_NOT_FOUND)
        answer = generate_response(query, results)
        return Response({'answer': answer, 'products': [{'id': p.id, 'name': p.name} for p in results]})    