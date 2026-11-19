import { useEffect, useRef, type ReactNode } from "react";
import { createPortal } from "react-dom";

/** Shared modal semantics, Escape handling, focus containment and restoration. */
export function Dialog({ children, labelledBy, onClose, className = "settings-modal", overlayClassName = "" }: {
  children: ReactNode;
  labelledBy: string;
  onClose: () => void;
  className?: string;
  overlayClassName?: string;
}) {
  const ref = useRef<HTMLElement>(null);
  useEffect(() => {
    const element = ref.current!;
    const previous = document.activeElement as HTMLElement | null;
    const controls = () => Array.from(element.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), a[href], [tabindex="0"]')).filter(item => !item.hidden);
    (controls()[0] ?? element).focus();
    const keydown = (event: KeyboardEvent) => {
      const dialogs = document.querySelectorAll('[data-app-dialog]');
      if (dialogs[dialogs.length - 1] !== element) return;
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); onClose(); }
      if (event.key === "Tab") {
        const items = controls();
        const first = items[0]; const last = items[items.length - 1];
        if (!first) { event.preventDefault(); element.focus(); }
        else if (event.shiftKey && (document.activeElement === first || !element.contains(document.activeElement))) { event.preventDefault(); last.focus(); }
        else if (!event.shiftKey && (document.activeElement === last || !element.contains(document.activeElement))) { event.preventDefault(); first.focus(); }
      }
    };
    document.addEventListener('keydown', keydown);
    return () => { document.removeEventListener('keydown', keydown); previous?.focus(); };
  }, [onClose]);
  return createPortal(<div className={`modal-backdrop ${overlayClassName}`} role="presentation">
    <section ref={ref} tabIndex={-1} data-app-dialog aria-labelledby={labelledBy} aria-modal="true" role="dialog" className={className}>{children}</section>
  </div>, document.body);
}
