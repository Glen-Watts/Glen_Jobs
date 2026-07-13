import os
import re
import smtplib
import sqlite3
import subprocess
import time
import zipfile
from email.message import EmailMessage
from pathlib import Path

import requests
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

# Configuration
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
AI_API_KEY = os.getenv("AI_API_KEY")
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
SENDER_PASSWORD = os.getenv("SENDER_PASSWORD")
RECEIVER_EMAIL = os.getenv("RECEIVER_EMAIL")

# Optional second-pass quality critic: feeds the drafted CV/letter back to
# Gemini under a skeptical-recruiter persona to catch remaining AI tells.
# Doubles Gemini calls per successfully-tailored job, so it's opt-in only —
# the 20/day free-tier quota can't absorb this by default. Enable with
# CRITIC_PASS=1 on days with few expected new jobs, or on a paid tier.
CRITIC_PASS_ENABLED = os.getenv("CRITIC_PASS", "").strip().lower() in (
    "1",
    "true",
    "yes",
)

# AI setup
client = genai.Client(api_key=AI_API_KEY) if AI_API_KEY else None

# Paths
INPUT_DIR = Path("inputs")
OUTPUT_DIR = Path("outputs")
BASE_CV_PATH = INPUT_DIR / "base_cv.txt"
DB_PATH = Path("jobs.db")

# Search targeting: matched to Glen's actual experience (customer service
# management, cash handling, regulatory compliance) plus realistic entry-level
# growth paths (apprenticeships/trainee roles), not senior technical roles he
# has no qualifications for. Kept small to stay within the SerpAPI free-tier
# monthly search quota (250/month, shared across every run this cron makes).
JOB_QUERIES = [
    "Customer Service Manager",
    "Assistant Manager",
    "Compliance Officer",
    "Data Analyst Apprentice",
]
JOB_LOCATIONS = [
    "Durham, England",
    "Newcastle upon Tyne, England",
]
DATE_POSTED_CHIP = "date_posted:week"

# build_application_pdfs() outcomes. PROCESSED and UNSUITABLE are both
# persisted to jobs.db (via job_exists()) so the same job is never re-sent to
# Gemini on a later run — UNSUITABLE jobs would otherwise be re-tailored on
# every run for their whole date_posted:week window, burning the 20/day
# free-tier quota on jobs already rejected. FAILED is deliberately NOT
# persisted so a transient compile error gets retried next run.
STATUS_PROCESSED = "processed"
STATUS_UNSUITABLE = "unsuitable"
STATUS_FAILED = "failed"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        f"""CREATE TABLE IF NOT EXISTS jobs
                 (job_id TEXT PRIMARY KEY, title TEXT, company TEXT,
                  link TEXT, status TEXT NOT NULL DEFAULT '{STATUS_PROCESSED}',
                  date_found DATETIME DEFAULT CURRENT_TIMESTAMP)"""
    )
    # Migration: jobs.db files created before the status column existed
    # (e.g. the live database on Glen's Actions runner) need it added.
    # Every pre-existing row was saved under the old always-processed
    # behavior, so backfill them as STATUS_PROCESSED rather than leaving
    # them NULL.
    c.execute("PRAGMA table_info(jobs)")
    existing_columns = {row[1] for row in c.fetchall()}
    if "status" not in existing_columns:
        c.execute(
            f"ALTER TABLE jobs ADD COLUMN status TEXT NOT NULL "
            f"DEFAULT '{STATUS_PROCESSED}'"
        )
    conn.commit()
    conn.close()


def job_exists(job_id):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT 1 FROM jobs WHERE job_id = ?", (job_id,))
    exists = c.fetchone() is not None
    conn.close()
    return exists


def save_job(job_id, title, company, link, status=STATUS_PROCESSED):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO jobs (job_id, title, company, link, status) "
        "VALUES (?, ?, ?, ?, ?)",
        (job_id, title, company, link, status),
    )
    conn.commit()
    conn.close()


def get_pdf_page_count(pdf_path):
    """Return the PDF's page count via `pdfinfo`, or None if it can't be read."""
    try:
        result = subprocess.run(
            ["pdfinfo", str(pdf_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"Could not read page count for {pdf_path}: {e}")
        return None

    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":", 1)[1].strip())
    return None


def compile_latex(tex_path, output_name):
    print(f"Compiling {output_name}...")
    try:
        subprocess.run(
            [
                "pdflatex",
                "-interaction=nonstopmode",
                "-output-directory",
                str(OUTPUT_DIR),
                str(tex_path),
            ],
            check=True,
            capture_output=True,
        )
        # Cleanup auxiliary files
        for ext in [".aux", ".log", ".out"]:
            aux_file = OUTPUT_DIR / (tex_path.stem + ext)
            if aux_file.exists():
                aux_file.unlink()
        return True
    except FileNotFoundError:
        print(
            "pdflatex not found. Install LaTeX to compile PDFs."
            " On Ubuntu: sudo apt-get install texlive-latex-base"
        )
        return False
    except subprocess.CalledProcessError as e:
        # pdflatex reports errors on stdout and in the .log file, not stderr,
        # so e.stderr is normally empty — fall back to those for a useful message.
        detail = e.stdout.decode(errors="replace").strip() or e.stderr.decode(
            errors="replace"
        ).strip()
        log_file = OUTPUT_DIR / (tex_path.stem + ".log")
        if not detail and log_file.exists():
            detail = log_file.read_text(errors="replace")
        print(f"LaTeX Compilation Error for {output_name}:\n{detail[-1500:]}")
        return False


def search_jobs():
    print("Searching for jobs...")
    all_jobs = []

    for query in JOB_QUERIES:
        for location in JOB_LOCATIONS:
            params = {
                "engine": "google_jobs",
                "q": f"{query} in {location}",
                "location": location,
                "google_domain": "google.co.uk",
                "gl": "uk",
                "hl": "en",
                "api_key": SERPAPI_KEY,
                "chips": DATE_POSTED_CHIP,
            }
            try:
                response = requests.get("https://serpapi.com/search", params=params)
                response.raise_for_status()
                results = response.json()
                if "error" in results:
                    print(f"SerpAPI Error: {results['error']}")
                    continue
                jobs = results.get("jobs_results", [])
                print(f"Found {len(jobs)} jobs for {query} in {location}")
                all_jobs.extend(jobs)
            except requests.exceptions.HTTPError as e:
                print(f"HTTP Error searching for {query} in {location}: {e}")
            except Exception as e:
                print(f"Unexpected Error searching for {query} in {location}: {e}")

            time.sleep(1)

    return all_jobs


def tailor_application(job_title, company, description, base_cv, extra_instruction=""):
    print(f"Tailoring application for {job_title} at {company}...")

    prompt = rf"""
    {extra_instruction}
    You are a professional CV writer who writes in a direct,
    understated, and punchy British style.

    TASK:
    Tailor a CV and cover letter for the role below.
    Use SIMPLE, DIRECT ENGLISH.
    Absolutely NO "AI fluff," generic superlatives, or robotic transitions.

    JOB TITLE: {job_title}
    COMPANY: {company}
    JOB DESCRIPTION: {description}
    BASE CV: {base_cv}

    INSTRUCTIONS:
    1. CV CONTENT: Rewrite to match the job. Return it in RAW LATEX format
       suitable for the "(( CV_CONTENT ))" placeholder in my template.
       Include \section{{SUMMARY}}, \section{{WORK EXPERIENCE}},
       \section{{EDUCATION}}, and \section{{SKILLS}}.
       Use \begin{{itemize}} for bullets.
       - For every job in WORK EXPERIENCE and every entry in EDUCATION that
         gets full detail, start it with exactly this macro (already defined
         in the template, do not redefine it):
         \entryheader{{Job Title}}{{Employer - Location}}{{Start -- End}}
         Do NOT hand-write "\textbf{{...}} | ... | dates" lines — always use
         \entryheader so dates align correctly on the page.
       - LENGTH IS CRITICAL: this must fit on a SINGLE A4 page at 10pt.
         Do not include every role from BASE CV in full detail — that
         will not fit and produces an unprofessional CV with a near-empty
         second page.
       - Give full detail (\entryheader + 2-3 bullets) only to the 3-4 roles
         most relevant/recent to this specific job.
       - For older or less relevant roles, either omit them or compress
         them into a single line each (job title, employer, dates, no
         bullets) under a brief "EARLIER EXPERIENCE" subheading.
       - Limit SKILLS to at most 6 items, written as a compact list.
    2. COVER LETTER CONTENT: Max 200-250 words. Return it in RAW LATEX format
       suitable for the "(( LETTER_CONTENT ))" placeholder in my template.
       - Paragraph 1: Direct opening and immediate value proposition.
       - Paragraph 2: Connect his actual background (customer service
         management, cash handling, regulatory compliance) to what this
         specific role actually needs. Do not invent a connection that
         isn't there.
       - Paragraph 3: You cannot research {company} beyond what's in JOB
         DESCRIPTION, so do not pretend to — do not paraphrase or quote
         the company's own marketing language back at them (that reads
         as fake research, not genuine interest). Instead, pick ONE
         specific requirement or duty stated in JOB DESCRIPTION and
         state plainly how his real experience covers it. Then, ONLY
         if BASE CV states relevant logistics (e.g. location, notice
         period, availability), mention the ones that matter for this
         role — do not invent logistics BASE CV doesn't mention. End
         with one short sentence inviting further discussion (e.g.
         availability for an interview).
       - Do NOT include a greeting (e.g., "Dear Hiring Manager") or a
         sign-off. I have already included these.
       - Do NOT mention any person's name found in the job description
         (recruiter, hiring manager, other candidate, etc). Only refer to
         {company} and the role itself.
       - CRITICAL: Escape all special LaTeX characters (e.g., \&, \%).

    CRITICAL TONE GUIDE & ANTI-FLUFF:
    - Tone: Professional, grounded, and slightly understated.
    - Style: Plain English. Short, factual sentences.
    - FORBIDDEN WORDS AND PHRASES: Do not use "delve", "testament",
      "tapestry", "seamlessly", "thrilled", "excited", "passionate",
      "pivotal", "spearheaded", "proven track record", "Adept at",
      "aligns directly with", "I am writing to apply for", "prepared to
      contribute effectively", "demonstrating a focus on", "fast-paced
      environment(s)", "Seeking to apply", or "results-focused". These
      are the most common phrases in AI-written and template CVs — a
      recruiter has read them hundreds of times. State facts, not
      emotions, and open the cover letter with something other than
      "I am writing to apply for..." every single time.
    - Do NOT quote or closely paraphrase the employer's own marketing
      language, slogans, or mission-statement wording back at them (e.g.
      if the job ad says "we offer sensational value", do not repeat
      "sensational value" in the letter). It reads as flattery lifted
      from the ad, not genuine interest.
    - Do NOT invent vague hedge-phrases to describe the employer or
      role (e.g. "retail-like setting" for a betting shop). If BASE CV
      says it's a licensed betting shop, call it that.
    - Vary sentence and bullet length. Do not give every job entry
      exactly the same number of bullets or every bullet the same
      length — a uniform, list-like cadence across the whole document
      is itself a giveaway that it wasn't written by a person.
    - NEVER change the spelling of any employer name, place name, or
      qualification name found in BASE CV — copy them character-for-
      character. Do not "correct" or embellish them (e.g. do not turn
      "Ladbroke Coral Group" into "Ladbroke \& Coral Group").

    HONESTY (CRITICAL — DO NOT VIOLATE):
    - Only use skills, qualifications, and experience present in BASE CV.
      Never invent degrees, certifications, years of experience, or
      technical skills he doesn't have.
    - If this role is clearly entry-level/apprenticeship/trainee, write as
      a candidate seeking to start that path, not as someone who already
      has the specialist experience.
    - If this role requires qualifications far beyond BASE CV (e.g. a
      completed relevant degree, a professional certification, or several
      years of specialist technical experience he does not have), do not
      paper over the gap with vague language. Instead, return exactly the
      text NOT_SUITABLE as the entire response, with nothing else.

    FORMAT:
    ---TAILORED CV LATEX---
    [Latex content here]
    ---COVER LETTER LATEX---
    [Latex content here]

    Return ONLY the requested sections.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Error generating AI content: {e}")
        return None


def sanitize_filename(text: str, max_length: int = 60) -> str:
    text = re.sub(r"[^A-Za-z0-9 _-]", "", text)
    text = re.sub(r"\s+", "_", text.strip())
    return text[:max_length] or "untitled"


# Escapes the prompt instructs the model to apply for LaTeX safety. Reversed
# here to show readable plain text in the review email — the PDF itself
# still uses the original LaTeX-escaped version.
_LATEX_ESCAPES_TO_PLAIN = {
    r"\&": "&",
    r"\%": "%",
    r"\$": "$",
    r"\#": "#",
    r"\_": "_",
    r"\{": "{",
    r"\}": "}",
}


def delatex_for_display(text: str) -> str:
    for latex, plain in _LATEX_ESCAPES_TO_PLAIN.items():
        text = text.replace(latex, plain)
    return text.strip()


def parse_tailored_response(raw_response):
    """Split a tailor_application() response into (cv_latex, letter_latex).

    Raises ValueError if the expected markers aren't present.
    """
    try:
        cv_latex = (
            raw_response.split("---TAILORED CV LATEX---")[1]
            .split("---COVER LETTER LATEX---")[0]
            .strip()
        )
        letter_latex = raw_response.split("---COVER LETTER LATEX---")[1].strip()
    except IndexError as e:
        raise ValueError("response missing expected section markers") from e

    cv_latex = cv_latex.replace("```latex", "").replace("```", "").strip()
    letter_latex = letter_latex.replace("```latex", "").replace("```", "").strip()
    return cv_latex, letter_latex


def run_critic_pass(job_title, company, cv_latex, letter_latex):
    """One extra Gemini call: review the drafted CV/letter as a skeptical
    recruiter would, and either approve them or return tightened versions.

    Returns the raw model response text, or None on API failure.
    """
    print(f"Running critic pass for {job_title} at {company}...")

    prompt = rf"""
    You are a skeptical, experienced UK retail/service-sector recruiter in
    North East England, reviewing a CV and cover letter just drafted for a
    real candidate applying to {job_title} at {company}.

    Find anything that reads as AI-written, vague, generic, or inconsistent,
    and fix it. Be ruthless about:
    - Corporate-sounding boilerplate or CV-mill phrasing.
    - Sentences that don't sound like something a real person would say.
    - Vagueness where a concrete detail already present in the drafts could
      be used instead.
    - Uniform, robotic bullet-point rhythm (every entry the same length).
    - Any line that quotes the employer's own marketing language back at them.
    - Factual inconsistencies between the CV and the cover letter.

    Do NOT invent new facts, qualifications, or experience that isn't
    already present in the drafts below. Only tighten, cut, and rephrase
    what's there. Do not change any employer name, place name, or
    qualification name.

    CURRENT CV (LaTeX):
    {cv_latex}

    CURRENT COVER LETTER (LaTeX):
    {letter_latex}

    If both are already good and need no changes, respond with exactly:
    NO_CHANGES

    Otherwise, return the revised versions in exactly this format:
    ---TAILORED CV LATEX---
    [revised CV LaTeX]
    ---COVER LETTER LATEX---
    [revised cover letter LaTeX]

    Return ONLY one of these two outputs, nothing else.
    """

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Error running critic pass for {job_title} at {company}: {e}")
        return None


def apply_critic_pass(job_title, company, cv_latex, letter_latex):
    """Run the critic pass if CRITIC_PASS_ENABLED, else return the pair
    unchanged. Also returns the pair unchanged if the critic pass fails,
    finds nothing to change, or its response can't be parsed — the critic
    pass can only ever tighten content, never lose an application.
    """
    if not CRITIC_PASS_ENABLED:
        return cv_latex, letter_latex

    critic_response = run_critic_pass(job_title, company, cv_latex, letter_latex)
    if not critic_response or critic_response.strip() == "NO_CHANGES":
        return cv_latex, letter_latex

    try:
        return parse_tailored_response(critic_response)
    except ValueError:
        print(
            f"Could not parse critic response for {job_title} at "
            f"{company}, keeping original draft"
        )
        return cv_latex, letter_latex


# A CV overflowing to a second page (often by a single orphaned line) reads
# as unprofessional. The prompt already instructs a one-page target, but
# that's not a guarantee, so this is a mechanical backstop: one extra
# Gemini call to compress, only when the first attempt didn't fit.
CV_COMPRESS_INSTRUCTION = (
    "IMPORTANT: Your previous attempt at this CV did not fit on a single "
    "A4 page — it ran to {page_count} pages. Cut more content: drop or "
    "further compress older/less relevant roles, shorten bullets, and "
    "reduce SKILLS further if needed. It MUST fit one page this time."
)


def build_application_pdfs(job, base_cv, cv_template, letter_template):
    """Generate and compile the CV/cover-letter PDFs for one job.

    Returns one of STATUS_PROCESSED, STATUS_UNSUITABLE, or STATUS_FAILED.
    Only STATUS_PROCESSED means real PDF attachments exist and the job
    should be emailed. STATUS_UNSUITABLE and STATUS_PROCESSED both get
    persisted to jobs.db so the job is never re-sent to Gemini on a later
    run; STATUS_FAILED is not persisted, so a transient compile error
    retries next run instead of being lost.
    """
    title = job["title"]
    company = job["company"]
    description = job["description"]

    raw_response = tailor_application(title, company, description, base_cv)
    if not raw_response:
        return STATUS_FAILED
    if raw_response.strip() == "NOT_SUITABLE":
        print(f"Skipping unsuitable role: {title} at {company}")
        return STATUS_UNSUITABLE

    try:
        cv_latex, letter_latex = parse_tailored_response(raw_response)
    except ValueError:
        print(f"Could not parse AI response for {title} at {company}")
        return STATUS_FAILED

    cv_latex, letter_latex = apply_critic_pass(title, company, cv_latex, letter_latex)

    job_slug = f"{sanitize_filename(company)}_{sanitize_filename(title)}"

    cv_full = cv_template.replace("(( CV_CONTENT ))", cv_latex)
    cv_name = f"Glen_Watts_CV_{job_slug}"
    cv_tex_path = OUTPUT_DIR / f"{cv_name}.tex"
    cv_tex_path.write_text(cv_full)
    cv_ok = compile_latex(cv_tex_path, f"{cv_name}.pdf")

    if cv_ok:
        page_count = get_pdf_page_count(OUTPUT_DIR / f"{cv_name}.pdf")
        if page_count is not None and page_count > 1:
            print(
                f"CV for {title} at {company} ran to {page_count} pages, "
                "retrying once with a compress instruction"
            )
            retry_response = tailor_application(
                title,
                company,
                description,
                base_cv,
                extra_instruction=CV_COMPRESS_INSTRUCTION.format(
                    page_count=page_count
                ),
            )
            if retry_response and retry_response.strip() != "NOT_SUITABLE":
                try:
                    retry_cv_latex, retry_letter_latex = parse_tailored_response(
                        retry_response
                    )
                except ValueError:
                    retry_cv_latex = None
                if retry_cv_latex is not None:
                    cv_latex, letter_latex = retry_cv_latex, retry_letter_latex
                    cv_full = cv_template.replace("(( CV_CONTENT ))", cv_latex)
                    cv_tex_path.write_text(cv_full)
                    cv_ok = compile_latex(cv_tex_path, f"{cv_name}.pdf")
                    if cv_ok:
                        page_count = get_pdf_page_count(
                            OUTPUT_DIR / f"{cv_name}.pdf"
                        )
                        if page_count is not None and page_count > 1:
                            print(
                                f"CV for {title} at {company} still {page_count} "
                                "pages after compress retry — sending as-is"
                            )

    letter_full = letter_template.replace("(( LETTER_CONTENT ))", letter_latex)
    letter_name = f"Glen_Watts_Cover_Letter_{job_slug}"
    letter_tex_path = OUTPUT_DIR / f"{letter_name}.tex"
    letter_tex_path.write_text(letter_full)
    letter_ok = compile_latex(letter_tex_path, f"{letter_name}.pdf")

    if not (cv_ok and letter_ok):
        print(f"PDF compilation failed for {title} at {company}, will retry next run")
        return STATUS_FAILED

    # Let process_jobs()/send_email() show the letter text in the review
    # email without Glen having to unzip PDFs to see what was drafted.
    job["letter_preview"] = delatex_for_display(letter_latex)

    return STATUS_PROCESSED


def process_jobs():
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir()

    if not BASE_CV_PATH.exists():
        print("Base CV not found. Please create inputs/base_cv.txt")
        return []

    base_cv = BASE_CV_PATH.read_text()

    cv_template_path = Path("cv/cv_template.tex")
    letter_template_path = Path("cv/letter_template.tex")
    if not cv_template_path.exists() or not letter_template_path.exists():
        print("LaTeX templates not found in cv/ directory.")
        return []

    cv_template = cv_template_path.read_text()
    letter_template = letter_template_path.read_text()

    jobs = search_jobs()
    processed_jobs = []

    for raw_job in jobs:
        job_id = raw_job.get("job_id")
        if not job_id or job_exists(job_id):
            continue

        job = {
            "title": raw_job.get("title"),
            "company": raw_job.get("company_name"),
            "link": raw_job.get("related_links", [{}])[0].get("link", "No link"),
            "description": raw_job.get("description", ""),
        }

        try:
            status = build_application_pdfs(job, base_cv, cv_template, letter_template)
        except Exception as e:
            print(f"Error processing {job['title']} at {job['company']}: {e}")
            continue

        if status in (STATUS_PROCESSED, STATUS_UNSUITABLE):
            save_job(job_id, job["title"], job["company"], job["link"], status=status)
        if status == STATUS_PROCESSED:
            processed_jobs.append(job)
        time.sleep(2)

    return processed_jobs


def send_email(processed_jobs):
    msg = EmailMessage()
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL

    if not processed_jobs:
        msg["Subject"] = "Job Search: No New Roles Found Today"
        msg.set_content("No new job listings were found today.")
    else:
        role_word = "role" if len(processed_jobs) == 1 else "roles"
        msg["Subject"] = (
            f"Job Search: {len(processed_jobs)} Draft Application"
            f"{'s' if len(processed_jobs) != 1 else ''} to Review"
        )

        zip_name = "job_applications.zip"
        with zipfile.ZipFile(zip_name, "w") as zipf:
            for file in OUTPUT_DIR.glob("*.pdf"):
                zipf.write(file, file.name)

        body = (
            f"These are AI-DRAFTED applications, not sent applications. "
            f"Read each one below before applying — the AI can get things "
            f"wrong. {len(processed_jobs)} {role_word} matched today.\n\n"
        )
        for j in processed_jobs:
            body += "-" * 60 + "\n"
            body += f"{j['title']} at {j['company']}\n"
            body += f"Job posting: {j['link']}\n\n"
            body += "Draft cover letter:\n"
            body += j.get("letter_preview", "(preview unavailable)") + "\n\n"
        body += "-" * 60 + "\n"
        body += (
            "Tailored PDF CVs and cover letters for all roles above are "
            "attached (zipped)."
        )

        msg.set_content(body)

        with open(zip_name, "rb") as f:
            file_data = f.read()
            msg.add_attachment(
                file_data,
                maintype="application",
                subtype="zip",
                filename=zip_name,
            )

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(SENDER_EMAIL, SENDER_PASSWORD)
            smtp.send_message(msg)
        print("Email sent successfully.")
    except Exception as e:
        print(f"Error sending email: {e}")


if __name__ == "__main__":
    init_db()
    jobs_done = process_jobs()
    send_email(jobs_done)
    print("Done.")
