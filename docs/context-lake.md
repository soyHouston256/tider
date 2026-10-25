# Context Lake: recuperación documental en memoria

Primera implementación local. La consola permite arrastrar o seleccionar archivos
`.md` y `.drawio`, listar los documentos, retirarlos y buscar fragmentos con su
nombre, página y número de fragmento. No interpreta documentos como comandos.

El índice usa una colección Chroma efímera distinta por instancia de aplicación.
Cerrar o recargar el navegador conserva los documentos mientras siga vivo el
servidor. Reiniciar el servidor pierde documentos, fragmentos e índice. No se
escriben archivos subidos en disco ni se envían a un proveedor de generación.

Los embeddings se calculan localmente con el modelo predeterminado de Chroma,
`all-MiniLM-L6-v2`, mediante ONNX. La primera carga descarga y conserva los pesos
en la caché local del modelo; esa caché sí permanece en disco. Requiere conexión
para esa descarga inicial. No se configura un LLM ni una clave de pago. El modelo
es una elección provisional: falta evaluar recuperación con el corpus técnico
real en español e inglés antes de fijarlo definitivamente.

## Alcance

- Markdown excluye el front matter YAML antes de dividir por encabezados y
  fragmentos de hasta 900 caracteres. Los documentos de solo metadatos no se indexan.
- draw.io extrae texto de nodos y conexiones de páginas XML normales o comprimidas.
  Una conexión se etiqueta como relación dibujada, no como dependencia confirmada.
- No hay OCR, PDF, extracción de imágenes, importación de enlaces ni ejecución de
  contenido. Etiquetas personalizadas fuera de mxCell pueden requerir otro parser.
- Máximo 1 MB por archivo, 20 documentos y 300 fragmentos por sesión.
- Cargar el mismo nombre y contenido no crea un duplicado. Versiones con contenido
  distinto se conservan por separado hasta retirarlas.
- La búsqueda muestra hasta cuatro vecinos semánticos con su procedencia. Puede
  devolver candidatos irrelevantes; no afirma que sean respuestas ni evidencia
  de causalidad. Un filtro heurístico admite distancia coseno hasta 0,55 o
  coincidencia de al menos 65 % de los términos relevantes de la consulta. Si
  ninguno pasa, muestra que no encontró información suficiente. No es un
  clasificador de preguntas respondibles: puede descartar paráfrasis válidas
  o aceptar texto que mencione el tema sin resolverlo; requiere evaluación amplia.

## Catálogo revisable

El botón **Revisar catálogo** propone candidatos con sus fuentes. Extrae
identificadores técnicos en minúsculas de nodos draw.io, relaciones Mermaid y el
campo `service` del front matter Markdown. No interpreta prosa libre con un LLM;
no garantiza reconocer todos los servicios ni distinguir semánticamente todos los
componentes. Frases y títulos del diagrama no se convierten en identificadores.

Cada candidato conserva documento, página o bloque, y texto de origen. Coincidencias
con el mismo nombre se agrupan; no son corroboraciones independientes. Las relaciones
se agrupan por extremos. El operador selecciona servicios, corrige nombres, incluye
o descarta relaciones y puede corregir dirección y descripción. Los identificadores
confirmados deben corresponder a las etiquetas reales de la telemetría; no son alias
visuales. Corregir un nombre no renombra recursos ni modifica documentos originales.

Nada queda confirmado automáticamente. La confirmación guarda un catálogo en memoria,
con origen y valores originales. Rechaza revisiones antiguas, nombres duplicados,
candidatos inexistentes y relaciones con extremos no seleccionados. Cargar un nuevo
documento o retirar uno invalida la confirmación; volver a cargar un duplicado idéntico
no la invalida. Cerrar o recargar la pestaña conserva el catálogo; reiniciar lo pierde.

## Uso en la consulta y límites del diagnóstico

Con documentos cargados, los logs reales requieren un catálogo confirmado. El selector
GKE ofrece esos servicios; la consulta incluye el elegido y sus vecinos directos en
ambos sentidos de las relaciones confirmadas. No recorre dependencias transitivas.
Proyecto, clúster, región, namespace, ventana y límites de registros siguen acotados
por la configuración existente. El proveedor valida el catálogo también fuera de la UI.

Los escenarios mock conservan su catálogo fijo. Sin documentos, GKE conserva el catálogo
predeterminado de Online Boutique. El catálogo documental no verifica que los recursos
existan actualmente ni concede acceso al clúster.

El diagnóstico sigue con reglas y contexto empaquetado: esta etapa no conecta la
recuperación de documentos al razonamiento del investigador. No usar el baseline de
Boutique como diagnóstico general de otra plataforma. Queda pendiente elegir un LLM,
conectar el contexto revisado al grafo y evaluar con casos independientes.

## API local

- `GET /v1/context`: inventario y límites.
- `POST /v1/context/documents`: JSON con `name` y `content` UTF-8.
- `DELETE /v1/context/documents/{doc_id}`: retira documento y sus fragmentos.
- `POST /v1/context/search`: JSON con `query`; devuelve fragmentos candidatos.
- `GET /v1/context/catalog`: propuesta, revisión y catálogo confirmado.
- `POST /v1/context/catalog/confirm`: revisión, servicios y relaciones seleccionadas.

La API usa el acceso local de la consola, sin autenticación multiusuario. Rechaza
escrituras desde orígenes web diferentes. No exponer este servidor públicamente.

## Validación

Pruebas con Chroma real y embeddings pequeños deterministas para no descargar
modelos en la suite: aislamiento, duplicados, recuperación, eliminación, límites,
rechazo de XML con entidades externas y equivalencia draw.io normal/comprimido.
La comprobación del modelo local real se realiza aparte de estas pruebas.

### Mapa de revisión

La revisión incluye un diagrama SVG de los candidatos y las relaciones seleccionadas.
Se actualiza al corregir nombres, extremos o descripciones. Los nodos verdes están
incluidos en el borrador; gris indica que no están seleccionados. Ninguno se activa
hasta confirmar. Seleccionar un nodo abre su origen en la lista de revisión.
Las flechas expresan relaciones documentadas, no tráfico observado. El mapa admite
ciclos y usa desplazamiento horizontal en pantallas estrechas. La edición se realiza
en los campos de revisión; no es un editor libre de diagramas draw.io.
