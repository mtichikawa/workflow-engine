"""Specialist — an agent that performs one capability (role + contract).

Two kinds: `capability` (generic, reused across recipes) and `domain` (bespoke).
Some are pure code (adapters, fetch); judgment specialists call the brain port.

The base `run()` enforces the contract on both sides, so a specialist can NEVER
silently return the wrong shape — that discipline is what keeps recipes composable.
"""

from __future__ import annotations

from .contract import Contract

_REGISTRY: dict[str, "Specialist"] = {}


class Specialist:
    name: str = "unnamed"
    kind: str = "capability"          # capability | domain | adapter
    description: str = ""             # first-class metadata (registry falls back to its own map)
    tags: tuple = ()
    contract: Contract = Contract(input={}, output={})

    def run(self, input: dict, config: dict | None = None) -> dict:
        config = config or {}
        merged = {**config, **input}          # config fields + resolved inputs
        self.contract.validate_input(merged)
        output = self._run(merged, config)
        self.contract.validate_output(output)
        return output

    def _run(self, input: dict, config: dict) -> dict:  # noqa: ARG002
        raise NotImplementedError(f"{self.name} has no _run")


def register(spec: "Specialist") -> "Specialist":
    """Register a single shared instance. Both recipes import the SAME object —
    that's what keeps 'shared specialist' honest rather than a near-copy."""
    _REGISTRY[spec.name] = spec
    return spec


def get(name: str) -> "Specialist":
    if name not in _REGISTRY:
        raise KeyError(f"no specialist named '{name}' (have: {sorted(_REGISTRY)})")
    return _REGISTRY[name]


def all_specialists() -> dict[str, "Specialist"]:
    return dict(_REGISTRY)
