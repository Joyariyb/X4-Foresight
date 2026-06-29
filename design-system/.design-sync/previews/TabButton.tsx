import { TabButton } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const row: React.CSSProperties = { display: 'flex', gap: '6px', flexWrap: 'wrap' };

export function TabRow() {
  return (
    <div style={bg}>
      <div style={row}>
        <TabButton active>Overview</TabButton>
        <TabButton>Fleet</TabButton>
        <TabButton>Stations</TabButton>
        <TabButton>Wares</TabButton>
        <TabButton>Factions</TabButton>
      </div>
    </div>
  );
}

export function States() {
  return (
    <div style={{ ...bg, ...row }}>
      <TabButton active>Active</TabButton>
      <TabButton>Inactive</TabButton>
    </div>
  );
}
