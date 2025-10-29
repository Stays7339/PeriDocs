#PeriDocs

Curated, paraphrased discussions and public journal links about neurological well-being.
Early-stage prototype.

---

##Setup

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

##Project Structure

PeriDocs-code/
│
├─ venv/ # Python virtual environment
│
├─ app/ # Backend + frontend
│ ├─ routes.py # Streamlined FastAPI routes. This is now the main FastAPI app.
│ ├─ nlp.py # spaCy wrappers & text processing
│ ├─ templates/
│ │ └─ index.html # Current aesthetic HTML
│ └─ static/
│ └─ [undisclosed file] # Compressed background image (local-only)
│
├─ data/ # Local data storage
│ └─ journals.json # Ignored by Git
│
├─ tests/ # Optional: pytest/unittest scripts
│
├─ requirements.txt # Pinned pip packages
├─ .gitignore # Includes venv, journals.json, logs, etc.
└─ README.md


---
   4. Run the app locally:
    uvicorn app.routes:app --reload

   5. Open your browser:
    http://127.0.0.1:8000/

---
##Notes:

    main.py (a short FastAPI test script) has been deleted.

    The background image file remains local and is not committed to GitHub.

    data/journals.json will be ignored by Git and used for local journaling data.
    > The prototype is under active development. Visual and data assets (like the background image and font references) are intentionally undisclosed in this public repo.


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

