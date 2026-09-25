from application.use_cases.grounding import content_tokens, support_score


def test_sentence_final_punctuation_does_not_break_matching():
    assert support_score("Wait 30 minutes.", ("Wait 30 minutes before resuming",)) == 1.0


def test_decimal_values_survive_tokenising():
    assert "0.5" not in content_tokens("minimum 0.5 m/s")  # too short to count on its own
    assert "0.05mm" in content_tokens("runout exceeds 0.05mm.")


def test_degenerate_and_invented_answers_score_low():
    cited = ("Allow the spindle to cool for 30 minutes before resuming.",)

    assert support_score("1", cited) == 0.0
    assert support_score("Paris", cited) == 0.0
    assert support_score("Tighten the mounting bolts to 1200Nm", cited) < 0.2


def test_a_faithful_paraphrase_is_supported():
    cited = ("Allow the spindle to cool for 30 minutes before resuming.",)

    assert support_score("The spindle must cool for 30 minutes", cited) >= 0.6
