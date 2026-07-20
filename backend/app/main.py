import os
import shutil

from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel

from database import get_connection, load_uploaded_csv, sanitize_table_name, get_schema_string
from nl2sql import generate_sql

app = FastAPI()

UPLOAD_DIR = "data/uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)


class AskRequest(BaseModel):
    table_name: str
    question: str


@app.get("/health")
def health_check():
    return {"status": "ok", "message": "AskSQL backend is running"}


@app.post("/upload")
async def upload_csv(file: UploadFile = File(...)):
    """
    Accepts a CSV file, saves it to disk, and loads it into a DuckDB table.
    Returns the table name and its inferred schema.
    """
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only .csv files are supported.")

    table_name = sanitize_table_name(file.filename)
    save_path = os.path.join(UPLOAD_DIR, f"{table_name}.csv")

    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    conn = get_connection()
    try:
        load_uploaded_csv(conn, save_path, table_name)
        schema = get_schema_string(conn, table_name)
        row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
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
    conn = get_connection()
    try:
        # Confirm the table actually exists before doing anything else
        existing = conn.execute("""
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
        """, [request.table_name]).fetchone()

        if not existing:
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

        try:
            result = conn.execute(sql)
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
        }
    finally:
        conn.close()
