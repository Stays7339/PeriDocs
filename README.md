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

2. Install Python 3.11+ and Git:

   ```bash
   brew install python@3.11 git
   ```

3. Verify installations:

   ```bash
   python3 --version
   git --version
   ```

   (If `python3` is not found, run `brew link python@3.11`)

---

#### For Linux (Ubuntu/Debian-based)

1. Update and install dependencies:

   ```bash
   sudo apt update && sudo apt upgrade -y
   sudo apt install -y python3.11 python3.11-venv python3-pip git curl
   ```

2. Verify installations:

   ```bash
   python3 --version
   git --version
   ```

3. (Optional) If you are using another distribution, substitute the package manager (dnf, pacman, etc.) as appropriate.

---

#### For Windows

1. Install Git for Windows
   Download and install from: [https://git-scm.com/download/win](https://git-scm.com/download/win)
   During setup, choose:

   * "Use Git from the Windows Command Prompt"
   * "Checkout Windows-style, commit Unix-style line endings"

2. Install Python 3.11 UP TO BUT NOT AFTER Python 3.13
   Download from: [https://www.python.org/downloads/windows/](https://www.python.org/downloads/windows/)
   During setup:

   * Check "Add Python to PATH"
   * Include pip during installation

3. Verify installations:
   Open Command Prompt (or PowerShell):

   ```powershell
   python --version
   git --version
   ```

---

### Step 1. Clone the Repository

Choose a folder to hold the project (for example, Desktop or Documents).

```bash
git clone https://github.com/Stays7339/PeriDocs.git
cd PeriDocs-code
```

---

### Step 2. Create a Virtual Environment

#### macOS / Linux

```bash
python3.11 -m venv venv
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

### Step 4. Run the App Locally

Run this command inside the project folder:

```bash
uvicorn app.routes:app --reload
```

You should see output similar to:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

---

### Step 5. Open the App

Open your browser and go to:

```
http://127.0.0.1:8000/
```

You now have PeriDocs running locally.

---

### Step 6. (Optional) Developer Tooling Setup

#### VS Code Recommended Setup

1. Install VS Code: [https://code.visualstudio.com/](https://code.visualstudio.com/)
2. Open the PeriDocs-code folder in VS Code.

## Canonical Project Directory


```
PeriDocs-code/                         # Root project folder
│
├─ models/                             # Where all-MiniLM (open source) lives
│   ├─ all-MiniLM-L6-v2                # pending summary comment
│   │  ├─ 1_Pooling/                   # contains just one file (config.json)
│   │  ├─ 2_Normalize/                 # contains no files
│   │  ├─ config_sentence_transformers.json                 # pending summary comment
│   │  ├─ config.json                 # pending summary comment
│   │  ├─ model.safetensors            # pending summary comment
│   │  ├─ modules.json                 # pending summary comment
│   │  ├─ README.md                    # "By default, input text longer than 256 word pieces is truncated."
│   │  ├─ sentence_bert_config.json    # pending summary comment
│   │  ├─ special_tokens_map.json      # pending summary comment
│   │  ├─ tokenizer_config.json        # pending summary comment
│   │  ├─ tokenizer.json               # pending summary comment
│   │  └─ vocab.txt                    # pending summary comment
│   └─ .gitkeep #avoids pushing the whole pre-trained one-way dataset through GitHub
│
├─ venv/                               # Python virtual environment (ignored by Git)
│   ├─ bin/                            # Executables (python, pip, etc.)
│   ├─ include/                        # Headers for building packages
│   ├─ lib/                            # Installed Python packages
│   ├─ share/                          # Shared resources for the virtual environment
│   └─ pyvenv.cfg                      # Virtual environment configuration
│
├─ app/                                # Backend + frontend application code
│  ├─ routes/
│  │  ├─ __init__.py                   # Imports and attaches all route modules to the main FastAPI app
│  │  ├─ feedback.py                   # "/feedback"
│  │  ├─ journal.py                    # "/submit", "/submit-success"
│  │  ├─/lexicon_admin.py              # Hidden admin route for lexicon moderation. Requires ADMIN_TOKEN in .env (string). Not linked from navigation.
│  │  ├─ main.py                       # "/", "/about", "/privacy-policy", "/terms-of-service"
│  │  └─ __pycache__/                
│  │
│  ├─ helpers/
│  │  ├─ __init__.py
│  │  ├─ display_last_entry.py         # GET: display last entry, sentiment, emotion, repetition
│  │  ├─ file_ops.py                   # load_data, save_data, ensure_feedback_file
│  │  ├─ json_safe.py                  # JSON secure operations (NumPy-safe)
│  │  ├─ security.py                   # optional: encryption/decryption, hashing helpers
│  │  ├─ similarity.py                 # raw similarity computations
│  │  └─ top_matches.py                # API-ready top matches + JSON-safe outputs
│  │
│  ├─ templates/                        # Jinja2 HTML templates
│  │  ├─ about.html                     # About page template
│  │  ├─ base.html                      # Layout template
│  │  ├─ index.html                     # Main homepage template
│  │  ├─ lexicon_admin.html             # Front-end UI for staff only, planned to be hidden before public release
│  │  ├─ privacy.html                   # Privacy policy page template
│  │  ├─ submit-success.html            # Submission success page template
│  │  ├─ terms-of-service.html          # Terms of Service page template
│  │  └─ includes/                      # Partial web-page templates
│  │      ├─ footer.html
│  │      └─ modal-feedback.html
│  │
│  ├─ static/                            # Frontend static files
│  │  ├─ cooldown.js                     # Handles global cooldowns for submission forms
│  │  ├─ style.css                       # Main stylesheet 
│  │  ├─ theme-toggle.js                 # Dark Mode toggle
│  │  ├─ feedback.js                     # Feedback modal JS
│  │  ├─ localStorage.js                 # What the general public commonly refer to as cookies.
│  │  ├─ peridocs-logo-v1.png
│  │  ├─ peridocs-logo-v1-white.png
│  │  ├─ favicon.png
│  │  ├─ cookies-icon-by-trinh-ho-from-flaticon-dot-com.png #icon for cookies
│  │  └─ CabinetGrotesk_Complete/Fonts/WEB/fonts
│  │
│  └─ __pycache__/                       # Python compiled bytecode cache
│
├─ core/
│  └─ nlp/                                # Modular NLP functionality (replaces monolithic nlp.py)
│      ├─ __init__.py                     # Exposes document_features and hooks to all NLP modules
│      ├─ anchors.py                      # Adds in a set list of anchor words for detections and analysis
│      ├─ crisis.py                       # crisis detection functions
│      ├─ embeddings.py                   # token embeddings cache, SentenceTransformer wrapper
│      ├─ emotion_analysis.py             # Emotion lexicon & summary
│      ├─ encryption.py                   # encrypt_text / decrypt_text
│      ├─ fuzzy_utils.py                  # Fuzzy matching lexicon utilities and dynamic lexicon loader for PeriDocs.
│      ├─ hash_utils.py                   # SHA8 hashing for unique IDs
│      ├─ pii.py                          # redact_pii, patterns, high-profile addresses
│      ├─ process_entry.py                # Full NLP processing pipeline for a single journal entry.
│      ├─ repetition_echo.py              # Repetition / echo weighting
│      ├─ sentiment_analysis.py           # Polarity, subjectivity, sentiment bucket
│      ├─ test_pipleline.py               # Tests the features implement for the actual processing of journal entries
│      └─ text_processing.py              # Tokenization, text cleaning, orchestrates NLP modules
│
├─ data/                                  # Local data storage
│  ├─ dynamic_lexicon.json                # Lexicons obtained from users of service
│  ├─ feedback.json                       # Stored feedback and report inquiries
│  ├─ high-profile-addresses.json         # Prevents PII exposure
│  ├─ journals.json                       # Stored journal entries
│  ├─ suggest_lexicon.py                  #Scan journal entries for tokens not matched by the current combined lexicons.
│  └─ .gitkeep                            # Shows where the data/ folder is for the sake of being transparent on Github without detailing which files go in there
│
├─ .env                                   # Private, proprietary data (never commit)
├─ README.md                              # Project overview, setup, and usage
├─ requirements.txt                       # Pinned Python dependencies
└─ .gitignore                             # Files and folders ignored by Git
```

---

## Notes

* The `--reload` flag automatically restarts the server when code changes.
* `main.py` has been deleted; `routes.py` is now the primary entry point.
* Background image files remain local and are not committed to GitHub.
* `data/journals.json` is intentionally ignored by Git for local journaling data.
* Backend entrypoint: `app.routes:app`
* Templates: `app/templates/`
* Static files: `app/static/`
* Local journal storage: `data/journals.json`
* Virtual environment: `venv/` (excluded from Git)

---
