# Esyy Tesla Connector

Sistema locale per leggere i dati di un inverter Afore (via Solarman LSW5), stimare il surplus fotovoltaico e preparare una gestione intelligente della ricarica Tesla in modo sicuro e progressivo.

## Obiettivo del progetto

Wave 1 e focalizzata su:

- lettura locale del collector Afore/Solarman in LAN;
- scansione registri per costruire una mappa dati affidabile;
- logica di surplus e decisioni in modalita dry-run (senza comandi reali).

Le integrazioni Tesla API, Supabase e dashboard web saranno introdotte nelle wave successive.

## Architettura (high level)

```text
Afore Inverter + Solarman LSW5 (LAN)
                |
                v
Controller locale Python (questa repo)
                |
                +--> Dry-run logic (Wave 1)
                +--> Supabase (future waves)
                +--> Tesla Fleet API (future waves)
                +--> Web Dashboard Next.js/Vercel (future waves)
```

## Requisiti

- Python 3.11+
- accesso LAN al collector (`192.168.1.20:8899`)

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

## Sicurezza e limiti Wave 1

- Tesla Fleet API non ancora attiva.
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
|  `- tesla_api_strategy.md
|- src/
|  |- __init__.py
|  |- config.py
|  |- read_afore.py
|  |- scan_afore_registers.py
|  |- analyze_register_changes.py
|  |- solar_logic.py
|  `- controller_dry_run.py
|- tests/
|  |- __init__.py
|  `- test_solar_logic.py
`- data/
   `- .gitkeep
```
