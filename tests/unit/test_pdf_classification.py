from pathlib import Path

from job_finder.documents import extract_pdf_sections
from job_finder.extraction import enrich_position_from_document
from job_finder.records import (
    DocumentStatus,
    FieldStatus,
    Position,
    TermsDocument,
)

FIXTURES = Path(__file__).parents[1] / "fixtures" / "pdf"


def _position() -> Position:
    return Position(
        position_key="position-1",
        contest_key="id:00123",
        title="Analista de Sistemas",
        institution="Ministerio de Prueba",
    )


def _document(filename: str) -> TermsDocument:
    return TermsDocument(
        document_key=f"id:00123:{filename}",
        contest_key="id:00123",
        status=DocumentStatus.DOWNLOADED,
        source_url="https://portal.test/media/documentos/bases.pdf",
        local_path=str(FIXTURES / filename),
    )


def test_pdf_sections_populate_fields_and_classify_it_relevance() -> None:
    document = extract_pdf_sections(_document("profile-sections.pdf"))

    position = enrich_position_from_document(_position(), document)

    assert position.education_raw == "Ingeniería Informática."
    assert position.education_status == FieldStatus.FOUND
    assert position.knowledge_raw == "Administración de redes y servidores."
    assert position.knowledge_status == FieldStatus.FOUND
    assert position.duties_raw == "Administrar sistemas institucionales."
    assert position.ti_relevance == "relevant"
    assert "redes" in (position.ti_relevance_evidence or "").lower()
    assert position.experience_requirement == "required"
    assert position.application_conditions_status == FieldStatus.FOUND


def test_non_it_profile_is_classified_with_source_evidence() -> None:
    document = extract_pdf_sections(_document("non-it-profile.pdf"))

    position = enrich_position_from_document(_position(), document)

    assert position.ti_relevance == "not_relevant"
    assert position.ti_relevance_evidence


def test_insufficient_profile_evidence_is_indeterminate() -> None:
    document = extract_pdf_sections(_document("vague-profile.pdf"))

    position = enrich_position_from_document(_position(), document)

    assert position.ti_relevance == "indeterminate"
    assert position.ti_relevance_evidence is None
    assert position.experience_requirement == "not_stated"


def test_no_text_document_marks_fields_unreadable_not_missing() -> None:
    document = extract_pdf_sections(_document("image-only.pdf"))

    position = enrich_position_from_document(_position(), document)

    assert document.status == DocumentStatus.REVIEW_REQUIRED
    assert position.education_status == FieldStatus.UNREADABLE
    assert position.knowledge_status == FieldStatus.UNREADABLE
    assert position.duties_status == FieldStatus.UNREADABLE
    assert position.experience_requirement == "unreadable"
    assert position.salary_pdf_status == FieldStatus.UNREADABLE
    assert position.vacancies_status == FieldStatus.UNREADABLE
    assert position.position_type_budget_status == FieldStatus.UNREADABLE
    assert position.min_experience_status == FieldStatus.UNREADABLE
    assert position.optional_experience_status == FieldStatus.UNREADABLE
    assert position.ti_relevance == "indeterminate"


def test_experience_without_required_evidence_is_not_required() -> None:
    document = extract_pdf_sections(_document("no-experience-profile.pdf"))

    position = enrich_position_from_document(_position(), document)

    assert position.experience_requirement == "not_required"
    assert position.min_experience_status == FieldStatus.NOT_STATED
    assert position.optional_experience_status == FieldStatus.NOT_STATED
