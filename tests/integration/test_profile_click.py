from pathlib import Path
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import Browser, Route

from job_finder.config import CrawlerConfig
from job_finder.crawler import crawl_listing, process_contests
from job_finder.records import Contest, DocumentStatus

FIXTURES = Path(__file__).parents[1] / "fixtures"
BASE_URL = "https://portal.test/"
PROFILE_URL = f"{BASE_URL}media/documentos/official.pdf"


@pytest.mark.parametrize(
    "profile_control",
    [
        '<button class="btn-perfil" data-url="/media/documentos/official.pdf" '
        'onclick="this.dataset.clicked=\'yes\';window.open(this.dataset.url)">'
        "Ver perfil</button>",
        '<a href="/media/documentos/official.pdf" '
        'onclick="this.dataset.clicked=\'yes\'">Ver perfil</a>',
    ],
)
def test_profile_pdf_is_fetched_with_same_origin_http_get(
    browser: Browser,
    monkeypatch,
    tmp_path: Path,
    profile_control: str,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    listing_html = f"""
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">Analista de Sistemas</h3>
            <span class="concurso-id">ID 00123</span>
            {profile_control}
            <a class="concurso-ver-detalle"
               href="/publicaciones/proceso/">Ver proceso</a>
          </article>
        </main>
        <nav id="pager-nav" class="pager"><span>1 de 1</span></nav>
    """
    detail_requests: list[str] = []
    profile_requests: list[tuple[str, dict[str, object]]] = []
    pdf_content = (FIXTURES / "pdf/native-text.pdf").read_bytes()

    class _Response:
        status = 200
        url = PROFILE_URL
        headers = {"content-type": "application/pdf"}

        def body(self) -> bytes:
            return pdf_content

    def fake_get(url: str, **kwargs: object) -> _Response:
        profile_requests.append((url, kwargs))
        return _Response()

    def route_requests(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path == "/":
            route.fulfill(
                body=listing_html,
                content_type="text/html; charset=utf-8",
            )
        elif path == "/publicaciones/proceso/":
            detail_requests.append(route.request.url)
            route.fulfill(
                path=str(FIXTURES / "html/detail/one-position.html"),
                content_type="text/html; charset=utf-8",
            )
        else:
            route.fulfill(status=404, body="not found")

    context.route("**/*", route_requests)
    monkeypatch.setattr(context.request, "get", fake_get)

    clicked_count = 0
    try:
        config = CrawlerConfig(
            base_url=BASE_URL,
            navigation_interval_seconds=3,
            navigation_timeout_ms=500,
            result_timeout_ms=500,
            max_retries=0,
        )
        crawled = crawl_listing(page, config, sleep=lambda _: None)
        result = process_contests(
            page,
            crawled.contests,
            config,
            run_id="run-profile-click",
            output_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
        clicked_count = page.locator("[data-clicked=yes]").count()
    finally:
        context.close()

    assert detail_requests == []
    assert len(crawled.contests) == 1
    assert result.failures == [], [failure.message for failure in result.failures]
    assert profile_requests == [
        (
            PROFILE_URL,
            {
                "timeout": 500,
                "headers": {"Accept": "application/pdf"},
            },
        )
    ]
    assert clicked_count == 0
    assert len(result.positions) == 1
    assert result.documents[0].status == DocumentStatus.PROCESSED


def test_profile_click_does_not_use_ver_proceso_or_click_excluded_cards(
    browser: Browser,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    requests: list[str] = []
    context.route(
        "**/*",
        lambda route: (requests.append(route.request.url), route.abort()),
    )
    contest = Contest(
        official_id="00123",
        title="ENCUADRAMIENTO",
        institution=None,
        status=None,
        dates_raw=None,
        profile_url=PROFILE_URL,
        process_url=f"{BASE_URL}publicaciones/proceso/",
        detail_url=f"{BASE_URL}publicaciones/proceso/",
        listing_page_url=BASE_URL,
        skip_reason="non_vacancy_encuadramiento",
    )
    try:
        result = process_contests(
            page,
            [contest],
            CrawlerConfig(base_url=BASE_URL),
            run_id="run-profile-skip",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    assert requests == []
    assert result.positions == []
    assert result.documents == []
    assert len(result.skipped_contests) == 1
