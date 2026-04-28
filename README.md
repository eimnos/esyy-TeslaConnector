# Esyy Tesla Connector

Sistema locale per leggere i dati di un inverter Afore (via Solarman LSW5), stimare il surplus fotovoltaico e preparare una gestione intelligente della ricarica Tesla in modo sicuro e progressivo.

## Obiettivo del progetto

Stato attuale (Wave 7 MVP):

- acquisizione locale dati inverter Afore/Solarman;
- mapping progressivo dei registri principali (PV/Grid);
- logica controller in modalita dry-run (senza comandi Tesla);
- scrittura best-effort su Supabase;
- dashboard web Next.js read-only per monitoraggio dati live, storico e grafici.

Le command Tesla reali restano volutamente disabilitate nelle wave correnti.

## Architettura (high level)

```text
Afore Inverter + Solarman LSW5 (LAN)
                |
                v
Controller locale Python (questa repo)
                |
                +--> Dry-run logic (attivo)
                +--> Supabase (attivo, best-effort)
                +--> Tesla Fleet API read-only (attivo)
                +--> Tesla commands (future waves)
                |
                v
Web Dashboard Next.js (web/, read-only)
```

## Requisiti

- Python 3.11+
- accesso LAN al collector (`192.168.1.20:8899`)
- Node.js 20+ (per la dashboard web)
- npm 10+

## Setup locale

1. Crea ed attiva un virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

2. Installa le dipendenze:

```powershell
pip install -r requirements.txt
```

3. Crea il file `.env` a partire dal template:

```powershell
Copy-Item .env.example .env
```

4. (Wave 6) Setup dashboard web:

```powershell
Copy-Item web/.env.example web/.env.local
cd web
npm install
npm run dev
```

La dashboard sara disponibile su `http://localhost:3000`.

## Esecuzione script

Lettura veloce dei primi registri dal collector:

```powershell
python -m src.read_afore --start 0 --count 100
```

Scansione registri con output CSV:

```powershell
python -m src.scan_afore_registers --start 0 --end 500 --block-size 50 --output data/afore_scan.csv
```

Simulazione logica di controllo senza Tesla API:

```powershell
python -m src.controller_dry_run --export-w 2200 --current-amps 0
```

Analisi differenze tra due scansioni registri:

```powershell
python -m src.analyze_register_changes data/scan_morning.csv data/scan_midday.csv --output data/diff_morning_midday.csv
```

## Test

```powershell
pytest
```

## Wave 2 - Register Mapping Procedure

Obiettivo Wave 2: identificare in modo affidabile i registri per PV Power, Grid Power, Load Power, Daily Production e Total Production.

1. Acquisire le scansioni in condizioni diverse (Tesla scollegata):

```powershell
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/scan_morning.csv
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/scan_midday.csv
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/scan_load_off.csv
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/scan_load_on.csv
```

2. Confrontare i file per vedere solo i registri che cambiano:

```powershell
python -m src.analyze_register_changes data/scan_morning.csv data/scan_midday.csv --left-label morning --right-label midday --output data/diff_morning_midday.csv
python -m src.analyze_register_changes data/scan_load_off.csv data/scan_load_on.csv --left-label load_off --right-label load_on --output data/diff_load_off_on.csv
```

3. Aggiornare `docs/afore_mapping.md` con:
- formula di conversione (es. signed int16/int32, scale x0.1 o x0.01);
- confronto con valore visto in app/inverter display;
- stato conferma finale.

Nota pratica:
- se i registri `holding` risultano troppo stabili, usare `--register-type input` per cercare la telemetria live.

## Wave 2B - Confirm Mapping Procedure

Obiettivo Wave 2B: confermare in modo piu robusto PV/Grid/Load e testare parsing signed32 sui registri adiacenti.

1. Baseline:

```powershell
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/confirm_baseline.csv
```

2. Carico noto ON (1.5-2.0 kW per almeno 2 minuti), poi scan:

```powershell
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/confirm_load_on.csv
```

3. Carico OFF, poi scan:

```powershell
python -m src.scan_afore_registers --register-type input --start 0 --end 1000 --block-size 50 --output data/confirm_load_off.csv
```

4. Diff registri variati + parsing sperimentale signed32:

```powershell
python -m src.analyze_register_changes data/confirm_load_off.csv data/confirm_load_on.csv --left-label load_off --right-label load_on --output data/diff_confirm_load.csv --signed32-pairs 524-525,526-527,528-529 --pairs-output data/diff_confirm_pairs.csv
```

## Wave 3 - Prudente Dry-Run Controller

Assunzioni provvisorie:
- Grid Power candidato: `524-525` (`int32 signed`)
- PV Power candidato: `560`
- Load Power: non confermato

Nuove variabili `.env` (con default in `.env.example`):

```text
AFORE_PV_POWER_REGISTER=560
AFORE_GRID_POWER_REGISTER_HIGH=524
AFORE_GRID_POWER_REGISTER_LOW=525
AFORE_GRID_POWER_SCALE=1
AFORE_PV_POWER_SCALE=1
AFORE_GRID_SIGN_MODE=unknown
```

Esecuzione loop dry-run (30 minuti, senza Tesla API):

```powershell
python -m src.controller_loop_dry_run --duration-minutes 30 --log-path data/controller_dry_run_log.csv
```

Smoke test rapido (1 ciclo):

```powershell
python -m src.controller_loop_dry_run --max-cycles 1 --interval-seconds 1
```

## Wave 5 Prep - Supabase opzionale

Per preparare la Wave 5 senza dipendere dal cloud:

- `SUPABASE_ENABLED=false` (default): il controller continua solo con log locale CSV.
- `SUPABASE_ENABLED=true` + credenziali valide: abilita write best-effort su Supabase.
- in caso di errore rete/auth/schema Supabase, il controller non si ferma.

Variabili `.env`:

```text
SUPABASE_ENABLED=false
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
```

Quando Supabase sara pronto:

```text
SUPABASE_ENABLED=true
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service-role-key>
```

## Wave 5A - Supabase Schema

Schema SQL idempotente disponibile in:

```text
db/schema.sql
```

Guida setup:

```text
docs/supabase_setup.md
```

Con `SUPABASE_ENABLED=true`, il controller dry-run prova a scrivere in:

- `inverter_samples`
- `controller_decisions`

in modalita best-effort (se Supabase fallisce, il loop continua).

Verifica connessione Supabase:

```powershell
python -m src.check_supabase_connection --insert-test-sample
```

## Wave 6 - Web Dashboard MVP

Dashboard Next.js in `web/`, solo lettura da Supabase:

- `/dashboard`: ultimo `inverter_sample`, ultima `controller_decision`, stato aggiornamento dati;
- `/history`: ultime 100 righe da `inverter_samples` e `controller_decisions`.

Variabili richieste (frontend):

```text
NEXT_PUBLIC_SUPABASE_URL=https://tygkqzhclglhfydtlxvi.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<publishable key>
```

Avvio locale:

```powershell
cd web
npm install
npm run dev
```

Note sicurezza frontend:

- usare solo `NEXT_PUBLIC_SUPABASE_ANON_KEY`;
- non usare mai `SUPABASE_SERVICE_ROLE_KEY` nel frontend;
- dashboard read-only, nessun comando Tesla e nessuna modifica configurazioni.

Deploy Vercel: vedi `docs/vercel_setup.md`.

## Wave 7 - Dashboard Enhancement MVP

Migliorie operative introdotte:

- refresh automatico dati configurabile (30s / 60s);
- badge stato dati (`OK`, `STALE`, `ERROR`);
- metriche live su `/dashboard`:
  - PV Power attuale;
  - Grid Import/Export attuale;
  - Target amps calcolato;
  - ultima decisione controller;
  - timestamp ultimo aggiornamento;
- grafici base su `/dashboard`:
  - PV Power nel tempo;
  - Grid Import/Export nel tempo;
  - Target amps nel tempo;
- filtri temporali su `/history`:
  - ultimi 30 min / 1h / 6h / 24h;
  - tabelle ordinate per `sample_timestamp` desc;
  - stati `loading`, `empty`, `error`.

Vincoli confermati:

- solo lettura Supabase;
- nessuna write da frontend;
- nessun comando Tesla.

## Sicurezza e limiti Wave 1

- Tesla commands non attivi.
- Nessun token/API secret hardcoded.
- Nessun comando reale inviato alla vettura.
- Tutta la logica di controllo resta locale.

## Struttura repository

```text
esyy-TeslaConnector/
|- README.md
|- .gitignore
|- .env.example
|- requirements.txt
|- docs/
|  |- architecture.md
|  |- waves.md
|  |- afore_mapping.md
|  |- tesla_api_strategy.md
|  |- tesla_api_setup.md
|  |- supabase_setup.md
|  `- vercel_setup.md
|- db/
|  `- schema.sql
|- src/
|  |- __init__.py
|  |- config.py
|  |- afore_reader.py
|  |- read_afore.py
|  |- scan_afore_registers.py
|  |- analyze_register_changes.py
|  |- solar_logic.py
|  |- controller_dry_run.py
|  |- controller_loop_dry_run.py
|  |- supabase_sink.py
|  `- check_supabase_connection.py
|- tests/
|  |- __init__.py
|  |- test_solar_logic.py
|  |- test_analyze_register_changes.py
|  |- test_afore_reader.py
|  |- test_tesla_client.py
|  |- test_supabase_sink.py
|  |- test_controller_loop_supabase.py
|  `- test_check_supabase_connection.py
`- web/
   |- app/
   |- lib/
   |- .env.example
   |- next.config.mjs
   `- package.json
`- data/
   `- .gitkeep
```
