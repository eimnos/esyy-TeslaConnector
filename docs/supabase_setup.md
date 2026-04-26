# Supabase Setup (Wave 5A)

## Obiettivo

Preparare Supabase per salvare:

- campioni inverter (`inverter_samples`)
- campioni Tesla (`tesla_samples`)
- decisioni controller (`controller_decisions`)
- impostazioni controller (`controller_settings`)

## 1. Creazione schema

1. Apri Supabase SQL Editor del progetto.
2. Copia il contenuto di `db/schema.sql`.
3. Esegui lo script.

Lo script e idempotente (`create table if not exists`, `create index if not exists`), quindi puo essere rieseguito senza errori di duplicazione.

## 2. Variabili ambiente

Aggiorna `.env`:

```text
SUPABASE_ENABLED=true
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

Per ambiente locale senza Supabase:

```text
SUPABASE_ENABLED=false
```

## 3. Comportamento runtime

Nel controller dry-run:

- se `SUPABASE_ENABLED=false`: scrive solo log CSV locale;
- se `SUPABASE_ENABLED=true` ma config incompleta: warning e fallback locale;
- se write Supabase fallisce: errore loggato ma loop continua (best-effort).

## 4. Test connessione

Verifica read/write di base:

```powershell
python -m src.check_supabase_connection
```

Verifica con inserimento test opzionale (`connection_test`):

```powershell
python -m src.check_supabase_connection --insert-test-sample
```

Se `SUPABASE_ENABLED=false` lo script termina con esito positivo senza errore (skip intenzionale).

## 5. Query SQL di verifica

```sql
select * from inverter_samples order by created_at desc limit 10;
select * from controller_decisions order by created_at desc limit 10;
```

## 6. Troubleshooting

- `SUPABASE_ENABLED=true` ma warning config mancante:
  - controlla `SUPABASE_URL` e `SUPABASE_SERVICE_ROLE_KEY` in `.env`.
- `401/403` su Supabase:
  - service role key errata/scaduta o progetto sbagliato.
- `404` su tabella:
  - schema non applicato o tabella con nome diverso.
- timeout/rete:
  - verifica connettivita internet/firewall e URL progetto.
- controller si deve sempre fermare? No:
  - in questo progetto la scrittura Supabase e best-effort, quindi il loop continua anche se Supabase fallisce.

## 7. RLS (stato attuale)

- In questa fase il controller usa `service_role` lato server.
- RLS va comunque pianificata prima di esporre endpoint client/public.
- Consiglio fase successiva:
  - abilitare RLS su tutte le tabelle;
  - creare policy specifiche per dashboard e ruoli applicativi;
  - mantenere `service_role` solo nei processi backend fidati.
