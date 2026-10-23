import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from job_finder.config import CrawlerConfig
from job_finder.errors import OutputError
from job_finder.pipeline import execute_search_run
from job_finder.records import RunFailure, SearchRun
from job_finder.run_report import write_run_report


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a positive integer") from exc
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="job-finder",
        description="Recorre el listado público de Paraguay Concursa bajo demanda.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    run_parser = commands.add_parser("run", help="Iniciar un recorrido del listado")
    run_parser.add_argument(
        "--confirm-public-access",
        action="store_true",
        required=True,
        help=(
            "Confirma que revisaste las condiciones vigentes del portal y que "
            "la consulta pública está permitida."
        ),
    )
    run_parser.add_argument(
        "--max-pages",
        type=_positive_int,
        help=(
            "Limita el número de páginas del listado que se recorrerán; "
            "si quedan páginas, el run se reporta como parcial."
        ),
    )
    run_parser.add_argument(
        "--headed",
        action="store_true",
        help="Muestra el navegador durante la ejecución.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command != "run":
        return 2

    config = CrawlerConfig(headed=args.headed)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid4().hex[:8]
    run = SearchRun(run_id=run_id)
    run_directory = config.output_root / run_id
    report_path = run_directory / "run-report.json"
    run.report_path = f"data/exports/{run_id}/run-report.json"

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=not config.headed)
            try:
                context = browser.new_context(user_agent=config.user_agent)
                page = context.new_page()
                run, _ = execute_search_run(
                    page,
                    config,
                    run_id=run_id,
                    max_pages=args.max_pages,
                    tmp_root=Path("data/tmp"),
                )
                context.close()
            finally:
                browser.close()
    except PlaywrightError as exc:
        run.failures.append(
            RunFailure(
                stage="listing",
                target=config.base_url,
                error_type=type(exc).__name__,
                message=f"Unable to start or operate the browser: {exc}",
                retry_count=0,
            )
        )
        run.pending_targets.append("listing traversal")
        run.finalize(listing_complete=False)
        print(f"Browser operation failed: {exc}", file=sys.stderr)
        write_run_report(run, report_path)
    except OutputError as exc:
        print(f"Output operation failed: {exc}", file=sys.stderr)
        return 1

    print(f"Run status: {run.status}")
    print(f"Contests found: {run.contests_discovered}")
    print(f"Contests skipped: {len(run.skipped_contests)}")
    print(f"Processed listing pages: {run.pages_processed}/{run.pages_discovered}")
    print(f"Run report: {report_path}")
    return 0 if run.status == "complete" else 1
