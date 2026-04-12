import logging
import re
import time
import hashlib
from collections import defaultdict
from typing import Any

import sqlite3
import plotly.express as px
import pandas as pd
import json

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, field_validator

from vanna_setup import agent, agent_memory
import os
from datetime import datetime, timedelta

DB_PATH = os.getenv("DB_PATH", "clinic.db")

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("clinic-api")

def _log_cache_event(action: str, cache_hit: bool = None, cache_size: int = None, question_preview: str = None):
    """Log cache-related events."""
    msg = f"Cache {action}"
    if cache_hit is not None:
        msg += f" | hit={cache_hit}"
    if cache_size is not None:
        msg += f" | size={cache_size}"
    if question_preview:
        msg += f" | q='{question_preview[:50]}...'"
    logger.info(msg)

def _log_rate_limit_event(client_ip: str, requests_in_window: int, limit: int):
    """Log rate limiting events."""
    logger.info(f"Rate limit check | ip={client_ip} | requests={requests_in_window}/{limit}")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Clinic NL-to-SQL API",
    description="Natural language queries over the clinic database powered by Groq",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Cache ─────────────────────────────────────────────────────────────────────
_cache: dict[str, dict] = {}
CACHE_TTL_SECONDS = 3600  # 1 hour cache expiration

# ── Rate Limiter ──────────────────────────────────────────────────────────────
_rate_store: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT = 20
RATE_WINDOW = 60.0

@app.on_event("startup")
async def startup_event():
    """Log application startup."""
    logger.info("🚀 Application startup | version=2.0.0 | features=[cache, rate-limit, logging]")
    logger.info(f"Configuration | cache_ttl={CACHE_TTL_SECONDS}s | rate_limit={RATE_LIMIT}/60s")

@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown."""
    logger.info(f"Application shutdown | cache_size={len(_cache)} | rate_store_size={len(_rate_store)}")

# ── Frontend ──────────────────────────────────────────────────────────────────────
@app.get("/")
async def serve_frontend():
    """Serve the frontend HTML."""
    frontend_path = os.path.join(os.path.dirname(__file__), "index.html")
    if os.path.exists(frontend_path):
        logger.info("Frontend requested | serving index.html")
        return FileResponse(frontend_path, media_type="text/html")
    return JSONResponse({"error": "Frontend not found"}, status_code=404)

def _cache_key(question: str) -> str:
    return hashlib.md5(question.strip().lower().encode()).hexdigest()

def _get_cached_result(question: str) -> dict | None:
    """Retrieve cached result if it exists and hasn't expired."""
    ck = _cache_key(question)
    if ck not in _cache:
        _log_cache_event("miss", cache_size=len(_cache), question_preview=question)
        return None
    
    cached_entry = _cache[ck]
    expiration = cached_entry.get("_expires_at")
    
    if expiration and datetime.utcnow() > datetime.fromisoformat(expiration):
        logger.info(f"Cache expired | key={ck[:8]}...")
        del _cache[ck]
        return None
    
    _log_cache_event("hit", cache_size=len(_cache), question_preview=question)
    return cached_entry.get("response")

def _store_cached_result(question: str, response: dict):
    """Store a result in cache with expiration timestamp."""
    ck = _cache_key(question)
    expires_at = (datetime.utcnow() + timedelta(seconds=CACHE_TTL_SECONDS)).isoformat()
    _cache[ck] = {
        "response": response,
        "_expires_at": expires_at,
        "_cached_at": datetime.utcnow().isoformat(),
    }
    logger.info(f"Cache store | key={ck[:8]}... | ttl={CACHE_TTL_SECONDS}s | size={len(_cache)}")

def _check_rate_limit(client_ip: str):
    """Check rate limit for an IP address. Raises HTTPException if exceeded."""
    now = time.time()
    timestamps = _rate_store[client_ip]
    
    # Clean up old timestamps outside the window
    _rate_store[client_ip] = [t for t in timestamps if now - t < RATE_WINDOW]
    
    requests_in_window = len(_rate_store[client_ip])
    _log_rate_limit_event(client_ip, requests_in_window, RATE_LIMIT)

    if requests_in_window >= RATE_LIMIT:
        logger.warning(
            f"Rate limit EXCEEDED | ip={client_ip} | requests={requests_in_window}/{RATE_LIMIT} | status=429"
        )
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded. Max {RATE_LIMIT} requests per {int(RATE_WINDOW)}s.",
        )

    # Record this request
    _rate_store[client_ip].append(now)
    logger.debug(f"Rate limit OK | ip={client_ip} | requests={requests_in_window + 1}/{RATE_LIMIT}")

# ── SQL Validation ────────────────────────────────────────────────────────────
_FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|EXEC|EXECUTE|xp_|sp_|GRANT|REVOKE|SHUTDOWN|TRUNCATE|CREATE|REPLACE|MERGE)\b",
    re.IGNORECASE,
)

_SYSTEM_TABLES = re.compile(
    r"\b(sqlite_master|sqlite_temp_master|sqlite_sequence|information_schema|sys\.)\b",
    re.IGNORECASE,
)

def validate_sql(sql: str) -> tuple[bool, str]:
    stripped = sql.strip().upper()

    if not stripped.startswith("SELECT"):
        return False, "Only SELECT queries are allowed. This interface is read-only for data retrieval only."

    if _FORBIDDEN_KEYWORDS.search(sql):
        match = _FORBIDDEN_KEYWORDS.search(sql)
        keyword = match.group()
        error_msgs = {
            "INSERT": "Cannot insert new records. This interface is read-only.",
            "UPDATE": "Cannot update records. This interface is read-only.",
            "DELETE": "Cannot delete records. This interface is read-only.",
            "GRANT": "Cannot perform permission changes. This interface is read-only.",
            "REVOKE": "Cannot revoke permissions. This interface is read-only.",
            "DROP": "Cannot drop tables or objects. This interface is read-only.",
            "ALTER": "Cannot alter table structure. This interface is read-only.",
            "CREATE": "Cannot create new objects. This interface is read-only.",
            "TRUNCATE": "Cannot truncate tables. This interface is read-only.",
            "EXEC": "Cannot execute procedures. This interface is read-only.",
            "EXECUTE": "Cannot execute procedures. This interface is read-only.",
            "SHUTDOWN": "Cannot shutdown the database.",
            "MERGE": "Cannot merge data. This interface is read-only.",
            "REPLACE": "Cannot replace records. This interface is read-only.",
        }
        user_msg = error_msgs.get(keyword, f"Keyword '{keyword}' is not allowed.")
        return False, f"{user_msg} Try asking a question about retrieving data instead."

    if _SYSTEM_TABLES.search(sql):
        return False, "Access to system tables is restricted. Try querying user data tables instead."

    return True, ""

# ── SQL Execution ─────────────────────────────────────────────────────────────
def run_sql(sql: str) -> tuple[list[str], list[list], int]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(sql)
    rows_raw = cur.fetchall()
    conn.close()

    if not rows_raw:
        return [], [], 0

    columns = list(rows_raw[0].keys())

    # ✅ FIX: convert numpy / sqlite types safely
    def safe(v):
        return v.item() if hasattr(v, "item") else v

    rows = [list(map(safe, r)) for r in rows_raw]

    return columns, rows, len(rows)

# ── Chart Generation ──────────────────────────────────────────────────────────
def _try_generate_chart(columns: list[str], rows: list[list]) -> tuple[dict | None, str | None]:
    if len(rows) == 0 or len(columns) < 2:
        return None, None

    try:
        df = pd.DataFrame(rows, columns=columns)

        numeric_cols = df.select_dtypes(include="number").columns.tolist()
        text_cols = [c for c in columns if c not in numeric_cols]

        if not numeric_cols:
            return None, None

        x_col = text_cols[0] if text_cols else columns[0]
        y_col = numeric_cols[0]

        if len(df) <= 15 and text_cols:
            fig = px.bar(df, x=x_col, y=y_col, title=f"{y_col} by {x_col}")
            chart_type = "bar"
        elif len(df) > 15:
            fig = px.line(df, x=x_col, y=y_col, title=f"{y_col} trend")
            chart_type = "line"
        else:
            fig = px.bar(df, x=x_col, y=y_col)
            chart_type = "bar"

        # ✅ FIX: JSON safe
        return json.loads(fig.to_json()), chart_type

    except Exception as e:
        logger.warning("Chart generation failed: %s", e)
        return None, None

# ── Models ────────────────────────────────────────────────────────────────────
class ChatRequest(BaseModel):
    question: str

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()

        if not v:
            raise ValueError("Question cannot be empty.")
        if len(v) > 500:
            raise ValueError("Question too long (max 500 characters).")

        # Check for SQL injection / dangerous patterns
        forbidden = re.compile(
            r"\b(DROP|DELETE|INSERT|UPDATE|ALTER|TRUNCATE|EXEC|EXECUTE|GRANT|REVOKE|SHUTDOWN|CREATE|REPLACE|MERGE|xp_|sp_|--|;|sqlite_master|sqlite_sequence|information_schema)\b",
            re.IGNORECASE
        )
        if forbidden.search(v):
            match = forbidden.search(v)
            raise ValueError(f"Unsafe keyword detected: '{match.group()}'. This interface is read-only for data retrieval only.")

        if not re.match(r"^[a-zA-Z0-9\s?,.%()'_-]+$", v):
            raise ValueError("Invalid characters in question.")

        return v

class ChatResponse(BaseModel):
    message: str
    sql_query: str | None = None
    columns: list[str] = []
    rows: list[list[Any]] = []
    row_count: int = 0
    chart: dict | None = None
    chart_type: str | None = None
    cached: bool = False

# ── Routes ────────────────────────────────────────────────────────────────────
from vanna.core.user import RequestContext

@app.get("/health")
async def health(request: Request):
    logger.info("Health check requested")

    # DB check
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("SELECT 1")
        conn.close()
        db_status = "connected"
        logger.debug("Database health check passed")
    except Exception as e:
        db_status = "error"
        logger.error(f"Database health check failed: {e}")

    # Memory check - retrieve memory count from DemoAgentMemory
    # Memory check - retrieve memory count from DemoAgentMemory
    memory_count = 0
    try:
        if agent_memory is None:
            logger.warning("Agent memory is None")
        else:
            count = 0

            # Accumulate across both stores — save_text_memory writes to _text_memories,
            # while question/SQL pairs land in _memories. Count both.
            if hasattr(agent_memory, '_memories') and isinstance(agent_memory._memories, (list, dict)):
                count += len(agent_memory._memories)

            if hasattr(agent_memory, '_text_memories') and isinstance(agent_memory._text_memories, (list, dict)):
                count += len(agent_memory._text_memories)

            memory_count = count
            logger.info(f"Agent memory count | total={memory_count} | type={type(agent_memory).__name__}")

    except Exception as e:
        logger.error(f"Memory check failed | type={type(e).__name__} | msg={str(e)}")
        memory_count = 0

    logger.info(f"Health check complete | db={db_status} | memory={memory_count}")

    return {
        "status": "ok",
        "database": db_status,
        "agent_memory_items": memory_count,
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    start_time = time.time()
    client_ip = request.client.host
    
    # 1. Rate limit check
    logger.info(f"Request started | ip={client_ip}, question_len={len(body.question)}")
    _check_rate_limit(client_ip)

    question = body.question
    logger.info(f"Chat request | ip={client_ip} | q='{question[:60]}...'")

    # 2. Cache check
    cached_result = _get_cached_result(question)
    if cached_result:
        elapsed = time.time() - start_time
        logger.info(f"Returning cached response | elapsed={elapsed:.3f}s")
        cached_response = dict(cached_result)
        cached_response["cached"] = True
        return ChatResponse(**cached_response)

    # 3. LLM call
    llm_start = time.time()
    try:
        sql = await agent.llm_service.generate(question)
        sql = sql.replace("```sql", "").replace("```", "").strip()
        llm_elapsed = time.time() - llm_start
        logger.info(f"LLM generated SQL | elapsed={llm_elapsed:.3f}s | sql_len={len(sql)}")
    except Exception as e:
        logger.error(f"LLM error | type={type(e).__name__} | msg={str(e)}")
        return ChatResponse(message=f"LLM error: {str(e)}")

    if not sql:
        logger.warning("LLM returned empty SQL")
        return ChatResponse(message="Could not generate SQL.")

    logger.debug(f"Generated SQL: {sql[:100]}...")

    # 4. Validation
    valid, err = validate_sql(sql)
    if not valid:
        logger.warning(f"SQL validation failed | keyword_blocked=true | reason={err} | sql={sql[:80]}...")
        return ChatResponse(
            message=f"❌ {err}",
            sql_query=sql,
        )
    logger.debug("SQL validation passed")

    # 5. Execution
    exec_start = time.time()
    try:
        columns, rows, row_count = run_sql(sql)
        exec_elapsed = time.time() - exec_start
        logger.info(f"SQL executed | elapsed={exec_elapsed:.3f}s | rows={row_count}")
    except Exception as e:
        logger.error(f"Database error | type={type(e).__name__} | msg={str(e)}")
        return ChatResponse(
            message=f"Database error: {str(e)}",
            sql_query=sql,
        )

    if row_count == 0:
        logger.info("Query returned no results")
        resp = ChatResponse(
            message="No data found.",
            sql_query=sql,
            columns=columns,
            rows=[],
            row_count=0,
        )
        
        # Store in memory even for empty results (learning opportunity)
        try:
            if agent_memory:
                logger.info("🔴 Starting memory storage for empty result...")
                ctx = RequestContext(user_id=client_ip)
                memory_message = f"Q: {question}\nA: {sql}\n--- Result: No rows found ---"
                logger.info(f"🔴 About to call save_text_memory() for empty result...")
                await agent_memory.save_text_memory(
                    memory_message,
                    ctx
                )
                logger.info(f"Memory stored (empty result) | question_len={len(question)}")
            else:
                logger.warning("🔴 agent_memory is None!")
        except Exception as e:
            logger.warning(f"🔴 Failed to store empty result memory | type={type(e).__name__} | msg={str(e)}")
            import traceback
            logger.warning(f"🔴 Traceback: {traceback.format_exc()}")
        
        _store_cached_result(question, resp.model_dump())
        return resp

    # 6. Chart generation
    chart_start = time.time()
    chart, chart_type = _try_generate_chart(columns, rows)
    chart_elapsed = time.time() - chart_start
    if chart:
        logger.info(f"Chart generated | type={chart_type} | elapsed={chart_elapsed:.3f}s")
    else:
        logger.debug(f"Chart generation skipped or failed | elapsed={chart_elapsed:.3f}s")

    resp = ChatResponse(
        message=f"Found {row_count} record(s).",
        sql_query=sql,
        columns=columns,
        rows=rows,
        row_count=row_count,
        chart=chart,
        chart_type=chart_type,
    )

    # 7. Store in agent memory for learning
    try:
        if agent_memory:
            logger.info("🔴 Starting memory storage...")
            ctx = RequestContext(user_id=client_ip)
            logger.info(f"🔴 Created context for user: {client_ip}")
            logger.info(f"🔴 Memory state BEFORE: _memories={len(agent_memory._memories)}, _text_memories={len(agent_memory._text_memories)}")
            
            # Create a learning message: "Q: ... | A: ..."
            memory_message = f"Q: {question}\nA: {sql}\n--- Result: {row_count} rows found ---"
            logger.info(f"🔴 Memory message created: {memory_message[:100]}...")
            
            # Store in agent memory
            logger.info(f"🔴 About to call save_text_memory()...")
            result = await agent_memory.save_text_memory(
                memory_message,
                ctx
            )
            logger.info(f"🔴 save_text_memory() returned: {result}")
            logger.info(f"🔴 Memory state AFTER: _memories={len(agent_memory._memories)}, _text_memories={len(agent_memory._text_memories)}")
            logger.info(f"Memory stored | question_len={len(question)} | sql_len={len(sql)} | rows={row_count}")
        else:
            logger.warning("🔴 agent_memory is None!")
    except Exception as e:
        logger.error(f"🔴 Failed to store memory | type={type(e).__name__} | msg={str(e)}")
        import traceback
        logger.error(f"🔴 Traceback: {traceback.format_exc()}")

    _store_cached_result(question, resp.model_dump())
    
    total_elapsed = time.time() - start_time
    logger.info(f"Request completed | status=200 | elapsed={total_elapsed:.3f}s | ip={client_ip}")
    
    return resp

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Handle FastAPI validation errors gracefully."""
    client_ip = request.client.host
    errors = exc.errors()
    
    # Extract the first validation error message
    error_msg = "Invalid input"
    if errors:
        err = errors[0]
        error_msg = err.get("msg", "Validation error")
        logger.warning(
            f"Validation error | ip={client_ip} | field={err.get('loc')} | msg={error_msg}"
        )
    
    return JSONResponse(
        status_code=422,
        content={"detail": error_msg},
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    client_ip = request.client.host
    logger.exception(
        f"Unhandled exception | ip={client_ip} | type={type(exc).__name__} | msg={str(exc)}"
    )
    return JSONResponse(
        status_code=500,
        content={"detail": "Server error"},
    )
