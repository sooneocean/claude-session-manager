"""Cost tracking models for Claude Session Manager - T5"""
from dataclasses import dataclass, field


@dataclass
class CostSummary:
    total_tokens_in: int = 0
    total_tokens_out: int = 0
    total_cost_usd: float = 0.0
    session_count: int = 0


class CostAggregator:
    """Aggregates cost across all sessions."""

    def __init__(self):
        self._costs: dict[str, tuple[int, int, float]] = {}  # session_id → (tokens_in, tokens_out, cost)

    def update(self, session_id: str, tokens_in: int, tokens_out: int, cost_usd: float) -> None:
        """Update (replace) cost data for a session."""
        self._costs[session_id] = (tokens_in, tokens_out, cost_usd)

    def remove(self, session_id: str) -> None:
        """Remove a session's cost data."""
        self._costs.pop(session_id, None)

    def get_total(self) -> CostSummary:
        """Get aggregated totals across all sessions."""
        total_in = 0
        total_out = 0
        total_cost = 0.0
        for tokens_in, tokens_out, cost_usd in self._costs.values():
            total_in += tokens_in
            total_out += tokens_out
            total_cost += cost_usd
        return CostSummary(
            total_tokens_in=total_in,
            total_tokens_out=total_out,
            total_cost_usd=total_cost,
            session_count=len(self._costs),
        )

    def get_session_cost(self, session_id: str) -> tuple[int, int, float]:
        """Get cost for a specific session. Returns (0, 0, 0.0) if not found."""
        return self._costs.get(session_id, (0, 0, 0.0))
