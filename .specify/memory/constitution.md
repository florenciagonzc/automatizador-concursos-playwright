<!--
Sync Impact Report
- Version change: 1.0.0 → 1.1.0
- Principios modificados: II. Scraping modular, resiliente y responsable;
  III. Documentos y datos verificables; V. Pruebas y trazabilidad de resultados.
- Secciones añadidas: ninguna.
- Secciones eliminadas: ninguna.
- TODOs pendientes: ninguno.
-->

# Job Finder Constitution

## Core Principles

### I. Desarrollo guiado por especificaciones (SDD)
Toda funcionalidad nueva o cambio de comportamiento MUST comenzar con una
especificación revisable que describa el problema, alcance, criterios de
aceptación y casos límite. El plan técnico y las tareas MUST derivarse de una
especificación aprobada; la implementación MUST ajustarse a ella. Si durante el
desarrollo cambian los requisitos, se actualiza y revisa primero la
especificación. Este orden evita automatizar supuestos ambiguos sobre las
vacantes o el portal.

### II. Scraping modular, resiliente y responsable
La automatización MUST usar Python y Playwright con responsabilidades separadas
para navegación, extracción, transformación y persistencia. Toda espera de
navegación o elemento MUST declarar la condición esperada y un tiempo límite
explícito. Los reintentos MUST ser acotados, aplicarse solo a fallos transitorios
y operaciones seguras para repetir, y usar una pausa creciente; cada intento
fallido y el agotamiento de reintentos MUST quedar identificados en el error o
registro correspondiente. Los errores permanentes MUST propagarse. Los
selectores MUST priorizar roles, etiquetas y atributos estables frente a la
estructura frágil del DOM, y las suposiciones sobre su estructura MUST quedar
aisladas en los componentes de extracción. La extracción MUST detectar
resultados ausentes o cambios estructurales y fallar con contexto útil, no
devolver datos vacíos como si fueran válidos. Las pruebas MUST cubrir los
contratos de extracción con datos locales para detectar roturas ante cambios de
estructura sin depender del portal en vivo. La automatización MUST respetar las
condiciones de acceso y la disponibilidad del portal, evitando solicitudes
innecesarias y cualquier intento de eludir sus controles.

### III. Documentos y datos verificables
Los PDF descargados MUST procesarse con pdfplumber, validando que el archivo
exista, sea legible y produzca contenido utilizable antes de extraer campos;
los documentos sin texto utilizable MUST identificarse como fallidos, no como
vacantes sin datos. Los datos extraídos MUST normalizarse y validarse contra un
esquema explícito antes de estructurarse con Pandas. El resultado tabular MUST
conservar columnas y tipos acordes con ese esquema, incluso cuando no haya
registros válidos. Cada registro MUST conservar referencias trazables a su
vacante y documento fuente. PDF corruptos, vacíos, ilegibles o con campos
inesperados MUST generar errores identificables; no se permite silenciar fallos
ni presentar una extracción incompleta como resultado confiable.

### IV. Código limpio y fallos explícitos
El código MUST mantener módulos pequeños con responsabilidades claras, nombres
descriptivos y dependencias justificadas. El desarrollo y la ejecución MUST
usar un entorno virtual `.venv`, que no se versiona; las dependencias del
proyecto MUST declararse para permitir una instalación reproducible. El manejo
de excepciones MUST ser específico: los errores de red, tiempo de espera,
descarga, lectura y escritura MUST conservar su causa y aportar contexto
operativo. No se permiten capturas amplias que oculten errores ni valores por
defecto que conviertan un fallo en un resultado exitoso aparente.

### V. Pruebas y trazabilidad de resultados
Los componentes de navegación, extracción, análisis y persistencia MUST poder
probarse de forma independiente. Los cambios MUST incluir pruebas para sus
criterios de aceptación y casos de fallo relevantes, usando datos de prueba
locales cuando no se necesite acceder al portal. Las pruebas MUST comprobar que
un cambio estructural, un PDF no procesable o un error de red o E/S no se
conviertan en resultados vacíos presentados como válidos. Las ejecuciones MUST
permitir identificar qué vacante y archivo originaron cada dato y comunicar
claramente los fallos parciales. La selección de vacantes MUST considerar
perfiles de Ingeniería Informática y TI, y también cualquier vacante que no
requiera experiencia laboral previa; MUST distinguir «sin experiencia
requerida» de información de experiencia ausente o ambigua.

## Restricciones técnicas y operativas

- La fuente objetivo es Paraguay Concursa
  (`paraguayconcursa.mef.gov.py`); el proyecto automatiza búsqueda, descarga y
  análisis de vacantes, no la postulación en nombre de una persona.
- Playwright es la herramienta de navegación automatizada; pdfplumber es la
  herramienta de extracción de PDF y Pandas la de estructuración tabular. Un
  cambio de estas tecnologías requiere justificarlo en una especificación y
  actualizar el plan y las pruebas afectadas.
- Las descargas y resultados MUST preservar suficiente metadato para
  relacionarlos con la vacante de origen. Los archivos generados y el entorno
  virtual MUST mantenerse fuera del control de versiones salvo que una
  especificación aprobada establezca otra cosa.
- La automatización MUST aplicar límites razonables de frecuencia y MUST
  detenerse ante restricciones de acceso o errores persistentes, en lugar de
  incrementar agresivamente las solicitudes.

## Flujo de desarrollo

1. Crear o actualizar la especificación con `/speckit-specify`; resolver
   ambigüedades relevantes antes de aprobarla.
2. Elaborar el diseño y las decisiones técnicas con `/speckit-plan`, verificando
   su conformidad con esta constitución.
3. Derivar tareas comprobables con `/speckit-tasks`; cada tarea debe tener una
   salida verificable y respetar los límites de alcance aprobados.
4. Implementar con `/speckit-implement` y ejecutar las pruebas pertinentes.
   La revisión final MUST confirmar los criterios de aceptación, el manejo
   explícito de errores y la actualización de documentación afectada.
5. Si una decisión o requisito no puede cumplir esta constitución, detener la
   implementación de ese alcance y proponer primero una enmienda documentada.

## Governance

Esta constitución prevalece sobre convenciones locales incompatibles. Toda
especificación, plan, tarea, implementación y revisión MUST comprobar los
principios aplicables. Las enmiendas requieren describir el motivo y el impacto
en especificaciones, planes, tareas, código y pruebas existentes, y actualizar
la versión de acuerdo con el cambio: MAJOR para cambios incompatibles en
principios; MINOR para principios o secciones nuevas o ampliaciones materiales;
PATCH para aclaraciones sin cambio de obligaciones. No se debe implementar una
excepción como atajo: debe aprobarse y reflejarse primero en la constitución y
en los artefactos SDD afectados.

**Version**: 1.1.0 | **Ratified**: 2026-10-22 | **Last Amended**: 2026-10-23
