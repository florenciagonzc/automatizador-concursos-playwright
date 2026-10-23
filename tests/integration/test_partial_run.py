from pathlib import Path

from playwright.sync_api import Browser

from job_finder.config import CrawlerConfig
from job_finder.crawler import process_contests
from job_finder.records import Contest, DocumentStatus, SearchRun

FIXTURES = Path(__file__).parents[1] / "fixtures"
BASE_URL = "https://portal.test/"


class _ApiResponse:
    def __init__(self, status: int, url: str, content: bytes) -> None:
        self.status = status
        self.url = url
        self.headers = {"content-type": "application/pdf"}
        self._content = content

    def body(self) -> bytes:
        return self._content


def _contest(identifier: str, *, pdf: bool = False) -> Contest:
    detail_url = f"{BASE_URL}detail/{identifier}/"
    profile_url = f"{BASE_URL}media/documentos/{identifier}.pdf" if pdf else None
    return Contest(
        official_id=identifier,
        title=f"Concurso {identifier}",
        institution="Institución de prueba",
        status="En Postulación",
        dates_raw=None,
        profile_url=profile_url,
        process_url=detail_url,
        detail_url=detail_url,
        listing_page_url=f"{BASE_URL}?page=1",
    )


def test_pdf_failures_do_not_stop_independent_contests(
    browser: Browser, monkeypatch, tmp_path: Path
) -> None:
    context = browser.new_context()
    page = context.new_page()
    pdf_attempts = 0
    process_requests: list[str] = []

    def route_process(route) -> None:
        process_requests.append(route.request.url)
        route.fulfill(body="generic process page", content_type="text/html")

    def route_pdf(route) -> None:
        nonlocal pdf_attempts
        pdf_attempts += 1
        route.fulfill(status=503, body="pdf unavailable")

    context.route("**/detail/**", route_process)
    context.route("**/publicaciones/**", route_process)
    listing_html = """
        <span id="total-count">4 concursos encontrados</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <span class="concurso-id">ID 2</span>
            <button data-url="/media/documentos/2.pdf"
                    onclick="window.open(this.dataset.url)">Ver perfil</button>
          </article>
          <article class="concurso-card">
            <span class="concurso-id">ID 3</span>
          </article>
          <article class="concurso-card">
            <span class="concurso-id">ID 4</span>
            <button data-url="/media/documentos/4.pdf"
                    onclick="window.open(this.dataset.url)">Ver perfil</button>
          </article>
        </main>
        <nav class="pager"><span>1 de 1</span></nav>
    """
    context.route(
        "**/*page=1*",
        lambda route: route.fulfill(
            body=listing_html,
            content_type="text/html; charset=utf-8",
        ),
    )
    context.route("**/media/documentos/2.pdf", route_pdf)
    context.route(
        "**/media/documentos/4.pdf",
        lambda route: route.fulfill(
            path=str(FIXTURES / "pdf/malformed.pdf"),
            content_type="application/pdf",
        ),
    )

    def fake_get(url: str, **_: object) -> _ApiResponse:
        nonlocal pdf_attempts
        pdf_attempts += 1
        if url.endswith("/2.pdf"):
            return _ApiResponse(503, url, b"pdf unavailable")
        return _ApiResponse(
            200,
            url,
            (FIXTURES / "pdf/malformed.pdf").read_bytes(),
        )

    monkeypatch.setattr(context.request, "get", fake_get)
    try:
        result = process_contests(
            page,
            [
                _contest("1"),
                _contest("2", pdf=True),
                _contest("3"),
                _contest("4", pdf=True),
            ],
            CrawlerConfig(
                base_url=BASE_URL,
                navigation_interval_seconds=3,
                result_timeout_ms=250,
            ),
            run_id="run-partial",
            output_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    assert [position.contest_key for position in result.positions] == [
        "id:1",
        "id:2",
        "id:3",
        "id:4",
    ]
    assert process_requests == []
    assert [failure.stage for failure in result.failures] == ["download", "pdf"]
    assert result.failures[0].retry_count == 2
    assert pdf_attempts == 4
    assert result.documents[0].status == DocumentStatus.NOT_OFFERED
    assert result.documents[1].status == DocumentStatus.DOWNLOAD_FAILED
    assert result.documents[3].status == DocumentStatus.PROCESSING_FAILED
    assert len(result.positions) == 4
    assert result.pending_targets

    run = SearchRun(
        run_id="run-partial",
        pages_discovered=1,
        pages_processed=1,
        contests_discovered=4,
        positions_recorded=len(result.positions),
        failures=result.failures,
        pending_targets=result.pending_targets,
    )
    run.finalize(listing_complete=True)
    assert run.status == "partial"


def test_encuadramiento_is_skipped_before_detail_or_pdf_request(
    browser: Browser,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    requests: list[str] = []

    def reject_any_navigation(route) -> None:
        requests.append(route.request.url)
        route.abort()

    context.route("**/*", reject_any_navigation)
    contest = _contest("13331", pdf=True)
    contest = Contest(
        official_id=contest.official_id,
        title="ENCUADRAMIENTO - FASE INICIAL",
        institution=contest.institution,
        status=contest.status,
        dates_raw=contest.dates_raw,
        profile_url=contest.profile_url,
        process_url=contest.process_url,
        detail_url=contest.detail_url,
        listing_page_url=contest.listing_page_url,
        skip_reason="non_vacancy_encuadramiento",
    )
    try:
        result = process_contests(
            page,
            [contest],
            CrawlerConfig(base_url=BASE_URL),
            run_id="run-skip",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    assert requests == []
    assert result.positions == []
    assert result.documents == []
    assert result.failures == []
    assert len(result.skipped_contests) == 1
    skipped = result.skipped_contests[0]
    assert skipped.contest_key == "id:13331"
    assert skipped.title == "ENCUADRAMIENTO - FASE INICIAL"
    assert skipped.reason == "non_vacancy_encuadramiento"
    assert skipped.listing_page_url == f"{BASE_URL}?page=1"
