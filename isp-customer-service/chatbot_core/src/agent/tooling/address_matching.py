"""Fuzzy street/locality scoring from the CRM address resolver (the same
scores the resolve_address tool uses), for the deterministic NLU reader."""

from crm_mcp.tools.address_resolver import locality_match_score, street_match_score

__all__ = ["locality_match_score", "street_match_score"]
