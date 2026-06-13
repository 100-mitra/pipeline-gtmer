import pipeline.prospector.ats as ats

GREENHOUSE = {
    "jobs": [
        {"title": "Sales Development Representative", "absolute_url": "https://x/1", "updated_at": "2026-06-01T00:00:00Z"},
        {"title": "Backend Engineer", "absolute_url": "https://x/2", "updated_at": "2026-06-01T00:00:00Z"},
    ]
}
LEVER = [
    {"text": "BDR (Outbound)", "hostedUrl": "https://lever/1", "createdAt": 1771200000000},
    {"text": "Product Manager", "hostedUrl": "https://lever/2", "createdAt": 1771200000000},
]
ASHBY = {"jobs": [{"title": "Inside Sales", "jobUrl": "https://ashby/1", "publishedDate": "2026-05-20"}]}


def test_discover_token():
    assert ats.discover_token('<a href="https://boards.greenhouse.io/acme">') == ("greenhouse", "acme")
    assert ats.discover_token('<script src="https://jobs.lever.co/acme/x.js">') == ("lever", "acme")
    assert ats.discover_token('href="https://jobs.ashbyhq.com/acme"') == ("ashby", "acme")
    assert ats.discover_token("<p>no ats here</p>") is None


def test_greenhouse_normalization(monkeypatch):
    monkeypatch.setattr(ats, "_get_json", lambda url: GREENHOUSE)
    jobs = ats.fetch_jobs("greenhouse", "acme")
    assert len(jobs) == 2
    assert jobs[0].title == "Sales Development Representative"
    assert jobs[0].ats_source == "greenhouse" and jobs[0].ats_token == "acme"


def test_lever_epoch_conversion(monkeypatch):
    monkeypatch.setattr(ats, "_get_json", lambda url: LEVER)
    jobs = ats.fetch_jobs("lever", "acme")
    assert jobs[0].title == "BDR (Outbound)"
    assert jobs[0].posted_at and jobs[0].posted_at.startswith("2026-")


def test_ashby_normalization(monkeypatch):
    monkeypatch.setattr(ats, "_get_json", lambda url: ASHBY)
    jobs = ats.fetch_jobs("ashby", "acme")
    assert jobs[0].title == "Inside Sales" and jobs[0].posted_at == "2026-05-20"


def test_bad_payload_is_safe(monkeypatch):
    monkeypatch.setattr(ats, "_get_json", lambda url: None)
    assert ats.fetch_jobs("greenhouse", "acme") == []
