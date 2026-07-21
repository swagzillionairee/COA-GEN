"""Core library for the Certificate of Analysis Generator."""

from .models import COAConfig
from .pdf_generator import generate_pdf

__all__ = ["COAConfig", "generate_pdf"]
__version__ = "0.3.0"
