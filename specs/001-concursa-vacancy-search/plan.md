# Implementation Plan: Paraguay Concursa vacancy search and analysis

**Branch**: `001-concursa-vacancy-search` | **Date**: 2026-10-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/001-concursa-vacancy-search/spec.md`

## Summary

Build an on-demand Python command-line batch pipeline that sequentially scans
the public Paraguay Concursa listings, captures contest and position fields
from each listing card, obtains the official PDF URL from the exact "Ver perfil"
control, downloads it with a direct same-origin HTTP GET without opening the
generic "Ver proceso" page, extracts native PDF text and tables, and exports
traceable position-level CSV records. A run
report communicates complete or partial coverage and failures. The crawler
stops at the portal's explicit last-page signal, obeys access controls, and
never treats timeouts or structural changes as successful empty results.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Playwright for Python (synchronous API), pdfplumber,
Pandas; pytest for tests.

**Storage**: Temporary PDFs and run artifacts on local disk; in-memory
DataFrame for consolidation; CSV and JSON files for exported results and run
status; persistent processed-contest ID state in `data/processed_contests.json`.
No database is required for this version.

**Testing**: pytest with local HTML/PDF fixtures and temporary output
directories; browser interactions use a local fixture server or deterministic
request routing. Live-portal checks are opt-in and not part of the default test
suite.

**Target Platform**: macOS and other Python-supported desktop environments.

**Project Type**: Python package with an on-demand command-line entry point.

**Performance Goals**: No elapsed-time SLA. Process listing pages and details
sequentially with at least 3 seconds between top-level navigations, subject to
longer portal crawl-delay guidance or `Retry-After`. A complete run prioritizes
coverage and portal safety over throughput.

**Constraints**: Public pages only; inspect portal terms and crawler guidance
before implementation; do not log in, submit applications, bypass access
controls, or parallelize requests. Use explicit 20-second navigation and
20-second result-state timeouts as initial budgets. Retry only transient
failures, at most twice after the initial attempt, with capped exponential
backoff; stop for access restrictions and persistent rejection. PDF
image-only/no-text documents are marked for review or processing failure; OCR
is out of scope. Analyze native text and tables from every PDF page, including structured
salary/vacancy/budget and minimum/optional experience fields without fixed
page assumptions. Preserve portal
contest title and listed position denomination/code separately. Keep the CSV
as a fixed, compact eleven-column projection while preserving detailed
position records and internal statuses in JSON. Use `.venv`,
declare dependencies, preserve explicit network, timeout, PDF, and file-I/O
errors, and atomically persist successful processed-contest IDs to avoid
re-downloading them on later runs.

**Scale/Scope**: One user-triggered run of the changing public listing, which
may span at least the approximately 103 pages cited in the request. No fixed
page count, parallel runs, scheduler, historical database, or multi-user
service is in scope. Continue processing independent contests after a detail
or PDF failure and mark the overall run partial.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / constraint | Plan alignment | Gate |
|---|---|---|
| I. Specification-driven development | This plan and its design artifacts derive from the approved spec; implementation remains a later phase. | PASS |
| II. Modular, resilient, responsible scraping | Separate navigation and extraction; explicit waits, bounded retries, sequential pacing, last-page detection, loop detection, and stop on restrictions. | PASS |
| III. Verifiable documents and data | Validate PDFs, extract with pdfplumber, validate a fixed record schema, consolidate with Pandas, preserve source references, and report unreadable documents. | PASS |
| IV. Clean code and explicit failures | Use `.venv`, declared dependencies, specific surfaced errors, and no success-shaped fallbacks. | PASS |
| V. Testing and traceability | Use offline fixtures for page/PDF cases, check complete/partial status, and trace rows to source contest/document. | PASS |
| Technical/operational restrictions | Public target only, reasonable crawl pacing, no access circumvention or application submission, generated artifacts kept out of version control. | PASS |

No constitution violations or complexity exceptions are required.

## Project Structure

### Documentation (this feature)

```text
specs/001-concursa-vacancy-search/
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── output-contract.md
└── tasks.md                 # Created in the tasks phase
```

### Source Code (repository root)

```text
pyproject.toml
src/
└── job_finder/
    ├── __init__.py
    ├── __main__.py
    ├── cli.py
    ├── config.py
    ├── crawler.py
    ├── extraction.py
    ├── documents.py
    ├── records.py
    ├── errors.py
    ├── export.py
    └── run_report.py
tests/
├── fixtures/
│   ├── html/
│   └── pdf/
├── unit/
├── integration/
└── contract/
data/
├── tmp/                     # Per-run downloaded PDFs; ignored by version control
└── exports/                 # Per-run CSV and JSON report; ignored by version control
```

**Structure Decision**: Use a single `src`-layout Python package and a thin
CLI because the requested workflow is user-triggered, batch-oriented, and
produces files rather than serving a web application. Keep portal navigation,
DOM extraction, PDF processing, record validation, and export in distinct
modules. Test those boundaries independently. Do not introduce a database,
web UI, scheduler, or multi-project layout.

## Constitution Check (post-design)

The design preserves all gates. The fixed record/export schema supports
traceability and empty outputs; the run report distinguishes a valid completed
run from incomplete work; separate modules keep extraction and persistence
testable. No additional dependencies beyond the constitution-required stack
and pytest are justified. Generated PDFs and exports must remain outside version
control. The pre-implementation access review is a release gate; a prohibition
or access restriction blocks the relevant crawl rather than prompting a bypass.

## Complexity Tracking

No constitution violations. No added architectural complexity requires
justification.
