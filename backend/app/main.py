# TODO: test /upload with invalid/corrupt file formats
# TODO: test /tables with empty database
# TODO: test /ask with malformed or ambiguous questions
# TODO: add try/except around /ask for Groq API timeout/failure



import os
import re
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel
from .nl2sql import generate_sql, explain_sql

from .database import (
    get_connection,
    connect_postgres,
    disconnect_postgres,
    load_uploaded_csv,
    load_uploaded_excel,
    sanitize_table_name,
    get_schema_string,
    list_tables,
    drop_table,
    is_valid_table_name,
    init_feedback_table,
    insert_feedback,
    get_feedback_stats,
    MAX_UPLOAD_SIZE,
    MAX_RESULT_ROWS,
)

from .nl2sql import generate_sql

app = FastAPI()

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

_startup_conn = get_connection()
try:
    init_feedback_table(_startup_conn)
finally:
    _startup_conn.close()


class AskRequest(BaseModel):
    table_name: str
    question: str


class FeedbackRequest(BaseModel):
    question: str
    sql: str
    table_name: str
    rating: str


class ConnectDBRequest(BaseModel):
    pg_url: str


def is_safe_select(sql: str) -> bool:
    """
    Only allow single, read-only SELECT statements through to execution.
    Blocks DROP/DELETE/UPDATE/INSERT/ALTER/ATTACH/COPY/PRAGMA and
    multi-statement injection (semicolon-separated commands).
    """
    stripped = sql.strip().rstrip(";").strip()

    if not re.match(r"(?is)^\s*(with|select)\b", stripped):
        return False

    # Reject if a second statement is smuggled in after a semicolon
    if ";" in stripped:
        return False

    forbidden = r"\b(drop|delete|update|insert|alter|attach|detach|copy|pragma|create|grant|call|export|import)\b"
    if re.search(forbidden, stripped, re.IGNORECASE):
        return False

    return True


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AskSQL backend is running"}


@app.get("/tables")
def get_tables():
    """Lists all currently loaded tables along with their schemas."""
    conn = get_connection()
    try:
        tables = list_tables(conn)
        return {
            "tables": [
                {"table_name": t, "schema": get_schema_string(conn, t)}
                for t in tables
            ]
        }
    finally:
        conn.close()


@app.delete("/tables/{table_name}")
def delete_table(table_name: str):
    """Deletes a table by name."""
    if not is_valid_table_name(table_name):
        raise HTTPException(status_code=400, detail="Invalid table name.")

    conn = get_connection()
    try:
        existing = list_tables(conn)
        if table_name not in existing:
            raise HTTPException(status_code=404, detail=f"Table '{table_name}' not found.")
        drop_table(conn, table_name)
        return {"deleted": table_name}
    finally:
        conn.close()


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Accepts a CSV or Excel (.xlsx/.xls) file, saves it to disk, and loads
    it into a DuckDB table. Returns the table name and its inferred schema.
    """
    filename_lower = file.filename.lower()
    is_csv = filename_lower.endswith(".csv")
    is_excel = filename_lower.endswith(".xlsx") or filename_lower.endswith(".xls")

    if not (is_csv or is_excel):
        raise HTTPException(
            status_code=400,
            detail="Only .csv, .xlsx, and .xls files are supported."
        )

    # Enforce a max upload size by reading in chunks and counting bytes
    table_name = sanitize_table_name(file.filename)
    ext = os.path.splitext(filename_lower)[1]
    save_path = os.path.join(UPLOAD_DIR, f"{table_name}{ext}")

    size = 0
    try:
        with open(save_path, "wb") as f:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE:
                    f.close()
                    os.remove(save_path)
                    raise HTTPException(
                        status_code=413,
                        detail=f"File too large. Max size is {MAX_UPLOAD_SIZE // (1024*1024)} MB."
                    )
                f.write(chunk)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to save file: {e}")

    conn = get_connection()
    try:
        if is_excel:
            load_uploaded_excel(conn, save_path, table_name)
        else:
            load_uploaded_csv(conn, save_path, table_name)
        schema = get_schema_string(conn, table_name)
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
    status_code=400,
    detail=f"Unable to load the uploaded file. Error: {e}"
)
    finally:
        conn.close()

    return {
        "table_name": table_name,
        "schema": schema,
        "row_count": row_count,
    }


@app.post("/connect-db")
async def connect_db(request: ConnectDBRequest):
    """
    Attaches an external Postgres database (e.g. a Neon connection string)
    and exposes its public tables as local views, so /ask and /explain
    work on them exactly like uploaded files.
    """
    if not request.pg_url or not request.pg_url.strip():
        raise HTTPException(status_code=400, detail="Connection string cannot be empty.")

    if not request.pg_url.startswith(("postgresql://", "postgres://")):
        raise HTTPException(status_code=400, detail="Only postgresql:// connection strings are supported.")

    try:
        view_names = connect_postgres(request.pg_url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to connect: {e}")

    if not view_names:
        raise HTTPException(status_code=400, detail="Connected, but no tables found in the 'public' schema.")

    conn = get_connection()
    try:
        return {
            "connected": True,
            "tables": [
                {"table_name": t, "schema": get_schema_string(conn, t)}
                for t in view_names
            ],
        }
    finally:
        conn.close()


@app.post("/disconnect-db")
async def disconnect_db():
    """Forgets the currently connected Postgres database."""
    disconnect_postgres()
    return {"connected": False}


@app.post("/ask")
async def ask_question(request: AskRequest):
    """
    Takes a natural language question about an uploaded table, converts it
    to SQL via Groq, runs it against DuckDB, and returns both the SQL and
    the query results.
    """
    if not is_valid_table_name(request.table_name):
        raise HTTPException(status_code=400, detail="Invalid table name.")

    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    conn = get_connection()
    try:
        existing = list_tables(conn)
        if request.table_name not in existing:
            raise HTTPException(
                status_code=404,
                detail=f"Table '{request.table_name}' not found. Upload it first via /upload."
            )

        schema = get_schema_string(conn, request.table_name)

        try:
            generation_result = generate_sql(request.question, schema)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=f"SQL generation failed: {e}")

        if generation_result["confidence"] == "low":
            return {
                "question": request.question,
                "sql": None,
                "results": [],
                "clarifying_question": generation_result["clarifying_question"],
                "message": "Your question was ambiguous. Please clarify and ask again.",
            }

        sql = generation_result["sql"]

        if not sql:
            return {
                "question": request.question,
                "sql": None,
                "results": [],
                "message": "The question could not be answered with the available data.",
            }

        if not is_safe_select(sql):
            raise HTTPException(
                status_code=400,
                detail=f"Generated query was rejected for safety reasons. SQL was: {sql}"
            )

        try:
            result = conn.execute(f"SELECT * FROM ({sql}) LIMIT {MAX_RESULT_ROWS}")
            columns = [desc[0] for desc in result.description]
            rows = result.fetchall()
            results = [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Generated SQL failed to execute: {e}. SQL was: {sql}"
            )

        return {
            "question": request.question,
            "sql": sql,
            "results": results,
            "truncated": len(results) == MAX_RESULT_ROWS,
        }
    finally:
        conn.close()


@app.post("/explain")
async def explain_question(request: AskRequest):
    """
    Takes a natural language question, converts it to SQL via Groq,
    but instead of executing it, runs DuckDB's EXPLAIN and asks Groq
    to comment on whether the query plan looks efficient.
    """
    if not is_valid_table_name(request.table_name):
        raise HTTPException(status_code=400, detail="Invalid table name.")

    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    conn = get_connection()
    try:
        existing = list_tables(conn)
        if request.table_name not in existing:
            raise HTTPException(
                status_code=404,
                detail=f"Table '{request.table_name}' not found. Upload it first via /upload."
            )

        schema = get_schema_string(conn, request.table_name)

        try:
            generation_result = generate_sql(request.question, schema)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=f"SQL generation failed: {e}")

        if generation_result["confidence"] == "low":
            return {
                "question": request.question,
                "sql": None,
                "plan": None,
                "commentary": None,
                "clarifying_question": generation_result["clarifying_question"],
                "message": "Your question was ambiguous. Please clarify and ask again.",
            }

        sql = generation_result["sql"]

        if not sql:
            return {
                "question": request.question,
                "sql": None,
                "plan": None,
                "commentary": None,
                "message": "The question could not be answered with the available data.",
            }

        if not is_safe_select(sql):
            raise HTTPException(
                status_code=400,
                detail=f"Generated query was rejected for safety reasons. SQL was: {sql}"
            )

        try:
            plan_result = conn.execute(f"EXPLAIN {sql}").fetchall()
            plan_text = "\n".join(row[-1] for row in plan_result)
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to generate query plan: {e}. SQL was: {sql}"
            )

        try:
            commentary = explain_sql(sql, plan_text)
        except RuntimeError as e:
            commentary = f"(Commentary unavailable: {e})"

        return {
            "question": request.question,
            "sql": sql,
            "plan": plan_text,
            "commentary": commentary,
        }
    finally:
        conn.close()


@app.post("/feedback")
async def submit_feedback(request: FeedbackRequest):
    """
    Records a thumbs up/down rating for a previously generated SQL query.
    """
    if request.rating not in ("up", "down"):
        raise HTTPException(status_code=400, detail="Rating must be 'up' or 'down'.")

    if not request.question or not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if not request.sql or not request.sql.strip():
        raise HTTPException(status_code=400, detail="SQL cannot be empty.")

    conn = get_connection()
    try:
        insert_feedback(conn, request.question, request.sql, request.table_name, request.rating)
        return {"status": "recorded", "rating": request.rating}
    finally:
        conn.close()


@app.get("/feedback/stats")
def feedback_stats():
    """Returns aggregate up/down counts for all recorded feedback."""
    conn = get_connection()
    try:
        return get_feedback_stats(conn)
    finally:
        conn.close()