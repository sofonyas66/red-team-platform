import os
import pytest
import httpx

BASE_URL = os.getenv("RTAP_API_URL", "http://localhost:8000")

ENDPOINTS_GET = [
    ("/graph/stats", "get", {}),
    ("/paths", "get", {"source": "a", "target": "b"}),
    ("/gnn/status", "get", {}),
]

ENDPOINTS_PLAN = [
    pytest.param("/plan/generate", "post_plan", {}, marks=pytest.mark.llm, id="plan_generate"),
]

ALL_ENDPOINTS = ENDPOINTS_GET + ENDPOINTS_PLAN

def make_request(method_type, url, token=None, engagement_id=None, base_params=None, timeout=30.0):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    params = dict(base_params) if base_params else {}
    if engagement_id is not None:
        params["engagement_id"] = engagement_id
    
    if method_type == "get":
        return httpx.get(url, headers=headers, params=params, timeout=timeout)
    elif method_type == "post_plan":
        return httpx.post(url, headers=headers, params=params, json={"source": "a", "target": "b"}, timeout=timeout)
    raise ValueError(f"Unknown method_type {method_type}")

def test_me_endpoint(admin1_token):
    resp = httpx.get(f"{BASE_URL}/me", headers={"Authorization": f"Bearer {admin1_token}"}, timeout=30.0)
    assert resp.status_code == 200
    data = resp.json()
    assert set(data.keys()) == {"id", "email", "role", "org_name"}

@pytest.mark.parametrize("endpoint,mtype,base_params", ENDPOINTS_GET)
def test_positive_control_admin1(endpoint, mtype, base_params, admin1_token, admin1_engagement_id):
    url = BASE_URL + endpoint
    resp = make_request(mtype, url, token=admin1_token, engagement_id=admin1_engagement_id, base_params=base_params)
    assert resp.status_code == 200, f"Owner 200 failed for {endpoint}: {resp.text}"

@pytest.mark.parametrize("endpoint,mtype,base_params", ENDPOINTS_GET)
def test_positive_control_admin2(endpoint, mtype, base_params, admin2_token, admin2_engagement_id):
    url = BASE_URL + endpoint
    resp = make_request(mtype, url, token=admin2_token, engagement_id=admin2_engagement_id, base_params=base_params)
    assert resp.status_code == 200, f"Owner 200 failed for admin2 on {endpoint}: {resp.text}"

@pytest.mark.parametrize("endpoint,mtype,base_params", ALL_ENDPOINTS)
def test_no_token_401(endpoint, mtype, base_params, admin1_engagement_id):
    url = BASE_URL + endpoint
    resp = make_request(mtype, url, token=None, engagement_id=admin1_engagement_id, base_params=base_params)
    assert resp.status_code == 401, f"Expected 401 for no token on {endpoint}, got {resp.status_code}"

@pytest.mark.parametrize("endpoint,mtype,base_params", ALL_ENDPOINTS)
def test_cross_tenant_404(endpoint, mtype, base_params, admin2_token, admin1_engagement_id):
    url = BASE_URL + endpoint
    resp = make_request(mtype, url, token=admin2_token, engagement_id=admin1_engagement_id, base_params=base_params)
    assert resp.status_code == 404, f"Expected 404 for cross-tenant access on {endpoint}, got {resp.status_code}"

@pytest.mark.parametrize("endpoint,mtype,base_params", ALL_ENDPOINTS)
def test_missing_id_422(endpoint, mtype, base_params, admin1_token):
    url = BASE_URL + endpoint
    resp = make_request(mtype, url, token=admin1_token, engagement_id=None, base_params=base_params)
    assert resp.status_code == 422, f"Expected 422 for missing engagement_id on {endpoint}, got {resp.status_code}"
    data = resp.json()
    err_str = str(data)
    assert "engagement_id" in err_str, f"Expected engagement_id in validation error detail, got {data}"

@pytest.mark.parametrize("endpoint,mtype,base_params", ALL_ENDPOINTS)
def test_bad_uuid_422(endpoint, mtype, base_params, admin1_token):
    url = BASE_URL + endpoint
    resp = make_request(mtype, url, token=admin1_token, engagement_id="not-a-valid-uuid", base_params=base_params)
    assert resp.status_code == 422, f"Expected 422 for bad UUID on {endpoint}, got {resp.status_code}"
    data = resp.json()
    err_str = str(data)
    assert "engagement_id" in err_str, f"Expected engagement_id in validation error detail, got {data}"

def test_ingest_bloodhound_bad_uuid(admin1_token):
    url = f"{BASE_URL}/ingest/bloodhound"
    dummy_file = ("file", ("dummy.zip", b"PK\x03\x04...", "application/zip"))
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {admin1_token}"},
        data={"engagement_id": "not-a-uuid"},
        files=[dummy_file],
        timeout=30.0
    )
    assert resp.status_code == 422, f"Expected 422 for bad UUID on /ingest/bloodhound, got {resp.status_code}"

def test_ingest_bloodhound_cross_tenant(admin2_token, admin1_engagement_id):
    # Proves owner check (backend/api/main.py:256-261) runs before reading/ingesting the file content
    url = f"{BASE_URL}/ingest/bloodhound"
    dummy_file = ("file", ("dummy.zip", b"PK\x03\x04...", "application/zip"))
    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {admin2_token}"},
        data={"engagement_id": admin1_engagement_id},
        files=[dummy_file],
        timeout=30.0
    )
    assert resp.status_code == 404, f"Expected 404 for cross-tenant ingestion, got {resp.status_code}"
