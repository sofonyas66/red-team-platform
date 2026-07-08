import json
import sys
from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)

print("============================================================")
print("1. GET /health response")
print("============================================================")
response = client.get("/health")
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2))
print()

print("============================================================")
print("2. GET /graph/stats response")
print("============================================================")
response = client.get("/graph/stats")
print(f"Status Code: {response.status_code}")
print(json.dumps(response.json(), indent=2))
print()

print("============================================================")
print("3. POST /plan/generate response")
print("============================================================")
payload = {
    "source": "STANNIS.BARATHEON@SEVENKINGDOMS.LOCAL",
    "target": "KINGSLANDING.SEVENKINGDOMS.LOCAL"
}
print(f"Sending payload: {json.dumps(payload, indent=2)}")
response = client.post("/plan/generate", json=payload)
print(f"Status Code: {response.status_code}")
if response.status_code == 200:
    print(json.dumps(response.json(), indent=2))
else:
    print(f"Error Detail: {response.text}")
print("============================================================")
