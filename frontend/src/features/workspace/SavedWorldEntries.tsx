import type { ApiEntry } from "../../api/types";
import { WORLD_CATEGORIES } from "../../domain/worldbuilding";

export function SavedWorldEntries({ entries }: { entries: ApiEntry[] }) {
  if (entries.length === 0) return null;
  return (
    <article className="card full-card">
      <h3>Saved this session ({entries.length})</h3>
      <div className="canon-grid">
        {entries.map((entry) => (
          <span key={entry.id}>
            {WORLD_CATEGORIES.find((category) => category.id === entry.category)
              ?.label ?? entry.category}
            : {entry.title}
          </span>
        ))}
      </div>
    </article>
  );
}
