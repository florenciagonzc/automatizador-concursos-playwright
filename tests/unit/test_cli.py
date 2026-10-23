from unittest.mock import MagicMock

import pytest

from job_finder.cli import _parser, main
from job_finder.config import CrawlerConfig
from job_finder.records import SearchRun


def test_run_command_accepts_positive_max_pages() -> None:
    args = _parser().parse_args(
        ["run", "--confirm-public-access", "--max-pages", "1"]
    )

    assert args.max_pages == 1


@pytest.mark.parametrize("value", ["0", "-2", "many"])
def test_run_command_rejects_invalid_max_pages(value: str) -> None:
    with pytest.raises(SystemExit):
        _parser().parse_args(
            ["run", "--confirm-public-access", "--max-pages", value]
        )


def test_run_command_accepts_headed_flag() -> None:
    args = _parser().parse_args(["run", "--confirm-public-access", "--headed"])

    assert args.headed is True


def test_crawler_config_defaults_to_headless_mode() -> None:
    assert CrawlerConfig().headed is False


@pytest.mark.parametrize(
    ("extra_args", "expected_headless"),
    [([], True), (["--headed"], False)],
)
def test_cli_launches_browser_with_selected_visibility(
    extra_args: list[str],
    expected_headless: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    playwright_manager = MagicMock()
    browser = playwright_manager.__enter__.return_value.chromium.launch.return_value
    completed_run = SearchRun(run_id="test-run")
    completed_run.status = "complete"

    monkeypatch.setattr("job_finder.cli.sync_playwright", lambda: playwright_manager)
    monkeypatch.setattr(
        "job_finder.cli.execute_search_run",
        lambda *args, **kwargs: (completed_run, None),
    )

    result = main(["run", "--confirm-public-access", *extra_args])

    assert result == 0
    playwright_manager.__enter__.return_value.chromium.launch.assert_called_once_with(
        headless=expected_headless
    )
    browser.new_context.assert_called_once()
