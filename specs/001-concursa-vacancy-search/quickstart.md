# Quickstart: Validate the vacancy search pipeline

This guide describes local validation and the guarded, opt-in portal workflow.

## Prerequisites

- Python 3.11 or later.
- Network access to the public portal only after its terms and crawler guidance
  have been reviewed and no restriction prevents the requested access.
- No account, application submission, or access-control bypass is used.

## Local setup

From the repository root:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

Dependencies are declared by the project package metadata. The `.venv`,
downloaded PDFs, and generated exports are not versioned.

## Offline validation

Run tests using local fixtures only:

```bash
pytest
```

Expected coverage includes:

1. Sequential traversal stops only when a valid page confirms there is no next
   page.
2. A repeated URL/cursor or repeated page fingerprint is reported as a partial
   crawl rather than a successful end.
3. A transient navigation failure retries within the configured budget; a
   timeout, access denial, or retry exhaustion is reported with its page or
   contest context.
4. A PDF failure does not prevent independent contests from processing; the
   listing-derived row remains exportable and the run becomes partial.
5. The crawler obtains the official URL from each non-excluded card's exact
   **Ver perfil** control, uses a direct HTTP GET, validates the `%PDF-` file
   signature, and stores the PDF under `data/tmp/<run_id>/pdf/`; it never opens
   **Ver proceso** or follows an intermediate viewer page.
6. Native-text, empty, malformed, encrypted, and image-only PDFs produce
   distinct explicit outcomes; no failed extraction is presented as a valid
   empty requirements field.
7. Native PDF text is segmented into the published `Descripción del Puesto`,
   `Oferta Salarial`, and `Perfil Requerido` sections with page provenance.
8. Empty and populated CSV files contain exactly the eleven documented columns
   and pass round-trip checks for row count, Unicode, commas, and quotes; the
   JSON report preserves detailed statuses and provenance.
9. A bounded crawl such as `--max-pages 1` visits only the first listing page,
   still processes contests found there, and reports unvisited listing pages
   as pending in a partial run.
10. Profile extraction selects the exact **Ver perfil** control and never the
    general **Ver proceso** link.
11. Cards whose title, type, or label contains **ENCUADRAMIENTO** or
    **ENCUADERNAMIENTO** produce a skipped-contest report entry and trigger no
    detail or PDF request.
12. Profile downloading uses only the PDF URL published by the exact
    **Ver perfil** control inside the listing card; a direct PDF link without
    that label and a **Ver proceso** link are not used as profile controls.
13. Position extraction works when the position cards are not wrapped in a
    fixed `#detalle-concurso` element.
14. A direct **Ver perfil** GET accepts a same-origin PDF response and rejects
    HTML, non-PDF bytes, HTTP errors, and redirects away from the portal origin.
15. Processing a contest never sends a navigation request to its **Ver proceso**
    URL; one row is made from each included listing card, then enriched from
    the profile PDF when one is available.
16. Structured PDF-table extraction maps the denomination to both
    `position_title` and `position_name`, reads the salary/vacancies/FF/OG values
    from the data row, extracts minimum and optional experience from their
    columns, and records `found` statuses in the JSON report for each
    successfully extracted field.
17. Salary-table parsing skips multi-row headings/subheadings, extracts only a
    currency amount from the `Salario` value cell, and reads numeric vacancies
    and FF/OG values from their corresponding data-row columns. Heading-only
    tables must not produce salary, vacancies, or budget values.
18. Experience-table parsing maps “Experiencia Específica” to minimum
    experience and “Experiencia general” to optional experience, including
    tables whose data cells are shifted or concatenated by the PDF layout.
19. Previously processed contest IDs are skipped before PDF requests; after a
    successful PDF extraction, the ID is atomically added to
    `data/processed_contests.json`. Existing historical reports seed the state
    only when that file does not yet exist.

## Opt-in portal smoke test

As of the access review recorded in
[`research.md`](research.md#review-performed-on-2026-10-23), permission for
automated consultation is unconfirmed: the portal's `robots.txt` and checked
candidate terms pages returned HTTP 404, and no explicit authorization or
published crawl guidance was found. Do not start a live run until the portal
operator or an authoritative policy source confirms that this use is
permitted. If confirmed, start a run explicitly:

```bash
python -m job_finder run --confirm-public-access
```

Añade `--headed` para visualizar la ventana de Chromium mientras navega:

```bash
python -m job_finder run --confirm-public-access --headed
```

Sin esta bandera, el navegador se ejecuta de forma headless. Esta opción solo
cambia la visibilidad del navegador; no elimina la confirmación de acceso ni
las restricciones de consulta.

Add `--max-pages 1` to limit the listing traversal to its first page for a
bounded manual run. Details and offered PDFs for contests discovered on that
page are still processed, and the run is partial if more listing pages remain.
The limit must be a positive integer; omitting it traverses until the portal's
explicit end signal.

An online validation is intentionally deferred until the user explicitly
requests it. Offline tests cover direct GET success and rejection paths and do
not contact the portal.

Do not use a live portal during default test runs. The invocation runs the
on-demand traversal; the confirmation flag records that the user reviewed
current portal terms and confirmed access is permitted. Do not start it if
terms or access guidance prohibit the activity. Outputs are stored under
`data/exports/<run_id>/`, with temporary PDFs under
`data/tmp/<run_id>/pdf/`. The CSV and JSON run report must identify
complete/partial status, pages and contests processed, and skipped or failed
targets. The JSON report's `positions` array contains detailed records,
including technical statuses and provenance omitted from the eleven-column
CSV; both outputs contain one row/record per processed position.

## Output references

- The flattened CSV columns and missing-value contract are defined in
  [contracts/output-contract.md](contracts/output-contract.md).
- Entity relationships and lifecycle statuses are defined in
  [data-model.md](data-model.md).
