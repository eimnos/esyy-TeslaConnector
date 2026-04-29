"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import { getRecentAforeCandidateSamples, getSupabaseEnvStatus } from "../../lib/supabase";

const RANGE_OPTIONS = [
  { label: "30 min", minutes: 30 },
  { label: "1 hour", minutes: 60 },
  { label: "6 hours", minutes: 360 },
  { label: "24 hours", minutes: 1440 }
];
const REFRESH_OPTIONS_SECONDS = [30, 60];
const DEFAULT_RANGE = 60;
const DEFAULT_REFRESH = 60;
const QUERY_LIMIT = 600;
const TABLE_LIMIT = 180;
const CHART_COLORS = ["#0f9d58", "#c95f3d", "#0f7c9d", "#d08e21", "#6d5bd0", "#226f54"];

function asNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatNumber(value) {
  const parsed = asNumber(value);
  if (parsed === null) {
    return "-";
  }
  return parsed.toLocaleString("en-US", { maximumFractionDigits: 3 });
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

function groupNameForRegister(registerName) {
  const value = String(registerName || "");
  if (value.startsWith("grid_")) {
    return "Grid";
  }
  if (value.startsWith("load_")) {
    return "Load";
  }
  if (value.startsWith("pv_")) {
    return "PV";
  }
  if (value.startsWith("meter_")) {
    return "Energy";
  }
  return "Other";
}

function getCandidateKey(row) {
  return `${row.register_name} | ${row.register_order} | scale=${row.scale}`;
}

function getDataBadgeState(latestTimestamp, errorMessage) {
  if (errorMessage) {
    return { label: "ERROR", tone: "pill-error", detail: errorMessage };
  }
  if (!latestTimestamp) {
    return { label: "STALE", tone: "pill-warn", detail: "No candidate samples available." };
  }

  const latestMs = new Date(latestTimestamp).getTime();
  if (Number.isNaN(latestMs)) {
    return { label: "ERROR", tone: "pill-error", detail: "Invalid candidate timestamp." };
  }

  const ageSeconds = Math.max(0, Math.floor((Date.now() - latestMs) / 1000));
  if (ageSeconds <= 120) {
    return { label: "OK", tone: "pill-ok", detail: `Data age: ${ageSeconds}s` };
  }
  return {
    label: "STALE",
    tone: "pill-warn",
    detail: `Data age: ${Math.floor(ageSeconds / 60)}m`
  };
}

function buildChartModel(rows, groupName) {
  const filtered = rows.filter((row) => groupNameForRegister(row.register_name) === groupName);
  const candidateKeys = [];
  for (const row of filtered) {
    const key = getCandidateKey(row);
    if (!candidateKeys.includes(key)) {
      candidateKeys.push(key);
    }
  }
  const selectedKeys = candidateKeys.slice(0, 6);
  const sampleMap = new Map();
  for (const row of [...filtered].reverse()) {
    const key = getCandidateKey(row);
    if (!selectedKeys.includes(key)) {
      continue;
    }
    const timestamp = row.sample_timestamp;
    if (!sampleMap.has(timestamp)) {
      sampleMap.set(timestamp, {
        label: formatChartTime(timestamp),
        timestamp
      });
    }
    sampleMap.get(timestamp)[key] = asNumber(row.value_w);
  }
  const series = Array.from(sampleMap.values()).sort((left, right) => {
    const leftMs = new Date(left.timestamp).getTime();
    const rightMs = new Date(right.timestamp).getTime();
    return leftMs - rightMs;
  });
  const hasData = series.some((point) =>
    selectedKeys.some((key) => point[key] !== null && point[key] !== undefined)
  );
  return { series, keys: selectedKeys, hasData };
}

export default function AforeCandidatesPage() {
  const envStatus = useMemo(() => getSupabaseEnvStatus(), []);
  const [rangeMinutes, setRangeMinutes] = useState(DEFAULT_RANGE);
  const [refreshSeconds, setRefreshSeconds] = useState(DEFAULT_REFRESH);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [queryStatus, setQueryStatus] = useState("idle");
  const [lastPollAt, setLastPollAt] = useState(null);

  const fetchRows = useCallback(
    async (isBackgroundRefresh = false) => {
      if (isBackgroundRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      try {
        const data = await getRecentAforeCandidateSamples(QUERY_LIMIT, rangeMinutes);
        const sorted = sortByTimestampDesc(Array.isArray(data) ? data : []);
        setRows(sorted);
        setErrorMessage(null);
        setQueryStatus("ok");
      } catch (error) {
        setErrorMessage(error instanceof Error ? error.message : String(error));
        setQueryStatus("error");
      } finally {
        setLastPollAt(new Date().toISOString());
        setLoading(false);
        setRefreshing(false);
      }
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

  const latestTimestamp = rows[0]?.sample_timestamp ?? null;
  const badgeState = getDataBadgeState(latestTimestamp, errorMessage);
  const latestCreatedAt = rows[0]?.created_at ?? null;
  const latestByCandidate = useMemo(() => {
    const latestMap = new Map();
    for (const row of rows) {
      const key = getCandidateKey(row);
      if (!latestMap.has(key)) {
        latestMap.set(key, row);
      }
    }
    return Array.from(latestMap.values());
  }, [rows]);

  const latestGrouped = useMemo(() => {
    const initial = {
      Grid: [],
      Load: [],
      PV: [],
      Energy: [],
      Other: []
    };
    for (const row of latestByCandidate) {
      const group = groupNameForRegister(row.register_name);
      initial[group].push(row);
    }
    return initial;
  }, [latestByCandidate]);

  const gridChart = useMemo(() => buildChartModel(rows, "Grid"), [rows]);
  const loadChart = useMemo(() => buildChartModel(rows, "Load"), [rows]);
  const pvChart = useMemo(() => buildChartModel(rows, "PV"), [rows]);
  const tableRows = rows.slice(0, TABLE_LIMIT);

  return (
    <section className="page-grid">
      <div className="section-header">
        <h1>Afore Candidates</h1>
        <p>
          Candidate/unconfirmed HA-Afore registers for manual comparison with Solarman Smart.
        </p>
      </div>

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>Data Status</h2>
          <span className={`pill ${badgeState.tone}`}>{badgeState.label}</span>
        </div>
        <p className="status-subtext">{badgeState.detail}</p>
        <div className="controls-row">
          <label className="control-field" htmlFor="candidate-range">
            Time range
            <select
              id="candidate-range"
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
          <label className="control-field" htmlFor="candidate-refresh">
            Refresh
            <select
              id="candidate-refresh"
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
          {loading ? "Loading candidate samples..." : `Last poll: ${formatTimestamp(lastPollAt)}`}
        </p>
      </article>

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>Diagnostics</h2>
          <span className={`pill ${queryStatus === "error" ? "pill-error" : "pill-ok"}`}>
            {queryStatus === "error" ? "QUERY ERROR" : "QUERY OK"}
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
            <strong>Rows loaded:</strong> {rows.length}
          </p>
          <p>
            <strong>Latest sample_timestamp:</strong> {formatTimestamp(latestTimestamp)}
          </p>
          <p>
            <strong>Latest created_at:</strong> {formatTimestamp(latestCreatedAt)}
          </p>
          <p>
            <strong>Latest candidate count:</strong> {latestByCandidate.length}
          </p>
          <p>
            <strong>Query status:</strong> {queryStatus}
          </p>
        </div>
        {errorMessage ? <p className="status-error">Supabase error: {errorMessage}</p> : null}
      </article>

      <section className="metric-grid">
        <article className="metric-card">
          <h3>Latest update</h3>
          <p className="metric-value">{formatTimestamp(latestTimestamp)}</p>
        </article>
        <article className="metric-card">
          <h3>Grid candidates</h3>
          <p className="metric-value">{latestGrouped.Grid.length}</p>
        </article>
        <article className="metric-card">
          <h3>Load candidates</h3>
          <p className="metric-value">{latestGrouped.Load.length}</p>
        </article>
        <article className="metric-card">
          <h3>PV candidates</h3>
          <p className="metric-value">{latestGrouped.PV.length}</p>
        </article>
      </section>

      <div className="card-grid">
        <article className="data-card">
          <h2>Latest Grid Candidates</h2>
          <dl>
            {latestGrouped.Grid.length === 0 ? (
              <div>
                <dt>status</dt>
                <dd>No rows</dd>
              </div>
            ) : (
              latestGrouped.Grid.slice(0, 8).map((row) => (
                <div key={`${row.id || row.sample_timestamp}-${getCandidateKey(row)}`}>
                  <dt>{getCandidateKey(row)}</dt>
                  <dd>
                    {formatNumber(row.value_w)} {row.unit}
                  </dd>
                </div>
              ))
            )}
          </dl>
        </article>

        <article className="data-card">
          <h2>Latest Load Candidates</h2>
          <dl>
            {latestGrouped.Load.length === 0 ? (
              <div>
                <dt>status</dt>
                <dd>No rows</dd>
              </div>
            ) : (
              latestGrouped.Load.slice(0, 8).map((row) => (
                <div key={`${row.id || row.sample_timestamp}-${getCandidateKey(row)}`}>
                  <dt>{getCandidateKey(row)}</dt>
                  <dd>
                    {formatNumber(row.value_w)} {row.unit}
                  </dd>
                </div>
              ))
            )}
          </dl>
        </article>

        <article className="data-card">
          <h2>Latest PV Candidates</h2>
          <dl>
            {latestGrouped.PV.length === 0 ? (
              <div>
                <dt>status</dt>
                <dd>No rows</dd>
              </div>
            ) : (
              latestGrouped.PV.slice(0, 8).map((row) => (
                <div key={`${row.id || row.sample_timestamp}-${getCandidateKey(row)}`}>
                  <dt>{getCandidateKey(row)}</dt>
                  <dd>
                    {formatNumber(row.value_w)} {row.unit}
                  </dd>
                </div>
              ))
            )}
          </dl>
        </article>
      </div>

      <section className="chart-grid">
        <article className="chart-card">
          <div className="status-header">
            <h2>Grid Candidates Over Time</h2>
            <span className="pill pill-warn">candidate / unconfirmed</span>
          </div>
          {gridChart.hasData ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={gridChart.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  {gridChart.keys.map((key, index) => (
                    <Line
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={CHART_COLORS[index % CHART_COLORS.length]}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No Grid candidate samples in selected range.</p>
          )}
        </article>

        <article className="chart-card">
          <div className="status-header">
            <h2>Load Candidates Over Time</h2>
            <span className="pill pill-warn">candidate / unconfirmed</span>
          </div>
          {loadChart.hasData ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={loadChart.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  {loadChart.keys.map((key, index) => (
                    <Line
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={CHART_COLORS[index % CHART_COLORS.length]}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No Load candidate samples in selected range.</p>
          )}
        </article>

        <article className="chart-card">
          <div className="status-header">
            <h2>PV Candidates Over Time</h2>
            <span className="pill pill-warn">candidate / unconfirmed</span>
          </div>
          {pvChart.hasData ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={pvChart.series}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  {pvChart.keys.map((key, index) => (
                    <Line
                      key={key}
                      type="monotone"
                      dataKey={key}
                      stroke={CHART_COLORS[index % CHART_COLORS.length]}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No PV candidate samples in selected range.</p>
          )}
        </article>
      </section>

      <article className="table-card">
        <h2>afore_candidate_samples (latest rows)</h2>
        <div className="table-wrapper">
          <table>
            <thead>
              <tr>
                <th>sample_timestamp</th>
                <th>register_name</th>
                <th>register_address</th>
                <th>register_order</th>
                <th>decoded_int32</th>
                <th>scale</th>
                <th>value</th>
                <th>unit</th>
                <th>status</th>
                <th>notes</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={10}>Loading candidate samples...</td>
                </tr>
              ) : tableRows.length === 0 ? (
                <tr>
                  <td colSpan={10}>No candidate samples in selected range.</td>
                </tr>
              ) : (
                tableRows.map((row) => (
                  <tr key={row.id ?? `${row.sample_timestamp}-${getCandidateKey(row)}`}>
                    <td>{formatTimestamp(row.sample_timestamp)}</td>
                    <td>{row.register_name ?? "-"}</td>
                    <td>{row.register_address ?? "-"}</td>
                    <td>{row.register_order ?? "-"}</td>
                    <td>{formatNumber(row.decoded_int32)}</td>
                    <td>{formatNumber(row.scale)}</td>
                    <td>{formatNumber(row.value_w)}</td>
                    <td>{row.unit ?? "-"}</td>
                    <td>
                      <span className="pill pill-warn">candidate</span>
                    </td>
                    <td>{row.notes ?? "-"}</td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </article>
    </section>
  );
}
