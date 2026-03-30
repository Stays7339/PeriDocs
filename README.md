# PeriDocs.org

An ad-free free-to-the-public platform which systematically indexes and cites writing passages which focus on mixing anecdotes & recurring collective experiences with applied philosophy. PeriDocs avoids applied psychology, and PeriDocs avoids claiming professionalism of any kind; at the same time, PeriDocs believes that there is a lot of public good that can be done unto many people by reducing the friction of searching for non-paywalled rigorous sources. PeriDocs plans to do this via deterministic fine-tuning around the specific search query that the user sends to us.
Users may actively choose to rigorously describe their perspective of the world, and they would get more-relevant results as a process. They would also be able to opt-in to keep their search query as its own perpetual public entry on the platform, so it, too, can contribute to the way people described lived experiences in ways that often go unarticulated. 

---

## Setup Guide (Full Walkthrough)

### Step 0. Install Prerequisites

#### For macOS

1. Install Homebrew (if not already installed):

```bash (Terminal)
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Official site: [https://brew.sh](https://brew.sh)

2. Install Python 3.12.7 and Git (pyenv recommended for exact version):

   ```bash (Terminal)
   brew install pyenv git
   pyenv install 3.12.7
   pyenv global 3.12.7
   ```

3. Verify installations:

   ```bash (Terminal)
   python3 --version
   git --version
   ```

---

#### For Linux (OpenSUSE is preferred for its backups and OS-level version control)

1. Update and install dependencies:

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3.12 python3.12-venv python3-pip git curl
   ```

2. Verify installations:

   ```bash
   python3 --version
   git --version
   ```

3. (Optional) If you are using another distribution, substitute the package manager (dnf, pacman, etc.) as appropriate.

---

#### For Windows

1. Install Git for Windows: [https://git-scm.com/download/win](https://git-scm.com/download/win)
   During setup, choose:

   * "Use Git from the Windows Command Prompt"
   * "Checkout Windows-style, commit Unix-style line endings"

2. Install Python 3.12.7 (3.12.7 is the only version confirmed to work with compatibility between required libraries)
   Download from: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
   During setup:

   * Check "Add Python to PATH"
   * Include pip during installation

3. Verify installations:

   ```powershell
   python --version
   git --version
   ```

---

### Step 1. Clone the Repository

Choose a folder to hold the project (for example, PeriDocs/).

```bash
git clone https://github.com/Stays7339/PeriDocs.git
cd PeriDocs
```

> Note: This repository should remain set to private. Only collaborators with access can clone it or pull from it.

---

### Step 2. Create a Virtual Environment
Activating the virtual environment ensures packages are installed locally and not system-wide.

#### macOS / Linux

```bash
python3 -m venv venv
source venv/bin/activate
```

#### Windows (PowerShell)

```powershell
python -m venv venv
venv\Scripts\activate
```

If activation fails on Windows due to a security policy error:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
venv\Scripts\activate
```

---

### Step 3. Install Dependencies

With your virtual environment activated:

```bash
pip install -r requirements.txt
```

If pip needs upgrading:

```bash
pip install --upgrade pip
```

---

### Step 4. Set Up Secrets / Environment Variables

Create a `.env` file in the project root with your local keys:

```
PERIDOCS_AES_KEY=your-secret-key
```

> Do **not** commit `.env` to GitHub.

For collaborators, you can store secrets in GitHub **Settings > Secrets and Variables** if using CI/CD pipelines, but never expose them in the repository.

You **should** put a file simply titled `.gitignore` directly within the first level of the root folder `PeriDocs`
The .gitignore file should exist with no characters before the `.`, and within the `.gitignore` file, all of the following should be included:

# Important: check what is *CRUCIAL* to add into .gitignore before continuing
<details>
<summary>Click to reveal Crucial Data Leak Prevention List: `.gitignore`</summary>
# ------------------------------
# PeriDocs Crucial Data Leak Prevention List: Ignore-File-List - Python
# ------------------------------
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
build/
dist/
*.egg-info/
.eggs/

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# PyInstaller
*.manifest
*.spec

# ------------------------------
# Virtual Environment Ignore-File-List
# ------------------------------
venv/
env/
ENV/
.venv/
# you can add any other env folder you use

# ------------------------------
# VS Code Ignore-File-List
# ------------------------------
.vscode/
.history/
*.code-workspace

# ------------------------------
# OS / system Ignore-File-List
# ------------------------------
.DS_Store
Thumbs.db

# ------------------------------
# Logs and databases Ignore-File-List
# ------------------------------
*.log
*.sqlite3

# ------------------------------
# Other common Python stuff Ignore-File-List
# ------------------------------
__pycache__/
*.pytest_cache/
*.mypy_cache/
*.coverage
htmlcov/
.coverage.*

# ------------------------------
# Node.js / frontend (if you add any) Ignore-File-List
# ------------------------------
node_modules/
dist/
build/

# ------------------------------
# Ignore data folders, even in dev, just in case we accidentally push to production
# Ignore-File-List
# ------------------------------
data/*
!data/.gitkeep
data/entries.json
backups-for-the-main-data-folder/*

# ------------------------------
# Ignore embeddings models folders since we have large data sets
# Ignore-File-List
# ------------------------------
models/*
!models/.gitkeep


# ignore everything in static folder
app/static/CabineyGrotesk_Complete/*


# # Ignore sensitive env files and environment variables
.env
</details>

# ^ ! ^ ! ^

---

### Step 5. Run the App Locally

Run this command inside the project folder:

```bash
uvicorn app.routes:app --host 0.0.0.0 --port 8000 --reload
```

You should see output similar to:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

### Step 6. Open the App

Open your browser and go to:

```
http://127.0.0.1:8000/
```

You now have PeriDocs running locally.

---

### Step 7. (Optional) Developer Tooling Setup

#### VS Code Recommended Setup

1. Install VS Code: [https://code.visualstudio.com/](https://code.visualstudio.com/)
2. Open the PeriDocs-code folder in VS Code.


---

# Canonical Project Directory 

<details>
<summary>Click to expand canonical project directory</summary>
## Canonical Project Directory as of 2026-03-30T16:10:00-04:00
**Important Note**: *While the software developers of PeriDocs try their best to keep the following project directory updated as best as they can, there may be some old filenames, old filepaths, and unused or obsolete files that are effectively no longer in use. The original intention is for this Canonical Project Directory to be as reliable as possible, but during the throws of development, details tend to get updated in some places but not others each moment.*

```
PeriDocs-code/                         # Root project folder
│
├─ app/                                # Backend + frontend application code
│  │
│  ├─ helpers/
│  │  ├─ __init__.py                   # FastAPI app startup, embedding preloading, centroid loading, static mounting, route inclusion.
│  │  ├─ entry_similarity.py           # Can handle loading embeddings from disk, raw similarity computations for embeddings, and deterministic mean. Other files may still use their own internal helpers rather than calling this file.
│  │  ├─ file_ops.py                   # load_data, save_data, ensure_feedback_file
│  │  ├─ json_safe.py                  # Convert NumPy and other non-JSON-native types into JSON-serializable Python primitives.
│  │  └─  top_matches.py                # API-ready top matches + JSON-safe outputs
│  │
│  │
│  │
├─ routes/
│  │  ├─ __init__.py                   # Imports and attaches all route modules to the main FastAPI app
│  │  ├─ admin_routing.py              # "/admin*"
│  │  ├─ entry.py                      # "/submit", "/submit-success"
│  │  ├─ feedback.py                   # "/feedback"
│  │  ├─ info_navigation.py            # "/", "/about", "/privacy-policy", "/terms-of-service"
│  │  └─ __pycache__/                
│  │
│  ├─ static/                            # Frontend static files
│  │  ├─ admin-review.js                 # Allows humans to dictate what counts and what doesn't with centroids and semantic auto-groups
│  │  ├─ cookies-icon-by-trinh-ho-from-flaticon-dot-com.png  #icon for privacy notice about local storage
│  │  ├─ favicon.png
│  │  ├─ peridocs-logo-v1-white.png
│  │  ├─ peridocs-logo-v1.png
│  │  ├─ peridocs-logo-v2.png
│  │  ├─ peridocs-ui.js                  # unified localStorage UI state: theme, cooldowns, modals, toasts, feedback/entry 
│  │  ├─ peridocs-wordmark-202602232127.svg
│  │  ├─ peridocs-wordmark-and-logo-202602232100.png
│  │  ├─ peridocs-wordmark-and-logo-202602232133.png
│  │  ├─ peridocs-wordmark-and-logo-202602232133.svg
│  │  ├─ santa-hat-free-icon-by-surang-from-flaticon-dot-com #icon to display for users who's local time is set to Deccember 25 of any year
│  │  ├─ style.css                       # Main stylesheet
│  │  └─ CabinetGrotesk_Complete/Fonts/WEB/fonts
│  │
│  │
│  ├─ templates/                        # Jinja2 HTML templates
│  │  ├─ about.html                     # About page template
│  │  ├─ admin-review.html              # Dashboard to manage centroids, which are neighborhoods of an emotion, populated by user entries.
│  │  ├─ base.html                      # Layout template
│  │  ├─ index.html                     # Main homepage template
│  │  ├─ privacy.html                   # Privacy policy page template
│  │  ├─ submit-success.html            # Submission success page template
│  │  ├─ terms-of-service.html          # Terms of Service page template
│  │  └─ includes/                      # Partial web-page templates
│  │      ├─ modal-crisis.html
│  │      └─ modal-feedback.html
│  │
│  │
│  └─ __pycache__/                       # Python compiled bytecode cache
│
├─backups-for-the-main-data-folder
│   └─peridocs_backup_[YYYY]-[MM]-[DD]T[HH]-[mm]-[ss]Z.zip
├─ core/
│   ├─ map/
│   │   ├─ centroids.py                   # The Engine - making centroids / clusters / neighborhoods per nuanced emotion and some (but not all) SAAJE affiliations.
│   │   ├─ deletion.py                    # The Surgical Pulverizer - if a user wants something removed, it should all go through here.
│   │   ├─ entry_membership_sequencer.py                       # The Evaluation Layer - controls assignment of Software-auto-added journal entries (SAAJEs). This is so that centroids-math (which is in centroids.py) stays separate from assignment to centroids which stays separate from the admin dashboard for human intervention, which stays separate from the historical ledger for determinism.
│   │   ├─ ledger.py                      # ==== THE CRITICAL AUTHORITY===== FOR ALL OF PERIDOCS CENTROIDS SYSTEM. Keeps track of thuth via sequence of actions across the system, rather than through the veriability of time, which quietly throws off determinism.
│   │   └─ mapping_runtime.py             # The Instantiation Boundary - Prevents against excessive coupling, repo fragility, and code sprawl.
│   │
│   │
│   │
│   └─ nlp/
│      ├─ __init__.py                     # Exposes core NLP pipeline, PII, embeddings, emotion, and crisis utilities.
│      ├─ clause_utils.py                 # Splits text into clauses (sentence-level granularity). Optionally merge clauses into windows of ~max_words to avoid too short embeddings.
│      ├─ crisis_detector.py              # Lemma-aware, thresholded detection of crisis-related content.
│      ├─ crisis_recorder.py              # Atomic storage of encrypted crisis records for flagged entries.
│      ├─ embeddings.py                   # Manages all encryption, SentenceTransformer model, embedding computation, and caching.
│      ├─ hash_utils.py                   # Generates SHA hashes for unique IDs and text integrity tracking.
│      ├─ orthography.py                  # Dictates choices for norms of spelling, punctuation, boundaries of phrases, capitalization, hyphenation, etc.
│      ├─ pii.py                          # redact_pii, pattern library for emails, phone numbers, addresses, etc.
│      └─ process_entry.py                # Orchestrates NLP workflow per journal entry: embedding, centroid assignment, crisis check.
│
│
│
│
├─ data/                                  # Local data storage
│  ├─ centroids/
│  │   ├─[centroid/precentroid]_[natural_sort_integer]_summary.json
│  │   └─[centroid/precentroid]_[natural_sort_integer].npz
│  ├─ entries/                        # Stored entries
│  │   ├─ entries_clause_embeddings_dump[YYYYMMDD]_[0-3].json file(s) 
│  │   ├─ entries_mean_embeddings_dump[YYYYMMDD]_[0-3].json file(s) 
│  │   └─ entries_standout_flags_dump[YYYYMMDD]_[0-3].json file(s) 
│  ├─ feedback.json                       # Stored feedback and report inquiries
│  ├─ recorded_crises.lock                # For preventing corrupted data in case of crash.
│  ├─ recorded_crises.npz                 # logs for crises that have been submitted to our servers. NOTE: These should never be entered into the main database.
│  └─ .gitkeep                            # Shows where the data/ folder is for the sake of being transparent on Github without detailing which files go in there
│
│
│
│
├─ models/                             # Where open source pre-trained context-understanding models lives
│   ├─.locks/
│   └─ models--sentence-transformers--all-roberta-large-v1/
│   │   └─ models--sentence-transformers--all-roberta-large-v1/ # yes the same name
│   │               ├─ .no_exist/
│   │               │       └─ cf74d8acd4f198de950bf004b262e6accfed5d2c/
│   │               │                 ├─ adapter_config.json
│   │               │                 └─ added_tokens.json
│   │               ├─ blobs/
│   │               │    ├─ 2ea7ad0e45a9d1d1591782ba7e29a703d0758831 # no . or "dot" extension nor / or "slash" extension
│   │               │    ├─ 4ebe4bb3f3114daf2e4cc349f24873a1175a35d7 # no . or "dot" extension nor / or "slash" extension
│   │               │    ├─ 7a7f517f71e7a3286b03572ece4fb2e5a0571db6 # no . or "dot" extension nor / or "slash" extension
│   │               │    └─ [xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx] # Nine more files just like that
│   │               └─ snapshots/
│   │                       └─ cf74d8acd4f198de950bf004b262e6accfed5d2c/
│   │                                  ├─ 1_Pooling/
│   │                                  ├─ config_sentence_transformers.json
│   │                                  ├─ config.json
│   │                                  ├─ merges.txt
│   │                                  ├─ model.safetensors
│   │                                  ├─ modules.json
│   │                                  ├─ README.md
│   │                                  ├─ sentence_bert_config.json
│   │                                  ├─ special_tokens_map.json
│   │                                  ├─ tokenizer_config.json
│   │                                  ├─ tokenizer.json
│   │                                  └─ vocab.json
│   └─ .gitkeep                        # avoids pushing the whole pre-trained one-way dataset through GitHub
│
│
│
│
├─ test-and-debug/                     
│    ├─ debug_embeddings.py             # Debugging for running emebeddings only, not the full suite
│    ├─ test_crisis_flag_detection.py   # Testing benchmarks for crisis detection
│    ├─ test_dsmx.py                    # OBSOLETE
│    ├─ test_embeddings_similarity.py   # now contains multi-faceted embedding similarity analysis
│    ├─ test_mps.py                     # testing for Apples GPUs, NVIDIA GPUs, and CPUs from AMD and Intel.
│    └─ test_pipeline.py                # Comprehensive test suite for NLP pipeline modules (unit + integration).
│
├─ venv/                               # No other option but to manually re-create on startup. It's considered data-risky to reupload venv because it is even slightly in communication with .env . So, /venv/ is in .gitignore until further notice.
│
├─ .env                      # Private, proprietary data (never commit)
├─ .gitignore                # Files and folders ignored by Git
├─ README.md                 # Project overview, setup, and usage
├─ requirements.txt          # Pinned Python dependencies
└─ setup_roberta.py          # Setup file to run in terminal to be sure that the FOSS ML model is installed correctly.
```
</details>


# ^ ! ^ ! ^

---

## Notes

* The `--reload` flag automatically restarts the server when code changes.
* `data/` is intentionally ignored by Git for local user data.
* Virtual environment: `venv/` (excluded from Git since it only is used to install libraries and and just run the code once until deleted. PeriDocs proprietary code is not stored in `venv/` and libraries can be redownloaded from their third-party severs with ```pip install -r requirements.txt``` )

## Miscellaneous FAQ
---
*Homebrew isn’t strictly *required*—it’s just the most common and convenient way to install packages like Python, Git, or other developer tools on macOS without having to manually manage binaries or paths. It basically acts as a “package manager” similar to `apt` on Linux.

### Why Homebrew is recommended

1. **Simplifies installation of dependencies**
   Installing Python 3.12.7 manually on macOS can be tedious (downloading `.pkg`, configuring paths, handling multiple Python versions). Homebrew automates all that.
2. **Manages versions easily**
   You can have multiple Python versions and switch between them via `brew` or `pyenv`.
3. **Keeps software up-to-date**
   Homebrew handles updates for you (`brew update` and `brew upgrade`).
4. **Consistency with Linux workflows**
   If you or collaborators use Linux, `brew` gives a package-manager experience similar to `apt` or `dnf`.

---

### Alternatives to Homebrew

1. **Python.org installer**

   * Download the official Python 3.12.7 `.pkg` from [python.org](https://www.python.org/downloads/macos/).
   * Install manually and add it to your PATH.
   * Pros: No extra package manager required.
   * Cons: Harder to manage multiple versions or update Python.

2. **pyenv**

   * Can install and switch between multiple Python versions independent of system Python.
   * On macOS, you often still need some build tools (`xcode-select --install`) but you can install Python via pyenv without Homebrew if you compile from source.
   * Pros: More precise control over versions, portable between macOS/Linux.
   * Cons: Slightly more complex setup than Homebrew.

3. **MacPorts**

   * Another package manager for macOS (less popular than Homebrew).
   * Pros: Full package ecosystem, similar to Homebrew.
   * Cons: Less community support, not as widely adopted today.

4. **Manual installation of Git and Python**

   * Download and install Git from [git-scm.com](https://git-scm.com/download/mac).
   * Download and install Python from Python.org.
   * Add paths manually.
   * Pros: No extra tools needed.
   * Cons: Tedious, can cause conflicts with macOS system Python.

 **Summary:**

* **Homebrew is convenient but optional.**
* If you want absolute minimal setup, you could skip Homebrew and just install Python 3.12.7 and Git manually from their official sources.
* If you plan on keeping multiple Python versions, using `pyenv` (with or without Homebrew) is highly recommended.

---

