import base64
import gzip
import json
import os
import re
import time
from typing import Any, Optional

import pymysql
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pymysql.cursors import DictCursor


VALID_SERVICES = {"landom", "attune", "sian", "soom", "moyo"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class LeadCreate(BaseModel):
    service: str
    email: str
    language: str = "ko"
    ctaId: Optional[str] = None
    pagePath: Optional[str] = None
    sourceUrl: Optional[str] = None


class SdkEvent(BaseModel):
    type: str
    timestamp: Optional[int] = None
    cssSelector: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SdkEventBatch(BaseModel):
    sessionId: str
    userAgent: Optional[str] = None
    url: Optional[str] = None
    apiKey: Optional[str] = None
    events: list[SdkEvent] = Field(default_factory=list)


def mysql_config() -> dict:
    return {
        "host": os.getenv("MYSQL_HOST", "mysql"),
        "port": int(os.getenv("MYSQL_PORT", "3306")),
        "user": os.getenv("MYSQL_USER", "landing"),
        "password": os.getenv("MYSQL_PASSWORD", "landing_password"),
        "database": os.getenv("MYSQL_DATABASE", "landing_pages"),
        "charset": "utf8mb4",
        "autocommit": True,
        "cursorclass": DictCursor,
    }


def connect():
    return pymysql.connect(**mysql_config())


def init_db() -> None:
    ddl_statements = [
        """
    CREATE TABLE IF NOT EXISTS lead_signups (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        service VARCHAR(32) NOT NULL,
        email VARCHAR(255) NOT NULL,
        language VARCHAR(16) NOT NULL DEFAULT 'ko',
        cta_id VARCHAR(64) NULL,
        page_path VARCHAR(255) NULL,
        source_url VARCHAR(2048) NULL,
        user_agent VARCHAR(512) NULL,
        ip_address VARCHAR(45) NULL,
        created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_service_created_at (service, created_at),
        INDEX idx_email (email)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
        """
    CREATE TABLE IF NOT EXISTS sdk_sessions (
        session_id VARCHAR(96) NOT NULL PRIMARY KEY,
        service VARCHAR(32) NOT NULL,
        first_url VARCHAR(2048) NULL,
        user_agent VARCHAR(512) NULL,
        first_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        last_seen_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
        INDEX idx_service_last_seen_at (service, last_seen_at)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
        """
    CREATE TABLE IF NOT EXISTS sdk_events (
        id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
        service VARCHAR(32) NOT NULL,
        session_id VARCHAR(96) NOT NULL,
        event_type VARCHAR(64) NOT NULL,
        event_timestamp BIGINT NULL,
        css_selector TEXT NULL,
        payload_json LONGTEXT NULL,
        page_url VARCHAR(2048) NULL,
        user_agent VARCHAR(512) NULL,
        received_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
        INDEX idx_service_received_at (service, received_at),
        INDEX idx_session_id (session_id),
        INDEX idx_event_type (event_type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """,
    ]

    last_error = None
    for _ in range(30):
        try:
            with connect() as conn:
                with conn.cursor() as cursor:
                    for ddl in ddl_statements:
                        cursor.execute(ddl)
            return
        except Exception as exc:  # MySQL may still be accepting connections.
            last_error = exc
            time.sleep(1)

    raise RuntimeError(f"Could not initialize MySQL: {last_error}")


app = FastAPI(title="Landing Lead API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup() -> None:
    init_db()


def normalized_service(service: str) -> str:
    value = service.strip().lower()
    if value not in VALID_SERVICES:
        raise HTTPException(status_code=400, detail="Unknown service.")
    return value


def normalized_email(email: str) -> str:
    value = email.strip().lower()
    if not EMAIL_RE.match(value) or len(value) > 255:
        raise HTTPException(status_code=400, detail="올바른 이메일 주소를 입력해 주세요.")
    return value


def client_ip(request: Request) -> Optional[str]:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    if request.client:
        return request.client.host[:45]
    return None


def sdk_project_keys() -> dict[str, str]:
    keys = {
        os.getenv("LANDOM_SDK_API_KEY"): "landom",
        os.getenv("ATTUNE_SDK_API_KEY"): "attune",
        os.getenv("SIAN_SDK_API_KEY"): "sian",
        os.getenv("SOOM_SDK_API_KEY"): "soom",
        os.getenv("MOYO_SDK_API_KEY"): "moyo",
    }
    return {api_key: service for api_key, service in keys.items() if api_key}


def sdk_payload_json(event: SdkEvent) -> str:
    payload = event.payload or {}
    if (
        event.type == "replay"
        and payload.get("compressed") is True
        and payload.get("compression") == "gzip"
        and payload.get("encoding") == "base64"
        and isinstance(payload.get("data"), str)
    ):
        try:
            raw = gzip.decompress(base64.b64decode(payload["data"])).decode("utf-8")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                data = raw
            payload = {**payload, "compressed": False, "data": data, "serverDecoded": True}
        except Exception as exc:
            payload = {**payload, "serverDecodeError": str(exc)[:200]}

    return json.dumps(payload, ensure_ascii=False)


@app.get("/api/healthz")
def healthz() -> dict:
    with connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT 1 AS ok")
            cursor.fetchone()
    return {"ok": True}


@app.post("/api/leads", status_code=201)
def create_lead(payload: LeadCreate, request: Request) -> dict:
    service = normalized_service(payload.service)
    email = normalized_email(payload.email)
    language = (payload.language or "ko").strip().lower()[:16]
    cta_id = (payload.ctaId or "final").strip()[:64]
    page_path = (payload.pagePath or "").strip()[:255] or None
    source_url = (payload.sourceUrl or "").strip()[:2048] or None
    user_agent = (request.headers.get("user-agent") or "").strip()[:512] or None

    sql = """
    INSERT INTO lead_signups
        (service, email, language, cta_id, page_path, source_url, user_agent, ip_address)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    values = (service, email, language, cta_id, page_path, source_url, user_agent, client_ip(request))

    with connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, values)
            lead_id = cursor.lastrowid

    return {"ok": True, "id": lead_id}


@app.post("/api/v1/events", status_code=202)
def ingest_sdk_events(
    payload: SdkEventBatch,
    request: Request,
    x_project_key: Optional[str] = Header(default=None),
) -> dict:
    project_key = (x_project_key or payload.apiKey or "").strip()
    service = sdk_project_keys().get(project_key)
    if not service:
        raise HTTPException(status_code=401, detail="Invalid project key.")

    session_id = payload.sessionId.strip()[:96]
    if not session_id:
        raise HTTPException(status_code=400, detail="sessionId required.")

    if not payload.events:
        return {"ok": True, "accepted": 0}

    user_agent = (payload.userAgent or request.headers.get("user-agent") or "").strip()[:512] or None
    page_url = (payload.url or "").strip()[:2048] or None

    session_sql = """
    INSERT INTO sdk_sessions (session_id, service, first_url, user_agent)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        service = VALUES(service),
        user_agent = VALUES(user_agent),
        last_seen_at = CURRENT_TIMESTAMP
    """
    event_sql = """
    INSERT INTO sdk_events
        (service, session_id, event_type, event_timestamp, css_selector, payload_json, page_url, user_agent)
    VALUES
        (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    rows = [
        (
            service,
            session_id,
            event.type.strip()[:64],
            event.timestamp,
            (event.cssSelector or "").strip() or None,
            sdk_payload_json(event),
            page_url,
            user_agent,
        )
        for event in payload.events
        if event.type.strip()
    ]

    if not rows:
        return {"ok": True, "accepted": 0}

    with connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(session_sql, (session_id, service, page_url, user_agent))
            cursor.executemany(event_sql, rows)

    return {"ok": True, "accepted": len(rows)}


@app.get("/api/leads")
def list_leads(
    x_admin_token: Optional[str] = Header(default=None),
    service: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> dict:
    expected_token = os.getenv("LEADS_ADMIN_TOKEN")
    if not expected_token or x_admin_token != expected_token:
        raise HTTPException(status_code=401, detail="Admin token required.")

    params = []
    where = ""
    if service:
        where = "WHERE service = %s"
        params.append(normalized_service(service))

    params.append(limit)
    sql = f"""
    SELECT id, service, email, language, cta_id, page_path, source_url, created_at
    FROM lead_signups
    {where}
    ORDER BY created_at DESC, id DESC
    LIMIT %s
    """

    with connect() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, params)
            rows = cursor.fetchall()

    return {"ok": True, "leads": rows}
