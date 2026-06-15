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
