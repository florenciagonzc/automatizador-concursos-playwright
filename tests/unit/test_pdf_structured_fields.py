from pathlib import Path

import pandas as pd
import pdfplumber

from job_finder.documents import extract_pdf_sections
from job_finder.extraction import enrich_position_from_document
from job_finder.export import build_dataframe, write_csv
from job_finder.records import (
    Contest,
    DocumentStatus,
    FieldStatus,
    Position,
    PublishedFieldStatus,
    TermsDocument,
)


class _Page:
    def __init__(self, text: str, tables: list[list[list[str]]] | None = None) -> None:
        self.text = text
        self.tables = tables or []

    def extract_text(self) -> str:
        return self.text

    def extract_tables(self) -> list[list[list[str]]]:
        return self.tables


class _Pdf:
    def __init__(self, pages: list[_Page] | None = None) -> None:
        self.pages = pages or [
            _Page(
                "2. OFERTA SALARIAL\n"
                "Remuneración: Gs. 8.500.000\n"
                "Vacancias: 2\n"
                "Tipo de presupuesto: Permanente\n"
                "3. PERFIL REQUERIDO\n"
                "a) EXPERIENCIA LABORAL\n"
                "Mínimos Requeridos:\n"
                "2 años de experiencia en administración de redes."
            ),
            _Page(
                "Opcionales:\n"
                "Experiencia en servicios de nube.\n"
                "b) FORMACIÓN ACADÉMICA\n"
                "Ingeniería Informática."
            ),
        ]

    def __enter__(self) -> "_Pdf":
        return self

    def __exit__(self, *_: object) -> None:
        return None


def test_all_pdf_pages_feed_structured_salary_and_experience_fields(
    monkeypatch,
) -> None:
    monkeypatch.setattr(pdfplumber, "open", lambda _: _Pdf())
    document = TermsDocument(
        document_key="id:00123:terms",
        contest_key="id:00123",
        status=DocumentStatus.DOWNLOADED,
        local_path=str(Path("bases.pdf")),
    )

    processed = extract_pdf_sections(document)
    position = enrich_position_from_document(
        Position(position_key="position-1", contest_key="id:00123"),
        processed,
    )

    assert processed.extracted_fields["page_count"] == 2
    assert processed.extracted_fields["sections"]["perfil_requerido"]["pages"] == [
        1,
        2,
    ]
    assert position.salary == "Gs. 8.500.000"
    assert position.salary_pdf_status == FieldStatus.FOUND
    assert position.vacancies == "2"
    assert position.vacancies_status == FieldStatus.FOUND
    assert position.position_type_budget == "Permanente"
    assert position.position_type_budget_status == FieldStatus.FOUND
    assert position.min_experience_req == (
        "2 años de experiencia en administración de redes."
    )
    assert position.min_experience_status == FieldStatus.FOUND
    assert position.optional_experience_req == "Experiencia en servicios de nube."
    assert position.optional_experience_status == FieldStatus.FOUND


def test_extracts_13470_fields_from_tables_without_assuming_page_number(
    monkeypatch, tmp_path: Path
) -> None:
    page = _Page(
        "1. DESCRIPCIÓN DEL PUESTO\n"
        "Denominación del Auxiliar de Servicio - Chofer Descripción CH-AUX-SERV\n"
        "2. OFERTA SALARIAL\n"
        "3.1 Requerimientos mínimos y opcionales\n",
        tables=[
            [
                ["Denominación del\nPuesto", "Auxiliar de Servicio - Chofer"],
            ],
            [
                [
                    "Salario",
                    "Categoría/Denominación",
                    "FF",
                    "Vacancias",
                    "OG",
                    "Otros Beneficios",
                ],
                [
                    "Gs. 2.900.000\n(guaraníes dos millones novecientos mil)",
                    "G9G/Auxiliar de Servicios",
                    "10",
                    "7 (siete)",
                    "111",
                    "N/A",
                ],
            ],
            [
                [
                    "COMPONENTE",
                    "MÍNIMOS REQUERIDOS",
                    "",
                    "",
                    "OPCIONALES",
                ],
                [
                    "",
                    "Experiencia específica, 3 años en tareas relacionadas al puesto o cargo en el sector público o privado",
                    "",
                    "",
                    "Experiencia general, 3 años o más en el sector público o privado",
                ],
                ["a) EXPERIENCIA", "", "", "", ""],
                ["LABORAL", "", "", "", ""],
            ],
        ],
    )
    monkeypatch.setattr(pdfplumber, "open", lambda _: _Pdf([page]))
    document = TermsDocument(
        document_key="id:13470:terms",
        contest_key="id:13470",
        status=DocumentStatus.DOWNLOADED,
        local_path=str(Path("bases-13470.pdf")),
    )

    processed = extract_pdf_sections(document)
    position = enrich_position_from_document(
        Position(position_key="position-13470", contest_key="id:13470"),
        processed,
    )

    assert processed.extracted_fields["page_count"] == 1
    assert processed.extracted_fields["tables"][0]["page"] == 1
    assert processed.extracted_fields["tables"][0]["section"] == "descripcion_puesto"
    assert processed.extracted_fields["tables"][1]["section"] == "oferta_salarial"
    assert processed.extracted_fields["tables"][2]["section"] == "perfil_requerido"
    assert position.title == "Auxiliar de Servicio - Chofer"
    assert position.position_name == "Auxiliar de Servicio - Chofer"
    assert position.salary == "Gs. 2.900.000"
    assert position.salary_raw == "Gs. 2.900.000"
    assert position.salary_status == PublishedFieldStatus.PUBLISHED
    assert position.salary_pdf_status == FieldStatus.FOUND
    assert position.vacancies == "7 (siete)"
    assert position.vacancies_status == FieldStatus.FOUND
    assert position.position_type_budget == "FF: 10; OG: 111"
    assert position.position_type_budget_status == FieldStatus.FOUND
    assert position.min_experience_req == (
        "Experiencia específica, 3 años en tareas relacionadas al puesto o cargo en el sector público o privado"
    )
    assert position.min_experience_status == FieldStatus.FOUND
    assert position.optional_experience_req == (
        "Experiencia general, 3 años o más en el sector público o privado"
    )
    assert position.optional_experience_status == FieldStatus.FOUND

    contest = Contest(
        official_id="13470",
        title="AUXILIAR DE SERVICIO - CHOFER",
        institution="MINISTERIO DEL INTERIOR",
        status="En Publicación",
        dates_raw=None,
        profile_url="https://portal.test/media/documentos/13470.pdf",
        process_url="https://portal.test/publicaciones/info13470/",
        detail_url="https://portal.test/publicaciones/info13470/",
        listing_page_url="https://portal.test/?page=1",
    )
    frame = build_dataframe(
        "run-13470",
        [contest],
        [position],
        [processed],
        run_status="partial",
    )
    csv_path = write_csv(frame, tmp_path / "positions.csv")
    row = pd.read_csv(csv_path, dtype=str, keep_default_na=False).iloc[0]

    assert row["position_title"] == "Auxiliar de Servicio - Chofer"
    assert row["contest_id"] == "13470"
    assert row["salary"] == "Gs. 2.900.000"
    assert row["vacancies"] == "7 (siete)"
    assert row["budget_type"] == "FF: 10; OG: 111"
    assert row["min_experience"] == position.min_experience_req
    assert row["optional_experience"] == position.optional_experience_req
    assert list(frame.columns) == [
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


def test_salary_table_skips_subheaders_and_extracts_money_and_column_values(
    monkeypatch,
) -> None:
    page = _Page(
        "2. OFERTA SALARIAL\n3. PERFIL REQUERIDO",
        tables=[
            [
                ["", "", "", "Disponibilidad", "", ""],
                ["Salario", "FF", "Vacancias", "", "OG", "Otros Beneficios"],
                ["", "", "de vacancias", "", "", ""],
                ["", "", "", "", "", ""],
                [
                    "G. 2.899.048 (guaraníes dos millones)",
                    "10",
                    "2 (dos)",
                    "Autorización EEN",
                    "144",
                    "N/A",
                ],
            ]
        ],
    )
    monkeypatch.setattr(pdfplumber, "open", lambda _: _Pdf([page]))
    document = TermsDocument(
        document_key="id:12723:terms",
        contest_key="id:12723",
        status=DocumentStatus.DOWNLOADED,
        local_path="salary-table.pdf",
    )

    processed = extract_pdf_sections(document)
    position = enrich_position_from_document(
        Position(position_key="position-12723", contest_key="id:12723"),
        processed,
    )

    assert position.salary == "G. 2.899.048"
    assert position.salary_raw == "G. 2.899.048"
    assert position.salary_status == PublishedFieldStatus.PUBLISHED
    assert position.vacancies == "2 (dos)"
    assert position.position_type_budget == "FF: 10; OG: 144"


def test_salary_and_vacancies_do_not_fall_back_to_column_headings(
    monkeypatch,
) -> None:
    page = _Page(
        "2. OFERTA SALARIAL\nSalario | FF | Vacancias | OG | Otros Beneficios",
        tables=[
            [
                ["Salario", "FF", "Vacancias", "OG", "Otros Beneficios"],
                ["", "", "", "", ""],
            ]
        ],
    )
    monkeypatch.setattr(pdfplumber, "open", lambda _: _Pdf([page]))
    document = TermsDocument(
        document_key="id:headers-only:terms",
        contest_key="id:headers-only",
        status=DocumentStatus.DOWNLOADED,
        local_path="headers-only.pdf",
    )

    processed = extract_pdf_sections(document)
    position = enrich_position_from_document(
        Position(
            position_key="position-headers-only",
            contest_key="id:headers-only",
            salary_raw="FF Vacancias OG Otros Beneficios",
            salary_status=PublishedFieldStatus.PUBLISHED,
            salary="FF Vacancias OG Otros Beneficios",
            salary_pdf_status=FieldStatus.FOUND,
        ),
        processed,
    )

    assert position.salary is None
    assert position.salary_raw is None
    assert position.salary_status == PublishedFieldStatus.NOT_FOUND
    assert position.vacancies is None
    assert position.position_type_budget is None


def test_experience_table_assigns_values_by_category_when_cells_shift(
    monkeypatch,
) -> None:
    minimum = (
        "Experiencia Específica: 4 (cuatro) años de vinculación temporal "
        "con la institución convocante al 31 de diciembre de 2026. (Excluyente)"
    )
    optional = (
        "Experiencia general, de 1 (un) año 6 (seis) meses en el sector "
        "público o privado."
    )
    page = _Page(
        "2. PERFIL REQUERIDO\n2.1 Requerimientos mínimos y opcionales",
        tables=[
            [
                ["", "COMPONENTE", "", "", "MÍNIMOS REQUERIDOS", "", "", "OPCIONALES"],
                [
                    "a) EXPERIENCIA LABORAL",
                    "",
                    "",
                    minimum,
                    "",
                    "",
                    optional,
                    "",
                ],
            ]
        ],
    )
    monkeypatch.setattr(pdfplumber, "open", lambda _: _Pdf([page]))
    document = TermsDocument(
        document_key="id:12691:terms",
        contest_key="id:12691",
        status=DocumentStatus.DOWNLOADED,
        local_path="experience-columns.pdf",
    )

    processed = extract_pdf_sections(document)
    position = enrich_position_from_document(
        Position(position_key="position-12691", contest_key="id:12691"),
        processed,
    )

    assert position.min_experience_req == minimum
    assert position.optional_experience_req == optional
    assert position.min_experience_status == FieldStatus.FOUND
    assert position.optional_experience_status == FieldStatus.FOUND


def test_concatenated_experience_text_splits_specific_and_general_requirements(
    monkeypatch,
) -> None:
    minimum = (
        "Experiencia Específica: 4 (cuatro) años de vinculación temporal "
        "con la institución convocante al 31 de diciembre de 2026. (Excluyente)"
    )
    optional = (
        "Experiencia general, de 1 (un) año 6 (seis) meses en el sector "
        "público o privado."
    )
    page = _Page(
        "2. PERFIL REQUERIDO\n"
        "2.1 Requerimientos mínimos y opcionales\n"
        "a) EXPERIENCIA LABORAL "
        f"{minimum} {optional}"
    )
    monkeypatch.setattr(pdfplumber, "open", lambda _: _Pdf([page]))
    document = TermsDocument(
        document_key="id:concatenated-experience:terms",
        contest_key="id:concatenated-experience",
        status=DocumentStatus.DOWNLOADED,
        local_path="concatenated-experience.pdf",
    )

    processed = extract_pdf_sections(document)
    position = enrich_position_from_document(
        Position(
            position_key="position-concatenated-experience",
            contest_key="id:concatenated-experience",
        ),
        processed,
    )

    assert position.min_experience_req == minimum
    assert position.optional_experience_req == optional
