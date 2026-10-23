import json
from pathlib import Path

from job_finder.errors import OutputError
from job_finder.records import SearchRun


def write_run_report(run: SearchRun, path: Path) -> None:
    run.report_path = str(path)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path.write_text(
            json.dumps(run.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary_path.replace(path)
    except OSError as exc:
        raise OutputError(
            f"Unable to write run report: {exc}", target=str(path), cause=exc
        ) from exc
