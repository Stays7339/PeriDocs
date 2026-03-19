# PeriDocs.org

An ad-free free-to-the-public platform which systematically indexes and cites writing passages which focus on mixing anecdotes & recurring collective experiences with applied philosophy. PeriDocs avoids applied psychology, and PeriDocs avoids claiming professionalism of any kind; at the same time, PeriDocs believes that there is a lot of public good that can be done unto many people by reducing the friction of searching for non-paywalled rigorous sources. PeriDocs plans to do this via deterministic fine-tuning around the specific search query that the user sends to us.
Users may actively choose to rigorously describe their perspective of the world, and they would get more-relevant results as a process. They would also be able to opt-in to keep their search query as its own perpetual public entry on the platform, so it, too, can contribute to the way people described lived experiences in ways that often go unarticulated. 

---


## PeriDocs Full Setup Instructions (from Zero to Running Webapp)

Imagine you are starting with a completely clean machine. The instructions cover **macOS, Linux (like openSUSE), and Windows**, and assume you are not working as root except where necessary for initial permissions.

### Step 0: Decide Your User

You **do not need to create a new admin/root user**, but you **should not run the app under an admin/root account**. Any pre-existing standard user account is fine, as long as you have **full write permissions in the folder where PeriDocs will live**.

* Example safe locations: `/home/username/peridocs` on Linux/macOS, or `C:\Users\username\peridocs` on Windows.
* The setup script will create `.ssh` and `app` folders under this root directory.

**Important:** Do **not** run the webapp as root—this prevents permissions and SSH problems like we’ve seen.

---

### Step 1: SSH Key Setup and Permissions

1. Run the setup script with your standard user account. The script will:

   * Check if an SSH key already exists for this user.
   * If not, generate a new SSH key.
   * Display the **public key** so you can copy it into your GitHub account.

2. The script will pause and ask you to confirm that the key has been added to GitHub. This ensures that later, when the app pulls the repository, it can authenticate without root or manual password entry.

**Tip:** This SSH key is created **one level above your app folder**—for example, if your PeriDocs root is `/home/user/peridocs`, the key lives in `/home/user/peridocs/.ssh`.

---

### Step 2: `.env` File Creation and Fernet Key

1. After SSH setup, the script prompts you to create and fill a `.env` file in `peridocs/app/`.

2. You can either:

   * Let the script generate a Fernet key for you, or
   * Provide a Fernet key from an **encrypted password manager** if you already have one.

3. This `.env` file is **mandatory**. Without it, the webapp **will not start**, because the encryption key is required for internal operations.

**Tip:** Keep the `.env` file private. Never commit it to GitHub. The script ensures it is created in the correct folder relative to `.ssh` so everything can interact properly.

---

### Step 3: Pull Repository

1. With SSH configured and `.env` in place, the script **pulls the repository** into `peridocs/app`.
2. If the folder already exists, the script will **update the repository instead of cloning**.
3. At this point, `.env` is already present and the SSH key allows GitHub authentication without root.

**Why this order matters:** Pulling the repo before `.env` exists or before SSH is set up will fail the daemon and prevent the RoBERTa model from installing correctly.

---

### Step 4: Virtual Environment and Dependencies

1. The script creates a **Python virtual environment** inside the app folder (`venv`) to isolate dependencies from the system.
2. It automatically installs all Python packages listed in `requirements.txt`.

**Tip for MacOS, Linux, Windows:**

* macOS/Linux: `python3 -m venv venv` and `source venv/bin/activate`
* Windows: `python -m venv venv` and `venv\Scripts\activate`

This step ensures the correct versions of PyTorch, sentence-transformers, and other dependencies are installed, including the CPU-only version of PyTorch.

---

### Step 5: Setup RoBERTa Model

1. After dependencies are installed, the script runs `setup_roberta.py`.
2. This downloads a **snapshot-locked RoBERTa model**, symlinks it to `app/models/roberta-large`, and enforces offline mode.
3. The script performs a deterministic embedding test to make sure the model is loaded correctly.

**Important:** This step **must run after the virtual environment is ready** but **before systemd** or any daemon attempt to start the app.

---

### Step 6: Optional Systemd / Service Setup (Linux Only)

1. The script asks whether you want to set up the app as a **systemd service**.
2. If yes, it creates a non-root service running as the user you’re logged in as, pointing at the `venv` Python binary.
3. The script reloads systemd, enables the service, and can start it automatically.

**Tip:** Skip this step if you are a developer and only want to run the app locally.

---

### Step 7: Verify the Webapp

1. Run the app either via systemd (Linux) or manually:

   ```bash
   /path/to/peridocs/app/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
   ```

2. Open your browser at `http://127.0.0.1:8000/` to see the webapp running.

3. Check the terminal logs to ensure the RoBERTa embeddings loaded correctly and there are no errors about missing `.env` or permissions.

---

### Security Notes

* SSH key is generated **per user**, never under root.
* `.env` must be kept private.
* The script enforces non-root execution for app files, models, and the `.ssh` folder.
* Systemd runs as the non-root user if enabled.

**Minor things to note:**

* On Windows, systemd is skipped; you can use the virtual environment directly.
* On MacOS/Linux, ensure firewall rules allow port 8000 if you want external access.
* Fernet keys in `.env` must be unique per deployment to avoid conflicts.

---

### TL;DR Order of Operations

1. SSH keys & non-root permissions
2. `.env` creation + Fernet key
3. Pull repository into `peridocs/app`
4. Virtual environment setup & pip install
5. Run `setup_roberta.py` to download and validate model
6. Optional: systemd service setup (Linux only)
7. Run the webapp and verify

---

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

Absolutely. Let’s lay this out in simple, hand-holding English while keeping it **production-safe and context-specific**. I’ll include all the logic we’ve worked out for SSH, `.env`, repo pull, venv, RoBERTa setup, and optional systemd.

---


# Canonical Project Directory 

<details>
<summary>Click to expand canonical project directory</summary>
## Canonical Project Directory as of 24 February 2026 (202602241322 ; YYYYMMDDhhmm)
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
│   │   ├─ admin_review_helpers.py        # The Moderation Layer - logic for creating a dashboard for human administrators at PeriDocs.
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
│  ├─ [entries_embeddings_dumpYYYYMMDD_[0-3].json file(s)] # Storage for embeddings to keep the main entries much more readable by humans.
│  ├─ entries.json                        # Stored entries
│  ├─ feedback.json                       # Stored feedback and report inquiries
│  ├─ high-profile-addresses.json         # Prevents PII exposure     
│  ├─ names_au.json                       # Common-enough first names and last names from Australia.
│  ├─ names_ca.json                       # Common-enough first names and last names from Canada.
│  ├─ names_ie.json                       # Common-enough first names and last names from Ireland.
│  ├─ names_in.json                       # Common-enough first names and last names from India.
│  ├─ names_nz.json                       # Common-enough first names and last names from New Zealand.
│  ├─ names_sg.json                       # Common-enough first names and last names from Singapore.
│  ├─ names_uk.json                       # Common-enough first names and last names from United Kingdom.
│  ├─ names_us.json                       # Common-enough first names and last names from United States.
│  ├─ names_za.json                       # Common-enough first names and last names from South Africa.
│  ├─ recorded_crises.lock                # For preventing corrupted data in case of crash.
│  ├─ recorded_crises.npz                 # logs for crises that have been submitted to our servers. NOTE: These should never be entered into the main database.
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
├─ peridocs_full_setup_script.sh         # Installs .ssh, .env. venv, pip, pip libraries, and offline RoBERTa cache
└─ setup_roberta.py          # Setup file to run in terminal to be sure that the FOSS ML model is installed correctly.
```
</details>


# ^ ! ^ ! ^

---

## Notes

* The `--reload` flag automatically restarts the server when code changes.
* `data/entries.json` is intentionally ignored by Git for local user data.
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

