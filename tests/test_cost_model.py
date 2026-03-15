"""Tests for CostAggregator and CostSummary - T5"""
import pytest
from csm.models.cost import CostAggregator, CostSummary


class TestCostSummary:

    def test_cost_summary_defaults(self):
        summary = CostSummary()
        assert summary.total_tokens_in == 0
        assert summary.total_tokens_out == 0
        assert summary.total_cost_usd == 0.0
        assert summary.session_count == 0


class TestCostAggregator:

    def test_empty_aggregator_returns_zero(self):
        agg = CostAggregator()
        summary = agg.get_total()
        assert summary.total_tokens_in == 0
        assert summary.total_tokens_out == 0
        assert summary.total_cost_usd == 0.0
        assert summary.session_count == 0

    def test_single_session_update(self):
        agg = CostAggregator()
        agg.update("sess-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        summary = agg.get_total()
        assert summary.total_tokens_in == 100
        assert summary.total_tokens_out == 50
        assert summary.total_cost_usd == pytest.approx(0.01)
        assert summary.session_count == 1

    def test_multiple_sessions_accumulate(self):
        agg = CostAggregator()
        agg.update("sess-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        agg.update("sess-2", tokens_in=200, tokens_out=80, cost_usd=0.02)
        agg.update("sess-3", tokens_in=300, tokens_out=120, cost_usd=0.05)
        summary = agg.get_total()
        assert summary.total_tokens_in == 600
        assert summary.total_tokens_out == 250
        assert summary.total_cost_usd == pytest.approx(0.08)
        assert summary.session_count == 3

    def test_remove_session_deducts_cost(self):
        agg = CostAggregator()
        agg.update("sess-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        agg.update("sess-2", tokens_in=200, tokens_out=80, cost_usd=0.02)
        agg.remove("sess-1")
        summary = agg.get_total()
        assert summary.total_tokens_in == 200
        assert summary.total_tokens_out == 80
        assert summary.total_cost_usd == pytest.approx(0.02)
        assert summary.session_count == 1

    def test_update_same_session_replaces(self):
        agg = CostAggregator()
        agg.update("sess-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        # Update same session with new values (replace, not add)
        agg.update("sess-1", tokens_in=300, tokens_out=150, cost_usd=0.05)
        summary = agg.get_total()
        assert summary.total_tokens_in == 300
        assert summary.total_tokens_out == 150
        assert summary.total_cost_usd == pytest.approx(0.05)
        assert summary.session_count == 1

    def test_remove_nonexistent_session_is_noop(self):
        agg = CostAggregator()
        agg.update("sess-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        agg.remove("not-exist")
        summary = agg.get_total()
        assert summary.session_count == 1

    def test_get_session_cost_existing(self):
        agg = CostAggregator()
        agg.update("sess-1", tokens_in=100, tokens_out=50, cost_usd=0.01)
        tokens_in, tokens_out, cost = agg.get_session_cost("sess-1")
        assert tokens_in == 100
        assert tokens_out == 50
        assert cost == pytest.approx(0.01)

    def test_get_session_cost_not_found(self):
        agg = CostAggregator()
        tokens_in, tokens_out, cost = agg.get_session_cost("not-exist")
        assert tokens_in == 0
        assert tokens_out == 0
        assert cost == 0.0
