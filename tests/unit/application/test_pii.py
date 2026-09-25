import pytest

from application.pii import redact_pii


@pytest.mark.parametrize(
    "text,label",
    [
        ("mail me at ahmed.ali@example.com please", "EMAIL"),
        ("my id is 29001011234567", "NATIONAL_ID"),
        ("call 01012345678 when done", "PHONE"),
        ("call +20 101 234 5678 when done", "PHONE"),
        ("call +44 20 7946 0958 when done", "PHONE"),
        ("card 4111 1111 1111 1111 expires soon", "CARD"),
    ],
)
def test_each_kind_of_identifier_is_replaced_by_a_typed_placeholder(text, label):
    result = redact_pii(text)

    assert f"[{label}]" in result.text
    assert result.counts == {label: 1}
    assert result.total == 1


def test_the_value_never_survives_in_any_form():
    result = redact_pii("id 29001011234567, phone 01012345678, mail a.b@x.io")

    for leaked in ("29001011234567", "01012345678", "a.b@x.io", "1234567"):
        assert leaked not in result.text
    assert result.total == 3


@pytest.mark.parametrize(
    "technical",
    [
        "Spindle: 9kW air-cooled, 6,000-24,000 RPM.",
        "Work envelope 2200mm x 1300mm x 200mm on the DWR-2200",
        "Reset the DCS-800 gauge to 40C within 30 minutes",
        "Part number 4400123 and 4400124, torque 45 Nm",
        "Rev. C effective 2025-11-01, section 3.2.1",
        "eq-cnc-router-dwr2200 doc-cnc-router-dwr2200-rev-c",
    ],
)
def test_technical_text_is_left_alone(technical):
    result = redact_pii(technical)

    assert result.text == technical and result.total == 0


def test_a_long_number_that_fails_the_card_checksum_is_not_treated_as_a_card():
    text = "serial 4111 1111 1111 1112"

    assert redact_pii(text).text == text


def test_redaction_is_idempotent():
    once = redact_pii("write to a@b.co or 01012345678")

    assert redact_pii(once.text).text == once.text
