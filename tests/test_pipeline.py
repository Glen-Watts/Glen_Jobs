import subprocess

import pytest

from main import (
    STATUS_FAILED,
    STATUS_PROCESSED,
    STATUS_UNSUITABLE,
    apply_critic_pass,
    build_application_pdfs,
    delatex_for_display,
    get_pdf_page_count,
    init_db,
    job_exists,
    process_jobs,
    sanitize_filename,
    send_email,
)


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


def test_build_application_pdfs_unsuitable_status_when_not_suitable(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: "NOT_SUITABLE")

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_UNSUITABLE


def test_build_application_pdfs_failed_when_ai_returns_nothing(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: None)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_FAILED


def test_build_application_pdfs_failed_when_response_unparseable(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: "garbage response")

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_FAILED


def test_build_application_pdfs_failed_when_compile_fails(job, templates, monkeypatch):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw)
    # CV compiles, cover letter fails to compile: job must not be marked done.
    monkeypatch.setattr("main.compile_latex", lambda path, name: "CV" in name)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_FAILED


def test_build_application_pdfs_processed_when_both_compile(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_PROCESSED


@pytest.fixture
def pipeline_env(tmp_path, monkeypatch):
    """A full process_jobs() environment: temp DB, output dir, and base CV."""
    monkeypatch.setattr("main.DB_PATH", tmp_path / "jobs.db")
    monkeypatch.setattr("main.OUTPUT_DIR", tmp_path / "outputs")
    base_cv_path = tmp_path / "base_cv.txt"
    base_cv_path.write_text("base cv content")
    monkeypatch.setattr("main.BASE_CV_PATH", base_cv_path)
    init_db()
    return tmp_path


def test_process_jobs_persists_unsuitable_so_it_is_never_retailored(
    pipeline_env, monkeypatch
):
    raw_job = {
        "job_id": "unsuitable-1",
        "title": "Lead Data Scientist",
        "company_name": "BigCorp",
        "related_links": [{"link": "http://example.com"}],
        "description": "desc",
    }
    monkeypatch.setattr("main.search_jobs", lambda: [raw_job])
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: "NOT_SUITABLE")

    processed = process_jobs()

    assert processed == []
    # The regression this guards against: an unsuitable job must be
    # persisted so search_jobs() finding it again next run does not burn
    # another Gemini call re-tailoring a job already rejected.
    assert job_exists("unsuitable-1") is True


def test_process_jobs_does_not_persist_a_failed_job_so_it_retries(
    pipeline_env, monkeypatch
):
    raw_job = {
        "job_id": "failed-1",
        "title": "Assistant Manager",
        "company_name": "SmallCorp",
        "related_links": [{"link": "http://example.com"}],
        "description": "desc",
    }
    monkeypatch.setattr("main.search_jobs", lambda: [raw_job])
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: None)

    processed = process_jobs()

    assert processed == []
    assert job_exists("failed-1") is False


def test_process_jobs_persists_and_emails_a_successful_job(
    pipeline_env, monkeypatch
):
    raw_job = {
        "job_id": "ok-1",
        "title": "Assistant Manager",
        "company_name": "GoodCorp",
        "related_links": [{"link": "http://example.com"}],
        "description": "desc",
    }
    raw_response = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    monkeypatch.setattr("main.search_jobs", lambda: [raw_job])
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw_response)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)

    processed = process_jobs()

    assert len(processed) == 1
    assert processed[0]["title"] == "Assistant Manager"
    assert job_exists("ok-1") is True


def test_get_pdf_page_count_parses_pdfinfo_output(monkeypatch):
    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout="Producer:       pdfTeX\nPages:          2\nPage size:      x\n",
        )

    monkeypatch.setattr("main.subprocess.run", fake_run)

    assert get_pdf_page_count("fake.pdf") == 2


def test_get_pdf_page_count_returns_none_when_pdfinfo_missing(monkeypatch):
    def fake_run(*args, **kwargs):
        raise FileNotFoundError("pdfinfo not found")

    monkeypatch.setattr("main.subprocess.run", fake_run)

    assert get_pdf_page_count("fake.pdf") is None


def test_build_application_pdfs_retries_once_when_cv_overflows(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    compressed = "---TAILORED CV LATEX---\nSHORT CV\n---COVER LETTER LATEX---\nLETTER"

    call_count = {"n": 0}

    def fake_tailor(*args, **kwargs):
        call_count["n"] += 1
        return compressed if "extra_instruction" in kwargs else raw

    # First compile check reports 2 pages (overflow), retry check reports 1.
    page_counts = iter([2, 1])
    monkeypatch.setattr("main.tailor_application", fake_tailor)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)
    monkeypatch.setattr("main.get_pdf_page_count", lambda path: next(page_counts))

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_PROCESSED
    assert call_count["n"] == 2  # original attempt + one compress retry


def test_build_application_pdfs_still_processed_if_retry_does_not_fix_overflow(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"

    call_count = {"n": 0}

    def fake_tailor(*args, **kwargs):
        call_count["n"] += 1
        return raw

    monkeypatch.setattr("main.tailor_application", fake_tailor)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)
    # Always overflows, even after the retry.
    monkeypatch.setattr("main.get_pdf_page_count", lambda path: 2)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    # Documented decision: don't lose an otherwise-good application over a
    # persistent formatting nit — ship it with a warning instead of an
    # unbounded retry loop.
    assert result == STATUS_PROCESSED
    assert call_count["n"] == 2  # original attempt + exactly one retry, no more


def test_build_application_pdfs_sets_letter_preview_on_success(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    raw = (
        "---TAILORED CV LATEX---\nCV\n"
        "---COVER LETTER LATEX---\n"
        r"Worked at Smith \& Sons for 5\% more pay."
    )
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)
    monkeypatch.setattr("main.get_pdf_page_count", lambda path: 1)

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_PROCESSED
    assert job["letter_preview"] == "Worked at Smith & Sons for 5% more pay."


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (r"Smith \& Sons", "Smith & Sons"),
        (r"5\% off", "5% off"),
        (r"\#1 choice", "#1 choice"),
        (r"cost \$5", "cost $5"),
        (r"file\_name", "file_name"),
        (r"\{curly\}", "{curly}"),
        ("plain text, no escapes", "plain text, no escapes"),
    ],
)
def test_delatex_for_display(raw, expected):
    assert delatex_for_display(raw) == expected


class _FakeSMTP:
    """Records the message it would have sent instead of touching a real server."""

    sent_messages = []

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def login(self, *args, **kwargs):
        pass

    def send_message(self, msg):
        _FakeSMTP.sent_messages.append(msg)


@pytest.fixture
def fake_smtp(monkeypatch):
    _FakeSMTP.sent_messages = []
    monkeypatch.setattr("main.smtplib.SMTP_SSL", _FakeSMTP)
    monkeypatch.setattr("main.SENDER_EMAIL", "sender@example.com")
    monkeypatch.setattr("main.SENDER_PASSWORD", "pw")
    monkeypatch.setattr("main.RECEIVER_EMAIL", "receiver@example.com")
    return _FakeSMTP


def test_send_email_body_is_review_queue_with_letter_preview(
    fake_smtp, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("main.OUTPUT_DIR", tmp_path / "outputs")
    (tmp_path / "outputs").mkdir()

    processed_jobs = [
        {
            "title": "Assistant Manager",
            "company": "Farmfoods",
            "link": "http://example.com/job1",
            "letter_preview": "This is the drafted letter body.",
        }
    ]

    send_email(processed_jobs)

    assert len(fake_smtp.sent_messages) == 1
    msg = fake_smtp.sent_messages[0]
    assert "Review" in msg["Subject"]
    body = msg.get_body(preferencelist=("plain",)).get_content()
    # Review-queue framing: must warn Glen these are drafts, not sent.
    assert "AI-DRAFTED" in body
    assert "not sent applications" in body
    # The actual letter text must be visible in the body itself.
    assert "This is the drafted letter body." in body
    assert "Assistant Manager" in body
    assert "Farmfoods" in body
    assert "http://example.com/job1" in body


def test_send_email_no_jobs_sends_clear_empty_notice(fake_smtp, tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("main.OUTPUT_DIR", tmp_path / "outputs")

    send_email([])

    assert len(fake_smtp.sent_messages) == 1
    msg = fake_smtp.sent_messages[0]
    assert "No New Roles" in msg["Subject"]


def test_apply_critic_pass_is_a_noop_when_disabled(monkeypatch):
    monkeypatch.setattr("main.CRITIC_PASS_ENABLED", False)
    called = {"n": 0}
    monkeypatch.setattr(
        "main.run_critic_pass", lambda *a, **k: called.update(n=called["n"] + 1)
    )

    cv, letter = apply_critic_pass("Title", "Corp", "original cv", "original letter")

    assert (cv, letter) == ("original cv", "original letter")
    assert called["n"] == 0  # must not spend a Gemini call when disabled


def test_apply_critic_pass_keeps_original_on_no_changes(monkeypatch):
    monkeypatch.setattr("main.CRITIC_PASS_ENABLED", True)
    monkeypatch.setattr("main.run_critic_pass", lambda *a, **k: "NO_CHANGES")

    cv, letter = apply_critic_pass("Title", "Corp", "original cv", "original letter")

    assert (cv, letter) == ("original cv", "original letter")


def test_apply_critic_pass_returns_revised_content(monkeypatch):
    monkeypatch.setattr("main.CRITIC_PASS_ENABLED", True)
    revised = (
        "---TAILORED CV LATEX---\nTIGHTER CV\n"
        "---COVER LETTER LATEX---\nTIGHTER LETTER"
    )
    monkeypatch.setattr("main.run_critic_pass", lambda *a, **k: revised)

    cv, letter = apply_critic_pass("Title", "Corp", "original cv", "original letter")

    assert cv == "TIGHTER CV"
    assert letter == "TIGHTER LETTER"


def test_apply_critic_pass_keeps_original_when_critic_response_unparseable(
    monkeypatch,
):
    monkeypatch.setattr("main.CRITIC_PASS_ENABLED", True)
    monkeypatch.setattr("main.run_critic_pass", lambda *a, **k: "garbage, no markers")

    cv, letter = apply_critic_pass("Title", "Corp", "original cv", "original letter")

    assert (cv, letter) == ("original cv", "original letter")


def test_apply_critic_pass_keeps_original_on_api_failure(monkeypatch):
    monkeypatch.setattr("main.CRITIC_PASS_ENABLED", True)
    monkeypatch.setattr("main.run_critic_pass", lambda *a, **k: None)

    cv, letter = apply_critic_pass("Title", "Corp", "original cv", "original letter")

    assert (cv, letter) == ("original cv", "original letter")


def test_build_application_pdfs_does_not_call_critic_by_default(
    job, templates, monkeypatch
):
    cv_template, letter_template = templates
    raw = "---TAILORED CV LATEX---\nCV\n---COVER LETTER LATEX---\nLETTER"
    critic_called = {"n": 0}
    monkeypatch.setattr("main.tailor_application", lambda *a, **k: raw)
    monkeypatch.setattr("main.compile_latex", lambda path, name: True)
    monkeypatch.setattr("main.get_pdf_page_count", lambda path: 1)
    monkeypatch.setattr(
        "main.run_critic_pass",
        lambda *a, **k: critic_called.update(n=critic_called["n"] + 1),
    )

    result = build_application_pdfs(job, "base cv", cv_template, letter_template)

    assert result == STATUS_PROCESSED
    assert critic_called["n"] == 0  # CRITIC_PASS_ENABLED defaults to False
