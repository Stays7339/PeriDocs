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
````

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


## Canonical Project Directory as of 13 November 2025


```
PeriDocs-code/                         # Root project folder
│
├─ models/                             # Where open source pre-trained context-understanding models lives
│   ├─ roberta-large/                  # Sentence-understanding model
│   └─ .gitkeep                        #a voids pushing the whole pre-trained one-way dataset through GitHub
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
│  │  ├─ lexicon_admin.py              # Hidden admin route for lexicon moderation. Requires ADMIN_TOKEN in .env (string). Not linked from navigation.
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
│   └─ nlp/
│      ├─ __init__.py                     # Exposes document_features; acts as import hub for NLP modules.
│      ├─ anchors.py                      # Defines anchor word lists for emotion/semantic weighting.
│      ├─ crisis.py                       # Detects crisis indicators and escalation flags.
│      ├─ embeddings.py                   # Handles SentenceTransformer model, embedding caching, and vector ops.
│      ├─ emotion_analysis.py             # Computes emotion lexicon match, valence/arousal summary, and embedding-weighted emotion distribution.
│      ├─ encryption.py                   # encrypt_text / decrypt_text functions for sensitive fields.
│      ├─ fuzzy_utils.py                  # Fuzzy string matching + dynamic lexicon loader.
│      ├─ hash_utils.py                   # Generates SHA8 hashes for unique IDs and text integrity tracking.
│      ├─ pii.py                          # redact_pii, pattern library for emails, phone numbers, addresses, etc.
│      ├─ process_entry.py                # Main pipeline orchestrator: calls preprocessing, PII redaction, emotion, embeddings, sentiment, and echo weighting.
│      ├─ repetition_echo.py              # Detects and weighs phrase repetition to reduce redundancy bias.
│      ├─ sentiment_analysis.py           # Calculates polarity, subjectivity, and maps sentiment into categorical buckets.
│      ├─ test_pipeline.py                # Comprehensive test suite for NLP pipeline modules (unit + integration).
│      └─ text_processing.py              # Text normalization, tokenization, basic linguistic preprocessing, and orchestrates lower-level modules.
│
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
├─ embeddings_explainer.md                # Overview created by GPT-5, who also drafted the particular wording of the code.
├─ requirements.txt                       # Pinned Python dependencies
└─ .gitignore                             # Files and folders ignored by Git
```

---

## Notes

* The `--reload` flag automatically restarts the server when code changes.
* `data/journals.json` is intentionally ignored by Git for local journaling data.
* Virtual environment: `venv/` (excluded from Git since it only is used to install libraries and and just run the code once until deleted. PeriDocs proprietary code is not stored in `venv/` and libraries can be redownloaded from their third-party severs with ```pip install -r requirements.txt``` )



## Fully corrected vertical-flow ASCII map as of 13 November 2025.

```
Raw Text Input
    │
    ▼
process_entry.py
    * text_processing.py.clean_text
    * text_processing.py.tokenize_text
    * pii.py.redact_pii
    * repetition_echo.py.weight_repetition
    * sentiment_analysis.py.analyze_sentiment
    * crisis.py.detect_crisis
    │
    ▼
text_processing.py.process_text
    │→ cleaned text
    │→ token_dicts
    │→ token_strings
    │→ features
    * text_processing.py.document_features
        │
        * _lexicon_emotion_features(tokens)
            │
            * detect_emotion_tokens(tokens)
                │
                * anchors.py._EMOTION_LEXICONS
                * fuzzy_utils.py.get_combined_lexicons
                * fuzzy_utils.py.fuzzy_matches_above
        │ outputs: 
            token_count
            emotion_anchor_hits
            raw_emotion_hits
        │
        * emotion_analysis.py.analyze_emotions(raw_text)
            │
            * embeddings.py.compute_embedding_vectors
            │ outputs:
                embedding_emotion_distribution
                valence_arousal_summary
    │
    ▼
process_entry.py collects all outputs:
    cleaned text
    token_dicts
    token_strings
    features = {
        token_count
        emotion_anchor_hits
        raw_emotion_hits
        embedding_emotion_distribution
        valence_arousal_summary
        sentiment
        repetition_weight
        crisis_flag
    }
    │
    ▼
core/nlp/__init__.py
    * exposes process_entry.py
    * exposes document_features / hooks to all NLP modules
    │
    ▼
External callers
    (app/routes/journal.py, app/helpers/display_last_entry.py, etc.)
```

---

### Notes on the diagram:

* `*` = Python module dependency
* `→` = data flow/output
* `process_entry.py` **does not call `emotion_analysis.py` directly** anymore.
* `emotion_analysis.py` is invoked **only inside `document_features(raw_text)`**, which is called by `text_processing.py`.
* `embeddings.py` is used **inside `emotion_analysis.py`**.
* Secondary modules (`pii.py`, `repetition_echo.py`, `sentiment_analysis.py`, `crisis.py`) feed directly into `process_entry.py`, not `text_processing.py`.








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

