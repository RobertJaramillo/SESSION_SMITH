import { useEffect, useState } from "react";
import { listCanonEvents } from "../../api/client";
import type { ApiCanonEvent } from "../../api/types";
import { PageHeader } from "../../components/Layout";

export function CanonBrowserPage({ campaignId }: { campaignId: string }) {
  const [canon, setCanon] = useState<ApiCanonEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  useEffect(() => {
    let active = true;
    listCanonEvents(campaignId)
      .then((data) => {
        if (active) {
          setCanon(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [campaignId]);
  const needle = query.trim().toLowerCase();
  const filtered = needle
    ? canon.filter((item) =>
        `${item.category} ${item.summary}`.toLowerCase().includes(needle),
      )
    : canon;
  return (
    <section>
      <PageHeader
        kicker="Canon Memory Browser"
        title="Search approved campaign truth"
        body="Browse the approved memory the AI is allowed to draw on when generating prep and answers."
      />
      <article className="card full-card">
        <label>
          Search canon
          <input
            onChange={(event) => setQuery(event.target.value)}
            placeholder="NPC, faction, region, artifact, player character..."
            value={query}
          />
        </label>
        {loading ? (
          <p className="empty-state" role="status">
            Loading canon…
          </p>
        ) : canon.length === 0 ? (
          <p className="empty-state">
            No approved canon yet. Approve proposals in the review queue to
            build this campaign's memory.
          </p>
        ) : filtered.length === 0 ? (
          <p className="empty-state" role="status">
            No canon matches “{query}”.
          </p>
        ) : (
          <>
            <p className="empty-state" role="status">
              Showing {filtered.length} of {canon.length} approved memories.
            </p>
            <div className="canon-list">
              {filtered.map((item) => (
                <article className="canon-item" key={item.id}>
                  <span className="eyebrow">{item.category}</span>
                  <p>{item.summary}</p>
                </article>
              ))}
            </div>
          </>
        )}
      </article>
    </section>
  );
}
