# Feature Specification: Búsqueda y análisis de vacantes en Paraguay Concursa

**Feature Branch**: `Sin rama asignada`

**Created**: 2026-10-23

**Status**: Draft

**Input**: User description: "Recorrer secuencialmente todas las páginas del listado general de Paraguay Concursa, extraer datos de concursos y puestos, descargar sus bases en PDF, extraer información clave y consolidar los resultados para su consulta y exportación."

## Clarifications

### Session 2026-10-23

- Q: ¿Qué regla debe determinar si dos registros del listado corresponden al mismo concurso? → A: Usar el identificador oficial del concurso cuando esté disponible y, si no, su enlace canónico al detalle.
- Q: Si falla la descarga o lectura de las bases de un concurso, ¿el sistema debe continuar procesando los demás concursos? → A: Continuar con los demás, registrar el fallo y marcar la ejecución como parcial.
- Q: Si la ejecución queda parcial, ¿qué debe pasar con los resultados que sí se obtuvieron? → A: Permitir exportar los resultados disponibles, identificando claramente la ejecución como parcial y los concursos pendientes o fallidos.
- Q: ¿Cómo debe decidirse si una vacante es pertinente para Ingeniería Informática o TI? → A: Evaluar los requisitos y funciones publicados que mencionen formación, conocimientos o tareas de informática/TI; los casos ambiguos quedan indeterminados.
- Q: ¿La búsqueda debe ejecutarse solo cuando una persona la inicia o también de forma programada y recurrente? → A: Solo bajo demanda en esta versión.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Recorrer el listado de concursos (Priority: P1)

Una persona ejecuta la búsqueda y obtiene los concursos del listado general,
sin tener que avanzar manualmente por cada página. El recorrido comienza en la
primera página y continúa en orden hasta que el portal indique que no hay una
página siguiente. Por cada concurso se conservan los datos visibles y los
enlaces que permiten localizar su perfil y proceso.

**Why this priority**: El listado completo es la base para conocer y analizar
las oportunidades disponibles; sin él, las etapas posteriores no pueden
demostrar cobertura.

**Independent Test**: Usar un listado de prueba con varias páginas, concursos
conocidos y una última página identificable. Comparar el orden y cantidad de
concursos obtenidos con el listado de referencia.

**Acceptance Scenarios**:

1. **Given** un listado con varias páginas, **When** se inicia una búsqueda,
   **Then** se procesan en orden desde la página 1 hasta la última indicada por
   el portal, sin omitir páginas intermedias.
2. **Given** un concurso visible en una página, **When** se procesa el listado,
   **Then** se registran su título, institución, estado, fechas visibles y
   enlaces disponibles al perfil y al proceso.
3. **Given** que el portal informa que no existe una página siguiente,
   **When** se alcanza esa página, **Then** el recorrido del listado termina y
   se identifica como completo.
4. **Given** que una página no puede leerse tras los intentos permitidos,
   **When** se interrumpe el recorrido, **Then** el resultado se identifica
   como parcial y señala la página y el motivo, sin declararse completo.
5. **Given** que una persona quiere actualizar los resultados,
   **When** inicia una búsqueda, **Then** el sistema ejecuta un nuevo recorrido
   bajo demanda y no inicia recorridos periódicos sin una acción de la persona.

---

### User Story 2 - Procesar la convocatoria y sus bases (Priority: P2)

Una persona procesa el puesto a partir de la tarjeta del listado y, cuando se
ofrecen las bases, obtiene el URL PDF oficial del control «Ver perfil» y descarga
ese recurso con una petición HTTP GET directa. El enlace «Ver proceso» se
conserva como referencia del listado, pero no se abre porque lleva a una ficha
genérica que no contiene los datos del puesto ni las bases.

**Why this priority**: Los datos del listado identifican la oportunidad y las
bases PDF aportan información esencial y verificable sin depender de la ficha
genérica «Ver proceso».

**Independent Test**: Probar con concursos de referencia con y sin URL PDF en
«Ver perfil», y con respuestas PDF correctas, HTML y errores HTTP. Verificar
que el flujo nunca navega al enlace «Ver proceso», conserva los datos del
listado, valida la firma `%PDF-` y asocia el archivo a la vacante.

**Acceptance Scenarios**:

1. **Given** una tarjeta del listado con enlaces «Ver proceso» y «Ver perfil»,
   **When** se procesa, **Then** se conserva el enlace del proceso como dato,
   pero no se navega a él; se toma el URL exclusivamente del control exacto
   «Ver perfil».
2. **Given** un concurso que ofrece un PDF de bases, **When** se recopilan sus
   documentos, **Then** se hace una petición HTTP GET al URL oficial de
   `Ver perfil`, se valida que la respuesta comience con `%PDF-` y se guarda
   bajo `data/tmp/<run_id>/pdf/` asociado al concurso/puesto, sin abrir la ficha
   intermedia.
3. **Given** un concurso sin PDF disponible, **When** se procesa, **Then** se
   conserva el resto de sus datos y se informa explícitamente que el documento
   no está disponible.
4. **Given** que la descarga o lectura del PDF falla de forma persistente,
   **When** termina su procesamiento, **Then** el fallo queda asociado al
   concurso afectado y no se presenta como una descarga o extracción exitosa,
   mientras la fila derivada del listado se conserva.
5. **Given** que un concurso contiene varios puestos o aparece repetido en el
   listado, **When** se consolida, **Then** se crea un puesto por tarjeta y se
   conserva su relación con el concurso correspondiente, usando la
   denominación/código visibles cuando se publican.
6. **Given** que falla de forma persistente la descarga o lectura de las bases
   de un concurso, **When** se procesa el resto del listado, **Then** los demás
   concursos continúan procesándose y la ejecución queda marcada como parcial.
7. **Given** un PDF legible que publica las secciones «Descripción del Puesto»,
   «Oferta Salarial» y «Perfil Requerido», **When** se procesa el documento,
   **Then** el texto de cada sección se conserva por separado junto con las
   páginas fuente para su análisis posterior.
8. **Given** que la tarjeta web publica un nombre/título de convocatoria y una
   denominación o código de puesto, **When** se extraen los datos del listado,
   **Then** ambos valores se conservan como campos distintos en cada puesto
   relacionado.
9. **Given** un PDF de varias páginas con datos de oferta salarial o experiencia
   en texto o en tablas de cualquiera de sus páginas, **When** se procesa,
   **Then** se analizan todas las páginas y se extraen salario/remuneración,
   cantidad de vacantes, tipo de puesto/presupuesto, denominación del puesto y
   requisitos mínimos y opcionales de experiencia, manteniendo separados los
   valores publicados.
10. **Given** una tabla de oferta salarial con encabezados y una fila de valores,
    **When** se procesa, **Then** la remuneración se mapea desde la columna
    «Salario», las vacancias desde «Vacancias» y la clasificación presupuestaria
    desde «FF» y «OG», no desde la fila de encabezados. La denominación de la
    tabla «Descripción del Puesto» se exporta como `position_title` y
    `position_name`; los campos que se extraen correctamente tienen estado
    `found` en el CSV.
---

### User Story 3 - Revisar y exportar resultados consolidados (Priority: P3)

Una persona obtiene una tabla que relaciona los datos del listado, el detalle
del puesto y la información clave de las bases. Puede exportar los resultados
para filtrarlos, compararlos y revisarlos fuera de la ejecución. Las
oportunidades de Ingeniería Informática y TI y las que no requieren experiencia
previa pueden identificarse sin perder el resto de los concursos recolectados.

**Why this priority**: La consolidación convierte la recolección en información
útil para comparar oportunidades y permite revisar su origen.

**Independent Test**: Procesar un conjunto pequeño de concursos y PDF
conocidos; verificar los campos, su origen, las etiquetas de perfil y que la
exportación contenga los mismos registros que la tabla consolidada.

**Acceptance Scenarios**:

1. **Given** un PDF legible con requisitos y condiciones, **When** se procesa,
   **Then** se extraen los campos clave publicados y se conserva la referencia
   al PDF de origen.
2. **Given** un PDF corrupto, vacío o sin texto utilizable, **When** se procesa,
   **Then** el documento queda marcado como no procesable, sin inventar datos
   ni clasificar la vacante como carente de requisitos.
3. **Given** un puesto que declara no requerir experiencia, **When** se
   consolida, **Then** se distingue de un puesto cuyo requisito de experiencia
   está ausente o es ambiguo.
4. **Given** que existen concursos de distintos perfiles, **When** se genera
   el resultado, **Then** cada concurso queda disponible y los de Ingeniería
   Informática, TI o sin experiencia requerida pueden identificarse mediante
   sus datos o clasificación.
5. **Given** una ejecución con resultados, **When** la persona exporta la
   tabla, **Then** obtiene un CSV legible y consistente con los registros
   consolidados.
6. **Given** un registro consolidado con un documento asociado, **When** se
   revisa el resultado, **Then** se puede rastrear la fila hasta el concurso y
   el documento de origen.
7. **Given** una página de paginación que no avanza o repite un destino,
   **When** se intenta continuar el recorrido, **Then** la ejecución se detiene
   como parcial e identifica el problema, sin entrar en un bucle ni declarar
   cobertura completa.
8. **Given** una ejecución parcial con resultados obtenidos, **When** la persona
   revisa o exporta la tabla, **Then** puede usar los resultados disponibles y
   distinguir claramente la ejecución parcial y los concursos pendientes o
   fallidos.
9. **Given** que los requisitos y funciones publicados no permiten determinar
   con claridad si un puesto corresponde a Ingeniería Informática o TI,
   **When** se clasifica la vacante, **Then** queda marcada como indeterminada
   en lugar de asignarse una categoría sin evidencia suficiente.
10. **Given** puestos extraídos del listado y de sus PDF, **When** finaliza la
    ejecución, **Then** el CSV contiene exactamente las once columnas
    `contest_id`, `institution`, `position_title`, `salary`, `vacancies`,
    `budget_type`, `min_experience`, `optional_experience`, `contest_dates`,
    `pdf_url` y `contest_url`, mientras el JSON contiene un registro detallado
    por cada fila y conserva estados y procedencia.

### Edge Cases

- El listado no contiene concursos o contiene una página sin resultados.
- El portal presenta un enlace de paginación ausente, repetido o que no avanza;
  el recorrido debe evitar bucles y no anunciar cobertura completa sin verificar
  la última página.
- Un concurso aparece más de una vez o tiene varios puestos asociados; los
  registros no deben duplicarse accidentalmente ni perder la relación entre
  concurso y puesto.
- Un campo no se publica, tiene un formato inesperado o no puede interpretarse;
  debe quedar como desconocido o no disponible, sin completar un valor supuesto.
- Un enlace al detalle o al PDF no está disponible, deja de funcionar o conduce
  a un documento que no puede leerse.
- El PDF tiene páginas vacías, texto ilegible o contenido que no permite extraer
  uno o más campos clave.
- Un error de red, espera o lectura/escritura interrumpe el procesamiento; los
  datos ya obtenidos deben conservarse como parciales y el fallo debe ser
  identificable.
- La página del portal limita el acceso o muestra una restricción; el proceso
  debe detenerse de manera controlada y no intentar eludirla.
- Una ejecución no produce filas válidas; la estructura exportable sigue
  identificable como vacía, sin confundirse con un fallo no reportado.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: El sistema MUST iniciar el recorrido en la primera página del
  listado general público de Paraguay Concursa.
- **FR-002**: El sistema MUST avanzar de forma secuencial hasta detectar la
  última página a partir de la navegación ofrecida por el portal; MUST NOT
  depender de un número de páginas fijo.
- **FR-003**: El sistema MUST registrar por cada concurso del listado el título,
  institución, estado, fechas visibles y enlaces disponibles al perfil y al
  proceso.
- **FR-004**: El sistema MUST crear un registro de posición a partir de cada
  tarjeta de concurso incluida y preservar el título, denominación/código,
  institución y enlace de perfil publicados. MUST NOT navegar al enlace
  «Ver proceso» para extraer detalles; los campos no presentes en el listado o
  PDF deben quedar explícitamente no disponibles.
- **FR-005**: El sistema MUST descargar las bases y condiciones cuando el
  concurso ofrezca un PDF, guardarlo en un directorio temporal dentro del
  proyecto y conservar la asociación entre archivo y concurso o puesto.
- **FR-006**: El sistema MUST indicar explícitamente cuándo un PDF no está
  disponible, no puede descargarse o no puede procesarse.
- **FR-007**: El sistema MUST extraer de los PDF legibles la información clave
  publicada sobre perfil, formación, experiencia, funciones, remuneración y
  condiciones de postulación, cuando corresponda.
- **FR-008**: El sistema MUST consolidar los datos del listado y PDF en
  registros tabulares que puedan revisarse como tabla y exportarse a CSV.
- **FR-009**: Cada registro consolidado MUST preservar el enlace de origen del
  concurso y la referencia del documento asociado cuando exista.
- **FR-010**: El sistema MUST distinguir un requisito de experiencia declarado
  como inexistente de un dato ausente, ilegible o ambiguo.
- **FR-011**: El sistema MUST permitir identificar concursos pertinentes para
  Ingeniería Informática y TI, así como puestos que no requieren experiencia
  previa, sin descartar por defecto los demás concursos recolectados.
- **FR-012**: Los datos que no estén publicados o no puedan determinarse MUST
  marcarse como desconocidos o no disponibles; el sistema MUST NOT inventar ni
  inferir valores para presentarlos como publicados.
- **FR-013**: Ante fallos persistentes de navegación, red, descarga o lectura y
  escritura, el sistema MUST informar el concurso o página afectada, el tipo de
  fallo y si el resultado de la ejecución quedó parcial; un fallo aislado de
  descarga o lectura de bases MUST NOT impedir procesar los demás concursos.
- **FR-014**: El sistema MUST distinguir una ejecución completa de una parcial
  y MUST NOT declararla completa si alguna página o PDF
  ofrecido quedó sin procesar; la ausencia declarada de un PDF no cuenta como
  fallo de procesamiento.
- **FR-015**: El sistema MUST aplicar límites de espera y reintentos acotados
  para fallos transitorios, y detenerse ante restricciones de acceso del portal.
- **FR-016**: El sistema MUST identificar un concurso por su identificador
  oficial cuando esté disponible y, en su ausencia, por su enlace canónico al
  detalle; MUST evitar duplicados con esa identidad y conservar cada puesto
  relacionado con el concurso.
- **FR-017**: El sistema MUST permitir revisar y exportar los resultados
  disponibles de una ejecución parcial, indicando su estado y los concursos
  pendientes o fallidos.
- **FR-018**: El sistema MUST evaluar la pertinencia para Ingeniería Informática
  o TI usando la formación, los conocimientos y las funciones publicados; si
  esos datos no permiten una clasificación clara, MUST marcarla como
  indeterminada y preservar la información que fundamenta la evaluación.
- **FR-019**: El sistema MUST ejecutar búsquedas únicamente bajo demanda en esta
  versión y MUST NOT iniciar búsquedas periódicas automáticas.
- **FR-020**: Cada puesto consolidado MUST conservar por separado el nombre o
  título de convocatoria publicado en la web y la denominación o código de
  puesto publicado en la tarjeta, cuando estén disponibles.
- **FR-021**: El procesamiento de PDF MUST analizar todas las páginas y extraer
  los campos publicados de oferta salarial (salario/remuneración, vacantes y
  tipo de puesto o presupuesto) y experiencia laboral (mínimos requeridos y
  opcionales) sin fusionar requisitos de distinta categoría.
- **FR-022**: El CSV y el reporte JSON MUST exponer los campos consolidados por
  puesto. El JSON MUST conservar estados explícitos cuando un campo no pueda
  leerse o no esté publicado; el CSV utiliza el esquema compacto definido en
  FR-025.
- **FR-023**: El sistema MUST obtener el URL PDF del control exacto «Ver perfil»
  y descargar el recurso con una petición HTTP GET directa, validando la firma
  `%PDF-`; MUST NOT navegar a la URL «Ver proceso» como etapa intermedia.
- **FR-024**: El sistema MUST asociar celdas de tablas PDF mediante sus
  encabezados y columnas, mapear la fila de valores de oferta salarial y las
  columnas de experiencia mínima/opcional a campos dedicados, y exportar
  `position_title`, `position_name`, `salary_raw`, `salary`, `vacancies` y
  `position_type_budget` con estado `found` cuando haya evidencia legible.
- **FR-025**: El archivo `positions.csv` MUST contener únicamente, y en este
  orden, las columnas `contest_id`, `institution`, `position_title`, `salary`,
  `vacancies`, `budget_type`, `min_experience`, `optional_experience`,
  `contest_dates`, `pdf_url` y `contest_url`. MUST NOT incluir columnas de
  estado técnico, valores redundantes/raw, relevancia TI o metadatos internos
  del documento; el reporte JSON MUST conservar un registro detallado por
  puesto con los estados y la procedencia necesarios para interpretar la
  ejecución.
- **FR-026**: El sistema MUST mantener en `data/processed_contests.json` los
  identificadores oficiales de convocatorias cuyos PDF se descargaron y
  analizaron correctamente. Antes de solicitar el perfil de una convocatoria,
  MUST omitir las identificadas como procesadas y reportarlas como
  `already_processed`. MUST registrar cada ID inmediatamente después de que la
  descarga, lectura PDF y extracción estructurada concluyan correctamente;
  los fallos, enlaces sin PDF y documentos que requieran revisión MUST NOT
  marcarse como procesados. Si no existe estado previo, MUST inicializarlo a
  partir de reportes históricos con documentos `processed`.

### Key Entities *(include if feature involves data)*

- **Concurso**: Registro publicado en el listado general; incluye su
  identificador oficial cuando esté disponible o, en su ausencia, el enlace
  canónico al detalle como identidad, además de título, institución, estado,
  fechas, enlaces al perfil y al proceso, y referencia a la página donde fue
  encontrado.
- **Puesto**: Oportunidad laboral vinculada a un concurso; incluye título,
  institución, remuneración, fecha límite, enlace de detalle y clasificación
  sobre perfil TI y experiencia requerida cuando la información lo permita,
  junto con el fundamento publicado o el estado indeterminado de cada
  clasificación.
- **Bases y condiciones**: Documento ofrecido para un concurso o puesto; incluye
  ubicación temporal, estado de descarga y procesamiento, contenido clave
  extraído y vínculo al origen.
- **Ejecución de búsqueda**: Recorrido de una consulta; incluye páginas
  procesadas, estado completo o parcial y los errores asociados.
- **Resultado consolidado**: Fila tabular trazable a su concurso, puesto y
  documento fuente, con los campos publicados o estados explícitos de ausencia.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: En un listado de referencia de varias páginas, el 100% de las
  páginas desde la primera hasta la última se representa en el resultado de una
  ejecución declarada completa, sin páginas omitidas.
- **SC-002**: En el conjunto de referencia, el 100% de los concursos visibles
  queda registrado una vez, con sus datos publicados o con un estado explícito
  para cada dato ausente.
- **SC-003**: Para todos los puestos de referencia con detalle accesible, el
  100% conserva un enlace directo y los valores publicados de remuneración y
  fecha límite; los campos no publicados se identifican como no disponibles.
- **SC-004**: Para todos los concursos de referencia que ofrecen bases
  descargables, el 100% de los PDF válidos queda asociado a su origen; los
  documentos no disponibles o no procesables quedan identificados como tales.
- **SC-005**: En un conjunto de referencia con contenido conocido, cada campo
  clave extraído coincide con el documento fuente o queda marcado como ausente,
  ambiguo o no procesable; ningún error de extracción se representa como un
  dato confirmado.
- **SC-006**: La exportación CSV contiene el mismo número de registros que la
  tabla consolidada y permite rastrear cada fila hasta su concurso de origen.
- **SC-007**: Las oportunidades de Ingeniería Informática, TI y sin experiencia
  requerida pueden identificarse en el resultado, y la ausencia de información
  de experiencia no se clasifica como «sin experiencia requerida»; los casos
  de pertinencia TI sin evidencia clara se marcan como indeterminados.
- **SC-008**: Cada `positions.csv` contiene exactamente las once columnas
  especificadas, en el orden publicado, incluso cuando no tiene filas; ninguna
  columna de estado técnico, valor raw, relevancia TI o metadatos internos del
  documento aparece en el CSV, mientras el JSON conserva los registros
  detallados correspondientes.
- **SC-009**: En una segunda ejecución con el mismo estado persistente, ninguna
  convocatoria ya procesada genera una solicitud a su perfil; las nuevas
  convocatorias se procesan y sus identificadores se agregan al registro solo
  después de una extracción PDF exitosa.

## Assumptions

- La búsqueda cubre el listado general público disponible durante la ejecución;
  no requiere iniciar sesión, postular a concursos ni eludir restricciones.
- El número total de páginas cambia con el portal y se determina durante cada
  recorrido, no mediante una cifra preconfigurada.
- Se conserva cada concurso recolectado; la pertinencia para TI y la experiencia
  previa se usan para identificar oportunidades, no para excluir resultados por
  defecto.
- Un concurso puede contener uno o varios puestos; cuando haya varios, cada
  puesto puede tener su propio registro relacionado con el mismo concurso.
- Las bases se descargan en un directorio temporal del proyecto y no se
  consideran parte del CSV exportado.
- La constitución vigente del proyecto determina las herramientas y prácticas
  técnicas obligatorias; esta especificación define el comportamiento y los
  resultados esperados.
- Las fechas y remuneraciones se conservan según la publicación original; solo
  se normalizan si el valor puede interpretarse sin ambigüedad.
- Los errores persistentes pueden dejar resultados parciales utilizables, pero
  siempre se informa qué quedó sin procesar.
- Cada recorrido se inicia por acción de la persona; la ejecución programada o
  periódica queda fuera del alcance de esta versión.
