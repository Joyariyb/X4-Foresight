// Side-effect CSS imports — bundled by Vite into a single x4-foresight-ds.css.
// Order matters: tokens define the vars, fonts/icons register faces, then the
// component rules consume them.
import "./styles/tokens.css";
import "./styles/fonts.css";
import "./styles/icons.css";
import "./styles/components.css";

export { X4Icon } from "./components/X4Icon";
export type { X4IconProps } from "./components/X4Icon";

export { SummaryCard } from "./components/SummaryCard";
export type { SummaryCardProps, SummaryCardTone } from "./components/SummaryCard";

export { Badge } from "./components/Badge";
export type { BadgeProps, BadgeRelation } from "./components/Badge";

export { Alert } from "./components/Alert";
export type { AlertProps, AlertTone } from "./components/Alert";

export { Panel } from "./components/Panel";
export type { PanelProps } from "./components/Panel";

export { DataTable } from "./components/DataTable";
export type { DataTableProps, DataTableColumn } from "./components/DataTable";

export { SectionHeader } from "./components/SectionHeader";
export type { SectionHeaderProps } from "./components/SectionHeader";

export { TabButton } from "./components/TabButton";
export type { TabButtonProps } from "./components/TabButton";

export { ProgressBar } from "./components/ProgressBar";
export type { ProgressBarProps, ProgressBarVariant, ProgressBarTone } from "./components/ProgressBar";

export { Tag } from "./components/Tag";
export type { TagProps } from "./components/Tag";
