from application.use_cases.ingestion.clean_text import clean_text


def test_normalizes_crlf_to_lf():
    assert clean_text("line one\r\nline two\r\n") == "line one\nline two"


def test_strips_trailing_whitespace_per_line():
    assert clean_text("line one   \nline two\t\n") == "line one\nline two"


def test_collapses_three_or_more_blank_lines_to_one():
    assert clean_text("a\n\n\n\n\nb") == "a\n\nb"


def test_preserves_single_blank_line_between_paragraphs():
    assert clean_text("a\n\nb") == "a\n\nb"
