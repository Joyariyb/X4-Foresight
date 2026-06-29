import { ProgressBar } from "@x4-foresight/design-system";

const Row = ({ label, children }: { label: string; children: React.ReactNode }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: "var(--font-data)", fontSize: 12, color: "var(--text-secondary)" }}>
    <span style={{ width: 130 }}>{label}</span>
    {children}
  </div>
);

export const HullHealth = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 280 }}>
    <Row label="ARG Behemoth">{<ProgressBar variant="hull" value={92} />}</Row>
    <Row label="Hauler Prime">{<ProgressBar variant="hull" value={58} />}</Row>
    <Row label="Scout Theta">{<ProgressBar variant="hull" value={21} />}</Row>
  </div>
);

export const Reputation = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 280 }}>
    <Row label="Argon Federation">{<ProgressBar value={88} tone="teal" />}</Row>
    <Row label="Teladi Company">{<ProgressBar value={64} tone="teal" />}</Row>
    <Row label="Holy Order">{<ProgressBar value={22} tone="amber" />}</Row>
  </div>
);
