import os
import re
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

from database import (
    get_connection,
    load_uploaded_csv,
    sanitize_table_name,
    get_schema_string,
    list_tables,
    drop_table,
    is_valid_table_name,
    MAX_UPLOAD_SIZE,
    MAX_RESULT_ROWS,
)
from nl2sql import generate_sql

app = FastAPI()

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class AskRequest(BaseModel):
    table_name: str
    question: str


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
    Accepts a CSV file, saves it to disk, and loads it into a DuckDB table.
    Returns the table name and its inferred schema.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    # Enforce a max upload size by reading in chunks and counting bytes
    table_name = sanitize_table_name(file.filename)
    save_path = os.path.join(UPLOAD_DIR, f"{table_name}.csv")

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
        load_uploaded_csv(conn, save_path, table_name)
        schema = get_schema_string(conn, table_name)
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to load CSV: {e}")
    finally:
        conn.close()

    return {
        "table_name": table_name,
        "schema": schema,
        "row_count": row_count,
    }


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
            sql = generate_sql(request.question, schema)
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail=f"SQL generation failed: {e}")

        if sql.strip().startswith("--"):
            return {
                "question": request.question,
                "sql": sql,
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
