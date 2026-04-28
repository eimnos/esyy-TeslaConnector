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

function getWindowStartIso(minutesBack) {
  if (!Number.isFinite(minutesBack) || minutesBack <= 0) {
    return null;
  }
  const nowMs = Date.now();
  return new Date(nowMs - minutesBack * 60 * 1000).toISOString();
}

async function queryRecent(tableName, options = {}) {
  const { limitCount = 100, minutesBack = null } = options;
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

  return Array.isArray(data) ? data : [];
}

export function getLatestInverterSample() {
  return queryLatest("inverter_samples");
}

export function getLatestControllerDecision() {
  return queryLatest("controller_decisions");
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
