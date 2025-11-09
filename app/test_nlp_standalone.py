from nlp import document_features
import json

text = "I’m exhausted but hopeful. Everything feels heavy but I’m trying."
features = document_features(text)

print("Raw output:", features)
print("JSON test:", json.dumps(features, indent=2))
