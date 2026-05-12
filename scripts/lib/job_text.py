"""Transient job-description normalization for scoring and embeddings."""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from typing import Any


_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "fieldset",
    "figcaption",
    "figure",
    "footer",
    "form",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "hr",
    "li",
    "main",
    "nav",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "tfoot",
    "th",
    "thead",
    "tr",
    "ul",
}

_IGNORED_CONTENT_TAGS = {"script", "style"}

_FOOTER_PATTERNS = (
    re.compile(r"\s*Find\s+more\s+English\s+Speaking\s+Jobs\s+in\s+Germany\s+on\s+Arbeitnow\s*$", re.I),
    re.compile(r"\s*Find\s+Jobs\s+in\s+Germany\s+on\s+Arbeitnow\s*$", re.I),
)

_MOJIBAKE_MARKERS = ("Ã", "Â", "â€", "â€“", "â€”", "â€™", "â€œ", "â€�")

_DASH_TRANSLATION = str.maketrans(
    {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
    }
)


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._chunks: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_CONTENT_TAGS:
            self._ignored_depth += 1
            return
        if normalized_tag in _BLOCK_TAGS:
            self._newline()

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in _IGNORED_CONTENT_TAGS:
            self._ignored_depth = max(0, self._ignored_depth - 1)
            return
        if normalized_tag in _BLOCK_TAGS:
            self._newline()

    def handle_data(self, data: str) -> None:
        if data and self._ignored_depth == 0:
            self._chunks.append(data)

    def get_text(self) -> str:
        return "".join(self._chunks)

    def _newline(self) -> None:
        if self._chunks and not self._chunks[-1].endswith("\n"):
            self._chunks.append("\n")


def _unescape_repeated(text: str) -> str:
    for _ in range(5):
        unescaped = html.unescape(text)
        if unescaped == text:
            return text
        text = unescaped
    return text


def _html_to_text(text: str) -> str:
    parser = _HTMLTextExtractor()
    parser.feed(text)
    parser.close()
    return parser.get_text()


def _marker_count(text: str) -> int:
    return sum(text.count(marker) for marker in _MOJIBAKE_MARKERS) + sum(
        text.count(marker) for marker in ("\u00c3", "\u00c2", "\u00e2\u20ac", "\ufffd")
    )


def _repair_mojibake_span(text: str) -> str:
    current = text
    for _ in range(3):
        current_markers = _marker_count(current)
        if current_markers == 0:
            break

        candidates = []
        for encoding in ("cp1252", "latin1"):
            try:
                candidates.append(current.encode(encoding).decode("utf-8"))
            except UnicodeError:
                pass

        better = [candidate for candidate in candidates if _marker_count(candidate) < current_markers]
        if not better:
            break
        current = min(better, key=_marker_count)
    return current


def _repair_mojibake(text: str) -> str:
    mojibake_span = re.compile(r"\S*(?:\u00c3|\u00c2|\u00e2\u20ac|\ufffd)\S*")
    return mojibake_span.sub(lambda match: _repair_mojibake_span(match.group(0)), text)


def _normalize_whitespace(text: str) -> str:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    collapsed: list[str] = []
    blank_seen = False

    for line in lines:
        if line:
            collapsed.append(line)
            blank_seen = False
        elif collapsed and not blank_seen:
            collapsed.append("")
            blank_seen = True

    return "\n".join(collapsed).strip()


def _strip_source_footer(text: str) -> str:
    cleaned = text
    for pattern in _FOOTER_PATTERNS:
        cleaned = pattern.sub("", cleaned).rstrip()
    return cleaned


def normalize_description(raw: Any) -> str:
    """Return transient plain text for LLM scoring/embedding inputs."""
    if raw is None:
        return ""

    text = str(raw)
    text = _unescape_repeated(text)
    text = _html_to_text(text)
    text = _unescape_repeated(text)
    text = _repair_mojibake(text)
    text = text.translate(_DASH_TRANSLATION)
    text = _normalize_whitespace(text)
    text = _strip_source_footer(text)
    return _normalize_whitespace(text)


def normalize_job_for_llm(job: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of a job with only description normalized."""
    cleaned = dict(job)
    cleaned["description"] = normalize_description(job.get("description"))
    return cleaned
