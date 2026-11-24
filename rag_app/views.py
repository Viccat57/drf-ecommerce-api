from rest_framework import viewsets
from rest_framework import filters
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import Brand, Category, Product, ProductImage, Conversation, Message, ProductReview
from .serializers import BrandSerializer, CategorySerializer, ProductDetailSerializer, ProductListSerializer, ProductImageSerializer, ProductReviewSerializer
from .filters import ProductFilter
from rag_app.ai import search_products, generate_response, build_retrieval_query
from .permissions import AIEnabled, IsReviewAuthorOrStaff
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.shortcuts import get_object_or_404

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
    queryset = Product.objects.select_related("brand", "category")

    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
    filterset_class = ProductFilter

    search_fields = [
        "name",
        "description",
        "sku",
        "brand__name",
        "category__name",
    ]
    ordering_fields = ["price", "name", "created_at", "stock", "id"]
    ordering = ["-created_at", "id"]

    def get_serializer_class(self):
        if self.action == "list":
            return ProductListSerializer
        return ProductDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            qs = qs.filter(active=True)
        return qs

    def perform_destroy(self, instance):
        serializer = self.get_serializer(
            instance,
            data={"active": False},
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
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

    def perform_destroy(self, instance):
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

            producto_id = actual.product_id
            era_principal = actual.is_primary

            actual.delete()

            if era_principal:
                siguiente = (
                    ProductImage.objects
                    .filter(product_id=producto_id)
                    .order_by("created_at", "pk")
                    .first()
                )

                if siguiente is not None:
                    siguiente.is_primary = True
                    siguiente.save(update_fields=["is_primary"])

class AskView(APIView):
    permission_classes = [IsAuthenticated, AIEnabled]

    def post(self, request):
        query = request.data.get('query')
        if not query:
            return Response(
                {'error': 'query es requerido'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        conversation_id = request.data.get('conversation_id')
        if conversation_id:
            try:
                conversation = Conversation.objects.get(pk=conversation_id, user=request.user,)
            except (Conversation.DoesNotExist, DjangoValidationError, ValueError):
                return Response(
                    {'error': 'conversation_id inválido'},
                    status=status.HTTP_404_NOT_FOUND,
                )
        else:
            conversation = Conversation.objects.create(user=request.user)

        recent = list(
            conversation.messages.order_by('-id')[:settings.AI_HISTORY_MESSAGES]
        )
        history = [
            {'role': m.role, 'content': m.content}
            for m in reversed(recent)
        ]

        results = search_products(build_retrieval_query(query, history))
        if results:
            answer = generate_response(query, results, history)
        else:
            answer = 'No encontré productos relacionados con tu consulta.'

        Message.objects.create(
            conversation=conversation,
            role=Message.Role.USER,
            content=query,
        )
        Message.objects.create(
            conversation=conversation,
            role=Message.Role.ASSISTANT,
            content=answer,
            product_ids=[p.id for p in results],
        )

        return Response(
            {
                'conversation_id': str(conversation.id),
                'answer': answer,
                'products': [{'id': p.id, 'name': p.name} for p in results],
            },
            status=status.HTTP_200_OK,
        )

class ProductReviewViewSet(viewsets.ModelViewSet):
    queryset = ProductReview.objects.select_related("user").order_by(
        "-created_at", "-id"
    )
    serializer_class = ProductReviewSerializer
    permission_classes = [IsAuthenticatedOrReadOnly, IsReviewAuthorOrStaff]

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action == "list":
            product = self.request.query_params.get("product")
            if product is not None:
                if not product.isdigit():
                    raise ValidationError(
                        "Se necesita un ID valido para buscar un producto"
                    )
                qs = qs.filter(product_id=product)
        return qs

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)