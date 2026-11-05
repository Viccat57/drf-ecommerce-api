from django.urls import reverse
from rest_framework import status
from rag_app.models import Brand,Category
from rag_app.tests.base import BaseAPITestCase


class BrandListTests(BaseAPITestCase):
    def setUp(self):
        self.activa = Brand.objects.create(name="Nueva Marca", active=True)
        self.inactiva = Brand.objects.create(name="Vieja Marca", active=False)
        self.categoria = Category.objects.create(name='CategoryNew',slug='ctgnew')

    def test_get_solo_muestra_marcas_activas(self):
        response = self.client.get(reverse("brand-list"))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        nombres = [b["name"] for b in response.data["results"]]
        self.assertIn("Nueva Marca", nombres)
        self.assertNotIn("Vieja Marca", nombres)
    
    def test_get_detalle_marca_inactiva(self):
        response = self.client.get(reverse("brand-detail", args=[self.inactiva.pk]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
    
    def test_delete_marca_sin_productos(self):
        marca_productosnt = Brand.objects.create(name='sin_productos')
        response = self.client.delete(reverse("brand-detail", args=[marca_productosnt.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        marca_productosnt.refresh_from_db()
        self.assertFalse(marca_productosnt.active)
    
    def test_delete_marca_con_productos(self):
        marca_con_productos = Brand.objects.create(name='marca_cProductos')
        self.crear_producto(marca_con_productos)
        response = self.client.delete(reverse("brand-detail", args=[marca_con_productos.pk]))
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        marca_con_productos.refresh_from_db()
        self.assertTrue(marca_con_productos.active)
        
    def test_delete_marca_sin_productos_activos(self):
        marca_con_productos = Brand.objects.create(name='marca_cProductos')
        self.crear_producto(marca_con_productos,active=False)
        response = self.client.delete(reverse("brand-detail", args=[marca_con_productos.pk]))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        marca_con_productos.refresh_from_db()
        self.assertFalse(marca_con_productos.active)
                
    def test_patch_desactivar_marca_sin_productos_activos(self):
        marca_con_productos = Brand.objects.create(name='no-editar')
        response = self.client.patch(reverse("brand-detail", args=[marca_con_productos.pk]),{"active":False},format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        marca_con_productos.refresh_from_db()
        self.assertFalse(marca_con_productos.active)
    
    def test_patch_desactivar_marca_con_un_solo_producto_activo(self):
        marca_con_productos = Brand.objects.create(name='no-editar')
        
        for i in range(5):
            if i == 2:
                self.crear_producto(marca_con_productos,sku=str(i))
            else:
                self.crear_producto(marca_con_productos,sku=str(i),active=False)
            
        response = self.client.patch(reverse("brand-detail", args=[marca_con_productos.pk]),{"active":False},format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        marca_con_productos.refresh_from_db()
        self.assertTrue(marca_con_productos.active)           
    
    def test_patch_reactivar_marca(self):
        response = self.client.patch(reverse("brand-detail", args=[self.inactiva.pk]), {"active":True},format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.inactiva.refresh_from_db()
        self.assertTrue(self.inactiva.active)
    
    def test_post_crear_marca(self):
        response = self.client.post(reverse("brand-list"),{"name":"new"},format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Brand.objects.filter(name="new", active=True).exists())
    
    def test_get_detalle_marca_no_existe(self):
        response = self.client.get(reverse("brand-detail", args=[999]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)    
          
                         