import logging
import os
import re
import shutil
import subprocess
from typing import List, Tuple

from audiobook_generator.book_parsers.base_book_parser import BaseBookParser
from audiobook_generator.config.general_config import GeneralConfig

logger = logging.getLogger(__name__)


def _try_imports():
    reader_cls = None
    backend = None
    try:
        from pypdf import PdfReader  # type: ignore
        reader_cls = PdfReader
        backend = "pypdf"
        return backend, reader_cls
    except Exception:  # pragma: no cover - depends on environment
        pass
    try:
        from PyPDF2 import PdfReader as LegacyPdfReader  # type: ignore
        reader_cls = LegacyPdfReader
        backend = "pypdf2"
        return backend, reader_cls
    except Exception:  # pragma: no cover - depends on environment
        pass
    try:
        from pdfminer.high_level import extract_text  # type: ignore

        # Signal pdfminer usage by returning callable
        backend = "pdfminer"
        return backend, extract_text
    except Exception:  # pragma: no cover - depends on environment
        pass
    try:
        pdftotext_path = shutil.which("pdftotext")
        if not pdftotext_path:
            raise FileNotFoundError

        def _extract_with_pdftotext(path: str) -> str:
            try:
                completed = subprocess.run(
                    [pdftotext_path, "-layout", "-enc", "UTF-8", path, "-"],
                    check=True,
                    capture_output=True,
                )
            except subprocess.CalledProcessError as exc:  # pragma: no cover - system dependent
                raise RuntimeError(f"pdftotext failed with exit code {exc.returncode}") from exc
            return completed.stdout.decode("utf-8", errors="ignore")

        backend = "pdftotext"
        return backend, _extract_with_pdftotext
    except Exception:  # pragma: no cover - depends on environment
        pass
    return None, None


class PdfBookParser(BaseBookParser):
    """Basic PDF parser that extracts text per page and creates chapters.

    Backends (first available is used):
      - pypdf
      - PyPDF2
      - pdfminer.six

    Note: PDF structure varies widely; this parser treats each page as a
    chapter by default and applies light cleaning similar to the EPUB parser.
    """

    def __init__(self, config: GeneralConfig):
        super().__init__(config)
        self._backend, self._reader = _try_imports()
        if not self._backend:
            raise RuntimeError(
                "No PDF backend available. Install one of: pypdf, PyPDF2, pdfminer.six, or ensure pdftotext is installed"
            )
        self._pdf = None
        self._metadata = {}
        if self._backend in ("pypdf", "pypdf2"):
            try:
                self._pdf = self._reader(self.config.input_file)
            except Exception as exc:
                raise RuntimeError(f"Failed to open PDF: {exc}") from exc
            try:
                meta = getattr(self._pdf, "metadata", None) or {}
                # pypdf/PyPDF2 may return None or dict-like object
                self._metadata = dict(meta) if isinstance(meta, dict) else getattr(meta, "__dict__", {}) or {}
            except Exception:
                self._metadata = {}
        # pdfminer handled on demand

    def __str__(self) -> str:
        return super().__str__()

    def validate_config(self):
        if self.config.input_file is None:
            raise ValueError("PDF Parser: Input file cannot be empty")
        if not self.config.input_file.endswith(".pdf"):
            raise ValueError(
                f"PDF Parser: Unsupported file format: {self.config.input_file}"
            )

    def get_book(self):
        return self._pdf

    def get_book_title(self) -> str:
        # Try metadata first
        title = None
        if self._metadata:
            # common keys across pypdf/PyPDF2
            for key in ("/Title", "title"):
                if key in self._metadata and self._metadata[key]:
                    title = str(self._metadata[key])
                    break
        if not title:
            title = os.path.splitext(os.path.basename(self.config.input_file))[0]
        return title or "Untitled"

    def get_book_author(self) -> str:
        author = None
        if self._metadata:
            for key in ("/Author", "author"):
                if key in self._metadata and self._metadata[key]:
                    author = str(self._metadata[key])
                    break
        return author or "Unknown"

    def _clean_text(self, raw: str, break_string: str) -> str:
        # newline handling similar to EPUB parser
        if self.config.newline_mode == "single":
            cleaned = re.sub(r"[\n\r]+", break_string, raw.strip())
        elif self.config.newline_mode == "double":
            cleaned = re.sub(r"[\n\r]{2,}", break_string, raw.strip())
        elif self.config.newline_mode == "none":
            cleaned = re.sub(r"[\n\r]+", " ", raw.strip())
        else:
            raise ValueError(f"Invalid newline mode: {self.config.newline_mode}")

        cleaned = re.sub(r"\s+", " ", cleaned)

        if self.config.remove_endnotes:
            cleaned = re.sub(r'(?<=[a-zA-Z.,!?;”")])\d+', "", cleaned)

        if self.config.remove_reference_numbers:
            cleaned = re.sub(r'\[\d+(\.\d+)?\]', '', cleaned)

        # Apply custom search/replace from file if provided
        for s, r in self._get_search_and_replaces():
            cleaned = re.sub(s, r, cleaned)
        return cleaned

    def _get_search_and_replaces(self):
        pairs: List[Tuple[str, str]] = []
        if self.config.search_and_replace_file:
            try:
                with open(self.config.search_and_replace_file) as fp:
                    for line in fp:
                        if (
                            '==' in line
                            and not line.startswith('==')
                            and not line.endswith('==')
                            and not line.startswith('#')
                        ):
                            left, right = line.split('==', 1)
                            pairs.append((left, right.rstrip('\n')))
            except Exception as exc:
                logger.debug("Failed reading search/replace file: %s", exc)
        return pairs

    @staticmethod
    def _sanitize_title(title: str, break_string: str) -> str:
        title = title.replace(break_string, " ")
        title = re.sub(r'(?<=[a-zA-Z]) (?=[a-zA-Z])', '', title)
        sanitized = re.sub(r"[^\w\s]", "", title, flags=re.UNICODE)
        sanitized = re.sub(r"\s+", "_", sanitized.strip())
        return sanitized or "Page"

    def _title_for_page(self, cleaned_text: str, page_index: int) -> str:
        mode = self.config.title_mode
        if mode == "first_few":
            title = cleaned_text[:60]
        elif mode == "tag_text":
            # No tags in PDF text flow; fall back
            title = cleaned_text[:60] or f"Page_{page_index+1}"
        elif mode == "auto":
            title = cleaned_text[:60] or f"Page_{page_index+1}"
        else:
            raise ValueError("Unsupported title_mode")
        return self._sanitize_title(title, "\n")

    def get_chapters(self, break_string) -> List[Tuple[str, str]]:
        chapters: List[Tuple[str, str]] = []

        if self._backend in ("pypdf", "pypdf2"):
            pages = getattr(self._pdf, "pages", None)
            if pages is None:
                raise RuntimeError("PDF has no pages attribute")
            for idx, page in enumerate(pages):
                try:
                    raw = page.extract_text() or ""
                except Exception as exc:
                    logger.debug("Failed to extract text for page %d: %s", idx + 1, exc)
                    raw = ""
                cleaned = self._clean_text(raw, break_string)
                if not cleaned.strip():
                    continue
                title = self._title_for_page(cleaned, idx)
                chapters.append((title, cleaned))
        elif self._backend in ("pdfminer", "pdftotext"):
            # extract_text returns full text with form-feed '\f' between pages
            try:
                full_text = self._reader(self.config.input_file)  # type: ignore[misc]
            except Exception as exc:
                raise RuntimeError(f"Failed to extract text via {self._backend}: {exc}") from exc
            parts = re.split(r"\f+", full_text)
            for idx, part in enumerate(parts):
                cleaned = self._clean_text(part, break_string)
                if not cleaned.strip():
                    continue
                title = self._title_for_page(cleaned, idx)
                chapters.append((title, cleaned))
        else:  # pragma: no cover - defensive
            raise RuntimeError("Unknown PDF backend selected")

        return chapters
