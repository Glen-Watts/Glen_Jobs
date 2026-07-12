import pytest

from main import build_application_pdfs, sanitize_filename


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (
            "Senior Business Analyst: Data, Systems & Change Leader",
            "Senior_Business_Analyst_Data_Systems_Change_Leader",
        ),
        ("Career.zycto – Systems Analyst", "Careerzycto_Systems_Analyst"),
        ("   ", "untitled"),
    ],
)
def test_sanitize_filename_strips_unsafe_characters(raw, expected):
    assert sanitize_filename(raw) == expected


def test_sanitize_filename_truncates_to_max_length():
    result = sanitize_filename("A" * 100, max_length=10)
    assert result == "A" * 10


@pytest.fixture
def job():
    return {
        "title": "Data Analyst Apprentice",
        "company": "Test Corp",
        "description": "Entry level role.",
    }


@pytest.fixture
def templates(tmp_path, monkeypatch):
    monkeypatch.setattr("main.OUTPUT_DIR", tmp_path)
    return "(( CV_CONTENT ))", "(( LETTER_CONTENT ))"


def test_build_application_pdfs_skips_not_suitable(job, templates, monkeypatch):
    cv_template, letter_template = templates
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: "NOT_SUITABLE")

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result is False


def test_build_application_pdfs_false_when_ai_returns_nothing(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: None)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result is False


def test_build_application_pdfs_false_when_response_unparseable(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: "garbage response")

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result is False


def test_build_application_pdfs_false_when_compile_fails(job, templates, monkeypatch):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw)
    # CV compiles, cover letter fails to compile: job must not be marked done.
    monkeypatch.setattr("main.compile_latex", lambda path, name: "CV" in name)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result is False


def test_build_application_pdfs_true_when_both_compile(job, templates, monkeypatch):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result is True
