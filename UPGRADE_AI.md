# AI Job Hunter — AI matching and cover-letter upgrade (v0.2)

This upgrade is designed to be copied **on top of your existing `AI_Job_Hunter_Starter` folder**. It updates code but does **not** include, delete, or overwrite your `.env`, `runtime/` database, uploaded CV, or live job results.

## Install safely (Windows, VS Code / PowerShell)

1. Stop your running Uvicorn server with **Ctrl+C** in the terminal running it.
2. Make a backup of your project folder, particularly `.env` and `runtime/`.
3. Put the `AI_Job_Hunter_AI_Upgrade.zip` file in your Downloads folder.
4. In VS Code's PowerShell terminal, while inside your **existing** `AI_Job_Hunter_Starter` project directory, run:

```powershell
Expand-Archive -Path "$HOME\Downloads\AI_Job_Hunter_AI_Upgrade.zip" -DestinationPath . -Force
python -m pip install -r requirements.txt
python -m pytest -q
```

5. The offline test suite should report **16 passed**. Your existing `.env` and `runtime/` were not included in this patch.
6. Open your `.env` file (not `.env.example`), then add these lines if missing:

```ini
BEDROCK_ENABLED=false
AWS_REGION=us-east-1
BEDROCK_MODEL_ID=amazon.nova-lite-v1:0
AUTO_APPLY_ENABLED=false
```

7. Start the server again:

```powershell
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

8. Open http://127.0.0.1:8000, paste the admin token, and **re-upload your CV**. This refreshes parsed skills and rescored vacancies. Click **Prepare application** on a suitable live job. With `BEDROCK_ENABLED=false`, your draft will already reference relevant projects and requirements.

## Optional: enable actual Amazon Bedrock drafting

This feature **costs money per inference** and sends a redacted excerpt of your CV (skills, studies, projects and professional history) plus job description to Amazon Bedrock. Redaction removes detected email, phone, name and profile URLs, but **you must review the CV for other sensitive details before enabling it**. The model cannot guarantee that all claims are correct; each draft still requires your approval.

1. Ensure the AWS CLI and your AWS credentials/profile work on the same computer. For example, run `aws sts get-caller-identity` (do not publish the output). Do **not** paste access keys into source code or GitHub.
2. In your AWS account, verify Amazon Nova Lite is available in `us-east-1` and the AWS identity has permission `bedrock:InvokeModel` for the chosen model. Model access requirements vary by account and model.
3. Set `BEDROCK_ENABLED=true` in `.env` and restart the server. Leave `AUTO_APPLY_ENABLED=false`.
4. Click **Prepare application** on one vacancy. Only that click makes the paid Bedrock request. If the AWS request fails, the dashboard will show an error rather than claim that AI drafting worked.
5. Review the generated letter, its quoted supporting CV evidence and any gaps. **Approving a draft does not submit the application.** Website-only vacancies still require the employer application link. Do not click Send on an unverified email vacancy.

To return to zero Bedrock inference while developing, set `BEDROCK_ENABLED=false` and restart.

## What changed

- `app/matching.py`: ranks skills, recognises mandatory experience/degree review flags, and cites relevant CV project bullets.
- `app/cv.py`: recognises `REST APIs` and `HTTP/REST APIs` skill variants.
- `app/workflow.py`: generates evidence-based offline letters; optionally calls Amazon Bedrock; persists fit notes; requires approval for AI drafts.
- `app/ai.py`: AWS Bedrock Converse integration with basic contact-data redaction, strict JSON parsing and checked verbatim CV citations.
- `app/db.py`: safely migrates the existing SQLite application table and preserves data.
- `app/main.py`: passes full CV text for matching, increments version.
- `app/dashboard.html`: displays match evidence, AI-identified gaps and disables email submission for website-only listings.
- `requirements.txt`: adds `boto3`.
- `.env.example`: documents the optional settings. It is a template, not your actual `.env`.
- `tests/test_ai_upgrade.py`: adds six offline regression tests (mocked Bedrock; no AWS or employer submission).

## Known limitations

- Match scores are rule-based, not hiring probabilities. Mandatory eligibility requirements still require human verification.
- Bedrock only drafts and identifies possible gaps; it **does not** take the place of official employer eligibility checks.
- This upgrade **does not automate arbitrary website forms** or LinkedIn Easy Apply. Submission remains limited to manually verified, permitted email workflows.
- With `BEDROCK_ENABLED=true`, unattended automatic sending is disabled to prevent unreviewed AI drafts being sent.
- The dashboard is local-only development software. Do not publicly deploy it without authentication and security hardening.

## Push to your existing GitHub repository

After local testing and after verifying that `.env`, `runtime/` and your CV are excluded from Git:

```powershell
git status
git add app tests requirements.txt .env.example UPGRADE_AI.md
git commit -m "feat: add evidence-based matching and optional Bedrock drafting"
git push origin main
```

The above steps update your existing repository; there is no need to create another one.
