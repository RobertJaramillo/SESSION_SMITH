import {
  WORLD_CATEGORIES,
  worldCompleteness,
} from "../../domain/worldbuilding";

export function WorldCategoryNavigator({
  activeIndex,
  completeness,
  onSelect,
}: {
  activeIndex: number;
  completeness: ReturnType<typeof worldCompleteness>;
  onSelect: (index: number) => void;
}) {
  return (
    <div className="jump-strip" role="tablist" aria-label="World categories">
      {WORLD_CATEGORIES.map((category, index) => {
        const built = completeness.perCategory[index].built;
        const active = index === activeIndex;
        const state = built ? "built" : "gap";
        return (
          <button
            aria-selected={active}
            className={`category-pill ${active ? "active" : ""} ${state}`}
            key={category.id}
            onClick={() => onSelect(index)}
            role="tab"
            type="button"
          >
            <span className={`pill-dot ${state}`} aria-hidden="true" />
            {category.label}
          </button>
        );
      })}
    </div>
  );
}
