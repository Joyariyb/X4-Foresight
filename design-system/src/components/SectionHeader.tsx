export interface SectionHeaderProps {
  /** Uppercase section title. */
  title: string;
}

/**
 * SectionHeader — a titled divider that introduces a block of content.
 *
 * A short uppercase label in the condensed label font followed by a thin rule
 * that fills the remaining width. Used between summary cards and the detail
 * panels on each dashboard tab.
 */
export function SectionHeader({ title }: SectionHeaderProps) {
  return (
    <div className="x4-sec-header">
      <span className="x4-sec-title">{title}</span>
      <span className="x4-sec-line" />
    </div>
  );
}
