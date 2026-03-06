"""
Rule-based transaction categorization using rules/category_rules.yaml.
Description is uppercased and matched against keywords; default category is Other.
"""

import os
import yaml
import pandas as pd
from typing import Dict, List

# Default path relative to project root
DEFAULT_RULES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "rules", "category_rules.yaml"
)


def load_rules(rules_path: str = None) -> Dict[str, List[str]]:
    """
    Load category rules from YAML.
    Format: category_name: [KEYWORD1, KEYWORD2, ...]
    """
    path = rules_path or DEFAULT_RULES_PATH
    if not os.path.isfile(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data:
        return {}
    # Normalize: keys are category names, values are lists of uppercase keywords
    return {
        str(k).strip().lower(): [str(v).strip().upper() for v in (vlist if isinstance(vlist, list) else [vlist])]
        for k, vlist in data.items()
    }


def categorize_description(description: str, rules: Dict[str, List[str]]) -> str:
    """Return category for a single description string."""
    if not description or not rules:
        return "Other"
    upper = str(description).strip().upper()
    for category, keywords in rules.items():
        for kw in keywords:
            if kw in upper:
                return category
    return "Other"


def categorize_transactions(
    df: pd.DataFrame,
    description_column: str = "description",
    rules_path: str = None,
) -> pd.DataFrame:
    """
    Assign category to each row based on description and YAML rules.
    Adds/overwrites column 'category'.
    """
    rules = load_rules(rules_path)
    out = df.copy()
    if description_column not in out.columns:
        return out
    out["category"] = out[description_column].apply(
        lambda d: categorize_description(d, rules)
    )
    return out
