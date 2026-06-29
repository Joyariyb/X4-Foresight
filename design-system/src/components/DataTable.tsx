import type { ReactNode } from "react";

export interface DataTableColumn {
  /** Column header label (rendered uppercase). */
  header: string;
  /** Key into each row object for this column's cell value. */
  field: string;
  /** Right-align and monospace the column (for numeric data). */
  numeric?: boolean;
}

export interface DataTableProps {
  /** Column definitions, in display order. */
  columns: DataTableColumn[];
  /** Row data — each row is a map of field → cell content. */
  rows: Array<Record<string, ReactNode>>;
}

/**
 * DataTable — the dense, hover-highlighting table used for fleets, stations,
 * and ware lists.
 *
 * Uppercase monospace headers, brand-green labels, and per-row hover. Mark a
 * column `numeric` to right-align it in the data font. Cell values are
 * arbitrary nodes, so Badges and ProgressBars can be embedded directly.
 * Drop inside a Panel for the standard framed look.
 */
export function DataTable({ columns, rows }: DataTableProps) {
  return (
    <table className="x4-table">
      <thead>
        <tr>
          {columns.map((col) => (
            <th key={col.field} className={col.numeric ? "x4-table__num" : undefined}>
              {col.header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i}>
            {columns.map((col) => (
              <td key={col.field} className={col.numeric ? "x4-table__num" : undefined}>
                {row[col.field]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
