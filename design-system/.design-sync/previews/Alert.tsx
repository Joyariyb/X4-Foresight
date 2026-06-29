import { Alert } from "@x4-foresight/design-system";

export const Critical = () => (
  <Alert tone="red">Xenon fleet detected jumping into Grand Exchange — 2 stations under threat.</Alert>
);

export const Warning = () => (
  <Alert tone="amber">Hull Parts Forge running below 20% input stock — production stalling.</Alert>
);

export const Positive = () => (
  <Alert tone="green" icon="shield">Trade defence contract fulfilled — reputation with Teladi Company increased.</Alert>
);

export const Stacked = () => (
  <div style={{ display: "flex", flexDirection: "column", gap: 6, minWidth: 420 }}>
    <Alert tone="red">2 ships destroyed near Hatikvah's Choice III.</Alert>
    <Alert tone="amber">Energy Cells surplus building up at 4 stations.</Alert>
    <Alert tone="green" icon="shield">New wharf construction complete in Argon Prime.</Alert>
  </div>
);
