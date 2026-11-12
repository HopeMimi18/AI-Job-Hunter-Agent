# StudentRoom opportunity feed (AI Job Hunter v0.3)

This optional integration uses the publicly advertised RSS feed at `https://www.studentroom.co.za/feed/` to discover **titles, short summaries, publication dates and article links**. It does not scrape article pages, log in to the website, submit forms, or attempt automatic applications. It is distinct from the separate `student-room.co.za` domain.

## Install into your existing v0.2 project

1. Back up your project folder and stop Uvicorn (`Ctrl+C`).
2. Unzip the v0.3 patch **into your existing `AI_Job_Hunter_Starter` folder** (not into an extra nested folder). It replaces only the listed project files, and does **not** contain or replace `.env`, `runtime/`, or your CV.
3. From your activated `.venv` PowerShell terminal:

   ```powershell
   python -m pip install -r requirements.txt
   python -m pytest -q
   ```

4. Review StudentRoom's current policies and feed usage conditions before opting into automated retrieval; seek publisher permission if your use requires it. Add to your **existing** `.env`:

   ```ini
   STUDENTROOM_ENABLED=true
   STUDENTROOM_MAX_ITEMS=30
   ```

   There is **no StudentRoom API key** involved. Do not change your Adzuna or AWS settings. Keep `AUTO_APPLY_ENABLED=false` during testing.
5. Restart Uvicorn:

   ```powershell
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
   ```

6. Open `http://127.0.0.1:8000`, enter the existing admin token, and click **Search configured job feeds**. Use **Source → StudentRoom** and **Opportunity type → Bursaries** or another category to filter.

## Important restrictions

- **RSS availability is not guaranteed**. The integration has automated offline tests using RSS fixtures; it has not been tested live against the StudentRoom server. If access is blocked or prohibited, switch it off and use StudentRoom's own email subscription or manually imported links.
- It is an announcement service, not an application API. Always check the original listing and the **actual employer/bursary provider website** for eligibility, documentation, closing date and official application URL. StudentRoom does not automatically authorise email applications.
- Bursaries, apprenticeships, learnerships and general training programmes intentionally **do not generate generic job cover letters** and cannot be auto-submitted by this integration. Read their requirements, including academic results, institution, NQF level, age and location. Internship/graduate programme application drafts still require human review.
- Scores for programme types are **discovery relevance**, not eligibility or acceptance probabilities. Publication dates are not application deadlines.
- Each manual discovery sends at most **one request** to the RSS feed, processes a maximum of 30 current entries and stores only short excerpts and links. For scheduled execution, once daily is a reasonable starting cadence (subject to source policies).
- Email summaries can include multiple categories if you have configured SMTP and `NOTIFY_EMAIL`. No notifications are sent without that configuration.
- Keep `.env` (Adzuna/API/AWS/SMTP secrets) and `runtime/` out of Git.

## Troubleshooting

- If your dashboard shows a message like `StudentRoom RSS: HTTPStatusError`, the provider may be blocking the feed or the URL may have changed. Disable StudentRoom rather than bypassing restrictions.
- If you get a parsing error, check that the feed returns RSS/XML. The program intentionally avoids scraping HTML as a fallback.
- If StudentRoom results do not appear, check `STUDENTROOM_ENABLED=true`, restart Uvicorn, and clear the type/source filters. You may also have reached the feed's latest-entries limit.

## What's new

- `app/sources.py`: opt-in RSS reader, source links and opportunity classification
- `app/matching.py`: category-aware relevance and eligibility-review warnings
- `app/db.py`: backwards-compatible `opportunity_type` and `published_at` columns
- `app/dashboard.html`: source/type selectors and safe announcement links
- `app/workflow.py`: block generic job applications for non-job programmes
- `app/mailer.py`, `app/main.py`, `scripts/daily_run.py`: mixed-category email digests
- `tests/test_studentroom.py`: offline RSS/security/migration tests
