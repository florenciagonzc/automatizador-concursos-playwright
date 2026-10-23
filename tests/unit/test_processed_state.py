import json
from pathlib import Path

import pytest

from job_finder.errors import OutputError
from job_finder.processed_state import ProcessedContestStore


def test_initial_state_seeds_only_successful_historical_documents(
    tmp_path: Path,
) -> None:
    export_root = tmp_path / "exports"
    report_dir = export_root / "run-1"
    report_dir.mkdir(parents=True)
    (report_dir / "run-report.json").write_text(
        json.dumps(
            {
                "positions": [
                    {"official_id": "123", "document_status": "processed"},
                    {"official_id": "456", "document_status": "download_failed"},
                    {"official_id": None, "document_status": "processed"},
                ]
            }
        ),
        encoding="utf-8",
    )

    store = ProcessedContestStore(
        tmp_path / "processed_contests.json",
        export_root=export_root,
    )

    assert store.contest_ids == {"123"}
    assert json.loads(
        (tmp_path / "processed_contests.json").read_text(encoding="utf-8")
    ) == {"version": 1, "contest_ids": ["123"]}


def test_historical_reports_without_position_details_cannot_seed_state(
    tmp_path: Path,
) -> None:
    export_root = tmp_path / "exports"
    report_dir = export_root / "run-legacy"
    report_dir.mkdir(parents=True)
    (report_dir / "run-report.json").write_text(
        json.dumps({"positions_recorded": 2, "documents": {"processed": 2}}),
        encoding="utf-8",
    )

    store = ProcessedContestStore(
        tmp_path / "processed_contests.json",
        export_root=export_root,
    )

    assert store.contest_ids == frozenset()


def test_mark_processed_persists_id_and_restart_reads_it(tmp_path: Path) -> None:
    state_path = tmp_path / "processed_contests.json"
    store = ProcessedContestStore(state_path, export_root=tmp_path / "exports")

    store.mark_processed(" 123 ")
    restarted_store = ProcessedContestStore(
        state_path,
        export_root=tmp_path / "exports",
    )

    assert restarted_store.contains("123")
    assert restarted_store.contest_ids == {"123"}


def test_invalid_state_is_reported_instead_of_reset(tmp_path: Path) -> None:
    state_path = tmp_path / "processed_contests.json"
    state_path.write_text("{not-json", encoding="utf-8")

    with pytest.raises(OutputError, match="Unable to read processed-contest state"):
        ProcessedContestStore(state_path, export_root=tmp_path / "exports")


def test_malformed_historical_report_is_reported(tmp_path: Path) -> None:
    export_root = tmp_path / "exports"
    report_dir = export_root / "run-1"
    report_dir.mkdir(parents=True)
    (report_dir / "run-report.json").write_text("{not-json", encoding="utf-8")

    with pytest.raises(OutputError, match="Unable to read historical run report"):
        ProcessedContestStore(
            tmp_path / "processed_contests.json",
            export_root=export_root,
        )
