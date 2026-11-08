"""The shared Claude client for every agent in the app (the Arena's Lanista and Sceptic, the Gauntlet's
Scribe, Alchemist and Skeptic).

Agents never produce numbers or verdicts; this module only moves text. `ask_traced` validates a reply
against a pydantic schema and returns, with it, a trace of how the answer was obtained: which execution
mode produced it, why the script had to take over, and the request id when the API gives one. The trace
never contains the API key or the prompt, so it is safe to write to the public ledger.
"""

from __future__ import annotations

import json
import os
from typing import Callable

from pydantic import BaseModel, ValidationError

Complete = Callable[[str, str], str]  # (system, user) -> text

LIVE = "LIVE_CLAUDE"
SCRIPTED = "SCRIPTED"                    # no model was asked (no key, or the script was chosen)
FALLBACK = "SCRIPTED_FALLBACK"           # the model was asked, and its answer could not be used

ENV_FILE = os.path.join(os.path.dirname(__file__), "..", "..", ".env")
TIMEOUT_S = 45.0


def _extract_json(text: str) -> str:
    starts = [i for i in (text.find("{"), text.find("[")) if i >= 0]
    if not starts:
        raise ValueError("no JSON in reply")
    start = min(starts)
    end = max(text.rfind("}"), text.rfind("]"))
    return text[start:end + 1]


def _reason(e: Exception) -> str:
    name = e.__class__.__name__.lower()
    if "timeout" in name:
        return "TIMEOUT"
    if "auth" in name or "permission" in name:
        return "API_AUTH_ERROR"
    if "connection" in name:
        return "API_UNREACHABLE"
    return "API_ERROR"


def ask_traced(complete: Complete | None, system: str, payload: dict, schema: type[BaseModel],
               prompt_version: str = "") -> tuple[BaseModel | None, dict]:
    """Call the model, validate against `schema`, retry once with the error.

    Returns (reply or None, trace). The trace is what the ledger records: execution mode, fallback reason,
    schema validation outcome, prompt version and the API's request id (never the key, never the prompt).
    """
    trace = {"execution_mode": FALLBACK, "fallback_reason": None, "schema_validation": "NOT_RUN",
             "prompt_version": prompt_version, "request_id": None, "attempts": 0}
    if complete is None:
        trace.update(execution_mode=SCRIPTED, fallback_reason="NO_API_KEY")
        return None, trace
    user = json.dumps(payload, default=str)
    for _ in range(2):
        trace["attempts"] += 1
        try:
            text = complete(system, user)
            trace["request_id"] = getattr(complete, "last_request_id", None)
            reply = schema.model_validate_json(_extract_json(text))
            trace.update(execution_mode=LIVE, schema_validation="VALID", fallback_reason=None)
            return reply, trace
        except ValueError as e:  # pydantic's ValidationError is a ValueError too
            trace.update(schema_validation="INVALID",
                         fallback_reason="SCHEMA_INVALID" if isinstance(e, ValidationError) else "MALFORMED_JSON")
            if isinstance(e, ValidationError):   # where and why it failed, never the reply's content
                trace["schema_errors"] = [f"{'.'.join(map(str, x['loc']))}: {x['type']}" for x in e.errors()][:6]
            user = json.dumps({**payload, "your_last_reply_was_invalid": str(e)[:300]}, default=str)
        except Exception as e:  # network or API error: give up and let the script take over
            trace.update(fallback_reason=_reason(e))
            return None, trace
    return None, trace


def ask(complete: Complete, system: str, payload: dict, schema: type[BaseModel]):
    """Call the model, validate against `schema`, retry once with the error. None on failure."""
    return ask_traced(complete, system, payload, schema)[0]


def anthropic_complete(model: str | None = None, temperature: float | None = None) -> Complete:
    """A Complete function backed by the Anthropic API. Needs ANTHROPIC_API_KEY.

    The function remembers the id of its last response (`last_request_id`) for request tracing.
    """
    import inspect

    import anthropic

    try:   # a timeout and one retry, but only if this SDK's constructor accepts them
        accepted = set(inspect.signature(anthropic.Anthropic).parameters)
    except (TypeError, ValueError):
        accepted = set()
    opts = {k: v for k, v in (("timeout", TIMEOUT_S), ("max_retries", 1)) if k in accepted}
    client = anthropic.Anthropic(**opts)
    model = model or os.environ.get("ARENA_MODEL", "claude-sonnet-5-5")

    def complete(system: str, user: str) -> str:
        extra = {} if temperature is None else {"temperature": temperature}
        complete.calls += 1
        msg = client.messages.create(model=model, max_tokens=1500, system=system,
                                     messages=[{"role": "user", "content": user}], **extra)
        complete.last_request_id = getattr(msg, "id", None)
        return "".join(block.text for block in msg.content if block.type == "text")

    complete.last_request_id = None
    complete.calls = 0     # API calls made, for the benchmark's compute budget
    return complete


def load_env_key(path: str | os.PathLike = ".env") -> None:
    """Put ANTHROPIC_API_KEY from a .env file into the environment, unless it is already set."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return
    for line in lines:
        key, sep, value = line.strip().partition("=")
        value = value.strip().strip('"').strip("'")
        if sep and key.strip() == "ANTHROPIC_API_KEY" and value:
            os.environ["ANTHROPIC_API_KEY"] = value
            return


def llm_available(env_file: str | os.PathLike = ENV_FILE) -> bool:
    """Claude plays whenever an API key is set (in the shell or in .env)."""
    load_env_key(env_file)
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def client_or_none(use_llm: bool) -> Complete | None:
    """A Complete function when Claude should be used and a key exists, else None (the script plays)."""
    if not use_llm or not llm_available():
        return None
    return anthropic_complete()
