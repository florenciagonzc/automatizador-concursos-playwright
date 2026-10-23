from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CrawlerConfig:
    base_url: str = "https://paraguayconcursa.mef.gov.py/"
    navigation_timeout_ms: int = 20_000
    result_timeout_ms: int = 20_000
    max_retries: int = 2
    navigation_interval_seconds: float = 3.0
    retry_backoff_seconds: float = 2.0
    max_retry_backoff_seconds: float = 30.0
    output_root: Path = Path("data/exports")
    processed_state_path: Path = Path("data/processed_contests.json")
    user_agent: str = "job-finder/0.1 (public vacancy listing client)"
    headed: bool = False

    def __post_init__(self) -> None:
        if self.navigation_timeout_ms <= 0:
            raise ValueError("navigation_timeout_ms must be positive")
        if self.result_timeout_ms <= 0:
            raise ValueError("result_timeout_ms must be positive")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("max_retries must be between 0 and 2")
        if self.navigation_interval_seconds < 3:
            raise ValueError("navigation_interval_seconds must be at least 3")
        if self.retry_backoff_seconds <= 0:
            raise ValueError("retry_backoff_seconds must be positive")
        if self.max_retry_backoff_seconds < self.retry_backoff_seconds:
            raise ValueError(
                "max_retry_backoff_seconds must be at least retry_backoff_seconds"
            )
        if not self.base_url.startswith(("http://", "https://")):
            raise ValueError("base_url must be an HTTP(S) URL")
