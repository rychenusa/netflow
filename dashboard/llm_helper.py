"""
Optional LLM helpers for Netflow (OpenAI-compatible API).
Only used when OPENAI_API_KEY is set in Streamlit secrets or environment.
"""

import os
from typing import List, Optional


def get_api_key() -> Optional[str]:
    """Get OpenAI API key: session state (entered in app) > Streamlit secrets > env. Returns None if not set."""
    try:
        import streamlit as st
        # Key entered in the app (turn on AI on the website)
        session_key = st.session_state.get("openai_api_key") or ""
        if session_key and session_key.strip():
            return session_key.strip()
        key = st.secrets.get("OPENAI_API_KEY") or st.secrets.get("openai", {}).get("api_key")
        if key:
            return key
    except Exception:
        pass
    return os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_API_KEY".lower())


def llm_suggest_category(description: str, existing_categories: List[str]) -> Optional[str]:
    """
    Ask the LLM to suggest one category for a transaction description.
    existing_categories: list of valid category names (e.g. from rules or DB).
    Returns suggested category name or None on error.
    """
    key = get_api_key()
    if not key:
        return None
    try:
        from openai import OpenAI  # optional: pip install openai
        client = OpenAI(api_key=key)
        cats = ", ".join(existing_categories) if existing_categories else "groceries, dining, transport, subscriptions, utilities, shopping, entertainment, other"
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": f"Pick exactly one category for the transaction. Reply with only the category name, nothing else. Choose from: {cats}. If unsure use 'other'."},
                {"role": "user", "content": f"Transaction description: {description[:500]}"},
            ],
            max_tokens=30,
        )
        text = (resp.choices[0].message.content or "").strip().lower()
        for c in existing_categories:
            if c.lower() == text or (len(text) > 2 and c.lower() in text):
                return c
        return "other" if "other" in [x.lower() for x in existing_categories] else (existing_categories[0] if existing_categories else "other")
    except Exception:
        return None


def llm_ask(question: str, context: str) -> Optional[str]:
    """Answer a short question about the user's finances given a context string."""
    key = get_api_key()
    if not key:
        return None
    try:
        from openai import OpenAI  # optional: pip install openai
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful personal finance assistant. Answer in 1-3 short sentences based only on the context. Be concise."},
                {"role": "user", "content": f"Context:\n{context}\n\nQuestion: {question}"},
            ],
            max_tokens=200,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        return None
