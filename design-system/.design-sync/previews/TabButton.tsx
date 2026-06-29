import { TabButton } from "@x4-foresight/design-system";

export const TabRow = () => (
  <div style={{ display: "flex", gap: 6, flexWrap: "wrap" }}>
    <TabButton active>Overview</TabButton>
    <TabButton>Production</TabButton>
    <TabButton>Storage</TabButton>
    <TabButton>Docked Ships</TabButton>
  </div>
);

export const States = () => (
  <div style={{ display: "flex", gap: 6 }}>
    <TabButton active>Active</TabButton>
    <TabButton>Inactive</TabButton>
  </div>
);
