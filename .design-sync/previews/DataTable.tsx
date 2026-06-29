import { DataTable, Badge, ProgressBar } from '@x4-foresight/design-system';
import type { DataTableColumn } from '@x4-foresight/design-system';

const bg: React.CSSProperties = { background: 'var(--surface-0)', padding: '16px' };

export function FleetTable() {
  const columns: DataTableColumn[] = [
    { header: 'Ship', field: 'name' },
    { header: 'Class', field: 'class' },
    { header: 'Faction', field: 'faction' },
    { header: 'Hull', field: 'hull' },
    { header: 'Location', field: 'location' },
    { header: 'Cargo', field: 'cargo', numeric: true },
  ];
  const rows = [
    { name: 'ARG Mjölnir', class: 'Destroyer', faction: <Badge relation="allied" />, hull: <ProgressBar value={87} variant="hull" tone="auto" />, location: "Hatikvah's Choice", cargo: '12 400' },
    { name: 'TEL Serpent', class: 'Freighter', faction: <Badge relation="friendly" />, hull: <ProgressBar value={32} variant="hull" tone="auto" />, location: 'Argon Prime', cargo: '4 200' },
    { name: 'PAR Kronos', class: 'Scout', faction: <Badge relation="neutral" />, hull: <ProgressBar value={95} variant="hull" tone="auto" />, location: 'Matrix #9', cargo: '0' },
    { name: 'SPL Mamba', class: 'Frigate', faction: <Badge relation="hostile" />, hull: <ProgressBar value={11} variant="hull" tone="auto" />, location: 'Ianamus Zura', cargo: '800' },
  ];
  return (
    <div style={bg}>
      <DataTable columns={columns} rows={rows} />
    </div>
  );
}

export function WareTable() {
  const columns: DataTableColumn[] = [
    { header: 'Ware', field: 'ware' },
    { header: 'Stock', field: 'stock', numeric: true },
    { header: 'Price', field: 'price', numeric: true },
    { header: 'Demand', field: 'demand', numeric: true },
  ];
  const rows = [
    { ware: 'Energy Cells', stock: '12 400', price: '14 Cr', demand: '840' },
    { ware: 'Hull Parts', stock: '2 100', price: '628 Cr', demand: '212' },
    { ware: 'Smart Chips', stock: '640', price: '1 450 Cr', demand: '88' },
    { ware: 'Graphene', stock: '8 800', price: '92 Cr', demand: '310' },
    { ware: 'Field Coils', stock: '200', price: '2 840 Cr', demand: '42' },
  ];
  return (
    <div style={bg}>
      <DataTable columns={columns} rows={rows} />
    </div>
  );
}
