import csv
from pathlib import Path

import pandas as pd

from job_finder.errors import OutputError
from job_finder.records import Contest, Position, TermsDocument

CSV_COLUMNS = [
    "contest_id",
    "institution",
    "position_title",
    "salary",
    "vacancies",
    "budget_type",
    "min_experience",
    "optional_experience",
    "contest_dates",
    "pdf_url",
    "contest_url",
]

REPORT_POSITION_COLUMNS = [
    "run_id",
    "contest_key",
    "official_id",
    "web_contest_title",
    "institution",
    "contest_status",
    "contest_dates_raw",
    "profile_url",
    "process_url",
    "contest_detail_url",
    "listing_page_url",
    "position_key",
    "position_title",
    "position_name",
    "position_code",
    "salary_raw",
    "salary_status",
    "salary",
    "salary_pdf_status",
    "vacancies",
    "vacancies_status",
    "position_type_budget",
    "position_type_budget_status",
    "min_experience_req",
    "min_experience_status",
    "optional_experience_req",
    "optional_experience_status",
    "deadline_raw",
    "deadline_status",
    "position_detail_url",
    "ti_relevance",
    "ti_relevance_evidence",
    "experience_requirement",
    "education_raw",
    "education_status",
    "knowledge_raw",
    "knowledge_status",
    "duties_raw",
    "duties_status",
    "application_conditions_raw",
    "application_conditions_status",
    "document_status",
    "document_url",
    "document_path",
    "document_sha256",
    "document_retrieved_at",
    "run_status",
]


def _document_path(document: TermsDocument) -> str | None:
    if not document.local_path:
        return None
    path = Path(document.local_path)
    parts = path.parts
    if "tmp" in parts:
        index = parts.index("tmp")
        return Path("data", *parts[index:]).as_posix()
    return path.as_posix()


def build_position_records(
    run_id: str,
    contests: list[Contest],
    positions: list[Position],
    documents: list[TermsDocument],
    *,
    run_status: str,
) -> list[dict[str, object]]:
    if run_status not in {"complete", "partial", "failed"}:
        raise ValueError(f"unsupported run status for position records: {run_status}")
    contests_by_key = {contest.contest_key: contest for contest in contests}
    documents_by_contest: dict[str, TermsDocument] = {}
    documents_by_position: dict[tuple[str, str], TermsDocument] = {}
    for document in documents:
        if document.contest_key not in contests_by_key:
            raise ValueError(
                f"document {document.document_key} references an unknown contest"
            )
        if document.position_key:
            documents_by_position[
                (document.contest_key, document.position_key)
            ] = document
        else:
            documents_by_contest.setdefault(document.contest_key, document)

    rows: list[dict[str, object]] = []
    for position in positions:
        contest = contests_by_key.get(position.contest_key)
        if contest is None:
            raise ValueError(
                f"position {position.position_key} references an unknown contest"
            )
        document = documents_by_position.get(
            (position.contest_key, position.position_key)
        ) or documents_by_contest.get(position.contest_key)
        row: dict[str, object] = {
            "run_id": run_id,
            "contest_key": contest.contest_key,
            "official_id": contest.official_id,
            "web_contest_title": contest.title,
            "institution": position.institution or contest.institution,
            "contest_status": contest.status,
            "contest_dates_raw": contest.dates_raw,
            "profile_url": contest.profile_url,
            "process_url": contest.process_url,
            "contest_detail_url": contest.detail_url,
            "listing_page_url": contest.listing_page_url,
            "position_key": position.position_key,
            "position_title": position.title,
            "position_name": position.position_name or contest.position_name,
            "position_code": position.position_code or contest.position_code,
            "salary_raw": position.salary_raw,
            "salary_status": position.salary_status.value,
            "salary": position.salary,
            "salary_pdf_status": position.salary_pdf_status.value,
            "vacancies": position.vacancies,
            "vacancies_status": position.vacancies_status.value,
            "position_type_budget": position.position_type_budget,
            "position_type_budget_status": (
                position.position_type_budget_status.value
            ),
            "min_experience_req": position.min_experience_req,
            "min_experience_status": position.min_experience_status.value,
            "optional_experience_req": position.optional_experience_req,
            "optional_experience_status": position.optional_experience_status.value,
            "deadline_raw": position.deadline_raw,
            "deadline_status": position.deadline_status.value,
            "position_detail_url": position.detail_url,
            "ti_relevance": position.ti_relevance,
            "ti_relevance_evidence": position.ti_relevance_evidence,
            "experience_requirement": position.experience_requirement,
            "education_raw": position.education_raw,
            "education_status": position.education_status.value,
            "knowledge_raw": position.knowledge_raw,
            "knowledge_status": position.knowledge_status.value,
            "duties_raw": position.duties_raw,
            "duties_status": position.duties_status.value,
            "application_conditions_raw": position.application_conditions_raw,
            "application_conditions_status": (
                position.application_conditions_status.value
            ),
            "document_status": document.status.value if document else None,
            "document_url": document.source_url if document else None,
            "document_path": _document_path(document) if document else None,
            "document_sha256": document.sha256 if document else None,
            "document_retrieved_at": document.retrieved_at if document else None,
            "run_status": "partial" if run_status == "failed" else run_status,
        }
        rows.append(row)

    if any(list(row) != REPORT_POSITION_COLUMNS for row in rows):
        raise ValueError("position records do not match the report schema")
    return rows


def build_dataframe(
    run_id: str,
    contests: list[Contest],
    positions: list[Position],
    documents: list[TermsDocument],
    *,
    run_status: str,
) -> pd.DataFrame:
    report_rows = build_position_records(
        run_id,
        contests,
        positions,
        documents,
        run_status=run_status,
    )
    rows: list[dict[str, object]] = []
    for report_row in report_rows:
        rows.append(
            {
                "contest_id": report_row["official_id"] or report_row["contest_key"],
                "institution": report_row["institution"],
                "position_title": (
                    report_row["position_title"]
                    or report_row["position_name"]
                    or report_row["web_contest_title"]
                ),
                "salary": report_row["salary"] or report_row["salary_raw"],
                "vacancies": report_row["vacancies"],
                "budget_type": report_row["position_type_budget"],
                "min_experience": report_row["min_experience_req"],
                "optional_experience": report_row["optional_experience_req"],
                "contest_dates": report_row["contest_dates_raw"],
                "pdf_url": report_row["document_url"] or report_row["profile_url"],
                "contest_url": (
                    report_row["contest_detail_url"] or report_row["process_url"]
                ),
            }
        )

    frame = pd.DataFrame.from_records(rows, columns=CSV_COLUMNS)
    if list(frame.columns) != CSV_COLUMNS:
        raise ValueError("DataFrame columns do not match the CSV contract")
    return frame


def write_csv(frame: pd.DataFrame, path: Path) -> Path:
    if list(frame.columns) != CSV_COLUMNS:
        raise ValueError("DataFrame columns do not match the CSV contract")
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(
            temporary_path,
            index=False,
            encoding="utf-8",
            quoting=csv.QUOTE_MINIMAL,
            lineterminator="\n",
        )
        temporary_path.replace(path)
    except OSError as exc:
        raise OutputError(
            f"Unable to write vacancy CSV: {exc}",
            target=str(path),
            cause=exc,
        ) from exc
    return path
