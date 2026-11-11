# API E-commerce con Django REST Framework

Proyecto de portafolio en desarrollo: una API de e-commerce con catálogo de productos, almacenamiento de imágenes y, más adelante, un asesor de compras basado en RAG.

> **Estado:**  en desarrollo. La API de catálogo, el almacenamiento de imágenes en Garage y el asistente RAG básico funcionan. Este documento solo describe lo que existe y se ha probado; lo pendiente aparece en la sección [Pendiente](#pendiente).

## Stack

| Componente | Versión / detalle |
| --- | --- |
| Python | 3.14 (imagen `python:3.14.10-slim`) |
| Django | 6.1 |
| Django REST framework | Paginación activada (10 por página) |
| Base de datos | PostgreSQL 17 (contenedor `postgres:17`) |
| Driver | `psycopg[binary]` |
| Imágenes | Pillow 13.0.0 (requerido por `ImageField`) |
| Orquestación | Docker Compose (servicios `db`, `garage` y `web`) |
| Búsqueda vectorial | pgvector (extensión PostgreSQL, índice HNSW) |
| IA local | Ollama (embeddings con `nomic-embed-text`, chat con `qwen3.5:4b`) |
| Almacenamiento de imágenes | Garage v2.4.1, compatible con S3 |
| Integración | django-storages[s3]==1.14.6 |

## Cómo levantarlo

El proyecto se levanta con Docker Compose. Existen dos modos de despliegue:
por etapas (más control) o todo-en-uno (menos comandos).

### Requisitos previos

1. Copia las plantillas de configuración:

   ```bash
   cp .env.example .env
   cp garage.toml.example garage.toml
   ```

2. El archivo `garage.toml` usa rutas a archivos de secretos generados
   automáticamente; no requiere editar valores manualmente.

3. (Opcional) Edita `.env` para activar datos de demostración automáticos:

   ```dotenv
   SEED_DEMO=true
   ```

   Con `SEED_DEMO=true`, el arranque crea marcas, categorías y productos
   de demostración automáticamente. Con `SEED_DEMO=false` (default),
   puedes cargarlos después con `seed_demo`.

### Modo todo-en-uno (recomendado)

Un solo comando levanta todo: secretos, base de datos, Garage, Django,
y (con `--profile ai`) Ollama más embeddings.

```bash
docker compose -p <nombre-proyecto> -f docker-compose.yml -f compose.full.yml --profile ai up -d --build
```

Reemplaza `<nombre-proyecto>` por un nombre fijo (por ejemplo, `ragtest`)
para evitar conflictos si la carpeta tiene espacios o caracteres especiales.

Este comando:

- Genera secretos automáticamente (`init_secrets.py`).
- Inicializa Garage (layout, bucket, llave) automáticamente (`init_garage.py`).
- Ejecuta migraciones y crea el superusuario automáticamente.
- Si `SEED_DEMO=true`, carga datos de demostración.
- Si usas `--profile ai`, descarga modelos de Ollama y genera embeddings.

La contraseña del superusuario se genera automáticamente y se guarda en
`/secrets/app/django_admin_password`. Para verla:

```bash
docker compose -p <nombre-proyecto> exec web cat /secrets/app/django_admin_password
```

### Modo por etapas

Si prefieres control paso a paso:

**Etapa 1 — API + base de datos:**

```bash
docker compose -p <nombre-proyecto> up -d --build db web
```

**Etapa 2 — Garage y conexión automática:**

```bash
docker compose -p <nombre-proyecto> up -d --build garage garage-init
Start-Sleep -Seconds 5
docker compose -p <nombre-proyecto> up -d --no-deps --force-recreate web
```

**Etapa 3 — IA (opcional):**

```bash
docker compose -p <nombre-proyecto> --profile ai up -d --build ollama ollama-init
Start-Sleep -Seconds 5
docker compose -p <nombre-proyecto> exec web python manage.py embed_products
```

**Datos de demostración (opcional, en cualquier momento después de la etapa 1):**

  ```bash
  docker compose -p <nombre-proyecto> exec web python manage.py seed_demo
  docker compose -p <nombre-proyecto> exec web python manage.py embed_products
  ```

### Nota sobre GPU

El servicio `ollama` incluye un bloque `deploy` con GPU NVIDIA. En máquinas
sin GPU, elimina o comenta ese bloque; Ollama funcionará en CPU (más lento).

### Acceso

- Panel de administración: `http://localhost:8000/admin/`
- API navegable: `http://localhost:8000/api/`

La base de datos no publica puertos hacia el host; solo es accesible desde
la red interna de Compose. Los datos persisten en el volumen `pgdata`.

## Datos de demostración

El comando `seed_demo` crea marcas, categorías y productos de demostración.
Es idempotente: puede ejecutarse varias veces sin duplicar registros.

```bash
docker compose -p <nombre-proyecto> exec web python manage.py seed_demo
```

Si `SEED_DEMO=true` en `.env`, el arranque automático ya lo ejecuta.
Si `SEED_DEMO=false`, ejecútalo manualmente después de levantar `web`.

Para regenerar embeddings después de crear o modificar productos:

```bash
docker compose -p <nombre-proyecto> exec web python manage.py embed_products
```

## Pruebas

Las pruebas usan `APITestCase` y una base de datos temporal que Django crea y elimina por sí mismo, sin afectar a los datos de desarrollo. Con los servicios levantados:

```bash
docker compose exec web python manage.py test
docker compose exec web python manage.py test rag_app.tests.test_brand -v 2
```

**Cobertura actual**: reglas de Brand y Category en la API, y reglas de integridad de Category en la base de datos y el ORM. Product e imágenes están pendientes.

Para reiniciar los datos de desarrollo sin afectar Garage, se puede
vaciar la base de datos y volver a cargar el catálogo de demostración:

```bash
docker compose exec web python manage.py flush
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
```

`flush` elimina todas las filas de PostgreSQL, incluido el superusuario.
Los archivos ya subidos a Garage permanecen en el bucket, pero quedan
sin referencia en la base de datos.

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
| `/api/ia/ask` | POST | Asistente RAG: recibe `{"query": "..."}` y retorna una recomendación basada en el catálogo |

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

La configuración de Garage se realiza automáticamente al arrancar:

1. `init_secrets.py` genera `garage_rpc_secret`, `garage_admin_token` y
   `django_secret_key` en `/secrets`.
2. `init_garage.py` usa la API Admin de Garage para:
   - Asignar capacidad al nodo y aplicar el layout.
   - Crear el bucket `ecommerce-images`.
   - Crear la llave `django-garage-key` con permisos de lectura y escritura.
   - Guardar las credenciales S3 en `/secrets/s3/garage_s3.env`.
3. El servicio `web` carga esas credenciales al arrancar.

No es necesario ejecutar pasos manuales de Garage.

### Inicialización de Garage

La inicialización de Garage (layout, bucket y llave de acceso) se realiza
automáticamente por el servicio `garage-init` al arrancar. No requiere
pasos manuales.

El script `docker/init_garage.py`:

- Detecta el identificador del nodo.
- Asigna capacidad y aplica el layout.
- Crea el bucket `ecommerce-images`.
- Crea la llave `django-garage-key` con permisos de lectura y escritura.
- Guarda las credenciales S3 en `/secrets/s3/garage_s3.env`.

El servicio `web` carga esas credenciales al arrancar (o al recrearse
después de que Garage termine). No es necesario configurar
`GARAGE_ACCESS_KEY_ID` ni `GARAGE_SECRET_ACCESS_KEY` manualmente.

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

Las credenciales S3 (`GARAGE_ACCESS_KEY_ID` y `GARAGE_SECRET_ACCESS_KEY`)
se generan automáticamente por `init_garage.py` y se guardan en
`/secrets/s3/garage_s3.env`. El servicio `web` las carga al arrancar.

No es necesario configurarlas manualmente en `.env`. Las variables
restantes tienen valores por defecto en `docker-compose.yml`:

```dotenv
GARAGE_BUCKET_NAME=ecommerce-images
GARAGE_ENDPOINT_URL=http://garage:3900
GARAGE_REGION=garage
```

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
- Subida de imágenes con Pillow 13.0.0 respondió `201 Created`.

Estas comprobaciones son manuales; no equivalen a pruebas automatizadas.

## Asistente RAG

La API incluye un asistente de compras basado en RAG (Retrieval-Augmented Generation) que responde preguntas sobre el catálogo usando solo productos reales.

### Arquitectura del rag

1. El usuario envía una pregunta a `POST /api/ia/ask`.
2. Se genera un embedding de la pregunta con Ollama (`nomic-embed-text`, 768 dimensiones).
3. PostgreSQL filtra productos activos, con stock, y con marca/categoría activas; luego ordena por similitud coseno usando el índice HNSW.
4. Se toman los top 5 productos y se construye un prompt con nombre, descripción, especificaciones, precio (MXN) y stock.
5. Ollama (`qwen3.5:4b`) genera una respuesta usando solo el contexto proporcionado.

### Uso

```powershell
Invoke-RestMethod -Uri http://localhost:8000/api/ia/ask -Method Post -ContentType "application/json" -Body '{"query": "laptop gaming"}'
```

La respuesta incluye `answer` (texto del LLM) y `products` (lista de IDs y nombres de los productos recuperados).

### Limitaciones del rag

- No hay memoria de conversación: cada llamada es independiente.
- El flag `AI_ENABLED` aún no se valida en el código.
- Si no hay productos relevantes, la búsqueda puede retornar resultados de baja similitud (sin umbral).
- `embed_products` recalcula todos los embeddings en cada ejecución; no es idempotente en el sentido de "saltar si ya existe".

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
- **Pruebas automáticas parciales**: cubren Brand y Category; Product e imágenes pendientes.

## Seguridad

- Las credenciales viven en `.env` y `garage.toml`, que están en `.gitignore` y `.dockerignore`. El repositorio solo incluye plantillas (`.env.example`, `garage.toml.example`).
- PostgreSQL no publica puertos. La API S3 de Garage y la API de Django solo escuchan en `127.0.0.1`.
- La key de Garage solo tiene permisos de lectura y escritura sobre un bucket.
- **LIMITACIÓN CONOCIDA**: la API no tiene autenticación. No la expongas a Internet en este estado.
- La imagen base puede reportar vulnerabilidades en componentes incluidos sin parche disponible. El proyecto está pensado para desarrollo local; para producción se recomienda una imagen mínima, ejecución sin root y escaneo en CI.

## Pendiente

### Imágenes

- [x] Almacenamiento de imágenes en Garage con `django-storages[s3]`.
- [x] Documentar la inicialización de Garage desde cero y proporcionar una plantilla `garage.toml.example` sin secretos.
- [ ] Limitar formatos y tamaño en la subida de imágenes (formatos permitidos y límite de píxeles).
- [ ] Probar la limpieza de archivos al eliminar registros o sustituir imágenes.
- [ ] Verificar la descarga y visualización de una imagen real desde el host.
- [ ] Pruebas manuales de cambio y desmarcado de la principal mediante PATCH.

### Tests

- [x] Comando `seed_demo` con marcas, categorías y productos de demostración.
- [x] Prueba manual de subida de imágenes y reemplazo de la principal mediante POST.
- [x] Pruebas automáticas con `APITestCase` para las reglas de Brand y Category.
- [ ] Pruebas automatizadas de imágenes y manejo de cambios concurrentes de principal.
- [ ] Pruebas automatizadas para Product.
- [ ] Pruebas manuales de creación de imágenes secundarias y creación sin enviar `is_primary`.

### RAG

- [x] Asesor de compras con RAG sobre el catálogo.
- [x] Embeddings de productos y endpoint de búsqueda semántica.
- [x] Respuesta del asistente con los productos recuperados.
- [x] Servicio Ollama opcional en Compose (profiles: ["ai"]).
- [x] Imagen de PostgreSQL con pgvector y migración de la extensión.
- [x] Despliegue todo-en-uno con `compose.full.yml` (Garage + IA opcionales).
- [x] Inicialización automática de Garage (`init_garage.py`).
- [ ] Memoria de conversación (multi-turno).
- [ ] Flag `AI_ENABLED` para activar/desactivar el asistente.
- [ ] Umbral de similitud para descartar resultados irrelevantes.
- [ ] Embeddings idempotentes (saltar si ya existen).
- [ ] Tests automatizados del RAG.

### API

- [x] Endpoints de productos, con serializers de lista y detalle y validación de precio y stock.
- [x] Endpoints de imágenes mediante `ProductImageViewSet`.
- [x] Filtrado de imágenes por producto mediante `/api/product-images?product=<id>`.
- [ ] Filtros y búsqueda de productos por categoría, marca, texto y orden.
- [ ] Autenticación con `TokenAuthentication` y permisos por grupos de Django.
- [ ] Endpoints de reseñas.
