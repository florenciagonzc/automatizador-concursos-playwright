import time
from pathlib import Path
from typing import Callable

import pandas as pd
from playwright.sync_api import Page

from job_finder.config import CrawlerConfig
from job_finder.crawler import crawl_listing, process_contests
from job_finder.errors import OutputError
from job_finder.export import build_dataframe, build_position_records, write_csv
from job_finder.processed_state import ProcessedContestStore
from job_finder.records import DocumentStatus, RunFailure, SearchRun
from job_finder.run_report import write_run_report

_DOCUMENT_STATUSES = (
    DocumentStatus.NOT_OFFERED,
    DocumentStatus.DOWNLOADED,
    DocumentStatus.DOWNLOAD_FAILED,
    DocumentStatus.PROCESSED,
    DocumentStatus.PROCESSING_FAILED,
    DocumentStatus.REVIEW_REQUIRED,
)


def execute_search_run(
    page: Page,
    config: CrawlerConfig,
    *,
    run_id: str,
    max_pages: int | None = None,
    tmp_root: Path = Path("data/tmp"),
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[SearchRun, pd.DataFrame]:
    run = SearchRun(run_id=run_id)
    export_directory = config.output_root / run_id
    csv_path = export_directory / "positions.csv"
    report_path = export_directory / "run-report.json"
    run.report_path = f"data/exports/{run_id}/run-report.json"

    processed_state = ProcessedContestStore(
        config.processed_state_path,
        export_root=config.output_root,
    )
    listing = crawl_listing(page, config, max_pages=max_pages, sleep=sleep)
    run.pages_discovered = listing.pages_discovered
    run.pages_processed = listing.pages_processed
    run.contests_discovered = len(listing.contests)
    run.failures.extend(listing.failures)
    run.pending_targets.extend(listing.pending_targets)

    processed = process_contests(
        page,
        listing.contests,
        config,
        run_id=run_id,
        output_root=tmp_root,
        processed_state=processed_state,
        sleep=sleep,
    )
    run.positions_recorded = len(processed.positions)
    run.skipped_contests.extend(processed.skipped_contests)
    run.documents = {
        status.value: sum(document.status == status for document in processed.documents)
        for status in _DOCUMENT_STATUSES
    }
    run.failures.extend(processed.failures)
    run.pending_targets.extend(processed.pending_targets)

    planned_status = (
        "complete"
        if listing.listing_complete and not run.failures and not run.pending_targets
        else "partial"
        if run.pages_processed or run.contests_discovered
        else "failed"
    )
    report_status = planned_status
    frame = build_dataframe(
        run_id,
        listing.contests,
        processed.positions,
        processed.documents,
        run_status=planned_status,
    )
    try:
        write_csv(frame, csv_path)
    except OutputError as exc:
        run.failures.append(
            RunFailure(
                stage="export",
                target=exc.target,
                error_type=type(exc).__name__,
                message=str(exc),
                retry_count=exc.retry_count,
            )
        )
        run.pending_targets.append(f"export:{exc.target}")
        report_status = (
            "partial"
            if run.pages_processed or run.contests_discovered
            else "failed"
        )
        frame = build_dataframe(
            run_id,
            listing.contests,
            processed.positions,
            processed.documents,
            run_status=report_status,
        )
    else:
        run.output_csv = f"data/exports/{run_id}/positions.csv"

    run.positions = build_position_records(
        run_id,
        listing.contests,
        processed.positions,
        processed.documents,
        run_status=report_status,
    )
    run.positions_recorded = len(run.positions)
    run.finalize(listing_complete=listing.listing_complete)
    write_run_report(run, report_path)
    return run, frame
