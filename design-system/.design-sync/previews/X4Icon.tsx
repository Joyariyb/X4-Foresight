import { X4Icon } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const grid: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(5, 64px)', gap: '12px 8px' };
const item: React.CSSProperties = { display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '4px' };
const nameLabel: React.CSSProperties = { fontFamily: 'var(--font-data)', fontSize: '9px', color: 'var(--text-dim)', textAlign: 'center', lineHeight: 1.2 };

const ICONS = [
  'alert-triangle', 'building-factory', 'building-factory-2', 'building-warehouse',
  'chart-line', 'coin', 'cpu', 'database', 'flask', 'package',
  'planet', 'rocket', 'shield', 'ship', 'swords',
  'trending-down', 'trending-up', 'users', 'wallet', 'world',
];

export function CuratedSet() {
  return (
    <div style={bg}>
      <div style={grid}>
        {ICONS.map(name => (
          <div key={name} style={item}>
            <X4Icon name={name} size={18} color="var(--text-secondary)" />
            <span style={nameLabel}>{name}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function Sizes() {
  return (
    <div style={{ ...bg, display: 'flex', gap: '16px', alignItems: 'center' }}>
      <X4Icon name="rocket" size={12} color="var(--color-primary)" />
      <X4Icon name="rocket" size={16} color="var(--color-primary)" />
      <X4Icon name="rocket" size={20} color="var(--color-primary)" />
      <X4Icon name="rocket" size={24} color="var(--color-primary)" />
      <X4Icon name="rocket" size={32} color="var(--color-primary)" />
    </div>
  );
}

export function Colors() {
  return (
    <div style={{ ...bg, display: 'flex', gap: '16px', alignItems: 'center' }}>
      <X4Icon name="shield" size={20} color="var(--color-positive)" />
      <X4Icon name="alert-triangle" size={20} color="var(--color-warning)" />
      <X4Icon name="swords" size={20} color="var(--color-negative)" />
      <X4Icon name="planet" size={20} color="var(--color-primary)" />
      <X4Icon name="rocket" size={20} color="var(--color-special)" />
    </div>
  );
}
