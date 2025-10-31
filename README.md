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

PeriDocs-code/                  # Root project folder
│
├─ venv/                        # Python virtual environment (ignored by Git)
│   ├─ bin/                     # Executables (python, pip, etc.)
│   ├─ include/                 # Headers for building packages
│   ├─ lib/                     # Installed site-packages
│   ├─ share/                   # Shared resources for venv
│   └─ pyvenv.cfg               # venv config
│
├─ app/                         # Backend + frontend code
│   ├─ routes.py                # FastAPI routes; this is the main app now
│   ├─ nlp.py                   # spaCy wrappers & text processing
│   ├─ templates/               # Jinja2 HTML templates
│   │   ├─ index.html
│   │   └─ submit-success.html
│   ├─ static/                  # CSS, JS, images
│   │   └─ style.css
│   └─ __pycache__/             # Compiled Python cache
│
├─ data/                        # Local data storage (ignored by Git except .gitkeep)
│   ├─ journals.json            # Journal entries
│   └─ .gitkeep                 # Keeps folder in Git
│
├─ README.md                     # Project overview, usage, setup
├─ requirements.txt              # Pinned Python packages
└─ .gitignore                    # Ignored files/folders (venv, journals.json, logs, etc.)



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

That version uses Markdown’s key syntax features exactly where they matter:

| Symbol | Meaning | Used For |
|---------|----------|-----------|
| `#` | Header | Section titles (“Setup”, “Project Structure”) |
| `##`, `###` | Subheaders | Steps or subsections |
| `---` | Horizontal line | Separates sections cleanly |
| `*` or `_` | Italics or bullets | Emphasis or lists |
| ```` ```bash ... ``` ```` | Code block | Commands you type in terminal |
| `>` | Blockquote | Notes, warnings, or commentary |

---

If you copy that **as-is** into your `README.md`, GitHub will automatically render it with proper bold headers, boxes around code blocks, and spacing — no extra formatting steps needed.

