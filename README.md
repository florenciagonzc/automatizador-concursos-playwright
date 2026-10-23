# job-finder

Automatización bajo demanda para recorrer vacantes públicas de Paraguay
Concursa, descargar sus bases en PDF, extraer requisitos y exportar resultados
analizables para perfiles de Ingeniería Informática y TI.

## Requisitos

- Python 3.11 o posterior.
- Chromium instalado para Playwright (`playwright install chromium`).
- Revisar las condiciones vigentes y las pautas de acceso del portal antes de
  iniciar una consulta real. No se evaden controles de acceso.

## Instalación

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
playwright install chromium
```

## Ejecución

El rastreo no se inicia automáticamente. Para ejecutar el flujo completo,
confirma que revisaste las condiciones actuales y que la consulta pública está
permitida:

```bash
python -m job_finder run --confirm-public-access
```

Para limitar una ejecución manual a la primera página del listado:

```bash
python -m job_finder run --confirm-public-access --max-pages 1
```

Para visualizar la ventana del navegador durante la ejecución, añade `--headed`:

```bash
python -m job_finder run --confirm-public-access --headed
```

Por defecto, Playwright se ejecuta en modo headless.

`--max-pages` debe ser un entero positivo. El límite restringe el recorrido del
listado; los concursos encontrados en esas páginas se consolidan desde su
tarjeta y se procesan sus PDFs ofrecidos. Si el límite deja páginas del listado sin visitar,
la ejecución termina como `partial` y el reporte enumera la siguiente página
pendiente. Sin esta opción, el crawler recorre la paginación hasta su final
explícito. El límite no sustituye la revisión de autorización requerida antes
de cualquier ejecución real.

El crawler recorre secuencialmente las páginas y procesa cada concurso y su PDF
si está disponible. No abre «Ver proceso», porque esa opción conduce a una
ficha genérica; toma el URL del control exacto «Ver perfil» y descarga el PDF
mediante una petición HTTP GET directa al portal, validando la firma `%PDF-`.
Usa
timeouts de 20 segundos para navegación y espera de resultados, hasta dos
reintentos y al menos tres segundos entre navegaciones de primer nivel. Estos
valores están definidos en `src/job_finder/config.py`.
El CSV conserva todas las vacantes procesadas, incluidas las clasificadas como
no pertinentes para TI o con pertinencia indeterminada; la clasificación se
exporta como dato y no actúa como filtro. Las convocatorias de
`ENCUADRAMIENTO` y `ENCUADERNAMIENTO` siguen excluidas explícitamente por no
corresponder a vacantes.

Los errores de navegación, acceso, extracción, descarga y escritura se
conservan en el reporte del run. Una ejecución es `partial` cuando algún
objetivo falla o queda pendiente; los concursos independientes continúan
procesándose. Cada tarjeta no excluida se conserva como un registro de posición,
aunque el PDF falte o falle; sus campos no publicados quedan vacíos con estado.
Las tarjetas identificadas como `ENCUADRAMIENTO` o `ENCUADERNAMIENTO` se
omiten antes de hacer clic en el perfil o descargar su PDF y quedan registradas en
`skipped_contests` en el reporte JSON.

## Salidas

Cada ejecución genera:

- `data/exports/<run_id>/positions.csv`: CSV UTF-8 con exactamente 11 columnas
  estables (`contest_id`, `institution`, `position_title`, `salary`,
  `vacancies`, `budget_type`, `min_experience`, `optional_experience`,
  `contest_dates`, `pdf_url`, `contest_url`) y sin índice Pandas.
- `data/exports/<run_id>/run-report.json`: estado, páginas y concursos
  procesados, fallos y objetivos pendientes, además del arreglo `positions`
  detallado con estados técnicos, procedencia y análisis que no se incluyen en
  el CSV compacto.
- `data/tmp/<run_id>/pdf/`: PDFs descargados y procesados temporalmente.
- `data/processed_contests.json`: identificadores de convocatorias cuyos PDFs
  se analizaron correctamente; las ejecuciones posteriores las omiten antes
  de volver a descargar sus archivos. Si el estado aún no existe, se inicializa
  con los reportes históricos exitosos.

El análisis de bases PDF recorre todas las páginas y lee tanto texto como
tablas. Extrae denominación del puesto, oferta salarial, vacancias y experiencia
mínima/opcional cuando estén publicados.

El esquema de salida y su semántica están descritos en
[`specs/001-concursa-vacancy-search/contracts/output-contract.md`](specs/001-concursa-vacancy-search/contracts/output-contract.md).
Los directorios de salidas generadas y `.venv` están excluidos del control de
versiones.

## Validación offline

Las pruebas usan fixtures locales y no acceden al portal:

```bash
pytest
```

Consulta [`specs/001-concursa-vacancy-search/quickstart.md`](specs/001-concursa-vacancy-search/quickstart.md)
para los escenarios cubiertos y el flujo de validación.
