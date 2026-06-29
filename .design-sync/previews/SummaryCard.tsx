import { SummaryCard } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const grid2: React.CSSProperties = { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' };

export function KPIRow() {
  return (
    <div style={bg}>
      <div style={grid2}>
        <SummaryCard label="Account Balance" value="4 289 000 Cr" icon="coin" tone="teal" />
        <SummaryCard label="Active Ships" value="42" icon="rocket" tone="green" />
        <SummaryCard label="Hull Damage" value="3 ships" icon="shield" tone="amber" />
        <SummaryCard label="Losses This Cycle" value="2" icon="swords" tone="red" />
      </div>
    </div>
  );
}

export function Tones() {
  return (
    <div style={bg}>
      <div style={grid2}>
        <SummaryCard label="Default" value="186 412 Cr" />
        <SummaryCard label="Teal" value="186 412 Cr" tone="teal" />
        <SummaryCard label="Green" value="186 412 Cr" tone="green" />
        <SummaryCard label="Amber" value="186 412 Cr" tone="amber" />
        <SummaryCard label="Red" value="186 412 Cr" tone="red" />
      </div>
    </div>
  );
}
