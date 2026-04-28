# Vercel Setup (Wave 6)

Questa guida descrive il deploy della dashboard Next.js (`/web`) in sola lettura.

## Prerequisiti

- progetto Supabase attivo;
- tabelle create (`inverter_samples`, `controller_decisions`);
- key pubblica Supabase (publishable/anon key), non service role.

## Variabili ambiente Vercel

Impostare nel progetto Vercel:

- `NEXT_PUBLIC_SUPABASE_URL=https://tygkqzhclglhfydtlxvi.supabase.co`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY=<publishable key>`

Non impostare nel frontend:

- `SUPABASE_SERVICE_ROLE_KEY`

## Deploy

1. Importare la repository su Vercel.
2. Impostare `Root Directory` su `web`.
3. Framework: `Next.js` (auto-detected).
4. Inserire le variabili ambiente sopra per `Production` (ed eventuale `Preview`).
5. Eseguire deploy.

## Verifiche post-deploy

1. Aprire `/dashboard` e controllare presenza di:
   - ultimo campione inverter;
   - ultima decisione controller;
   - stato aggiornamento dati.
2. Aprire `/history` e verificare le due tabelle (ultime 100 righe).
3. Controllare che non esistano feature di comando Tesla (solo read-only).

## Troubleshooting

- Errore "Missing NEXT_PUBLIC_SUPABASE_*":
  - variabili non configurate su Vercel o non presenti in `web/.env.local` in locale.
- Risposta vuota dalle tabelle:
  - il controller non ha ancora scritto dati recenti.
- Errore auth/permission:
  - verificare key pubblica corretta;
  - verificare policy RLS e privilegi di lettura per ruolo `anon`.
