import { Alert } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };
const col: React.CSSProperties = { display: 'flex', flexDirection: 'column', gap: '8px' };

export function AllTones() {
  return (
    <div style={bg}>
      <div style={col}>
        <Alert tone="red">Capital ship destroyed: ARG Mjölnir lost near Hatikvah&apos;s Choice</Alert>
        <Alert tone="amber">Hull integrity critical: TEL Serpent at 12% — return to dock</Alert>
        <Alert tone="green">Trade route established: Energy Cells +840 Cr/cycle</Alert>
      </div>
    </div>
  );
}

export function CustomIcons() {
  return (
    <div style={bg}>
      <div style={col}>
        <Alert tone="amber" icon="package">Argon Energy Cells stock below minimum threshold (120 / 500 units)</Alert>
        <Alert tone="red" icon="swords">War declared: Xenon offensive detected in Grand Exchange sector</Alert>
        <Alert tone="green" icon="trending-up">Station profit up 18% vs last cycle — Microchips margin improved</Alert>
      </div>
    </div>
  );
}
