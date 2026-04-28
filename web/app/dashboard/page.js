"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from "recharts";
import {
  getLatestControllerDecision,
  getLatestInverterSample,
  getRecentControllerDecisions,
  getRecentInverterSamples
} from "../../lib/supabase";

const REFRESH_OPTIONS_SECONDS = [30, 60];
const CHART_WINDOW_OPTIONS = [
  { label: "1h", minutes: 60 },
  { label: "6h", minutes: 360 },
  { label: "24h", minutes: 1440 }
];
const DEFAULT_REFRESH_SECONDS = 60;
const DEFAULT_WINDOW_MINUTES = 360;
const CHART_LIMIT = 400;

function asNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const parsed = Number(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatNumber(value, unit = "") {
  const parsed = asNumber(value);
  if (parsed === null) {
    return "-";
  }
  const suffix = unit ? ` ${unit}` : "";
  return `${parsed.toLocaleString("en-US", { maximumFractionDigits: 2 })}${suffix}`;
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

function newestTimestamp(...timestamps) {
  const valid = timestamps
    .map((value) => (value ? new Date(value).getTime() : Number.NaN))
    .filter((value) => !Number.isNaN(value));
  if (valid.length === 0) {
    return null;
  }
  return new Date(Math.max(...valid)).toISOString();
}

function getDataBadgeState(latestTimestamp, errorMessage) {
  if (errorMessage) {
    return { label: "ERROR", tone: "pill-error", detail: errorMessage };
  }

  if (!latestTimestamp) {
    return { label: "STALE", tone: "pill-warn", detail: "No recent samples available." };
  }

  const sampleMs = new Date(latestTimestamp).getTime();
  if (Number.isNaN(sampleMs)) {
    return { label: "ERROR", tone: "pill-error", detail: "Invalid sample timestamp." };
  }

  const ageSeconds = Math.max(0, Math.floor((Date.now() - sampleMs) / 1000));
  if (ageSeconds <= 120) {
    return { label: "OK", tone: "pill-ok", detail: `Data age: ${ageSeconds}s` };
  }

  if (ageSeconds <= 900) {
    return {
      label: "STALE",
      tone: "pill-warn",
      detail: `Data age: ${Math.floor(ageSeconds / 60)}m`
    };
  }

  return {
    label: "STALE",
    tone: "pill-warn",
    detail: `Data age: ${Math.floor(ageSeconds / 3600)}h`
  };
}

function metricValueClass(value) {
  return value === "-" ? "metric-value metric-empty" : "metric-value";
}

export default function DashboardPage() {
  const [refreshSeconds, setRefreshSeconds] = useState(DEFAULT_REFRESH_SECONDS);
  const [windowMinutes, setWindowMinutes] = useState(DEFAULT_WINDOW_MINUTES);
  const [inverterSample, setInverterSample] = useState(null);
  const [controllerDecision, setControllerDecision] = useState(null);
  const [inverterRows, setInverterRows] = useState([]);
  const [decisionRows, setDecisionRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [lastPollAt, setLastPollAt] = useState(null);

  const fetchData = useCallback(
    async (isBackgroundRefresh = false) => {
      if (isBackgroundRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      try {
        const [latestInverter, latestDecision, inverterHistory, decisionHistory] = await Promise.all([
          getLatestInverterSample(),
          getLatestControllerDecision(),
          getRecentInverterSamples(CHART_LIMIT, windowMinutes),
          getRecentControllerDecisions(CHART_LIMIT, windowMinutes)
        ]);

        setInverterSample(latestInverter);
        setControllerDecision(latestDecision);
        setInverterRows(Array.isArray(inverterHistory) ? inverterHistory : []);
        setDecisionRows(Array.isArray(decisionHistory) ? decisionHistory : []);
        setErrorMessage(null);
      } catch (error) {
        const readable = error instanceof Error ? error.message : "Unknown error while loading data.";
        setErrorMessage(readable);
      } finally {
        setLastPollAt(new Date().toISOString());
        setLoading(false);
        setRefreshing(false);
      }
    },
    [windowMinutes]
  );

  useEffect(() => {
    fetchData(false);
  }, [fetchData]);

  useEffect(() => {
    const intervalMs = refreshSeconds * 1000;
    const timerId = window.setInterval(() => {
      fetchData(true);
    }, intervalMs);

    return () => window.clearInterval(timerId);
  }, [fetchData, refreshSeconds]);

  const latestTimestamp = newestTimestamp(
    inverterSample?.sample_timestamp,
    controllerDecision?.sample_timestamp
  );
  const badgeState = getDataBadgeState(latestTimestamp, errorMessage);

  const pvValue = formatNumber(inverterSample?.pv_power_w, "W");
  const gridImportValue = formatNumber(inverterSample?.grid_import_w, "W");
  const gridExportValue = formatNumber(inverterSample?.grid_export_w, "W");
  const targetAmpsValue = formatNumber(controllerDecision?.target_amps, "A");
  const decisionValue = controllerDecision?.action ?? "-";
  const updatedAtValue = formatTimestamp(latestTimestamp);

  const pvSeries = useMemo(() => {
    return [...inverterRows].reverse().map((row) => ({
      label: formatChartTime(row.sample_timestamp),
      pvPower: asNumber(row.pv_power_w)
    }));
  }, [inverterRows]);

  const gridSeries = useMemo(() => {
    return [...inverterRows].reverse().map((row) => ({
      label: formatChartTime(row.sample_timestamp),
      gridImport: asNumber(row.grid_import_w),
      gridExport: asNumber(row.grid_export_w),
      gridRaw: asNumber(row.grid_power_raw_w)
    }));
  }, [inverterRows]);

  const ampsSeries = useMemo(() => {
    return [...decisionRows].reverse().map((row) => ({
      label: formatChartTime(row.sample_timestamp),
      targetAmps: asNumber(row.target_amps),
      exportW: asNumber(row.export_w)
    }));
  }, [decisionRows]);

  const hasPvSeries = pvSeries.some((item) => item.pvPower !== null);
  const hasGridSeries = gridSeries.some(
    (item) => item.gridImport !== null || item.gridExport !== null || item.gridRaw !== null
  );
  const hasAmpsSeries = ampsSeries.some((item) => item.targetAmps !== null);

  return (
    <section className="page-grid">
      <div className="section-header">
        <h1>Dashboard</h1>
        <p>Read-only live monitoring from Supabase with automatic refresh.</p>
      </div>

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>Data Status</h2>
          <span className={`pill ${badgeState.tone}`}>{badgeState.label}</span>
        </div>
        <p className="status-subtext">{badgeState.detail}</p>
        <div className="controls-row">
          <label className="control-field" htmlFor="refresh-interval">
            Refresh
            <select
              id="refresh-interval"
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
          <label className="control-field" htmlFor="chart-window">
            Chart window
            <select
              id="chart-window"
              value={windowMinutes}
              onChange={(event) => setWindowMinutes(Number(event.target.value))}
            >
              {CHART_WINDOW_OPTIONS.map((option) => (
                <option key={option.minutes} value={option.minutes}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            className="refresh-button"
            onClick={() => fetchData(true)}
            disabled={loading || refreshing}
          >
            {refreshing ? "Refreshing..." : "Refresh now"}
          </button>
        </div>
        <p className="status-meta">
          {loading ? "Loading data..." : `Last poll: ${formatTimestamp(lastPollAt)}`}
        </p>
      </article>

      <section className="metric-grid">
        <article className="metric-card">
          <h3>PV Power</h3>
          <p className={metricValueClass(pvValue)}>{pvValue}</p>
        </article>
        <article className="metric-card">
          <h3>Grid Import</h3>
          <p className={metricValueClass(gridImportValue)}>{gridImportValue}</p>
        </article>
        <article className="metric-card">
          <h3>Grid Export</h3>
          <p className={metricValueClass(gridExportValue)}>{gridExportValue}</p>
        </article>
        <article className="metric-card">
          <h3>Target Amps</h3>
          <p className={metricValueClass(targetAmpsValue)}>{targetAmpsValue}</p>
        </article>
        <article className="metric-card">
          <h3>Latest Decision</h3>
          <p className={metricValueClass(decisionValue)}>{decisionValue}</p>
        </article>
        <article className="metric-card">
          <h3>Last Update</h3>
          <p className={metricValueClass(updatedAtValue)}>{updatedAtValue}</p>
        </article>
      </section>

      <div className="card-grid">
        <article className="data-card">
          <h2>Latest Inverter Sample</h2>
          <dl>
            <div>
              <dt>Sample timestamp</dt>
              <dd>{formatTimestamp(inverterSample?.sample_timestamp)}</dd>
            </div>
            <div>
              <dt>PV power</dt>
              <dd>{formatNumber(inverterSample?.pv_power_w, "W")}</dd>
            </div>
            <div>
              <dt>Grid raw</dt>
              <dd>{formatNumber(inverterSample?.grid_power_raw_w, "W")}</dd>
            </div>
            <div>
              <dt>Grid import</dt>
              <dd>{formatNumber(inverterSample?.grid_import_w, "W")}</dd>
            </div>
            <div>
              <dt>Grid export</dt>
              <dd>{formatNumber(inverterSample?.grid_export_w, "W")}</dd>
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
              <dt>Export</dt>
              <dd>{formatNumber(controllerDecision?.export_w, "W")}</dd>
            </div>
            <div>
              <dt>Current amps before</dt>
              <dd>{formatNumber(controllerDecision?.current_amps_before, "A")}</dd>
            </div>
            <div>
              <dt>Target amps</dt>
              <dd>{formatNumber(controllerDecision?.target_amps, "A")}</dd>
            </div>
          </dl>
          <p className="note">{controllerDecision?.note ?? "No notes."}</p>
        </article>
      </div>

      <section className="chart-grid">
        <article className="chart-card">
          <h2>PV Power Over Time</h2>
          {hasPvSeries ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <AreaChart data={pvSeries}>
                  <defs>
                    <linearGradient id="pvFill" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#0f9d58" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#0f9d58" stopOpacity={0.04} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Area type="monotone" dataKey="pvPower" stroke="#0f9d58" fill="url(#pvFill)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No PV chart data in selected range.</p>
          )}
        </article>

        <article className="chart-card">
          <h2>Grid Import / Export Over Time</h2>
          {hasGridSeries ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={gridSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="gridImport" name="Grid Import (W)" stroke="#c95f3d" />
                  <Line type="monotone" dataKey="gridExport" name="Grid Export (W)" stroke="#0f7c9d" />
                  <Line type="monotone" dataKey="gridRaw" name="Grid Raw (W)" stroke="#6d5bd0" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No grid chart data in selected range.</p>
          )}
        </article>

        <article className="chart-card">
          <h2>Target Amps Over Time</h2>
          {hasAmpsSeries ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={ampsSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="targetAmps" name="Target Amps (A)" stroke="#d08e21" />
                  <Line type="monotone" dataKey="exportW" name="Export (W)" stroke="#4a5f8b" />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No target amps data in selected range.</p>
          )}
        </article>
      </section>
    </section>
  );
}
