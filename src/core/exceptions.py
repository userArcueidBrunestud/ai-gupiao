class DataFetchError(Exception):
    """Raised when fetching data from an external source fails."""

    def __init__(self, source: str, detail: str = "") -> None:
        self.source = source
        self.detail = detail
        super().__init__(f"[{source}] fetch failed: {detail}")


class StorageError(Exception):
    """Raised when database read/write operations fail."""


class AnalysisError(Exception):
    """Raised when technical indicator computation fails."""


class ModelError(Exception):
    """Raised when ML model training or prediction fails."""


class FeatureError(Exception):
    """Raised when feature engineering fails."""


class PipelineError(Exception):
    """Raised when pipeline orchestration fails."""
