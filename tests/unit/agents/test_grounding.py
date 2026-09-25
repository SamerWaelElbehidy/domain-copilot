from application.use_cases.grounding import content_tokens, support_score


def test_sentence_final_punctuation_does_not_break_matching():
    assert support_score("Wait 30 minutes.", ("Wait 30 minutes before resuming",)) == 1.0


def test_numbers_and_units_count_but_a_lone_digit_does_not():
    assert "0.5" in content_tokens("minimum 0.5 m/s")
    assert "40c" in content_tokens("below 40C")
    assert "0.05mm" in content_tokens("runout exceeds 0.05mm.")
    assert "1" not in content_tokens("1. Confirm the belt guard")


def test_a_terse_correct_answer_is_supported_but_a_bare_digit_is_not():
    cited = ("The chamber must be below 40C before opening a door.",)

    assert support_score("40C", cited) == 1.0
    assert support_score("1", cited) == 0.0


def test_degenerate_and_invented_answers_score_low():
    cited = ("Allow the spindle to cool for 30 minutes before resuming.",)

    assert support_score("1", cited) == 0.0
    assert support_score("Paris", cited) == 0.0
    assert support_score("Tighten the mounting bolts to 1200Nm", cited) < 0.2


def test_a_faithful_paraphrase_is_supported():
    cited = ("Allow the spindle to cool for 30 minutes before resuming.",)

    assert support_score("The spindle must cool for 30 minutes", cited) >= 0.6
