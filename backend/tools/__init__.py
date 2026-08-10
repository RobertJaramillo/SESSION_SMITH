"""
tools — The internal tool skeleton (baseline).

These are the bounded building blocks the AI worker is allowed to call
(AI_ARCHITECTURE.md §12.1). Each tool does ONE thing and knows nothing about the
others. Workflows (see worker.py) compose them in order — the tools themselves
are not workflows.

Design rules baked in (AI_ARCHITECTURE.md §12.2 — "Bounded Agent Design"):
    • retrieve_relevant_memory returns APPROVED CANON ONLY — never raw notes or
      pending/rejected proposals. This is the trust boundary.
    • store_memory_proposals writes with status=pending — it CANNOT create canon.
      Only a human GM decision (a separate API path) promotes a proposal to canon.
    • validate_structured_output rejects anything that doesn't match the schema;
      nothing invalid ever reaches the database.

All types come from schemas.py, so the tool signatures ARE the data contract.
Bodies are stubs (`raise NotImplementedError`) — this is the agreed skeleton to
build against, not the implementation.

Each tool lives in its own module grouped by concern; import from this package
(`from backend.tools import build_prompt`, or `import backend.tools as tools`)
so call sites are unaffected as new tools are added.
"""

from __future__ import annotations

from backend.tools.context import load_campaign_context
from backend.tools.llm import call_llm_provider
from backend.tools.prompting import build_prompt
from backend.tools.retrieval import retrieve_relevant_memory
from backend.tools.storage import store_memory_proposals, store_session_prep
from backend.tools.usage import record_usage_event
from backend.tools.validation import validate_structured_output

__all__ = [
    "load_campaign_context",
    "retrieve_relevant_memory",
    "build_prompt",
    "call_llm_provider",
    "validate_structured_output",
    "store_memory_proposals",
    "store_session_prep",
    "record_usage_event",
]
