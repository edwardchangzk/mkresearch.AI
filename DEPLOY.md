# Step by step: from your PC to a website your friends can open

Do these in order. Total time: about 30 minutes, plus waiting for the first data job.

## 0. What you need
- A GitHub account (you have one) and Git installed. Check in the VS Code terminal: `git --version`.
  If it is not recognized, install "Git for Windows" from git-scm.com (default options are fine), then reopen VS Code.
  (Prefer clicking over typing? GitHub Desktop can do steps 2-3: File > Add local repository, then Publish repository.)

## 1. Create a NEW repository
1. github.com > "+" (top right) > New repository.
2. Name: `mkresearch-ai`. Visibility: Public (simplest) or Private (see README notes).
3. Do NOT tick "Add a README", ".gitignore" or "license". Click Create repository.
Why new, not an existing one: the data job publishes to a branch called `data` and replaces it on every run.
An existing repo with its own `data` branch would lose it, and Streamlit expects `app.py` at the top level.

## 2. Check what will be uploaded
In the VS Code terminal, inside the project folder:
    git init
    git add .
    git status
Read the list under "Changes to be committed". It SHOULD show app.py, model.py, README.md, watchlist.txt, the
.github folder, .streamlit/config.toml and .streamlit/secrets.toml.example.
It must NOT show any of these (if one appears, stop and ask):
- `.streamlit/secrets.toml`  (your real API key; .gitignore already blocks it)
- `data/`                    (your local database)
- `.venv/`                   (hundreds of MB of installed libraries)

## 3. Upload
    git config --global user.name "Your Name"
    git config --global user.email "you@example.com"
    git commit -m "MKResearch.AI"
    git branch -M main
    git remote add origin https://github.com/YOUR-USER/mkresearch-ai.git
    git push -u origin main
The first push opens a browser window to sign in to GitHub. GitHub no longer accepts account passwords in the
terminal, so use that browser sign-in. Reload the repository page: your files should be there.

## 4. Run the data job once
1. Repository > Actions tab. If GitHub asks, click "I understand my workflows, go ahead and enable them".
2. Left side: "refresh-data" > "Run workflow" (right) > green "Run workflow" button.
3. Wait about 5 minutes. A green check means success. Open the branch dropdown on the Code tab: a `data` branch
   with a `snapshot` folder (prices.csv, intraday.csv, news.csv, predictions.csv, ...) should now exist.
If it fails (red X), click the run > "refresh" > expand the red step and read the last lines:
- 403 / permission denied on push: Settings > Actions > General > Workflow permissions > "Read and write" > Save, then re-run.
- "Every price download failed": Yahoo is blocking GitHub's servers right now. Wait an hour and re-run.
- "Restore previous snapshot" shown in red on the very first run: expected, the `data` branch does not exist yet.

## 5. Check the snapshot address (public repositories)
Open this in a browser, with your username and repository name filled in:
    https://raw.githubusercontent.com/YOUR-USER/mkresearch-ai/data/snapshot/meta.json
You should see a short line of text containing "generated_at". That is the address the website will read.

## 6. Deploy on Streamlit Community Cloud
1. Go to share.streamlit.io and sign in with GitHub. Allow access to your repositories.
2. Create app > "Deploy a public app from GitHub". Repository: YOUR-USER/mkresearch-ai. Branch: main. Main file path: app.py.
3. Open "Advanced settings": Python version 3.12. In Secrets paste (edit the first line):
       MKR_SNAPSHOT_URL = "https://raw.githubusercontent.com/YOUR-USER/mkresearch-ai/data/snapshot"
       ANTHROPIC_API_KEY = "sk-ant-..."     # optional: turns on the AI chat. Leave the line out to use built-in help only.
4. Deploy. The first build takes a few minutes while libraries install. You get an address ending in .streamlit.app.

## 7. Check it and share it
- The watchlist loads, the header says "data snapshot ... ago", the Scoreboard says no graded predictions yet (normal).
- Send friends the link. First visit after a quiet spell takes 20-60 seconds (the free app sleeps when unused).

## 8. Changing things later
- Different tickers: on GitHub open `watchlist.txt`, click the pencil, edit, commit. The next job run picks it up.
- Code changes: edit locally, then `git add .` / `git commit -m "what changed"` / `git push`. Streamlit redeploys in about a minute.
- Secrets: app > Settings > Secrets on Streamlit. Never put keys in files that get committed.

## What the files you must not upload contain, and how big things get
- `.streamlit/secrets.toml` holds your private API key. Anyone who sees it can spend your money. Bots scan public GitHub
  for keys within minutes, and deleting the file later does NOT remove it from history (you would have to revoke the key).
  Streamlit's Secrets box replaces this file online.
- `data/market.db` is your local database (prices, news, predictions). Roughly 5-15 MB now, growing by perhaps 15-40 MB
  a year (mostly saved news). Not uploaded because it is a binary file that changes on every refresh and the website
  rebuilds its data from the snapshot anyway.
- The snapshot on the `data` branch is about 8 MB (about 5 MB of daily prices, about 3 MB of hourly and 5-minute
  bars) plus a slowly growing news and prediction log. Because each run replaces the branch history, repository size
  stays at roughly one snapshot instead of piling up copies.
