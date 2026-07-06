"""
llm_client.py — one reusable function for talking to the LLM.

Using Groq's free tier (fast, no cost, generous limits) with Llama 3.
Everything else in the app calls `ask_llm()` — nobody else needs to
know which provider is behind it. That makes swapping to Gemini/Ollama
later a one-file change.
"""

import os
import json
from dotenv import load_dotenv
from groq import Groq

load_dotenv()

_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
MODEL = "llama-3.3-70b-versatile"


def ask_llm(system_prompt: str, user_prompt: str, expect_json: bool = False) -> str:
    """
    Send a prompt to the LLM and return its text response.

    expect_json=True asks Groq to force valid JSON output, which we rely
    on heavily since planner.py needs structured task lists back, not
    free-flowing prose.
    """
    kwargs = {}
    if expect_json:
        kwargs["response_format"] = {"type": "json_object"}

    response = _client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        max_tokens=2000,
        **kwargs,
    )
    return response.choices[0].message.content


def ask_llm_json(system_prompt: str, user_prompt: str) -> dict:
    """
    Convenience wrapper: calls ask_llm with expect_json=True and parses it.
    Retries once with a stricter instruction if parsing fails — this is
    our simple retry/fallback safeguard against malformed LLM output.
    """
    raw = ask_llm(system_prompt, user_prompt, expect_json=True)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        strict_prompt = user_prompt + "\n\nIMPORTANT: Respond with ONLY valid JSON. No markdown, no commentary."
        raw_retry = ask_llm(system_prompt, strict_prompt, expect_json=True)
        return json.loads(raw_retry)  # if this still fails, let it raise — caller handles the error