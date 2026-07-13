import sqlite3

import pytest

from main import init_db, job_exists, save_job


@pytest.fixture
def test_db(tmp_path, monkeypatch):
    db_path = tmp_path / "test_jobs.db"
    monkeypatch.setattr("main.DB_PATH", db_path)
    return db_path

def test_init_db(test_db):
    init_db()
    assert test_db.exists()
    
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
    assert c.fetchone() is not None
    conn.close()

def test_job_operations(test_db):
    init_db()
    job_id = "test_123"
    assert not job_exists(job_id)

    save_job(job_id, "Analyst", "Test Corp", "http://test.com")
    assert job_exists(job_id)

    # Check if data was saved correctly
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT title, company FROM jobs WHERE job_id = ?", (job_id,))
    row = c.fetchone()
    assert row == ("Analyst", "Test Corp")
    conn.close()


def test_init_db_migrates_pre_status_column_database(test_db):
    # Regression test: jobs.db files created before the status column
    # existed (this is the schema of the live database on Glen's Actions
    # runner as of this change) must not break when init_db() runs again.
    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE jobs
             (job_id TEXT PRIMARY KEY, title TEXT, company TEXT,
              link TEXT, date_found DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )
    c.execute(
        "INSERT INTO jobs (job_id, title, company, link) VALUES (?, ?, ?, ?)",
        ("pre-migration-job", "Old Title", "Old Corp", "http://old.com"),
    )
    conn.commit()
    conn.close()

    init_db()  # must not raise, and must backfill status on the old row
    save_job("post-migration-job", "New Title", "New Corp", "http://new.com")

    conn = sqlite3.connect(test_db)
    c = conn.cursor()
    c.execute("SELECT status FROM jobs WHERE job_id = ?", ("pre-migration-job",))
    assert c.fetchone() == ("processed",)
    c.execute("SELECT status FROM jobs WHERE job_id = ?", ("post-migration-job",))
    assert c.fetchone() == ("processed",)
    conn.close()
