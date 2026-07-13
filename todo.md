# TODO — Make the generated CV & cover letter genuinely excellent

Goal: every PDF that lands in Glen's inbox should read like a strong, honest,
human-written application — one page, specific, quantified where truthful,
with zero "AI tells" — and sell Glen's real strengths (6 years of betting-shop
management: cash accountability, regulatory compliance, lone-working
responsibility, customer conflict handling) instead of generic service-speak.

Ordering matters: Phase 0 is the ceiling on everything else. A prompt cannot
invent what the base CV doesn't contain, and the honesty constraint (correctly)
forbids it from trying.

---

## Phase 0 — Fix the input data (interview Glen, ~30 minutes) 🔴 highest leverage

The current `inputs/base_cv.txt` has no numbers, no achievements, and several
ambiguities. Every generated CV inherits these gaps. Sit down with Glen and get:

- [ ] **Real numbers for William Hill & Ladbrokes** (only what he can defend in
      an interview — never estimate on his behalf):
  - Daily/weekly cash volume handled (e.g. "reconciled tills of £X,000 daily")
  - Team size supervised, if any; lone-shop responsibility if solo
  - Target performance ("hit monthly targets N months running", "top-X shop in region")
  - Compliance specifics: age-verification checks, self-exclusion scheme
    (GamStop/MOSES), Think 21/25, safer-gambling interactions logged, audits passed
  - Incidents handled: fraud spotting, disputes resolved, security events
- [ ] **What the Ladbrokes "recognition for exceptional support" actually was**
      (named award? letter? mystery-shopper score?) — a named thing beats the phrase.
- [ ] **Confirm the employer's legal/common name** — base CV says "Ladbroke Coral
      Group"; one generated CV mutated it to "Ladbroke \& Coral Group". It is
      probably "Ladbrokes Coral". A wrong employer name is an instant credibility
      hit. Lock the exact string in the base CV and forbid the model from editing
      employer names (see Phase 3).
- [ ] **Decide how to frame the university year** (Hertfordshire, Sept 2017–Apr 2018,
      Mathematics, not completed). An unexplained 7-month university line invites a
      negative inference. Options: "Completed first-year modules in pure maths and
      statistics before moving into full-time work" or drop it and lead with A-levels.
      Glen's call — but it must be deliberate, not silent.
- [ ] **Reality-check "Basic Python Programming."** If he can't talk about it for
      2 minutes in an interview, cut it. If real, name what he did with it.
- [ ] **Collect logistics that UK retail employers screen on:** driving licence,
      shift/weekend flexibility, notice period at William Hill, right to work
      (UK citizen — one line), and how far he'll commute from Durham DH1.
- [ ] **Get 3–4 sentences Glen writes himself** about why he wants to move / what
      he's good at, in his own words. These become voice seeds (Phase 3) so
      letters sound like him, not like a model.

## Phase 1 — Rewrite `inputs/base_cv.txt` with that material

- [ ] Convert duty bullets to achievement bullets. Pattern: *action + specifics +
      outcome*. "Handled high-volume cash transactions" → "Reconciled daily takings
      of £X with zero discrepancies across N years" (only with Glen's real figures).
- [ ] Cut or compress the noise roles. A paper round from 2013 and a takeaway job
      from 2016 dilute a CV with 6 years of management on it. Keep them only as
      single lines under "Earlier experience", or drop entirely.
- [ ] Add the logistics block (licence, flexibility, notice period) so the model
      can use it in letters — availability is often the deciding factor for
      retail-management hires.
- [ ] Keep the file strictly truthful — it is the honesty anchor the prompt
      enforces against. Nothing goes in it that Glen can't back up aloud.

## Phase 2 — Template & typography (make the PDF look designed, not defaulted)

- [x] Kill page numbers (`\pagestyle{empty}`) — done.
- [x] One-page fit at 10pt with tightened section spacing — done, verified by
      recompiling real output.
- [x] **Right-align dates.** Added a template-defined `\entryheader{title}{employer}{dates}`
      macro (title left, dates via `\hfill` flush right) so the AI fills in
      three fields instead of hand-writing raw LaTeX alignment — deterministic,
      less compile-error-prone. Verified: compiles clean, 1 page, dates render
      correctly right-aligned (checked via `pdftotext -layout`).
- [x] Added `cmap` + `T1` fontenc + `lmodern` + `microtype` to both templates
      (correct load order: cmap before fontenc). Also added
      `texlive-latex-recommended` to the CI apt-get line since that's the
      actual Debian/Ubuntu package providing these three .sty files — don't
      rely on it being pulled in transitively. Verified: recompiled the
      full 7-job CV, still fits 1 page, and confirmed via `pdftotext` that
      ligature words ("efficient", "office") extract with correct characters
      intact (this is the actual ATS-parsing risk cmap fixes).
- [x] **Put Glen's name in the output filenames**: now
      `Glen_Watts_CV_<Company>_<Title>.pdf` / `Glen_Watts_Cover_Letter_<Company>_<Title>.pdf`,
      not `<Company>_<Title>_CV.pdf`. Company+title kept in the name for
      uniqueness across multiple jobs at the same employer in one run.
      Verified by running `build_application_pdfs()` with mocked AI/compile
      calls and inspecting the actual files written to disk.
- [x] Letter template: removed `\today`. Reasoning: Phase 4 reframes the email
      as a review queue Glen reads before sending, so a generation-time date
      could go stale by the time he actually applies. Omitting the date
      entirely is standard/accepted for digitally-submitted cover letters.
      Verified: recompiles clean, layout intact, no leftover blank line.

## Phase 3 — Prompt engineering (kill the remaining AI tells)

Observed in real output and to be banned/fixed in `tailor_application()`:

- [x] **Extend the forbidden-phrase list.** Added all 9 to the FORBIDDEN WORDS
      AND PHRASES block, plus an explicit "open with something other than 'I am
      writing to apply for...' every single time" instruction.
- [x] **Ban quoting employer marketing slogans.** Added explicit rule with the
      real "sensational value" example as the illustration.
- [x] **Ban hedge-coinages** like "retail-like setting". Added explicit rule
      using that exact real example.
- [x] **Fix paragraph 3 honestly.** Rewritten: explicitly tells the model it
      cannot research the company beyond JOB DESCRIPTION and must not fake it;
      redirects to one concrete requirement-to-experience tie, plus logistics
      *only if BASE CV actually states them* (added this guard myself after
      drafting — my first version said "mention his notice period" unconditionally,
      which would have pushed the model to invent one, directly violating the
      HONESTY block below it. Caught and fixed before verification.)
- [x] **Vary rhythm.** Added explicit instruction against uniform bullet
      count/length across entries.
- [x] **Never alter proper nouns from the base CV.** Added explicit rule using
      the real "Ladbroke \& Coral Group" mutation as the counter-example.
      Verification for all of the above: confirmed the prompt f-string still
      builds without error (no brace mismatches) by actually calling
      `tailor_application()` with a mocked client, and full lint/test suite
      still passes (11 passed). Whether Gemini's real output actually honors
      the new phrasing needs checking against the next live run (Phase 5) —
      today's 20/day free-tier quota is already exhausted from earlier testing.
- [ ] **Inject Glen's voice seeds** (from Phase 0) into the prompt: "Where natural,
      reuse the candidate's own phrasing from these sentences." One recognisably
      human sentence per letter beats a page of polish. **Blocked on Phase 0** —
      no voice-seed sentences exist yet to inject.
- [x] Keep (do not weaken) the existing guards: NOT_SUITABLE gate, no invented
      qualifications, no names lifted from job descriptions, LaTeX escaping.
      Verified via grep that all four are still present in the prompt and
      enforced in code (including the NOT_SUITABLE check in the compress-retry
      path added later, which could easily have been missed).

## Phase 4 — Pipeline quality gates

- [x] **Persist NOT_SUITABLE verdicts.** Added a `status` column
      (`processed` / `unsuitable` / not-persisted-`failed`). `job_exists()`
      needed no change — it already matches any row regardless of status,
      which is exactly right: skip re-processing both `processed` and
      `unsuitable` jobs, but let `failed` (compile errors etc.) retry since
      those rows are never inserted. `build_application_pdfs()` now returns
      one of `STATUS_PROCESSED` / `STATUS_UNSUITABLE` / `STATUS_FAILED`
      instead of a bare bool so `process_jobs()` can persist the first two
      and skip persisting the third.

      **Caught during verification, not before:** `Glen-Watts/Glen_Jobs`'s
      live `jobs.db` already exists with the *old* 4-column schema (no
      `status` column) from every run since 2026-06-15.
      `CREATE TABLE IF NOT EXISTS` does nothing to an existing table, so
      deploying this as-written would have thrown
      `OperationalError: table jobs has no column named status` on Glen's
      very next scheduled run and broken the pipeline outright. Reproduced
      this exact failure against a hand-built old-schema DB, then added a
      migration to `init_db()` (`PRAGMA table_info` check + `ALTER TABLE
      ... ADD COLUMN` when missing, defaulting existing rows to
      `processed` since that matches their real prior behavior). Verified:
      the reproduced failure now succeeds, pre-existing rows backfill to
      `processed`, and `init_db()` is idempotent (safe to call repeatedly,
      which `main.py`'s `__main__` block does every run). Added a
      regression test (`test_init_db_migrates_pre_status_column_database`)
      plus three new `process_jobs()`-level tests proving the actual bug
      end-to-end: an unsuitable job is persisted (not re-tailored), a
      failed job is not persisted (retries), a successful job is both
      persisted and included in the email list. 15/15 tests pass, lint clean.
- [x] **Enforce the one-page rule mechanically.** Added `get_pdf_page_count()`
      using `pdfinfo` (explicitly added `poppler-utils` to the CI apt-get
      line rather than assuming it's transitively present — same reasoning
      as the earlier `texlive-latex-recommended` addition). After the CV
      compiles, `build_application_pdfs()` checks the page count; if >1, it
      calls `tailor_application()` once more with a `CV_COMPRESS_INSTRUCTION`
      telling the model exactly how many pages it produced and to cut
      further, then recompiles. If it's still >1 after the one retry, it
      ships anyway with a logged warning rather than dropping an otherwise
      good application (a bounded retry, not a loop — this trades a
      possible rare 2-page CV for never silently losing a job Glen could
      have applied to).
      Costed: this is +1 Gemini call only on the (should be rare, now that
      Phase 1's length-prioritization prompt exists) jobs that overflow —
      not a fixed per-job cost.
      Verified three ways: (1) mocked-based unit tests proving the retry
      fires exactly once and the compress instruction is passed to the
      second call; (2) mocked test proving a persistent overflow still
      returns `STATUS_PROCESSED` after exactly 2 attempts, not an unbounded
      loop; (3) **real, non-mocked integration test** — compiled a
      deliberately bloated CV through the actual `cv_template.tex` with
      real `pdflatex`, confirmed `get_pdf_page_count()` correctly detected
      2 pages, then separately confirmed a genuinely 1-page CV reports
      exactly `1` (no false positive). 19/19 tests pass, lint clean.
- [x] **Put the cover-letter text in the email body** under each job entry.
      Added `delatex_for_display()` to reverse the LaTeX escapes the prompt
      instructs the model to apply (`\&`, `\%`, `\$`, `\#`, `\_`, `\{`,
      `\}`) so the plain-text preview reads naturally rather than showing
      backslash-escapes. `build_application_pdfs()` sets
      `job["letter_preview"]` on success; `send_email()` prints it under
      each job's title/company/link. Glen can now read every letter on his
      phone without unzipping PDFs.
- [x] **Reframe the email as a review queue, not finished goods.** Subject
      is now "Job Search: N Draft Application(s) to Review" and the body
      opens with "These are AI-DRAFTED applications, not sent applications.
      Read each one below before applying — the AI can get things wrong."
      Deviated from the todo's literal "why this matched" one-liner: with
      no per-job reasoning ever generated by the model, inventing one
      would just be fabricated confidence. Showing the actual drafted
      letter text lets Glen judge fit himself in the time it takes to
      read it — same 30-second goal, without manufacturing an explanation
      that doesn't exist.
      Verified: 4 new tests (`delatex_for_display` round-trip on all 6
      escape sequences, `build_application_pdfs` sets the preview
      correctly including on real escaped text, and two `send_email` tests
      that intercept `smtplib.SMTP_SSL` — no real network call — and
      assert on the actual constructed `EmailMessage` body/subject rather
      than trusting the code path ran; caught and fixed a real bug in my
      own first test attempt, where `msg.get_content()` doesn't work on a
      multipart message with a zip attached — needed `msg.get_body()`
      instead). Also confirmed no stray `job_applications.zip` was written
      to the repo root during the test run (the zip-write side effect is
      isolated via `monkeypatch.chdir(tmp_path)`). 29/29 tests pass, lint
      clean.
- [x] Optional (quota-permitting): **second-pass critic**. Implemented
      `run_critic_pass()` / `apply_critic_pass()` in `main.py`, behind
      `CRITIC_PASS_ENABLED` (env var `CRITIC_PASS=1`/`true`/`yes`, off by
      default). Reviews the drafted CV+letter as a skeptical North East
      England retail recruiter, targeting the same AI tells fixed in Phase
      3 (boilerplate, vagueness, uniform rhythm, slogan-quoting), and can
      either approve (`NO_CHANGES`) or return a tightened version. Design
      choices: runs on the *initial* draft, before the one-page compress
      retry. On any failure mode (API error, unparseable response,
      disabled) it falls back to the original draft unchanged — the critic
      pass can only ever improve output, never lose an application.
      **Known gap, caught on final review, not fixed:** if a job needs
      *both* the critic pass and a compress retry (overflowed one page),
      the compress retry calls `tailor_application()` fresh and replaces
      `cv_latex`/`letter_latex` outright — the shipped content in that
      specific case is the compressed draft, not the critic-reviewed one.
      This only matters when `CRITIC_PASS=1` and the CV overflows on the
      same job — rare, and the shipped content is still honesty-guarded
      and one-page, just not critic-polished. Left as-is rather than add
      a third possible Gemini call per job to close a rare edge case;
      worth fixing if `CRITIC_PASS` sees real use.
      Verified: confirmed `CRITIC_PASS_ENABLED` actually reads the env var
      correctly at import time for `1`/`true`/`0`/unset (ran `main.py` as
      a subprocess with each value, not just unit-tested); added 6 tests
      covering disabled-by-default (asserts zero extra calls), NO_CHANGES,
      revised content, unparseable response, API failure, and that
      `build_application_pdfs()` doesn't invoke the critic at all under
      default settings. 35/35 tests pass, lint clean.

## Phase 5 — Verify like a human would

- [ ] After the next real Actions run, open 3 PDFs and read them aloud. If any
      sentence couldn't come out of Glen's mouth in an interview, it's a Phase 3
      failure — tighten the prompt and re-test. **Blocked**: needs a live run;
      today's Gemini 20/day free-tier quota is already exhausted from earlier
      testing this session.
- [x] `pdftotext` every CV once after the Phase 2 font changes to confirm ATS-safe
      extraction — done as part of Phase 2 verification (checked ligature
      words "efficient"/"office" extract intact).
- [ ] ~~Grep generated `.tex` outputs for the banned-phrase list as a cheap
      regression test~~ — **investigated, not implemented**: the workflow
      runs `pytest` *before* `Run Job Scraper and AI Generator`
      (`.github/workflows/daily_run_workflow.yml` lines 28-34), so
      `outputs/` is always empty at test time in CI. A test scanning it
      would pass unconditionally in the one environment that matters and
      give false confidence. A real version of this check would need to
      run as a separate post-generation step (or a local/manual script
      Glen — or whoever maintains this — runs after inspecting a batch of
      real output), not a pytest case. Left undone rather than ship
      something that looks like coverage but isn't.
- [ ] Show Glen the before/after of one application and get his sign-off on the
      voice — he has to be comfortable claiming every line as his own.
      **Blocked**: needs Glen directly, same as Phase 0.

---

## Known constraints (do not "fix" these away)

- Gemini free tier: 20 requests/day on `gemini-2.5-flash`. SerpAPI free tier:
  250 searches/month. Both are already near their sustainable limits — every
  feature above must be quota-costed before shipping.
- The honesty guard is a feature, not a limitation. The route to a stronger CV
  is better *true* input from Glen (Phase 0), never looser generation rules.
