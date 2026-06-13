from pipeline.evals.heuristics import check_touch

GOOD_T1 = dict(
    touch=1,
    subject="Your SDR hire at Acme",
    body=(
        "Saw Acme is hiring an SDR to push outbound. Most teams spend three months "
        "ramping that rep before the first booked meeting. GTMer runs the same motion "
        "from day one and books meetings into your calendar. Worth a 15-minute look?"
    ),
    company_name="Acme",
    job_title="Sales Development Representative",
)


def test_good_touch1_passes():
    r = check_touch(**GOOD_T1)
    assert r.passed, r.detail


def test_spam_word_fails():
    bad = {**GOOD_T1, "body": GOOD_T1["body"] + " 100% guaranteed results, act now!"}
    r = check_touch(**bad)
    assert not r.passed
    assert not r.checks["no_spam_words"]


def test_placeholder_leak_fails():
    bad = {**GOOD_T1, "body": "Hi {{first_name}}, saw Acme is hiring an SDR. Worth a look?"}
    r = check_touch(**bad)
    assert not r.passed
    assert not r.checks["no_placeholders"]


def test_banned_phrase_fails():
    bad = {**GOOD_T1, "body": "I hope this finds you well. " + GOOD_T1["body"]}
    r = check_touch(**bad)
    assert not r.checks["no_banned_phrases"]


def test_multiple_ctas_fail():
    bad = {**GOOD_T1, "body": "Acme is hiring an SDR. Want a demo? Free this week? Reply?"}
    r = check_touch(**bad)
    assert not r.checks["single_cta"]


def test_touch1_must_reference_signal_and_company():
    bad = {**GOOD_T1, "body": "We help companies grow revenue with automation software tools. Interested?"}
    r = check_touch(**bad)
    assert not r.checks["references_signal"] or not r.checks["personalized"]


def test_overlong_body_fails():
    bad = {**GOOD_T1, "body": " ".join(["word"] * 200)}
    r = check_touch(**bad)
    assert not r.checks["body_length"]


def test_fake_thread_subject_fails():
    for subj in ("Re: Your SDR hire", "RE: outbound", "Fwd: a thought", "fw: hi"):
        r = check_touch(**{**GOOD_T1, "subject": subj})
        assert not r.checks["no_fake_thread"], subj
        assert not r.passed


def test_real_subject_starting_with_re_word_passes():
    # "Rethinking ..." must NOT trip the Re:/Fwd: guard (it keys on "re:" + colon).
    r = check_touch(**{**GOOD_T1, "subject": "Rethinking Acme outbound"})
    assert r.checks["no_fake_thread"]
