# Research: Paraguay Concursa vacancy search and analysis

**Date**: 2026-10-23

## Decisions

### Sequential browser navigation and pagination

- **Decision**: Use one Playwright page and process listing pages, contest
  details, and offered documents sequentially. Wait for a known listing or
  explicit empty-state locator rather than relying on `load`, `networkidle`, or
  fixed sleep as proof that content is ready.
- **Rationale**: The portal may render or load results after navigation. A
  page-specific readiness condition distinguishes an empty final page from a
  timeout or broken DOM and keeps interaction observable.
- **Alternatives considered**: A documented public feed/API or stable static
  HTML would be simpler and must be checked before using browser automation.
  Parallel browser pages were rejected because the constitution requires
  reasonable request pacing and sequential traversal.
- **Sources**: [Playwright navigation](https://playwright.dev/python/docs/navigations),
  [Playwright locators](https://playwright.dev/python/docs/locators),
  [Playwright auto-waiting](https://playwright.dev/python/docs/actionability).

### Pagination termination and safety

- **Decision**: Follow the portal's next-page link/cursor until it is explicitly
  absent, disabled, or an explicit end state is reached. Track normalized
  destinations and page fingerprints; a repeated destination or content page
  is a pagination error, not normal completion. A configured safety ceiling,
  if needed, results in a partial run when reached.
- **Rationale**: This supports changing page counts and guards against loops
  and false completion.
- **Alternatives considered**: Hard-coding the example page count was rejected;
  treating repeated content or an unreadable page as end-of-list was rejected.
- **Sources**: [Playwright Page API](https://playwright.dev/python/docs/api/class-page),
  [Playwright Response API](https://playwright.dev/python/docs/api/class-response).

### Waits, retries, and responsible pacing

- **Decision**: Start with explicit 20-second navigation and 20-second
  result-state timeouts, at most two retries after the initial attempt for
  transient failures, capped exponential backoff, and at least three seconds
  between top-level navigations. Honor longer crawl-delay guidance and
  `Retry-After`; stop on access restrictions, 401/403, persistent rejection,
  or retry exhaustion. Do not retry selector/schema errors or other permanent
  failures.
- **Rationale**: Finite budgets bound failure duration, and a slower
  sequential crawl prioritizes portal load and reliable status reporting.
  Initial timings are configurable implementation defaults and should be tuned
  only using observed portal latency and access guidance.
- **Alternatives considered**: Infinite retries, fixed sleeps as readiness
  checks, concurrent workers, and retrying access denials were rejected.
- **Sources**: [Playwright `page.goto`](https://playwright.dev/python/docs/api/class-page#page-goto),
  [RFC 9309 Robots Exclusion Protocol](https://www.rfc-editor.org/rfc/rfc9309.html),
  [Python `urllib.robotparser`](https://docs.python.org/3/library/urllib.robotparser.html),
  [RFC 6585 429](https://www.rfc-editor.org/rfc/rfc6585.html#section-4),
  [RFC 9110 Retry-After](https://www.rfc-editor.org/rfc/rfc9110.html#section-10.2.3).

### Offline browser and crawler tests

- **Decision**: Test HTML extraction and pagination logic with saved local
  fixtures; use Playwright request routing or a local fixture server for browser
  integration tests. Keep a live portal check opt-in.
- **Rationale**: Deterministic tests verify selectors, page termination, loop
  detection, status handling, and retry exhaustion without a live service or
  accidental traffic.
- **Alternatives considered**: Live portal access in the default test suite was
  rejected due to nondeterminism and unnecessary portal load.
- **Sources**: [Playwright network mocking](https://playwright.dev/python/docs/mock),
  [Playwright pytest integration](https://playwright.dev/python/docs/test-runners),
  [pytest monkeypatch](https://docs.pytest.org/en/stable/how-to/monkeypatch.html).

### PDF extraction and scanned documents

- **Decision**: Validate downloaded files (successful response, nonempty file,
  readable PDF with pages) and extract native text with pdfplumber. Record
  unreadable, encrypted, empty-text, or otherwise failed documents explicitly.
  Do not add OCR in the first version; mark image-only documents as requiring
  review or as not processable.
- **Rationale**: This matches the requested toolset and avoids adding OCR
  complexity without evidence that scans are common. A lack of native text must
  not be misrepresented as a vacancy with no requirements.
- **Alternatives considered**: OCR via OCRmyPDF/Tesseract was deferred pending
  demonstrated need and a quality-review approach; PDF structural validators
  are optional diagnostics, not proof of readability.
- **Sources**: [pdfplumber documentation](https://github.com/jsvine/pdfplumber/blob/stable/README.md),
  [pypdf text extraction and scanned documents](https://pypdf.readthedocs.io/en/stable/user/extract-text.html),
  [OCRmyPDF introduction](https://ocrmypdf.readthedocs.io/en/latest/introduction.html).

### Provenance and output format

- **Decision**: Maintain a fixed, ordered row schema and an explicit run
  report. Preserve the contest identity, source URLs, source PDF, retrieval
  time, extraction statuses, and classification rationale. Export UTF-8 CSV
  without an implicit index; generate the same header for zero rows. Re-read
  generated CSV in tests to verify column order, row count, Unicode, quoting,
  and missing-value behavior.
- **Rationale**: CSV does not preserve rich types or explain why a field is
  missing. Explicit statuses, provenance, and a separate run report make
  partial results auditable.
- **Alternatives considered**: Treating blank CSV cells as distinct states or
  using CSV as the complete system of record was rejected. A persistent
  database is unnecessary for this single-run, file-oriented scope.
- **Sources**: [pandas `DataFrame.to_csv`](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.to_csv.html),
  [pandas `read_csv`](https://pandas.pydata.org/docs/reference/api/pandas.read_csv.html),
  [Python `csv`](https://docs.python.org/3/library/csv.html),
  [RFC 4180](https://datatracker.ietf.org/doc/html/rfc4180).

## Access and operations precondition

Before implementing live navigation, inspect the portal's current terms,
`robots.txt`, and any published crawl guidance. Robots rules inform crawler
behavior but are not authorization. If access is prohibited, the relevant
workflow must stop and be reconsidered; no control bypass is permitted.

### Live listing selector spot-check on 2026-10-23

With the user's confirmation of authorization, the first listing URL
(`https://paraguayconcursa.mef.gov.py/?page=1&modo=lista`) was opened once in
Playwright. It returned HTTP 200 and reported 412 contests, with four cards
rendered on that page. No detail page was opened and no PDF was requested.

The rendered card markup distinguishes the controls:

- **Ver perfil** is a button with classes
  `concurso-ver-detalle btn-perfil btn-open-url`; its `data-url` points to a
  same-origin PDF under `/media/documentos/...pdf`.
- **Ver proceso** is a separate anchor with class `concurso-ver-detalle` and
  an `href` under `/publicaciones/.../`.

The current profile extraction scans anchors and buttons, selects the exact
`Ver perfil` label only when its resolved URL is a same-origin PDF/official
document. A live spot-check of all four rendered cards selected their
`/media/documentos/...pdf` URLs and did not select any `/publicaciones/.../`
process link. The initially implemented click-based PDF capture was replaced
by a same-origin direct HTTP GET to the exact URL extracted from `Ver perfil`;
the current flow does not click the control or open a process page. Regression
coverage for the observed button markup and direct GET behavior is in
`tests/integration/test_listing_crawl.py` and
`tests/integration/test_profile_click.py`.

### Single-contest live processing test on 2026-10-23

With the user's authorization confirmation, the crawler was run against page
1 only (`max_pages=1`) and exactly the first discovered contest was processed:
contest `id:13331`, titled `ENCUADRAMIENTO`. Although the listing contained
four cards, the other three were not opened or processed.

- The selected profile URL was the same-origin button `data-url` ending in
  `/media/documentos/2026/288/13331/manual-operativo-v2_-final_22_10_2026_08_52_37.pdf`.
- The contest detail endpoint returned HTTP 200, but its rendered page had no
  `#detalle-concurso` marker and no position cards. Its visible content
  identifies a public-service career encuadramiento process, not a vacancy
  detail page, so zero positions were extracted and the detail stage remained
  unresolved.
- The selected PDF was downloaded and opened locally by pdfplumber; it has 24
  pages and contains a "Manual Operativo" for incorporating public employees
  into the Civil Service Career. It does not use the expected vacancy section
  headings. The document status is therefore `review_required`, with
  `section_headings_not_found`; it must not be treated as a successfully
  analyzed vacancy PDF.
- The PDF was saved at
  `data/tmp/manual-one-contest-20261023/pdf/274b461fe262be820de7.pdf`.

**Result**: The live test confirms that the `Ver perfil` selector selected and
downloaded the correct PDF URL for this card. It does not establish successful
vacancy detail/PDF extraction for a vacancy-type contest. The result is
partial/unresolved, not an end-to-end success. No additional profile, detail,
or PDF was requested during the test.

### Review performed on 2026-10-23

- The public homepage at
  `https://paraguayconcursa.mef.gov.py/` was reachable and displayed the
  public contest listing and pagination (103 pages at the time of review).
  This confirms public visibility of the listings only; it does not establish
  permission for automated collection.
- `https://paraguayconcursa.mef.gov.py/robots.txt` returned HTTP 404. No
  robots directives or `Crawl-delay` value could therefore be reviewed.
- The homepage content contained no terms-of-use, privacy, or crawler-guidance
  text or links. The candidate paths `/terminos-y-condiciones/`, `/terminos/`,
  `/politica-de-privacidad/`, and `/aviso-legal/` each returned HTTP 404.
  These checks do not prove that no terms exist elsewhere or outside the
  inspected pages.
- No explicit terms authorizing automated consultation and no published
  crawling/rate guidance were found. Permission for automated consultation is
  therefore **unconfirmed**, not confirmed or denied. Do not run the live
  crawler until the portal operator or an authoritative policy source confirms
  that this use is permitted.
- The crawler's configured minimum interval remains three seconds between
  top-level navigations. Since no portal `Crawl-delay` was available, this
  interval satisfies the project default but cannot be represented as
  compliance with a portal-published rate limit. Any longer published delay
  must take precedence before live use.
- No live listing traversal, detail navigation, or document download was
  performed as part of this review.

**T031 status**: blocked pending authoritative confirmation of permission for
automated public-listing consultation and any applicable rate guidance.

### Profile and detail readiness refinements on 2026-10-23

The detail-navigation readiness check no longer requires the wrapper ID
`#detalle-concurso`; it recognizes position cards by their card class or
published position identifier. The extraction fixture intentionally has no
fixed wrapper ID.

The prior click-based capture supported response, download, popup, and viewer
paths. That mechanism is superseded by the direct HTTP GET and signature
validation described below. No live verification was performed for the current
change; it remains deferred until the user explicitly requests a live test.

### Bypass of generic "Ver proceso" pages

The live five-page run on 2026-10-23 found that the two non-excluded process
URLs timed out waiting for position cards, while the listing card exposed the
official PDF through its exact **Ver perfil** control. The process URL is a
generic institution page rather than a vacancy detail. The crawler creates one
position record from each included listing card and does not navigate to
`process_url`/`detail_url`; it obtains the profile URL from the listing and
downloads it directly. Missing profile links are recorded as `not_offered`,
and failed PDFs leave the listing-derived row available with a partial run
state. Offline integration tests verify no `/publicaciones/.../` request is
made. No live run was performed for this change.

### Direct profile PDF retrieval and table extraction

The profile URL is obtained from the exact `Ver perfil` control during listing
extraction and fetched with `page.context.request.get`. The request accepts
only a same-origin URL under `/media/documentos/` ending in `.pdf`; download
processing validates HTTP status, final origin, non-empty bytes, and the
`%PDF-` signature before persisting the file. It does not click the control,
navigate to the generic process URL, or follow an HTML viewer page.

PDF processing now calls `extract_text()` and `extract_tables()` for every page,
retains page-numbered table rows as evidence, and makes table content available
to the structured field parser. The parser can read denomination, remuneration,
vacancies, and minimum/optional experience from labeled cells without assuming
which page contains them. Offline regression coverage models the reported
13470 values; tests do not contact the live portal.

### PDF 13470 table-column verification

The previously downloaded 8-page PDF for contest 13470 was reprocessed locally
after the column-aware parser change. Its “Descripción del Puesto” table maps
“Auxiliar de Servicio - Chofer” to both position title and denomination. The
salary table maps `Gs. 2.900.000`, `7 (siete)`, and `FF: 10; OG: 111` from its
value row, not its header. The experience table maps the minimum requirement
from the “MÍNIMOS REQUERIDOS” column and the optional requirement from the
“OPCIONALES” column. All five dedicated field-status columns are `found`, and
`salary_status` is `published`. This was an offline reprocessing of the
existing PDF, not an additional portal request.

## Resolved open points

- No performance SLA was specified. The first implementation uses measured
  page/selector timeouts and conservative sequential pacing; it reports elapsed
  time but does not claim a speed target.
- No fixed contest count or page count is assumed. Pagination is discovered at
  run time; the user-provided example of approximately 103 pages is an expected
  scale reference, not a stopping condition.
- Native text extraction is the first-version boundary; OCR is deferred.
- The run remains on-demand; scheduling and history storage are out of scope.
