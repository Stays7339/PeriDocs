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

2. Install Python 3.11+
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

## Project Structure

```text
PeriDocs-code/                         # Root project folder
│
├─ venv/                               # Python virtual environment (ignored by Git)
│   ├─ bin/                            # Executables (python, pip, etc.)
│   ├─ include/                        # Headers for building packages
│   ├─ lib/                            # Installed Python packages
│   ├─ share/                          # Shared resources for the virtual environment
│   └─ pyvenv.cfg                      # Virtual environment configuration
│
├─ app/                                # Backend + frontend application code
│   ├─ routes.py                       # FastAPI route definitions (main app logic)
│   ├─ nlp.py                          # spaCy wrappers and text processing utilities
│   ├─ templates/                      # Jinja2 HTML templates
│   │   ├─ index.html                  # Main homepage template
│   │   ├─ about.html                  # About page template
│   │   ├─ privacy.html                # Privacy policy page template
│   │   ├─ base.html                   # Layout template for all webpages
│   │   ├─ submit-success.html         # Submission success template
│   │   ├─ includes/                   # Partial templates (included in other pages)
│   │   │   ├─ modal-feedback.html     # Feedback modal HTML
│   │   |   └─ footer.html             # Navigation links at the bottom of each webpage
│   ├─ static/                         # Frontend static files
│   │   ├─ cooldown.js                 # Handles global cooldowns for submission forms
│   │   ├─ style.css                   # Main stylesheet
│   │   ├─ theme-toggle.js             # Dark Mode toggle
│   │   ├─ feedback.js                 # Feedback modal JS
│   │   └─ CabinetGrotesk_Complete/Fonts/WEB/fonts   
│   └─ __pycache__/                    # Python compiled bytecode cache
│
├─ data/                               # Local data storage (ignored except .gitkeep)
│   ├─ journals.json                   # Stored journal entries
│   ├─ feedback.json                   # Stored feedback and report inquiries
│   └─ .gitkeep                        # Keeps folder in Git
│
├─ README.md                           # Project overview, setup, and usage instructions
├─ requirements.txt                    # Pinned Python dependencies
└─ .gitignore                          # Files and folders ignored by Git
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

Would you like me to append an optional “Common Issues and Fixes” section (covering things like venv activation errors, pip SSL errors, and port conflicts) at the end, or leave it at this level of completeness?
