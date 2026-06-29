import { ProgressBar } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const col: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '10px' };
const row: React.CSSProperties = { display: 'flex', alignItems: 'center', gap: '10px' };
const label: React.CSSProperties = { fontFamily: 'var(--font-data)', fontSize: '11px', color: 'var(--text-secondary)', width: '90px' };
const value: React.CSSProperties = { fontFamily: 'var(--font-data)', fontSize: '11px', color: 'var(--text-dim)', minWidth: '32px', textAlign: 'right' };

export function RepVariant() {
  return (
    <div style={bg}>
      <div style={col}>
        {[
          { name: 'Argon Fed.', val: 92 },
          { name: 'Teladi Co.', val: 65 },
          { name: 'Paranid', val: 38 },
          { name: 'Split Fam.', val: 15 },
          { name: 'Boron', val: 0 },
        ].map(({ name, val }) => (
          <div key={name} style={row}>
            <span style={label}>{name}</span>
            <ProgressBar value={val} variant="rep" tone="teal" />
            <span style={value}>{val}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function HullVariant() {
  return (
    <div style={bg}>
      <div style={col}>
        {[
          { name: 'Full', val: 100 },
          { name: 'Damaged', val: 55 },
          { name: 'Critical', val: 18 },
          { name: 'Destroyed', val: 0 },
        ].map(({ name, val }) => (
          <div key={name} style={row}>
            <span style={label}>{name}</span>
            <ProgressBar value={val} variant="hull" tone="auto" />
            <span style={value}>{val}%</span>
          </div>
        ))}
      </div>
    </div>
  );
}

export function ToneVariants() {
  return (
    <div style={bg}>
      <div style={col}>
        {(['teal', 'green', 'amber', 'red'] as const).map(tone => (
          <div key={tone} style={row}>
            <span style={{ ...label, textTransform: 'capitalize' }}>{tone}</span>
            <ProgressBar value={65} variant="hull" tone={tone} />
          </div>
        ))}
      </div>
    </div>
  );
}
