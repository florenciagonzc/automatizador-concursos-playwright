# Data Model: Paraguay Concursa vacancy search and analysis

## Modeling decisions

- One consolidated record represents one position. If a contest has multiple
  positions, each position has a separate record tied to the same contest.
- A contest is identified by its official identifier when published; otherwise
  its canonical detail URL is the identity key. Do not deduplicate by title
  alone.
- A contest with no extractable position detail may still produce one record
  with position fields explicitly unavailable.
- Source values are preserved as published. Normalize dates or remuneration
  only when the value can be interpreted unambiguously.
- A missing value is not enough to describe why it is missing. Use field
  statuses for values whose absence, ambiguity, or unreadability affects
  interpretation.

## Entities

### SearchRun

Represents one user-triggered end-to-end crawl.

| Field | Type / allowed values | Required | Validation |
|---|---|---:|---|
| `run_id` | Unique string | Yes | Unique per execution; used to correlate output artifacts. |
| `started_at` | ISO 8601 timestamp | Yes | Set at run start. |
| `finished_at` | ISO 8601 timestamp or null | No | Null only while actively running. |
| `status` | `running`, `complete`, `partial`, `failed` | Yes | `complete` only if all discovered pages, accessible details, and offered PDFs were processed successfully or explicitly unavailable. |
| `pages_discovered` | Non-negative integer | Yes | Count of unique listing pages reached. |
| `pages_processed` | Non-negative integer | Yes | Cannot exceed `pages_discovered`. |
| `contests_discovered` | Non-negative integer | Yes | Unique contests by identity key. |
| `skipped_contests` | List of `SkippedContest` | Yes | Intentionally excluded non-vacancy records; does not include position rows. |
| `positions_recorded` | Non-negative integer | Yes | Number of output rows; JSON includes the consolidated position records. |
| `positions` | Array of detailed row-level records | Yes | One record per CSV row; includes the compact export values plus statuses, provenance, and analysis metadata omitted from the CSV. |
| `processed_contests` | Persistent set of official contest IDs | Yes | Contains only contests whose offered PDF was downloaded and successfully analyzed; failed, absent, or review-required documents are excluded. |
| `failures` | List of `RunFailure` | Yes | Empty when no failures occurred. |
| `output_csv` | Relative path or null | No | Present when a CSV was produced, including valid empty output. |
| `report_path` | Relative path | Yes | Points to the run report. |

### Contest

Represents an item in the public general listing.

| Field | Type / allowed values | Required | Validation |
|---|---|---:|---|
| `contest_key` | String | Yes | Official identifier if available, otherwise canonical detail URL. |
| `official_id` | String or null | No | Preserve identifier formatting, including leading zeroes. |
| `title` | String or null | Yes | Null only when not published/readable; never fabricate a title. |
| `position_name` | String or null | Yes | Position denomination shown on the listing card, when published. |
| `position_code` | String or null | Yes | Position code shown on the listing card, when published. |
| `institution` | String or null | Yes | Preserve source text; null when unavailable. |
| `status` | String or null | Yes | Preserve published status; null when unavailable. |
| `dates_raw` | String or null | Yes | Preserve visible date text; null when unavailable. |
| `profile_url` | Absolute URL or null | No | Must resolve to the portal origin or be reported for review. |
| `process_url` | Absolute URL or null | No | Must resolve to the portal origin or be reported for review. |
| `detail_url` | Canonical absolute URL or null | No | Fallback identity when `official_id` is absent. |
| `skip_reason` | String or null | No | `non_vacancy_encuadramiento` when the card title/type/label contains `encuadramiento` or its known typo; skipped contests must not be detailed or downloaded. |
| `listing_page_url` | Absolute URL | Yes | Page where the contest was discovered. |

### SkippedContest

Represents a listing card intentionally excluded from vacancy processing.

| Field | Type / allowed values | Required | Validation |
|---|---|---:|---|
| `contest_key` | Contest identity key | Yes | Same identity as the corresponding `Contest`. |
| `title` | String or null | Yes | Published listing title; never fabricated. |
| `reason` | String | Yes | Current exclusion reason is `non_vacancy_encuadramiento`. |
| `listing_page_url` | Absolute URL | Yes | Listing page where the excluded card was found. |

### Position

Represents a vacancy tied to a contest. A contest may have zero, one, or many
positions.

| Field | Type / allowed values | Required | Validation |
|---|---|---:|---|
| `position_key` | String | Yes | Official position ID if available, else canonical position detail URL; otherwise contest key plus stable occurrence ordinal. Never deduplicate by title alone. |
| `contest_key` | String | Yes | Foreign-key relationship to `Contest.contest_key`. |
| `title` | String or null | Yes | Position title from the PDF's “Descripción del Puesto” table when available; otherwise preserve the published listing value. |
| `position_name` | String or null | Yes | Position denomination from the PDF's “Descripción del Puesto” table when available, otherwise the listing value; distinct from the contest title. |
| `position_code` | String or null | Yes | Listing position code, preserved as text. |
| `institution` | String or null | Yes | Preserve detail value; do not silently replace with another source value. |
| `salary_raw` | String or null | Yes | Preserve published remuneration text. |
| `salary_status` | `published`, `not_stated`, `not_found`, `ambiguous` | Yes | `published` requires a nonempty `salary_raw`. |
| `salary` | String or null | Yes | Remuneration parsed from PDF section 2 when published; preserve source formatting. |
| `salary_pdf_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | Status of salary extraction from PDF section 2. |
| `vacancies` | String or null | Yes | Number/count text from PDF section 2, preserved as published. |
| `vacancies_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | Status of vacancy-count extraction from PDF section 2. |
| `position_type_budget` | String or null | Yes | Published position type/budget or budgetary classification from section 2; FF and OG values are labeled and preserved together when both are published. |
| `position_type_budget_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | Status of position type/budget extraction from PDF section 2. |
| `min_experience_req` | String or null | Yes | Experience requirements in the PDF subsection “Mínimos Requeridos”. |
| `min_experience_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | Distinguishes absent and unreadable minimum experience evidence. |
| `optional_experience_req` | String or null | Yes | Experience requirements in the PDF subsection “Opcionales”. |
| `optional_experience_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | Distinguishes absent and unreadable optional experience evidence. |
| `deadline_raw` | String or null | Yes | Preserve published date text. |
| `deadline_status` | `published`, `not_stated`, `not_found`, `ambiguous` | Yes | `published` requires a nonempty `deadline_raw`. |
| `detail_url` | Absolute URL or null | No | Direct position/contest detail link where available. |
| `ti_relevance` | `relevant`, `not_relevant`, `indeterminate` | Yes | Based on published education, knowledge, or duties. |
| `ti_relevance_evidence` | String or null | No | Source excerpt or short rationale; required when `relevant` or `not_relevant`. |
| `experience_requirement` | `required`, `not_required`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | Never map missing/unclear evidence to `not_required`. |
| `education_raw` | String or null | Yes | Published education requirement text; null when unavailable. |
| `education_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | `found` requires nonempty `education_raw`. |
| `knowledge_raw` | String or null | Yes | Published knowledge/skills text; null when unavailable. |
| `knowledge_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | `found` requires nonempty `knowledge_raw`. |
| `duties_raw` | String or null | Yes | Published duties text; null when unavailable. |
| `duties_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | `found` requires nonempty `duties_raw`. |
| `application_conditions_raw` | String or null | Yes | Other relevant published application conditions. |
| `application_conditions_status` | `found`, `not_stated`, `not_found`, `ambiguous`, `unreadable` | Yes | `found` requires nonempty `application_conditions_raw`. |

### TermsDocument

Represents an offered bases-and-conditions PDF and its processing lifecycle.

| Field | Type / allowed values | Required | Validation |
|---|---|---:|---|
| `document_key` | String | Yes | Unique per source PDF and associated contest/position. |
| `contest_key` | String | Yes | Foreign-key relationship to contest. |
| `position_key` | String or null | No | Present when the document is position-specific. |
| `source_url` | Absolute URL or null | No | URL offered by the portal. |
| `local_path` | Relative path or null | No | Path under the current run's temporary directory. |
| `retrieved_at` | ISO 8601 timestamp or null | No | Set only after successful download. |
| `sha256` | Hex digest or null | No | Calculated for successful download to support provenance. |
| `status` | `not_offered`, `downloaded`, `download_failed`, `processed`, `processing_failed`, `review_required` | Yes | Transitions follow the lifecycle below. |
| `extracted_fields` | Map of field name to extracted value/status/evidence | Yes | May be empty only when not offered or processing failed, with status explaining why. |

### RunFailure

Represents an error that makes the run partial or failed.

| Field | Type / allowed values | Required | Validation |
|---|---|---:|---|
| `stage` | `access_check`, `listing`, `detail`, `download`, `pdf`, `export` | Yes | Identifies failing operation. |
| `target` | URL, contest key, or file path | Yes | Identifies affected resource. |
| `error_type` | String | Yes | Specific error class/category; preserve original cause in logs. |
| `message` | String | Yes | Actionable, contextual description without secrets. |
| `retry_count` | Non-negative integer | Yes | Counts retries actually attempted. |
| `timestamp` | ISO 8601 timestamp | Yes | Failure occurrence time. |
| `resolution` | `retry_succeeded`, `skipped`, `stopped` | Yes | Failure list includes unresolved issues; retry success may be retained in diagnostics. |

## Lifecycle and run state

- `SearchRun`: `running → complete` only after the listing end is confirmed and
  every discovered accessible detail and offered PDF has an explicit successful
  or not-offered state. Any unresolved page/detail/document/export failure makes
  the run `partial`; a failure before useful collection or output may make it
  `failed`.
- `TermsDocument`: `not_offered` is terminal; otherwise
  `downloaded → processed`, `downloaded → processing_failed`, or
  `download_failed`. A downloaded image-only/no-text PDF becomes
  `review_required` or `processing_failed`, never an empty successful
  extraction.
- `position_key` uses a source-provided position identity where possible. If
  no position ID or unique detail URL exists, use a stable ordinal from the
  position's order in the contest detail and retain that source order.
- A partial run continues with independent contests after a detail or PDF
  failure. Results already obtained remain reviewable and exportable, while
  the run report lists affected and pending targets.
- Excluded contest cards remain counted among discovered listing contests and
  appear in the run report's `skipped_contests` collection. They create no
  position or document records and do not make an otherwise successful run
  partial.

## Consolidated CSV record

The output row is a flattened view of `Contest`, `Position`, and
`TermsDocument`, joined by their keys. The exact ordered columns and status
representations are defined in [contracts/output-contract.md](contracts/output-contract.md).
