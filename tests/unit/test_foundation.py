import json

import pytest

from job_finder.config import CrawlerConfig
from job_finder.errors import DetailError, DownloadError, OutputError, PdfProcessingError
from job_finder.records import (
    DocumentStatus,
    Position,
    RunFailure,
    SearchRun,
    SkippedContest,
    TermsDocument,
)
from job_finder.run_report import write_run_report


def test_crawler_config_defaults_match_resilience_requirements() -> None:
    config = CrawlerConfig()

    assert config.navigation_timeout_ms == 20_000
    assert config.result_timeout_ms == 20_000
    assert config.max_retries == 2
    assert config.navigation_interval_seconds >= 3


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"navigation_timeout_ms": 0}, "navigation_timeout_ms"),
        ({"result_timeout_ms": 0}, "result_timeout_ms"),
        ({"max_retries": 3}, "max_retries"),
        ({"navigation_interval_seconds": 2.9}, "navigation_interval_seconds"),
    ],
)
def test_crawler_config_rejects_invalid_resilience_settings(
    override: dict[str, object], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        CrawlerConfig(**override)


def test_search_run_rejects_invalid_counters() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        SearchRun(run_id="run-1", pages_discovered=-1)
    with pytest.raises(ValueError, match="cannot exceed"):
        SearchRun(run_id="run-1", pages_discovered=1, pages_processed=2)


def test_run_report_serializes_run_state_and_failure(tmp_path) -> None:
    run = SearchRun(run_id="run-1", pages_discovered=1, pages_processed=1)
    run.failures.append(
        RunFailure(
            stage="listing",
            target="https://portal.test/?page=2",
            error_type="NavigationError",
            message="timeout",
            retry_count=2,
        )
    )
    run.pending_targets.append("https://portal.test/?page=2")
    run.finalize(listing_complete=False)
    report_path = tmp_path / "run-report.json"

    write_run_report(run, report_path)
    payload = json.loads(report_path.read_text(encoding="utf-8"))

    assert run.status == "partial"
    assert payload["status"] == "partial"
    assert payload["csv_path"] is None
    assert payload["failures"][0]["retry_count"] == 2
    assert payload["pending_targets"] == ["https://portal.test/?page=2"]


def test_run_report_serializes_skipped_contests(tmp_path) -> None:
    run = SearchRun(
        run_id="run-1",
        skipped_contests=[
            SkippedContest(
                contest_key="id:13331",
                title="ENCUADRAMIENTO",
                reason="non_vacancy_encuadramiento",
                listing_page_url="https://portal.test/?page=1",
            )
        ],
    )
    run.finalize(listing_complete=True)

    write_run_report(run, tmp_path / "run-report.json")
    payload = json.loads((tmp_path / "run-report.json").read_text(encoding="utf-8"))

    assert payload["skipped_contests"] == [
        {
            "contest_key": "id:13331",
            "title": "ENCUADRAMIENTO",
            "reason": "non_vacancy_encuadramiento",
            "listing_page_url": "https://portal.test/?page=1",
        }
    ]


def test_run_report_surfaces_filesystem_errors(tmp_path) -> None:
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("block", encoding="utf-8")

    with pytest.raises(OutputError) as error:
        write_run_report(SearchRun(run_id="run-1"), blocker / "run-report.json")

    assert error.value.target == str(blocker / "run-report.json")
    assert error.value.cause is not None


def test_search_run_only_completes_when_no_work_remains() -> None:
    run = SearchRun(run_id="run-1", pages_discovered=1, pages_processed=1)
    run.pending_targets.append("detail:id:123")

    run.finalize(listing_complete=True)

    assert run.status == "partial"


def test_search_run_can_fail_without_processed_listing_pages() -> None:
    run = SearchRun(run_id="run-1")

    run.finalize(listing_complete=False)

    assert run.status == "failed"


def test_run_failure_counts_only_nonnegative_retries() -> None:
    with pytest.raises(ValueError, match="retry_count"):
        RunFailure(
            stage="listing",
            target="https://portal.test/",
            error_type="NavigationError",
            message="failed",
            retry_count=-1,
        )


def test_conclusive_ti_relevance_requires_evidence() -> None:
    with pytest.raises(ValueError, match="ti_relevance_evidence"):
        Position(
            position_key="position-1",
            contest_key="id:123",
            ti_relevance="relevant",
        )


def test_document_validation_matches_processing_state() -> None:
    with pytest.raises(ValueError, match="local_path"):
        TermsDocument(
            document_key="doc-1",
            contest_key="id:123",
            status=DocumentStatus.PROCESSED,
        )
    with pytest.raises(ValueError, match="download metadata"):
        TermsDocument(
            document_key="doc-1",
            contest_key="id:123",
            status=DocumentStatus.NOT_OFFERED,
            local_path="data/tmp/bases.pdf",
        )
    with pytest.raises(ValueError, match="sha256"):
        TermsDocument(
            document_key="doc-1",
            contest_key="id:123",
            status=DocumentStatus.DOWNLOADED,
            local_path="data/tmp/bases.pdf",
            sha256="bad-hash",
        )


@pytest.mark.parametrize("error_type", [DetailError, DownloadError, PdfProcessingError])
def test_domain_errors_retain_target_and_cause(error_type) -> None:
    cause = OSError("underlying failure")
    error = error_type("operation failed", target="target-1", cause=cause)

    assert error.target == "target-1"
    assert error.cause is cause
