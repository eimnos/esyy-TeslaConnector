"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import {
  getSupabaseEnvStatus,
  getRecentControllerDecisions,
  getRecentInverterSamples,
  getRecentTeslaSamples
} from "../../lib/supabase";

const RANGE_OPTIONS = [
  { label: "30 min", minutes: 30 },
  { label: "1 hour", minutes: 60 },
  { label: "6 hours", minutes: 360 },
  { label: "24 hours", minutes: 1440 }
];
const REFRESH_OPTIONS_SECONDS = [30, 60];
const DEFAULT_RANGE = 60;
const DEFAULT_REFRESH = 60;
const TABLE_LIMIT = 100;

function formatNumber(value, digits = 2) {
  if (value === null || value === undefined) {
    return "-";
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric)) {
    return String(value);
  }
  return numeric.toLocaleString("en-US", { maximumFractionDigits: digits });
}

function asNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
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

function formatChartTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function sortByTimestampDesc(rows) {
  return [...rows].sort((left, right) => {
    const leftMs = new Date(left.sample_timestamp).getTime();
    const rightMs = new Date(right.sample_timestamp).getTime();
    return rightMs - leftMs;
  });
}

export default function HistoryPage() {
  const envStatus = useMemo(() => getSupabaseEnvStatus(), []);
  const [rangeMinutes, setRangeMinutes] = useState(DEFAULT_RANGE);
  const [refreshSeconds, setRefreshSeconds] = useState(DEFAULT_REFRESH);
  const [inverterRows, setInverterRows] = useState([]);
  const [decisionRows, setDecisionRows] = useState([]);
  const [teslaRows, setTeslaRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [queryStatus, setQueryStatus] = useState({
    inverter: "idle",
    decisions: "idle",
    tesla: "idle"
  });
  const [lastPollAt, setLastPollAt] = useState(null);

  const fetchRows = useCallback(
    async (isBackgroundRefresh = false) => {
      if (isBackgroundRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      const settled = await Promise.allSettled([
        getRecentInverterSamples(TABLE_LIMIT, rangeMinutes),
        getRecentControllerDecisions(TABLE_LIMIT, rangeMinutes),
        getRecentTeslaSamples(TABLE_LIMIT, rangeMinutes)
      ]);

      const nextStatus = { inverter: "ok", decisions: "ok", tesla: "ok" };
      const failures = [];

      if (settled[0].status === "fulfilled") {
        setInverterRows(sortByTimestampDesc(Array.isArray(settled[0].value) ? settled[0].value : []));
      } else {
        nextStatus.inverter = "error";
        failures.push(
          `inverter: ${
            settled[0].reason instanceof Error ? settled[0].reason.message : String(settled[0].reason)
          }`
        );
      }

      if (settled[1].status === "fulfilled") {
        setDecisionRows(sortByTimestampDesc(Array.isArray(settled[1].value) ? settled[1].value : []));
      } else {
        nextStatus.decisions = "error";
        failures.push(
          `decisions: ${
            settled[1].reason instanceof Error ? settled[1].reason.message : String(settled[1].reason)
          }`
        );
      }

      if (settled[2].status === "fulfilled") {
        setTeslaRows(sortByTimestampDesc(Array.isArray(settled[2].value) ? settled[2].value : []));
      } else {
        nextStatus.tesla = "error";
        failures.push(
          `tesla: ${
            settled[2].reason instanceof Error ? settled[2].reason.message : String(settled[2].reason)
          }`
        );
      }

      setQueryStatus(nextStatus);
      setErrorMessage(failures.length > 0 ? failures.join(" | ") : null);
      setLastPollAt(new Date().toISOString());
      setLoading(false);
      setRefreshing(false);
    },
    [rangeMinutes]
  );

  useEffect(() => {
    fetchRows(false);
  }, [fetchRows]);

  useEffect(() => {
    const timerId = window.setInterval(() => fetchRows(true), refreshSeconds * 1000);
    return () => window.clearInterval(timerId);
  }, [fetchRows, refreshSeconds]);

  const teslaSeries = useMemo(() => {
    return [...teslaRows].reverse().map((row) => ({
      label: formatChartTime(row.sample_timestamp),
      soc: asNumber(row.battery_level),
      requestedAmps: asNumber(row.charge_current_request),
      maxAmps: asNumber(row.charge_current_request_max)
    }));
  }, [teslaRows]);

  const hasTeslaSeries = teslaSeries.some(
    (point) => point.soc !== null || point.requestedAmps !== null || point.maxAmps !== null
  );
  const latestInverterCreatedAt = inverterRows[0]?.created_at ?? null;
  const latestDecisionCreatedAt = decisionRows[0]?.created_at ?? null;
  const latestTeslaCreatedAt = teslaRows[0]?.created_at ?? null;

  return (
    <section className="page-grid">
      <div className="section-header">
        <h1>History</h1>
        <p>Read-only logs from Supabase with time filters and automatic refresh.</p>
      </div>

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>History Filters</h2>
          {errorMessage ? <span className="pill pill-error">ERROR</span> : null}
        </div>
        <div className="controls-row">
          <label className="control-field" htmlFor="history-range">
            Time range
            <select
              id="history-range"
              value={rangeMinutes}
              onChange={(event) => setRangeMinutes(Number(event.target.value))}
            >
              {RANGE_OPTIONS.map((option) => (
                <option key={option.minutes} value={option.minutes}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <label className="control-field" htmlFor="history-refresh">
            Refresh
            <select
              id="history-refresh"
              value={refreshSeconds}
              onChange={(event) => setRefreshSeconds(Number(event.target.value))}
            >
              {REFRESH_OPTIONS_SECONDS.map((seconds) => (
                <option key={seconds} value={seconds}>
                  {seconds}s
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="refresh-button"
            onClick={() => fetchRows(true)}
            disabled={loading || refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh now"}
          </button>
        </div>
        <p className="status-meta">
          {loading ? "Loading history..." : `Last poll: ${formatTimestamp(lastPollAt)}`}
        </p>
        {errorMessage ? <p className="status-error">Error: {errorMessage}</p> : null}
      </article>

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>History Diagnostics</h2>
          <span className={`pill ${errorMessage ? "pill-error" : "pill-ok"}`}>
            {errorMessage ? "QUERY ERROR" : "QUERY OK"}
          </span>
        </div>
        <div className="diagnostic-grid">
          <p>
            <strong>Env URL present:</strong> {envStatus.urlPresent ? "yes" : "no"}
          </p>
          <p>
            <strong>Env anon key present:</strong> {envStatus.anonKeyPresent ? "yes" : "no"}
          </p>
          <p>
            <strong>Env host:</strong> {envStatus.urlHost ?? "-"}
          </p>
          <p>
            <strong>Inverter records:</strong> {inverterRows.length}
          </p>
          <p>
            <strong>Decision records:</strong> {decisionRows.length}
          </p>
          <p>
            <strong>Tesla records:</strong> {teslaRows.length}
          </p>
          <p>
            <strong>Latest inverter created_at:</strong> {formatTimestamp(latestInverterCreatedAt)}
          </p>
          <p>
            <strong>Latest decision created_at:</strong> {formatTimestamp(latestDecisionCreatedAt)}
          </p>
          <p>
            <strong>Latest tesla created_at:</strong> {formatTimestamp(latestTeslaCreatedAt)}
          </p>
          <p>
            <strong>Query status:</strong>{" "}
            {`inv=${queryStatus.inverter}, dec=${queryStatus.decisions}, tesla=${queryStatus.tesla}`}
          </p>
        </div>
      </article>

      <article className="chart-card">
        <h2>Tesla SOC / Ampere</h2>
        {loading ? (
          <p className="chart-empty">Loading Tesla chart...</p>
        ) : hasTeslaSeries ? (
          <div className="chart-body">
            <ResponsiveContainer width="100%" height={280}>
              <LineChart data={teslaSeries}>
                <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip />
                <Legend />
                <Line type="monotone" dataKey="soc" name="SOC (%)" stroke="#0f9d58" />
                <Line
                  type="monotone"
                  dataKey="requestedAmps"
                  name="Requested Amps (A)"
                  stroke="#c95f3d"
                />
                <Line type="monotone" dataKey="maxAmps" name="Max Amps (A)" stroke="#0f7c9d" />
              </LineChart>
            </ResponsiveContainer>
          </div>
        ) : (
          <p className="chart-empty">No Tesla samples in selected range.</p>
        )}
      </article>

      <div className="history-grid history-grid-wide">
        <article className="table-card">
          <h2>inverter_samples (latest 100)</h2>
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
                {loading ? (
                  <tr>
                    <td colSpan={6}>Loading inverter samples...</td>
                  </tr>
                ) : inverterRows.length === 0 ? (
                  <tr>
                    <td colSpan={6}>No inverter samples in selected range.</td>
                  </tr>
                ) : (
                  inverterRows.map((row) => (
                    <tr key={row.id}>
                      <td>{formatTimestamp(row.sample_timestamp)}</td>
                      <td>{formatNumber(row.pv_power_w)}</td>
                      <td>{formatNumber(row.grid_power_raw_w)}</td>
                      <td>{formatNumber(row.grid_import_w)}</td>
                      <td>{formatNumber(row.grid_export_w)}</td>
                      <td>{row.source ?? "-"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="table-card">
          <h2>controller_decisions (latest 100)</h2>
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
                {loading ? (
                  <tr>
                    <td colSpan={6}>Loading controller decisions...</td>
                  </tr>
                ) : decisionRows.length === 0 ? (
                  <tr>
                    <td colSpan={6}>No controller decisions in selected range.</td>
                  </tr>
                ) : (
                  decisionRows.map((row) => (
                    <tr key={row.id}>
                      <td>{formatTimestamp(row.sample_timestamp)}</td>
                      <td>{formatNumber(row.cycle, 0)}</td>
                      <td>{row.action ?? "-"}</td>
                      <td>{formatNumber(row.export_w)}</td>
                      <td>{formatNumber(row.target_amps, 0)}</td>
                      <td>{row.note ?? "-"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>

        <article className="table-card">
          <h2>tesla_samples (latest 100)</h2>
          <div className="table-wrapper">
            <table>
              <thead>
                <tr>
                  <th>sample_timestamp</th>
                  <th>vehicle_id</th>
                  <th>vehicle_state</th>
                  <th>battery_level</th>
                  <th>charging_state</th>
                  <th>req_amps</th>
                  <th>max_amps</th>
                  <th>charge_limit_soc</th>
                  <th>odometer_km</th>
                  <th>energy_added_kwh</th>
                  <th>source</th>
                </tr>
              </thead>
              <tbody>
                {loading ? (
                  <tr>
                    <td colSpan={11}>Loading Tesla samples...</td>
                  </tr>
                ) : teslaRows.length === 0 ? (
                  <tr>
                    <td colSpan={11}>No Tesla samples in selected range.</td>
                  </tr>
                ) : (
                  teslaRows.map((row) => (
                    <tr key={row.id}>
                      <td>{formatTimestamp(row.sample_timestamp)}</td>
                      <td>{row.vehicle_id ?? "-"}</td>
                      <td>{row.vehicle_state ?? "-"}</td>
                      <td>{formatNumber(row.battery_level)}</td>
                      <td>{row.charging_state ?? "-"}</td>
                      <td>{formatNumber(row.charge_current_request)}</td>
                      <td>{formatNumber(row.charge_current_request_max)}</td>
                      <td>{formatNumber(row.charge_limit_soc)}</td>
                      <td>{formatNumber(row.odometer_km)}</td>
                      <td>{formatNumber(row.energy_added_kwh)}</td>
                      <td>{row.source ?? "-"}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </article>
      </div>
    </section>
  );
}
