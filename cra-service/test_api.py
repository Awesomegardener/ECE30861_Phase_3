import requests

BASE_URL = "http://localhost:8080/api/v1"
HEADERS = {"X-User-Id": "test-engineer"}

def test_reset():
    # AC-10/Test Isolation: Setup clean state by wiping all tables
    res = requests.post(f"{BASE_URL}/test/reset")
    assert res.status_code == 204

def test_ac_01_release_support_status():
    # REQ-01 / AC-01: Inject reference clock to test boundaries
    requests.put(f"{BASE_URL}/test/clock", json={"now": "2026-10-17T12:00:00Z"})
    
    # Supported release (boundary date is in the future)
    r1 = requests.post(f"{BASE_URL}/releases", headers=HEADERS, json={
        "product": "RouterX", "version": "1.0", "support_end_date": "2027-01-01"
    })
    assert r1.status_code == 201
    assert r1.json()["support_status"] == "supported"

    # Unsupported release (boundary date is in the past)
    r2 = requests.post(f"{BASE_URL}/releases", headers=HEADERS, json={
        "product": "RouterX", "version": "0.9", "support_end_date": "2025-01-01"
    })
    assert r2.status_code == 201
    assert r2.json()["support_status"] == "unsupported"

def test_ac_02_sbom_ingestion():
    # REQ-02 / AC-02: Register release and ingest valid CycloneDX
    rel = requests.post(f"{BASE_URL}/releases", headers=HEADERS, json={
        "product": "Gateway", "version": "2.0", "support_end_date": "2028-01-01"
    }).json()
    rel_id = rel["release_id"]

    # Ingest a 1-component CycloneDX payload
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.6",
        "version": 1,
        "components": [
            {"name": "openssl", "version": "3.0.2", "purl": "pkg:generic/openssl@3.0.2"}
        ]
    }
    put_res = requests.put(f"{BASE_URL}/releases/{rel_id}/sbom", headers=HEADERS, json=sbom)
    assert put_res.status_code == 200
    assert put_res.json()["component_count"] == 1

    # Verify component recall
    get_res = requests.get(f"{BASE_URL}/releases/{rel_id}/components")
    assert get_res.status_code == 200
    components = get_res.json()["components"]
    assert len(components) == 1
    assert components[0]["name"] == "openssl"

def test_ac_03_invalid_sbom():
    # REQ-02 / AC-03: Ensure malformed or invalid CycloneDX is rejected
    rel = requests.post(f"{BASE_URL}/releases", headers=HEADERS, json={
        "product": "Firewall", "version": "1.0", "support_end_date": "2028-01-01"
    }).json()
    rel_id = rel["release_id"]

    # Missing bomFormat and components array
    invalid_sbom = {"random_data": True}
    
    put_res = requests.put(f"{BASE_URL}/releases/{rel_id}/sbom", headers=HEADERS, json=invalid_sbom)
    assert put_res.status_code == 400
    assert "error" in put_res.json()