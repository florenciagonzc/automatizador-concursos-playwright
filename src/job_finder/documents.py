import hashlib
import re
import time
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping
from urllib.parse import urlsplit

import pdfplumber
from pdfminer.pdfdocument import PDFException
from pdfplumber.utils.exceptions import PdfminerException

from job_finder.errors import AccessRestrictedError, DownloadError, PdfProcessingError
from job_finder.records import Contest, DocumentStatus, TermsDocument

_SECTION_HEADINGS = {
    "descripcion_puesto": re.compile(
        r"^\s*(?:\d+\s*[.)-]?\s*)?descripcion\s+del\s+puesto\b\s*:?\s*(.*)$",
        re.IGNORECASE,
    ),
    "oferta_salarial": re.compile(
        r"^\s*(?:\d+\s*[.)-]?\s*)?oferta\s+salarial\b\s*:?\s*(.*)$",
        re.IGNORECASE,
    ),
    "perfil_requerido": re.compile(
        r"^\s*(?:\d+\s*[.)-]?\s*)?perfil\s+requerido\b\s*:?\s*(.*)$",
        re.IGNORECASE,
    ),
}
_RUN_ID = re.compile(r"^[A-Za-z0-9_-]+$")


def _table_section(rows: list[list[str]]) -> str | None:
    normalized = " ".join(
        re.sub(r"\s+", " ", _normalize_heading(cell)).lower()
        for row in rows
        for cell in row
        if cell
    )
    if (
        "minimos requeridos" in normalized
        and "opcionales" in normalized
        and ("componente" in normalized or "experiencia laboral" in normalized)
    ):
        return "perfil_requerido"
    if (
        "vacancias" in normalized
        and "salario" in normalized
        and ("ff" in normalized or "og" in normalized)
    ):
        return "oferta_salarial"
    if "denominacion del puesto" in normalized or "descripcion corta" in normalized:
        return "descripcion_puesto"
    return None


@dataclass(frozen=True)
class PdfResponse:
    status: int
    url: str
    headers: Mapping[str, str]
    content: bytes


def _normalize_heading(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )


def download_terms_pdf(
    retrieve_response: Callable[[], PdfResponse],
    *,
    run_id: str,
    contest: Contest,
    source_url: str,
    output_root: Path = Path("data/tmp"),
    max_retries: int = 2,
    retry_backoff_seconds: float = 2.0,
    max_retry_backoff_seconds: float = 30.0,
    sleep: Callable[[float], None] = time.sleep,
) -> TermsDocument:
    if not _RUN_ID.fullmatch(run_id):
        raise ValueError(
            "run_id must contain only letters, numbers, underscores, or hyphens"
        )
    if not 0 <= max_retries <= 2:
        raise ValueError(
            "max_retries must be between 0 and 2"
        )
    if retry_backoff_seconds <= 0 or max_retry_backoff_seconds < retry_backoff_seconds:
        raise ValueError("PDF retry backoff configuration is invalid")
    origin = urlsplit(contest.process_url or contest.listing_page_url)
    source = urlsplit(source_url)
    if (
        source.scheme not in {"http", "https"}
        or source.netloc.lower() != origin.netloc.lower()
    ):
        raise DownloadError(
            "PDF URL must use the contest portal origin",
            target=source_url,
        )

    response: PdfResponse | None = None
    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        if attempt:
            sleep(
                min(
                    retry_backoff_seconds * (2 ** (attempt - 1)),
                    max_retry_backoff_seconds,
                )
            )
        try:
            response = retrieve_response()
        except DownloadError as exc:
            last_error = exc
            if attempt == max_retries:
                raise DownloadError(
                    f"PDF HTTP retrieval failed after {max_retries} retries: {exc}",
                    target=source_url,
                    cause=exc,
                    retry_count=max_retries,
                ) from exc
            continue
        status = response.status
        if status in (401, 403):
            raise AccessRestrictedError(
                f"Portal denied PDF access with HTTP {status}",
                target=source_url,
            )
        final_url = urlsplit(response.url)
        if final_url.netloc.lower() != origin.netloc.lower():
            raise AccessRestrictedError(
                "PDF request redirected away from the contest portal origin",
                target=source_url,
            )
        if status == 429 or (isinstance(status, int) and status >= 500):
            last_error = DownloadError(
                f"Temporary portal response HTTP {status}",
                target=source_url,
            )
            if attempt < max_retries:
                continue
            raise DownloadError(
                f"PDF retry budget exhausted: {last_error}",
                target=source_url,
                cause=last_error,
                retry_count=max_retries,
            )
        if not isinstance(status, int) or status < 200 or status >= 300:
            raise DownloadError(
                f"Portal returned HTTP {status} for the PDF",
                target=source_url,
            )
        break

    if response is None:
        raise DownloadError(
            f"PDF retry budget exhausted: {last_error}",
            target=source_url,
            cause=last_error,
            retry_count=max_retries,
        )
    content = response.content
    if not content:
        raise DownloadError("Portal returned an empty PDF response", target=source_url)
    if not content.startswith(b"%PDF-"):
        raise DownloadError(
            "Response does not have a PDF file signature",
            target=source_url,
        )

    document_key = f"{contest.contest_key}:terms"
    filename = hashlib.sha256(
        f"{contest.contest_key}\n{source_url}".encode("utf-8")
    ).hexdigest()[:20] + ".pdf"
    directory = output_root / run_id / "pdf"
    destination = directory / filename
    temporary = destination.with_suffix(".pdf.part")
    try:
        directory.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(content)
        temporary.replace(destination)
    except OSError as exc:
        raise DownloadError(
            f"Unable to persist downloaded PDF: {exc}",
            target=str(destination),
            cause=exc,
        ) from exc

    return TermsDocument(
        document_key=document_key,
        contest_key=contest.contest_key,
        position_key=None,
        source_url=source_url,
        local_path=str(destination),
        retrieved_at=datetime.now(timezone.utc).isoformat(),
        sha256=hashlib.sha256(content).hexdigest(),
        status=DocumentStatus.DOWNLOADED,
    )


def extract_pdf_sections(document: TermsDocument) -> TermsDocument:
    if not document.local_path:
        raise PdfProcessingError(
            "PDF document has no local file path",
            target=document.document_key,
        )

    sections: dict[str, dict[str, object]] = {
        key: {"text": None, "pages": [], "status": "not_found"}
        for key in _SECTION_HEADINGS
    }
    current_section: str | None = None
    page_count = 0
    has_native_text = False
    page_text: list[str] = []
    table_text: list[str] = []
    extracted_tables: list[dict[str, object]] = []
    try:
        with pdfplumber.open(document.local_path) as pdf:
            page_count = len(pdf.pages)
            if page_count == 0:
                raise PdfProcessingError(
                    "PDF contains no readable pages",
                    target=document.local_path,
                )
            for page_number, page in enumerate(pdf.pages, start=1):
                text = page.extract_text()
                tables = page.extract_tables()
                if text:
                    page_text.append(text)
                    has_native_text = True
                    for line in text.splitlines():
                        normalized_line = _normalize_heading(line)
                        heading = next(
                            (
                                (key, pattern.match(normalized_line))
                                for key, pattern in _SECTION_HEADINGS.items()
                                if pattern.match(normalized_line)
                            ),
                            None,
                        )
                        if heading:
                            current_section, match = heading
                            section = sections[current_section]
                            section["status"] = "found"
                            pages = section["pages"]
                            if page_number not in pages:
                                pages.append(page_number)
                            heading_value = (match.group(1) or "").strip()
                            if heading_value:
                                section["text"] = "\n".join(
                                    filter(None, [section["text"], heading_value])
                                )
                            continue
                        if current_section is not None and line.strip():
                            section = sections[current_section]
                            pages = section["pages"]
                            if page_number not in pages:
                                pages.append(page_number)
                            section["text"] = "\n".join(
                                filter(None, [section["text"], line.strip()])
                            )
                for table in tables or []:
                    rows = [
                        [str(cell).strip() if cell is not None else "" for cell in row]
                        for row in table
                    ]
                    rows = [row for row in rows if any(row)]
                    if rows:
                        has_native_text = True
                        table_section = _table_section(rows)
                        extracted_tables.append(
                            {
                                "page": page_number,
                                "section": table_section,
                                "rows": rows,
                            }
                        )
                        table_lines = [
                            " | ".join(cell for cell in row if cell)
                            for row in rows
                        ]
                        table_text.extend(table_lines)
                        section_key = table_section or current_section
                        if section_key is not None:
                            section = sections[section_key]
                            section["status"] = "found"
                            pages = section["pages"]
                            if page_number not in pages:
                                pages.append(page_number)
                            section["text"] = "\n".join(
                                filter(None, [section["text"], *table_lines])
                            )
    except PdfProcessingError:
        raise
    except (PDFException, PdfminerException, OSError, ValueError) as exc:
        raise PdfProcessingError(
            f"Unable to read PDF pages or extract native text: {exc}",
            target=document.local_path,
            cause=exc,
        ) from exc

    if not has_native_text:
        return replace(
            document,
            status=DocumentStatus.REVIEW_REQUIRED,
            extracted_fields={
                "native_text_status": "no_native_text",
                "page_count": page_count,
                "tables": extracted_tables,
            },
        )

    if not any(section["status"] == "found" for section in sections.values()):
        return replace(
            document,
            status=DocumentStatus.REVIEW_REQUIRED,
            extracted_fields={
                "native_text_status": "section_headings_not_found",
                "page_count": page_count,
                "sections": sections,
                "all_text": "\n".join(page_text),
                "table_text": "\n".join(table_text),
                "tables": extracted_tables,
            },
        )

    for section in sections.values():
        if section["text"]:
            section["status"] = "found"
        elif section["status"] == "found":
            section["status"] = "not_stated"
    return replace(
        document,
        status=DocumentStatus.PROCESSED,
        extracted_fields={
            "native_text_status": "available",
            "page_count": page_count,
            "sections": sections,
            "all_text": "\n".join(page_text),
            "table_text": "\n".join(table_text),
            "tables": extracted_tables,
        },
    )
