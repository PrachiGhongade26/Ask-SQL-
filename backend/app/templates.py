"""
Role-based query templates for AskSQL.
Each role has a set of pre-built natural language questions
that map well to the synthetic e-commerce dataset schema.
"""

ROLE_TEMPLATES = {
    "sales_manager": {
        "label": "Sales Manager",
        "description": "Revenue, customers, and sales performance",
        "templates": [
            {"id": "sm_1", "question": "What is the total revenue by month for this year?"},
            {"id": "sm_2", "question": "Who are the top 10 customers by total order value?"},
            {"id": "sm_3", "question": "Which product category generated the most revenue last quarter?"},
            {"id": "sm_4", "question": "What is the average order value by region?"},
        ],
    },
    "inventory_analyst": {
        "label": "Inventory Analyst",
        "description": "Stock levels, product movement, and supply insights",
        "templates": [
            {"id": "ia_1", "question": "Which products have the lowest stock quantity right now?"},
            {"id": "ia_2", "question": "What are the top 10 fastest-selling products this month?"},
            {"id": "ia_3", "question": "Which products have had zero sales in the last 90 days?"},
            {"id": "ia_4", "question": "What is the total inventory value by category?"},
        ],
    },
    "marketing_analyst": {
        "label": "Marketing Analyst",
        "description": "Campaigns, customer segments, and engagement",
        "templates": [
            {"id": "ma_1", "question": "Which customer segment has the highest repeat purchase rate?"},
            {"id": "ma_2", "question": "What is the customer acquisition trend by month?"},
            {"id": "ma_3", "question": "Which products are most frequently bought together?"},
            {"id": "ma_4", "question": "What percentage of customers are first-time buyers vs repeat buyers?"},
        ],
    },
}


def get_all_templates():
    """Return the full role -> templates structure."""
    return ROLE_TEMPLATES


def get_templates_by_role(role_key: str):
    """Return templates for a single role, or None if not found."""
    return ROLE_TEMPLATES.get(role_key)