"""
nl2sql.py
Converts natural language questions into DuckDB-compatible SQL using the Groq API.
"""

import os
import re
import json
from dotenv import load_dotenv
from groq import Groq


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------

load_dotenv()  # reads backend/.env and loads GROQ_API_KEY into the environment

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError(
        "GROQ_API_KEY is not set. Add it to your environment or .env file."
    )

client = Groq(api_key=GROQ_API_KEY)

MODEL_NAME = "llama-3.3-70b-versatile"


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert SQL generator for DuckDB.

You must respond with ONLY a single valid JSON object. No markdown fences, no explanations outside the JSON.

The JSON must have exactly these fields:
- "confidence": either "high" or "low"
- "sql": the SQL query as a string (use DuckDB syntax, no trailing semicolon), or null if confidence is "low"
- "clarifying_question": a short question to ask the user if confidence is "low", or null if confidence is "high"

Rules:
1. Only use tables and columns provided in the schema below. Never invent column or table names.
2. Set confidence to "low" ONLY if the question is genuinely ambiguous — e.g. it references a vague term
   like "top performers", "best", "recent" without specifying what field or time range to use, AND the
   schema does not make the meaning obvious. Do NOT mark simple, clear questions as low confidence.
3. If confidence is "low", write ONE short clarifying question in plain English, and set "sql" to null.
4. If the question cannot be answered with the given schema at all, set "confidence" to "high",
   set "sql" to null, and set "clarifying_question" to null. (This case will be handled separately.)
5. Prefer explicit column names over SELECT * unless the user clearly wants all columns.

Schema:
{schema}

Example response for a clear question:
{{"confidence": "high", "sql": "SELECT region, SUM(amount) FROM sales GROUP BY region", "clarifying_question": null}}

Example response for an ambiguous question:
{{"confidence": "low", "sql": null, "clarifying_question": "When you say 'top performers', do you mean by sales amount, or by number of orders?"}}
"""
def build_prompt(question: str, schema: str) -> list[dict]:
    """Builds the Groq chat messages payload for a given question + schema."""
    return [
        {"role": "system", "content": SYSTEM_PROMPT.format(schema=schema)},
        {"role": "user", "content": question},
    ]


# ---------------------------------------------------------------------------
# Response cleaning
# ---------------------------------------------------------------------------

def clean_json_response(raw: str) -> dict:
    """Strips markdown fences and parses the model's JSON response."""
    text = raw.strip()

    # Remove ```json ... ``` or ``` ... ``` fences if present
    fence_match = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Model did not return valid JSON: {e}\nRaw output: {raw}") from e

    # Basic shape validation with safe defaults
    confidence = data.get("confidence", "high")
    sql = data.get("sql")
    clarifying_question = data.get("clarifying_question")

    if sql:
        sql = sql.rstrip(";").strip()

    return {
        "confidence": confidence,
        "sql": sql,
        "clarifying_question": clarifying_question,
    }

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_sql(question: str, schema: str, temperature: float = 0.1) -> dict:
    """
    Converts a natural language question into a SQL query.

    Args:
        question: The user's natural language question.
        schema: A string describing table(s) and column(s).
        temperature: Lower = more deterministic SQL. Default 0.1 for consistency.

    Returns:
        A dict with keys:
            "confidence": "high" or "low"
            "sql": the SQL string, or None if confidence is "low" or unanswerable
            "clarifying_question": a string if confidence is "low", else None

    Raises:
        RuntimeError: if the Groq API call fails or returns invalid JSON.
    """
    messages = build_prompt(question, schema)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
            max_tokens=512,
            response_format={"type": "json_object"},
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed: {e}") from e

    raw_output = response.choices[0].message.content
    return clean_json_response(raw_output)


# ---------------------------------------------------------------------------
# Quick manual test (run: python app/nl2sql.py)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_schema = """
    TABLE sales(
        id INTEGER,
        region TEXT,
        product TEXT,
        amount FLOAT,
        sale_date DATE
    )
    """

    print("--- Clear question ---")
    result1 = generate_sql("What is the total sales amount by region for the year 2025?", test_schema)
    print(result1)

    print("\n--- Ambiguous question ---")
    result2 = generate_sql("Show me the top performers", test_schema)
    print(result2) 