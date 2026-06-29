export type ProgressBarVariant = "rep" | "hull";
export type ProgressBarTone = "auto" | "teal" | "green" | "amber" | "red";

export interface ProgressBarProps {
  /** Fill percentage, 0–100. */
  value: number;
  /** `rep` is the thin reputation bar; `hull` is the taller health bar. */
  variant?: ProgressBarVariant;
  /** Fill colour. `auto` derives green/amber/red from the value (health style). */
  tone?: ProgressBarTone;
}

const TONE_COLOR: Record<Exclude<ProgressBarTone, "auto">, string> = {
  teal: "var(--color-primary)",
  green: "var(--color-positive)",
  amber: "var(--color-warning)",
  red: "var(--color-negative)",
};

/** Health-style colour ramp: full = green, damaged = amber, critical = red. */
function autoColor(value: number): string {
  if (value >= 66) return TONE_COLOR.green;
  if (value >= 33) return TONE_COLOR.amber;
  return TONE_COLOR.red;
}

/**
 * ProgressBar — the inline reputation / hull-health bar.
 *
 * A fixed-width track with a coloured fill. `rep` is the thin 3px reputation
 * meter; `hull` is the taller rounded health bar. With `tone="auto"` the fill
 * colours itself green→amber→red by value, matching the ship hull readouts.
 */
export function ProgressBar({ value, variant = "rep", tone = "auto" }: ProgressBarProps) {
  const pct = Math.max(0, Math.min(100, value));
  const color = tone === "auto" ? autoColor(pct) : TONE_COLOR[tone];
  return (
    <span className={`x4-bar-wrap x4-bar-wrap--${variant}`}>
      <span className="x4-bar" style={{ width: `${pct}%`, background: color }} />
    </span>
  );
}
