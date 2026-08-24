import { useState } from "react";
import type {
  ApiCanonEvent,
  ApiEntry,
  ApiProposal,
  ReviewAction,
} from "../../api/types";
import { PageHeader } from "../../components/Layout";
import {
  WORLD_CATEGORIES,
  worldCompleteness,
} from "../../domain/worldbuilding";
import { WorldBuildStatus } from "./WorldBuildStatus";
import { WorldCategoryCarousel } from "./WorldCategoryCarousel";
import { WorldCategoryNavigator } from "./WorldCategoryNavigator";
import { InlineWorldReview, SealedWorldView } from "./WorldReviewViews";
import { WorldSealPanel } from "./WorldSealPanel";
import { SavedWorldEntries } from "./SavedWorldEntries";

export function WorldBuilderPage({
  campaignId,
  worldStatus,
  saved,
  canonEvents,
  proposals,
  onSave,
  building,
  buildFeedback,
  buildProgress,
  onBuildWorld,
  onSealWorld,
  sealing,
  onReview,
  reviewFeedback,
}: {
  campaignId: string;
  worldStatus: "draft" | "sealed";
  saved: ApiEntry[];
  canonEvents: ApiCanonEvent[];
  proposals: ApiProposal[];
  onSave: (entry: Omit<ApiEntry, "id">) => void;
  building: boolean;
  buildFeedback: string;
  buildProgress: { completed: string[]; total: number } | null;
  onBuildWorld: (categoryIds: string[]) => void;
  onSealWorld: () => void;
  sealing: boolean;
  onReview: (id: string, action: ReviewAction, detail?: string) => void;
  reviewFeedback: string;
}) {
  const total = WORLD_CATEGORIES.length;
  const completeness = worldCompleteness(saved, canonEvents);
  const [activeIndex, setActiveIndex] = useState(0);
  const [title, setTitle] = useState("");
  const [body, setBody] = useState("");
  const [tags, setTags] = useState("");
  const [showForm, setShowForm] = useState(false);
  if (worldStatus === "sealed")
    return (
      <SealedWorldView
        campaignId={campaignId}
        completeness={completeness}
        total={total}
        proposals={proposals}
        reviewFeedback={reviewFeedback}
        onReview={onReview}
      />
    );
  const activeCategory = WORLD_CATEGORIES[activeIndex];
  const activeStatus = completeness.perCategory[activeIndex];
  const activeEntries = saved.filter(
    (entry) => entry.category === activeCategory.id,
  );
  const canSave = title.trim().length > 0 && body.trim().length > 0;
  const clearForm = () => {
    setTitle("");
    setBody("");
    setTags("");
  };
  const goTo = (index: number) => {
    setActiveIndex(((index % total) + total) % total);
    setShowForm(false);
    clearForm();
  };
  const saveEntry = () => {
    if (!canSave) return;
    onSave({
      category: activeCategory.id,
      title: title.trim(),
      note: body.trim(),
      tags: tags
        .split(",")
        .map((tag) => tag.trim())
        .filter(Boolean),
    });
    clearForm();
    setShowForm(false);
  };
  return (
    <section className="world-builder">
      <PageHeader
        kicker="World Builder"
        title="Build your world"
        body="Step through the 18 categories and add what you know as tiles. When you build, the AI grounds every category on what you've provided and drafts the rest, so all 18 come back with cohesive, interlinked canon for you to review — then Seal world when you're happy."
      />
      <WorldBuildStatus
        buildFeedback={buildFeedback}
        buildProgress={buildProgress}
        building={building}
        completeness={completeness}
        onBuildWorld={onBuildWorld}
        proposals={proposals}
        total={total}
      />
      {proposals.length > 0 && (
        <InlineWorldReview
          proposals={proposals}
          reviewFeedback={reviewFeedback}
          onReview={onReview}
        />
      )}
      <WorldSealPanel
        building={building}
        hasBuiltContent={completeness.builtCount > 0}
        onSealWorld={onSealWorld}
        proposalsCount={proposals.length}
        sealing={sealing}
      />
      <WorldCategoryNavigator
        activeIndex={activeIndex}
        completeness={completeness}
        onSelect={goTo}
      />
      <WorldCategoryCarousel
        activeCategory={activeCategory}
        activeEntries={activeEntries}
        activeIndex={activeIndex}
        activeStatus={activeStatus}
        body={body}
        canSave={canSave}
        clearForm={clearForm}
        goTo={goTo}
        onBodyChange={setBody}
        onShowForm={setShowForm}
        onTagsChange={setTags}
        onTitleChange={setTitle}
        saveEntry={saveEntry}
        showForm={showForm}
        tags={tags}
        title={title}
        total={total}
      />
      <SavedWorldEntries entries={saved} />
    </section>
  );
}
