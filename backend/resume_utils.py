"""Resume parsing straight from uploaded bytes — nothing is ever written
to disk, unlike the original CLI script which read from a local path."""
import io

import docx
from pypdf import PdfReader


def extract_resume_text(filename: str, content: bytes) -> str:
    lower = filename.lower()
    if lower.endswith(".pdf"):
        reader = PdfReader(io.BytesIO(content))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    elif lower.endswith(".docx"):
        d = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in d.paragraphs)
    else:
        raise ValueError("Resume must be a .pdf or .docx file")
