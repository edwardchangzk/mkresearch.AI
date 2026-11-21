# MKResearch.AI

Personal stock-research dashboard: watchlist, scroll-zoom charts, a walk-forward prediction model with an honest
scorecard, a live **Scoreboard** that grades its own past predictions, news archive, earnings reactions,
fundamentals, screener, paper backtest, and a chat assistant.

## Run it on your own PC
    python -m venv .venv
    .venv\Scripts\activate
    python -m pip install -r requirements.txt
    python -m streamlit run app.py
Local mode downloads data straight from Yahoo into `data/market.db`. Optional: copy `.streamlit/secrets.toml.example`
to `.streamlit/secrets.toml` and add an Anthropic API key to turn on the AI chat (otherwise it uses built-in help).

## Put it online for friends (GitHub + Streamlit Community Cloud)
The detailed click-by-click guide is in DEPLOY.md. The short version:

Why not just deploy and go: Streamlit Community Cloud wipes its disk whenever the app restarts, and Yahoo often
blocks requests from its shared servers. So the **GitHub Action fetches the data** and publishes it as small CSV files
on a `data` branch; **the website only reads those files**. GitHub is the database, and your prediction log survives.

1. **Create a GitHub repository** (public is simplest; see notes) and push this folder:
       git init
       git add .
       git commit -m "MKResearch.AI"
       git branch -M main
       git remote add origin https://github.com/YOUR-USER/YOUR-REPO.git
       git push -u origin main
   `.gitignore` already keeps `.venv`, `data/` and `secrets.toml` out of the repo. Check no secret was committed.
2. **Run the data job once:** repository > Actions tab > "refresh-data" > Run workflow. The first run downloads all
   history and takes a few minutes. When it finishes, a `data` branch with a `snapshot/` folder exists. If the push
   fails with a 403 error, go to Settings > Actions > General > Workflow permissions and choose "Read and write".
   If the job reports that every price download failed, Yahoo is blocking GitHub's servers at that moment; re-run later.
3. **Deploy:** share.streamlit.io > New app > your repo, branch `main`, main file `app.py`. Under Advanced settings choose
   Python 3.12 and paste into Secrets:
       MKR_SNAPSHOT_URL = "https://raw.githubusercontent.com/YOUR-USER/YOUR-REPO/data/snapshot"
       ANTHROPIC_API_KEY = "sk-ant-..."      # optional
   Private repo? Also add `MKR_SNAPSHOT_TOKEN = "github_pat_..."` (a fine-grained token with read access to contents).
4. **Change the watchlist** by editing `watchlist.txt` on GitHub; the next job run picks it up.

Notes
- The job runs every 30 minutes on weekdays and every 6 hours at weekends (GitHub may delay runs). The site re-reads
  the snapshot every 30 minutes while open.
- The job also saves about a year of hourly and 30 days of 5-minute bars, so the zoom chart works on the hosted site.
- Predictions are logged once per trading day, after the US close, for 1-week, 1-month and 3-month horizons.
- Public repositories get free Actions minutes. A private repository only gets 2,000 free minutes a month, which a
  30-minute schedule can exceed; change the cron line in `.github/workflows/refresh-data.yml` to hourly.
- GitHub pauses scheduled workflows on a public repo after 60 days without repository activity; re-enable them in the
  Actions tab (or push any commit) if the Scoreboard stops growing.
- A free Streamlit app goes to sleep when unused; the first visit afterwards takes 20-60 seconds.
- The AI chat is limited to 40 messages per visitor session and 150 AI answers per day in total
  (`MKR_CHAT_DAILY_CAP` changes the daily limit). Usage is billed to your API key.

## Files
app.py (UI) · model.py (prediction model) · chart.py (zoom chart) · chatbot.py · snapshot.py (CSV snapshot sync) ·
refresh_job.py (data job) · .github/workflows/refresh-data.yml · sources.py (news, earnings, fundamentals) ·
ingest.py (prices) · db.py (SQLite) · tracking.py (Scoreboard) · stats.py · events.py · backtest.py · sentiment.py ·
universe.py (tickers) · config.py · style.py
