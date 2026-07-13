"""Recipe — a graph of specialist-steps connected by edges.

A recipe is `steps + edges`. An **edge** connects the end of one step to the start of
another and may carry a `when` condition. A **backward** edge (whose target appears at or
before its source in `steps`) forms a loop, bounded by `max_visits`. A step with multiple
in-edges is a **join** (`and` = wait for all, `or` = the first). Branches are just multiple
conditional out-edges.

`inputs` maps a specialist's contract fields to sources in the item's context:
    "payload" · "payload.<key>" · "<step_id>" · "<step_id>.<key>"  (anything else = a literal)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Step:
    id: str
    specialist: str
    config: dict = field(default_factory=dict)
    inputs: dict = field(default_factory=dict)
    gate: bool = False
    domain: bool = False
    join: str = "and"                    # for multiple in-edges: "and" (all) | "or" (first)


@dataclass
class Edge:
    src: str
    dst: str
    when: str | None = None              # condition on src's output; None = unconditional


@dataclass
class Recipe:
    name: str
    steps: list[Step]
    edges: list[Edge] = field(default_factory=list)
    max_visits: int = 6                  # loop guard: a step runs at most this many times

    def __post_init__(self):
        if not self.edges:               # no edges given -> a linear chain (back-compat)
            self.edges = [Edge(a.id, b.id) for a, b in zip(self.steps, self.steps[1:])]

    # ---- lookups --------------------------------------------------------
    def step(self, step_id: str) -> Step:
        for s in self.steps:
            if s.id == step_id:
                return s
        raise KeyError(f"recipe '{self.name}' has no step '{step_id}'")

    def step_ids(self) -> list[str]:
        return [s.id for s in self.steps]

    def _order(self, step_id: str) -> int:
        return self.step_ids().index(step_id)

    # ---- edges ----------------------------------------------------------
    def is_backward(self, e: Edge) -> bool:
        return self._order(e.dst) <= self._order(e.src)

    def in_edges(self, step_id: str) -> list[Edge]:
        return [e for e in self.edges if e.dst == step_id]

    def out_edges(self, step_id: str) -> list[Edge]:
        return [e for e in self.edges if e.src == step_id]

    def forward_in(self, step_id: str) -> list[Edge]:
        return [e for e in self.in_edges(step_id) if not self.is_backward(e)]

    def backward_out(self, step_id: str) -> list[Edge]:
        return [e for e in self.out_edges(step_id) if self.is_backward(e)]

    def entry_steps(self) -> list[str]:
        return [s.id for s in self.steps if not self.forward_in(s.id)]

    def loop_body(self, dst: str, src: str) -> list[str]:
        """The steps to reset when a backward edge src->dst fires: dst .. src inclusive."""
        lo, hi = self._order(dst), self._order(src)
        return self.step_ids()[lo:hi + 1]
