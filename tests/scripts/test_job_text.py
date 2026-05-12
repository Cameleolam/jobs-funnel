"""Tests for scoring/embedding job text normalization."""

from scripts.lib.job_text import normalize_description, normalize_job_for_llm


def test_normalize_description_converts_html_entities_and_tags_to_text():
    raw = "<h2>Profil</h2><ul><li>Python &amp; REST APIs</li><li>Remote&nbsp;Germany</li></ul>"

    text = normalize_description(raw)

    assert "<h2>" not in text
    assert "<li>" not in text
    assert "Python & REST APIs" in text
    assert "Remote Germany" in text
    assert "Profil" in text


def test_normalize_description_ignores_script_and_style_contents():
    raw = "<style>.x{}</style><script>alert(1)</script><p>Python role</p>"

    text = normalize_description(raw)

    assert "Python role" in text
    assert ".x" not in text
    assert "alert(1)" not in text


def test_normalize_description_removes_arbeitnow_english_footer():
    raw = """
    <p>You are fluent in English. German is a plus.</p>
    <p>Find more <a href="https://www.arbeitnow.com/english-speaking-jobs">English Speaking Jobs in Germany</a> on Arbeitnow</a>
    """

    text = normalize_description(raw)

    assert "You are fluent in English" in text
    assert "German is a plus" in text
    assert "English Speaking Jobs in Germany" not in text
    assert "Arbeitnow" not in text


def test_normalize_description_removes_arbeitnow_generic_footer():
    raw = '<p>Fließend in deutsch und englisch.</p><p>Find <a href="https://www.arbeitnow.com/">Jobs in Germany</a> on Arbeitnow</a>'

    text = normalize_description(raw)

    assert "Fließend in deutsch und englisch." in text
    assert "Jobs in Germany" not in text
    assert "Arbeitnow" not in text


def test_normalize_description_fixes_common_latin1_utf8_mojibake():
    raw = "Location: MÃ¼nster. Aufgaben â€“ Python APIs."

    text = normalize_description(raw)

    assert "Münster" in text
    assert "Aufgaben - Python APIs." in text
    assert "MÃ¼nster" not in text
    assert "â€“" not in text


def test_normalize_description_preserves_non_footer_english_signal():
    raw = "<p>Collaborative Communication: Thrive in an English-speaking agile environment.</p>"

    text = normalize_description(raw)

    assert "English-speaking agile environment" in text


def test_normalize_description_repairs_mojibake_without_dropping_unrelated_unicode():
    raw = "Location: MÃ¼nster 😀"

    text = normalize_description(raw)

    assert "Münster" in text
    assert "😀" in text
    assert "MÃ¼nster" not in text


def test_normalize_job_for_llm_returns_shallow_copy_with_clean_description():
    job = {
        "title": "Backend Engineer",
        "description": "<p>Python &amp; APIs</p><p>Find more English Speaking Jobs in Germany on Arbeitnow</p>",
        "tags": ["Software Development"],
    }

    cleaned = normalize_job_for_llm(job)

    assert cleaned is not job
    assert cleaned["tags"] is job["tags"]
    assert cleaned["description"] == "Python & APIs"
    assert job["description"].startswith("<p>")
