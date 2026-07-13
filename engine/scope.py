"""Scope — the tenant seam, built in from the start so it never has to be retrofitted.

The lesson (learned the hard way elsewhere): the cost of multi-tenancy isn't the feature,
it's the single-tenant *assumption* baked into the data model — un-baking it later means
threading a tenant key through every read and hunting silent leaks. So we bake the seam in
now, while it's tiny, without building the multi-tenant *runtime* (server/isolation — held).

Two design choices make leaks impossible by construction rather than by discipline:
  - **Isolation by path, not by filter** — each scope's examples live in their own directory
    (state/examples/<scope>/). You can't accidentally read another tenant; you'd have to name
    their directory. (See examples.py.)
  - **Ambient context, not a threaded parameter** — the active scope lives in one ContextVar
    set once at the entry point; the storage layer reads it. Specialists never see it (they
    keep calling fewshot.block(name, input), unaware of scope — like they're unaware of
    concurrency). ContextVar (not a global) because the dispatcher runs specialists in a
    thread pool; each run carries its own scope safely.

Reads resolve a LAYER CHAIN [baseline, <tenant>] (baseline always first, tenant on top — the
baseline+tailored model). Writes target ONE scope (the tenant if set, else baseline).

SECURITY BOUNDARY — read this before trusting it with real customer data.
This is ISOLATION (a correctness property), NOT SECURITY (enforced access control). It stops
tenants from being read *by accident*; it does NOT stop a determined or compromised caller.
Everything runs as ONE process / ONE OS user / ONE filesystem: the active scope is just a
string (nothing *authenticates* that the caller is that tenant), any code in-process can open
any directory, and golds are plaintext at rest. Real cross-tenant security is a property of the
RUNTIME (held): the recommended model is PER-CUSTOMER DEPLOYMENT ISOLATION — each customer in
its own container/VM with its own filesystem + credentials, so the OS enforces "X can't reach
Y," not our code being bug-free. A shared multi-tenant server would instead need authn + a
verified tenant claim + an authz check on every access + encryption — the expensive path.
Correct framing for a customer: "tenant data is isolated by construction WITHIN a deployment;
cross-customer security is provided by deploying each customer separately."
"""

from __future__ import annotations

import contextlib
import contextvars

BASELINE = "baseline"
_active: contextvars.ContextVar = contextvars.ContextVar("engine_scope", default=None)


def set_scope(name: str | None):
    """Set the active tenant scope; returns a token (reset via reset_scope). Entry-point use."""
    return _active.set(name or None)


def reset_scope(token) -> None:
    _active.reset(token)


@contextlib.contextmanager
def use_scope(name: str | None):
    """Temporarily run under a tenant scope."""
    token = _active.set(name or None)
    try:
        yield
    finally:
        _active.reset(token)


def active() -> str | None:
    """The current tenant scope, or None (= baseline-only)."""
    a = _active.get()
    return None if a in (None, BASELINE) else a


def read_layers() -> list[str]:
    """The scopes to read, in order: baseline first, then the tenant (if any) on top."""
    a = active()
    return [BASELINE] if a is None else [BASELINE, a]


def write_scope() -> str:
    """The single scope writes target: the tenant if set, else baseline."""
    return active() or BASELINE
