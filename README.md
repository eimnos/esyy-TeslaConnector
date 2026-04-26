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

## Test

```powershell
pytest
```

## Sicurezza e limiti Wave 1

- Tesla Fleet API non ancora attiva.
- Nessun token/API secret hardcoded.
- Nessun comando reale inviato alla vettura.
- Tutta la logica di controllo resta locale.

## Struttura repository

```text
esyy-TeslaConnector/
├─ README.md
├─ .gitignore
├─ .env.example
├─ requirements.txt
├─ docs/
│  ├─ architecture.md
│  ├─ waves.md
│  ├─ afore_mapping.md
│  └─ tesla_api_strategy.md
├─ src/
│  ├─ __init__.py
│  ├─ config.py
│  ├─ read_afore.py
│  ├─ scan_afore_registers.py
│  ├─ solar_logic.py
│  └─ controller_dry_run.py
├─ tests/
│  ├─ __init__.py
│  └─ test_solar_logic.py
└─ data/
   └─ .gitkeep
```
