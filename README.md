# PeriDocs

Curated, paraphrased discussions and public journal links about neurological well-being.
Early-stage prototype.

---

## Setup Guide (Full Walkthrough)

### Step 0. Install Prerequisites

#### For macOS

1. Install Homebrew (if not already installed):

   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

Official site: [https://brew.sh](https://brew.sh)

2. Install Python 3.12.7 and Git (pyenv recommended for exact version):

   ```bash
   brew install pyenv git
   pyenv install 3.12.7
   pyenv global 3.12.7
   ```

3. Verify installations:

   ```bash
   python3 --version
   git --version
   ```

---

#### For Linux (Ubuntu/Debian-based)

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

Choose a folder to hold the project (for example, Desktop/ or Documents/ or PeriDocs-code/).

```bash
git clone https://github.com/Stays7339/PeriDocs.git
cd PeriDocs-code
```

> Note: This repository is private. Only collaborators with access can clone it or pull from it.

---

### Step 2. Create a Virtual Environment

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
ADMIN_TOKEN=your-admin-token
```

> Do **not** commit `.env` to GitHub.
> For collaborators, you can store secrets in GitHub **Settings > Secrets and Variables** if using CI/CD pipelines, but never expose them in the repository.

---

### Step 5. Run the App Locally

Run this command inside the project folder:

```bash
uvicorn app.routes:app --reload
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


## Canonical Project Directory as of 24 December 2025 (202512241857 ; YYYYMMDDhhmm)
**Important Note**: *While the software developers of PeriDocs try their best to keep the following project directory updated as best as they can, there may be some old filenames, old filepaths, and unused or obsolete files that are effectively no longer in use. The original intention is for this Canonical Project Directory to be as reliable as possible, but during the throws of development, details tend to get updated in some places but not others each moment.*

```
PeriDocs-code/                         # Root project folder
│
├─ app/                                # Backend + frontend application code
│  │
│  ├─ helpers/
│  │  ├─ __init__.py
│  │  ├─ entry_similarity.py           # raw similarity computations for entry-to-entry
│  │  ├─ file_ops.py                   # load_data, save_data, ensure_feedback_file
│  │  ├─ json_safe.py                  # Convert NumPy and other non-JSON-native types into JSON-serializable Python primitives.
│  │  └─  top_matches.py                # API-ready top matches + JSON-safe outputs
│  │
│  │
│  │
├─ routes/
│  │  ├─ __init__.py                   # Imports and attaches all route modules to the main FastAPI app
│  │  ├─ admin.py                      # "/admin-review"
│  │  ├─ feedback.py                   # "/feedback"
│  │  ├─ journal.py                    # "/submit", "/submit-success"
│  │  ├─ info_navigation.py            # "/", "/about", "/privacy-policy", "/terms-of-service"
│  │  └─ __pycache__/                
│  │
│  ├─ static/                            # Frontend static files
│  │  ├─ style.css                       # Main stylesheet
│  │  ├─ peridocs-ui.js                  # unified localStorage UI state: theme, cooldowns, modals, toasts, feedback/journal 
│  │  ├─ peridocs-logo-v1.png
│  │  ├─ peridocs-logo-v1-white.png
│  │  ├─ favicon.png
│  │  ├─ cookies-icon-by-trinh-ho-from-flaticon-dot-com.png #icon for privacy notice about local storage
│  │  ├─ cookiessanta-hat-free-icon-by-surang-from-flaticon-dot-com #icon to display for users who's local time is set to Deccember 25 of any year
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
│  │      ├─ footer.html
│  │      ├─ modal-crisis.html
│  │      └─ modal-feedback.html
│  │
│  │
│  └─ __pycache__/                       # Python compiled bytecode cache
│
│
│
├─ core/
│   ├─ map/
│   │   ├─ admin_review_helpers.py        # logic for creating a dashboard for human administrators at PeriDocs.
│   │   └─ centroids.py                   # making centroids / clusters / neighborhoods per nuanced emotion
│   │
│   │
│   │
│   └─ nlp/
│      ├─ __init__.py                     # Exposes core NLP pipeline, PII, embeddings, emotion, and crisis utilities.
│      ├─ clause_utils.py                 # Splits text into clauses (sentence-level granularity). Optionally merge clauses into windows of ~max_words to avoid too short embeddings.
│      ├─ crisis_detector.py              # Lemma-aware, thresholded detection of crisis-related content.
│      ├─ crisis_recorder.py              # Atomic storage of encrypted crisis records for flagged entries.
│      ├─ embeddings.py                   # Manages SentenceTransformer model, embedding computation, caching, and encryption.
│      ├─ hash_utils.py                   # Generates SHA hashes for unique IDs and text integrity tracking.
│      ├─ orthography.py                  # Dictates choices for norms of spelling, punctuation, boundaries of phrases, capitalization, hyphenation, etc.
│      ├─ pii.py                          # redact_pii, pattern library for emails, phone numbers, addresses, etc.
│      └─ process_entry.py                # Orchestrates NLP workflow per journal entry: embedding, centroid assignment, crisis check.
│
│
│
│
├─ data/                                  # Local data storage
│  ├─ feedback.json                       # Stored feedback and report inquiries
│  ├─ high-profile-addresses.json         # Prevents PII exposure
│  ├─ journals_embeddings_dump20251216_3.json       # Storage for embeddings to keep the main entries much more readable by humans.
│  ├─ journals.json                       # Stored journal entries
│  ├─ names_au.json                       # Common-enough first names and last names from Australia.
│  ├─ names_ca.json                       # Common-enough first names and last names from Canada.
│  ├─ names_ie.json                       # Common-enough first names and last names from Ireland.
│  ├─ names_in.json                       # Common-enough first names and last names from India.
│  ├─ names_nz.json                       # Common-enough first names and last names from New Zealand.
│  ├─ names_sg.json                       # Common-enough first names and last names from Singapore.
│  ├─ names_uk.json                       # Common-enough first names and last names from United Kingdom.
│  ├─ names_us.json                       # Common-enough first names and last names from United States.
│  ├─ names_za.json                       # Common-enough first names and last names from South Africa.
│  ├─ recorded_crises.json                # logs for crises that have been submitted to our servers. NOTE: These should never be entered into the main database.
│  └─ .gitkeep                            # Shows where the data/ folder is for the sake of being transparent on Github without detailing which files go in there
│
│
│
│
├─ models/                             # Where open source pre-trained context-understanding models lives
│   ├─ roberta-large/                  # Sentence-understanding model
│   │   ├─.locks/
│   │   │   └─ models--sentence-transformers--all-roberta-large-v1/
│   │   │           ├─ 2ea7ad0e45a9d1d1591782ba7e29a703d0758831.lock
│   │   │           ├─ 4ebe4bb3f3114daf2e4cc349f24873a1175a35d7.lock
│   │   │           ├─ 7a7f517f71e7a3286b03572ece4fb2e5a0571db6.lock
│   │   │           └─ [xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx].lock # Nine more files just like that
│   │   └─ models--sentence-transformers--all-roberta-large-v1/ # yes the same name
│   │               ├─ .no_exist/
│   │               │       └─ cf74d8acd4f198de950bf004b262e6accfed5d2c/
│   │               │                 └─ added_tokens.json
│   │               ├─ blobs/
│   │               │           ├─ 2ea7ad0e45a9d1d1591782ba7e29a703d0758831 # no . or "dot" extension nor / or "slash" extension
│   │               │           ├─ 4ebe4bb3f3114daf2e4cc349f24873a1175a35d7 # no . or "dot" extension nor / or "slash" extension
│   │               │           ├─ 7a7f517f71e7a3286b03572ece4fb2e5a0571db6 # no . or "dot" extension nor / or "slash" extension
│   │               │           └─ [xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx] # Nine more files just like that
│   │               ├─ refs/
│   │               │           ├─ main # no . or "dot" extension nor / or "slash" extension
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
├─ venv/                               # Python virtual environment (ignored by Git)
│   ├─ bin/                            # Executables (python, pip, etc.)
│   ├─ include/                        # Headers for building packages
│   ├─ lib/                            # Installed Python packages
│   ├─ share/                           # Shared resources for the virtual environment
│   └─ pyvenv.cfg                      # Virtual environment configuration
│
├─ .env                      # Private, proprietary data (never commit)
├─ .gitignore                # Files and folders ignored by Git
├─ README.md                 # Project overview, setup, and usage
├─ requirements.txt          # Pinned Python dependencies
└─ setup_roberta.py          # Setup file to run in terminal to be sure that the FOSS ML model is installed correctly.

```

---

## Notes

* The `--reload` flag automatically restarts the server when code changes.
* `data/journals.json` is intentionally ignored by Git for local journaling data.
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

