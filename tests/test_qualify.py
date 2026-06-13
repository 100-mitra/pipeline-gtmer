from pipeline.prospector.qualify import score_signal, title_matches


def test_strong_titles_match():
    for t in ["SDR", "Sales Development Representative", "BDR - Outbound",
              "Business Development Representative", "Inside Sales Executive"]:
        assert title_matches(t) == "strong", t


def test_weak_titles_match():
    for t in ["Sales Executive", "Lead Generation Specialist", "Demand Generation Manager"]:
        assert title_matches(t) == "weak", t


def test_false_positives_excluded():
    # The classic trap: software/engineering roles must NOT register as sales signals.
    for t in ["SDET", "Software Engineer", "QA Engineer", "Senior Developer", "Backend Engineer"]:
        assert title_matches(t) is None, t


def test_unrelated_titles_none():
    for t in ["Product Designer", "Office Manager", "Data Scientist"]:
        assert title_matches(t) is None, t


def test_scoring_tiers_and_recency():
    hot_score, hot_tier, _ = score_signal("SDR", "2026-06-05")  # ~1 week old
    assert hot_tier == "hot" and hot_score >= 80

    warm_score, warm_tier, _ = score_signal("Sales Executive", None)
    assert warm_tier == "warm" and 50 <= warm_score < 80

    none_score, none_tier, _ = score_signal("Backend Engineer", "2026-06-05")
    assert none_score == 0 and none_tier == "cold"


def test_india_boost():
    base, _, _ = score_signal("Business Development Representative", None)
    boosted, _, ev = score_signal("Business Development Representative", None, india=True)
    assert boosted == base + 15
    assert "India-HQ priority" in ev


def test_is_india_detection():
    from pipeline.prospector.universe import is_india
    assert is_india("Bengaluru, KA, India")
    assert is_india("Mumbai")
    assert not is_india("San Francisco, CA")
    assert not is_india(None)
