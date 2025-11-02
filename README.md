# PeriDocs

Curated, paraphrased discussions and public journal links about neurological well-being.
Early-stage prototype.

---

## Setup

   1. Clone this repository:
    git clone https://github.com/Stays7339/PeriDocs.git


    cd PeriDocs-code

   2. Create a virtual environment:
    python3.11 -m venv venv
    source venv/bin/activate # macOS/Linux
    venv\Scripts\activate # Windows

   3. Install dependencies:
    pip install -r requirements.txt

---

## Project Structure

```text
PeriDocs-code/                  # Root project folder
│
├─ venv/                        # Python virtual environment (ignored by Git)
│   ├─ bin/                     # Executables (python, pip, etc.)
│   ├─ include/                 # Headers for building packages
│   ├─ lib/                     # Installed Python packages
│   ├─ share/                   # Shared resources for the virtual environment
│   └─ pyvenv.cfg               # Virtual environment configuration
│
├─ app/                         # Backend + frontend application code
│   ├─ routes.py                # FastAPI route definitions (main app logic)
│   ├─ nlp.py                   # spaCy wrappers and text processing utilities
│   ├─ templates/               # Jinja2 HTML templates
│   │   ├─ index.html           # Main homepage template
│   │   ├─ about.html           # About page template
│   │   ├─ privacy.html         # Privacy policy page template
│   │   ├─ base.html            # Layout template for all webpages
│   │   ├─ submit-success.html  # Submission success template
│   │   ├─ includes/            # Partial templates (included in other pages)
│   │   │   ├─ modal-feedback.html # Feedback modal HTML
│   ├─ static/                  # Frontend static files
│   │   ├─ cooldown.js          # Handles global cooldown for all submission forms on PeriDocs
│   │   ├─ style.css            # Main stylesheet
│   │   ├─ theme-toggle.js      # Dark Mode toggle
│   │   └─ feedback.js          # Feedback modal JS
│   └─ __pycache__/             # Python compiled bytecode cache
│
├─ data/                        # Local data storage (ignored except .gitkeep)
│   ├─ journals.json            # Stored journal entries
│   ├─ feedback.json            # Stored feedback and software report inquiries
│   └─ .gitkeep                 # Keeps folder in Git
│
├─ README.md                     # Project overview, setup, and usage instructions
├─ requirements.txt              # Pinned Python dependencies
└─ .gitignore                    # Files and folders ignored by Git

```


---
   4. Run the app locally:
    uvicorn app.routes:app --reload

   5. Open your browser:
    http://127.0.0.1:8000/

---
## Notes:

    --reload watches for file changes after saves.
    
    main.py (a short FastAPI test script) has been deleted. routes.py is the primary app now, replacing main.py .

    The background image file remains local and is not committed to GitHub.

    data/journals.json should be ignored by Git and used for local journaling data.
    > The prototype is under active development. Visual and data assets (like the background image and font references) are intentionally undisclosed in this public repo.

    Backend entrypoint: app.routes:app

    Templates: app/templates/

    Static files: app/static/

    Local journal storage: data/journals.json

    Virtual environment: venv/ (excluded from Git)


---

This version uses Markdown’s key syntax features exactly where they matter:

| Symbol | Meaning | Used For |
|---------|----------|-----------|
| `#` | Header | Section titles (“Setup”, “Project Structure”) |
| `##`, `###` | Subheaders | Steps or subsections |
| `---` | Horizontal line | Separates sections cleanly |
| `*` or `_` | Italics or bullets | Emphasis or lists |
| ```` ```bash ... ``` ```` | Code block | Commands you type in terminal |
| `>` | Blockquote | Notes, warnings, or commentary |

---