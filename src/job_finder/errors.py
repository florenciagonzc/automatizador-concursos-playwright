class JobFinderError(Exception):
    """Base error that carries the affected portal resource."""

    def __init__(
        self,
        message: str,
        *,
        target: str,
        cause: Exception | None = None,
        retry_count: int = 0,
    ):
        super().__init__(message)
        self.target = target
        self.cause = cause
        self.retry_count = retry_count


class AccessRestrictedError(JobFinderError):
    pass


class NavigationError(JobFinderError):
    pass


class PageStructureError(JobFinderError):
    pass


class PaginationLoopError(JobFinderError):
    pass


class ContestIdentityError(JobFinderError):
    pass


class DetailError(JobFinderError):
    pass


class DownloadError(JobFinderError):
    pass


class PdfProcessingError(JobFinderError):
    pass


class OutputError(JobFinderError):
    pass
