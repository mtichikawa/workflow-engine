# deploy/ — container-per-customer isolation (4A · DESIGN ARTIFACT, not run)

**This is a design skeleton, not a running deployment.** Under the free-to-develop constraint the
engine runs on the Max-plan CLI brain, which is tied to one account and can't be containerized
per-customer — real deployment forces the **API brain** (a held item, per-call cost). These files
capture the *target* security model concretely; they're illustrative and intentionally not wired to run.

## The security distinction (the honest core)

The `--scope` seam (`state/examples/<scope>/…`) is **isolation, not security**: it prevents *accidental*
cross-tenant reads (you must name another scope to read it), but a determined or compromised caller
sharing one process/filesystem is not stopped by a string. **Real** cross-tenant security is an
**OS-enforced boundary**:

- **One container per customer.** Each mounts its **own** named volume at `state/`; customer X's
  container has no path to customer Y's volume — the kernel enforces it. "X can't reach Y" becomes an
  OS guarantee, not our code being bug-free.
- **baseline/tailored maps onto image/volume.** The base **image** ships code + `baseline/` exemplars
  (shared, versioned, identical everywhere); each customer's **volume** holds their `tailored/`
  exemplars + config + secrets. Improve the baseline → new image; add a customer → new volume, same image.
- **Requires the API brain.** Containers can't use the interactive Max CLI login — one API key per
  deployment (or a shared key with per-tenant accounting). "Deployment isolation" and "API brain" are
  one decision. Held for cost.

Full reasoning + trade-offs (kernel-sharing vs VM-per-customer, ops cost): `DESIGN.md` → *Deployment model*.

## Files
- `Dockerfile` — base-image skeleton (code + baseline exemplars; API-brain entrypoint).
- `docker-compose.yml` — two customers, each its own service + own volume, demonstrating the
  kernel-enforced isolation (no shared volume between them).

The brain flip (`ENGINE_BRAIN=api`) is real + already built; `ENGINE_SCOPE` here is illustrative — scope is set per container at the entrypoint via `--scope`.
