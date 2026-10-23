# Tasks: Paraguay Concursa vacancy search and analysis

**Input**: Design documents from `/specs/001-concursa-vacancy-search/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Organization**: Tasks are grouped by user story to support independently
testable increments. Tests are included because the project constitution
requires verification of acceptance criteria and failure cases.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with other tasks in the same phase because it
  edits different files and has no dependency on incomplete work.
- **[Story]**: Identifies the user story served by the task.
- Every task includes its target file path.

## Path Conventions

The project uses one Python `src/` package and tests at repository root, as
defined in [plan.md](plan.md).

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the installable Python package and safe generated-file
boundaries.

- [X] T001 Define Python package metadata, Python 3.11+ support, runtime dependencies (Playwright, pdfplumber, Pandas), pytest test extra, and CLI entry point in `pyproject.toml`.
- [X] T002 [P] Ignore `.venv/`, `data/tmp/`, and `data/exports/` in `.gitignore`.
- [X] T003 [P] Create package initialization and `python -m job_finder` entry-point files in `src/job_finder/__init__.py` and `src/job_finder/__main__.py`.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Define shared run configuration, domain validation, and error
reporting needed by every story.

- [X] T004 Create explicit defaults and validation for the 20-second navigation and result-state timeouts, no more than two retries after the initial attempt, at least three seconds between top-level navigations, and output directories in `src/job_finder/config.py`.
- [X] T005 [P] Implement shared Contest, Position, SearchRun, TermsDocument, and RunFailure records in `src/job_finder/records.py`; preserve official contest ID or canonical detail URL identity, position ID/URL or stable occurrence ordinal identity, and every required/null field, status enum, and validation rule in `data-model.md`.
- [X] T006 [P] Implement explicit typed errors for access restriction, navigation/readiness failure, pagination loop, detail/download/PDF failure, and output I/O failure in `src/job_finder/errors.py`; each error must retain its cause and identify the affected target.
- [X] T007 Create shared run lifecycle and JSON run-report serialization for `running`, `complete`, `partial`, and `failed` states in `src/job_finder/run_report.py`; prohibit `complete` while any discovered page, accessible detail, offered PDF, or export remains unresolved.

**Checkpoint**: Shared configuration, record validation, and failure lifecycle
are ready before user-story implementation.

---

## Phase 3: User Story 1 - Recorrer el listado de concursos (Priority: P1) 🎯 MVP

**Goal**: Run a user-triggered, sequential traversal of the complete public
listing and capture each contest's visible listing fields without false
completion on an unreadable or repeated page.

**Independent Test**: With local HTML fixtures for multiple pages, verify
page 1-to-last order, every unique listing record, correct normal end detection,
and partial status for a timeout or repeated page/cursor.

### Implementation for User Story 1

- [X] T008 [P] [US1] Add local listing fixtures for populated first/next pages, explicit last page, empty results, changed markup, and repeated destination in `tests/fixtures/html/listing/`.
- [X] T009 [P] [US1] Implement listing-page parsing for title, institution, status, visible dates, profile/process/detail links, and official contest identifier in `src/job_finder/extraction.py`.
- [X] T010 [US1] Implement sequential listing navigation in `src/job_finder/crawler.py`; wait for a results or explicit empty-state locator, apply configured timeout/retry/pacing, follow the portal's next link/cursor, and stop without bypassing access restrictions.
- [X] T011 [US1] Detect repeated normalized page destinations and repeated ordered listing fingerprints in `src/job_finder/crawler.py`; report either as an incomplete pagination failure, never as normal last-page completion.
- [X] T012 [US1] Deduplicate contests by official identifier or canonical detail URL and retain page provenance in `src/job_finder/records.py`.
- [X] T013 [US1] Add on-demand CLI command setup for a listing run, run ID creation, and run-report finalization in `src/job_finder/cli.py`.
- [X] T014 [P] [US1] Verify multi-page extraction, end-of-list recognition, empty listings, changed DOM, retry exhaustion, repeated destination, and access-denial stop behavior using the fixtures in `tests/integration/test_listing_crawl.py`.
- [X] T015 [P] [US1] Verify contest identity fallback and unique-record behavior for official IDs and canonical detail URLs in `tests/unit/test_contest_identity.py`.

**Checkpoint**: A user can initiate a listing-only crawl and receive
unambiguously complete or partial results.

---

## Phase 4: User Story 2 - Consultar el detalle y las bases (Priority: P2)

**Goal**: Enrich each discovered contest with position detail and download
offered terms PDFs while continuing to process independent contests after
individual failures.

**Independent Test**: Given local detail fixtures with one and multiple
positions, an absent PDF, a valid PDF, and a failing detail/download, verify
position association, published values, document states, and partial-run
continuation.

### Implementation for User Story 2

- [X] T016 [P] [US2] Add local contest-detail fixtures for one position, multiple positions, missing fields, and offered/not-offered PDF links in `tests/fixtures/html/detail/`.
- [X] T017 [P] [US2] Add native-text, empty, malformed, encrypted, and image-only PDF fixtures in `tests/fixtures/pdf/`.
- [X] T018 [US2] Parse each accessible contest detail into one position record per published position in `src/job_finder/extraction.py`; preserve title, institution, raw remuneration, raw deadline, direct detail URL, and explicit field statuses.
- [X] T019 [US2] Extend contest processing to create positions from listing-card data and associate each clicked profile PDF with the canonical contest identity in `src/job_finder/crawler.py`.
- [X] T020 [US2] Download offered PDFs under `data/tmp/<run_id>/pdf/` and validate successful response, nonempty bytes, readable PDF pages, retrieval timestamp, and SHA-256 in `src/job_finder/documents.py`.
- [X] T021 [US2] Record `not_offered`, `downloaded`, `download_failed`, and processing failure states in `src/job_finder/records.py`; continue processing independent contests after a detail or PDF failure and mark the run partial.
- [X] T022 [P] [US2] Verify detail extraction, multiple-position identity, missing-field statuses, document validation, and PDF state transitions with local fixtures in `tests/unit/test_detail_and_documents.py`.
- [X] T023 [P] [US2] Verify that PDF failures are contextualized, do not stop other contests, preserve listing-derived position rows, and make run status partial in `tests/integration/test_partial_run.py`.

**Checkpoint**: Contest detail and offered PDF outcomes are associated,
traceable, and explicitly successful, absent, or failed.

---

## Phase 5: User Story 3 - Revisar y exportar resultados consolidados (Priority: P3)

**Goal**: Extract key information from readable PDFs, classify IT relevance
and experience accurately, and export stable, traceable results for complete
or partial runs.

**Independent Test**: Use known position/PDF inputs to validate field values,
source evidence and status distinctions, then read the generated CSV back and
compare headers, rows, Unicode, and partial-run metadata.

### Implementation for User Story 3

- [X] T024 [US3] Extract education, knowledge, duties, experience, remuneration, and application-condition text from native PDF pages using pdfplumber in `src/job_finder/documents.py`; record page evidence and mark image-only/no-text or unreadable documents for review/failure without treating them as empty requirements.
- [X] T025 [US3] Classify IT relevance from published education, knowledge, and duties, preserving evidence and using `indeterminate` when evidence is insufficient; distinguish `not_required` experience from `not_stated`, `not_found`, `ambiguous`, and `unreadable` in `src/job_finder/extraction.py`.
- [X] T026 [US3] Consolidate Contest, Position, and TermsDocument data into ordered output records, validate statuses and provenance, and preserve the CSV header for zero rows in `src/job_finder/export.py`.
- [X] T027 [US3] Export UTF-8 CSV without a DataFrame index under `data/exports/<run_id>/` and finalize the matching JSON run report with CSV path, failures, and pending targets using `src/job_finder/export.py` and `src/job_finder/run_report.py`.
- [X] T028 [P] [US3] Verify every CSV column name/order, zero-row header, missing-value semantics, UTF-8 content, quoting, and row-count round trip against `contracts/output-contract.md` in `tests/contract/test_output_contract.py`.
- [X] T029 [P] [US3] Verify PDF field extraction, evidence/page provenance, TI relevance rationale, and experience-status distinctions with local fixtures in `tests/unit/test_pdf_classification.py`.
- [X] T030 [US3] Verify the complete on-demand flow from local listing fixtures through positions/PDF processing to CSV and run report, including exportable partial results, in `tests/integration/test_end_to_end.py`.

**Checkpoint**: Both complete and partial runs produce traceable and
contract-compliant CSV and JSON outputs.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Finalize operational safeguards, documentation, and full offline
validation.

- [X] T031 Review the portal's current terms, `robots.txt`, and published access/rate guidance before enabling live navigation; record the result and block live runs when prohibited in `specs/001-concursa-vacancy-search/research.md`.
- [X] T032 [P] Document CLI usage, configuration, complete/partial status semantics, error output, and generated-file locations in `README.md`.
- [X] T033 [P] Confirm generated PDFs, exports, and `.venv` are excluded from version control and generated output paths match `contracts/output-contract.md` in `.gitignore`.
- [X] T034 Run the offline test suite and every runnable scenario in `specs/001-concursa-vacancy-search/quickstart.md`; record any remaining gap in `specs/001-concursa-vacancy-search/quickstart.md`.
- [X] T035 Add the optional `--max-pages` listing limit to the crawler pipeline and CLI; report unvisited pages as pending, preserve partial-run semantics, and cover the behavior with offline tests and usage documentation in `src/job_finder/crawler.py`, `src/job_finder/pipeline.py`, `src/job_finder/cli.py`, and `tests/`.
- [X] T036 Add the optional `--headed` CLI flag and configuration so Playwright launches visibly when requested while remaining headless by default; verify both launch modes with tests and document the flag in `README.md` and `quickstart.md`.
- [X] T037 Select the profile PDF only from the exact "Ver perfil" link/button, excluding the general process link and other direct PDF links; add offline selector regression coverage in `src/job_finder/extraction.py` and `tests/integration/test_listing_crawl.py`.
- [X] T038 Detect `ENCUADRAMIENTO` and `ENCUADERNAMIENTO` in a listing card's title/type/label before selecting profile URLs; skip detail and PDF processing, serialize an explicit `skipped_contests` report entry, and validate no excluded-card requests occur in `src/job_finder/extraction.py`, `src/job_finder/crawler.py`, `src/job_finder/pipeline.py`, and `tests/`.
- [X] T039 Preserve every processed position in the CSV regardless of TI relevance, cover non-TI records in end-to-end and CSV contract tests, increase the configured result-state timeout to 20 seconds, and document the output behavior in `src/job_finder/config.py`, `tests/`, `README.md`, and `specs/001-concursa-vacancy-search/contracts/output-contract.md`.
- [X] T040 Revisit the matching listing card for each non-excluded contest, click only its exact `Ver perfil` control, wait for the resulting PDF response or navigation, and persist/validate those response bytes without direct URL fetching; cover popup clicks and excluded cards in tests and document the interaction in `src/job_finder/crawler.py`, `src/job_finder/documents.py`, `src/job_finder/extraction.py`, `tests/`, `README.md`, and `specs/001-concursa-vacancy-search/quickstart.md`.
- [X] T041 Preserve the portal contest title separately from the listing position denomination/code; extract salary, vacancies, position type/budget, and minimum/optional experience from all PDF pages; include consolidated position records in CSV and JSON, with unit, contract, and end-to-end coverage in `src/job_finder/records.py`, `src/job_finder/extraction.py`, `src/job_finder/documents.py`, `src/job_finder/export.py`, `src/job_finder/pipeline.py`, and `tests/`.
- [X] T042 Remove the fixed `#detalle-concurso` readiness dependency; recognize position cards without a wrapper ID and handle PDF response bodies, browser downloads, popup/new-tab documents, and viewer pages with a same-origin PDF link after clicking the exact `Ver perfil` control. Cover each path offline and document that live verification is deferred until the user requests it in `src/job_finder/crawler.py`, `src/job_finder/extraction.py`, `tests/`, and `specs/001-concursa-vacancy-search/quickstart.md`.
- [X] T043 Stop navigating to generic `Ver proceso` pages; construct one listing-derived position row per included contest and obtain its PDF only via the exact `Ver perfil` control, retaining the process link as provenance only. Verify no process-page requests and preserve rows when a PDF is absent or fails; update the specification and operations documentation in `src/job_finder/crawler.py`, `tests/`, and `specs/001-concursa-vacancy-search/`.
- [X] T044 Fetch the official same-origin profile PDF with direct HTTP GET and signature validation; extract page-numbered tables across the entire PDF and parse the 13470 denomination, salary, vacancies, and split experience fields. Update offline tests and documents in `src/job_finder/crawler.py`, `src/job_finder/documents.py`, `src/job_finder/extraction.py`, `tests/`, and `specs/001-concursa-vacancy-search/`.
- [X] T045 Map PDF table values by their actual header/column positions, set the extracted denomination as both `position_title` and `position_name`, extract FF/OG and the separate experience columns, and verify the five dedicated exported status fields are `found` and `salary_status` is `published` against the downloaded 13470 PDF layout. Cover table provenance, CSV values, and regression cases in `src/job_finder/documents.py`, `src/job_finder/extraction.py`, `tests/unit/test_pdf_structured_fields.py`, and feature documentation.
- [X] T046 Replace the CSV with the fixed eleven-column public schema while preserving the existing detailed position records in the JSON report; update the output contract, documentation, and contract/end-to-end/PDF regression tests in `src/job_finder/export.py`, `src/job_finder/pipeline.py`, and `tests/`.
- [X] T047 Parse salary exclusively as a currency amount, skip multi-row table subheadings, validate numeric vacancies and FF/OG data cells, and cover explicit/no-salary table cases plus the available 15-page PDF corpus in `src/job_finder/extraction.py`, `tests/unit/test_pdf_structured_fields.py`, and the salary contract.
- [X] T048 Map experience fragments by the “Experiencia Específica” and “Experiencia general” labels when PDF table columns shift or text is concatenated; verify the final CSV fields for contest 12691 and run the requested 15-page live crawl in `src/job_finder/extraction.py`, `tests/unit/test_pdf_structured_fields.py`, and `specs/001-concursa-vacancy-search/quickstart.md`.
- [X] T049 Add persistent processed-contest state initialized from successful historical reports, skip known official IDs before profile requests, and atomically record each new ID only after successful PDF parsing and structured extraction; cover restart, error, legacy seeding, and skip-report behavior in `src/job_finder/processed_state.py`, `src/job_finder/crawler.py`, `src/job_finder/pipeline.py`, and `tests/`.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; establishes package metadata and
  generated-file boundaries.
- **Foundational (Phase 2)**: Depends on Setup; blocks all user stories because
  they share configuration, validated records, and run failure/status handling.
- **User Story 1 (Phase 3)**: Depends on Foundational; delivers the listing-only
  MVP.
- **User Story 2 (Phase 4)**: Depends on US1's contest identity and crawl
  pipeline; extends the same records with detail and documents.
- **User Story 3 (Phase 5)**: Depends on US2's enriched positions and document
  status; consolidates and exports completed or partial results.
- **Polish (Phase 6)**: Depends on all desired stories.

### User Story Dependencies

- **US1 (P1)**: Starts after Phase 2; no dependency on another story.
- **US2 (P2)**: Starts after US1 because it enriches discovered contests using
  the shared canonical contest identity and navigation pipeline.
- **US3 (P3)**: Starts after US2 because it classifies and exports combined
  listing, detail, and PDF data.

### Within Each User Story

- Establish fixtures and independent validation before final integration.
- Listing parsing must precede listing traversal integration.
- Contest/position identity and PDF outcomes must be validated before
  consolidation.
- Consolidation must satisfy the output contract before end-to-end validation.

### Parallel Opportunities

- Setup: T002 and T003 can proceed independently after package metadata paths
  are agreed.
- Foundational: T005 and T006 can proceed in parallel; T007 depends on their
  shared record/error definitions.
- US1: T008 fixtures and T009 listing parser can proceed in parallel after
  Phase 2; T014 and T015 are separate validation files.
- US2: T016 and T017 fixture sets can proceed in parallel; T022 and T023 are
  separate tests after implementation boundaries exist.
- US3: T028 contract tests and T029 classification tests are separate files
  after the output and extraction interfaces are fixed.
- Different user stories are **not** independent in this plan: US2 extends
  US1's crawler/identity, and US3 consumes US2's document-enriched records.

## Parallel Example: User Story 1

```text
Task: T008 Add local listing fixtures in tests/fixtures/html/listing/
Task: T009 Implement listing-page parsing in src/job_finder/extraction.py
```

## Parallel Example: User Story 2

```text
Task: T016 Add contest detail fixtures in tests/fixtures/html/detail/
Task: T017 Add PDF fixtures in tests/fixtures/pdf/
```

## Parallel Example: User Story 3

```text
Task: T028 Add CSV contract checks in tests/contract/test_output_contract.py
Task: T029 Add PDF classification checks in tests/unit/test_pdf_classification.py
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup.
2. Complete Phase 2: Foundational.
3. Complete Phase 3: User Story 1.
4. Validate pagination, extraction, identity, normal termination, and partial
   failure entirely with offline fixtures.
5. Only enable an opt-in live smoke test after the access precondition review.

### Incremental Delivery

1. Deliver the listing-only MVP (US1), with complete/partial run reporting.
2. Add detail enrichment and PDF downloads (US2), preserving independent
   contest processing on failure.
3. Add PDF analysis, classification, and contract-compliant export (US3).
4. Complete cross-cutting access review, documentation, and offline validation.

### Independent Test Criteria

- **US1**: Fixture-backed traversal reaches the valid final page in order,
  records each contest once, detects loops, and reports timeouts/access
  restrictions as incomplete.
- **US2**: Detail fixtures create correctly related position records; PDF
  fixtures produce explicit download/processing states; an individual failure
  does not prevent independent contests from processing.
- **US3**: Local source fields and classification evidence map to the fixed
  CSV schema; zero-row and populated CSV round trips preserve header, values,
  provenance, and partial status.
