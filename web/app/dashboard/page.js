import { getLatestControllerDecision, getLatestInverterSample } from "../../lib/supabase";

export const dynamic = "force-dynamic";
export const revalidate = 0;

function getFreshnessInfo(timestampValue) {
  if (!timestampValue) {
    return { label: "No sample yet", stale: true };
  }

  const nowMs = Date.now();
  const sampleMs = new Date(timestampValue).getTime();
  if (Number.isNaN(sampleMs)) {
    return { label: "Invalid timestamp", stale: true };
  }

  const diffSeconds = Math.max(0, Math.floor((nowMs - sampleMs) / 1000));
  if (diffSeconds <= 90) {
    return { label: `Updated ${diffSeconds}s ago`, stale: false };
  }
  if (diffSeconds <= 3600) {
    return { label: `Updated ${Math.floor(diffSeconds / 60)}m ago`, stale: true };
  }
  return { label: `Updated ${Math.floor(diffSeconds / 3600)}h ago`, stale: true };
}

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

export default async function DashboardPage() {
  let inverterSample = null;
  let controllerDecision = null;
  let loadError = null;

  try {
    [inverterSample, controllerDecision] = await Promise.all([
      getLatestInverterSample(),
      getLatestControllerDecision()
    ]);
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Unknown error";
  }

  const latestTimestamp =
    inverterSample?.sample_timestamp || controllerDecision?.sample_timestamp || null;
  const freshness = getFreshnessInfo(latestTimestamp);

  return (
    <section className="page-grid">
      <div className="section-header">
        <h1>Dashboard</h1>
        <p>Live read-only view of the latest Supabase samples.</p>
      </div>

      <article className="status-card">
        <h2>Data Connection</h2>
        {loadError ? (
          <p className="status-error">Error: {loadError}</p>
        ) : (
          <div className="status-row">
            <span className={`pill ${freshness.stale ? "pill-warn" : "pill-ok"}`}>
              {freshness.stale ? "STALE OR DELAYED" : "LIVE"}
            </span>
            <span>{freshness.label}</span>
          </div>
        )}
      </article>

      <div className="card-grid">
        <article className="data-card">
          <h2>Latest Inverter Sample</h2>
          <dl>
            <div>
              <dt>Sample timestamp</dt>
              <dd>{formatTimestamp(inverterSample?.sample_timestamp)}</dd>
            </div>
            <div>
              <dt>PV power (W)</dt>
              <dd>{formatNumber(inverterSample?.pv_power_w)}</dd>
            </div>
            <div>
              <dt>Grid raw (W)</dt>
              <dd>{formatNumber(inverterSample?.grid_power_raw_w)}</dd>
            </div>
            <div>
              <dt>Grid import (W)</dt>
              <dd>{formatNumber(inverterSample?.grid_import_w)}</dd>
            </div>
            <div>
              <dt>Grid export (W)</dt>
              <dd>{formatNumber(inverterSample?.grid_export_w)}</dd>
            </div>
            <div>
              <dt>Sign mode</dt>
              <dd>{inverterSample?.grid_sign_mode ?? "-"}</dd>
            </div>
          </dl>
        </article>

        <article className="data-card">
          <h2>Latest Controller Decision</h2>
          <dl>
            <div>
              <dt>Sample timestamp</dt>
              <dd>{formatTimestamp(controllerDecision?.sample_timestamp)}</dd>
            </div>
            <div>
              <dt>Cycle</dt>
              <dd>{formatNumber(controllerDecision?.cycle)}</dd>
            </div>
            <div>
              <dt>Action</dt>
              <dd>{controllerDecision?.action ?? "-"}</dd>
            </div>
            <div>
              <dt>Export (W)</dt>
              <dd>{formatNumber(controllerDecision?.export_w)}</dd>
            </div>
            <div>
              <dt>Current amps before</dt>
              <dd>{formatNumber(controllerDecision?.current_amps_before)}</dd>
            </div>
            <div>
              <dt>Target amps</dt>
              <dd>{formatNumber(controllerDecision?.target_amps)}</dd>
            </div>
          </dl>
          <p className="note">{controllerDecision?.note ?? "No notes."}</p>
        </article>
      </div>
    </section>
  );
}
