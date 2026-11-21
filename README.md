# API E-commerce con Django REST Framework

![tests](https://github.com/Viccat57/drf-ecommerce-api/actions/workflows/test.yml/badge.svg)

Proyecto de portafolio en desarrollo: una API de e-commerce con catálogo de productos, almacenamiento de imágenes y un asesor de compras basado en RAG.

> Estado: en desarrollo. Funcionan la API de catálogo con filtros y búsqueda,
> la autenticación por token, el almacenamiento de imágenes en Garage y el
> asistente RAG con memoria de conversación y aislamiento por usuario.
> Este documento describe lo implementado y validado localmente; las tareas
> pendientes aparecen en [Pendiente](#pendiente).

## Contenido

- [Stack](#stack)
- [Cómo levantarlo](#cómo-levantarlo)
- [Datos de demostración](#datos-de-demostración)
- [Pruebas](#pruebas)
- [Autenticación y alcance](#autenticación-y-alcance)
- [Endpoints disponibles](#endpoints-disponibles)
- [Filtros y búsqueda de productos](#filtros-y-búsqueda-de-productos)
- [Modelos](#modelos)
- [Reglas de integridad](#reglas-de-integridad)
- [Decisiones de diseño](#decisiones-de-diseño)
- [Almacenamiento de imágenes con Garage](#almacenamiento-de-imágenes-con-garage)
- [Asistente RAG](#asistente-rag)
- [Limitaciones del almacenamiento de imágenes](#limitaciones-del-almacenamiento-de-imágenes)
- [Limitaciones conocidas](#limitaciones-conocidas)
- [Seguridad](#seguridad)
- [Pendiente](#pendiente)

## Stack

| Componente | Versión / detalle |
| --- | --- |
| Python | 3.14 (imagen `python:3.14.10-slim`) |
| Django | 6.1 |
| Django REST framework | Paginación activada (10 por página) |
| Base de datos | PostgreSQL 17 con pgvector (imagen `pgvector/pgvector:pg17`) |
| Driver | `psycopg[binary]` |
| Imágenes | Pillow 13.0.0 (requerido por `ImageField`) |
| Orquestación | Docker Compose (servicios `db`, `garage` y `web`) |
| Búsqueda vectorial | pgvector (extensión PostgreSQL, índice HNSW) |
| IA local | Ollama (embeddings con `nomic-embed-text`, chat con `qwen3.5:4b`) |
| Almacenamiento de imágenes | Garage v2.4.1, compatible con S3 |
| Integración | django-storages[s3]==1.14.6 |
| Filtros de catálogo | django-filter==26.2 |
| Autenticación de la API | TokenAuthentication de Django REST framework |

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

4. Para usar el asistente, configura en `.env` antes de arrancar:

   ```dotenv
   AI_ENABLED=1
   AI_MIN_SIMILARITY=0.60
   AI_HISTORY_MESSAGES=10
   ```

   El valor de ejemplo `AI_ENABLED=0` mantiene la IA desactivada. El perfil
   `ai` inicia sus servicios, pero no sustituye esta configuración.

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
- Con `--profile ai`, `ollama-init` descarga los modelos y `ai-init` ejecuta
  `embed_products`; para generar embeddings debes configurar `AI_ENABLED=1`
  y contar con productos cargados.

El comando con `-d` retorna antes de que termine la descarga. Revisa los logs:

```bash
docker compose -p <nombre-proyecto> -f docker-compose.yml -f compose.full.yml --profile ai logs -f ollama-init ai-init
```

La contraseña del superusuario se genera automáticamente y se guarda en
`/secrets/app/django_admin_password`. Para verla:

```bash
docker compose -p <nombre-proyecto> exec web cat /secrets/app/django_admin_password
```

La contraseña del archivo corresponde a la generada por la inicialización.
Si cambiaste la contraseña de la cuenta posteriormente, utiliza la nueva.
Para restablecerla sin borrar datos:

```powershell
docker compose -p <nombre-proyecto> exec web python manage.py changepassword TU_USUARIO_ADMIN
```

Sustituye `TU_USUARIO_ADMIN` por el nombre real de la cuenta; no es
necesariamente `root`.

### Modo por etapas

Si prefieres control paso a paso:

**Etapa 1 — API + base de datos:**

```bash
docker compose -p <nombre-proyecto> up -d --build db web
```

**Etapa 2 — Garage y conexión automática:**

```powershell
docker compose -p <nombre-proyecto> up -d --build garage garage-init
Start-Sleep -Seconds 5
docker compose -p <nombre-proyecto> up -d --no-deps --force-recreate web
```

**Etapa 3 — IA (opcional):**

```bash
docker compose -p <nombre-proyecto> --profile ai up -d --build ollama ollama-init
docker compose -p <nombre-proyecto> --profile ai logs -f ollama-init
```

Espera a que `ollama-init` termine correctamente: descarga los modelos
indicados por `AI_EMBED_MODEL` y `AI_CHAT_MODEL`. Iniciar solo `ollama`
no ejecuta `ollama-init`; declarar el nombre de un modelo no lo descarga.
Una espera fija de cinco segundos no garantiza que la descarga termine.

Si activaste la IA en `.env` después de iniciar `web`, recréalo para tomar
las variables nuevas. Luego verifica los modelos y genera embeddings:

```bash
docker compose -p <nombre-proyecto> up -d --no-deps --force-recreate web
docker compose -p <nombre-proyecto> exec ollama ollama list
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

La suite validada localmente contiene 75 tests. Usa una base temporal que
Django crea y elimina; no utiliza Ollama real porque las llamadas de IA se
simulan en los tests.

Levanta la base de datos y reconstruye la imagen después de cambiar código
si no tienes un bind mount:

```bash
docker compose up -d db
docker compose build web

docker compose run --rm --no-deps -e DJANGO_SETTINGS_MODULE=rag.settings_test --entrypoint python web manage.py test --noinput -v 2

docker compose run --rm --no-deps -e DJANGO_SETTINGS_MODULE=rag.settings_test --entrypoint python web manage.py makemigrations --check --dry-run
```

La configuración `rag.settings_test` usa almacenamiento de pruebas.
`--entrypoint python` evita ejecutar el script habitual de arranque.
Si usas `-p <nombre-proyecto>`, conserva ese mismo nombre en todos los comandos.

Cobertura actual: reglas de Brand y Category, integridad de Category,
filtros y búsqueda de productos, orden y paginación, autenticación por
token, rechazo de escrituras anónimas, búsqueda vectorial y umbral,
flag de IA, embeddings idempotentes y `--force`, memoria multi-turno,
asignación de propietario a las conversaciones, rechazo de conversaciones
ajenas o sin dueño, construcción de mensajes para Ollama y exclusión de
campos internos del serializer de detalle.

La cobertura completa del CRUD de Product e imágenes sigue pendiente.

Para reiniciar los datos de desarrollo sin afectar Garage, se puede
vaciar la base de datos y volver a cargar el catálogo de demostración:

```bash
docker compose exec web python manage.py flush
docker compose exec web python manage.py createsuperuser
docker compose exec web python manage.py seed_demo
```

`flush` vacía los datos de la base configurada, incluidos los usuarios,
tokens y conversaciones. No es necesario para ejecutar las pruebas ni
para aplicar las migraciones de esta fase.
Los archivos ya subidos a Garage permanecen en el bucket, pero quedan
sin referencia en la base de datos.

## Autenticación y alcance

La API utiliza `TokenAuthentication` de Django REST framework.

- La lectura del catálogo y de sus registros de imágenes es pública.
- Crear, modificar y eliminar registros del catálogo requiere autenticación.
- Cualquier usuario autenticado puede modificar cualquier registro del
  catálogo: no existen roles ni propiedad de productos.
- El asistente requiere autenticación y cada usuario solo puede continuar
  sus propias conversaciones.

### Obtener un token

Las cuentas se crean desde Django Admin o mediante herramientas de
administración de Django. No hay endpoint público de registro.

Envía a `POST /api/auth/token`, con `Content-Type: application/json`:

```json
{
  "username": "TU_USUARIO",
  "password": "TU_CONTRASEÑA"
}
```

Con credenciales válidas, la respuesta incluye:

```json
{
  "token": "TOKEN_DEVUELTO"
}
```

En las peticiones autenticadas, envía:

```http
Authorization: Token TOKEN_DEVUELTO
```

No uses el prefijo `Bearer`. No guardes tokens ni contraseñas en el
repositorio ni los compartas en capturas.

### Decisiones de alcance

Este proyecto se centra en integrar IA mediante RAG en una API y en
gestionar imágenes con almacenamiento S3-compatible.

La autorización del catálogo se limita deliberadamente a lectura pública
y escritura autenticada. No se implementan roles, grupos de negocio ni
propiedad de productos. Por tanto, una cuenta autenticada puede modificar
registros creados por otra cuenta. Es una decisión de alcance, no una
garantía de autorización adecuada para una tienda multiusuario real.

Las conversaciones sí se aíslan por usuario porque forman parte del
historial personal del asistente. Conocer un UUID no concede acceso:
la API comprueba también el propietario.

Este aislamiento se aplica al endpoint del chat. No implica cifrado de
mensajes ni impide el acceso desde Django Admin a administradores con
los permisos correspondientes.

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
| `/api/ia/ask` | POST | Requiere token; recibe `query` y `conversation_id` opcional; solo permite continuar conversaciones propias |
| `/api/auth/token` | POST | Obtiene un token con credenciales de una cuenta existente |

Las rutas de la API se usan sin barra final. La lectura del catálogo es
pública; sus operaciones de escritura requieren el encabezado
`Authorization: Token <token>`.

En marcas, categorías y productos, `DELETE` realiza **borrado lógico**
(`active = false`). Para reactivar, se utiliza `PATCH` con `{"active": true}`.

En imágenes, `DELETE` elimina la fila de ProductImage. La eliminación
del archivo correspondiente en Garage todavía no está implementada.

## Filtros y búsqueda de productos

`GET /api/products` admite parámetros combinables:

## Filtros y búsqueda de productos

`GET /api/products` admite los siguientes parámetros combinables:

| Parámetro | Comportamiento |
| --- | --- |
| `brand` | Filtra por ID de marca |
| `category` | Filtra por ID de categoría e incluye sus descendientes |
| `min_price` | Precio mínimo, incluido |
| `max_price` | Precio máximo, incluido |
| `in_stock=true` | Solo productos con stock mayor que cero |
| `in_stock=false` | Solo productos con stock igual a cero |
| `search` | Busca en nombre, descripción, SKU, nombre de marca y nombre de categoría |
| `ordering` | Ordena por `price`, `name`, `created_at`, `stock` o `id`; el prefijo `-` invierte el orden |
| `page` | Selecciona una página de resultados |

Ejemplo:

```http
GET /api/products?search=monitor&min_price=1000&max_price=5000&in_stock=true&ordering=price
```

El listado mantiene la restricción de productos activos y una paginación
de 10 elementos. El orden predeterminado es `-created_at,id`.

Los parámetros `brand` y `category` deben identificar registros existentes;
los valores inválidos devuelven `400`.

Estos filtros son independientes de la recuperación semántica del RAG.
El endpoint del chat no aplica automáticamente los parámetros del listado
ni garantiza encontrar el producto más barato de todo el catálogo.

## Modelos

- **Category**: relación recursiva mediante `parent`; una subcategoría es una categoría con padre.
- **Brand**: marca de productos y estado `active`.
- **Product**: precio `Decimal(10,2)`, stock, especificaciones en `JSONB` y estado `active`.
- **ProductImage**: imagen mediante `ImageField`, relación con producto y marca de imagen principal. Cuenta con endpoints.
- **ProductReview**: calificación de 1 a 5, ligada a un producto y a un usuario. Todavía no tiene endpoints.
- **Conversation**: conversación persistente identificada mediante UUID y asociada a un usuario. El campo admite NULL para conservar conversaciones anteriores a la incorporación de autenticación; esas conversaciones no pueden continuarse desde la API.
- **Message**: pregunta o respuesta asociada a una conversación, con IDs de productos recuperados en la respuesta.

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
  registros de imágenes y reseñas; al borrar un usuario, sus reseñas y
  conversaciones. Al borrar una conversación se eliminan sus mensajes.
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

```powershell
curl.exe -X POST http://localhost:8000/api/product-images -H "Authorization: Token TU_TOKEN" -F "product=1" -F "image=@foto.jpg" -F "is_primary=true"
```

`TU_TOKEN` y el ID del producto deben sustituirse por valores reales.

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

Para subir imágenes utiliza Postman o curl con un token. Iniciar sesión
en Django Admin no autentica por sí solo las escrituras de la API, que
está configurada con TokenAuthentication.

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
- Antes de incorporar autenticación por token, se verificó la subida de
  una imagen real mediante la API navegable de DRF, con respuesta 201 Created.
  El procedimiento actual requiere enviar un token desde Postman o curl.
- Creación de una segunda imagen principal para el mismo producto:
  la anterior quedó con is_primary=false y la nueva con is_primary=true.
- Subida de imágenes con Pillow 13.0.0 respondió `201 Created`.

Estas comprobaciones son manuales; no equivalen a pruebas automatizadas.

## Asistente RAG

El asistente recupera productos del catálogo y construye una respuesta con
Ollama. El prompt exige usar el contexto actual, conservar precios exactos
y no inventar características; estas instrucciones no garantizan que el
modelo esté libre de errores.

### Configuración

Valores de ejemplo de `.env.example`:

```dotenv
AI_BASE_URL=http://ollama:11434
AI_EMBED_MODEL=nomic-embed-text
AI_CHAT_MODEL=qwen3.5:4b
AI_ENABLED=0
AI_MIN_SIMILARITY=0.60
AI_SEARCH_LIMIT=5
AI_HISTORY_MESSAGES=10
```

Configura `AI_ENABLED=1` para habilitar el asistente y el comando de
embeddings. El endpoint del chat requiere además autenticación.

Para una petición con token válido, `AI_ENABLED=0` devuelve 503.
Una petición anónima devuelve 401 antes de comprobar ese flag.
Con `AI_ENABLED=0`, `embed_products` no genera vectores.

Cambiar `.env.example` no modifica tu `.env` local. Después de cambiar
variables del servicio, recréalo para que las lea.

### Arquitectura del RAG

1. El cliente envía un token válido, `query` y, opcionalmente,
   `conversation_id`.
2. Se crea una Conversation asociada al usuario autenticado o se recupera
   una existente que pertenezca a ese mismo usuario. Un UUID ajeno,
   inexistente o sin propietario no permite continuar el chat y devuelve
   404. Después se leen los mensajes recientes de esa conversación.
   Message guarda rol, contenido e IDs de productos asociados.
3. `build_retrieval_query` antepone la última pregunta del usuario a la actual
   cuando existe historial. No hace una llamada adicional al LLM.
4. Ollama genera el embedding de esa consulta con `nomic-embed-text`
   (768 dimensiones).
5. Se consideran productos activos, con stock, marca y categoría activas y
   embedding no nulo. La consulta calcula distancia coseno mediante pgvector;
   el modelo dispone de un índice HNSW, aunque el plan de ejecución concreto
   lo decide PostgreSQL.
6. Se filtra por `similitud = 1 - distancia coseno`, aplicando el mínimo
   configurado antes de ordenar y limitar a `AI_SEARCH_LIMIT` productos.
7. Si hay resultados, se envían a Ollama las instrucciones `system`, el
   historial reciente y la pregunta con el contexto actual: nombre,
   descripción, especificaciones, precio en MXN y stock.
8. Si no hay resultados, se devuelve un mensaje fijo sin llamar al modelo
   de chat. En ambos casos se guardan la pregunta y la respuesta.

`AI_HISTORY_MESSAGES=10` permite reenviar hasta cinco turnos previos completos
(pregunta y respuesta). No limita el número total de preguntas: los mensajes
antiguos permanecen en PostgreSQL, pero salen de la ventana enviada al modelo.
El cliente debe reutilizar el UUID para continuar la conversación.

### Uso

Envía este cuerpo a `POST http://localhost:8000/api/ia/ask` desde
Postman (Body > raw > JSON), con los encabezados
`Content-Type: application/json` y `Authorization: Token TU_TOKEN`:

```json
{
  "query": "laptop para programar"
}
```

La respuesta incluye `conversation_id`, `answer` y `products` (IDs y nombres
de los productos recuperados). Copia el UUID devuelto y continúa con:

```json
{
  "query": "¿y la más barata?",
  "conversation_id": "PEGA_AQUI_EL_UUID_DEVUELTO"
}
```

Sustituye el marcador por el UUID real y conserva el token del propietario
para continuar el chat. Omite `conversation_id` para iniciar otra
conversación asociada al usuario autenticado.

Una petición anónima devuelve 401. Con autenticación válida y la IA
habilitada, un ID inexistente, ajeno, sin dueño o mal formado no vacío
devuelve 404; una petición sin pregunta devuelve 400.

Sin resultados, el endpoint responde 200 con el UUID de la conversación,
`products: []` y el texto exacto:

```text
No encontré productos relacionados con tu consulta.
```

### Embeddings idempotentes

```bash
docker compose -p <nombre-proyecto> exec web python manage.py embed_products
docker compose -p <nombre-proyecto> exec web python manage.py embed_products --force
```

El comando procesa productos activos. Omite un producto cuando ya tiene un
vector y su `embedding_hash` coincide con el hash calculado. `--force` obliga
a regenerarlo. Un vector ausente se genera aunque coincida el hash.

El hash SHA-256 combina el nombre del modelo de embeddings y el texto del
producto: nombre, descripción, especificaciones JSON ordenadas y categoría.
No es un hash del vector. Cambiar ese texto o el nombre del modelo provoca
regeneración en la siguiente ejecución. Un nuevo modelo debe ser compatible
con las 768 dimensiones del campo; cambiar el hash no adapta el esquema.

Editar productos no recalcula automáticamente sus embeddings: vuelve a
correr el comando. Los campos internos `embedding` y `embedding_hash` no se
exponen en el serializer de detalle público del producto.

### Validación manual local

Se generaron embeddings para 13 productos y se probaron consultas de laptops,
una continuación sobre la opción más barata, audífonos y una consulta ajena
al catálogo. Con el umbral 0.60, la prueba de audífonos recuperó los dos
productos pertinentes y la de casa voladora activó la respuesta vacía.
También se verificaron el precio exacto de la Vivobook S16 y la ausencia de
campos internos en el GET de detalle. Son comprobaciones locales, no una
medición general de calidad.

También se comprobó manualmente en Postman:

- Lectura pública del catálogo: 200.
- Escritura anónima del catálogo: 401.
- Uso anónimo del chat: 401.
- Creación y continuación del chat por su propietario: 200, conservando
  el mismo conversation_id al continuar.
- Intento de continuar ese chat con otro usuario: 404.
- Creación de un chat nuevo con el segundo usuario: 200 y otro UUID.

Estas comprobaciones verifican el comportamiento de autenticación y
aislamiento en los casos probados. No constituyen una auditoría de
seguridad ni una evaluación general de calidad del modelo.

### Limitaciones del RAG

- El umbral 0.60 se probó con el catálogo local; no garantiza relevancia para
  todas las consultas. La recuperación puede incluir otras categorías.
- “El más barato” se refiere a los productos del contexto recuperado, no
  necesariamente a todo el catálogo. La búsqueda semántica no ordena precios.
- La consulta de recuperación solo antepone la última pregunta: no realiza
  una reformulación completa de conversaciones largas.
- Limitar el número de mensajes no garantiza un máximo de tokens. También
  cuentan la longitud del historial, los productos y la respuesta.
- El prompt no elimina todos los errores, contradicciones o afirmaciones
  sin respaldo del modelo.
- Las conversaciones anteriores a la migración 0006 pueden conservar
  user=NULL y no son accesibles desde el endpoint del chat.
- El aislamiento por usuario se aplica a la API, no frente a
  administradores con acceso autorizado a Django Admin o PostgreSQL.
- Los errores de Ollama todavía pueden propagarse como 500; no hay manejo
  completo de fallos del proveedor.
- En una prueba manual con lenguaje coloquial
  ("monitor para chambear de chill"), el asistente recuperó monitores
  junto con laptops y orientó la recomendación hacia gaming en lugar
  de trabajo. Es una observación puntual, no una evaluación general
  del modelo. La comprensión de expresiones coloquiales y la pertinencia
  de las recomendaciones no están garantizadas.

## Limitaciones del almacenamiento de imágenes

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

- **Autorización del catálogo deliberadamente mínima**: la lectura es pública
  y cualquier usuario autenticado puede crear, modificar o eliminar
  registros del catálogo. No hay roles ni propiedad de productos.
  La API de desarrollo solo se publica en 127.0.0.1.
- **Las validaciones de la API solo aplican a la API**: el panel de administración, el shell y los scripts no pasan por los serializers. El caso más delicado son los ciclos de categorías; la base solo bloquea la autorreferencia directa. Una posible solución sería mover la regla a `Category.clean()`, pero se mantuvo simple.
- **Reactivación de categorías sin comprobar el padre**: un `PATCH` con `active: true` no verifica que la categoría padre esté activa. La reactivación de productos sí comprueba que su marca y categoría efectivas estén activas.
- **Pruebas automáticas parciales**: 75 tests cubren reglas de Brand y Category, filtros, autenticación, aislamiento de conversaciones, el pipeline RAG y la exclusión de campos internos del detalle de Product. La cobertura completa del CRUD de Product e imágenes sigue pendiente.

## Seguridad

- Las credenciales viven en `.env` y `garage.toml`, que están en `.gitignore` y `.dockerignore`. El repositorio solo incluye plantillas (`.env.example`, `garage.toml.example`).
- PostgreSQL no publica puertos. La API S3 de Garage y la API de Django solo escuchan en `127.0.0.1`.
- La key de Garage solo tiene permisos de lectura y escritura sobre un bucket.
- La API incorpora autenticación por token, pero conserva autorización
  global de escritura para usuarios autenticados. No está preparada
  para exponerse a Internet como una tienda multiusuario real.
- No envíes credenciales ni tokens por HTTP fuera del entorno local.
  Un despliegue remoto requiere HTTPS.
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
- [x] Memoria de conversación (multi-turno).
- [x] Flag `AI_ENABLED` para activar/desactivar el asistente.
- [x] Umbral de similitud para descartar resultados irrelevantes.
- [x] Embeddings idempotentes (saltar si ya existen).
- [x] Tests automatizados del RAG.
- [x] Autenticación y aislamiento de conversaciones por usuario.

### API

- [x] Endpoints de productos, con serializers de lista y detalle y validación de precio y stock.
- [x] Endpoints de imágenes mediante `ProductImageViewSet`.
- [x] Filtrado de imágenes por producto mediante `/api/product-images?product=<id>`.
- [x] Filtros y búsqueda de productos por categoría, marca, texto, precio, stock y orden.
- [x] Autenticación con TokenAuthentication y lectura pública/escritura autenticada, sin roles por decisión de alcance.
- [ ] Endpoints de reseñas, pospuestos hasta después de las fases de imágenes y cobertura de tests.
