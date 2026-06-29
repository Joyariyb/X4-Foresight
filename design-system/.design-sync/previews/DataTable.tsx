import { DataTable, Badge, ProgressBar } from "@x4-foresight/design-system";

export const FleetTable = () => (
  <div style={{ minWidth: 560 }}>
    <DataTable
      columns={[
        { header: "Ship", field: "ship" },
        { header: "Class", field: "cls" },
        { header: "Hull", field: "hull" },
        { header: "Cargo", field: "cargo", numeric: true },
      ]}
      rows={[
        { ship: "ARG Behemoth", cls: "Destroyer", hull: <ProgressBar variant="hull" value={92} />, cargo: "—" },
        { ship: "Hauler Prime", cls: "Freighter", hull: <ProgressBar variant="hull" value={61} />, cargo: "18,400" },
        { ship: "Scout Theta", cls: "Scout", hull: <ProgressBar variant="hull" value={24} />, cargo: "0" },
      ]}
    />
  </div>
);

export const DiplomacyTable = () => (
  <div style={{ minWidth: 480 }}>
    <DataTable
      columns={[
        { header: "Faction", field: "faction" },
        { header: "Standing", field: "standing" },
        { header: "Reputation", field: "rep" },
      ]}
      rows={[
        { faction: "Argon Federation", standing: <Badge relation="allied" />, rep: <ProgressBar value={88} tone="teal" /> },
        { faction: "Teladi Company", standing: <Badge relation="friendly" />, rep: <ProgressBar value={64} tone="teal" /> },
        { faction: "Holy Order", standing: <Badge relation="hostile" />, rep: <ProgressBar value={22} tone="amber" /> },
        { faction: "Xenon", standing: <Badge relation="atwar" />, rep: <ProgressBar value={4} tone="red" /> },
      ]}
    />
  </div>
);
