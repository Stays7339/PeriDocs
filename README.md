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

To crate a new key, open a bash (Born Again Shell) terminal or a zsh terminal(Z shell),
then past the following command and press the enter/return button on your keyboard:

Should work with Linux, MacOS, and Windows
```
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```



IMPORTANT! 
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

FIRST, run these commands in terminal so that HTTPS (encrypted web connection) is working properly

```bash
uvicorn app.routes:app \
  --host 0.0.0.0 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips="*"
```

(or add them into systemd if you're running a server on Liunx)

```bash
ExecStart=/path/to/venv/bin/uvicorn app.routes:app \
  --host 127.0.0.1 \
  --port 8000 \
  --proxy-headers \
  --forwarded-allow-ips=127.0.0.1
  ```

then for nginx configuration file

```
proxy_set_header X-Forwarded-Proto $scheme;
```

THEN, AFTER you're done with that first command,


Run this command inside the project folder:

```bash
uvicorn app.routes:app --host 0.0.0.0 --port 8000 --reload
```

You should see output similar to:

```
INFO:     Uvicorn running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

(or for an already configured server)

git pull && sudo systemctl restart peridocs


---

### Step 6. Open the App

Open your browser and go to:

```
http://127.0.0.1:8000/
```

You now have PeriDocs running locally.

---

For public servers AFTER thoroughly configuring firewalld, nginx, let's encrypt, FastAPI, and systemctl 

go to: {yourChosenName}.yourTopLevelDomain

You should automatically get connected to HTTPS without having to specify it in your browser.

### Step 7. (Optional) Developer Tooling Setup

#### VS Code Recommended Setup

1. Install VS Code: [https://code.visualstudio.com/](https://code.visualstudio.com/)
2. Open the PeriDocs-code folder in VS Code.


---

## The Dynamic Process Workflow
```
[ Raw User Submission ]
          │
          ▼
┌───────────────────┐
│    app/routes     │  <--- Establishes the connection & captures payload
└───────────────────┘
          │
          ▼
┌───────────────────┐
│    core/nlp/pii   │  <--- ACTION: Runs regex patterns
└───────────────────┘
          │
          ▼  (State Change: Text is now sanitized/anonymous)
          │
┌───────────────────┐
│ core/nlp/clauses  │  <--- ACTION: Breaks text into sentence-level chunks
└───────────────────┘
          │
          ▼
┌───────────────────────────┐
│ core/nlp/crisis_detector  │
└───────────────────────────┘
          │
          ├── [ IF CRISIS TRIGGERED ] ──► core/nlp/crisis_recorder ──► [ Encrypted Isolation Lockfile ]
          │
          └── [ IF CLEAR ] 
                  │
                  ▼
      ┌───────────────────────┐
      │  core/nlp/embeddings  │  <--- ACTION: Passes clean text to RoBERTa model
      └───────────────────────┘
                  │
                  ▼  (State Change: Text becomes a 1024-dimension vector float)
                  │
      ┌───────────────────────────────┐
      │ core/map/membership_sequencer │  <--- ACTION: Evaluates mathematical cluster overlap
      └───────────────────────────────┘
                  │
                  ▼
      ┌───────────────────────┐
      │    core/map/ledger    │  <--- ACTION: Registers the event in numerical order
      └───────────────────────┘
                  │
                  ▼  (Final State: Persisted to disk)
                  │
         [ data/entries.json ]

```

# Canonical Project Directory 

<details>
<summary>Click to expand canonical project directory</summary>
## Canonical Project Directory as of 2026-07-12T16:59-04:00
**Important Note**: *While the software developers of PeriDocs try their best to keep the following project directory updated as best as they can, there may be some old filenames, old filepaths, and unused or obsolete files that are effectively no longer in use. The original intention is for this Canonical Project Directory to be as reliable as possible, but during the throws of development, details tend to get updated in some places but not others each moment.*

```
PeriDocs/                         # Root project folder
│
├─ app/                                # Backend + frontend application code
│  │
│  ├─ credentialing/
│  │  ├─ account_routing.py
│  │  ├─ account_runtime.py       
│  │  ├─ authentication_middleware.py    
│  │  ├─ security_fundamentals.py 
│  │  └─ __pycache__/  
│  ├─ helpers/
│  │  ├─ __init__.py                   # FastAPI app startup, embedding preloading, centroid loading, static mounting, route inclusion.
│  │  ├─ file_ops.py                  # Thin script to persist short plaintext strings of feedback to the backend in an isolated dumb json file.
│  │  ├─ json_safe.py                  # Convert NumPy and other non-JSON-native types into JSON-serializable Python primitives.
│  │  └─ __pycache__/  
│  │
│  │
├─ routes/
│  │  ├─ __init__.py                   # Imports and attaches all route modules to the main FastAPI app
│  │  ├─ admin_routing.py              # "/admin*"
│  │  ├─ donation.py                   # Provides routing to Stripe Checkout page for the amount and frequency that user opts-in to.
│  │  ├─ feedback.py                   # "/feedback"
│  │  ├─ info_navigation.py            # "/", "/about", "/privacy-policy", "/terms-of-service"
│  │  ├─ submission_routing.py                      # "/submit", "/submit-success"
│  │  └─ __pycache__/                
│  │
│  ├─ static/                            # raw files served directly to browser unchanged
│  │  ├─ account_authentication.js       # We're currently considering moving this into PeriDocs/app/credentialing  
│  │  ├─ account-signin-responsiveness.js  
│  │  ├─ account-signup-responsiveness.js  
│  │  ├─ admin_review_ux.js              # Logic for getting the information from the client webpage to the actual server.
│  │  ├─ arrow.svg                        # Adds some fun flair for the hero on the landing page.
│  │  ├─ base-html-responsiveness.js      # this is the part of the code that helps us do custom widths on the header's navigation bar without us having to hardcode position and width in that nav bar.
│  │  ├─ cookies-icon-by-trinh-ho-from-flaticon-dot-com.png  #icon for privacy notice about local storage
│  │  ├─ custom-styled-text-field.css     # autocomplete dropdown for text fields on webpages
│  │  ├─ donation-ui.js                   # Provides toast messages and redirects to assiting in routing to Stripe Checkout page for the amount and frequency that user opts-in to.
│  │  ├─ entry-frontend.js                # controls the javascript for transporting the entry from the page to the server while being sure CSRF is enabled. Also calls on the toast system and websocket
│  │  ├─ feedback-ui.js                   # controls the transportation of feedback from the page to the server. This file also uses CSRF.
│  │  ├─ fi-rr-search-alt.svg             # icon for the button leading to the create-entry page
│  │  ├─ globals.css                      # webpage styling that should be applied everywhere
│  │  ├─ info-card-border.png             # decorative framing for landing page content
│  │  ├─ modal-ui.js                      # Controls the behavior of modals (i.e., site-official popups)
│  │  ├─ myers-reset-2.0.css              # public domain boilerplate code that helps to keep css styling consistent across different web browsers
│  │  ├─ [... some images from the public domain just for style ...]
│  │  ├─ peridocs-logo-icon-2026-05-05.svg
│  │  ├─ peridocs-logo-icon-and-wordmark-2026-05-05.svg
│  │  ├─ peridocs-logo-workmark-2026-05-05.svg
│  │  ├─ peridocs-misc-ux.js                  # handles many things including but not limited to: theme toggle (light mode / dark mode), cooldowns...
│  │  ├─ peridocs-wordmark-and-logo-v2.png 
│  │  ├─ styleguide.css                       # Where all the brainstorming for the brand goes
│  │  ├─ stylesheet.css                       # Where the styling choises are chosen and carried out
│  │  ├─ toast-ui.js 
│  │  ├─ user-icon.png
│  │  ├─ user-icon.svg
│  │  └─ CabinetGrotesk_Complete/Fonts/WEB/fonts
│  │
│  │
│  └─ templates/                          # server-rendered files processed by Jinja
│   ├─ about.html                         # About page template
│   ├─ account-signin.html                
│   ├─ account-signup.html                
│   ├─ account.html                       
│   ├─ admin-review.html              # Dashboard to manage centroids, which are neighborhoods of an common theme populated by user entries.
│   ├─ base.html                       # The new new more polished looking base (floating header + background)
│   ├─ create-entry.html 
│   ├─ delete.html                    # The public facing page where users can go and enter a one-time string generated with their post so that posts can be deleted without an account. Works by hasing that string and matching the hash based on what's within the entries.json file.
│   ├─ index.html                     # Landing page template
│   ├─ privacy.html                   # Privacy policy page template
│   ├─ submit-success.html            # Submission success page template
│   ├─ terms-of-service.html          # Terms of Service page template
│   ├─ ways-to-help.html          # Terms of Service page template
│   └─ includes/                      # Partial web-page templates
│      ├─ modal-crisis.html
│      └─ modal-feedback.html
│
│
│
├─backups-for-the-main-data-folder
│   └─peridocs_backup_[YYYY]-[MM]-[DD]T[HH]-[mm]-[ss]Z.zip
│
│
│
├─ core/
│   ├─ database.py # as the operational runtime glue that grabs the lower-level environment-agnostic engines and binds them to the live application via web-framework elements (i.e. this imports FastAPI).
│   ├─ mode_lock.py # forces the app to focus on either only saving to PostgreSQL or only saving only to JSON and NPZ files, but never both of those options.
│   │
│   │
│   ├─ entry-orchestrator/                      
│   │   ├─ __init__.py              # Exposes EntryRuntime
│   │   ├─ entry_runtime.py      # Single-event pipeline with rich payload. state manager + persistence authority.
│   │   └─ entry_similarity.py           # Can handle loading embeddings from disk, raw similarity computations for embeddings, and deterministic mean. Other files may still use their own internal helpers rather than calling this file.
│   │
│   │
│   │
│   ├─ map/
│   │   ├─ __init__.py                    # to avoid having to redfine the same value everywhere, this is being used as a config file for this specific package
│   │   ├─ centroids.py                   # The Engine - making centroids / clusters / neighborhoods per nuanced common theme and some (but not all) SAAJE affiliations.
│   │   ├─ deletion.py                    # The Surgical Pulverizer - if a user wants something removed, it should all go through here.
│   │   ├─ entry_membership_sequencer.py                       # The Evaluation Layer - controls assignment of Software-auto-added journal entries (SAAJEs). This is so that centroids-math (which is in centroids.py) stays separate from assignment to centroids which stays separate from the admin dashboard for human intervention, which stays separate from the historical ledger for determinism.
│   │   ├─ ledger.py                      # ==== THE CRITICAL AUTHORITY===== FOR ALL OF PERIDOCS CENTROIDS SYSTEM. Keeps track of thuth via sequence of actions across the system, rather than through the veriability of time, which quietly throws off determinism.
│   │   ├─ mapping_runtime.py             # The Instantiation Boundary - Prevents against excessive coupling, repo fragility, and code sprawl.
│   │   ├─ perist_reasoning_data.py       # Used so that we can switch between JSON and TTL files for the sake of helping for ontology quieries.
│   │   ├─ subregion_detector.py          # Used to detect areas of notable density inside of what's defined as technically one centroids. That way, the system has the ability to lightly suggest the potential of multiple centroids being made from that larger conglomerate of a given centroid.
│   │   └─ __pycache__/
│   │
│   ├─  nlp/
│   |   ├─ __init__.py                     # Exposes core NLP pipeline, PII, embeddings, common theme, and crisis utilities.
│   |   ├─ clause_utils.py                 # Splits text into clauses (sentence-level granularity). Optionally merge clauses into windows of ~max_words to avoid too short embeddings.
│   |   ├─ crisis_detector.py              # Lemma-aware, thresholded detection of crisis-related content.
│   |   ├─ crisis_recorder.py              # Atomic storage of encrypted crisis records for flagged entries.
│   |   ├─ embeddings.py                   # Manages all encryption, SentenceTransformer model, embedding computation, and caching.
│   |   ├─ hash_utils.py                   # Generates SHA hashes for unique IDs and text integrity tracking.
│   |   ├─ orthography.py                  # Dictates choices for norms of spelling, punctuation, boundaries of phrases, capitalization, hyphenation, etc.
│   |   ├─ pii.py                          # redact_pii, pattern library for emails, phone numbers, addresses, etc.
│   |   ├─ process_entry.py                # Orchestrates NLP workflow per journal entry: embedding centroid assignment, crisis check.
│   |   └─ __pycache__/
│   | 
│   | 
│   ├─ reasoning/
│   |       ├─ __init__.py # Just there so that its straightforward to call on functions in this filepath.
│   |       ├─ build_evaluation_group.py # finds which centroids / concepts are in question for the starting point for the context of the inferences being made
│   |       ├─ damping.py # the purpose of this file, currently, is to make later inferences have less influence than future inferences
│   |       ├─ evaluator.py # the longest script (as of 2026-04-23) because it does the leg work of using concepts, heuristics, and inferences in one fell swoop. This file heavily relies on types.py .
│   |       ├─ heuristic_loader.py # tried to make the name as self-explanatory as possible. Ideally, this file would call into memory any heuristic file that contains the concepts / centroids in question.
│   |       ├─ reasoning_runtime.py # the most important part of this file is to loop the evaluator over and over, up to a set number of times specified within this same file.
│   |       ├─ receipt_maker.py # responsible for keeping an appended record of what inferences were made from which heuristics, and which heuristics were used based on the relevant concepts.
│   |       └─ types.py # A class file that sets a template solely for what is and isn't allowed to be used in the inference process. In contrast, dicts don't work because they scatter/spill/sprawl important metadata way too easily. And functions don't let a working idea evolve nearly as easily as an isntance formed from a class.
│   | 
│   | 
│   ├─ database.py # builds the foundations of the bridge between the database and the runtime of the app. Also helps open and close the database when starting and stopping the app.
│   └─ mode_lock.py  # forces the system to remember whether it started in database mode (PostgreSQL or Flat-file JSON + NPZ) upon the first time setting up the app (bootstrapping) with no data subfolder / a blank database.
│ 
│           
│
├─ data/                                  # Local data storage
│  ├─ accounts/
│  │   └─accounts.encrypted.json
│  │
│  │
│  ├─ centroids/
│  │   ├─[centroid/precentroid]_[natural_sort_integer]_summary.json
│  │   └─[centroid/precentroid]_[natural_sort_integer].npz
│  ├─ entries/                        # Stored entries
│  │   ├─ entries.json # safe text in plaintext with encrypted raw text. Also important metadata is contained here.
│  │   ├─ entries_window_embeddings_dump.npz # embedding vectors for thousands of float numbers per every few sentences in each entry.
│  │   ├─ entries_window_text_dump.npz # plain-text-safe-text is stored for how the windows of the entry were specifically partitioned.
│  │   ├─ entries_mean_embeddings_dump.npz # embedding vectors for thousands of float numbers per every entry overall.
│  │   └─ entries_standout_window_flags_dump.npz # true or false as to whether one part of the entry is drastically different from the rest of that same entry
│  ├─ reasoning_data/                        # Stored entries
│  │   ├─ heuristics.json
│  │   └─ [concept files ending in .ttl, beginning with various names, often but not always centroid [x]]
│  ├─ feedback.json                       # Stored feedback and report inquiries
│  ├─ .system_mode_lock                   # the actual file that remembers whether the app should be sticking to database mode (including Sandbox mode) or sticking to offline / flat-file mode
│  ├─ ledger.json                         # Keeps track of which event took place at which step, numbered one at a time in sequence.
│  ├─ recorded_crises.lock                # For preventing corrupted data in case of crash.
│  ├─ recorded_crises.npz                 # logs for crises that have been submitted to our servers. NOTE: These should never be entered into the main database.
│  └─ .gitkeep                            # Shows where the data/ folder is for the sake of being transparent on Github without detailing which files go in there
│
│
├─ database-management/ # aims to be an environment-agnostic infrastructure layer. It holds static SQL schemas, validation utilities, and raw storage drivers
│   ├─ schemas/
│   │     ├─00_db_init.sql # initializes the physical catalog storage engine if absent.
│   │     ├─01_roles_init.sql # loosely defines roles for the postgres instance itself, not for the webapp
│   │     ├─02_schemas_init.sql # Establish clean structural boundaries to enforce domain separation,
│   │     ├─03_permissions_init.sql # specifies what each database role can do
│   │     └─ tables/
│   │          ├─ app_schema.sql # Current just stores information for webapp end-user accounts.
│   │          ├─ content_schema.sql # Stores the main user data. the raw text entries, their AI vector math, and those Creative Commons/public domain outlinks you mentioned.
│   │          ├─ kb_schema.sql # Stores the moderation logic. the 500 approved concepts and the rules connecting those concepts to the outlinks.
│   │          ├─ ledger_schema.sql # A historical logbook that tracks changes (great for backups and audit trails).
│   │          └─ search_schema.sql # Vector Index & Cluster Optimization Storage
│   │
│   ├─ storage_engines/
│   │     ├─ __init__.py            # Exposes the factory/bootloader
│   │     └─ postgres_engine.py    # The actual worker code that takes Python data (like a user's text entry) and translates it into a SQL command to save it.
│   │
│   └─ validation/ 
│      └─ verify_infrastructure.py 
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
├─ venv/                               # Recreated upon system initialization / bootstrap for the whole project, after installing requirements.txt using 'pip install' and after setup_roberta.py.
│
├─ .env                      # Private, proprietary data (never commit)
├─ .gitignore                # Files and folders ignored by Git
├─ audit_entries_store.py
├─ list_the_table_of_contents_for_this_npz_file.py
├─ README.md                 # Project overview, setup, and usage
├─ requirements.txt          # Pinned Python dependencies
├─ setup_roberta.py          # Setup file to run in terminal to be sure that the FOSS ML model is installed correctly.
└─ setup.py  # loads in the specific configurations of the database, including specifiying between test sandbox empty dummy vs local actual database vs centralized real production server. Also, runs the setup_roberta.py script mentioned before.
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

