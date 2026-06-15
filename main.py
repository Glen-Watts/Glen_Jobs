import os
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

# AI setup
client = genai.Client(api_key=AI_API_KEY)

# Paths
INPUT_DIR = Path("inputs")
OUTPUT_DIR = Path("outputs")
BASE_CV_PATH = INPUT_DIR / "base_cv.txt"
DB_PATH = Path("jobs.db")


def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS jobs
                 (job_id TEXT PRIMARY KEY, title TEXT, company TEXT,
                  link TEXT, date_found DATETIME DEFAULT CURRENT_TIMESTAMP)"""
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


def save_job(job_id, title, company, link):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO jobs (job_id, title, company, link) VALUES (?, ?, ?, ?)",
        (job_id, title, company, link),
    )
    conn.commit()
    conn.close()


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
    except subprocess.CalledProcessError as e:
        print(f"LaTeX Compilation Error for {output_name}: {e.stderr.decode()}")
        return False


def search_jobs():
    print("Searching for jobs...")
    queries = [
        "Junior Analyst",
        "Data Analyst",
        "Customer Success",
    ]
    locations = [
        "Newcastle upon Tyne",
    ]
    all_jobs = []

    for query in queries:
        for location in locations:
            params = {
                "engine": "google_jobs",
                "q": f"{query} in {location}",
                "api_key": SERPAPI_KEY,
                "chips": "date_posted:today",
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


def tailor_application(job_title, company, description, base_cv):
    print(f"Tailoring application for {job_title} at {company}...")

    prompt = rf"""
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
    2. COVER LETTER CONTENT: Max 200-250 words. Return it in RAW LATEX format
       suitable for the "(( LETTER_CONTENT ))" placeholder in my template.
       - Paragraph 1: Direct opening and immediate value proposition.
       - Paragraph 2: Demonstrate how your background aligns specifically
         with this field (e.g., bridging operational management and
         quantitative aptitude).
       - Paragraph 3: Include specific research or a direct reference
         to the {company} or the specifics of the {job_title} role from the
         job description to prove this isn't a generic application.
       - Do NOT include a greeting (e.g., "Dear Hiring Manager") or a
         sign-off. I have already included these.
       - CRITICAL: Escape all special LaTeX characters (e.g., \&, \%).

    CRITICAL TONE GUIDE & ANTI-FLUFF:
    - Tone: Professional, grounded, and slightly understated.
    - Style: Plain English. Short, factual sentences.
    - FORBIDDEN WORDS: Do not use "delve", "testament", "tapestry",
      "seamlessly", "thrilled", "excited", "passionate", "pivotal", or
      "spearheaded". State facts, not emotions.

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


def process_jobs():
    if not OUTPUT_DIR.exists():
        OUTPUT_DIR.mkdir()

    if not BASE_CV_PATH.exists():
        print("Base CV not found. Please create inputs/base_cv.txt")
        return

    with open(BASE_CV_PATH) as f:
        base_cv = f.read()

    # Load templates
    cv_template_path = Path("cv/cv_template.tex")
    letter_template_path = Path("cv/letter_template.tex")

    if not cv_template_path.exists() or not letter_template_path.exists():
        print("LaTeX templates not found in cv/ directory.")
        return

    with open(cv_template_path) as f:
        cv_template = f.read()
    with open(letter_template_path) as f:
        letter_template = f.read()

    jobs = search_jobs()
    processed_jobs = []

    for job in jobs:
        job_id = job.get("job_id")
        title = job.get("title")
        company = job.get("company_name")
        link = job.get("related_links", [{}])[0].get("link", "No link")
        description = job.get("description", "")

        if not job_id or job_exists(job_id):
            continue

        raw_response = tailor_application(title, company, description, base_cv)
        if raw_response:
            try:
                cv_latex = (
                    raw_response.split("---TAILORED CV LATEX---")[1]
                    .split("---COVER LETTER LATEX---")[0]
                    .strip()
                )
                letter_latex = raw_response.split("---COVER LETTER LATEX---")[1].strip()

                # Sanitize LaTeX
                cv_latex = cv_latex.replace("```latex", "").replace("```", "").strip()
                letter_latex = (
                    letter_latex.replace("```latex", "").replace("```", "").strip()
                )

                base_name = f"{company.replace(' ', '_')}_{title.replace(' ', '_')}"

                # Generate CV
                cv_full = cv_template.replace("(( CV_CONTENT ))", cv_latex)
                cv_tex_path = OUTPUT_DIR / f"{base_name}_CV.tex"
                with open(cv_tex_path, "w") as f:
                    f.write(cv_full)
                compile_latex(cv_tex_path, f"{base_name}_CV.pdf")

                # Generate Letter
                letter_full = letter_template.replace(
                    "(( LETTER_CONTENT ))", letter_latex
                )
                letter_tex_path = OUTPUT_DIR / f"{base_name}_Cover_Letter.tex"
                with open(letter_tex_path, "w") as f:
                    f.write(letter_full)
                compile_latex(letter_tex_path, f"{base_name}_Cover_Letter.pdf")

                save_job(job_id, title, company, link)
                processed_jobs.append(
                    {"title": title, "company": company, "link": link}
                )
                time.sleep(2)
            except Exception as e:
                print(f"Error processing AI response for {title}: {e}")

    return processed_jobs


def send_email(processed_jobs):
    if not processed_jobs:
        print("No new jobs found. Skipping email.")
        return

    zip_name = "job_applications.zip"
    with zipfile.ZipFile(zip_name, "w") as zipf:
        for file in OUTPUT_DIR.glob("*.pdf"):
            zipf.write(file, file.name)

    msg = EmailMessage()
    msg["Subject"] = f"Daily Job Applications - {len(processed_jobs)} New Roles"
    msg["From"] = SENDER_EMAIL
    msg["To"] = RECEIVER_EMAIL
    
    body = f"Found and processed {len(processed_jobs)} new job listings.\n\n"
    for j in processed_jobs:
        body += f"- {j['title']} at {j['company']}\n  Link: {j['link']}\n\n"
    body += "Tailored PDF CVs and cover letters are attached."
    
    msg.set_content(body)

    with open(zip_name, "rb") as f:
        file_data = f.read()
        msg.add_attachment(
            file_data, maintype="application", subtype="zip", filename=zip_name
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
