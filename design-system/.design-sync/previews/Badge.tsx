import { Badge } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const row: React.CSSProperties = { display: 'flex', gap: '8px', flexWrap: 'wrap' };

export function AllRelations() {
  return (
    <div style={bg}>
      <div style={row}>
        <Badge relation="allied" />
        <Badge relation="friendly" />
        <Badge relation="neutral" />
        <Badge relation="hostile" />
        <Badge relation="atwar" />
      </div>
    </div>
  );
}

export function CustomLabels() {
  return (
    <div style={bg}>
      <div style={row}>
        <Badge relation="allied">Argon Federation</Badge>
        <Badge relation="friendly">Teladi Company</Badge>
        <Badge relation="neutral">Paranid Empire</Badge>
        <Badge relation="hostile">Split Families</Badge>
        <Badge relation="atwar">Xenon</Badge>
      </div>
    </div>
  );
}
