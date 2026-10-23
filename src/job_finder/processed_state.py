import json
import os
from pathlib import Path
from uuid import uuid4

from job_finder.errors import OutputError

_STATE_VERSION = 1


class ProcessedContestStore:
    def __init__(self, path: Path, *, export_root: Path) -> None:
        self.path = path
        try:
            self.path.stat()
        except FileNotFoundError:
            self._contest_ids = self._seed_from_historical_reports(export_root)
            self._write_state()
        except OSError as exc:
            raise OutputError(
                f"Unable to inspect processed-contest state: {exc}",
                target=str(self.path),
                cause=exc,
            ) from exc
        else:
            self._contest_ids = self._read_state()

    @property
    def contest_ids(self) -> frozenset[str]:
        return frozenset(self._contest_ids)

    def contains(self, official_id: str | None) -> bool:
        return bool(official_id and official_id.strip() in self._contest_ids)

    def mark_processed(self, official_id: str) -> None:
        normalized_id = official_id.strip()
        if not normalized_id:
            raise ValueError("official_id must not be empty")
        if normalized_id in self._contest_ids:
            return
        self._contest_ids.add(normalized_id)
        self._write_state()

    def _read_state(self) -> set[str]:
        try:
            content = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OutputError(
                f"Unable to read processed-contest state: {exc}",
                target=str(self.path),
                cause=exc,
            ) from exc
        if (
            not isinstance(content, dict)
            or content.get("version") != _STATE_VERSION
            or not isinstance(content.get("contest_ids"), list)
            or any(
                not isinstance(contest_id, str) or not contest_id.strip()
                for contest_id in content["contest_ids"]
            )
        ):
            raise OutputError(
                "Processed-contest state has an invalid schema",
                target=str(self.path),
            )
        return {contest_id.strip() for contest_id in content["contest_ids"]}

    def _seed_from_historical_reports(self, export_root: Path) -> set[str]:
        contest_ids: set[str] = set()
        try:
            report_paths = sorted(export_root.glob("*/run-report.json"))
        except OSError as exc:
            raise OutputError(
                f"Unable to inspect historical run reports: {exc}",
                target=str(export_root),
                cause=exc,
            ) from exc

        for report_path in report_paths:
            try:
                report = json.loads(report_path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise OutputError(
                    f"Unable to read historical run report: {exc}",
                    target=str(report_path),
                    cause=exc,
                ) from exc
            if not isinstance(report, dict):
                raise OutputError(
                    "Historical run report has an invalid schema",
                    target=str(report_path),
                )
            if "positions" not in report:
                continue
            if not isinstance(report["positions"], list):
                raise OutputError(
                    "Historical run report has an invalid positions collection",
                    target=str(report_path),
                )
            for position in report["positions"]:
                if not isinstance(position, dict):
                    raise OutputError(
                        "Historical run report contains an invalid position record",
                        target=str(report_path),
                    )
                official_id = position.get("official_id")
                if (
                    position.get("document_status") == "processed"
                    and isinstance(official_id, str)
                    and official_id.strip()
                ):
                    contest_ids.add(official_id.strip())
        return contest_ids

    def _write_state(self) -> None:
        temporary_path = self.path.with_name(
            f".{self.path.name}.{uuid4().hex}.tmp"
        )
        payload = {
            "version": _STATE_VERSION,
            "contest_ids": sorted(self._contest_ids),
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with temporary_path.open("w", encoding="utf-8") as state_file:
                json.dump(payload, state_file, ensure_ascii=False, indent=2)
                state_file.write("\n")
                state_file.flush()
                os.fsync(state_file.fileno())
            temporary_path.replace(self.path)
        except OSError as exc:
            cleanup_error: OSError | None = None
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as cleanup_exc:
                cleanup_error = cleanup_exc
            detail = f"Unable to write processed-contest state: {exc}"
            if cleanup_error is not None:
                detail += f"; unable to remove temporary state file: {cleanup_error}"
            raise OutputError(
                detail,
                target=str(self.path),
                cause=exc,
            ) from exc
