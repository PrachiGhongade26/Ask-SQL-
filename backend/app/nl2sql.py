"""
nl2sql.py
Converts natural language questions into DuckDB-compatible SQL using the Groq API.
"""

import os
import re
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

Rules you must follow strictly:
1. Output ONLY a single valid SQL query. No explanations, no comments, no markdown code fences.
2. Only use tables and columns provided in the schema below. Never invent column or table names.
3. Use DuckDB SQL syntax (it is close to PostgreSQL syntax).
4. Prefer explicit column names over SELECT * unless the user clearly wants all columns.
5. If the question is ambiguous, make the most reasonable interpretation rather than asking for clarification.
6. Do not include a trailing semicolon.
7. If the question cannot be answered with the given schema, output exactly: -- UNANSWERABLE

Schema:
{schema}
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

def clean_sql(raw: str) -> str:
    """Strips markdown fences, stray labels, and whitespace from model output."""
    text = raw.strip()

    # Remove ```sql ... ``` or ``` ... ``` fences if present
    fence_match = re.search(r"```(?:sql)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fence_match:
        text = fence_match.group(1).strip()

    # Remove a leading "SQL:" or similar label some models add
    text = re.sub(r"^(sql\s*:)\s*", "", text, flags=re.IGNORECASE)

    # Drop trailing semicolon for consistency (DuckDB doesn't need it)
    text = text.rstrip(";").strip()

    return text


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_sql(question: str, schema: str, temperature: float = 0.1) -> str:
    """
    Converts a natural language question into a SQL query.

    Args:
        question: The user's natural language question.
        schema: A string describing table(s) and column(s), e.g.:
                "TABLE sales(id INT, region TEXT, amount FLOAT, sale_date DATE)"
        temperature: Lower = more deterministic SQL. Default 0.1 for consistency.

    Returns:
        A cleaned SQL string, or "-- UNANSWERABLE" if the model can't answer it.

    Raises:
        RuntimeError: if the Groq API call fails.
    """
    messages = build_prompt(question, schema)

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            temperature=temperature,
            max_tokens=512,
        )
    except Exception as e:
        raise RuntimeError(f"Groq API call failed: {e}") from e

    raw_output = response.choices[0].message.content
    return clean_sql(raw_output)


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
    test_question = "What is the total sales amount by region for the year 2025?"

    sql = generate_sql(test_question, test_schema)
    print("Generated SQL:\n", sql)
