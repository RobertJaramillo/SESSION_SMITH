"""
llm.py — Model-call tools (through the provider-agnostic seam).

Thin wrapper so workflows depend on the LLMProvider interface, not a vendor SDK.
"""

from __future__ import annotations

from backend.llm_provider import LLMProvider, LLMRequest, LLMResponse


def call_llm_provider(provider: LLMProvider, req: LLMRequest) -> LLMResponse:
    """Send the request to whichever provider is configured. Thin wrapper so
    workflows depend on the interface, not a vendor SDK."""
    resp = provider.generate_structured(req)
    resp.prompt_version = req.prompt_version
    return resp


__all__ = ["call_llm_provider"]
