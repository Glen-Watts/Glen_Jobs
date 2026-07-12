# CLAUDE.md

Guidance for Claude Code when working in this repository.

## What this is

An automated job-application pipeline built **for Glen** (not Oscar). It runs daily
on Glen's own GitHub account via GitHub Actions:

1. Searches Google Jobs (via SerpAPI) for roles matching Glen's target queries/locations.
2. Skips any job already seen (tracked in `jobs.db`).
3. Sends each new job + Glen's base CV to Gemini, which returns a tailored CV and
   cover letter in LaTeX.
4. Compiles both to PDF (`pdflatex`) using the templates in `cv/`.
5. Zips the PDFs and emails them to Glen.

## Live deployment — read this before touching workflow/secrets

- **The real, running deployment is `github.com/Glen-Watts/Glen_Jobs`.** Its Actions
  cron (`.github/workflows/daily_run_workflow.yml`, weekdays 08:00 UTC) has been
  running successfully since 2026-06-15.
- **`git remote origin` for this local checkout points at `Glen-Watts/Glen_Jobs`
  directly** (Oscar has collaborator/push access). This is intentional — there is no
  separate "Oscar's fork" deployment anymore, and there should not be one. Do not
  point origin back at `OscarHickman/Glen_Jobs` or push workflow-triggering changes
  anywhere except Glen's repo.
- **Never run/trigger GitHub Actions, or push a `.github/workflows/*` change, under
  Oscar's own GitHub account or any repo Oscar owns.** All Actions runs, minutes, and
  API keys for this project belong to Glen's account. This was an explicit user
  instruction — treat it as a hard constraint, not a preference.
- Repo secrets live only in `Glen-Watts/Glen_Jobs` → Settings → Secrets:
  `AI_API_KEY` (Gemini), `SERPAPI_KEY`, `SENDER_EMAIL`, `SENDER_PASSWORD`
  (Gmail app password), `RECEIVER_EMAIL`. Never hardcode these; `main.py` reads them
  via `os.getenv` / `.env` locally.
- Before pushing, `git pull --ff-only origin main` first — the live repo gets
  iterated on directly (workflow fixes, lint fixes) and can drift ahead of any local
  checkout.

## Local development

```bash
uv sync                  # install deps
uv run ruff check .      # lint (also runs in CI)
uv run pytest            # tests (also runs in CI)
uv run python main.py    # full pipeline run — needs .env populated and pdflatex installed
```

`.env` (gitignored) needs the same five variables as the repo secrets above. Running
`main.py` locally with real keys will hit paid APIs and send a real email to Glen —
don't run it casually.

## Key files

- `main.py` — the entire pipeline (search → tailor → compile → email). Single file by
  design; keep it that way unless it grows past ~300 lines.
- `inputs/base_cv.txt` — Glen's plain-text base CV, the source Gemini tailors from.
- `cv/cv_template.tex`, `cv/letter_template.tex` — LaTeX templates with
  `(( CV_CONTENT ))` / `(( LETTER_CONTENT ))` placeholders filled in per job.
- `jobs.db` — SQLite dedup store (`job_id` primary key), gitignored, lives only in
  the Actions runner / local checkout.
- `outputs/`, `job_applications.zip` — generated per run, gitignored.
- `.github/workflows/daily_run_workflow.yml` — the cron. Runs ruff + pytest before
  the actual pipeline step, so CI failures block a run.

## Working on this repo

- This is Glen's tool, tuned to Glen's CV and target roles. `JOB_QUERIES` /
  `JOB_LOCATIONS` in `main.py` are matched to his actual experience (customer
  service management, cash handling, regulatory compliance) plus realistic
  entry-level growth paths (apprenticeships/trainee roles) — not senior
  technical roles requiring quals he doesn't have. Don't widen these without
  checking SerpAPI quota headroom first (`GET https://serpapi.com/account`
  with the key — free plan is 250 searches/month, shared across every cron
  run); each extra query × location combination is one search per run.
- The AI prompt in `tailor_application()` enforces a specific tone (direct, no
  corporate fluff, banned words list) and an honesty constraint: it must not
  invent qualifications Glen doesn't have, and returns the literal string
  `NOT_SUITABLE` for roles clearly beyond his experience rather than
  fabricating a fit. `build_application_pdfs()` treats that as "skip, don't
  email" — preserve that behavior when editing the pipeline.
- A job is only marked processed (deduped in `jobs.db`, included in the
  email) once both PDFs actually compile — don't reintroduce marking a job
  "done" on partial failure, or Glen ends up with an email entry with no
  attached CV that never retries.
- Location strings in `JOB_LOCATIONS` must stay disambiguated (e.g.
  `"Durham, England"`, not bare `"Durham"`) and `search_jobs()` must keep
  passing `gl="uk"` / `google_domain="google.co.uk"`. Without this, Google
  Jobs happily returns Durham, North Carolina / other US results — confirmed
  live (Harris Teeter, Public Storage, a Domino's on a real NC street address
  all showed up under a bare "Durham" query before this fix).
- Gemini's free tier caps `gemini-2.5-flash` at **20 requests/day total**
  (hit live while testing with a wiped `jobs.db`, which made ~39 jobs "new"
  at once). A normal day's *actually new* job count should stay well under
  that, but if it's ever exceeded, `build_application_pdfs()` correctly
  leaves the unprocessed jobs unmarked so they retry on the next run — don't
  "fix" that by force-marking them done.
