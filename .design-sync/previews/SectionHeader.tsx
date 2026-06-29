import { SectionHeader } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };

export function Single() {
  return (
    <div style={bg}>
      <SectionHeader title="Fleet Overview" />
    </div>
  );
}

export function Multiple() {
  return (
    <div style={{ ...bg, display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <SectionHeader title="Active Ships" />
      <SectionHeader title="Stationed Vessels" />
      <SectionHeader title="Trade Routes" />
    </div>
  );
}
