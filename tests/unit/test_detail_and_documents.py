from pathlib import Path

import pytest
from playwright.sync_api import Browser

from job_finder.documents import PdfResponse, download_terms_pdf, extract_pdf_sections
from job_finder.errors import DownloadError, PdfProcessingError
from job_finder.extraction import extract_positions
from job_finder.records import (
    Contest,
    DocumentStatus,
    FieldStatus,
    Position,
    PublishedFieldStatus,
    TermsDocument,
)

FIXTURES = Path(__file__).parents[1] / "fixtures"
PDF_FIXTURES = FIXTURES / "pdf"
BASE_URL = "https://portal.test/"


def _contest(profile_url: str | None = None) -> Contest:
    return Contest(
        official_id="00123",
        title="Concurso de prueba",
        institution="Ministerio de Prueba",
        status="En Postulación",
        dates_raw=None,
        profile_url=profile_url,
        process_url=f"{BASE_URL}detail/123/",
        detail_url=f"{BASE_URL}detail/123/",
        listing_page_url=f"{BASE_URL}?page=1",
    )


def test_extracts_one_position_and_published_values(browser: Browser) -> None:
    page = browser.new_page()
    try:
        page.set_content((FIXTURES / "html/detail/one-position.html").read_text())
        positions = extract_positions(page, _contest(), f"{BASE_URL}detail/123/")
    finally:
        page.context.close()

    assert len(positions) == 1
    position = positions[0]
    assert position.position_key == "id:puesto-001"
    assert position.contest_key == "id:00123"
    assert position.title == "Analista de Infraestructura"
    assert position.institution == "Ministerio de Prueba"
    assert position.salary_raw == "Gs. 8.500.000"
    assert position.salary_status == PublishedFieldStatus.PUBLISHED
    assert position.deadline_raw == "30/11/2026"
    assert position.detail_url == f"{BASE_URL}puestos/puesto-001/"


def test_extracts_multiple_positions_with_distinct_keys(browser: Browser) -> None:
    page = browser.new_page()
    try:
        page.set_content(
            (FIXTURES / "html/detail/multiple-positions.html").read_text()
        )
        positions = extract_positions(page, _contest(), f"{BASE_URL}detail/123/")
    finally:
        page.context.close()

    assert [position.position_key for position in positions] == [
        "id:puesto-101",
        "id:puesto-102",
    ]
    assert positions[1].salary_status == PublishedFieldStatus.NOT_FOUND


def test_missing_fields_have_explicit_statuses(browser: Browser) -> None:
    page = browser.new_page()
    try:
        page.set_content((FIXTURES / "html/detail/missing-fields.html").read_text())
        position = extract_positions(
            page, _contest(), f"{BASE_URL}detail/123/"
        )[0]
    finally:
        page.context.close()

    assert position.salary_status == PublishedFieldStatus.NOT_STATED
    assert position.salary_raw is None
    assert position.deadline_status == PublishedFieldStatus.NOT_FOUND
    assert position.institution is None


def test_missing_pdf_is_explicitly_not_offered() -> None:
    document = TermsDocument(
        document_key="id:00123:terms",
        contest_key="id:00123",
        status=DocumentStatus.NOT_OFFERED,
    )

    assert document.status == DocumentStatus.NOT_OFFERED
    assert document.local_path is None


@pytest.mark.parametrize(
    ("fixture", "expected_fields"),
    [
        (
            "native-text.pdf",
            {
                "descripcion_puesto": "Responsable de sistemas institucionales.",
                "oferta_salarial": "Gs. 8.500.000 mensuales.",
                "perfil_requerido": "Ingenieria Informatica.",
            },
        ),
    ],
)
def test_extracts_requested_pdf_sections(
    fixture: str, expected_fields: dict[str, str], tmp_path: Path
) -> None:
    path = PDF_FIXTURES / fixture
    document = TermsDocument(
        document_key="id:00123:terms",
        contest_key="id:00123",
        status=DocumentStatus.DOWNLOADED,
        local_path=str(path),
    )

    processed = extract_pdf_sections(document)

    assert processed.status == DocumentStatus.PROCESSED
    sections = processed.extracted_fields["sections"]
    for key, expected in expected_fields.items():
        assert sections[key]["text"] == expected
        assert sections[key]["pages"] == [1]


def test_no_native_text_is_marked_for_review() -> None:
    document = TermsDocument(
        document_key="image-only",
        contest_key="id:00123",
        status=DocumentStatus.DOWNLOADED,
        local_path=str(PDF_FIXTURES / "image-only.pdf"),
    )

    processed = extract_pdf_sections(document)

    assert processed.status == DocumentStatus.REVIEW_REQUIRED
    assert processed.extracted_fields["native_text_status"] == "no_native_text"


@pytest.mark.parametrize("fixture", ["empty.pdf", "malformed.pdf", "encrypted.pdf"])
def test_unreadable_pdfs_raise_contextual_processing_error(fixture: str) -> None:
    document = TermsDocument(
        document_key=fixture,
        contest_key="id:00123",
        status=DocumentStatus.DOWNLOADED,
        local_path=str(PDF_FIXTURES / fixture),
    )

    with pytest.raises(PdfProcessingError) as error:
        extract_pdf_sections(document)

    assert error.value.target == str(PDF_FIXTURES / fixture)


def test_persists_and_validates_pdf_response_under_run_directory(
    tmp_path: Path,
) -> None:
    source = f"{BASE_URL}media/documentos/official.pdf"
    pdf_response = PdfResponse(
        status=200,
        url=source,
        headers={"content-type": "application/pdf"},
        content=(PDF_FIXTURES / "native-text.pdf").read_bytes(),
    )
    document = download_terms_pdf(
        lambda: pdf_response,
        run_id="run-123",
        contest=_contest(source),
        source_url=source,
        output_root=tmp_path / "data/tmp",
    )

    assert document.status == DocumentStatus.DOWNLOADED
    assert document.local_path is not None
    assert Path(document.local_path).parent == tmp_path / "data/tmp/run-123/pdf"
    assert Path(document.local_path).read_bytes().startswith(b"%PDF-")
    assert document.retrieved_at
    assert len(document.sha256 or "") == 64


def test_download_failure_is_contextual_and_not_silenced(
    tmp_path: Path,
) -> None:
    source = f"{BASE_URL}media/documentos/missing.pdf"
    with pytest.raises(DownloadError) as error:
        download_terms_pdf(
            lambda: PdfResponse(
                status=404,
                url=source,
                headers={"content-type": "text/plain"},
                content=b"missing",
            ),
            run_id="run-404",
            contest=_contest(source),
            source_url=source,
            output_root=tmp_path,
        )

    assert error.value.target == source


def test_html_profile_response_is_rejected_as_non_pdf(tmp_path: Path) -> None:
    source = f"{BASE_URL}media/documentos/official.pdf"
    with pytest.raises(DownloadError, match="PDF file signature") as error:
        download_terms_pdf(
            lambda: PdfResponse(
                status=200,
                url=source,
                headers={"content-type": "text/html"},
                content=b"<html>login page</html>",
            ),
            run_id="run-html-response",
            contest=_contest(source),
            source_url=source,
            output_root=tmp_path,
            max_retries=0,
        )

    assert error.value.target == source


def test_position_status_contract_rejects_found_without_value() -> None:
    with pytest.raises(ValueError, match="salary_raw is required"):
        Position(
            position_key="position-1",
            contest_key="id:00123",
            salary_status=PublishedFieldStatus.PUBLISHED,
        )
