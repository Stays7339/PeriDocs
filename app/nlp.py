import spacy

nlp = spacy.load("en_core_web_sm")

def analyze_text(text: str):
    doc = nlp(text)
    return {
        "tokens": [token.text for token in doc],
        "entities": [(ent.text, ent.label_) for ent in doc.ents]
    }
