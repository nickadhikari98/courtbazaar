"""Generic state-machine helper shared by every status-driven flow in this
app (Lead->Professional verification, Hearing lifecycle, Settlement, Review)
so each flow's transition rules live in one small table instead of scattered
`if status == X: set to Y` branches — and so audit logging, notification
fan-out, and later AI-orchestration hooks attach in exactly one place per
flow instead of being reimplemented per flow.

Used by leads.py, hearings.py, escrow.py, and settlements.py. Deliberately
small: this is a transition table + one hook, not a workflow-orchestration
framework.
"""
import inspect
from typing import Any, Awaitable, Callable, Dict, Optional, Tuple, Union

TransitionTable = Dict[Tuple[str, str], str]  # (from_state, action) -> to_state
OnTransition = Callable[[Any, str, str, Optional[dict]], Union[None, "Awaitable[None]"]]


class IllegalTransition(Exception):
    def __init__(self, from_state: str, action: str):
        super().__init__(f"No transition for action '{action}' from state '{from_state}'")
        self.from_state = from_state
        self.action = action


class StateMachine:
    """`transitions` maps (current_state, action) -> next_state.

    `on_transition`, if given, runs after every successful transition as
    `on_transition(entity, from_state, to_state, actor)` — sync or async are
    both fine, an awaitable return value is awaited automatically. This is
    the one hook point audit logging / notification fan-out / (future) AI
    orchestration attach to, per flow, instead of each flow re-implementing
    that fan-out inline.
    """

    def __init__(self, transitions: TransitionTable, on_transition: Optional[OnTransition] = None):
        self.transitions = transitions
        self.on_transition = on_transition

    def next_state(self, current_state: str, action: str) -> str:
        try:
            return self.transitions[(current_state, action)]
        except KeyError:
            raise IllegalTransition(current_state, action)

    async def apply(self, entity: Any, current_state: str, action: str, actor: Optional[dict] = None) -> str:
        """Raises IllegalTransition if `action` isn't legal from `current_state`.
        Returns the new state; does not persist it — the caller writes the
        entity's own status field, this only validates the transition and
        runs the shared hook."""
        to_state = self.next_state(current_state, action)
        if self.on_transition:
            result = self.on_transition(entity, current_state, to_state, actor)
            if inspect.isawaitable(result):
                await result
        return to_state
