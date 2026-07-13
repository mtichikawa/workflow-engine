"""Engine core — the engine: specialists, contracts, recipes, board, dispatcher."""

from .board import Board, Card
from .brain import BrainError, brain, brain_json
from .contract import Contract, ContractViolation
from .dispatcher import Dispatcher
from .recipe import Edge, Recipe, Step
from .specialist import Specialist, all_specialists, get, register
from .trace import Tracer
from .validator import Finding, is_valid, validate

__all__ = [
    "Board", "Card", "Contract", "ContractViolation", "Dispatcher",
    "Recipe", "Step", "Edge", "Specialist", "Tracer",
    "brain", "brain_json", "BrainError",
    "register", "get", "all_specialists",
    "validate", "is_valid", "Finding",
]
