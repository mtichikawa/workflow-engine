"""Brain port — the swappable Claude call behind judgment specialists.

Two backends:
  - cli  : `claude -p` (free on a Max plan) — the dev/proof default.
  - api  : the Anthropic API (billed) — for a shipped product.

Recipes never care which; a specialist just calls `brain(...)` / `brain_json(...)`.
GOTCHA (kept deliberately): the CLI backend strips ANTHROPIC_API_KEY from the
subprocess env, or the CLI tries the (possibly dead) key instead of the Max login.
"""

from __future__ import annotations

import json
import os
import re
import subprocess


class BrainError(Exception):
    pass


DEFAULT_PROVIDER = os.environ.get("ENGINE_BRAIN", "cli")
_CLI_TIMEOUT = int(os.environ.get("ENGINE_BRAIN_TIMEOUT", "180"))


def brain(prompt: str, system: str | None = None, temperature: float = 0.0,
          provider: str | None = None) -> str:
    """Return the model's raw text response."""
    provider = provider or DEFAULT_PROVIDER
    if provider == "cli":
        return _brain_cli(prompt, system)
    if provider == "api":
        return _brain_api(prompt, system, temperature)
    raise BrainError(f"unknown brain provider: {provider}")


def brain_json(prompt: str, system: str | None = None, temperature: float = 0.0,
               provider: str | None = None) -> dict | list:
    """Ask for JSON, parse it robustly, retry once on parse failure."""
    instruction = "\n\nReturn ONLY valid JSON. No prose, no markdown fences."
    raw = brain(prompt + instruction, system, temperature, provider)
    try:
        return _parse_json(raw)
    except ValueError:
        raw2 = brain(
            prompt + instruction + "\n\nYour previous reply was not valid JSON. "
            "Reply with the JSON object ONLY.",
            system, temperature, provider,
        )
        return _parse_json(raw2)


def _parse_json(raw: str):
    text = raw.strip()
    # strip ```json ... ``` fences if present
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # last resort: grab the first {...} or [...] block
        m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if m:
            return json.loads(m.group(1))
        raise ValueError(f"could not parse JSON from: {raw[:200]!r}")


def _brain_cli(prompt: str, system: str | None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    full = f"{system}\n\n{prompt}" if system else prompt
    try:
        r = subprocess.run(
            ["claude", "-p", "--output-format", "json", full],
            capture_output=True, text=True, env=env, timeout=_CLI_TIMEOUT,
        )
    except FileNotFoundError as e:
        raise BrainError("`claude` CLI not found on PATH") from e
    except subprocess.TimeoutExpired as e:
        raise BrainError("claude CLI timed out") from e
    if r.returncode != 0:
        raise BrainError(f"claude CLI failed: {r.stderr.strip()[:300]}")
    out = r.stdout.strip()
    try:                                          # JSON envelope: {result, usage, model, total_cost_usd}
        env_json = json.loads(out)
        u = env_json.get("usage") or {}
        _meter(env_json.get("model", "cli"), "cli", u.get("input_tokens"),
               u.get("output_tokens"), cli_cost=env_json.get("total_cost_usd"))
        return str(env_json.get("result", "")).strip()
    except json.JSONDecodeError:
        return out                                # older CLI without --output-format json


def _meter(model, provider, in_tok, out_tok, cli_cost=None) -> None:
    try:
        from ..costs import log_call
        log_call(model, provider, in_tok, out_tok, cli_cost=cli_cost)
    except Exception:  # noqa: BLE001 — metering must never break a call
        pass


def _brain_api(prompt: str, system: str | None, temperature: float) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise BrainError("api provider requires `pip install anthropic`") from e
    model = os.environ.get("ENGINE_BRAIN_MODEL", "claude-sonnet-4-5")
    client = anthropic.Anthropic()
    kwargs = {"model": model, "max_tokens": 2048, "temperature": temperature,
              "messages": [{"role": "user", "content": prompt}]}
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    u = getattr(msg, "usage", None)
    _meter(getattr(msg, "model", model), "api",
           getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()
