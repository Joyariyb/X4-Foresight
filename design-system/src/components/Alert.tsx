import type { ReactNode } from "react";
import { X4Icon } from "./X4Icon";

export type AlertTone = "red" | "amber" | "green";

export interface AlertProps {
  /** Severity, which sets the colour scheme. */
  tone: AlertTone;
  /** Message content. */
  children: ReactNode;
  /** Optional Tabler icon name (without `ti-`); defaults to a tone-appropriate glyph. */
  icon?: string;
}

const DEFAULT_ICON: Record<AlertTone, string> = {
  red: "alert-triangle",
  amber: "alert-triangle",
  green: "shield",
};

/**
 * Alert — an inline notice bar for empire events and warnings.
 *
 * A leading icon and a monospace message on a tinted, outlined background.
 * Three tones: red (critical — losses, war declarations), amber (warnings —
 * low stock, hull damage), green (positive confirmations).
 */
export function Alert({ tone, children, icon }: AlertProps) {
  return (
    <div className={`x4-alert x4-alert--${tone}`}>
      <X4Icon name={icon ?? DEFAULT_ICON[tone]} className="x4-alert__icon" />
      <span>{children}</span>
    </div>
  );
}
