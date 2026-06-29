import { SectionHeader, SummaryCard } from "@x4-foresight/design-system";

export const Basic = () => (
  <div style={{ minWidth: 420 }}>
    <SectionHeader title="Empire Overview" />
  </div>
);

export const WithContent = () => (
  <div style={{ minWidth: 520 }}>
    <SectionHeader title="Economy" />
    <div className="x4-cards-row" style={{ marginTop: 4 }}>
      <SummaryCard label="Account Balance" value="12,480,650 Cr" icon="wallet" tone="teal" />
      <SummaryCard label="Net Profit / hr" value="+842,300 Cr" icon="trending-up" tone="green" />
    </div>
  </div>
);
