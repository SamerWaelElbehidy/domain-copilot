from application.use_cases.ingestion.extract_markdown import extract_markdown_document


def test_frontmatter_is_parsed_into_metadata():
    raw = (
        "---\n"
        "equipment_id: eq-1\n"
        "revision: Rev. A\n"
        "---\n"
        "# Title\n\nBody text.\n"
    )

    extracted = extract_markdown_document(raw)

    assert extracted.metadata == {"equipment_id": "eq-1", "revision": "Rev. A"}
    assert extracted.body == "# Title\n\nBody text."


def test_document_without_frontmatter_has_empty_metadata():
    extracted = extract_markdown_document("# Title\n\nBody text.")

    assert extracted.metadata == {}
    assert extracted.body == "# Title\n\nBody text."
