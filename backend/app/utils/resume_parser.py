"""
AutoJob AI — Resume Text Extractor
Extracts text from uploaded PDF and DOCX resume files.
Used by the AI pipeline to analyze the user's full resume.
"""

import logging
import os

logger = logging.getLogger("autojob.utils.resume")


async def extract_resume_text(file_path: str) -> str:
    """
    Extract text content from a resume file (PDF or DOCX).

    Args:
        file_path: Absolute path to the resume file on disk.

    Returns:
        Extracted text content, or empty string if extraction fails.
    """
    if not file_path or not os.path.exists(file_path):
        logger.warning(f"Resume file not found: {file_path}")
        return ""

    ext = os.path.splitext(file_path)[1].lower()

    try:
        if ext == ".pdf":
            return _extract_pdf(file_path)
        elif ext in (".docx", ".doc"):
            return _extract_docx(file_path)
        else:
            logger.warning(f"Unsupported resume format: {ext}")
            return ""
    except Exception as e:
        logger.error(f"Failed to extract text from resume: {e}")
        return ""


def _extract_pdf(file_path: str) -> str:
    """Extract text from a PDF file using pdfplumber."""
    import pdfplumber

    text_parts = []
    with pdfplumber.open(file_path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text()
            if page_text:
                text_parts.append(page_text)

    full_text = "\n\n".join(text_parts).strip()
    logger.info(f"Extracted {len(full_text)} chars from PDF ({len(text_parts)} pages)")
    return full_text


def _extract_docx(file_path: str) -> str:
    """Extract text from a DOCX file using python-docx."""
    try:
        from docx import Document
    except ImportError:
        logger.warning("python-docx not installed, cannot extract DOCX text")
        return ""

    doc = Document(file_path)
    text_parts = [para.text for para in doc.paragraphs if para.text.strip()]
    full_text = "\n".join(text_parts).strip()
    logger.info(f"Extracted {len(full_text)} chars from DOCX ({len(text_parts)} paragraphs)")
    return full_text
