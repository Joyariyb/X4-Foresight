import type { ReactNode } from "react";

export type BadgeRelation = "allied" | "friendly" | "neutral" | "hostile" | "atwar";

export interface BadgeProps {
  /** Diplomatic relation, which picks the colour scheme. */
  relation: BadgeRelation;
  /** Label text; defaults to the capitalised relation name. */
  children?: ReactNode;
}

const DEFAULT_LABEL: Record<BadgeRelation, string> = {
  allied: "Allied",
  friendly: "Friendly",
  neutral: "Neutral",
  hostile: "Hostile",
  atwar: "At War",
};

/**
 * Badge — a small status pill for faction/diplomacy state.
 *
 * Five relation variants map to the semantic palette: allied (green),
 * friendly (teal), neutral (grey outline), hostile (amber), atwar (red).
 * Rendered in the monospace data font to sit inline in tables and headers.
 */
export function Badge({ relation, children }: BadgeProps) {
  return (
    <span className={`x4-badge x4-badge--${relation}`}>
      {children ?? DEFAULT_LABEL[relation]}
    </span>
  );
}
