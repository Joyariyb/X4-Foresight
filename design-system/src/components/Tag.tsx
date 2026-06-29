import type { ReactNode } from "react";

export interface TagProps {
  /** Tag label (e.g. a ware name like "Energy Cells"). */
  children: ReactNode;
}

/**
 * Tag — a neutral pill for wares, keywords, and small metadata chips.
 *
 * Monospace label on a panel-toned background with a subtle outline. Lay
 * several out in a flex-wrap row (e.g. the ware lists under a station panel).
 */
export function Tag({ children }: TagProps) {
  return <span className="x4-tag">{children}</span>;
}
