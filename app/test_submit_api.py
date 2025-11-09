# app/test_submit_api.py

from fastapi.testclient import TestClient
from .routes import app  # relative import works because we run with -m

def test_submit_endpoint():
    client = TestClient(app)
    response = client.post("/submit", data={"text": "Testing emotional processing."})
    
    print("Status code:", response.status_code)
    print("Response body:", response.text)

if __name__ == "__main__":
    test_submit_endpoint()
