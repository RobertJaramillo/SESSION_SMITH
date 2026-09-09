import type { ApiEntry } from "../../api/types";
import {
  type WORLD_CATEGORIES,
  worldCompleteness,
} from "../../domain/worldbuilding";

type Category = (typeof WORLD_CATEGORIES)[number];
type CategoryStatus = ReturnType<
  typeof worldCompleteness
>["perCategory"][number];

export function WorldCategoryCarousel({
  activeCategory,
  activeEntries,
  activeIndex,
  activeStatus,
  body,
  canSave,
  clearForm,
  goTo,
  onBodyChange,
  onShowForm,
  onTagsChange,
  onTitleChange,
  saveEntry,
  showForm,
  tags,
  title,
  total,
}: {
  activeCategory: Category;
  activeEntries: ApiEntry[];
  activeIndex: number;
  activeStatus: CategoryStatus;
  body: string;
  canSave: boolean;
  clearForm: () => void;
  goTo: (index: number) => void;
  onBodyChange: (value: string) => void;
  onShowForm: (show: boolean) => void;
  onTagsChange: (value: string) => void;
  onTitleChange: (value: string) => void;
  saveEntry: () => void;
  showForm: boolean;
  tags: string;
  title: string;
  total: number;
}) {
  return (
    <div className="carousel">
      <button
        className="carousel-arrow"
        aria-label="Previous category"
        onClick={() => goTo(activeIndex - 1)}
        type="button"
      >
        ‹
      </button>
      <article className="card full-card carousel-card">
        <div className="carousel-head">
          <span className="eyebrow">
            {activeCategory.label} · {activeIndex + 1}/{total}
          </span>
          <span
            className={`status-badge status-${activeStatus.built ? "active" : "paused"}`}
          >
            {activeStatus.built ? "built" : "gap"}
          </span>
        </div>
        <h3>{activeCategory.prompt}</h3>
        <div className="example-row">
          {activeCategory.examples.map((example) => (
            <span key={example}>{example}</span>
          ))}
        </div>
        <div className="tile-grid">
          {activeEntries.map((entry) => (
            <article className="tile" key={entry.id}>
              <strong>{entry.title}</strong>
              <p>{entry.note}</p>
              {entry.tags.length > 0 && (
                <div className="canon-grid">
                  {entry.tags.map((tag) => (
                    <span key={tag}>{tag}</span>
                  ))}
                </div>
              )}
            </article>
          ))}
          {activeStatus.canonCount > 0 && (
            <article className="tile tile-canon">
              <strong>{activeStatus.canonCount} approved canon</strong>
              <p>
                This category already has approved canon — browse it in the
                Canon Browser.
              </p>
            </article>
          )}
          {!showForm && (
            <button
              className="tile tile-add"
              onClick={() => onShowForm(true)}
              type="button"
            >
              + Add {activeCategory.label} detail
            </button>
          )}
        </div>
        {showForm && (
          <div className="add-form">
            <label>
              Entry title
              <input
                value={title}
                onChange={(event) => onTitleChange(event.target.value)}
                placeholder={`${activeCategory.label} entry title`}
              />
            </label>
            <label>
              Notes for this session document
              <textarea
                value={body}
                onChange={(event) => onBodyChange(event.target.value)}
                placeholder="Paste world setup, session notes, lore updates, NPC changes, or canon changes here."
              />
            </label>
            <label>
              Tags, comma separated
              <input
                value={tags}
                onChange={(event) => onTagsChange(event.target.value)}
                placeholder="session_01, faction, oath_magic"
              />
            </label>
            <div className="button-row">
              <button disabled={!canSave} onClick={saveEntry} type="button">
                Save entry to this session
              </button>
              <button
                className="secondary"
                onClick={() => {
                  clearForm();
                  onShowForm(false);
                }}
                type="button"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
        {!activeStatus.built && (
          <p className="empty-state">
            The AI will draft starter {activeCategory.label} canon when you
            build.
          </p>
        )}
      </article>
      <button
        className="carousel-arrow"
        aria-label="Next category"
        onClick={() => goTo(activeIndex + 1)}
        type="button"
      >
        ›
      </button>
    </div>
  );
}
