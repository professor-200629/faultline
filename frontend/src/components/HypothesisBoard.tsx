// Hypotheses board: the four catalogue hypotheses with status, cited evidence and notes.
import type { BoardEntry, Diagnosis } from "../api/types";
import { cls, hypName, STATUS_LABEL } from "../lib/format";

interface Props {
  board: BoardEntry[];
  descriptions: Record<string, string> | null;
  diagnosis: Diagnosis | null;
  knownEvidence: Set<string>;
  onEvidence: (id: string) => void;
}

function Chips({
  ids,
  tone,
  known,
  onEvidence,
}: {
  ids: string[];
  tone: "support" | "contra";
  known: Set<string>;
  onEvidence: (id: string) => void;
}) {
  if (!ids.length) return <span className="muted small">none</span>;
  return (
    <>
      {ids.map((id) => (
        <button
          key={id}
          type="button"
          className={cls("chip", "chip-evidence", "chip-btn", tone === "contra" && "chip-contra")}
          onClick={() => onEvidence(id)}
          disabled={!known.has(id)}
          aria-label={`${tone === "support" ? "Supporting" : "Contradicting"} evidence ${id}: show in timeline`}
          title={known.has(id) ? `Show ${id} in the timeline` : `${id} is not in the timeline`}
        >
          {id}
        </button>
      ))}
    </>
  );
}

export function HypothesisBoard({ board, descriptions, diagnosis, knownEvidence, onEvidence }: Props) {
  return (
    <ul className="board">
      {board.map((h) => {
        const id = String(h.id);
        const primary = diagnosis?.outcome === "diagnosed" && diagnosis.primary_hypothesis === id;
        return (
          <li key={id} className={cls("board-item", `board-${h.status}`, primary && "board-primary")}>
            <div className="board-head">
              <h3 className="board-title">{hypName(id)}</h3>
              <span className={cls("pill", `pill-${h.status}`)}>{STATUS_LABEL[h.status] ?? h.status}</span>
            </div>
            {descriptions?.[id] && <p className="board-desc">{descriptions[id]}</p>}
            {primary && <p className="board-flag">Submitted as the primary diagnosis</p>}
            <div className="board-ev">
              <span className="board-ev-label">supports</span>
              <Chips ids={h.supporting_evidence ?? []} tone="support" known={knownEvidence} onEvidence={onEvidence} />
            </div>
            <div className="board-ev">
              <span className="board-ev-label">contradicts</span>
              <Chips ids={h.contradicting_evidence ?? []} tone="contra" known={knownEvidence} onEvidence={onEvidence} />
            </div>
            {h.note ? <p className="board-note">{h.note}</p> : null}
          </li>
        );
      })}
    </ul>
  );
}
