export function WorldSealPanel({
  building,
  hasBuiltContent,
  onSealWorld,
  proposalsCount,
  sealing,
}: {
  building: boolean;
  hasBuiltContent: boolean;
  onSealWorld: () => void;
  proposalsCount: number;
  sealing: boolean;
}) {
  if (proposalsCount === 0 && !hasBuiltContent) return null;
  return (
    <article className="card full-card">
      <h3>Happy with your world?</h3>
      <p className="empty-state">
        {proposalsCount > 0
          ? "Sealing locks the World Builder — after this, every change comes from Session Notes. Approve the proposals you want first (or Regenerate above)."
          : "All proposals reviewed. Sealing locks the World Builder — after this, every change comes from Session Notes."}
      </p>
      <div className="button-row">
        <button
          disabled={sealing || building}
          onClick={onSealWorld}
          type="button"
        >
          {sealing ? "Sealing…" : "Seal world"}
        </button>
      </div>
    </article>
  );
}
