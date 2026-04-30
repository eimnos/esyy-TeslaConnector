import { createClient } from "@supabase/supabase-js";

function getSupabaseEnv() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY in web/.env.local"
    );
  }

  return { url, anonKey };
}

export function getSupabaseEnvStatus() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;
  let urlHost = null;
  if (url) {
    try {
      urlHost = new URL(url).host;
    } catch (_error) {
      urlHost = "invalid-url";
    }
  }
  return {
    urlPresent: Boolean(url),
    anonKeyPresent: Boolean(anonKey),
    urlHost
  };
}

function createSupabaseReadClient() {
  const { url, anonKey } = getSupabaseEnv();
  return createClient(url, anonKey, {
    auth: {
      persistSession: false,
      autoRefreshToken: false
    }
  });
}

async function queryLatest(tableName) {
  const supabase = createSupabaseReadClient();
  const { data, error } = await supabase
    .from(tableName)
    .select("*")
    .order("sample_timestamp", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (error) {
    throw new Error(`${tableName} read failed: ${error.message}`);
  }
  return data;
}

async function queryLatestFiltered(
  tableName,
  { column, value, fallbackToLatest = false }
) {
  const supabase = createSupabaseReadClient();
  const { data, error } = await supabase
    .from(tableName)
    .select("*")
    .eq(column, value)
    .order("sample_timestamp", { ascending: false })
    .limit(1)
    .maybeSingle();

  if (!error) {
    return data;
  }

  if (fallbackToLatest) {
    return queryLatest(tableName);
  }

  throw new Error(`${tableName} filtered read failed: ${error.message}`);
}

function getWindowStartIso(minutesBack) {
  if (!Number.isFinite(minutesBack) || minutesBack <= 0) {
    return null;
  }
  const nowMs = Date.now();
  return new Date(nowMs - minutesBack * 60 * 1000).toISOString();
}

async function queryRecent(tableName, options = {}) {
  const { limitCount = 100, minutesBack = null, fallbackToLatest = true } = options;
  const supabase = createSupabaseReadClient();
  let query = supabase
    .from(tableName)
    .select("*")
    .order("sample_timestamp", { ascending: false })
    .limit(limitCount);

  const startIso = getWindowStartIso(minutesBack);
  if (startIso) {
    query = query.gte("sample_timestamp", startIso);
  }

  const { data, error } = await query;

  if (error) {
    throw new Error(`${tableName} read failed: ${error.message}`);
  }
  let rows = Array.isArray(data) ? data : [];

  if (rows.length === 0 && startIso && fallbackToLatest) {
    const { data: fallbackData, error: fallbackError } = await supabase
      .from(tableName)
      .select("*")
      .order("sample_timestamp", { ascending: false })
      .limit(limitCount);

    if (fallbackError) {
      throw new Error(`${tableName} fallback read failed: ${fallbackError.message}`);
    }

    rows = Array.isArray(fallbackData) ? fallbackData : [];
  }

  return rows;
}

export function getLatestInverterSample() {
  return queryLatest("inverter_samples");
}

export function getLatestControllerDecision() {
  return queryLatest("controller_decisions");
}

export function getLatestSimulatedControllerDecision() {
  return queryLatestFiltered("controller_decisions", {
    column: "simulated",
    value: true,
    fallbackToLatest: true
  });
}

export function getRecentInverterSamples(limitCount = 100, minutesBack = null) {
  return queryRecent("inverter_samples", { limitCount, minutesBack });
}

export function getRecentControllerDecisions(limitCount = 100, minutesBack = null) {
  return queryRecent("controller_decisions", { limitCount, minutesBack });
}

export function getLatestTeslaSample() {
  return queryLatest("tesla_samples");
}

export function getRecentTeslaSamples(limitCount = 100, minutesBack = null) {
  return queryRecent("tesla_samples", { limitCount, minutesBack });
}

export function getLatestAforeCandidateSample() {
  return queryLatest("afore_candidate_samples");
}

export function getRecentAforeCandidateSamples(limitCount = 300, minutesBack = null) {
  return queryRecent("afore_candidate_samples", { limitCount, minutesBack });
}
