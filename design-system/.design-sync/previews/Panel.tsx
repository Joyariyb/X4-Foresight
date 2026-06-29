import { Panel, DataTable, Tag, Badge } from "@x4-foresight/design-system";

export const StationPanel = () => (
  <div style={{ minWidth: 520 }}>
    <Panel title="Grand Exchange · Trading Station" headerExtra={<Badge relation="allied">Owned</Badge>}>
      <DataTable
        columns={[
          { header: "Ware", field: "ware" },
          { header: "Stock", field: "stock", numeric: true },
          { header: "Price", field: "price", numeric: true },
        ]}
        rows={[
          { ware: "Energy Cells", stock: "48,200", price: "16 Cr" },
          { ware: "Hull Parts", stock: "9,140", price: "242 Cr" },
          { ware: "Silicon Wafers", stock: "2,008", price: "311 Cr" },
        ]}
      />
    </Panel>
  </div>
);

export const WarePanel = () => (
  <div style={{ minWidth: 360 }}>
    <Panel title="Produced Wares" headerExtra="6">
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: 10 }}>
        <Tag>Energy Cells</Tag>
        <Tag>Hull Parts</Tag>
        <Tag>Silicon Wafers</Tag>
        <Tag>Graphene</Tag>
        <Tag>Refined Metals</Tag>
        <Tag>Microchips</Tag>
      </div>
    </Panel>
  </div>
);
