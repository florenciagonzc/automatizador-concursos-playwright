from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import Browser, Route

from job_finder.config import CrawlerConfig
from job_finder.crawler import crawl_listing
from job_finder.extraction import extract_contests

FIXTURES = Path(__file__).parents[1] / "fixtures" / "html" / "listing"
BASE_URL = "https://portal.test/"


def _route_fixture(browser: Browser, page_name_by_number: dict[int, str]):
    context = browser.new_context()
    page = context.new_page()
    attempts: dict[int, int] = {}

    def handler(route: Route) -> None:
        query = parse_qs(urlsplit(route.request.url).query)
        page_number = int(query.get("page", ["1"])[0])
        attempts[page_number] = attempts.get(page_number, 0) + 1
        page_name = page_name_by_number[page_number]
        route.fulfill(
            path=str(FIXTURES / page_name),
            content_type="text/html; charset=utf-8",
        )

    context.route("**/*", handler)
    return context, page, attempts


def _config(**overrides: object) -> CrawlerConfig:
    return CrawlerConfig(base_url=BASE_URL, result_timeout_ms=250, **overrides)


def test_profile_url_uses_exact_ver_perfil_control_not_process_link(
    browser: Browser,
) -> None:
    page = browser.new_page()
    page.set_content(
        """
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">Analista de Sistemas</h3>
            <span class="concurso-id">ID 00123</span>
            <a class="concurso-ver-detalle" href="/publicaciones/proceso/">
              Ver proceso
            </a>
            <a href="/media/documentos/bases-oficiales.pdf">Ver perfil</a>
          </article>
        </main>
        """
    )
    try:
        contests = extract_contests(page, BASE_URL, BASE_URL)
    finally:
        page.context.close()

    assert contests[0].process_url == f"{BASE_URL}publicaciones/proceso/"
    assert contests[0].profile_url == (
        f"{BASE_URL}media/documentos/bases-oficiales.pdf"
    )


def test_profile_url_matches_live_portal_button_markup(browser: Browser) -> None:
    page = browser.new_page()
    page.set_content(
        """
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">Analista de Sistemas</h3>
            <span class="concurso-id">ID 13331</span>
            <button
              class="concurso-ver-detalle btn-perfil btn-open-url"
              data-url="/media/documentos/2026/288/bases-oficiales.pdf"
            >Ver perfil</button>
            <a class="concurso-ver-detalle" href="/publicaciones/info13331/4788/">
              Ver proceso
            </a>
          </article>
        </main>
        """
    )
    try:
        contests = extract_contests(page, BASE_URL, BASE_URL)
    finally:
        page.context.close()

    assert contests[0].profile_url == (
        f"{BASE_URL}media/documentos/2026/288/bases-oficiales.pdf"
    )
    assert contests[0].process_url == (
        f"{BASE_URL}publicaciones/info13331/4788/"
    )


@pytest.mark.parametrize("label", ["ENCUADRAMIENTO", "ENCUADERNAMIENTO"])
def test_encuadramiento_card_is_marked_and_profile_url_is_not_selected(
    browser: Browser, label: str
) -> None:
    page = browser.new_page()
    page.set_content(
        f"""
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">{label} - FASE INICIAL</h3>
            <span class="concurso-id">ID 13331</span>
            <button class="btn-perfil btn-open-url"
                    data-url="/media/documentos/manual.pdf">Ver perfil</button>
            <a href="/publicaciones/info13331/4788/">Ver proceso</a>
          </article>
        </main>
        """
    )
    try:
        contest = extract_contests(page, BASE_URL, BASE_URL)[0]
    finally:
        page.context.close()

    assert contest.skip_reason == "non_vacancy_encuadramiento"
    assert contest.profile_url is None


def test_encuadramiento_badge_marks_card_even_when_title_is_generic(
    browser: Browser,
) -> None:
    page = browser.new_page()
    page.set_content(
        """
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">Convocatoria institucional</h3>
            <span class="concurso-id">ID 13332</span>
            <span class="badge-tipo">ENCUADERNAMIENTO</span>
            <button class="btn-perfil btn-open-url"
                    data-url="/media/documentos/manual.pdf">Ver perfil</button>
            <a href="/publicaciones/proceso/">Ver proceso</a>
          </article>
        </main>
        """
    )
    try:
        contest = extract_contests(page, BASE_URL, BASE_URL)[0]
    finally:
        page.context.close()

    assert contest.skip_reason == "non_vacancy_encuadramiento"
    assert contest.profile_url is None


def test_profile_url_requires_ver_perfil_label_on_official_pdf_link(
    browser: Browser,
) -> None:
    page = browser.new_page()
    page.set_content(
        """
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">Analista de Sistemas</h3>
            <span class="concurso-id">ID 00123</span>
            <a class="concurso-ver-detalle" href="/publicaciones/proceso/">
              Ver proceso
            </a>
            <a href="/media/documentos/bases-oficiales.pdf">
              <span aria-label="documento de bases"></span>
            </a>
          </article>
        </main>
        """
    )
    try:
        contests = extract_contests(page, BASE_URL, BASE_URL)
    finally:
        page.context.close()

    assert contests[0].profile_url is None


def test_process_link_alone_is_not_mistaken_for_profile_pdf(browser: Browser) -> None:
    page = browser.new_page()
    page.set_content(
        """
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">Analista de Sistemas</h3>
            <span class="concurso-id">ID 00123</span>
            <a class="concurso-ver-detalle" href="/publicaciones/proceso/">
              Ver proceso
            </a>
          </article>
        </main>
        """
    )
    try:
        contests = extract_contests(page, BASE_URL, BASE_URL)
    finally:
        page.context.close()

    assert contests[0].process_url == f"{BASE_URL}publicaciones/proceso/"
    assert contests[0].profile_url is None


def test_crawls_pages_in_order_and_extracts_visible_contest_fields(browser: Browser) -> None:
    context, page, attempts = _route_fixture(
        browser, {1: "page-1.html", 2: "page-2.html"}
    )
    sleeps: list[float] = []
    try:
        result = crawl_listing(page, _config(), sleep=sleeps.append)
    finally:
        context.close()

    assert attempts == {1: 1, 2: 1}
    assert result.listing_complete
    assert result.pages_processed == 2
    assert result.pages_discovered == 2
    assert [contest.official_id for contest in result.contests] == ["00123", "124", "125"]
    first = result.contests[0]
    assert first.title == "Analista de Sistemas"
    assert first.position_name is None
    assert first.position_code is None
    assert first.institution == "Ministerio de Prueba"
    assert first.status == "En Postulación"
    assert "Fin de Postulación: 03/11/2026 15:30" in (first.dates_raw or "")
    assert first.profile_url == "https://portal.test/media/documentos/bases-123.pdf"
    assert first.process_url == "https://portal.test/publicaciones/info00123/4788/"
    assert sleeps and sleeps[0] >= 0


def test_max_pages_stops_listing_and_reports_unvisited_page(browser: Browser) -> None:
    context, page, attempts = _route_fixture(
        browser, {1: "page-1.html", 2: "page-2.html"}
    )
    try:
        result = crawl_listing(
            page,
            _config(),
            max_pages=1,
            sleep=lambda _: None,
        )
    finally:
        context.close()

    assert attempts == {1: 1}
    assert not result.listing_complete
    assert result.pages_processed == result.pages_discovered == 1
    assert [contest.official_id for contest in result.contests] == ["00123", "124"]
    assert result.pending_targets == [
        "listing page limit reached; not visited: "
        "https://portal.test/?page=2&modo=lista"
    ]


def test_max_pages_must_be_positive(browser: Browser) -> None:
    context = browser.new_context()
    page = context.new_page()
    try:
        with pytest.raises(ValueError, match="max_pages must be a positive integer"):
            crawl_listing(page, _config(), max_pages=0, sleep=lambda _: None)
    finally:
        context.close()


def test_recognizes_explicit_empty_listing_as_complete(browser: Browser) -> None:
    context, page, _ = _route_fixture(browser, {1: "empty.html"})
    try:
        result = crawl_listing(page, _config(), sleep=lambda _: None)
    finally:
        context.close()

    assert result.listing_complete
    assert result.contests == []
    assert result.failures == []


def test_changed_dom_is_partial_not_successful_empty(browser: Browser) -> None:
    context, page, _ = _route_fixture(browser, {1: "changed-markup.html"})
    try:
        result = crawl_listing(page, _config(), sleep=lambda _: None)
    finally:
        context.close()

    assert not result.listing_complete
    assert result.pages_processed == 0
    assert result.failures[0].error_type == "PageStructureError"
    assert result.pending_targets


def test_repeated_ordered_listing_fingerprint_is_partial(browser: Browser) -> None:
    context, page, _ = _route_fixture(
        browser, {1: "page-1.html", 2: "repeated-page.html"}
    )
    try:
        result = crawl_listing(page, _config(), sleep=lambda _: None)
    finally:
        context.close()

    assert not result.listing_complete
    assert result.pages_processed == 2
    assert result.failures[0].error_type == "PaginationLoopError"


def test_repeated_destination_is_partial(browser: Browser) -> None:
    context, page, attempts = _route_fixture(
        browser, {1: "repeated-destination.html"}
    )
    try:
        result = crawl_listing(page, _config(), sleep=lambda _: None)
    finally:
        context.close()

    assert attempts == {1: 1}
    assert not result.listing_complete
    assert result.pages_processed == 1
    assert result.failures[0].error_type == "PaginationLoopError"


def test_retry_exhaustion_is_reported_with_page_target(browser: Browser) -> None:
    context = browser.new_context()
    page = context.new_page()
    attempts = 0

    def unavailable(route: Route) -> None:
        nonlocal attempts
        attempts += 1
        route.fulfill(
            status=503,
            body="temporarily unavailable",
            content_type="text/html; charset=utf-8",
        )

    context.route("**/*", unavailable)
    try:
        result = crawl_listing(page, _config(), sleep=lambda _: None)
    finally:
        context.close()

    assert attempts == 3
    assert not result.listing_complete
    assert result.failures[0].error_type == "NavigationError"
    assert "retry budget exhausted" in result.failures[0].message.lower()
    assert result.failures[0].target.startswith(BASE_URL)
    assert result.failures[0].retry_count == 2


def test_access_denial_stops_without_retry(browser: Browser) -> None:
    context = browser.new_context()
    page = context.new_page()
    attempts = 0

    def denied(route: Route) -> None:
        nonlocal attempts
        attempts += 1
        route.fulfill(
            status=403,
            body="forbidden",
            content_type="text/html; charset=utf-8",
        )

    context.route("**/*", denied)
    try:
        result = crawl_listing(page, _config(), sleep=lambda _: None)
    finally:
        context.close()

    assert attempts == 1
    assert not result.listing_complete
    assert result.failures[0].error_type == "AccessRestrictedError"
