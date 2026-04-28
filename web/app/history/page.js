"use client";

import { useCallback, useEffect, useState } from "react";
import { getRecentControllerDecisions, getRecentInverterSamples } from "../../lib/supabase";

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

function sortByTimestampDesc(rows) {
  return [...rows].sort((left, right) => {
    const leftMs = new Date(left.sample_timestamp).getTime();
    const rightMs = new Date(right.sample_timestamp).getTime();
    return rightMs - leftMs;
  });
}

export default function HistoryPage() {
  const [rangeMinutes, setRangeMinutes] = useState(DEFAULT_RANGE);
  const [refreshSeconds, setRefreshSeconds] = useState(DEFAULT_REFRESH);
  const [inverterRows, setInverterRows] = useState([]);
  const [decisionRows, setDecisionRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [lastPollAt, setLastPollAt] = useState(null);

  const fetchRows = useCallback(
    async (isBackgroundRefresh = false) => {
      if (isBackgroundRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const [inverterResult, decisionsResult] = await Promise.all([
          getRecentInverterSamples(TABLE_LIMIT, rangeMinutes),
          getRecentControllerDecisions(TABLE_LIMIT, rangeMinutes)
        ]);

        setInverterRows(sortByTimestampDesc(Array.isArray(inverterResult) ? inverterResult : []));
        setDecisionRows(sortByTimestampDesc(Array.isArray(decisionsResult) ? decisionsResult : []));
        setErrorMessage(null);
      } catch (error) {
        const readable = error instanceof Error ? error.message : "Unknown error while loading history.";
        setErrorMessage(readable);
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

      <div className="history-grid">
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
      </div>
    </section>
  );
}
