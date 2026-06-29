import type { ReactNode } from "react";

export interface TabButtonProps {
  /** Button label. */
  children: ReactNode;
  /** Whether this tab is the active one (teal outline + text). */
  active?: boolean;
  /** Click handler for switching tabs. */
  onClick?: () => void;
}

/**
 * TabButton — an outlined pill toggle for switching sub-views.
 *
 * Uppercase condensed label in an outlined pill. The active tab uses the teal
 * primary colour for both text and border; inactive tabs brighten on hover.
 * Used for the per-station and per-faction sub-tab rows.
 */
export function TabButton({ children, active = false, onClick }: TabButtonProps) {
  return (
    <button
      type="button"
      className={["x4-tab-btn", active && "x4-tab-btn--active"].filter(Boolean).join(" ")}
      onClick={onClick}
    >
      {children}
    </button>
  );
}
