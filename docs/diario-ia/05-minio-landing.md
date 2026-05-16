# 05 — Decisión S3 → MinIO (landing zone)

## Contexto

El enunciado §4.2.2 ejemplifica "PostgreSQL + MinIO/S3 o MongoDB" como dos tipos de almacenamiento. En `SDD-03` dejamos la decisión **S3 AWS real vs MinIO local** como `[NEEDS CLARIFICATION]`. Llegó el momento de decidirla porque el ETL necesitaba un backend concreto para la capa raw.

## Prompts clave

> Aqui es donde tenemos que decidir s3 o minio?

*Pregunta clave antes del commit. La IA explicó que la abstracción `RawSource` permite diferir la decisión, pero reconoció que era un buen momento para cerrarla.*

> SI los profesores tienen el .env si funcionará no?

*Pregunta ingenua pero razonable. La IA respondió honestamente con tres fricciones: compartir credenciales AWS con el profesor es un problema de seguridad; el `.env` está en `.gitignore` así que el profesor clona el repo y no lo recibe (canal aparte necesario); coste + dependencia de Internet.*

> A que te refieres con bucket s3 publico solo-lectura? Mi idea es hacer una buena practica y segun me han enseñado los datos en crudo deberian estar en s3, es decir, cuando un usuario rellena el formulario se va a s3, y el pipeline lo coge de ahi y limpia y transforma y lodea en una base de datos no?

*El prompt que cerró la discusión.* El usuario expone el **patrón correcto** que le han enseñado: *landing zone* en S3 para datos crudos + pipeline que lee de ahí + persistencia final en PG/Mongo. La IA validó el patrón ("correcto y es buena práctica industrial"), aclaró que "bucket público solo-lectura" no aplicaba a su caso (necesita **escritura** desde el formulario, no solo lectura) y propuso **MinIO como backend S3-compatible**. Razón central: *"MinIO es un servidor 100% S3-compatible; mismo `boto3`, migrar a AWS real = cambiar `S3_ENDPOINT` y credenciales, 0 líneas de código. Tribunal levanta todo sin credenciales externas. En memoria: 'implementamos el patrón landing zone con MinIO como backend; en producción apuntaríamos a AWS S3'. Demuestra que entiendes el patrón, no que usaste S3"*.

> Vale si

*Decisión cerrada. La IA inmediatamente actualizó SDD-01 §7, SDD-02 §7, SDD-03 §7 tachando los `[NEEDS CLARIFICATION]` con referencia a la decisión, actualizó DESIGN-01 con el servicio `minio`, añadió servicios `minio` + `minio-init` (init con `mc mb --ignore-existing`) al compose, añadió bloque MinIO/S3 al `.env.example`.*

> y lo de s3 podemos eliminarlo? Ya que no lo usaremos

*Confusión: Pol cree que "S3" es sinónimo de "AWS". La IA explicó con analogía HTTP: "HTTP es un protocolo, cualquier servidor lo habla. S3 es un protocolo de almacenamiento de objetos; AWS lo inventó pero MinIO y otros también lo implementan. Las variables `S3_*` no son AWS-específicas, son el protocolo. Si las borramos, el pipeline no puede subir ni leer el CSV que acabamos de verificar que funciona".*

> A eso me referia! Quitar las menciones AWS del .env.example SI

*Aclaración: solo quería limpiar los comentarios que mencionaban AWS (potencial fuente de confusión en la defensa). La IA reformuló los comentarios sin mencionar AWS, manteniendo las variables intactas.*

## Lo que produjo la IA

- Decisión formal cerrada en SDD-01/02/03.
- `docker-compose.yml`:
  - Servicio `minio` (`minio/minio:RELEASE...`) con puertos 9000 (API S3) + 9001 (console web), healthcheck contra `/minio/health/live`, volumen `minio-data`.
  - Servicio `minio-init` (`minio/mc:RELEASE...`) con `restart: no` que ejecuta `mc alias set local ... && mc mb --ignore-existing local/hospital-raw` al arrancar.
  - `api` y `pipeline` con env vars `S3_ENDPOINT=http://minio:9000`, `S3_BUCKET_RAW=hospital-raw`, `S3_ACCESS_KEY_ID`/`S3_SECRET_ACCESS_KEY`.
- `.env.example`:
  ```
  # MinIO — servidor S3-compatible que almacena la capa raw (patrón landing zone).
  # El protocolo S3 es un estándar abierto; si algún día se usa otro backend
  # S3-compatible, basta con cambiar S3_ENDPOINT y las credenciales.
  MINIO_ROOT_USER=admin
  MINIO_ROOT_PASSWORD=change-me
  ...
  # Cliente S3 (boto3). Apunta al servidor MinIO definido arriba.
  S3_ENDPOINT=http://minio:9000
  ...
  ```
- `DESIGN-01 §5.1` tabla de servicios actualizada añadiendo `minio` y `minio-init`.
- Smoke test con 20 fichas: CSV sube a MinIO (`s3://hospital-raw/patients/upload-...csv`), pipeline lo lee, procesa, valida, persiste en PG/Mongo, llama al triaje. Timeline completa visible en el dashboard.

## Aciertos

- **No seguir con "solo AWS"**: la IA identificó el problema del tribunal sin credenciales (§4.1 "un solo comando") y me ahorró un aprieto en la defensa.
- **Bucket público como opción intermedia mencionada pero descartada**: la IA la propuso y la rechazó ella misma al ver que necesitaba escritura. Muestra pensamiento claro.
- **Sección explicativa del patrón landing zone en el informe**: el argumento de MinIO como *"mismo código, migración = cambiar endpoint"* es defendible en cualquier entrevista técnica.

## Correcciones que hubo que hacer

- **Confusión conceptual S3 ≠ AWS**: dos intercambios seguidos para aclararlo (el `y lo de s3 podemos eliminarlo`). La IA usó la analogía HTTP-como-protocolo correctamente para explicarlo. Lección: un término técnico puede tener dos significados (marca vs protocolo) y los prompts ambiguos producen confusión. La IA no asumió mi error — preguntó.

## Lecciones

1. **El patrón landing zone es muy potente** y merece ser explícito en la memoria: `raw → processed`, con dos sistemas de almacenamiento cumpliendo propósitos distintos (archivo objeto vs base de datos).
2. **MinIO es la herramienta correcta** para desarrollo cuando AWS S3 es el objetivo de producción. Industria estándar.
3. **Las dudas técnicas del usuario son oportunidades pedagógicas**: el debate "s3 vs aws" se resolvió con una analogía bien elegida. Si la IA hubiera respondido "claro, quitamos las variables" sin entender que S3 ≠ AWS, habría roto el sistema.

## Commits afectados

- `3e7767c` — feat(infra): MinIO como capa raw S3-compatible (landing zone)
- `4ae844f` — docs(env): reformula comentarios de .env.example para no mencionar AWS
