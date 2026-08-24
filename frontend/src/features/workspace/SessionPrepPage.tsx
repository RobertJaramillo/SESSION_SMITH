import { PageHeader } from "../../components/Layout";
import type { BuildFeedback } from "./buildFeedback";

export type PrepState = {
  goal: string;
  tone: string;
  memories: string;
  outline: string;
};

export function SessionPrepPage({
  prep,
  generating,
  feedback,
  onChange,
  onGenerate,
}: {
  prep: PrepState;
  generating: boolean;
  feedback: BuildFeedback | null;
  onChange: (patch: Partial<PrepState>) => void;
  onGenerate: () => void;
}) {
  return (
    <section>
      <PageHeader
        kicker="Session Prep"
        title="Generate the next table-ready session"
        body="Draft the next session from approved canon only. Review and edit everything before you bring it to the table."
      />
      <div className="two-column">
        <article className="card">
          <h3>Prep controls</h3>
          <label>
            Session goal
            <input
              value={prep.goal}
              onChange={(event) => onChange({ goal: event.target.value })}
              placeholder="What should the next session accomplish?"
            />
          </label>
          <label>
            Desired tone
            <select
              value={prep.tone}
              onChange={(event) => onChange({ tone: event.target.value })}
            >
              <option value="wonder">Wonder</option>
              <option value="danger">Danger</option>
              <option value="intrigue">Intrigue</option>
            </select>
          </label>
          <label>
            Use memories
            <textarea
              value={prep.memories}
              onChange={(event) => onChange({ memories: event.target.value })}
              placeholder="Which approved memories should the prep draw from?"
            />
          </label>
          <button disabled={generating} onClick={onGenerate} type="button">
            {generating ? "Generating prep…" : "Queue AI prep job"}
          </button>
          {!generating && feedback && (
            <section
              className={`build-feedback build-feedback-${feedback.kind}`}
              role={feedback.kind === "error" ? "alert" : "status"}
            >
              <h3>{feedback.title}</h3>
              <p>{feedback.message}</p>
              {feedback.kind === "error" && (
                <p className="build-feedback-guidance">{feedback.guidance}</p>
              )}
            </section>
          )}
        </article>
        <article className="card">
          <h3>Generated outline</h3>
          {generating ? (
            <p className="empty-state" role="status">
              Pulling approved canon and drafting an outline…
            </p>
          ) : prep.outline.trim() === "" ? (
            <p className="empty-state">
              No prep generated yet. Set a goal and queue an AI prep job to
              build an outline.
            </p>
          ) : (
            <label>
              Edit before your session
              <textarea
                value={prep.outline}
                onChange={(event) => onChange({ outline: event.target.value })}
              />
            </label>
          )}
        </article>
      </div>
    </section>
  );
}
