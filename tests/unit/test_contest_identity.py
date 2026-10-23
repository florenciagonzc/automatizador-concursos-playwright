import pytest

from job_finder.records import (
    Contest,
    build_position_key,
    canonicalize_url,
    deduplicate_contests,
)


def _contest(*, official_id: str | None, detail_url: str | None) -> Contest:
    return Contest(
        official_id=official_id,
        title="Vacante",
        institution="Institución",
        status="En Postulación",
        dates_raw=None,
        profile_url=None,
        process_url=detail_url,
        detail_url=detail_url,
        listing_page_url="https://portal.test/?page=1",
    )


def test_official_identifier_is_contest_identity() -> None:
    assert _contest(
        official_id="00123", detail_url="https://portal.test/detail/123/"
    ).contest_key == "id:00123"


def test_canonical_detail_url_is_fallback_identity() -> None:
    contest = _contest(
        official_id=None,
        detail_url="https://PORTAL.test/detail/123?tracking=ignored",
    )
    assert contest.contest_key == "https://portal.test/detail/123/"
    assert canonicalize_url("https://portal.test/detail/123/?x=1") == contest.contest_key


def test_contest_without_any_identity_is_invalid() -> None:
    with pytest.raises(ValueError, match="official_id or canonical detail_url"):
        _ = _contest(official_id=None, detail_url=None).contest_key


def test_deduplicate_contests_keeps_first_record_and_page_provenance() -> None:
    first = _contest(
        official_id="00123", detail_url="https://portal.test/detail/first/"
    )
    duplicate_id = _contest(
        official_id="00123", detail_url="https://portal.test/detail/other/"
    )
    url_fallback = _contest(
        official_id=None, detail_url="https://portal.test/detail/123?source=list"
    )
    duplicate_url = _contest(
        official_id=None, detail_url="https://portal.test/detail/123/"
    )

    unique = deduplicate_contests(
        [first, duplicate_id, url_fallback, duplicate_url]
    )

    assert unique == [first, url_fallback]


@pytest.mark.parametrize(
    ("arguments", "expected"),
    [
        ({"contest_key": "id:contest", "official_id": "0042"}, "id:0042"),
        (
            {
                "contest_key": "id:contest",
                "detail_url": "https://portal.test/position/42?tracking=x",
            },
            "https://portal.test/position/42/",
        ),
        (
            {"contest_key": "id:contest", "occurrence_ordinal": 2},
            "id:contest:position:2",
        ),
    ],
)
def test_position_identity_uses_stable_source_or_occurrence_key(
    arguments: dict[str, object], expected: str
) -> None:
    assert build_position_key(**arguments) == expected
