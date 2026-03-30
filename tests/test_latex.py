import deepr.latex as dl


class TestLatexToUnicode:
    def test_inline_math(self) -> None:
        result = dl.latex_to_unicode(r"Given $\alpha + \beta = \gamma$ holds.")
        assert "$" not in result
        assert "α" in result
        assert "β" in result
        assert "γ" in result

    def test_display_math(self) -> None:
        result = dl.latex_to_unicode(r"$$E = mc^2$$")
        assert "$$" not in result
        assert "E = mc^2" in result

    def test_display_math_multiline(self) -> None:
        text = "$$\n\\frac{a}{b}\n$$"
        result = dl.latex_to_unicode(text)
        assert "$$" not in result
        assert "a/b" in result

    def test_mixed_content(self) -> None:
        text = r"# Title" + "\n\nInline $x^2$ and display:\n\n$$E = mc^2$$\n\nEnd."
        result = dl.latex_to_unicode(text)
        assert "# Title" in result
        assert "End." in result
        assert "$" not in result

    def test_no_math_passthrough(self) -> None:
        text = "Just regular markdown with **bold** and `code`."
        assert dl.latex_to_unicode(text) == text

    def test_malformed_latex_fallback(self) -> None:
        text = r"See $\invalidcommand{x}$ here."
        result = dl.latex_to_unicode(text)
        # Should not raise; either converts or falls back to raw
        assert "here." in result

    def test_lone_dollar_not_matched(self) -> None:
        text = "Price is $5 for one item."
        result = dl.latex_to_unicode(text)
        # No closing $ to match, so text passes through unchanged
        assert result == text

    def test_fraction_conversion(self) -> None:
        result = dl.latex_to_unicode(r"$\frac{a}{b}$")
        assert "a/b" in result
        assert "$" not in result
