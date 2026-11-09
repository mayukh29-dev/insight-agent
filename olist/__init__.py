"""Optional historical Olist ingestion; independent of InsightAgent's demo."""

from .pipeline import ValidationError, ingest

__all__ = ["ValidationError", "ingest"]
