# API E-commerce con Django REST Framework

Proyecto de portafolio en desarrollo: una API de e-commerce con catálogo de productos, almacenamiento de imágenes y, más adelante, un asesor de compras basado en RAG.

> **Estado:**  en desarrollo. La API de catálogo y el almacenamiento de imágenes en Garage funcionan. El asistente RAG está planeado y aún no se implementa. Este documento solo describe lo que existe y se ha probado; lo pendiente aparece en la sección [Pendiente](#pendiente).

## Stack

| Componente | Versión / detalle |
| --- | --- |
| Python | 3.14 (imagen `python:3.14.10-slim`) |
| Django | 6.1 |
| Django REST framework | Paginación activada (10 por página) |
| Base de datos | PostgreSQL 17 (contenedor `postgres:17`) |
| Driver | `psycopg[binary]` |
| Imágenes | Pillow 13.0.0 (requerido por `ImageField`) |
| Orquestación | Docker Compose (servicios `db` , `garage` y `web`) |
| Almacenamiento de imágenes | Garage v2.4.1, compatible con S3 |
| Integración | django-storages[s3]==1.14.6 |

## Cómo levantarlo

Garage requiere una inicialización única (layout, bucket y llave de acceso), que se describe en [Inicialización de Garage](#inicialización-de-garage). Por ello, el arranque se realiza en dos fases.

1. Copia las plantillas de configuración:

   ```bash
   cp .env.example .env
   cp garage.toml.example garage.toml
   ```

2. Genera los secretos de `garage.toml` y reemplaza los marcadores `CHANGE_ME`. Con OpenSSL:

   ```bash
   openssl rand -hex 32      # rpc_secret
   openssl rand -base64 32   # admin_token
   ```

   Si OpenSSL no está disponible, puede usarse Python:

   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"      # rpc_secret
   python -c "import secrets; print(secrets.token_urlsafe(32))"  # admin_token
   ```

3. Completa `.env` con valores propios. Las variables `GARAGE_ACCESS_KEY_ID` y `GARAGE_SECRET_ACCESS_KEY` se dejan vacías hasta el paso 5.

4. Levanta la base de datos y Garage, y sigue la guía de [Inicialización de Garage](#inicialización-de-garage):

   ```bash
   docker compose up -d db garage
   ```

5. Registra en `.env` el identificador y el secreto de la llave generada, y levanta el resto de los servicios:

   ```bash
   docker compose up --build -d
   docker compose exec web python manage.py migrate
   docker compose exec web python manage.py createsuperuser
   ```

6. Abre `http://localhost:8000/admin/` (panel de administración) o `http://localhost:8000/api/` (API navegable).

La base de datos no publica puertos hacia el host; solo es accesible desde la red interna de Compose. Los datos persisten en el volumen nombrado `pgdata`.

## Endpoints disponibles

| Ruta | Métodos | Notas |
| --- | --- | --- |
| `/api/brands` | GET, POST | Lista solo marcas activas |
| `/api/brands/<id>` | GET, PUT, PATCH, DELETE | El detalle muestra también las inactivas |
| `/api/categories` | GET, POST | Lista solo categorías activas |
| `/api/categories/<id>` | GET, PUT, PATCH, DELETE | El detalle muestra también las inactivas |
| `/api/products` | GET, POST | Lista solo productos activos |
| `/api/products/<id>` | GET, PUT, PATCH, DELETE | El detalle incluye también los productos inactivos |
| `/api/product-images` | GET, POST | Lista registros de imágenes y permite subir archivos mediante multipart/form-data |
| `/api/product-images/<id>` | GET, PUT, PATCH, DELETE | Consulta y modifica un registro de imagen; DELETE realiza borrado real de la fila |

En marcas, categorías y productos, `DELETE` realiza **borrado lógico**
(`active = false`). Para reactivar, se utiliza `PATCH` con `{"active": true}`.

En imágenes, `DELETE` elimina la fila de ProductImage. La eliminación
del archivo correspondiente en Garage todavía no está implementada.

## Modelos

- **Category**: relación recursiva mediante `parent`; una subcategoría es una categoría con padre.
- **Brand**: marca de productos y estado `active`.
- **Product**: precio `Decimal(10,2)`, stock, especificaciones en `JSONB` y estado `active`.
- **ProductImage**: imagen mediante `ImageField`, relación con producto y marca de imagen principal. Cuenta con endpoints.
- **ProductReview**: calificación de 1 a 5, ligada a un producto y a un usuario. Todavía no tiene endpoints.

## Reglas de integridad

Las reglas viven en tres capas, porque cada una protege contra cosas distintas.

### 1. PostgreSQL (se aplican siempre, sin importar el camino de escritura)

- `stock >= 0` y `price >= 0` en productos.
- `rating` entre 1 y 5 en reseñas.
- Una categoría no puede ser su propio padre (`parent` distinto del propio `id`).
- Como máximo una imagen principal por producto (índice único parcial).
  Se permite que un producto no tenga ninguna imagen principal.
- Una sola reseña por usuario y producto.
- `slug` de categoría y `sku` de producto únicos.

### 2. Django ORM (`on_delete`, solo en borrados reales desde el ORM)

- `PROTECT`: una marca o categoría con productos no se puede borrar; una categoría con subcategorías tampoco.
- `CASCADE`: al borrar realmente un producto desde el ORM se eliminan sus
  registros de imágenes y reseñas; al borrar un usuario, sus reseñas.
  Esto no elimina automáticamente los archivos almacenados en Garage.

### 3. API (serializers de Brand, Category y Product)

- No se puede desactivar una categoría con subcategorías activas o con productos activos.
- No se puede desactivar una marca con productos activos.
- Una categoría no puede ser su propio padre, ni crear ciclos entre categorías (A → B → A).
- precio y stock no negativos en productos.
- Rechazo de marcas/categorías inactivas al asignarlas a un producto.
- Al actualizar un producto, si su estado final es activo, su marca y categoría también deben estar activas. Se consideran las relaciones enviadas en la petición o, si no vienen, las que ya tiene el producto.
- Se permite reactivar un producto y cambiar su marca y categoría en la misma petición.

## Decisiones de diseño

- **`DecimalField` para dinero**, en lugar de `float`, para evitar errores de redondeo binario.
- Borrado lógico en marcas, categorías y productos: `DELETE` reutiliza la
  validación del serializer y cambia `active` a `false`. Las imágenes no
  utilizan este mecanismo.
- **Reglas duplicadas a propósito**: la API da errores claros (400) y la base de datos actúa como última barrera.
- **`get_queryset` por acción**: la lista oculta lo inactivo, pero el detalle lo conserva para poder reactivarlo.

## Almacenamiento de imágenes con Garage

Las imágenes se almacenan en Garage, un servicio compatible con S3,
integrado con Django mediante django-storages[s3].

### Arquitectura

- PostgreSQL guarda los registros ProductImage y la ruta de cada archivo.
- Garage guarda el contenido de los archivos en el bucket ecommerce-images.
- Garage utiliza SQLite para sus metadatos internos; esto no cambia la
  base de datos PostgreSQL de Django.
- Django accede a Garage mediante `http://garage:3900`, dentro de la red
  de Docker Compose.
- La API S3 se publica únicamente en 127.0.0.1:3900.
- Los datos y metadatos persisten en los volúmenes garage-data y garage-meta.

El almacenamiento default de Django utiliza el backend S3. Los archivos
estáticos conservan el backend local de Django.

### Configuración local realizada

1. Se añadió el servicio dxflrs/garage:v2.4.1 a Docker Compose.
2. Se creó garage.toml con las rutas de datos y metadatos, SQLite y
   replication_factor = 1.
3. Se configuró y aplicó el layout inicial del nodo, con capacidad de 1G.
4. Se creó el bucket ecommerce-images.
5. Se creó la llave django-garage-key y se le otorgaron permisos de
   lectura y escritura sobre ese bucket, sin permisos de propietario
   ni de creación de buckets.
6. Se añadieron las variables de entorno de Garage.
7. Se configuró STORAGES en Django y se reconstruyó el servicio web.

Las credenciales reales se guardan en .env y no deben subirse al repositorio.
El archivo garage.toml contiene secretos y tampoco debe publicarse tal cual;
para documentarlo se debe utilizar una plantilla sin secretos reales.

### Inicialización de Garage

Un nodo de Garage recién creado no almacena datos hasta que se le asigna capacidad. El procedimiento siguiente se ejecuta una sola vez por cada conjunto de volúmenes y reproduce la configuración descrita en [Configuración local realizada](#configuración-local-realizada).

1. Obtén el identificador del nodo. Bastan los primeros 16 caracteres del campo `ID`:

   ```bash
   docker compose exec garage /garage status
   ```

2. Asigna capacidad al nodo y aplica el layout:

   ```bash
   docker compose exec garage /garage layout assign -z dc1 -c 1G <ID_DEL_NODO>
   docker compose exec garage /garage layout apply --version 1
   ```

3. Crea el bucket:

   ```bash
   docker compose exec garage /garage bucket create ecommerce-images
   ```

4. Crea la llave de acceso y otórgale permisos de lectura y escritura sobre el bucket. No se concede el permiso de propietario:

   ```bash
   docker compose exec garage /garage key create django-garage-key
   docker compose exec garage /garage bucket allow --read --write ecommerce-images --key django-garage-key
   ```

   El comando `key create` muestra el identificador y el secreto de la llave una única vez. Si se pierde el secreto, puede consultarse con `garage key info django-garage-key --show-secret`.

5. Registra ambos valores en `.env` como `GARAGE_ACCESS_KEY_ID` y `GARAGE_SECRET_ACCESS_KEY`. Si el servicio `web` ya estaba en ejecución, recréalo, porque `docker compose restart` no vuelve a leer `.env`:

   ```bash
   docker compose up -d --force-recreate web
   ```

#### Verificación

Sube una imagen a un producto existente mediante `multipart/form-data`. En PowerShell, utiliza `curl.exe`:

```bash
curl -X POST http://localhost:8000/api/product-images \
  -F "product=1" \
  -F "image=@foto.jpg" \
  -F "is_primary=true"
```

La respuesta esperada es `201 Created`. Puede confirmarse la existencia del bucket y de la llave con `garage bucket list` y `garage key list`.

#### Reinicio de los volúmenes

El comando `docker compose down -v` elimina los volúmenes `pgdata`, `garage-meta` y `garage-data`. Con ello se pierden los datos de PostgreSQL y toda la configuración de Garage, por lo que debe repetirse este procedimiento y generar una llave nueva.

### Variables de entorno

```dotenv
GARAGE_ACCESS_KEY_ID=
GARAGE_SECRET_ACCESS_KEY=
GARAGE_BUCKET_NAME=ecommerce-images
GARAGE_ENDPOINT_URL=http://garage:3900
GARAGE_REGION=garage
```

Los valores vacíos son marcadores de ejemplo. En el `.env` real deben
configurarse las credenciales S3 de la llave autorizada sobre el bucket.

### Subida de imágenes

Las rutas disponibles están en [Endpoints disponibles](#endpoints-disponibles).

La creación de imágenes requiere un formulario `multipart/form-data` con:

- `product`: ID de un producto existente.
- `image`: archivo de imagen.
- `is_primary`: booleano opcional; el valor predeterminado es `false`.

Puede probarse desde el formulario de la API navegable de DRF.

El listado consulta los registros de PostgreSQL, no enumera directamente
todos los objetos del bucket.

### Imagen principal

Un producto puede tener cero o una imagen principal.

- Al crear una imagen con is_primary=true, se desmarca la principal anterior.
- Al actualizar una imagen cuyo estado final sea is_primary=true, se
  desmarcan las otras principales del producto de destino.
- Marcar una imagen como principal no elimina la imagen anterior.
- Establecer is_primary=false puede dejar al producto sin principal.

El serializer agrupa el desmarcado y el guardado en transaction.atomic().
La base de datos conserva la UniqueConstraint condicional como última
barrera contra dos principales para el mismo producto.

Se desactivaron los validadores de clase automáticos del serializer para
permitir el reemplazo. Las validaciones de los campos permanecen activas.

### Filtrado por producto

`GET /api/product-images?product=<id>` devuelve solo las imágenes del
producto indicado.

- Sin el parámetro, se devuelve el listado completo.
- Si el ID no corresponde a ningún producto o el producto no tiene imágenes,
  la respuesta es `200` con `count: 0`.
- Si el valor no es un entero, la respuesta es `400` con un mensaje de error.

### Pruebas manuales realizadas

- Escritura, comprobación de existencia y lectura de un objeto desde
  default_storage.
- Subida de una imagen real mediante la API navegable de DRF, con
  respuesta 201 Created.
- Creación de una segunda imagen principal para el mismo producto:
  la anterior quedó con is_primary=false y la nueva con is_primary=true.

Estas comprobaciones son manuales; no equivalen a pruebas automatizadas.

### Limitaciones actuales

- Las URLs generadas están firmadas y tienen una vigencia de una hora.
  Caduca el enlace, no el archivo.
- Las URLs utilizan el hostname interno garage. El acceso desde el
  navegador del host requiere resolver ese nombre o configurar una
  estrategia de publicación; todavía no se ha verificado visualmente
  la imagen desde el host.
- No está implementada la eliminación de archivos de Garage al borrar
  registros ni la limpieza de archivos sustituidos.
- transaction.atomic() protege los cambios de PostgreSQL, no las
  operaciones del almacenamiento S3.
- Las solicitudes concurrentes de cambio de principal todavía no tienen
  una estrategia explícita de serialización y manejo de conflictos.
- El nodo único con replication_factor=1 no proporciona redundancia.

## Limitaciones conocidas

- **Sin autenticación ni permisos**: cualquier cliente que llegue al puerto 8000 puede leer y escribir. El puerto se publica solo en 127.0.0.1, por lo que únicamente es accesible desde la propia máquina.
- **Las validaciones de la API solo aplican a la API**: el panel de administración, el shell y los scripts no pasan por los serializers. El caso más delicado son los ciclos de categorías; la base solo bloquea la autorreferencia directa. Una posible solución sería mover la regla a `Category.clean()`, pero se mantuvo simple.
- **Reactivación de categorías sin comprobar el padre**: un `PATCH` con `active: true` no verifica que la categoría padre esté activa. La reactivación de productos sí comprueba que su marca y categoría efectivas estén activas.
- **Sin pruebas automáticas** por ahora; las reglas se han verificado manualmente.

## Seguridad

- Las credenciales viven en `.env` y `garage.toml`, que están en `.gitignore` y `.dockerignore`. El repositorio solo incluye plantillas (`.env.example`,`garage.toml.example`).
- PostgreSQL no publica puertos. La API S3 de Garage y la API de Django solo escuchan en `127.0.0.1`.
- La key de Garage solo tiene permisos de lectura y escritura sobre un bucket.
- **limitación conocida**: la API no tiene autenticación. No la exponga a Internet en este estado.

## Pendiente

- [ ] Pruebas automáticas con `APITestCase` para las reglas de Brand y Category.
- [x] Endpoints de productos, con serializers de lista y detalle y validación de precio y stock.
- [ ] Filtros y búsqueda de productos por categoría, marca, texto y orden.
- [ ] Autenticación con `TokenAuthentication` y permisos por grupos de Django.
- [x] Endpoints de imágenes mediante `ProductImageViewSet`.
- [x] Almacenamiento de imágenes en Garage con `django-storages[s3]`.
- [x] Prueba manual de subida de imágenes y reemplazo de la principal mediante POST.
- [x] Filtrado de imágenes por producto mediante `/api/product-images?product=<id>`.
- [ ] Pruebas manuales de creación de imágenes secundarias y creación sin enviar `is_primary`.
- [ ] Pruebas manuales de cambio y desmarcado de la principal mediante PATCH.
- [ ] Verificar la descarga y visualización de una imagen real desde el host.
- [ ] Implementar y probar la limpieza de archivos al eliminar registros o sustituir imágenes.
- [ ] Pruebas automatizadas de imágenes y manejo de cambios concurrentes de principal.
- [ ] Endpoints de reseñas.
- [ ] Asesor de compras con RAG sobre el catálogo.
- [x] Documentar la inicialización de Garage desde cero y proporcionar una plantilla `garage.toml.example` sin secretos.
- [ ] Imagen de PostgreSQL con pgvector y migración de la extensión.
- [ ] Servicio Ollama opcional en Compose (profiles: ["ai"]).
- [ ] Embeddings de productos y endpoint de búsqueda semántica.
- [ ] Respuesta del asistente con los productos recuperados.
- [ ] Limitar formatos y tamaño en la subida de imágenes (formatos permitidos y límite de píxeles).
