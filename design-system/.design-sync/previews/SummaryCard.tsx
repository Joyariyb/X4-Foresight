import { SummaryCard } from "@x4-foresight/design-system";

export const AccountBalance = () => (
  <SummaryCard label="Account Balance" value="12,480,650 Cr" icon="wallet" tone="teal" />
);

export const NetProfit = () => (
  <SummaryCard label="Net Profit / hr" value="+842,300 Cr" icon="trending-up" tone="green" />
);

export const StationsAtRisk = () => (
  <SummaryCard label="Stations Low on Wares" value="3 / 17" icon="building-factory-2" tone="amber" />
);

export const ShipsLost = () => (
  <SummaryCard label="Ships Lost (24h)" value="2" icon="ship" tone="red" />
);

export const SummaryStrip = () => (
  <div className="x4-cards-row" style={{ minWidth: 640 }}>
    <SummaryCard label="Account Balance" value="12,480,650 Cr" icon="wallet" tone="teal" />
    <SummaryCard label="Net Worth" value="48,902,110 Cr" icon="coin" />
    <SummaryCard label="Net Profit / hr" value="+842,300 Cr" icon="trending-up" tone="green" />
    <SummaryCard label="Stations Low" value="3 / 17" icon="building-factory-2" tone="amber" />
  </div>
);
