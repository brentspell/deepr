"""LaTeX-to-Unicode conversion for terminal display."""

import re

import pylatexenc.latex2text as pl


def latex_to_unicode(markdown: str) -> str:
    """Replace LaTeX math blocks in *markdown* with Unicode approximations.

    Processes ``$$...$$`` (display) blocks first, then ``$...$`` (inline)
    blocks.  If conversion fails for any individual snippet, the raw LaTeX
    is preserved as a fallback.
    """
    text = _DISPLAY_RE.sub(_convert_display, markdown)
    text = _INLINE_RE.sub(_convert_inline, text)
    return text


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

_DISPLAY_RE = re.compile(
    r"\$\$(.+?)\$\$",
    re.DOTALL,
)

_INLINE_RE = re.compile(
    r"(?<!\$)\$(?!\$)(.+?)(?<!\$)\$(?!\$)",
)

_CONVERTER = pl.LatexNodes2Text()


def _convert_snippet(latex: str) -> str:
    """Convert a single LaTeX snippet to Unicode, falling back to raw input."""
    try:
        return _CONVERTER.latex_to_text(latex)
    except Exception:
        return latex


def _convert_display(match: re.Match[str]) -> str:
    return "\n" + _convert_snippet(match.group(1)).strip() + "\n"


def _convert_inline(match: re.Match[str]) -> str:
    return _convert_snippet(match.group(1))
