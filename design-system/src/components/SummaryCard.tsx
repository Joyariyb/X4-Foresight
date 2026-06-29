import { X4Icon } from "./X4Icon";

export type SummaryCardTone = "default" | "teal" | "green" | "amber" | "red";

export interface SummaryCardProps {
  /** Small uppercase label above the value (e.g. "ACCOUNT BALANCE"). */
  label: string;
  /** The headline value, rendered in the monospace data font. */
  value: string;
  /** Optional Tabler icon name (without `ti-`) shown beside the label. */
  icon?: string;
  /** Colour of the value — maps to the semantic feedback palette. */
  tone?: SummaryCardTone;
}

const TONE_CLASS: Record<SummaryCardTone, string> = {
  default: "",
  teal: "x4-card__value--teal",
  green: "x4-card__value--green",
  amber: "x4-card__value--amber",
  red: "x4-card__value--red",
};

/**
 * SummaryCard — a compact KPI tile for the top of a dashboard tab.
 *
 * An uppercase label (optionally with a leading icon) over a large monospace
 * value. Tone colours the value to signal positive/warning/critical states.
 * Lay several out in an `.x4-cards-row` grid for the standard summary strip.
 */
export function SummaryCard({ label, value, icon, tone = "default" }: SummaryCardProps) {
  return (
    <div className="x4-card">
      <div className="x4-card__top">
        {icon && <X4Icon name={icon} className="x4-card__icon" />}
        <span className="x4-card__label">{label}</span>
      </div>
      <span className={["x4-card__value", TONE_CLASS[tone]].filter(Boolean).join(" ")}>
        {value}
      </span>
    </div>
  );
}
