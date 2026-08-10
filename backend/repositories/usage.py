"""Usage-event persistence (tokens/cost/latency per AI call)."""

from __future__ import annotations

from backend.db import connect
from backend.schemas import UsageEvent


class PostgresUsageRepository:
    def record(self, event: UsageEvent) -> None:
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO usage_events (
                    id, job_id, campaign_id, model_provider, model_name, prompt_version,
                    input_tokens, output_tokens, estimated_cost_usd, latency_ms
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    event.id, event.job_id, event.campaign_id, event.model_provider, event.model_name,
                    event.prompt_version, event.input_tokens, event.output_tokens,
                    event.estimated_cost_usd, event.latency_ms,
                ),
            )
