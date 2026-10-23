# Output Contract: CSV records and run report

## Vacancy CSV

The export is a UTF-8 CSV with one row per position, exactly eleven fixed
ordered columns, quoted fields as required, and no implicit DataFrame index. A
run with no rows still writes the header. Internal processing statuses,
provenance hashes/paths, raw duplicate values, and TI classification details
belong in the JSON report, not in this compact CSV.

Every processed position is exported regardless of `ti_relevance`; the
classification is descriptive metadata, not an inclusion filter. Only listing
records explicitly skipped as non-vacancy encuadramiento items are excluded
from position rows.

### Ordered columns

| # | Column | Meaning |
|---:|---|---|
| 1 | `contest_id` | Official contest identifier, or the canonical contest key when no official identifier is published. |
| 2 | `institution` | Institution associated with the position. |
| 3 | `position_title` | Position title from the PDF when available, otherwise the listed position denomination or contest title. |
| 4 | `salary` | Published monetary amount only, preserving the currency symbol and amount formatting; blank when no monetary amount is published. |
| 5 | `vacancies` | Published vacancies/count, preserving source formatting. |
| 6 | `budget_type` | Position/budget classification; when published in columns FF and OG, serialize as `FF: <value>; OG: <value>`. |
| 7 | `min_experience` | Text in the “Mínimos Requeridos” experience subsection. |
| 8 | `optional_experience` | Text in the “Opcionales” experience subsection. |
| 9 | `contest_dates` | Date text shown in the listing. |
| 10 | `pdf_url` | PDF source URL from the exact “Ver perfil” control, when available. |
| 11 | `contest_url` | Contest detail URL, falling back to its process URL when no detail URL is available. |

## CSV value rules

- Encode as UTF-8. Use `"` quoting and escape embedded quotes by doubling them,
  consistent with common CSV readers.
- Preserve identifiers as strings, including leading zeroes, and preserve dates,
  salary, and extracted text as published. Do not imply a normalized
  date/amount unless a later approved contract adds a normalized field.
- The `salary` value must be an actual currency amount, not a salary-table
  heading, a column label, or explanatory text such as a reference to a
  separate planilla. Leave it empty when no monetary amount is present.
- Use an empty cell when a value is absent. Detailed status and evidence for
  missing, ambiguous, or unreadable values remain available in the JSON report;
  an empty cell is not a positive assertion that a requirement does not exist.
- Do not serialize the Pandas index.
- Keep exactly the fixed eleven-column order above even when the result has
  zero rows.
- The JSON report includes one detailed position record for each CSV row. It
  retains the processing statuses, provenance, and analysis fields omitted
  from the compact CSV. `positions_recorded` equals both the CSV row count and
  the JSON array length.

## Run report JSON

The JSON report is written beside the CSV (and still written when no CSV rows
exist). It MUST contain:

| Field | Type | Requirement |
|---|---|---|
| `run_id` | String | Identifies the run and its output directory. |
| `started_at` | ISO 8601 string | Required. |
| `finished_at` | ISO 8601 string | Required after process completion. |
| `status` | `complete`, `partial`, `failed` | Required. |
| `pages_discovered` | Integer | Count of unique listing pages reached. |
| `pages_processed` | Integer | Number successfully interpreted. |
| `contests_discovered` | Integer | Unique contests under the identity rule. |
| `positions_recorded` | Integer | Must equal CSV data-row count. |
| `positions` | Array of objects | One detailed record per consolidated CSV row, including internal statuses, provenance, and analysis fields. |
| `documents` | Object | Counts by document status. |
| `skipped_contests` | Array | Contest identity, title, exclusion reason, and listing page for cards intentionally omitted from detail/PDF processing. |
| `failures` | Array | Specific stage, target, error type, message, retry count, timestamp, and resolution. |
| `pending_targets` | Array of strings | Targets not processed because the run ended early. |
| `csv_path` | String or null | Relative export path when produced. |

`status` is `complete` only after the listing end is confirmed and no discovered
page, accessible detail, or offered PDF remains unprocessed. A missing optional
PDF is `not_offered`, not a failure. If an individual target fails, processing
continues for independent contests, but the run is `partial`; pending and
failed targets remain visible. A preflight access restriction stops the run
and is reported without attempting a bypass.

Cards classified as non-vacancy encuadramiento records are listed in
`skipped_contests`; they do not create position rows or document entries and do
not count as processing failures.

Contest IDs already present in the persistent processed-contest state are also
listed in `skipped_contests` with reason `already_processed`; they are skipped
before any profile download and do not create position rows or document
entries. Only successfully downloaded and analyzed PDFs are added to the state.
On first use, historical run reports with `document_status: processed` seed
the state file.

## Command and artifact paths

The planned on-demand entry point is:

```text
python -m job_finder run
```

Each invocation creates a unique run directory. Downloaded PDFs are kept
temporarily under `data/tmp/<run_id>/pdf/`; the CSV and `run-report.json` are
written under `data/exports/<run_id>/`. These generated directories must be
excluded from version control. A live invocation must not run automatically
from tests or imports.
