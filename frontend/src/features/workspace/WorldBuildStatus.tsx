import type { ApiProposal } from "../../api/types";
import { worldCompleteness } from "../../domain/worldbuilding";
import type { BuildFeedback } from "./buildFeedback";

export function WorldBuildStatus({
  buildFeedback,
  buildProgress,
  building,
  completeness,
  onBuildWorld,
  proposals,
  total,
}: {
  buildFeedback: BuildFeedback | null;
  buildProgress: { completed: string[]; total: number } | null;
  building: boolean;
  completeness: ReturnType<typeof worldCompleteness>;
  onBuildWorld: (categoryIds: string[]) => void;
  proposals: ApiProposal[];
  total: number;
}) {
  const gaps = completeness.gaps;
  return (
    <article className="card full-card">
      <div className="world-progress">
        <h3>
          {completeness.builtCount}/{total} categories built
        </h3>
        <div className="progress-track" aria-hidden="true">
          <span
            className="progress-fill"
            style={{ width: `${(completeness.builtCount / total) * 100}%` }}
          />
        </div>
      </div>
      {gaps.length > 0 ? (
        <p className="empty-state">
          Gaps still open ({gaps.length}):{" "}
          {gaps.map((gap) => gap.label).join(", ")}. The AI will draft canon for
          all of them when you build.
        </p>
      ) : (
        <p className="empty-state">
          Every category has content — you're ready to build.
        </p>
      )}
      <div className="button-row">
        <button
          disabled={building}
          onClick={() => onBuildWorld([])}
          type="button"
        >
          {building
            ? "Building your world…"
            : proposals.length > 0
              ? "Regenerate world"
              : "Build world (all 18 categories)"}
        </button>
      </div>
      <p className="empty-state">
        Building won't seal the world — you review the proposals first, and can
        add more or regenerate.
      </p>
      {building &&
        (buildProgress ? (
          <div role="status">
            <div className="progress-track" aria-hidden="true">
              <span
                className="progress-fill"
                style={{
                  width: `${(buildProgress.completed.length / buildProgress.total) * 100}%`,
                }}
              />
            </div>
            <p className="empty-state">
              {buildProgress.completed.length}/{buildProgress.total} categories
              drafted so far
              {buildProgress.completed.length > 0
                ? `: ${buildProgress.completed.join(", ")}`
                : "…"}
            </p>
          </div>
        ) : (
          <p className="empty-state" role="status">
            The AI worker is developing a world bible before drafting each
            category…
          </p>
        ))}
      {!building && buildFeedback && (
        <section
          className={`build-feedback build-feedback-${buildFeedback.kind}`}
          role={buildFeedback.kind === "error" ? "alert" : "status"}
        >
          <h3>{buildFeedback.title}</h3>
          <p>{buildFeedback.message}</p>
          {buildFeedback.kind === "error" && (
            <p className="build-feedback-guidance">{buildFeedback.guidance}</p>
          )}
        </section>
      )}
    </article>
  );
}
