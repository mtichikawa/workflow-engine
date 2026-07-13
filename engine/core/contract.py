"""Contract — the fixed input/output shape of a specialist (the "plug").

Anything honoring a contract is interchangeable. Lightweight on purpose: a schema
is `{field_name: type}` for required fields; extra fields are allowed. `type` may be
a type, a tuple of types, or `object` for "anything".
"""

from __future__ import annotations

from dataclasses import dataclass


class ContractViolation(Exception):
    """Raised when a specialist's input or output does not match its contract."""


@dataclass(frozen=True)
class Contract:
    input: dict          # {field: type} required on the way in
    output: dict         # {field: type} guaranteed on the way out

    def validate_input(self, data: dict) -> None:
        self._check(data, self.input, "input")

    def validate_output(self, data: dict) -> None:
        self._check(data, self.output, "output")

    @staticmethod
    def _check(data: dict, schema: dict, which: str) -> None:
        if not isinstance(data, dict):
            raise ContractViolation(f"{which} must be a dict, got {type(data).__name__}")
        for field, typ in schema.items():
            if field not in data:
                raise ContractViolation(f"{which} missing required field '{field}'")
            if typ is object:
                continue
            if not isinstance(data[field], typ):
                want = getattr(typ, "__name__", str(typ))
                raise ContractViolation(
                    f"{which} field '{field}' should be {want}, got {type(data[field]).__name__}"
                )
