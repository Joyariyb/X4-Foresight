import { Badge } from "@x4-foresight/design-system";

export const AllRelations = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
    <Badge relation="allied" />
    <Badge relation="friendly" />
    <Badge relation="neutral" />
    <Badge relation="hostile" />
    <Badge relation="atwar" />
  </div>
);

export const FactionRow = () => (
  <div style={{ display: "flex", gap: 8, flexWrap: "wrap", alignItems: "center" }}>
    <Badge relation="allied">Argon Federation</Badge>
    <Badge relation="friendly">Teladi Company</Badge>
    <Badge relation="neutral">Paranid</Badge>
    <Badge relation="hostile">Holy Order</Badge>
    <Badge relation="atwar">Xenon</Badge>
  </div>
);
