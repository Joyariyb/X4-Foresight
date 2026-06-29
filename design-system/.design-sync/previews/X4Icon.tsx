import { X4Icon } from "@x4-foresight/design-system";

const names = ["wallet", "coin", "ship", "rocket", "building-factory-2", "world", "package", "users", "shield", "swords", "chart-line", "flask"];

export const IconGrid = () => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: 16, fontSize: 22, color: "var(--color-primary)", maxWidth: 360 }}>
    {names.map((n) => (
      <X4Icon key={n} name={n} />
    ))}
  </div>
);

export const Tones = () => (
  <div style={{ display: "flex", gap: 18, fontSize: 24 }}>
    <X4Icon name="wallet" color="var(--color-primary)" />
    <X4Icon name="trending-up" color="var(--color-positive)" />
    <X4Icon name="alert-triangle" color="var(--color-warning)" />
    <X4Icon name="swords" color="var(--color-negative)" />
  </div>
);
