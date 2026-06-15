# 🚀 Job Search Automation Engine: Project Roadmap

This document outlines the step-by-step process for building an automated pipeline that scrapes daily job postings, tailors a base CV, and drafts cover letters using Gemini CLI and GitHub Actions.

## Phase 1: Prerequisites & Account Setup
*Goal: Secure all the necessary API keys and accounts.*

- [x] **Install Git and Python:** (Already available in environment)
- [ ] **Create a GitHub Account:** (User responsibility)
- [ ] **Get Free AI API Key:**
    - We will use a free tier provider (e.g., Hugging Face, Groq free tier, or Google Gemini free tier).
    - For this implementation, we'll aim for Google Gemini (since it's Gemini CLI) or a similar free alternative.
- [ ] **Get a Job Search API Key:**
    - Sign up for SerpAPI (serpapi.com) for Google Jobs API.
    - Generate the API key.
- [ ] **Set up an App Password for Email:**
    - Generate a 16-character app password for the sender email (e.g., Gmail).

---

## Phase 2: Local Project Initialization
*Goal: Prepare the local environment and project structure.*

- [x] **Create the Project Structure:**
    - `inputs/`: For base CV and templates.
    - `outputs/`: For generated applications.
    - `.github/workflows/`: For automation.
- [x] **Configure .gitignore:** Prevent leaking keys and local db.
- [x] **Initialize README.md:** Project overview.
- [x] **Modernize Tooling:** Use `uv` for dependencies, `ruff` for linting, and `pytest` for tests.
- [x] **LaTeX Integration:** Professional PDF generation for CVs and cover letters.

---

## Phase 3: Building the Base Assets
*Goal: Provide the AI with the raw material it needs.*

- [x] **Draft `inputs/base_cv.txt`:** Plain text version of the CV.
- [x] **Draft `.env` (Local Environment Variables):** Using placeholders initially.

---

## Phase 4: Generating the Core Logic
*Goal: Write the Python scripts for scraping, AI generation, and emailing.*

- [x] **Create `pyproject.toml`:** Managed by `uv`.
- [x] **Create `main.py`:**
    - Load environment variables.
    - Search jobs via SerpAPI (Google Jobs).
    - Manage state with `jobs.db` (SQLite) to avoid duplicates.
    - Tailor CV and draft cover letter using AI (LaTeX format).
    - Compile LaTeX to PDF using `pdflatex`.
    - Save outputs to `outputs/`.
    - Zip and email the results (PDFs).

---

## Phase 5: Local Testing & Refinement
*Goal: Ensure the pipeline works locally.*

- [x] **Install Python Dependencies:** (via `uv sync`).
- [x] **Run Linting:** (via `uv run ruff check .`).
- [x] **Run Tests:** (via `uv run pytest`).
- [ ] **Verify Outputs and Email Delivery:** (Requires valid API keys).
- [ ] **Refine AI Prompts:** (Ongoing as needed).

---

## Phase 6: Deployment & Automation
*Goal: Automate daily runs via GitHub Actions.*

- [x] **Create GitHub Actions Workflow (`daily_run.yml`).**
- [ ] **Push to GitHub:** (User action required).
- [ ] **Configure GitHub Secrets:** (User action required: `AI_API_KEY`, `SERPAPI_KEY`, `SENDER_EMAIL`, `SENDER_PASSWORD`, `RECEIVER_EMAIL`).

---

## Phase 7: Operation & Maintenance
*Goal: Daily workflow management.*

- [ ] **Daily Review of Emails.**
- [ ] **Manual Submissions.**
- [ ] **Iterative CV Updates.**
