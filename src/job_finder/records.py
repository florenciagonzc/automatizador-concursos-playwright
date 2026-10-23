import re
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

RunStatus = Literal["running", "complete", "partial", "failed"]


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url)
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") + "/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, "", ""))


def build_position_key(
    *,
    contest_key: str,
    official_id: str | None = None,
    detail_url: str | None = None,
    occurrence_ordinal: int | None = None,
) -> str:
    if official_id and official_id.strip():
        return f"id:{official_id.strip()}"
    if detail_url:
        return canonicalize_url(detail_url)
    if occurrence_ordinal is None or occurrence_ordinal < 1:
        raise ValueError(
            "position identity requires an official ID, detail URL, or positive ordinal"
        )
    if not contest_key.strip():
        raise ValueError("contest_key is required for ordinal position identity")
    return f"{contest_key}:position:{occurrence_ordinal}"


@dataclass(frozen=True)
class Contest:
    official_id: str | None
    title: str | None
    institution: str | None
    status: str | None
    dates_raw: str | None
    profile_url: str | None
    process_url: str | None
    detail_url: str | None
    listing_page_url: str
    skip_reason: str | None = None
    position_name: str | None = None
    position_code: str | None = None

    @property
    def contest_key(self) -> str:
        if self.official_id and self.official_id.strip():
            return f"id:{self.official_id.strip()}"
        if self.detail_url:
            return canonicalize_url(self.detail_url)
        raise ValueError("Contest requires official_id or canonical detail_url")


@dataclass(frozen=True)
class SkippedContest:
    contest_key: str
    title: str | None
    reason: str
    listing_page_url: str


class FieldStatus(StrEnum):
    FOUND = "found"
    NOT_STATED = "not_stated"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"
    UNREADABLE = "unreadable"


class PublishedFieldStatus(StrEnum):
    PUBLISHED = "published"
    NOT_STATED = "not_stated"
    NOT_FOUND = "not_found"
    AMBIGUOUS = "ambiguous"


class DocumentStatus(StrEnum):
    NOT_OFFERED = "not_offered"
    DOWNLOADED = "downloaded"
    DOWNLOAD_FAILED = "download_failed"
    PROCESSED = "processed"
    PROCESSING_FAILED = "processing_failed"
    REVIEW_REQUIRED = "review_required"


@dataclass(frozen=True)
class Position:
    position_key: str
    contest_key: str
    title: str | None = None
    position_name: str | None = None
    position_code: str | None = None
    institution: str | None = None
    salary_raw: str | None = None
    salary_status: PublishedFieldStatus = PublishedFieldStatus.NOT_FOUND
    salary: str | None = None
    salary_pdf_status: FieldStatus = FieldStatus.NOT_FOUND
    vacancies: str | None = None
    vacancies_status: FieldStatus = FieldStatus.NOT_FOUND
    position_type_budget: str | None = None
    position_type_budget_status: FieldStatus = FieldStatus.NOT_FOUND
    min_experience_req: str | None = None
    min_experience_status: FieldStatus = FieldStatus.NOT_FOUND
    optional_experience_req: str | None = None
    optional_experience_status: FieldStatus = FieldStatus.NOT_FOUND
    deadline_raw: str | None = None
    deadline_status: PublishedFieldStatus = PublishedFieldStatus.NOT_FOUND
    detail_url: str | None = None
    ti_relevance: Literal["relevant", "not_relevant", "indeterminate"] = (
        "indeterminate"
    )
    ti_relevance_evidence: str | None = None
    experience_requirement: Literal[
        "required", "not_required", "not_stated", "not_found", "ambiguous", "unreadable"
    ] = "not_found"
    education_raw: str | None = None
    education_status: FieldStatus = FieldStatus.NOT_FOUND
    knowledge_raw: str | None = None
    knowledge_status: FieldStatus = FieldStatus.NOT_FOUND
    duties_raw: str | None = None
    duties_status: FieldStatus = FieldStatus.NOT_FOUND
    application_conditions_raw: str | None = None
    application_conditions_status: FieldStatus = FieldStatus.NOT_FOUND

    def __post_init__(self) -> None:
        if not self.position_key.strip():
            raise ValueError("position_key must not be empty")
        if not self.contest_key.strip():
            raise ValueError("contest_key must not be empty")
        if self.ti_relevance not in {"relevant", "not_relevant", "indeterminate"}:
            raise ValueError(f"unsupported ti_relevance: {self.ti_relevance}")
        if self.experience_requirement not in {
            "required",
            "not_required",
            "not_stated",
            "not_found",
            "ambiguous",
            "unreadable",
        }:
            raise ValueError(
                f"unsupported experience_requirement: {self.experience_requirement}"
            )
        for name in ("salary_status", "deadline_status"):
            try:
                value = PublishedFieldStatus(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"unsupported {name}: {getattr(self, name)}") from exc
            object.__setattr__(self, name, value)
        for name in (
            "education_status",
            "knowledge_status",
            "duties_status",
            "application_conditions_status",
            "min_experience_status",
            "optional_experience_status",
            "salary_pdf_status",
            "vacancies_status",
            "position_type_budget_status",
        ):
            try:
                value = FieldStatus(getattr(self, name))
            except (TypeError, ValueError) as exc:
                raise ValueError(f"unsupported {name}: {getattr(self, name)}") from exc
            object.__setattr__(self, name, value)
        for name, value, status in (
            ("salary_raw", self.salary_raw, self.salary_status),
            ("deadline_raw", self.deadline_raw, self.deadline_status),
            ("education_raw", self.education_raw, self.education_status),
            ("knowledge_raw", self.knowledge_raw, self.knowledge_status),
            ("duties_raw", self.duties_raw, self.duties_status),
            ("salary", self.salary, self.salary_pdf_status),
            ("vacancies", self.vacancies, self.vacancies_status),
            (
                "position_type_budget",
                self.position_type_budget,
                self.position_type_budget_status,
            ),
            (
                "min_experience_req",
                self.min_experience_req,
                self.min_experience_status,
            ),
            (
                "optional_experience_req",
                self.optional_experience_req,
                self.optional_experience_status,
            ),
            (
                "application_conditions_raw",
                self.application_conditions_raw,
                self.application_conditions_status,
            ),
        ):
            if status in {
                FieldStatus.FOUND,
                PublishedFieldStatus.PUBLISHED,
            } and not value:
                raise ValueError(f"{name} is required when status is {status.value}")
        if (
            self.ti_relevance in {"relevant", "not_relevant"}
            and not self.ti_relevance_evidence
        ):
            raise ValueError(
                "ti_relevance_evidence is required for a conclusive TI relevance"
            )


@dataclass(frozen=True)
class TermsDocument:
    document_key: str
    contest_key: str
    status: DocumentStatus
    position_key: str | None = None
    source_url: str | None = None
    local_path: str | None = None
    retrieved_at: str | None = None
    sha256: str | None = None
    extracted_fields: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.document_key.strip() or not self.contest_key.strip():
            raise ValueError("document_key and contest_key must not be empty")
        try:
            status = DocumentStatus(self.status)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"unsupported document status: {self.status}") from exc
        object.__setattr__(self, "status", status)
        if self.status == DocumentStatus.NOT_OFFERED:
            if self.local_path or self.retrieved_at or self.sha256:
                raise ValueError("a not_offered document cannot have download metadata")
            if self.extracted_fields:
                raise ValueError("a not_offered document cannot have extracted fields")
        if self.status in {
            DocumentStatus.DOWNLOADED,
            DocumentStatus.PROCESSED,
            DocumentStatus.PROCESSING_FAILED,
            DocumentStatus.REVIEW_REQUIRED,
        } and not self.local_path:
            raise ValueError(f"{self.status.value} requires a local_path")
        if self.sha256 and not re.fullmatch(r"[0-9a-fA-F]{64}", self.sha256):
            raise ValueError("sha256 must be a 64-character hexadecimal digest")
        if self.status in {DocumentStatus.PROCESSED, DocumentStatus.REVIEW_REQUIRED}:
            if not self.extracted_fields:
                raise ValueError(
                    f"{self.status.value} requires extracted_fields or evidence"
                )


@dataclass
class RunFailure:
    stage: Literal["access_check", "listing", "detail", "download", "pdf", "export"]
    target: str
    error_type: str
    message: str
    retry_count: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    resolution: Literal["retry_succeeded", "skipped", "stopped"] = "stopped"

    def __post_init__(self) -> None:
        if self.stage not in {
            "access_check",
            "listing",
            "detail",
            "download",
            "pdf",
            "export",
        }:
            raise ValueError(f"unsupported failure stage: {self.stage}")
        if self.retry_count < 0:
            raise ValueError("retry_count must not be negative")
        if self.resolution not in {"retry_succeeded", "skipped", "stopped"}:
            raise ValueError(f"unsupported failure resolution: {self.resolution}")


@dataclass
class SearchRun:
    run_id: str
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    finished_at: str | None = None
    status: RunStatus = "running"
    pages_discovered: int = 0
    pages_processed: int = 0
    listing_complete: bool = False
    contests_discovered: int = 0
    skipped_contests: list[SkippedContest] = field(default_factory=list)
    positions_recorded: int = 0
    positions: list[dict[str, Any]] = field(default_factory=list)
    documents: dict[str, int] = field(default_factory=dict)
    failures: list[RunFailure] = field(default_factory=list)
    pending_targets: list[str] = field(default_factory=list)
    output_csv: str | None = None
    report_path: str | None = None

    def __post_init__(self) -> None:
        if not self.run_id.strip():
            raise ValueError("run_id must not be empty")
        if min(
            self.pages_discovered,
            self.pages_processed,
            self.contests_discovered,
            self.positions_recorded,
        ) < 0:
            raise ValueError("run counters must not be negative")
        if self.pages_processed > self.pages_discovered:
            raise ValueError("pages_processed cannot exceed pages_discovered")
        if self.status not in {"running", "complete", "partial", "failed"}:
            raise ValueError(f"unsupported run status: {self.status}")
        if self.status != "running" and self.finished_at is None:
            raise ValueError("finished_at is required once a run is no longer running")
        if self.status == "running" and self.finished_at is not None:
            raise ValueError("a running run cannot have finished_at")

    def finalize(self, *, listing_complete: bool) -> None:
        self.listing_complete = listing_complete
        self.finished_at = datetime.now(timezone.utc).isoformat()
        unresolved_failures = [
            failure
            for failure in self.failures
            if failure.resolution != "retry_succeeded"
        ]
        if listing_complete and not unresolved_failures and not self.pending_targets:
            self.status = "complete"
        elif self.pages_processed or self.contests_discovered:
            self.status = "partial"
        else:
            self.status = "failed"

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["csv_path"] = payload.pop("output_csv")
        return payload


def deduplicate_contests(contests: list[Contest]) -> list[Contest]:
    unique: dict[str, Contest] = {}
    for contest in contests:
        unique.setdefault(contest.contest_key, contest)
    return list(unique.values())
