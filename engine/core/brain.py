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
import shutil
import subprocess


class BrainError(Exception):
    pass


DEFAULT_PROVIDER = os.environ.get("ENGINE_BRAIN", "cli")
_CLI_TIMEOUT = int(os.environ.get("ENGINE_BRAIN_TIMEOUT", "180"))


def brain(prompt: str, system: str | None = None, temperature: float = 0.0,
          provider: str | None = None, files: list[str] | None = None) -> str:
    """Return the model's raw text response. `files` are images (PNG/JPEG) the model looks at."""
    from .tape import active
    t = active()
    if t:                                   # a recording or replay is running (engine/core/tape.py)
        return t.call(prompt, system, lambda: _brain(prompt, system, temperature, provider, files), files)
    return _brain(prompt, system, temperature, provider, files)


def _brain(prompt: str, system: str | None, temperature: float, provider: str | None,
           files: list[str] | None = None) -> str:
    provider = provider or DEFAULT_PROVIDER
    if provider == "cli":
        return _brain_cli(prompt, system, files)
    if provider == "api":
        return _brain_api(prompt, system, temperature, files)
    raise BrainError(f"unknown brain provider: {provider}")


def brain_json(prompt: str, system: str | None = None, temperature: float = 0.0,
               provider: str | None = None, files: list[str] | None = None) -> dict | list:
    """Ask for JSON, parse it robustly, retry once on parse failure."""
    instruction = "\n\nReturn ONLY valid JSON. No prose, no markdown fences."
    raw = brain(prompt + instruction, system, temperature, provider, files)
    try:
        return _parse_json(raw)
    except ValueError:
        raw2 = brain(
            prompt + instruction + "\n\nYour previous reply was not valid JSON. "
            "Reply with the JSON object ONLY.",
            system, temperature, provider, files,
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


# GUI apps (Claude Desktop launching the MCP server), cron and systemd give child processes a minimal
# PATH that usually lacks the CLI's install dir — so PATH alone isn't enough to find it.
_CLAUDE_FALLBACKS = ("~/.local/bin/claude", "~/.claude/local/claude",
                     "/opt/homebrew/bin/claude", "/usr/local/bin/claude")


def _claude_bin() -> str:
    """ENGINE_CLAUDE_BIN, else `claude` on PATH, else the CLI's standard install locations."""
    if os.environ.get("ENGINE_CLAUDE_BIN"):
        return os.path.expanduser(os.environ["ENGINE_CLAUDE_BIN"])
    found = shutil.which("claude")
    if found:
        return found
    for cand in map(os.path.expanduser, _CLAUDE_FALLBACKS):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    raise BrainError("`claude` CLI not found on PATH or in "
                     + ", ".join(_CLAUDE_FALLBACKS) + " — set ENGINE_CLAUDE_BIN to its path")


def _brain_cli(prompt: str, system: str | None, files: list[str] | None = None) -> str:
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    full = f"{system}\n\n{prompt}" if system else prompt
    args = [_claude_bin(), "-p", "--output-format", "json"]
    if files:                               # the CLI looks at images through its Read tool, nothing else
        full += ("\n\nLook at each of these image files with the Read tool before answering, in order:\n"
                 + "\n".join(f"- {os.path.abspath(f)}" for f in files))
        args.append("--allowedTools=Read")
    try:
        r = subprocess.run(                 # prompt on stdin: an argv string is capped at 128 KB on Linux
            args, input=full,
            capture_output=True, text=True, env=env, timeout=_CLI_TIMEOUT,
        )
    except FileNotFoundError as e:
        raise BrainError(f"`claude` CLI not runnable: {e}") from e
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


def _brain_api(prompt: str, system: str | None, temperature: float,
               files: list[str] | None = None) -> str:
    try:
        import anthropic
    except ImportError as e:
        raise BrainError("api provider requires `pip install anthropic`") from e
    model = os.environ.get("ENGINE_BRAIN_MODEL", "claude-sonnet-4-5")
    client = anthropic.Anthropic()
    kwargs = {"model": model, "max_tokens": 2048, "temperature": temperature,
              "messages": [{"role": "user", "content": _api_content(prompt, files)}]}
    if system:
        kwargs["system"] = system
    msg = client.messages.create(**kwargs)
    u = getattr(msg, "usage", None)
    _meter(getattr(msg, "model", model), "api",
           getattr(u, "input_tokens", None), getattr(u, "output_tokens", None))
    return "".join(b.text for b in msg.content if getattr(b, "type", None) == "text").strip()


def _api_content(prompt: str, files: list[str] | None):
    if not files:
        return prompt
    import base64
    import mimetypes
    blocks = []
    for f in files:
        mime = mimetypes.guess_type(f)[0] or "image/png"
        with open(f, "rb") as fh:
            data = base64.standard_b64encode(fh.read()).decode()
        blocks.append({"type": "image", "source": {"type": "base64", "media_type": mime, "data": data}})
    return blocks + [{"type": "text", "text": prompt}]
