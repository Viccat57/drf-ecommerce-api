from decimal import Decimal
from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rag_app.models import Brand, Category, Product
from rag_app.tests.base import BaseAPITestCase

class CategoryTests(BaseAPITestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name='TestBrand')
        self.activa = Category.objects.create(name='categoria_activa',active=True, slug='activa')
        self.inactiva = Category.objects.create(name='categoria_inactiva',active=False,slug='inactiva')
    
    def test_get_solo_muestra_activas(self):
        response = self.client.get(reverse("category-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nombres = [b["name"] for b in response.data["results"]]
        self.assertIn("categoria_activa",nombres)
        self.assertNotIn('categoria_inactiva',nombres)
    
    def test_get_detalle_categoria_inactiva(self):
        response = self.client.get(reverse("category-detail", args=[self.inactiva.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_delete_categoria_sin_hijos(self):
        categoria_sin_hijos = Category.objects.create(name='sin_hijos',slug='nochild')
        response = self.client.delete(reverse('category-detail',args=[categoria_sin_hijos.pk]))
        self.assertEqual(response.status_code,status.HTTP_204_NO_CONTENT)
        categoria_sin_hijos.refresh_from_db()
        self.assertFalse(categoria_sin_hijos.active)
    
    def test_delete_categoria_con_hijos(self):
        categoria_padre = Category.objects.create(name='padre',slug='fth')
        categoria_hijo = Category.objects.create(name='hijo',slug='chld',parent=categoria_padre)
        response = self.client.delete(reverse('category-detail',args=[categoria_padre.pk]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        categoria_padre.refresh_from_db()
        self.assertTrue(categoria_padre.active)
    
    def test_delete_categoria_con_producto(self):
        categoria = Category.objects.create(name='cat',slug='cat')
        self.crear_producto(categoria=categoria)
        response = self.client.delete(reverse('category-detail',args=[categoria.pk]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        categoria.refresh_from_db()
        self.assertTrue(categoria.active)          
    
    def test_delete_categoria_sin_hijos_activos(self):
        categoria_padre = Category.objects.create(name='padre',slug='fth')
        categoria_hijo = Category.objects.create(name='hijo',slug='chld',parent=categoria_padre, active=False)
        response = self.client.delete(reverse('category-detail',args=[categoria_padre.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        categoria_padre.refresh_from_db()
        self.assertFalse(categoria_padre.active)
    
    def test_patch_desactivar_categoria_con_hijo(self):
        categoria_padre = Category.objects.create(name='padre',slug='fth-2')
        categoria_hijo = Category.objects.create(name='hijo',slug='chld-2',parent=categoria_padre)
        response = self.client.patch(reverse('category-detail',args=[categoria_padre.pk]),{"active":False},format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        categoria_padre.refresh_from_db()
        self.assertTrue(categoria_padre.active)
    
    def test_patch_reactivar_categoria(self):
        response = self.client.patch(reverse('category-detail',args=[self.inactiva.pk]),{"active":True},format='json')
        self.assertEqual(response.status_code,status.HTTP_200_OK)
        self.inactiva.refresh_from_db()
        self.assertTrue(self.inactiva.active)
    
    def test_patch_desactivar_categoria_con_un_solo_producto_activo(self):
            categoria_con_productos = Category.objects.create(name='conProductos',slug='cProdu')
            
            for i in range(5):
                if i == 2:
                    self.crear_producto(categoria=categoria_con_productos, sku=f'sku-{i}-cat')
                else:
                    self.crear_producto(categoria=categoria_con_productos, sku=f'sku-{i}-cat', active=False)
                
            response = self.client.patch(reverse("category-detail", args=[categoria_con_productos.pk]),{"active":False},format="json")
            self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            categoria_con_productos.refresh_from_db()
            self.assertTrue(categoria_con_productos.active)
    
    def test_delete_categoria_con_productos_desactivados(self):
        categoria_con_productos = Category.objects.create(name='conProductos',slug='cProductos')
        self.crear_producto(categoria=categoria_con_productos, active=False)
        response = self.client.delete(reverse("category-detail", args=[categoria_con_productos.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        categoria_con_productos.refresh_from_db()
        self.assertFalse(categoria_con_productos.active)   
    
    def test_patch_categoria_con_mismo_id(self):
        categoria = Category.objects.create(name='same',slug='sm')
        response = self.client.patch(reverse('category-detail',args=[categoria.pk]),{"parent":categoria.pk},format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        categoria.refresh_from_db()
        self.assertIsNone(categoria.parent)
    
    def test_post_slug_repetido_responde_400(self):
        Category.objects.create(name="original", slug="dup")
        response = self.client.post(reverse("category-list"), {"name": "otra", "slug": "dup"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("slug", response.data)
        self.assertEqual(Category.objects.filter(slug="dup").count(), 1)    


class CategoryHierarchyTests(BaseAPITestCase):
    def setUp(self):
        self.a = Category.objects.create(name='A', slug='a')
        self.b = Category.objects.create(name='B', slug='b', parent=self.a)
        self.c = Category.objects.create(name='C', slug='c', parent=self.b)

    def test_patch_ciclo_corto(self):
        response = self.client.patch(reverse('category-detail',args=[self.a.pk]),{"parent":self.b.pk},format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.parent)
    
    def test_patch_ciclo_largo(self): 
        response = self.client.patch(reverse('category-detail',args=[self.a.pk]),{"parent":self.c.pk},format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.a.refresh_from_db()
        self.assertIsNone(self.a.parent)
    
    def test_patch_cambio_de_padre_valido(self):  
        response = self.client.patch(reverse('category-detail',args=[self.c.pk]),{"parent":self.a.pk},format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.c.refresh_from_db()
        self.assertEqual(self.c.parent, self.a)
    
    def test_patch_categoria_con_parent_null(self):
        response = self.client.patch(reverse('category-detail',args=[self.c.pk]),{"parent":None},format='json')
        self.assertEqual(response.status_code,status.HTTP_200_OK)
        self.c.refresh_from_db()
        self.assertIsNone(self.c.parent)
    
    def test_post_subcategoria_con_parent(self):
        response = self.client.post(reverse('category-list'),{"name":'D', "slug":'d', "parent":self.a.pk},format='json')
        self.assertEqual(response.status_code,status.HTTP_201_CREATED)
        self.assertTrue(Category.objects.filter(slug='d', active=True).exists())
        self.assertEqual(Category.objects.get(slug='d').parent, self.a)  
        
class CategoryDatabaseTests(TestCase):
    def setUp(self):
        self.brand = Brand.objects.create(name="TestBrand")

    def test_db_rechaza_categoria_padre_de_si_misma(self):
        categoria = Category.objects.create(name="solo", slug="solo")
        categoria.parent = categoria

        with self.assertRaises(IntegrityError) as ctx:
            with transaction.atomic():
                categoria.save()

        self.assertIn("parent_no_puede_ser_uno_mismo", str(ctx.exception))

    def test_orm_protege_categoria_con_productos(self):
        categoria = Category.objects.create(name="con_prod", slug="con-prod")
        Product.objects.create(
            name="p", sku="sku-orm", description="d", price=Decimal("1.01"),
            brand=self.brand, category=categoria,
        )

        with self.assertRaises(ProtectedError):
            categoria.delete()

        self.assertTrue(Category.objects.filter(pk=categoria.pk).exists())                                          