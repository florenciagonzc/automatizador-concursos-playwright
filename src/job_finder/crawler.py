import hashlib
import re
import time
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Callable
from urllib.parse import parse_qs, urlencode, urljoin, urlsplit, urlunsplit

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import (
    Page,
    TimeoutError as PlaywrightTimeoutError,
)

from job_finder.config import CrawlerConfig
from job_finder.errors import (
    AccessRestrictedError,
    DownloadError,
    JobFinderError,
    NavigationError,
    PageStructureError,
    PaginationLoopError,
    PdfProcessingError,
)
from job_finder.documents import (
    PdfResponse,
    download_terms_pdf,
    extract_pdf_sections,
)
from job_finder.extraction import (
    enrich_position_from_document,
    extract_contests,
    next_page_url,
)
from job_finder.processed_state import ProcessedContestStore
from job_finder.records import (
    Contest,
    DocumentStatus,
    Position,
    RunFailure,
    SkippedContest,
    TermsDocument,
    build_position_key,
    deduplicate_contests,
)

_OFFICIAL_ID = re.compile(r"\bID\s+([A-Za-z0-9_-]+)\b", re.IGNORECASE)
_EXCLUDED_PROFILE_CARD = re.compile(
    r"\b(?:encuadramiento|encuadernamiento)\b",
    re.IGNORECASE,
)


@dataclass
class CrawlResult:
    contests: list[Contest] = field(default_factory=list)
    pages_discovered: int = 0
    pages_processed: int = 0
    listing_complete: bool = False
    failures: list[RunFailure] = field(default_factory=list)
    pending_targets: list[str] = field(default_factory=list)


@dataclass
class ContestProcessingResult:
    positions: list[Position] = field(default_factory=list)
    documents: list[TermsDocument] = field(default_factory=list)
    failures: list[RunFailure] = field(default_factory=list)
    pending_targets: list[str] = field(default_factory=list)
    skipped_contests: list[SkippedContest] = field(default_factory=list)


def page_url(base_url: str, page_number: int) -> str:
    parts = urlsplit(base_url)
    query = parse_qs(parts.query, keep_blank_values=True)
    query["page"] = [str(page_number)]
    query["modo"] = ["lista"]
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path or "/", urlencode(query, doseq=True), "")
    )


def _page_number(url: str) -> int | None:
    values = parse_qs(urlsplit(url).query).get("page")
    if not values:
        return None
    try:
        return int(values[0])
    except ValueError:
        return None


def _normalized_destination(url: str) -> str:
    parts = urlsplit(url)
    query = urlencode(sorted(parse_qs(parts.query, keep_blank_values=True).items()), doseq=True)
    return urlunsplit(
        (parts.scheme.lower(), parts.netloc.lower(), parts.path or "/", query, "")
    )


def _retry_after_seconds(response: object | None) -> float | None:
    if response is None:
        return None
    headers = getattr(response, "headers", {})
    raw_value = headers.get("retry-after")
    if not raw_value:
        return None
    try:
        return max(0.0, float(raw_value))
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(raw_value)
        except (TypeError, ValueError):
            return None
        if retry_at.tzinfo is None:
            retry_at = retry_at.replace(tzinfo=timezone.utc)
        return max(0.0, (retry_at - datetime.now(timezone.utc)).total_seconds())


def _navigate(
    page: Page,
    url: str,
    config: CrawlerConfig,
    sleep: Callable[[float], None],
) -> int:
    last_error: Exception | None = None
    for attempt in range(config.max_retries + 1):
        try:
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=config.navigation_timeout_ms,
            )
            status = response.status if response else None
            if urlsplit(page.url).netloc.lower() != urlsplit(url).netloc.lower():
                raise AccessRestrictedError(
                    "Portal redirected navigation away from its origin",
                    target=page.url,
                )
            if status in (401, 403):
                raise AccessRestrictedError(
                    f"Portal denied access with HTTP {status}",
                    target=url,
                )
            if status == 429 or (status is not None and status >= 500):
                last_error = NavigationError(
                    f"Temporary portal response HTTP {status}",
                    target=url,
                )
                if attempt < config.max_retries:
                    retry_after = _retry_after_seconds(response)
                    delay = retry_after if retry_after is not None else min(
                        config.retry_backoff_seconds * (2**attempt),
                        config.max_retry_backoff_seconds,
                    )
                    sleep(delay)  # type: ignore[operator]
                    continue
                break
            if status is not None and status >= 400:
                raise NavigationError(
                    f"Portal returned HTTP {status}",
                    target=url,
                )
            try:
                page.locator("#contenido-concursos").wait_for(
                    state="attached",
                    timeout=config.result_timeout_ms,
                )
            except PlaywrightTimeoutError as exc:
                last_error = NavigationError(
                    f"Timed out waiting for the listing container: {exc}",
                    target=url,
                    cause=exc,
                )
                if attempt < config.max_retries:
                    sleep(
                        min(
                            config.retry_backoff_seconds * (2**attempt),
                            config.max_retry_backoff_seconds,
                        )
                    )
                    continue
                break
            try:
                page.locator("#total-count").wait_for(
                    state="attached",
                    timeout=config.result_timeout_ms,
                )
            except PlaywrightTimeoutError as exc:
                raise PageStructureError(
                    f"Listing count marker did not appear: {exc}",
                    target=url,
                    cause=exc,
                ) from exc
            return attempt
        except AccessRestrictedError:
            raise
        except PlaywrightTimeoutError as exc:
            last_error = NavigationError(
                f"Timed out waiting for listing page: {exc}",
                target=url,
                cause=exc,
            )
        except PlaywrightError as exc:
            last_error = NavigationError(
                f"Browser navigation failed: {exc}",
                target=url,
                cause=exc,
            )
        if attempt < config.max_retries:
            delay = min(
                config.retry_backoff_seconds * (2**attempt),
                config.max_retry_backoff_seconds,
            )
            sleep(delay)  # type: ignore[operator]
    raise NavigationError(
        f"Navigation retry budget exhausted: {last_error}",
        target=url,
        cause=last_error,
        retry_count=config.max_retries,
    )


def _fingerprint(contests: list[Contest]) -> str:
    identity_sequence = "\n".join(contest.contest_key for contest in contests)
    return hashlib.sha256(identity_sequence.encode("utf-8")).hexdigest()


def crawl_listing(
    page: Page,
    config: CrawlerConfig,
    *,
    max_pages: int | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> CrawlResult:
    if max_pages is not None and max_pages < 1:
        raise ValueError("max_pages must be a positive integer")

    result = CrawlResult()
    current_url = page_url(config.base_url, 1)
    seen_urls: set[str] = set()
    seen_fingerprints: set[str] = set()
    discovered_contests: list[Contest] = []
    last_navigation_at: float | None = None

    while current_url:
        normalized_url = _normalized_destination(current_url)
        if normalized_url in seen_urls:
            error = PaginationLoopError(
                "Pagination repeated a previously visited destination",
                target=current_url,
            )
            result.failures.append(_as_failure("listing", error, 0))
            result.pending_targets.append(current_url)
            break
        seen_urls.add(normalized_url)
        result.pages_discovered = len(seen_urls)

        retry_count = 0
        try:
            if last_navigation_at is not None:
                elapsed = time.monotonic() - last_navigation_at
                remaining = config.navigation_interval_seconds - elapsed
                if remaining > 0:
                    sleep(remaining)
            retry_count = _navigate(page, current_url, config, sleep)
            last_navigation_at = time.monotonic()
            result.pages_processed += 1
            contests = extract_contests(page, current_url, config.base_url)
            if contests:
                fingerprint = _fingerprint(contests)
                if fingerprint in seen_fingerprints:
                    raise PaginationLoopError(
                        "Pagination returned the same ordered contest page twice",
                        target=current_url,
                    )
                seen_fingerprints.add(fingerprint)
            discovered_contests.extend(contests)
            next_url = next_page_url(page, current_url, config.base_url)
            if next_url is None:
                result.listing_complete = True
                break
            if _normalized_destination(next_url) in seen_urls:
                raise PaginationLoopError(
                    "Next-page link points to a previously visited destination",
                    target=next_url,
                )
            if max_pages is not None and result.pages_processed >= max_pages:
                result.pending_targets.append(
                    f"listing page limit reached; not visited: {next_url}"
                )
                break
            current_url = next_url
        except JobFinderError as exc:
            result.failures.append(
                _as_failure(
                    "listing",
                    exc,
                    max(retry_count, exc.retry_count),
                )
            )
            if isinstance(exc, AccessRestrictedError):
                result.pending_targets.append("remaining listing traversal")
            else:
                result.pending_targets.append(current_url)
            break
        except (PlaywrightError, ValueError) as exc:
            error = PageStructureError(
                f"Unable to interpret listing page: {exc}",
                target=current_url,
                cause=exc,
            )
            result.failures.append(_as_failure("listing", error, 0))
            result.pending_targets.append(current_url)
            break

    result.contests = deduplicate_contests(discovered_contests)
    return result


def _request_profile_pdf(
    page: Page,
    contest: Contest,
    config: CrawlerConfig,
) -> PdfResponse:
    source_url = contest.profile_url
    if not source_url:
        raise DownloadError(
            "Contest has no profile PDF URL",
            target=contest.contest_key,
        )
    source = urlsplit(source_url)
    portal = urlsplit(config.base_url)
    if (
        source.scheme not in {"http", "https"}
        or source.netloc.lower() != portal.netloc.lower()
        or not source.path.lower().startswith("/media/documentos/")
        or not source.path.lower().endswith(".pdf")
    ):
        raise DownloadError(
            "Profile URL is not an official same-origin PDF path",
            target=source_url,
        )
    try:
        response = page.context.request.get(
            source_url,
            timeout=config.navigation_timeout_ms,
            headers={"Accept": "application/pdf"},
        )
        return PdfResponse(
            status=response.status,
            url=response.url,
            headers=response.headers,
            content=response.body(),
        )
    except PlaywrightError as exc:
        raise DownloadError(
            f"Unable to GET the official profile PDF: {exc}",
            target=source_url,
            cause=exc,
        ) from exc


def process_contests(
    page: Page,
    contests: list[Contest],
    config: CrawlerConfig,
    *,
    run_id: str,
    output_root: Path = Path("data/tmp"),
    processed_state: ProcessedContestStore | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> ContestProcessingResult:
    result = ContestProcessingResult()
    for contest_index, contest in enumerate(contests):
        if contest.skip_reason:
            result.skipped_contests.append(
                SkippedContest(
                    contest_key=contest.contest_key,
                    title=contest.title,
                    reason=contest.skip_reason,
                    listing_page_url=contest.listing_page_url,
                )
            )
            continue

        if processed_state and processed_state.contains(contest.official_id):
            result.skipped_contests.append(
                SkippedContest(
                    contest_key=contest.contest_key,
                    title=contest.title,
                    reason="already_processed",
                    listing_page_url=contest.listing_page_url,
                )
            )
            continue

        position = Position(
            position_key=build_position_key(
                contest_key=contest.contest_key,
                occurrence_ordinal=1,
            ),
            contest_key=contest.contest_key,
            title=contest.position_name,
            position_name=contest.position_name,
            position_code=contest.position_code,
            institution=contest.institution,
        )
        result.positions.append(position)

        if not contest.profile_url:
            result.documents.append(
                TermsDocument(
                    document_key=f"{contest.contest_key}:terms",
                    contest_key=contest.contest_key,
                    position_key=position.position_key,
                    status=DocumentStatus.NOT_OFFERED,
                )
            )
            continue

        def retrieve_profile_response() -> PdfResponse:
            sleep(config.navigation_interval_seconds)
            return _request_profile_pdf(page, contest, config)

        try:
            document = download_terms_pdf(
                retrieve_profile_response,
                run_id=run_id,
                contest=contest,
                source_url=contest.profile_url,
                output_root=output_root,
                max_retries=config.max_retries,
                retry_backoff_seconds=config.retry_backoff_seconds,
                max_retry_backoff_seconds=config.max_retry_backoff_seconds,
                sleep=sleep,
            )
        except AccessRestrictedError as exc:
            result.documents.append(
                TermsDocument(
                    document_key=f"{contest.contest_key}:terms",
                    contest_key=contest.contest_key,
                    position_key=position.position_key,
                    source_url=contest.profile_url,
                    status=DocumentStatus.DOWNLOAD_FAILED,
                )
            )
            result.failures.append(_as_failure("download", exc, exc.retry_count))
            result.pending_targets.append(f"document:{contest.contest_key}")
            result.pending_targets.extend(
                f"contest:{remaining.contest_key}"
                for remaining in contests[contest_index + 1 :]
            )
            break
        except DownloadError as exc:
            result.documents.append(
                TermsDocument(
                    document_key=f"{contest.contest_key}:terms",
                    contest_key=contest.contest_key,
                    position_key=position.position_key,
                    source_url=contest.profile_url,
                    status=DocumentStatus.DOWNLOAD_FAILED,
                )
            )
            result.failures.append(_as_failure("download", exc, exc.retry_count))
            result.pending_targets.append(f"document:{contest.contest_key}")
            continue

        document = replace(document, position_key=position.position_key)
        try:
            document = extract_pdf_sections(document)
        except PdfProcessingError as exc:
            document = replace(document, status=DocumentStatus.PROCESSING_FAILED)
            result.failures.append(_as_failure("pdf", exc, exc.retry_count))
            result.pending_targets.append(f"document:{contest.contest_key}")
        else:
            if document.status == DocumentStatus.REVIEW_REQUIRED:
                result.pending_targets.append(f"document-review:{contest.contest_key}")
        result.documents.append(document)
        if document.status == DocumentStatus.PROCESSED:
            position = enrich_position_from_document(position, document)
            result.positions[-1] = position
            if processed_state and contest.official_id:
                processed_state.mark_processed(contest.official_id)

    for document in result.documents:
        if document.status in {
            DocumentStatus.NOT_OFFERED,
            DocumentStatus.PROCESSED,
        }:
            continue
        result.positions = [
            enrich_position_from_document(position, document)
            if position.contest_key == document.contest_key
            else position
            for position in result.positions
        ]
    return result


def _as_failure(stage: str, error: JobFinderError, retry_count: int) -> RunFailure:
    return RunFailure(
        stage=stage,
        target=error.target,
        error_type=type(error).__name__,
        message=str(error),
        retry_count=retry_count,
    )
