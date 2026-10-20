import os
import pytest
import httpx

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "llm: mark test as requiring LLM integration (/plan/generate)"
    )

BASE_URL = os.getenv("RTAP_API_URL", "http://localhost:8000")

@pytest.fixture(scope="session", autouse=True)
def verify_api_health():
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=30.0)
        if response.status_code != 200:
            pytest.fail(f"API /health returned status {response.status_code}. Ensure API is running in the foreground.")
    except Exception as e:
        pytest.fail(f"API not reachable at {BASE_URL} ({e}). Start it in the foreground.")

@pytest.fixture(scope="session")
def admin1_token():
    email = os.getenv("RTAP_ADMIN_EMAIL", "test-admin@example.com")
    password = os.getenv("RTAP_ADMIN_PW")
    if not password:
        pytest.fail("RTAP_ADMIN_PW not set in environment")
    resp = httpx.post(f"{BASE_URL}/auth/login", json={"username": email, "password": password}, timeout=30.0)
    if resp.status_code != 200:
        pytest.fail(f"Login failed for admin1 (status {resp.status_code}): {resp.text}")
    return resp.json()["access_token"]

@pytest.fixture(scope="session")
def admin2_token():
    email = os.getenv("RTAP_ADMIN2_EMAIL", "admin2@example.com")
    password = os.getenv("RTAP_ADMIN2_PW")
    if not password:
        pytest.fail("RTAP_ADMIN2_PW not set in environment")
    resp = httpx.post(f"{BASE_URL}/auth/login", json={"username": email, "password": password}, timeout=30.0)
    if resp.status_code != 200:
        pytest.fail(f"Login failed for admin2 (status {resp.status_code}): {resp.text}")
    return resp.json()["access_token"]

@pytest.fixture(scope="session")
def admin1_engagement_id(admin1_token):
    resp = httpx.get(f"{BASE_URL}/engagements", headers={"Authorization": f"Bearer {admin1_token}"}, timeout=30.0)
    assert resp.status_code == 200
    engs = resp.json()
    assert isinstance(engs, list) and len(engs) > 0, "Admin1 has no engagements"
    return engs[0]["id"]

@pytest.fixture(scope="session")
def admin2_engagement_id(admin2_token):
    resp = httpx.get(f"{BASE_URL}/engagements", headers={"Authorization": f"Bearer {admin2_token}"}, timeout=30.0)
    assert resp.status_code == 200
    engs = resp.json()
    assert isinstance(engs, list) and len(engs) > 0, "Admin2 has no engagements"
    return engs[0]["id"]
