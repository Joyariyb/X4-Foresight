import { Tag } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const row: React.CSSProperties = { display: 'flex', flexWrap: 'wrap', gap: '6px' };

export function WareList() {
  return (
    <div style={bg}>
      <div style={row}>
        <Tag>Energy Cells</Tag>
        <Tag>Hull Parts</Tag>
        <Tag>Smart Chips</Tag>
        <Tag>Graphene</Tag>
        <Tag>Refined Metals</Tag>
        <Tag>Field Coils</Tag>
        <Tag>Antimatter Cells</Tag>
        <Tag>Microchips</Tag>
        <Tag>Engine Parts</Tag>
      </div>
    </div>
  );
}

export function Single() {
  return (
    <div style={bg}>
      <Tag>Energy Cells</Tag>
    </div>
  );
}
