# Tesla API Setup (Wave 4 - Read-Only)

## Scopo Wave 4

In questa wave integriamo solo lettura stato veicolo via Tesla Fleet API.

Guardrail attivi:

- nessun comando veicolo;
- nessun wake-up automatico;
- token solo da `.env`;
- polling cost-aware;
- log chiamate API.

## Prerequisiti

- account Tesla Developer;
- una app registrata nel portale Tesla Developer;
- credenziali OAuth e token validi.

## Come creare app Tesla Developer (high level)

1. Accedi al portale Tesla Developer con il tuo account.
2. Crea una nuova app Fleet API.
3. Configura i redirect URI richiesti dal flusso OAuth.
4. Ottieni `client_id` e `client_secret`.
5. Completa il flusso OAuth e recupera:
   - `access_token`
   - `refresh_token`
6. Identifica il `vehicle_id` del veicolo target.

Nota:
- non inserire segreti nel codice;
- usare sempre variabili ambiente.

## Variabili `.env`

```text
TESLA_CLIENT_ID=
TESLA_CLIENT_SECRET=
TESLA_ACCESS_TOKEN=
TESLA_REFRESH_TOKEN=
TESLA_VEHICLE_ID=
TESLA_API_BASE_URL=https://fleet-api.prd.eu.vn.cloud.tesla.com
TESLA_READONLY_POLL_SECONDS=600
TESLA_ALLOW_WAKE_UP=false
TESLA_COMMANDS_ENABLED=false
```

Significato principale:

- `TESLA_READONLY_POLL_SECONDS`: intervallo polling read-only (default 600s).
- `TESLA_ALLOW_WAKE_UP=false`: blocca policy di risveglio automatico.
- `TESLA_COMMANDS_ENABLED=false`: comandi disabilitati in questa wave.

## Esecuzione read-only

Snapshot singolo:

```powershell
python -m src.tesla_readonly_status --output-json data/tesla_status_sample.json
```

Polling periodico (cost-aware):

```powershell
python -m src.tesla_readonly_status --watch --iterations 6
```

Log chiamate API:

- `data/tesla_api_calls_log.csv`

## Strategia anti-costo

- evitare polling continuo;
- evitare wake-up automatico;
- usare polling 10-15 minuti quando idle;
- usare polling 30-60 secondi solo durante carica (wave futura);
- mantenere comandi disabilitati in questa wave.

## Limiti Wave 4

- refresh token flow solo predisposto a livello config, non ancora automatizzato;
- nessuna integrazione comandi (`set_amps`, `start`, `stop`, `wake`) nel codice.
