from fastapi import FastAPI, HTTPException, Header, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import uuid
import datetime
import json

app = FastAPI(title="CRA Vulnerability Response Service", version="1.0.0")

@app.exception_handler(StarletteHTTPException)
async def custom_http_exception_handler(request: Request, exc: StarletteHTTPException):
    # If our endpoint already formatted the detail as {"error": ...}, return it directly
    if isinstance(exc.detail, dict) and "error" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    # Fallback for generic server errors
    return JSONResponse(
        status_code=exc.status_code, 
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}}
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    # Forces automatic FastAPI validation errors to match the Phase 2 OpenAPI contract
    return JSONResponse(
        status_code=400,
        content={"error": {"code": "INVALID_REQUEST", "message": "Malformed or invalid request payload"}}
    )


# --- Database Setup ---
DB_URL = os.getenv("DATABASE_URL", "postgresql://cra_user:cra_password@localhost:5432/cra_db")

def get_db_connection():
    return psycopg2.connect(DB_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    # Table for REQ-01: Releases
    cur.execute("""
        CREATE TABLE IF NOT EXISTS releases (
            release_id VARCHAR(64) PRIMARY KEY,
            product VARCHAR(255) NOT NULL,
            version VARCHAR(100) NOT NULL,
            support_end_date DATE NOT NULL,
            UNIQUE(product, version)
        )
    """)
    # Table for REQ-02: Components
    cur.execute("""
        CREATE TABLE IF NOT EXISTS components (
            id SERIAL PRIMARY KEY,
            release_id VARCHAR(64) REFERENCES releases(release_id) ON DELETE CASCADE,
            name VARCHAR(255) NOT NULL,
            version VARCHAR(100) NOT NULL,
            purl TEXT
        )
    """)
    # Table for AC-01/AC-07 Test Clock
    cur.execute("CREATE TABLE IF NOT EXISTS test_clock (id INT PRIMARY KEY, now TIMESTAMP WITH TIME ZONE)")
    conn.commit()
    cur.close()
    conn.close()

init_db()

def get_current_time():
    """Returns test clock time if set, otherwise system UTC time."""
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT now FROM test_clock WHERE id = 1")
    row = cur.fetchone()
    conn.close()
    if row and row['now']:
        return row['now']
    return datetime.datetime.now(datetime.timezone.utc)

# --- Schemas ---
class ReleaseCreate(BaseModel):
    product: str
    version: str
    support_end_date: datetime.date

class ClockUpdate(BaseModel):
    now: datetime.datetime

# --- Endpoints ---

@app.post("/api/v1/releases", status_code=201)
def create_release(release: ReleaseCreate, x_user_id: str = Header(..., alias="X-User-Id")):
    conn = get_db_connection()
    cur = conn.cursor()
    release_id = f"rel-{uuid.uuid4().hex[:8]}"
    
    try:
        cur.execute(
            "INSERT INTO releases (release_id, product, version, support_end_date) VALUES (%s, %s, %s, %s)",
            (release_id, release.product, release.version, release.support_end_date)
        )
        conn.commit()
    except psycopg2.errors.UniqueViolation:
        conn.rollback()
        raise HTTPException(status_code=409, detail={"error": {"code": "CONFLICT", "message": "Release already exists"}})
    finally:
        cur.close()
        conn.close()
        
    return get_release(release_id)

@app.get("/api/v1/releases/{releaseId}")
def get_release(releaseId: str):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM releases WHERE release_id = %s", (releaseId,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        raise HTTPException(status_code=404, detail={"error": {"code": "NOT_FOUND", "message": "Release not found"}})
    
    # Calculate support status based on current time (REQ-01 logic)
    current_date = get_current_time().date()
    status = "supported" if current_date <= row['support_end_date'] else "unsupported"
    
    return {
        "release_id": row['release_id'],
        "product": row['product'],
        "version": row['version'],
        "support_end_date": str(row['support_end_date']),
        "support_status": status
    }

@app.put("/api/v1/releases/{releaseId}/sbom")
async def upload_sbom(releaseId: str, request: Request, x_user_id: str = Header(..., alias="X-User-Id")):
    # Verify release exists
    get_release(releaseId) 
    
    try:
        sbom_data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_JSON", "message": "Malformed JSON payload"}})
        
    if sbom_data.get("bomFormat") != "CycloneDX" or "components" not in sbom_data:
        raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_SBOM", "message": "Not a valid CycloneDX SBOM"}})

    conn = get_db_connection()
    cur = conn.cursor()
    
    # AC-02: Replace existing components for this release
    cur.execute("DELETE FROM components WHERE release_id = %s", (releaseId,))
    
    components = sbom_data["components"]
    for comp in components:
        if "name" not in comp or "version" not in comp:
            conn.rollback()
            raise HTTPException(status_code=400, detail={"error": {"code": "INVALID_COMPONENT", "message": "Component missing name or version"}})
            
        cur.execute(
            "INSERT INTO components (release_id, name, version, purl) VALUES (%s, %s, %s, %s)",
            (releaseId, comp["name"], comp["version"], comp.get("purl"))
        )
        
    conn.commit()
    cur.close()
    conn.close()
    
    return {"release_id": releaseId, "component_count": len(components)}

@app.get("/api/v1/releases/{releaseId}/components")
def get_components(releaseId: str):
    get_release(releaseId) # Verify release exists
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT name, version, purl FROM components WHERE release_id = %s", (releaseId,))
    rows = cur.fetchall()
    conn.close()
    
    return {
        "release_id": releaseId,
        "components": [dict(r) for r in rows]
    }

# --- Test Endpoints (Section 5.3) ---

@app.post("/api/v1/test/reset", status_code=204)
def test_reset():
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("TRUNCATE releases CASCADE")
    cur.execute("DELETE FROM test_clock")
    conn.commit()
    cur.close()
    conn.close()
    return None

@app.put("/api/v1/test/clock")
def test_clock(clock: ClockUpdate):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO test_clock (id, now) VALUES (1, %s) ON CONFLICT (id) DO UPDATE SET now = EXCLUDED.now",
        (clock.now,)
    )
    conn.commit()
    cur.close()
    conn.close()
    return {"now": clock.now}