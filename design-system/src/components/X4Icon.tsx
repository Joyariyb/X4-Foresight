import type { CSSProperties } from "react";

export interface X4IconProps {
  /** Tabler icon name without the `ti-` prefix, e.g. "wallet", "rocket".
   *  Only the curated set in styles/icons.css renders a glyph. */
  name: string;
  /** Icon size in px. Defaults to inheriting the surrounding font-size. */
  size?: number;
  /** Optional colour override; defaults to the inherited text colour. */
  color?: string;
  className?: string;
}

/**
 * X4Icon — a single Tabler glyph in the X4 Foresight icon font.
 *
 * Thin wrapper over the `ti ti-<name>` icon-font classes the app uses for every
 * inline glyph (card headers, panel titles, alerts). Pass `name` without the
 * `ti-` prefix.
 */
export function X4Icon({ name, size, color, className }: X4IconProps) {
  const style: CSSProperties = {};
  if (size != null) style.fontSize = size;
  if (color != null) style.color = color;
  return (
    <i
      className={["ti", `ti-${name}`, className].filter(Boolean).join(" ")}
      style={style}
      aria-hidden="true"
    />
  );
}
