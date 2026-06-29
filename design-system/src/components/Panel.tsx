import type { ReactNode } from "react";

export interface PanelProps {
  /** Uppercase title shown in the panel header bar. */
  title: ReactNode;
  /** Optional content rendered on the right of the header (e.g. a count or action). */
  headerExtra?: ReactNode;
  /** Panel body — tables, lists, ware tags, etc. */
  children: ReactNode;
}

/**
 * Panel — a titled container surface for a section of the dashboard.
 *
 * A raised card with an uppercase header bar (optionally with a right-aligned
 * extra slot) over an inset body. Wraps DataTables, ware-tag rows, and lists.
 * The body has no padding so flush-edge tables sit cleanly inside.
 */
export function Panel({ title, headerExtra, children }: PanelProps) {
  return (
    <div className="x4-panel">
      <div className="x4-panel__head">
        <span>{title}</span>
        {headerExtra != null && <span>{headerExtra}</span>}
      </div>
      <div className="x4-panel__body">{children}</div>
    </div>
  );
}
