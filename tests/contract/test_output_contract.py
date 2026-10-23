import csv
from pathlib import Path

import pandas as pd

from job_finder.export import (
    CSV_COLUMNS,
    build_dataframe,
    build_position_records,
    write_csv,
)
from job_finder.records import Contest, DocumentStatus, Position, TermsDocument

CONTRACT = (
    Path(__file__).parents[2]
    / "specs/001-concursa-vacancy-search/contracts/output-contract.md"
)


def _records(*, document_position: str | None = "position-1"):
    contest = Contest(
        official_id="00123",
        title='Analista, "Plataformas"',
        position_name="Analista de Plataformas",
        position_code="AP-01",
        institution="Ministerio de Prueba",
        status="En Postulación",
        dates_raw=None,
        profile_url="https://portal.test/media/documentos/bases.pdf",
        process_url="https://portal.test/detail/123/",
        detail_url="https://portal.test/detail/123/",
        listing_page_url="https://portal.test/?page=1",
    )
    position = Position(
        position_key="position-1",
        contest_key=contest.contest_key,
        title="Analista, \"Plataformas\"",
        position_name=contest.position_name,
        position_code=contest.position_code,
        institution=contest.institution,
        salary_raw="Gs. 8.500.000",
        salary_status="published",
        salary="Gs. 8.500.000",
        salary_pdf_status="found",
        vacancies="2",
        vacancies_status="found",
        position_type_budget="Permanente",
        position_type_budget_status="found",
        min_experience_req="2 años de experiencia",
        min_experience_status="found",
        optional_experience_req="Experiencia en nube",
        optional_experience_status="found",
        deadline_raw="30/11/2026",
        deadline_status="published",
        detail_url=contest.detail_url,
        ti_relevance="relevant",
        ti_relevance_evidence="Perfil: Ingeniería Informática",
    )
    document = TermsDocument(
        document_key="id:00123:terms",
        contest_key=contest.contest_key,
        position_key=document_position,
        status=DocumentStatus.PROCESSED,
        source_url=contest.profile_url,
        local_path="data/tmp/run-1/pdf/bases.pdf",
        retrieved_at="2026-10-23T00:00:00+00:00",
        sha256="a" * 64,
        extracted_fields={
            "native_text_status": "available",
            "page_count": 1,
            "sections": {},
        },
    )
    return contest, position, document


def test_fixed_compact_columns_match_contract_and_preserve_values() -> None:
    contest, position, document = _records()

    frame = build_dataframe(
        "run-1",
        [contest],
        [position],
        [document],
        run_status="complete",
    )

    assert CSV_COLUMNS == [
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
    assert list(frame.columns) == CSV_COLUMNS
    assert frame.loc[0, "contest_id"] == "00123"
    assert frame.loc[0, "pdf_url"] == contest.profile_url
    assert frame.loc[0, "contest_url"] == contest.detail_url
    assert frame.loc[0, "salary"] == "Gs. 8.500.000"
    assert frame.loc[0, "vacancies"] == "2"
    assert frame.loc[0, "min_experience"] == "2 años de experiencia"
    assert frame.loc[0, "optional_experience"] == "Experiencia en nube"
    assert not any(
        column.endswith(("_status", "_raw"))
        or column.startswith(("ti_relevance_", "document_"))
        for column in frame.columns
    )
    assert CONTRACT.exists()


def test_csv_round_trip_has_utf8_quotes_fixed_header_and_no_index(
    tmp_path: Path,
) -> None:
    contest, position, document = _records()
    frame = build_dataframe(
        "run-1",
        [contest],
        [position],
        [document],
        run_status="partial",
    )
    path = write_csv(frame, tmp_path / "data/exports/run-1/positions.csv")

    raw = path.read_text(encoding="utf-8")
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    loaded = pd.read_csv(path, dtype=str, keep_default_na=False)

    assert rows[0] == CSV_COLUMNS
    assert len(rows) == 2
    assert rows[1][0] == "00123"
    assert '"Analista, ""Plataformas"""' in raw
    assert "Unnamed: 0" not in raw
    assert loaded.loc[0, "position_title"] == 'Analista, "Plataformas"'
    assert loaded.loc[0, "budget_type"] == "Permanente"


def test_empty_export_keeps_fixed_header_and_empty_cells(tmp_path: Path) -> None:
    frame = build_dataframe("run-empty", [], [], [], run_status="complete")
    path = write_csv(frame, tmp_path / "empty.csv")
    loaded = pd.read_csv(path, dtype=str, keep_default_na=False)

    assert list(loaded.columns) == CSV_COLUMNS
    assert loaded.empty
    assert len(path.read_text(encoding="utf-8").splitlines()) == 1


def test_document_join_is_by_contest_identity_for_multiple_positions() -> None:
    contest, position, document = _records(document_position=None)
    second = Position(
        position_key="position-2",
        contest_key=contest.contest_key,
        title="Técnico de Sistemas",
    )

    frame = build_dataframe(
        "run-1",
        [contest],
        [position, second],
        [document],
        run_status="partial",
    )

    records = build_position_records(
        "run-1",
        [contest],
        [position, second],
        [document],
        run_status="partial",
    )
    assert len(frame) == len(records) == 2
    assert [record["document_status"] for record in records] == [
        "processed",
        "processed",
    ]
    assert [record["position_key"] for record in records] == [
        "position-1",
        "position-2",
    ]


def test_non_it_position_remains_in_csv_with_its_classification(
    tmp_path: Path,
) -> None:
    contest, position, document = _records()
    non_it_position = Position(
        position_key=position.position_key,
        contest_key=position.contest_key,
        title=position.title,
        institution=position.institution,
        ti_relevance="not_relevant",
        ti_relevance_evidence="education: Contabilidad",
    )
    frame = build_dataframe(
        "run-1",
        [contest],
        [non_it_position],
        [document],
        run_status="complete",
    )
    path = write_csv(frame, tmp_path / "positions.csv")
    loaded = pd.read_csv(path, dtype=str, keep_default_na=False)

    assert len(loaded) == 1
    assert loaded.loc[0, "contest_id"] == contest.official_id
    assert "ti_relevance" not in loaded.columns
