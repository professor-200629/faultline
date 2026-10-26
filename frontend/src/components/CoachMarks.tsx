// Keyboard-navigable coach-mark sequence anchored to [data-coach] elements.
// The host returns focus on close (the card unmounts with focus inside it).
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

export interface CoachStep {
  target: string;
  title: string;
  body: ReactNode;
}

interface Rect {
  top: number;
  left: number;
  width: number;
  height: number;
}

const CARD_W = 340;
const GAP = 12;
const FOCUSABLE = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
}

export function CoachMarks({ steps, onClose, initial = 0 }: { steps: CoachStep[]; onClose: () => void; initial?: number }) {
  const [i, setI] = useState(initial);
  const [rect, setRect] = useState<Rect | null>(null);
  const [cardH, setCardH] = useState(260);
  const cardRef = useRef<HTMLDivElement>(null);
  const headRef = useRef<HTMLHeadingElement>(null);
  const step = steps[Math.min(i, steps.length - 1)];

  const measure = useCallback(() => {
    const el = document.querySelector<HTMLElement>(`[data-coach="${step.target}"]`);
    if (!el) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    // clip very tall targets to the viewport so the spotlight stays meaningful
    const top = Math.max(r.top, 4);
    const bottom = Math.min(r.bottom, window.innerHeight - 4);
    setRect({ top, left: r.left, width: r.width, height: Math.max(24, bottom - top) });
  }, [step.target]);

  useEffect(() => {
    const el = document.querySelector<HTMLElement>(`[data-coach="${step.target}"]`);
    el?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: prefersReducedMotion() ? "auto" : "smooth" });
    measure();
    const t = window.setTimeout(measure, 350);
    headRef.current?.focus();
    return () => window.clearTimeout(t);
  }, [i, step.target, measure]);

  useEffect(() => {
    let raf = 0;
    const onChange = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(measure);
    };
    window.addEventListener("resize", onChange);
    window.addEventListener("scroll", onChange, true);
    const iv = window.setInterval(measure, 1000); // content can grow while a run is live
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("resize", onChange);
      window.removeEventListener("scroll", onChange, true);
      window.clearInterval(iv);
    };
  }, [measure]);

  useLayoutEffect(() => {
    if (cardRef.current) setCardH(cardRef.current.getBoundingClientRect().height);
  }, [i, rect]);

  const next = useCallback(() => (i < steps.length - 1 ? setI(i + 1) : onClose()), [i, steps.length, onClose]);
  const back = useCallback(() => i > 0 && setI(i - 1), [i]);

  // Keys work wherever focus is (Escape always; arrows unless typing in a field), and
  // Tab / Shift+Tab wrap inside the card so keyboard focus cannot slip behind it.
  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => {
      if (e.defaultPrevented) return;
      const card = cardRef.current;
      const t = e.target instanceof HTMLElement ? e.target : null;
      const inCard = !!card && !!t && card.contains(t);
      const typing = !!t && !inCard && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName));
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      } else if ((e.key === "ArrowRight" || e.key === "ArrowLeft") && !typing && (inCard || !t || t === document.body)) {
        e.preventDefault();
        if (e.key === "ArrowRight") next();
        else back();
      } else if (e.key === "Tab" && card && (inCard || !t || t === document.body)) {
        const items = Array.from(card.querySelectorAll<HTMLElement>(FOCUSABLE));
        if (!items.length) return;
        const first = items[0];
        const last = items[items.length - 1];
        const active = document.activeElement;
        if (!inCard || (e.shiftKey && (active === first || active === headRef.current))) {
          e.preventDefault();
          (e.shiftKey ? last : first).focus();
        } else if (!e.shiftKey && active === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [next, back, onClose]);


  const vw = window.innerWidth;
  const vh = window.innerHeight;
  let style: CSSProperties;
  if (vw < 720 || !rect) {
    style = rect ? { left: GAP, right: GAP, bottom: GAP } : { left: Math.max(GAP, vw / 2 - CARD_W / 2), top: Math.max(GAP, vh / 2 - cardH / 2), width: CARD_W };
  } else {
    let left: number;
    let top: number;
    if (rect.left + rect.width + GAP + CARD_W <= vw - GAP) {
      left = rect.left + rect.width + GAP;
      top = rect.top;
    } else if (rect.left - GAP - CARD_W >= GAP) {
      left = rect.left - GAP - CARD_W;
      top = rect.top;
    } else {
      left = Math.min(Math.max(GAP, rect.left), vw - CARD_W - GAP);
      top = rect.top + rect.height + GAP + cardH <= vh - GAP ? rect.top + rect.height + GAP : rect.top - GAP - cardH;
    }
    top = Math.min(Math.max(GAP, top), vh - cardH - GAP);
    style = { left, top, width: CARD_W };
  }

  return (
    <div className="coach-layer">
      {rect && (
        <div
          className="coach-spot"
          aria-hidden="true"
          style={{ top: rect.top - 6, left: rect.left - 6, width: rect.width + 12, height: rect.height + 12 }}
        />
      )}
      <div
        className="coach-card"
        role="dialog"
        aria-modal="false"
        aria-labelledby="coach-title"
        aria-describedby="coach-body"
        ref={cardRef}
        style={style}
      >
        <p className="coach-count">
          Guide · step {i + 1} of {steps.length}
        </p>
        <h2 id="coach-title" className="coach-title" tabIndex={-1} ref={headRef}>
          {step.title}
        </h2>
        <div id="coach-body" className="coach-body">
          {step.body}
        </div>
        <div className="coach-actions">
          <button type="button" className="btn btn-sm" onClick={back} disabled={i === 0}>
            Back
          </button>
          <button type="button" className="btn btn-sm btn-primary" onClick={next}>
            {i < steps.length - 1 ? "Next" : "Finish"}
          </button>
          <button type="button" className="btn btn-sm btn-ghost" onClick={onClose}>
            Skip guide
          </button>
        </div>
        <p className="coach-keys">Keys: ← back · → next · Esc close</p>
      </div>
    </div>
  );
}
