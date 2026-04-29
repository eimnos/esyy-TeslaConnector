"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
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
  getSupabaseEnvStatus,
  getLatestControllerDecision,
  getLatestInverterSample,
  getLatestTeslaSample,
  getRecentControllerDecisions,
  getRecentInverterSamples,
  getRecentTeslaSamples
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
const GRID_RELIABILITY_LABEL = "UNCONFIRMED / UNRELIABLE";
const GRID_RELIABILITY_DETAIL =
  "Wave 9C: Grid Import/Export from Afore/Solarman is diagnostic only and not valid for automation.";

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
  const envStatus = useMemo(() => getSupabaseEnvStatus(), []);
  const [refreshSeconds, setRefreshSeconds] = useState(DEFAULT_REFRESH_SECONDS);
  const [windowMinutes, setWindowMinutes] = useState(DEFAULT_WINDOW_MINUTES);
  const [inverterSample, setInverterSample] = useState(null);
  const [controllerDecision, setControllerDecision] = useState(null);
  const [teslaSample, setTeslaSample] = useState(null);
  const [inverterRows, setInverterRows] = useState([]);
  const [decisionRows, setDecisionRows] = useState([]);
  const [teslaRows, setTeslaRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [errorMessage, setErrorMessage] = useState(null);
  const [queryStatus, setQueryStatus] = useState({
    latestInverter: "idle",
    latestDecision: "idle",
    latestTesla: "idle",
    historyInverter: "idle",
    historyDecision: "idle",
    historyTesla: "idle"
  });
  const [lastPollAt, setLastPollAt] = useState(null);

  const fetchData = useCallback(
    async (isBackgroundRefresh = false) => {
      if (isBackgroundRefresh) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }

      const resultKeys = [
        "latestInverter",
        "latestDecision",
        "latestTesla",
        "historyInverter",
        "historyDecision",
        "historyTesla"
      ];
      const settled = await Promise.allSettled([
        getLatestInverterSample(),
        getLatestControllerDecision(),
        getLatestTeslaSample(),
        getRecentInverterSamples(CHART_LIMIT, windowMinutes),
        getRecentControllerDecisions(CHART_LIMIT, windowMinutes),
        getRecentTeslaSamples(CHART_LIMIT, windowMinutes)
      ]);

      const nextStatus = {};
      const failures = [];
      settled.forEach((result, index) => {
        const key = resultKeys[index];
        if (result.status === "fulfilled") {
          nextStatus[key] = "ok";
        } else {
          nextStatus[key] = "error";
          const readable =
            result.reason instanceof Error
              ? result.reason.message
              : String(result.reason || "Unknown query error");
          failures.push(`${key}: ${readable}`);
        }
      });
      setQueryStatus(nextStatus);

      if (settled[0].status === "fulfilled") {
        setInverterSample(settled[0].value);
      }
      if (settled[1].status === "fulfilled") {
        setControllerDecision(settled[1].value);
      }
      if (settled[2].status === "fulfilled") {
        setTeslaSample(settled[2].value);
      }
      if (settled[3].status === "fulfilled") {
        setInverterRows(Array.isArray(settled[3].value) ? settled[3].value : []);
      }
      if (settled[4].status === "fulfilled") {
        setDecisionRows(Array.isArray(settled[4].value) ? settled[4].value : []);
      }
      if (settled[5].status === "fulfilled") {
        setTeslaRows(Array.isArray(settled[5].value) ? settled[5].value : []);
      }

      setErrorMessage(failures.length > 0 ? failures.join(" | ") : null);
      setLastPollAt(new Date().toISOString());
      setLoading(false);
      setRefreshing(false);
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
    controllerDecision?.sample_timestamp,
    teslaSample?.sample_timestamp
  );
  const badgeState = getDataBadgeState(latestTimestamp, errorMessage);

  const pvValue = formatNumber(inverterSample?.pv_power_w, "W");
  const gridImportValue = formatNumber(inverterSample?.grid_import_w, "W");
  const gridExportValue = formatNumber(inverterSample?.grid_export_w, "W");
  const targetAmpsValue = formatNumber(controllerDecision?.target_amps, "A");
  const decisionValue = controllerDecision?.action ?? "-";
  const updatedAtValue = formatTimestamp(latestTimestamp);
  const teslaSocValue = formatNumber(teslaSample?.battery_level, "%");
  const teslaChargingValue = teslaSample?.charging_state ?? "-";
  const teslaAmpsRequestValue =
    teslaSample?.charge_current_request !== null && teslaSample?.charge_current_request !== undefined
      ? `${formatNumber(teslaSample?.charge_current_request)} / ${formatNumber(
          teslaSample?.charge_current_request_max
        )} A`
      : "-";
  const teslaChargeLimitValue = formatNumber(teslaSample?.charge_limit_soc, "%");
  const teslaOdometerValue = formatNumber(teslaSample?.odometer_km, "km");

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

  const teslaSocSeries = useMemo(() => {
    return [...teslaRows].reverse().map((row) => ({
      label: formatChartTime(row.sample_timestamp),
      soc: asNumber(row.battery_level),
      requested: asNumber(row.charge_current_request)
    }));
  }, [teslaRows]);

  const hasPvSeries = pvSeries.some((item) => item.pvPower !== null);
  const hasGridSeries = gridSeries.some(
    (item) => item.gridImport !== null || item.gridExport !== null || item.gridRaw !== null
  );
  const hasAmpsSeries = ampsSeries.some((item) => item.targetAmps !== null);
  const hasTeslaSocSeries = teslaSocSeries.some(
    (item) => item.soc !== null || item.requested !== null
  );
  const latestInverterCreatedAt = inverterRows[0]?.created_at ?? inverterSample?.created_at ?? null;
  const latestDecisionCreatedAt =
    decisionRows[0]?.created_at ?? controllerDecision?.created_at ?? null;
  const latestTeslaCreatedAt = teslaRows[0]?.created_at ?? teslaSample?.created_at ?? null;

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

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>Grid Reliability</h2>
          <span className="pill pill-warn">{GRID_RELIABILITY_LABEL}</span>
        </div>
        <p className="status-subtext">{GRID_RELIABILITY_DETAIL}</p>
        <p className="status-meta">
          Candidate remapping view: <Link href="/afore-candidates">/afore-candidates</Link>
        </p>
      </article>

      <article className="status-card controls-card">
        <div className="status-header">
          <h2>Dashboard Diagnostics</h2>
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
            <strong>Controller records:</strong> {decisionRows.length}
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
            {`inv_latest=${queryStatus.latestInverter}, inv_hist=${queryStatus.historyInverter}, dec_latest=${queryStatus.latestDecision}, dec_hist=${queryStatus.historyDecision}, tes_latest=${queryStatus.latestTesla}, tes_hist=${queryStatus.historyTesla}`}
          </p>
        </div>
        {errorMessage ? <p className="status-error">Supabase error: {errorMessage}</p> : null}
      </article>

      <section className="metric-grid">
        <article className="metric-card">
          <h3>PV Power</h3>
          <p className={metricValueClass(pvValue)}>{pvValue}</p>
        </article>
        <article className="metric-card">
          <h3>Grid Import (unreliable)</h3>
          <p className={metricValueClass(gridImportValue)}>{gridImportValue}</p>
        </article>
        <article className="metric-card">
          <h3>Grid Export (unreliable)</h3>
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
        <article className="metric-card">
          <h3>Tesla SOC</h3>
          <p className={metricValueClass(teslaSocValue)}>{teslaSocValue}</p>
        </article>
        <article className="metric-card">
          <h3>Tesla Charging</h3>
          <p className={metricValueClass(teslaChargingValue)}>{teslaChargingValue}</p>
        </article>
        <article className="metric-card">
          <h3>Tesla Req/Max</h3>
          <p className={metricValueClass(teslaAmpsRequestValue)}>{teslaAmpsRequestValue}</p>
        </article>
        <article className="metric-card">
          <h3>Tesla Limit</h3>
          <p className={metricValueClass(teslaChargeLimitValue)}>{teslaChargeLimitValue}</p>
        </article>
        <article className="metric-card">
          <h3>Tesla Odometer</h3>
          <p className={metricValueClass(teslaOdometerValue)}>{teslaOdometerValue}</p>
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
              <dt>Grid import (unreliable)</dt>
              <dd>{formatNumber(inverterSample?.grid_import_w, "W")}</dd>
            </div>
            <div>
              <dt>Grid export (unreliable)</dt>
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
              <dt>Export (unreliable)</dt>
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

        <article className="data-card">
          <h2>Latest Tesla Sample</h2>
          <dl>
            <div>
              <dt>Sample timestamp</dt>
              <dd>{formatTimestamp(teslaSample?.sample_timestamp)}</dd>
            </div>
            <div>
              <dt>Vehicle ID</dt>
              <dd>{teslaSample?.vehicle_id ?? "-"}</dd>
            </div>
            <div>
              <dt>Vehicle state</dt>
              <dd>{teslaSample?.vehicle_state ?? "-"}</dd>
            </div>
            <div>
              <dt>Battery level</dt>
              <dd>{formatNumber(teslaSample?.battery_level, "%")}</dd>
            </div>
            <div>
              <dt>Charging state</dt>
              <dd>{teslaSample?.charging_state ?? "-"}</dd>
            </div>
            <div>
              <dt>Ampere richiesti</dt>
              <dd>{formatNumber(teslaSample?.charge_current_request, "A")}</dd>
            </div>
            <div>
              <dt>Ampere max</dt>
              <dd>{formatNumber(teslaSample?.charge_current_request_max, "A")}</dd>
            </div>
            <div>
              <dt>Charge limit</dt>
              <dd>{formatNumber(teslaSample?.charge_limit_soc, "%")}</dd>
            </div>
            <div>
              <dt>Odometer</dt>
              <dd>{formatNumber(teslaSample?.odometer_km, "km")}</dd>
            </div>
            <div>
              <dt>Energy added</dt>
              <dd>{formatNumber(teslaSample?.energy_added_kwh, "kWh")}</dd>
            </div>
          </dl>
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
          <h2>Grid Import / Export Over Time (unreliable)</h2>
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
            <p className="chart-empty">No grid chart data in selected range (diagnostic feed only).</p>
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

        <article className="chart-card">
          <h2>Tesla SOC / Requested Amps</h2>
          {hasTeslaSocSeries ? (
            <div className="chart-body">
              <ResponsiveContainer width="100%" height={280}>
                <LineChart data={teslaSocSeries}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#d8e6dc" />
                  <XAxis dataKey="label" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Line type="monotone" dataKey="soc" name="SOC (%)" stroke="#0f9d58" />
                  <Line
                    type="monotone"
                    dataKey="requested"
                    name="Requested Amps (A)"
                    stroke="#c95f3d"
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <p className="chart-empty">No Tesla chart data in selected range.</p>
          )}
        </article>
      </section>
    </section>
  );
}
