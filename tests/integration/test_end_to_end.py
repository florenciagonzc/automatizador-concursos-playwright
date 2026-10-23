import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pytest
from playwright.sync_api import Browser, Route

from job_finder.config import CrawlerConfig
from job_finder.pipeline import execute_search_run
from job_finder.records import SearchRun

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


@pytest.mark.parametrize(
    ("pdf_fixture", "expected_relevance"),
    [
        ("profile-sections.pdf", "relevant"),
        ("non-it-profile.pdf", "not_relevant"),
    ],
)
def test_complete_local_run_writes_csv_and_json_report(
    browser: Browser,
    monkeypatch,
    tmp_path: Path,
    pdf_fixture: str,
    expected_relevance: str,
) -> None:
    context = browser.new_context()
    page = context.new_page()
    process_requests: list[str] = []

    def route_all(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path == "/":
            route.fulfill(
                path=str(FIXTURES / "html/listing/one-contest.html"),
                content_type="text/html; charset=utf-8",
            )
        elif path == "/detail/123/":
            process_requests.append(route.request.url)
            route.fulfill(
                path=str(FIXTURES / "html/detail/one-position.html"),
                content_type="text/html; charset=utf-8",
            )
        elif path == "/media/documentos/bases-123.pdf":
            route.fulfill(
                path=str(FIXTURES / "pdf" / pdf_fixture),
                content_type="application/pdf",
            )
        else:
            route.fulfill(status=404, body="not found")

    context.route("**/*", route_all)
    monkeypatch.setattr(
        context.request,
        "get",
        lambda url, **_: _ApiResponse(
            200, url, (FIXTURES / "pdf" / pdf_fixture).read_bytes()
        ),
    )
    try:
        run, frame = execute_search_run(
            page,
            CrawlerConfig(
                base_url=BASE_URL,
                output_root=tmp_path / "data/exports",
                processed_state_path=tmp_path / "data/processed_contests.json",
                result_timeout_ms=250,
            ),
            run_id="run-e2e",
            tmp_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    csv_path = tmp_path / "data/exports/run-e2e/positions.csv"
    report_path = tmp_path / "data/exports/run-e2e/run-report.json"
    csv_frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert run.status == "complete"
    assert process_requests == []
    assert run.positions_recorded == len(frame)
    assert len(csv_frame) == run.positions_recorded
    assert report["status"] == "complete"
    assert report["csv_path"] == "data/exports/run-e2e/positions.csv"
    assert report["positions_recorded"] == len(report["positions"]) == len(csv_frame)
    assert len(csv_frame.columns) == 11
    assert report["positions"][0]["web_contest_title"] == "Analista de Infraestructura"
    assert report["positions"][0]["position_name"] == "Analista de Infraestructura"
    assert report["positions"][0]["position_code"] == "AI-07"
    assert len(csv_frame) == 1
    assert csv_frame.loc[0, "position_title"] == "Analista de Infraestructura"
    if expected_relevance == "relevant":
        assert report["positions"][0]["experience_requirement"] == "required"
    assert next((tmp_path / "data/tmp/run-e2e/pdf").glob("*.pdf")).exists()
    assert report["positions"][0]["run_status"] == "complete"


def test_partial_local_run_exports_available_positions_and_failure_report(
    browser: Browser, monkeypatch, tmp_path: Path
) -> None:
    context = browser.new_context()
    page = context.new_page()
    process_requests: list[str] = []

    def route_all(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path == "/":
            route.fulfill(
                path=str(FIXTURES / "html/listing/one-contest.html"),
                content_type="text/html; charset=utf-8",
            )
        elif path == "/detail/123/":
            process_requests.append(route.request.url)
            route.fulfill(
                path=str(FIXTURES / "html/detail/one-position.html"),
                content_type="text/html; charset=utf-8",
            )
        elif path == "/media/documentos/bases-123.pdf":
            route.fulfill(status=503, body="temporarily unavailable")
        else:
            route.fulfill(status=404, body="not found")

    context.route("**/*", route_all)
    monkeypatch.setattr(
        context.request,
        "get",
        lambda url, **_: _ApiResponse(503, url, b"temporarily unavailable"),
    )
    try:
        run, frame = execute_search_run(
            page,
            CrawlerConfig(
                base_url=BASE_URL,
                output_root=tmp_path / "data/exports",
                processed_state_path=tmp_path / "data/processed_contests.json",
                result_timeout_ms=250,
            ),
            run_id="run-partial-e2e",
            tmp_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    csv_path = tmp_path / "data/exports/run-partial-e2e/positions.csv"
    report_path = tmp_path / "data/exports/run-partial-e2e/run-report.json"
    csv_frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert run.status == "partial"
    assert process_requests == []
    assert len(frame) == len(csv_frame) == 1
    assert report["status"] == "partial"
    assert report["csv_path"] == "data/exports/run-partial-e2e/positions.csv"
    assert list(csv_frame.columns) == [
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
    assert report["positions"][0]["document_status"] == "download_failed"
    assert report["positions"][0]["run_status"] == "partial"
    assert report["failures"][0]["stage"] == "download"
    assert json.loads(
        (tmp_path / "data/processed_contests.json").read_text(encoding="utf-8")
    ) == {"version": 1, "contest_ids": []}


def test_max_pages_pipeline_exports_first_page_as_partial(
    browser: Browser, monkeypatch, tmp_path: Path
) -> None:
    context = browser.new_context()
    page = context.new_page()
    listing_requests: list[str] = []

    def route_all(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path == "/":
            listing_requests.append(route.request.url)
            route.fulfill(
                path=str(FIXTURES / "html/listing/page-1.html"),
                content_type="text/html; charset=utf-8",
            )
        elif path.startswith("/publicaciones/"):
            route.fulfill(
                path=str(FIXTURES / "html/detail/one-position.html"),
                content_type="text/html; charset=utf-8",
            )
        elif path.startswith("/media/documentos/"):
            route.fulfill(
                path=str(FIXTURES / "pdf/profile-sections.pdf"),
                content_type="application/pdf",
            )
        else:
            route.fulfill(status=404, body="not found")

    context.route("**/*", route_all)
    monkeypatch.setattr(
        context.request,
        "get",
        lambda url, **_: _ApiResponse(
            200, url, (FIXTURES / "pdf/profile-sections.pdf").read_bytes()
        ),
    )
    try:
        run, frame = execute_search_run(
            page,
            CrawlerConfig(
                base_url=BASE_URL,
                output_root=tmp_path / "data/exports",
                processed_state_path=tmp_path / "data/processed_contests.json",
                result_timeout_ms=250,
            ),
            run_id="run-limited",
            max_pages=1,
            tmp_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    csv_path = tmp_path / "data/exports/run-limited/positions.csv"
    report_path = tmp_path / "data/exports/run-limited/run-report.json"
    csv_frame = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert len(listing_requests) == 1
    assert {
        parse_qs(urlsplit(url).query)["page"][0]
        for url in listing_requests
    } == {"1"}
    assert run.status == "partial"
    assert run.pages_processed == run.pages_discovered == 1
    assert run.contests_discovered == 2
    assert len(frame) == len(csv_frame) == 2
    assert report["status"] == "partial"
    assert report["pending_targets"] == [
        "listing page limit reached; not visited: "
        "https://portal.test/?page=2&modo=lista"
    ]
    assert list(csv_frame.columns) == [
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


def test_encuadramiento_is_reported_as_skipped_without_detail_or_pdf_request(
    browser: Browser, tmp_path: Path
) -> None:
    context = browser.new_context()
    page = context.new_page()
    detail_or_pdf_requests: list[str] = []
    listing_html = """
        <span id="total-count">1 concurso encontrado</span>
        <main id="contenido-concursos">
          <article class="concurso-card">
            <h3 class="concurso-titulo">ENCUADRAMIENTO - FASE INICIAL</h3>
            <span class="concurso-id">ID 13331</span>
            <button class="btn-perfil btn-open-url"
                    data-url="/media/documentos/manual.pdf">Ver perfil</button>
            <a class="concurso-ver-detalle" href="/publicaciones/proceso/">
              Ver proceso
            </a>
          </article>
        </main>
        <nav id="pager-nav" class="pager"><span>1 de 1</span></nav>
    """

    def route_all(route: Route) -> None:
        path = urlsplit(route.request.url).path
        if path == "/":
            route.fulfill(body=listing_html, content_type="text/html; charset=utf-8")
        else:
            detail_or_pdf_requests.append(route.request.url)
            route.fulfill(status=500, body="excluded contest must not be opened")

    context.route("**/*", route_all)
    try:
        run, frame = execute_search_run(
            page,
            CrawlerConfig(
                base_url=BASE_URL,
                output_root=tmp_path / "data/exports",
                processed_state_path=tmp_path / "data/processed_contests.json",
                result_timeout_ms=250,
            ),
            run_id="run-encuadramiento",
            tmp_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    report_path = (
        tmp_path / "data/exports/run-encuadramiento/run-report.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))

    assert detail_or_pdf_requests == []
    assert run.status == "complete"
    assert run.contests_discovered == 1
    assert run.positions_recorded == 0
    assert len(frame) == 0
    assert report["skipped_contests"] == [
        {
            "contest_key": "id:13331",
            "title": "ENCUADRAMIENTO - FASE INICIAL",
            "reason": "non_vacancy_encuadramiento",
            "listing_page_url": f"{BASE_URL}?page=1&modo=lista",
        }
    ]


def test_successful_contest_is_skipped_on_the_next_run(
    browser: Browser, monkeypatch, tmp_path: Path
) -> None:
    context = browser.new_context()
    page = context.new_page()
    profile_requests: list[str] = []
    pdf_bytes = (FIXTURES / "pdf/profile-sections.pdf").read_bytes()
    context.route(
        "**/*",
        lambda route: route.fulfill(
            path=str(FIXTURES / "html/listing/one-contest.html"),
            content_type="text/html; charset=utf-8",
        )
        if urlsplit(route.request.url).path == "/"
        else route.fulfill(status=404, body="not found"),
    )

    def get_pdf(url: str, **_: object) -> _ApiResponse:
        profile_requests.append(url)
        return _ApiResponse(200, url, pdf_bytes)

    monkeypatch.setattr(context.request, "get", get_pdf)
    config = CrawlerConfig(
        base_url=BASE_URL,
        output_root=tmp_path / "data/exports",
        processed_state_path=tmp_path / "data/processed_contests.json",
        result_timeout_ms=250,
    )
    try:
        first_run, _ = execute_search_run(
            page,
            config,
            run_id="run-first",
            tmp_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
        second_run, second_frame = execute_search_run(
            page,
            config,
            run_id="run-second",
            tmp_root=tmp_path / "data/tmp",
            sleep=lambda _: None,
        )
    finally:
        context.close()

    state = json.loads(
        (tmp_path / "data/processed_contests.json").read_text(encoding="utf-8")
    )
    second_report = json.loads(
        (
            tmp_path / "data/exports/run-second/run-report.json"
        ).read_text(encoding="utf-8")
    )
    assert first_run.positions_recorded == 1
    assert first_run.status == "complete"
    assert len(profile_requests) == 1
    assert state == {"version": 1, "contest_ids": ["00123"]}
    assert second_run.status == "complete"
    assert second_run.positions_recorded == 0
    assert second_frame.empty
    assert second_report["skipped_contests"] == [
        {
            "contest_key": "id:00123",
            "title": "Analista de Infraestructura",
            "reason": "already_processed",
            "listing_page_url": f"{BASE_URL}?page=1&modo=lista",
        }
    ]
