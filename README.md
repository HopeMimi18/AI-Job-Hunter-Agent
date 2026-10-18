# AI Job Hunter — Starter MVP (Python)

A **local-first**, runnable foundation for a CV-based job agent. It can:

- Parse a PDF or DOCX resume **locally** and extract a candidate profile.
- Retrieve job adverts from **Adzuna** (your own API credentials) and specified public **Greenhouse** / **Lever** company boards.
- Rank them with a transparent rule-based score and eligibility review flags.
- Import a real job advert manually when it explicitly accepts applications by email.
- Prepare a factual cover letter, require approval, and **send the CV + letter to the employer's approved email address** using SMTP.
- Optionally auto-send only to exact *approved addresses* for manually verified email-application vacancies with high scores, no review flags, and a daily cap.
- Keep local application history, prevent repeat email applications, and send an email digest.

**It does NOT:** log in to or scrape LinkedIn; click LinkedIn Easy Apply; apply to arbitrary employer web forms; submit to Greenhouse/Lever (employer-issued submission keys would be required); use Amazon Bedrock yet; run on AWS yet. These are separate future integrations. The match score is not a hiring probability.

## 1 — Quick start (Windows PowerShell)

1. Unzip the project into a private directory, then open PowerShell in that directory.
2. Create and activate a virtual environment:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

3. Copy your environment template:

```powershell
Copy-Item .env.example .env
```

4. Open `.env`. Add a long random `JOB_HUNTER_ADMIN_TOKEN`. Optional: configure job providers and SMTP.
5. Launch the local app:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

6. Open **http://127.0.0.1:8000**, enter the token and upload your CV. Check the extracted name/email/skills before turning on applications.

**Your CV is not included in the ZIP.** Upload it using the dashboard. This ensures the repository doesn't accidentally publish sensitive personal data.

## 2 — Job discovery

- **Adzuna:** Sign up at <https://developer.adzuna.com/> to get `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`. Set `ADZUNA_COUNTRY=za` for South Africa. The script searches four entry-level role phrases.
- **Greenhouse:** Add public employer board slugs, comma-separated, to `GREENHOUSE_BOARDS`.
- **Lever:** Add public company site identifiers, comma-separated, to `LEVER_SITES`.
- Click **Search configured job feeds**. These APIs expose listings; their public GET endpoints do **not** grant a job seeker permission to submit applications through their POST APIs.
- **LinkedIn:** Create official LinkedIn job alerts using role keywords; use your email for alerts and the original job links for applying. There is no LinkedIn scraping or robotic application submission in this project.

## 3 — Application workflow

For a vacancy that explicitly says "email your CV to recruitment@...":

1. Verify the advert is genuine and the recipient actually belongs to the employer.
2. Import the full advert in the dashboard; select **Application by email** and check the confirmation box.
3. Put that **exact recipient address** in `APPROVED_APPLICATION_EMAILS` in `.env` (comma-separated if there are several).
4. Configure SMTP: `SMTP_HOST`, `SMTP_PORT` (465 or 587), `SMTP_USERNAME`, `SMTP_PASSWORD` and `SMTP_FROM`.
5. Select **Prepare application**, review the generated letter, click **Approve**, and click **Send email application**.

The employer email and CV attachment are actually sent only when SMTP is configured and the recipient is allowlisted. A `email_sent` status means the SMTP server accepted the message, **not** that the employer received, read or accepted the application.

### Optional automatic email applications

Once you've tested the manual submission flow, set:

```ini
AUTO_APPLY_ENABLED=true
AUTO_APPLY_MIN_SCORE=90
AUTO_APPLY_DAILY_LIMIT=3
APPROVED_APPLICATION_EMAILS=careers@verified-example.co.za
```

Restart the process, then **Run daily workflow now** or schedule `python -m scripts.daily_run`.

Only **manually verified, email-enabled vacancies with allowlisted recipient addresses, a match score at or above the threshold, no automatic review flags, and within the daily limit** are eligible. Autopilot will *not* attempt website forms or LinkedIn Easy Apply. Auto-generated cover letters are deliberately basic; no unsupported skills, degrees or prior employment are invented.

**Important:** Some jobs require screening questions, consent acknowledgments, cover-letter formats or other documents. Such listings should be excluded from autopilot and handled with review.

## 4 — Daily email summary

Set `NOTIFY_EMAIL` to the address where you'd like the daily shortlist. Configure SMTP as above, and test using **Run daily workflow now**. To run automatically while your laptop is ON, create a Windows Task Scheduler task with:

- Program: path to `.venv\Scripts\python.exe`
- Arguments: `-m scripts.daily_run`
- Start in: your project root
- Trigger: daily (choose your time)

For unattended execution while your computer is OFF, a future AWS deployment can use EventBridge Scheduler, Lambda, S3 and DynamoDB. **This ZIP is not yet deployed to AWS.** SQLite local persistence must be replaced before a serverless production deployment.

## 5 — Tests

```powershell
python -m pytest -q
```

Offline tests cover CV parsing, seniority/degree review flags, duplicate control, allowed recipients, mandatory approvals, autopilot off, safe auto-email sending (SMTP is mocked), and provider-source restrictions.

## 6 — Security and product limitations

- Run only on **127.0.0.1**, not on a public host; the included UI/API is a prototype, not a production auth stack.
- Keep `.env`, `runtime/` and your CV out of GitHub (provided `.gitignore`). Never put passwords, API keys or your uploaded CV in commits.
- Use the application's exact recipient allowlist rather than sending email to addresses automatically harvested from job descriptions.
- The owner of a hosted email account may need to configure an SMTP app password or use an email service provider. Connecting Gmail to ChatGPT does **not** grant this separate Python app permission to send email.
- Before cloud deployment, add strong login, HTTPS, access controls, secrets management, encryption at rest, logs and data-retention controls.
- The rule-based score is a starting point. Using Amazon Bedrock for structured job requirement analysis and tailored documents is a planned stage, not an implemented feature here.

## Planned next milestones

1. Improve CV-to-requirement comparisons and add configurable job preferences.
2. Add employer-specific, credentialed application integrations wherever permission is actually available.
3. Add richer tailoring, screening-question review, and a visible **application review queue**.
4. Move storage and scheduling to AWS, then deploy securely.
5. Add full application-status tracking and replies via explicitly authorised email integration.
## Getting Started

### 1. Clone or download the project

Open the project folder in VS Code and launch the PowerShell terminal.

### 2. Create a virtual environment

```powershell
py -3 -m venv .venv
```

### 3. Activate the virtual environment

```powershell
.\.venv\Scripts\Activate.ps1
```

### 4. Install dependencies

```powershell
pip install -r requirements.txt
```

### 5. Configure environment variables

Copy the example environment configuration:

```powershell
Copy-Item .env.example .env
```

Open `.env` and configure your admin token and optional job-search API credentials.

Keep your `.env` file private. Never commit credentials or tokens to GitHub.

### 6. Start the application

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 7. Open the dashboard

Visit:

http://127.0.0.1:8000

### 8. Upload your CV

1. Enter your admin token from the `.env` file.
2. Upload your PDF or Word resume.
3. Click "Upload and Analyse CV".
4. Configure job feeds and search for matching vacancies.

## Project Features

- AI-assisted CV analysis
- Job discovery and matching
- Job suitability scoring
- Application preparation
- Controlled email-based job applications
- Job application tracking
- Automated workflow support

