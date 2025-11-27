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


## Canonical Project Directory as of 22 November 2025 (202511221924)

```
PeriDocs-code/                         # Root project folder
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
│  │  ├─ journal_helpers.py            # sentiment, pruning, embedding utilities
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
│      ├─ crisis_writer.py                # Pending description.
│      ├─ crisis.py                       # Detects crisis indicators and escalation flags.
│      ├─ embeddings.py                   # Handles SentenceTransformer model, embedding caching, and vector ops.
│      ├─ emotion_analysis.py             # Computes emotion lexicon match, valence/arousal summary, and embedding-weighted emotion distribution.
│      ├─ encryption.py                   # encrypt_text / decrypt_text functions for sensitive fields.
│      ├─ fuzzy_utils.py                  # Fuzzy string matching + dynamic lexicon loader.
│      ├─ hash_utils.py                   # Generates SHA8 hashes for unique IDs and text integrity tracking.
│      ├─ pii.py                          # redact_pii, pattern library for emails, phone numbers, addresses, etc.
│      ├─ process_entry.py                # Main pipeline orchestrator: calls preprocessing, PII redaction, emotion, embeddings, sentiment, and echo weighting. early returns for crises skip embeddings, sentiment, and emotion calculation, which is intentional for security and performance.
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
│  ├─ suggest_lexicon.py                  # Scan journal entries for tokens not matched by the current combined lexicons.
│  ├─ names_au.json
│  ├─ names_ca.json
│  ├─ names_ie.json
│  ├─ names_in.json
│  ├─ names_nz.json
│  ├─ names_sg.json
│  ├─ names_uk.json
│  ├─ names_us.json
│  ├─ names_za.json
│  ├─ recorded_crises.json
│  └─ .gitkeep                            # Shows where the data/ folder is for the sake of being transparent on Github without detailing which files go in there
│
├─ .env                      # Private, proprietary data (never commit)
├─ .gitignore                # Files and folders ignored by Git
├─ debug_embeddings.py       # Debugging for running emebeddings only, not the full suite
├─ embeddings_explainer.md   # Overview created by GPT-5, who also drafted the particular wording of the code.
├─ README.md                 # Project overview, setup, and usage
├─ requirements.txt          # Pinned Python dependencies
├─ setup_roberta.py          # Setup file to run in terminal to be sure that the FOSS ML model is installed correctly.
├─ test_dsmx.py              # testing for deterministic softmax-like scaling for emotion distributions.
└─ test_mps.py               # testing for Apples GPUs, NVIDIA GPUs, and CPUs from AMD and Intel.
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

