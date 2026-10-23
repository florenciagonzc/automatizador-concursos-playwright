import re
import unicodedata
from dataclasses import replace
from urllib.parse import urljoin, urlsplit

from playwright.sync_api import Locator, Page

from job_finder.errors import ContestIdentityError, DetailError, PageStructureError
from job_finder.records import (
    Contest,
    DocumentStatus,
    FieldStatus,
    Position,
    PublishedFieldStatus,
    TermsDocument,
    build_position_key,
)

_OFFICIAL_ID = re.compile(r"\bID\s+([A-Za-z0-9_-]+)\b", re.IGNORECASE)
_EXCLUDED_CONTEST_LABEL = re.compile(
    r"\b(?:encuadramiento|encuadernamiento)\b",
    re.IGNORECASE,
)
_DATE_LABELS = re.compile(
    r"(Inicio de Postulación|Fin de Postulación)\s*:\s*([^\n]+)", re.IGNORECASE
)
_PROFILE_LABELS = {
    "education": (
        "formacion academica",
        "educacion",
        "nivel academico",
        "requisito academico",
    ),
    "knowledge": (
        "conocimientos",
        "conocimientos tecnicos",
        "competencias tecnicas",
        "habilidades tecnicas",
    ),
    "experience": ("experiencia", "experiencia laboral", "experiencia profesional"),
    "duties": ("funciones", "responsabilidades", "tareas principales"),
    "conditions": (
        "condiciones de postulacion",
        "requisitos de postulacion",
        "documentos requeridos",
    ),
}
_IT_TERMS = re.compile(
    r"\b(?:informatica|ingenieria informatica|sistemas informaticos|"
    r"tecnologias? de la informacion|software|programacion|programador|"
    r"desarrollo de sistemas|bases? de datos|redes? informaticas?|"
    r"administracion de redes|servidores?|ciberseguridad|"
    r"soporte tecnico|infraestructura tecnologica|teleinformatica)\b",
    re.IGNORECASE,
)
_NON_IT_TERMS = re.compile(
    r"\b(?:abogacia|derecho administrativo|contabilidad|contador|"
    r"recursos humanos|enfermeria|medicina|odontologia|"
    r"ingenieria civil|trabajo social|docencia)\b",
    re.IGNORECASE,
)
_NO_EXPERIENCE = re.compile(
    r"\b(?:no\s+(?:se\s+)?requiere\s+experiencia|sin\s+experiencia"
    r"(?:\s+previa|\s+laboral)?|experiencia\s+no\s+requerida)\b",
    re.IGNORECASE,
)
_REQUIRED_EXPERIENCE = re.compile(
    r"\b(?:experiencia\s+(?:laboral\s+)?(?:minima|minimo|comprobable|requerida)"
    r"|(?:minimo|al\s+menos)\s+\d+\s+anos?\s+de\s+experiencia"
    r"|\d+\s+anos?\s+de\s+experiencia|requiere\s+experiencia)\b",
    re.IGNORECASE,
)
_CURRENCY_AMOUNT = re.compile(
    r"\b(?:Gs\.?|G\.)\s*[\d.]+(?:,\d+)?",
    re.IGNORECASE,
)
_VACANCY_COUNT = re.compile(r"^\d+\b")
_EXPERIENCE_CATEGORY = re.compile(
    r"\bexperiencia\s+(espec[ií]fica|general)\s*[:,]\s*",
    re.IGNORECASE,
)


def _normalize_source_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        character
        for character in decomposed
        if not unicodedata.combining(character)
    )
    return re.sub(r"\s+", " ", without_marks).strip().lower()


def _profile_subsection(profile: str | None, labels: tuple[str, ...]) -> tuple[str | None, bool]:
    if not profile:
        return None, False
    normalized_labels = {_normalize_source_text(label) for label in labels}
    all_labels = {
        _normalize_source_text(label)
        for group in _PROFILE_LABELS.values()
        for label in group
    }
    lines = profile.splitlines()
    selected: list[str] = []
    active = False
    found = False
    for line in lines:
        normalized_line = _normalize_source_text(line)
        label_match = next(
            (
                label
                for label in all_labels
                if normalized_line == label
                or normalized_line.startswith(f"{label}:")
                or normalized_line.startswith(f"{label} -")
            ),
            None,
        )
        if label_match:
            active = label_match in normalized_labels
            found = found or active
            suffix = line[len(label_match) :].lstrip(" :-\t")
            if active and suffix:
                selected.append(suffix)
            continue
        if active and line.strip():
            selected.append(line.strip())
    value = "\n".join(selected).strip() or None
    return value, found


def _strip_explicit_label(value: str | None, labels: tuple[str, ...]) -> str | None:
    if not value:
        return None
    normalized_labels = {_normalize_source_text(label) for label in labels}
    lines = value.splitlines()
    first = lines[0]
    normalized_first = _normalize_source_text(first)
    for label in normalized_labels:
        if normalized_first.startswith(f"{label}:") or normalized_first.startswith(
            f"{label} -"
        ):
            lines[0] = first[len(label) :].lstrip(" :-\t")
            return "\n".join(lines).strip() or None
    return value


def _extract_pdf_value(section: str | None, labels: tuple[str, ...]) -> str | None:
    if not section:
        return None
    normalized_labels = tuple(
        sorted(
            (_normalize_source_text(label) for label in labels),
            key=len,
            reverse=True,
        )
    )
    lines = section.splitlines()
    for index, line in enumerate(lines):
        source_line = re.sub(r"^\s*[-*•▪]\s*", "", line).strip()
        normalized_line = _normalize_source_text(source_line)
        for label in normalized_labels:
            if normalized_line == label:
                next_value = next(
                    (
                        candidate.strip()
                        for candidate in lines[index + 1 :]
                        if candidate.strip()
                    ),
                    None,
                )
                if next_value and not re.match(
                    r"^(?:[a-z]\s*[\).:-]|\d+\s*[.)-]?\s*"
                    r"(?:descripcion del puesto|oferta salarial|perfil requerido))",
                    next_value,
                    re.IGNORECASE,
                ):
                    return next_value
            if normalized_line.startswith(label) and len(source_line) > len(label):
                separator = source_line[len(label)]
                if separator.isspace() or separator in ":|–—-\t":
                    value = source_line[len(label) :].lstrip(" :|–—-\t").strip()
                else:
                    value = ""
                if value:
                    return value
    return None


def _pdf_tables(document: TermsDocument) -> list[list[list[str]]]:
    tables = document.extracted_fields.get("tables", [])
    if not isinstance(tables, list):
        raise ValueError("PDF table evidence must be a list")
    parsed: list[list[list[str]]] = []
    for table in tables:
        if not isinstance(table, dict):
            raise ValueError("each PDF table must be a mapping")
        rows = table.get("rows")
        if not isinstance(rows, list):
            raise ValueError("PDF table rows must be a list")
        parsed_rows: list[list[str]] = []
        for row in rows:
            if not isinstance(row, list):
                raise ValueError("PDF table row must be a list")
            if not all(isinstance(cell, str) for cell in row):
                raise ValueError("PDF table cells must be strings")
            parsed_rows.append(row)
        parsed.append(parsed_rows)
    return parsed


def _table_cell(value: str) -> str:
    return " ".join(value.split()).strip()


def _extract_currency_amount(value: str | None) -> str | None:
    if not value:
        return None
    match = _CURRENCY_AMOUNT.search(value)
    return match.group(0).strip() if match else None


def _find_table_label_value(
    tables: list[list[list[str]]],
    labels: tuple[str, ...],
) -> str | None:
    normalized_labels = {_normalize_source_text(label) for label in labels}
    for table in tables:
        for row in table:
            for index, cell in enumerate(row):
                normalized_cell = _normalize_source_text(
                    _table_cell(cell).replace("/", " ")
                )
                matched = next(
                    (
                        label
                        for label in normalized_labels
                        if normalized_cell == label
                        or normalized_cell.startswith(f"{label}:")
                    ),
                    None,
                )
                if matched is None:
                    continue
                for candidate in row[index + 1 :]:
                    value = _table_cell(candidate)
                    if value:
                        return value
    return None


def _salary_table_fields(
    tables: list[list[list[str]]],
) -> dict[str, str]:
    fallback_fields: dict[str, str] = {}
    for table in tables:
        for header_index, row in enumerate(table):
            normalized = [_normalize_source_text(_table_cell(cell)) for cell in row]
            salary_index = next(
                (i for i, cell in enumerate(normalized) if cell == "salario"),
                None,
            )
            vacancies_index = next(
                (
                    i
                    for i, cell in enumerate(normalized)
                    if cell in {"vacancia", "vacancias", "vacantes"}
                ),
                None,
            )
            ff_index = next(
                (i for i, cell in enumerate(normalized) if cell == "ff"),
                None,
            )
            og_index = next(
                (i for i, cell in enumerate(normalized) if cell == "og"),
                None,
            )
            if salary_index is None or vacancies_index is None:
                continue

            def value_at(row: list[str], index: int | None) -> str | None:
                if index is None or index >= len(row):
                    return None
                value = _table_cell(row[index])
                return value or None

            fields: dict[str, str] = {}
            for value_row in table[header_index + 1 :]:
                salary = _extract_currency_amount(value_at(value_row, salary_index))
                vacancies_cell = value_at(value_row, vacancies_index)
                vacancies = (
                    vacancies_cell
                    if vacancies_cell and _VACANCY_COUNT.match(vacancies_cell)
                    else None
                )
                budget_parts = []
                for label, index in (("FF", ff_index), ("OG", og_index)):
                    value = value_at(value_row, index)
                    if value and re.match(r"^\d+\b", value):
                        budget_parts.append(f"{label}: {value}")
                if salary:
                    fields["salary"] = salary
                if vacancies:
                    fields["vacancies"] = vacancies
                if budget_parts and "position_type_budget" not in fields:
                    fields["position_type_budget"] = "; ".join(budget_parts)
                if salary:
                    return fields
                if fields and not fallback_fields:
                    fallback_fields = fields
    return fallback_fields


def _experience_table_fields(
    tables: list[list[list[str]]],
) -> tuple[str | None, str | None]:
    for table in tables:
        table_text = _normalize_source_text(
            " ".join(_table_cell(cell) for row in table for cell in row)
        )
        if "experiencia laboral" not in table_text:
            continue

        minimum_index: int | None = None
        optional_index: int | None = None
        header_index: int | None = None
        for row_index, row in enumerate(table):
            normalized = [_normalize_source_text(_table_cell(cell)) for cell in row]
            candidate_minimum = next(
                (
                    i
                    for i, cell in enumerate(normalized)
                    if "minimos requeridos" in cell
                ),
                None,
            )
            candidate_optional = next(
                (
                    i
                    for i, cell in enumerate(normalized)
                    if cell == "opcionales"
                ),
                None,
            )
            if candidate_minimum is not None and candidate_optional is not None:
                minimum_index = candidate_minimum
                optional_index = candidate_optional
                header_index = row_index
                break
        if header_index is None or minimum_index is None or optional_index is None:
            continue

        minimum_values: list[str] = []
        optional_values: list[str] = []
        for row in table[header_index + 1 :]:
            row_text = " ".join(_table_cell(cell) for cell in row if _table_cell(cell))
            categorized_minimum, categorized_optional = _experience_category_fragments(
                row_text
            )
            if categorized_minimum:
                minimum_values.append(categorized_minimum)
            if categorized_optional:
                optional_values.append(categorized_optional)
            if categorized_minimum or categorized_optional:
                continue

            minimum_cell = (
                _table_cell(row[minimum_index])
                if minimum_index < len(row)
                else ""
            )
            optional_cell = (
                _table_cell(row[optional_index])
                if optional_index < len(row)
                else ""
            )
            if minimum_cell:
                minimum_values.append(minimum_cell)
            if optional_cell:
                optional_values.append(optional_cell)
        minimum = "\n".join(dict.fromkeys(minimum_values)) or None
        optional = "\n".join(dict.fromkeys(optional_values)) or None
        return minimum, optional
    return None, None


def _experience_category_fragments(value: str) -> tuple[str | None, str | None]:
    matches = list(_EXPERIENCE_CATEGORY.finditer(value))
    fragments: dict[str, list[str]] = {"especifica": [], "general": []}
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(value)
        category = _normalize_source_text(match.group(1))
        fragment = re.sub(r"\s+", " ", value[match.start() : end]).strip(" \t\r\n|;")
        if fragment:
            fragments[category].append(fragment)
    minimum = " ".join(dict.fromkeys(fragments["especifica"])) or None
    optional = " ".join(dict.fromkeys(fragments["general"])) or None
    return minimum, optional


def _experience_subsections(
    profile: str | None,
) -> tuple[str | None, bool, str | None, bool, bool]:
    if not profile:
        return None, False, None, False, False
    categorized_minimum, categorized_optional = _experience_category_fragments(
        profile
    )
    in_experience = False
    experience_found = False
    active: str | None = None
    selected: dict[str, list[str]] = {"minimum": [], "optional": []}
    found: set[str] = set()
    for raw_line in profile.splitlines():
        line = re.sub(r"^\s*[-*•▪]\s*", "", raw_line).strip()
        normalized = _normalize_source_text(line)
        if re.match(
            r"^(?:[a-z]\s*[\).:-]\s*)?experiencia laboral\b", normalized
        ):
            in_experience = True
            experience_found = True
            active = None
            continue
        if in_experience and re.match(
            r"^(?:[a-z]\s*[\).:-]\s*)?(?:formacion academica|educacion|"
            r"conocimientos|funciones|responsabilidades|condiciones de postulacion)\b",
            normalized,
        ):
            in_experience = False
            active = None
        if re.match(
            r"^(?:minimos?\s+requeridos?|requisitos?\s+minimos?)\b", normalized
        ) and (in_experience or experience_found):
            active = "minimum"
            found.add(active)
            suffix = re.sub(r"^[^:|–—-]+[:|–—-]\s*", "", line, count=1).strip()
            if suffix:
                selected[active].append(suffix)
            continue
        if re.match(
            r"^(?:opcionales?|requisitos?\s+opcionales?)\b", normalized
        ) and (in_experience or experience_found):
            active = "optional"
            found.add(active)
            suffix = re.sub(r"^[^:|–—-]+[:|–—-]\s*", "", line, count=1).strip()
            if suffix:
                selected[active].append(suffix)
            continue
        if not in_experience:
            continue
        if active and line.strip():
            selected[active].append(line.strip())

    minimum = (
        "\n".join(dict.fromkeys(selected["minimum"])).strip()
        or categorized_minimum
    )
    optional = (
        "\n".join(dict.fromkeys(selected["optional"])).strip()
        or categorized_optional
    )
    return (
        minimum,
        "minimum" in found or categorized_minimum is not None,
        optional,
        "optional" in found or categorized_optional is not None,
        experience_found,
    )


def enrich_position_from_document(
    position: Position,
    document: TermsDocument,
) -> Position:
    if document.status in {
        DocumentStatus.DOWNLOAD_FAILED,
        DocumentStatus.PROCESSING_FAILED,
        DocumentStatus.REVIEW_REQUIRED,
    }:
        return replace(
            position,
            experience_requirement="unreadable",
            salary_pdf_status=FieldStatus.UNREADABLE,
            vacancies_status=FieldStatus.UNREADABLE,
            position_type_budget_status=FieldStatus.UNREADABLE,
            education_status=FieldStatus.UNREADABLE,
            knowledge_status=FieldStatus.UNREADABLE,
            duties_status=FieldStatus.UNREADABLE,
            application_conditions_status=FieldStatus.UNREADABLE,
            min_experience_status=FieldStatus.UNREADABLE,
            optional_experience_status=FieldStatus.UNREADABLE,
        )

    sections = document.extracted_fields.get("sections", {})
    if not isinstance(sections, dict):
        raise ValueError("processed PDF section data must be a mapping")

    def section_text(key: str) -> str | None:
        section = sections.get(key, {})
        if not isinstance(section, dict):
            raise ValueError(f"PDF section {key} must be a mapping")
        text = section.get("text")
        return text.strip() if isinstance(text, str) and text.strip() else None

    def parsed_pdf_status(value: str | None, key: str) -> FieldStatus:
        if value:
            return FieldStatus.FOUND
        section = sections.get(key, {})
        if not isinstance(section, dict):
            raise ValueError(f"PDF section {key} must be a mapping")
        if section.get("status") in {"found", "not_stated"}:
            return FieldStatus.NOT_STATED
        return FieldStatus.NOT_FOUND

    description = section_text("descripcion_puesto")
    salary_section = section_text("oferta_salarial")
    profile = section_text("perfil_requerido")
    all_text = document.extracted_fields.get("all_text", "")
    table_text = document.extracted_fields.get("table_text", "")
    if not isinstance(all_text, str) or not isinstance(table_text, str):
        raise ValueError("PDF text and table evidence must be strings")
    full_pdf_text = "\n".join(
        part for part in (all_text, table_text) if part.strip()
    )
    tables = _pdf_tables(document)
    table_salary_fields = _salary_table_fields(tables)
    salary_source = "\n".join(
        part for part in (salary_section or "", table_text, all_text) if part.strip()
    )
    table_position_name = _find_table_label_value(
        tables,
        (
            "denominacion del puesto",
            "denominacion del cargo",
            "nombre del puesto",
        ),
    )
    table_min_experience, table_optional_experience = _experience_table_fields(tables)
    salary = (
        table_salary_fields.get("salary")
        or _extract_currency_amount(salary_section)
        or _extract_currency_amount(position.salary)
        or _extract_currency_amount(position.salary_raw)
    )
    vacancies = table_salary_fields.get("vacancies") or _extract_pdf_value(
        salary_section or salary_source,
        (
            "vacantes",
            "vacancia",
            "vacancias",
            "cantidad de vacantes",
            "cantidad de vacancias",
        ),
    )
    if vacancies and not _VACANCY_COUNT.match(vacancies):
        vacancies = None
    position_type_budget = table_salary_fields.get(
        "position_type_budget"
    ) or _extract_pdf_value(
        salary_section or salary_source,
        (
            "tipo de puesto",
            "tipo de presupuesto",
            "tipo de puesto/presupuesto",
            "tipo de puesto / presupuesto",
            "tipo puesto/presupuesto",
            "presupuesto",
            "categoria presupuestaria",
        ),
    )
    (
        text_min_experience,
        text_min_found,
        text_optional_experience,
        text_optional_found,
        experience_section_found,
    ) = _experience_subsections(
        profile or all_text
    )
    min_experience_req = table_min_experience or text_min_experience
    optional_experience_req = table_optional_experience or text_optional_experience
    min_experience_found = bool(table_min_experience) or text_min_found
    optional_experience_found = bool(table_optional_experience) or text_optional_found
    position_name = table_position_name or _extract_pdf_value(
        full_pdf_text,
        (
            "denominacion del puesto",
            "denominacion del cargo",
            "nombre del puesto",
        ),
    )
    education, education_heading = _profile_subsection(
        profile, _PROFILE_LABELS["education"]
    )
    knowledge, knowledge_heading = _profile_subsection(
        profile, _PROFILE_LABELS["knowledge"]
    )
    profile_duties, duties_heading = _profile_subsection(
        profile, _PROFILE_LABELS["duties"]
    )
    conditions, conditions_heading = _profile_subsection(
        profile, _PROFILE_LABELS["conditions"]
    )
    profile_text = profile or ""
    normalized_profile = _normalize_source_text(profile_text)
    if _NO_EXPERIENCE.search(normalized_profile):
        experience = "not_required"
    elif _REQUIRED_EXPERIENCE.search(normalized_profile):
        experience = "required"
    elif re.search(r"\bexperiencia\b", normalized_profile, re.IGNORECASE):
        experience = "ambiguous"
    elif profile:
        experience = "not_stated"
    else:
        experience = "not_found"

    duties = profile_duties or _strip_explicit_label(
        description, _PROFILE_LABELS["duties"]
    )
    it_evidence = [
        (field_name, value)
        for field_name, value in (
            ("education", education),
            ("knowledge", knowledge),
            ("duties", duties),
        )
        if value and _IT_TERMS.search(_normalize_source_text(value))
    ]
    non_it_evidence = next(
        (
            (field_name, value)
            for field_name, value in (
                ("education", education),
                ("knowledge", knowledge),
                ("duties", duties),
            )
            if value and _NON_IT_TERMS.search(_normalize_source_text(value))
        ),
        None,
    )
    if it_evidence:
        relevance = "relevant"
        relevance_evidence = "; ".join(
            f"{field_name}: {value}" for field_name, value in it_evidence
        )
    elif non_it_evidence:
        relevance = "not_relevant"
        relevance_evidence = f"{non_it_evidence[0]}: {non_it_evidence[1]}"
    else:
        relevance = "indeterminate"
        relevance_evidence = None

    salary_raw = salary
    salary_status = position.salary_status
    if salary:
        salary_status = PublishedFieldStatus.PUBLISHED
    else:
        salary_section_status = sections.get("oferta_salarial", {}).get("status")
        salary_status = (
            PublishedFieldStatus.NOT_STATED
            if salary_section_status == "not_stated"
            else PublishedFieldStatus.NOT_FOUND
            if salary_section_status == "found"
            or position.salary_status == PublishedFieldStatus.PUBLISHED
            else position.salary_status
        )

    def field_status(value: str | None, heading_present: bool, section_exists: bool) -> FieldStatus:
        if value:
            return FieldStatus.FOUND
        if heading_present:
            return FieldStatus.NOT_STATED
        if section_exists:
            return FieldStatus.NOT_FOUND
        return FieldStatus.NOT_FOUND

    min_experience_status = (
        FieldStatus.FOUND
        if min_experience_req
        else FieldStatus.NOT_STATED
        if min_experience_found or experience_section_found or profile
        else FieldStatus.NOT_FOUND
    )
    optional_experience_status = (
        FieldStatus.FOUND
        if optional_experience_req
        else FieldStatus.NOT_STATED
        if optional_experience_found or experience_section_found or profile
        else FieldStatus.NOT_FOUND
    )

    return replace(
        position,
        title=position_name or position.title,
        position_name=position_name or position.position_name,
        salary_raw=salary_raw,
        salary_status=salary_status,
        salary=salary,
        salary_pdf_status=parsed_pdf_status(
            salary, "oferta_salarial"
        ),
        vacancies=vacancies or position.vacancies,
        vacancies_status=parsed_pdf_status(
            vacancies or position.vacancies, "oferta_salarial"
        ),
        position_type_budget=position_type_budget or position.position_type_budget,
        position_type_budget_status=parsed_pdf_status(
            position_type_budget or position.position_type_budget, "oferta_salarial"
        ),
        min_experience_req=min_experience_req,
        min_experience_status=min_experience_status,
        optional_experience_req=optional_experience_req,
        optional_experience_status=optional_experience_status,
        education_raw=education,
        education_status=field_status(education, education_heading, bool(profile)),
        knowledge_raw=knowledge,
        knowledge_status=field_status(knowledge, knowledge_heading, bool(profile)),
        duties_raw=duties,
        duties_status=field_status(duties, duties_heading, bool(description or profile)),
        application_conditions_raw=conditions,
        application_conditions_status=field_status(
            conditions, conditions_heading, bool(profile)
        ),
        experience_requirement=experience,
        ti_relevance=relevance,
        ti_relevance_evidence=relevance_evidence,
    )


def _text(locator: Locator) -> str | None:
    if locator.count() == 0:
        return None
    value = locator.first.inner_text().strip()
    return value or None


def _same_origin_url(base_url: str, value: str | None) -> str | None:
    if not value:
        return None
    absolute = urljoin(base_url, value.strip())
    if urlsplit(absolute).netloc.lower() != urlsplit(base_url).netloc.lower():
        return None
    return absolute


def _profile_pdf_url(card: Locator, base_url: str) -> str | None:
    controls = card.locator("a, button")
    for index in range(controls.count()):
        control = controls.nth(index)
        value = control.get_attribute("href") or control.get_attribute("data-url")
        absolute_url = _same_origin_url(base_url, value)
        if absolute_url is None:
            continue

        path = urlsplit(absolute_url).path.lower()
        is_official_document = path.startswith("/media/documentos/")
        is_pdf = path.endswith(".pdf")
        text = " ".join(control.inner_text().split())
        if text == "Ver perfil" and (is_official_document or is_pdf):
            return absolute_url
    return None


def _card_dates(card: Locator) -> str | None:
    if card.locator(".concurso-footer").count() == 0:
        return None
    footer_text = card.locator(".concurso-footer").inner_text()
    values = _DATE_LABELS.findall(footer_text)
    if not values:
        return None
    return "; ".join(f"{label}: {value.strip()}" for label, value in values)


def extract_contests(page: Page, listing_page_url: str, base_url: str) -> list[Contest]:
    total_count = _text(page.locator("#total-count"))
    cards = page.locator("article.concurso-card")
    card_count = cards.count()

    if total_count is None:
        raise PageStructureError(
            "Listing count marker #total-count is missing",
            target=listing_page_url,
        )

    total_match = re.search(r"\d+", total_count.replace(".", ""))
    if card_count == 0 and total_match and int(total_match.group()) > 0:
        raise PageStructureError(
            "Portal reports contests but no listing cards were found",
            target=listing_page_url,
        )

    contests: list[Contest] = []
    for index in range(card_count):
        card = cards.nth(index)
        official_text = _text(card.locator(".concurso-id"))
        id_match = _OFFICIAL_ID.search(official_text or "")
        official_id = id_match.group(1) if id_match else None

        process_link = card.locator("a.concurso-ver-detalle[href]")
        process_raw = (
            process_link.first.get_attribute("href") if process_link.count() else None
        )
        process_url = _same_origin_url(base_url, process_raw)

        skip_reason = (
            "non_vacancy_encuadramiento"
            if _EXCLUDED_CONTEST_LABEL.search(card.inner_text())
            else None
        )
        profile_url = None if skip_reason else _profile_pdf_url(card, base_url)
        position_name = _listing_position_value(
            card,
            '[data-field="position-name"], .position-name, .denominacion-puesto',
            re.compile(
                r"^(?:denominaci[oó]n(?:\s+del\s+puesto)?|nombre\s+del\s+puesto)\s*[:\-]\s*(.+)$",
                re.IGNORECASE,
            ),
        )
        position_code = _listing_position_value(
            card,
            '[data-field="position-code"], .position-code, .codigo-puesto',
            re.compile(
                r"^(?:c[oó]digo(?:\s+del\s+puesto)?|c[oó]digo\s+de\s+puesto)\s*[:\-]\s*(.+)$",
                re.IGNORECASE,
            ),
        )

        contest = Contest(
            official_id=official_id,
            title=_text(card.locator(".concurso-titulo")),
            institution=_text(card.locator(".info-value-entidad")),
            status=_text(card.locator(".pill-estado")),
            dates_raw=_card_dates(card),
            profile_url=profile_url,
            process_url=process_url,
            detail_url=process_url,
            listing_page_url=listing_page_url,
            skip_reason=skip_reason,
            position_name=position_name,
            position_code=position_code,
        )
        try:
            contest.contest_key
        except ValueError as exc:
            raise ContestIdentityError(
                f"Contest card {index + 1} has neither an official ID nor a detail URL",
                target=listing_page_url,
                cause=exc,
            ) from exc
        contests.append(contest)
    return contests


def _position_value(card: Locator, selectors: str) -> tuple[str | None, bool]:
    locator = card.locator(selectors)
    if locator.count() == 0:
        return None, False
    value = locator.first.inner_text().strip()
    return (value or None), True


def _listing_position_value(
    card: Locator,
    selectors: str,
    label_pattern: re.Pattern[str],
) -> str | None:
    locator = card.locator(selectors)
    if locator.count():
        value = locator.first.inner_text().strip()
        if value:
            match = label_pattern.match(value)
            return (match.group(1).strip() if match else value) or None
    for line in card.inner_text().splitlines():
        match = label_pattern.match(line.strip())
        if match and match.group(1).strip():
            return match.group(1).strip()
    return None


def extract_positions(
    page: Page,
    contest: Contest,
    detail_url: str,
) -> list[Position]:
    cards = page.locator("article.position-card, [data-position-id]")
    if cards.count() == 0:
        raise DetailError(
            "Contest detail contains no recognizable position cards",
            target=detail_url,
        )

    positions: list[Position] = []
    for index in range(cards.count()):
        card = cards.nth(index)
        official_id = card.get_attribute("data-position-id")
        raw_detail_url = card.locator("a.position-detail-link[href]")
        position_detail_url = (
            _same_origin_url(
                detail_url,
                raw_detail_url.first.get_attribute("href"),
            )
            if raw_detail_url.count()
            else detail_url
        )
        position_key = build_position_key(
            contest_key=contest.contest_key,
            official_id=official_id,
            detail_url=position_detail_url if raw_detail_url.count() else None,
            occurrence_ordinal=index + 1,
        )
        salary_raw, salary_present = _position_value(
            card, '[data-field="salary"], .position-salary'
        )
        deadline_raw, deadline_present = _position_value(
            card, '[data-field="deadline"], .position-deadline'
        )
        positions.append(
            Position(
                position_key=position_key,
                contest_key=contest.contest_key,
                title=_text(card.locator(".position-title")),
                position_name=contest.position_name,
                position_code=contest.position_code,
                institution=_text(card.locator(".position-institution")),
                salary_raw=salary_raw,
                salary_status=(
                    PublishedFieldStatus.PUBLISHED
                    if salary_raw
                    else PublishedFieldStatus.NOT_STATED
                    if salary_present
                    else PublishedFieldStatus.NOT_FOUND
                ),
                deadline_raw=deadline_raw,
                deadline_status=(
                    PublishedFieldStatus.PUBLISHED
                    if deadline_raw
                    else PublishedFieldStatus.NOT_STATED
                    if deadline_present
                    else PublishedFieldStatus.NOT_FOUND
                ),
                detail_url=position_detail_url,
            )
        )
    return positions


def next_page_url(page: Page, current_url: str, base_url: str) -> str | None:
    pager = page.locator("nav.pager")
    if pager.count() == 0:
        raise PageStructureError(
            "Pagination marker nav.pager is missing",
            target=current_url,
        )
    next_link = page.locator(
        'nav.pager a.js-page-link[aria-label="Ir a la página siguiente"]'
    )
    if next_link.count() == 0:
        pager_text = pager.inner_text().strip()
        page_match = re.search(r"\b(\d+)\s+de\s+(\d+)\b", pager_text, re.IGNORECASE)
        if page_match and page_match.group(1) == page_match.group(2):
            return None
        raise PageStructureError(
            "Next-page link is absent without an explicit last-page indicator",
            target=current_url,
        )
    href = next_link.first.get_attribute("href")
    next_url = _same_origin_url(base_url, href)
    if next_url is None:
        raise PageStructureError(
            "Next-page link is missing a same-origin destination",
            target=current_url,
        )
    return next_url
