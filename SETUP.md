# SETUP — getting this running on your PC (Windows)

This is a one-time setup. After this, running any script takes 2 commands.

Kushal will send you two files separately on Google Drive — keep them safe and don't share them:

- `.env`
- `credentials.json`

---

## Step 1 — Install Git

1. Go to https://git-scm.com/download/win and download the installer.
2. Run it. Click **Next** through all the screens — defaults are fine.
3. Open a new **PowerShell** window (press the Windows key, type "PowerShell", hit Enter).
4. Type this and press Enter:

   ```powershell
   git --version
   ```

   You should see something like `git version 2.45.x`. If yes, Git is installed. ✓

---

## Step 2 — Install Python 3.12

1. Go to https://www.python.org/downloads/windows/ and download **Windows installer (64-bit)** for the latest 3.12.x.
2. Run the installer. **Important:** before clicking "Install Now", check the box at the bottom that says **"Add python.exe to PATH"**.
3. Click **Install Now**, wait for it to finish, close the installer.
4. In a **new** PowerShell window, run:

   ```powershell
   python --version
   ```

   You should see `Python 3.12.x`. If yes, Python is installed. ✓

---

## Step 3 — Install Node.js

1. Go to https://nodejs.org/en/download and download the **Windows Installer (LTS)**.
2. Run it. Click **Next** through everything. Defaults are fine.
3. In a new PowerShell window:

   ```powershell
   node --version
   ```

   You should see `v20.x.x` or higher. ✓

---

## Step 4 — Clone the repo

Pick a folder for your code. We'll use `Documents`.

```powershell
cd $HOME\Documents
git clone https://github.com/akshat-git-jpg/myproj.git
cd myproj
```

This downloads the code into a `myproj` folder inside your Documents.

---

## Step 5 — Drop in the secret files

1. Open the Google Drive folder Kushal shared with you.
2. Download both files:
   - `.env`
   - `credentials.json`
3. Open File Explorer, go to `Documents\myproj`.
4. Drag both files into that folder. They should sit at the top level, next to `CLAUDE.md` and `SETUP.md`.

> **Why this matters:** these two files hold all the API keys and Google access. The code won't run without them. Don't ever upload them anywhere or commit them to git — they're already in `.gitignore` so git will skip them automatically.

---

## Step 6 — Set up the Python environment

From the `myproj` folder, in PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

If PowerShell shows an error like **"running scripts is disabled on this system"** when you try to activate the venv, run this **once**:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Type **Y** and press Enter. Then re-run the `Activate.ps1` line above.

After `pip install` finishes (takes a minute or two), your PowerShell prompt should start with `(venv)`. That means the Python environment is active.

---

## Step 7 — Test that everything works

With the venv still active (prompt shows `(venv)`):

```powershell
python youtube\yt-analysis\sync_metadata.py
```

This connects to the Google Sheets and copies any newly-uploaded videos from the YT Tracker sheet into the Analysis sheet. You should see a summary like `✓ Synced N rows` at the end.

If you see that, **everything is working.** 🎉

---

## Day-to-day usage

Every time you open a new PowerShell window to run something, do these two things first:

```powershell
cd $HOME\Documents\myproj
.\venv\Scripts\Activate.ps1
```

(Your prompt should now show `(venv)`.)

Then run whichever script you need:

| What you want to do                                                                   | Command                                            |
| ------------------------------------------------------------------------------------- | -------------------------------------------------- |
| Process new "To Process" rows in the YT Tracker (generates short links + description) | `python youtube\yt-analysis\process_yt_tracker.py` |
| Sync views, affiliate clicks, and/or rankings to the Analysis sheet                   | `python youtube\yt-analysis\yt_analysis.py`        |
| Sync just metadata from Tracker → Analysis                                            | `python youtube\yt-analysis\sync_metadata.py`      |
| Sync just views                                                                       | `python youtube\yt-analysis\sync_views.py`         |
| Sync just affiliate clicks                                                            | `python youtube\yt-analysis\sync_clicks.py`        |
| Sync just rankings                                                                    | `python youtube\yt-analysis\sync_rankings.py`      |

The interactive `yt_analysis.py` asks you which sub-syncs to run — easiest one to start with.

---

## Updating the code later

Whenever Kushal updates the repo on GitHub, pull the latest version:

```powershell
cd $HOME\Documents\myproj
git pull
```

If `requirements.txt` changed (new Python packages), also re-run:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

## If something goes wrong

| Problem                                          | Fix                                                                                                                                             |
| ------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `git` / `python` / `node` "is not recognized"    | The program isn't installed or isn't on PATH. Redo Step 1/2/3 and make sure you tick "Add to PATH" during install. Close and reopen PowerShell. |
| `credentials.json not found` or `.env not found` | Step 5 — the files need to be in the `myproj` folder at the top level, not inside a subfolder.                                                  |
| `pip install` errors out                         | Make sure the venv is active (prompt shows `(venv)`). Re-run `.\venv\Scripts\Activate.ps1`.                                                     |
| Google Sheet "permission denied"                 | Kushal needs to share that specific sheet with your Gmail as Editor. Send him the sheet name.                                                   |
| Anything else                                    | Screenshot the error and send to Kushal.                                                                                                        |
