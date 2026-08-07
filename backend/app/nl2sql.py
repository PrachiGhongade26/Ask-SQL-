"""
nl2sql.py
Converts natural language questions into SQL (DuckDB by default, or another
dialect if requested) using the Groq API.
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

SYSTEM_PROMPT = """You are an expert SQL generator.

{dialect_instruction}

You must respond with ONLY a single valid JSON object. No markdown fences, no explanations outside the JSON.

The JSON must have exactly these fields:
- "confidence": either "high" or "low"
- "sql": the SQL query as a string (follow the dialect instruction above, no trailing semicolon), or null if confidence is "low"
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

DEFAULT_DIALECT_INSTRUCTION = "Use DuckDB SQL syntax."


def build_prompt(question: str, schema: str, dialect_instruction: str = DEFAULT_DIALECT_INSTRUCTION) -> list[dict]:
    """Builds the Groq chat messages payload for a given question + schema + dialect."""
    return [
        {
            "role": "system",
            "content": SYSTEM_PROMPT.format(schema=schema, dialect_instruction=dialect_instruction),
        },
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

def generate_sql(
    question: str,
    schema: str,
    temperature: float = 0.1,
    dialect_instruction: str = DEFAULT_DIALECT_INSTRUCTION,
) -> dict:
    """
    Converts a natural language question into a SQL query.

    Args:
        question: The user's natural language question.
        schema: A string describing table(s) and column(s).
        temperature: Lower = more deterministic SQL. Default 0.1 for consistency.
        dialect_instruction: Syntax guidance for the target SQL dialect
            (e.g. "Use PostgreSQL syntax: ..."). Defaults to DuckDB syntax.

    Returns:
        A dict with keys:
            "confidence": "high" or "low"
            "sql": the SQL string, or None if confidence is "low" or unanswerable
            "clarifying_question": a string if confidence is "low", else None

    Raises:
        RuntimeError: if the Groq API call fails or returns invalid JSON.
    """
    messages = build_prompt(question, schema, dialect_instruction=dialect_instruction)

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
# Query plan commentary
# ---------------------------------------------------------------------------

EXPLAIN_SYSTEM_PROMPT = """You are a senior database engineer reviewing a DuckDB query plan.

You will be given a SQL query and its EXPLAIN output (the query plan). Comment briefly (2-4 sentences) in plain English on:
1. Whether the query looks efficient or has any obvious performance concerns (e.g. full table scans on large tables, missing filters, unnecessary joins).
2. One concrete suggestion if there's an issue, or a short confirming note if there isn't.

Keep your response to plain text only. No JSON, no markdown, no headers.
"""


def explain_sql(sql: str, plan: str) -> str:
    """
    Sends a SQL query and its EXPLAIN plan to Groq and returns a plain-English
    commentary on whether the query looks efficient.
    """
    messages = [
        {"role": "system", "content": EXPLAIN_SYSTEM_PROMPT},
        {"role": "user", "content": f"SQL:\n{sql}\n\nQuery plan:\n{plan}"},
    ]

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.2,
            max_tokens=300,
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed during explain: {e}") from e

    return response.choices[0].message.content.strip()



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

    print("\n--- Postgres dialect ---")
    result3 = generate_sql(
        "What is the total sales amount by region for the year 2025?",
        test_schema,
        dialect_instruction="Use PostgreSQL syntax: double-quoted identifiers if needed, DATE_TRUNC() for date grouping, || for string concatenation, LIMIT n for row limits.",
    )
    print(result3)