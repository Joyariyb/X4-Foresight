import { Panel, DataTable, Tag, Badge } from '@x4-foresight/design-system';
import type { DataTableColumn } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };

export function WithDataTable() {
  const columns: DataTableColumn[] = [
    { header: 'Station', field: 'name' },
    { header: 'Sector', field: 'sector' },
    { header: 'Relation', field: 'relation' },
    { header: 'Value', field: 'value', numeric: true },
  ];
  const rows = [
    { name: 'Getsu Fune Mining', sector: 'Getsu Fune', relation: <Badge relation="allied" />, value: '42 000 000 Cr' },
    { name: "Hatikvah's Trade", sector: "Hatikvah's Choice", relation: <Badge relation="friendly" />, value: '18 200 000 Cr' },
    { name: 'Matrix #9 Fab', sector: 'Matrix #9', relation: <Badge relation="neutral" />, value: '8 600 000 Cr' },
  ];
  return (
    <div style={bg}>
      <Panel title="Stations" headerExtra="3 stations">
        <DataTable columns={columns} rows={rows} />
      </Panel>
    </div>
  );
}

export function WithWareTags() {
  return (
    <div style={bg}>
      <Panel title="Wares Traded" headerExtra="7 wares">
        <div style={{ padding: '10px 12px', display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          <Tag>Energy Cells</Tag>
          <Tag>Hull Parts</Tag>
          <Tag>Smart Chips</Tag>
          <Tag>Graphene</Tag>
          <Tag>Refined Metals</Tag>
          <Tag>Field Coils</Tag>
          <Tag>Antimatter Cells</Tag>
        </div>
      </Panel>
    </div>
  );
}

export function Basic() {
  return (
    <div style={bg}>
      <Panel title="Empire Summary">
        <div style={{ padding: '12px', fontFamily: 'var(--font-data)', fontSize: '12px', color: 'var(--text-secondary)' }}>
          42 ships · 3 stations · 7 trade routes active
        </div>
      </Panel>
    </div>
  );
}
