from __future__ import annotations

import html
import re


def clean_ocr_text(value: str) -> str:
    text = value.replace("\r\n", "\n").replace("\r", "\n")
    if _looks_like_html(text):
        text = _strip_html(text)
    text = html.unescape(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return "\n".join(line.strip() for line in text.splitlines()).strip()


def _looks_like_html(value: str) -> bool:
    sample = value[:2000].lower()
    return "<html" in sample or "<!doctype" in sample or "<body" in sample


def _strip_html(value: str) -> str:
    text = re.sub(r"(?is)<script\b.*?</script>", "\n", value)
    text = re.sub(r"(?is)<style\b.*?</style>", "\n", text)
    text = re.sub(r"(?is)<head\b.*?</head>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:p|div|tr|li|h[1-6]|table|section|article)>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", " ", text)
    return text
