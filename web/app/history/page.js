import { getRecentControllerDecisions, getRecentInverterSamples } from "../../lib/supabase";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function formatNumber(value) {
  if (value === null || value === undefined) {
    return "-";
  }
  const num = Number(value);
  if (Number.isNaN(num)) {
    return String(value);
  }
  return num.toLocaleString("en-US", { maximumFractionDigits: 2 });
}

function formatTimestamp(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return date.toLocaleString();
}

export default async function HistoryPage() {
  let inverterRows = [];
  let decisionRows = [];
  let loadError = null;

  try {
    [inverterRows, decisionRows] = await Promise.all([
      getRecentInverterSamples(100),
      getRecentControllerDecisions(100)
    ]);
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Unknown error";
  }

  return (
    <section className="page-grid">
      <div className="section-header">
        <h1>History</h1>
        <p>Latest 100 rows from inverter_samples and controller_decisions.</p>
      </div>

      {loadError ? <p className="status-error">Error: {loadError}</p> : null}

      <div className="history-grid">
        <article className="table-card">
          <h2>inverter_samples</h2>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>sample_timestamp</th>
                  <th>pv_power_w</th>
                  <th>grid_raw_w</th>
                  <th>grid_import_w</th>
                  <th>grid_export_w</th>
                  <th>source</th>
                </tr>
              </thead>
              <tbody>
                {inverterRows.map((row) => (
                  <tr key={row.id}>
                    <td>{formatTimestamp(row.sample_timestamp)}</td>
                    <td>{formatNumber(row.pv_power_w)}</td>
                    <td>{formatNumber(row.grid_power_raw_w)}</td>
                    <td>{formatNumber(row.grid_import_w)}</td>
                    <td>{formatNumber(row.grid_export_w)}</td>
                    <td>{row.source ?? "-"}</td>
                  </tr>
                ))}
                {inverterRows.length === 0 ? (
                  <tr>
                    <td colSpan={6}>No inverter samples available.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>

        <article className="table-card">
          <h2>controller_decisions</h2>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>sample_timestamp</th>
                  <th>cycle</th>
                  <th>action</th>
                  <th>export_w</th>
                  <th>target_amps</th>
                  <th>note</th>
                </tr>
              </thead>
              <tbody>
                {decisionRows.map((row) => (
                  <tr key={row.id}>
                    <td>{formatTimestamp(row.sample_timestamp)}</td>
                    <td>{formatNumber(row.cycle)}</td>
                    <td>{row.action ?? "-"}</td>
                    <td>{formatNumber(row.export_w)}</td>
                    <td>{formatNumber(row.target_amps)}</td>
                    <td>{row.note ?? "-"}</td>
                  </tr>
                ))}
                {decisionRows.length === 0 ? (
                  <tr>
                    <td colSpan={6}>No controller decisions available.</td>
                  </tr>
                ) : null}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  );
}
