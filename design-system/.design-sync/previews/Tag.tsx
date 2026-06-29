import { Tag } from "@x4-foresight/design-system";

export const WareTags = () => (
  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, maxWidth: 360 }}>
    <Tag>Energy Cells</Tag>
    <Tag>Hull Parts</Tag>
    <Tag>Silicon Wafers</Tag>
    <Tag>Graphene</Tag>
    <Tag>Refined Metals</Tag>
    <Tag>Microchips</Tag>
    <Tag>Quantum Tubes</Tag>
  </div>
);

export const Single = () => <Tag>Energy Cells</Tag>;
