# Tesla API Setup (Wave 4 + Wave 9A Readiness)

## Scopo

Stato attuale del progetto:

- Wave 4/8: integrazione Tesla solo in lettura (read-only).
- Wave 9A: preparazione wrapper comandi, ma con protezioni hard e default bloccato.

## Guardrail attivi

- nessun comando automatico dal controller;
- nessun wake-up automatico;
- token solo da `.env` locale;
- refresh automatico access token con token store locale (Wave 11A.1);
- polling cost-aware;
- logging chiamate API;
- comandi Tesla bloccati di default (`TESLA_COMMANDS_ENABLED=false`);
- policy interna: comandi bloccati finche `Grid Power` non e `confirmed`.

## Prerequisiti base Fleet API

1. Account Tesla Developer con MFA abilitata.
2. Applicazione creata nel portale Tesla Developer.
3. OAuth configurato (authorization code flow) con redirect URI validi.
4. Token validi:
   - `access_token`
   - `refresh_token`
5. `vehicle_id` del veicolo target.

## Prerequisiti Vehicle Commands / Virtual Key

Per eseguire comandi veicolo servono prerequisiti aggiuntivi rispetto al solo read-only:

1. Generare key pair EC `prime256v1` (public/private key).
2. Ospitare la public key su:
   - `https://<developer-domain>/.well-known/appspecific/com.tesla.3p.public-key.pem`
3. Chiamare `POST /api/1/partner_accounts` (register) con partner token, usando un dominio coerente con `allowed_origins`.
4. Pairing della virtual key sul veicolo (deep link Tesla app):
   - `https://tesla.com/_ak/<developer-domain>`
5. Verificare stato pairing key e prerequisiti veicolo tramite endpoint `fleet_status`.
6. Usare scope OAuth adeguati (almeno `vehicle_cmds` e `vehicle_charging_cmds` per i comandi di ricarica).

## Variabili `.env`

```text
TESLA_CLIENT_ID=
TESLA_CLIENT_SECRET=
TESLA_ACCESS_TOKEN=
TESLA_REFRESH_TOKEN=
TESLA_VEHICLE_ID=
TESLA_API_BASE_URL=https://fleet-api.prd.eu.vn.cloud.tesla.com
TESLA_AUTH_BASE_URL=https://auth.tesla.com/oauth2/v3
TESLA_API_VERIFY_TLS=true
TESLA_READONLY_POLL_SECONDS=600
TESLA_TOKEN_STORE_PATH=data/tesla_token_store.json
TESLA_TOKEN_REFRESH_LEEWAY_SECONDS=120
TESLA_ALLOW_WAKE_UP=false
TESLA_COMMANDS_ENABLED=false
```

Note sicurezza:

- `TESLA_CLIENT_SECRET`, `TESLA_ACCESS_TOKEN` e `TESLA_REFRESH_TOKEN` non vanno mai committati.
- `.env` deve restare untracked.
- il token store locale `data/tesla_token_store.json` non va committato.
- non usare `SUPABASE_SERVICE_ROLE_KEY` nel frontend web.
- lasciare `TESLA_API_VERIFY_TLS=true` in produzione; impostarlo a `false` solo per test locali con proxy HTTPS self-signed.

## Wave 11A.1 - Auto Refresh Token

Da Wave 11A.1 il client read-only Tesla esegue refresh OAuth automatico:

- prima delle chiamate, se `expires_at` e vicino alla scadenza (`TESLA_TOKEN_REFRESH_LEEWAY_SECONDS`);
- su errore `401`, tenta un solo refresh e ritenta una sola volta la chiamata.

Store locale (gitignored):

- `data/tesla_token_store.json`
- campi: `access_token`, `refresh_token`, `expires_at`, `updated_at`

Nota importante su Tesla refresh token:

- il `refresh_token` e trattato come single-use;
- ad ogni refresh viene salvato atomicamente il nuovo `refresh_token` restituito;
- se refresh fallisce o il token e invalidato, il client alza:
  - `Tesla re-authorization required`
  - in quel caso serve rifare manualmente l'authorization code flow.

Utility CLI:

```powershell
py -m src.tesla_token_manager --status
py -m src.tesla_token_manager --refresh-now
```

## Read-only (attivo)

Snapshot singolo:

```powershell
python -m src.tesla_readonly_status --output-json data/tesla_status_sample.json
```

Polling periodico:

```powershell
python -m src.tesla_readonly_status --watch --iterations 6
```

Log chiamate API read-only:

- `data/tesla_api_calls_log.csv`

## Wave 9A - Command Readiness (safe mode)

Modulo preparato:

- `src/tesla_commands.py`

Wrapper disponibili (manual-only):

- `set_charge_amps`
- `start_charge`
- `stop_charge`

Regole hard del wrapper:

1. rifiuta se `TESLA_COMMANDS_ENABLED=false`;
2. richiede flag esplicito per singolo comando (`allow_command=True`);
3. rifiuta se `grid_status` non e `confirmed` (es. `unknown` / `partial`);
4. supporta dry-run (`dry_run=True`) senza chiamata API;
5. logga ogni tentativo su `data/tesla_command_calls_log.csv`.

Esempio (dry-run esplicito, nessuna chiamata reale):

```python
from src.tesla_commands import create_tesla_command_client, set_charge_amps

client = create_tesla_command_client()
result = set_charge_amps(
    client,
    8,
    allow_command=True,
    dry_run=True,
    grid_status="confirmed",
)
print(result)
client.close()
```

## Wave 10A - Manual Command Smoke Test

Script manuale:

- `src/tesla_manual_command.py`

Vincoli di sicurezza applicati:

- richiede sempre `--i-understand-this-sends-real-command`;
- nessun comando automatico;
- nessun wake-up (`TESLA_ALLOW_WAKE_UP` deve restare `false`);
- comando bloccato se `grid_status` non e `confirmed`;
- log obbligatorio su `data/tesla_command_calls_log.csv`.

Esempio dry-run consigliato:

```powershell
py -m src.tesla_manual_command --set-amps 6 --dry-run --i-understand-this-sends-real-command
```

Esempi manuali (reali, solo quando sicuro):

```powershell
py -m src.tesla_manual_command --set-amps 6 --i-understand-this-sends-real-command
py -m src.tesla_manual_command --start-charge --i-understand-this-sends-real-command
py -m src.tesla_manual_command --stop-charge --i-understand-this-sends-real-command
```

### Esito validazione operativa Wave 10A (2026-04-29)

Test eseguiti:

1. comando reale manuale:
   - `py -m src.tesla_manual_command --set-amps 6 --i-understand-this-sends-real-command`
2. verifica read-only successiva:
   - `py -m src.tesla_readonly_status --output-json data/tesla_status_sample.json`
3. verifica log:
   - `data/tesla_command_calls_log.csv`

Risultato:

- il comando `set_charge_amps` e stato inviato ma rifiutato da Tesla API con `403`:
  - `Unauthorized missing scopes`
- la lettura successiva ha mostrato `charge_current_request=5` e `charge_amps=5` (nessun cambio a 6A).
- `TESLA_COMMANDS_ENABLED` risulta nuovamente `false` in `.env` dopo il test.
- nessun `start_charge` / `stop_charge` eseguito in questa fase.

Conclusione:

- smoke test manuale eseguito correttamente dal lato procedura/guardrail;
- comando reale non applicabile finche il token non include gli scope comandi richiesti
  (es. `vehicle_cmds` / `vehicle_charging_cmds`).

### Retest dopo aggiornamento scope (2026-04-29)

Aggiornamenti effettuati:

- nuovo authorization flow con scope:
  - `openid`
  - `offline_access`
  - `vehicle_device_data`
  - `vehicle_cmds`
  - `vehicle_charging_cmds`
- nuovi token salvati in `.env` locale.

Test reale ripetuto:

- `py -m src.tesla_manual_command --set-amps 6 --i-understand-this-sends-real-command`

Risultato:

- risposta Tesla API ancora `403`, ma con causa diversa:
  - `Tesla Vehicle Command Protocol required`
- lettura read-only successiva: `charge_current_request=5`, `charge_amps=5` (nessun cambio a 6A).

Interpretazione:

- il blocco scope e risolto;
- per questo veicolo/firmware serve passare dal flusso Vehicle Command Protocol
  (comandi firmati con Virtual Key / Vehicle Command Proxy), non basta REST command legacy.

## Strategia anti-costo e rischio operativo

- evitare polling continuo su endpoint live;
- evitare `wake_up` salvo casi manuali e consapevoli;
- verificare stato connettivita prima di richieste costose;
- usare comandi solo quando strettamente necessario;
- evitare retry aggressivi sui comandi (rischio azioni duplicate);
- mantenere il controllo reale locale e con protezioni conservative.

## Riferimenti ufficiali Tesla

- Fleet API - What is Fleet API: https://developer.tesla.com/docs/fleet-api/getting-started/what-is-fleet-api
- Partner Endpoints (`register`): https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints
- Vehicle Commands: https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands
- Virtual Keys overview: https://developer.tesla.com/docs/fleet-api/virtual-keys/overview
- Virtual Keys developer guide: https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide
- API Best Practices: https://developer.tesla.com/docs/fleet-api/getting-started/best-practices
- Partner Tokens: https://developer.tesla.com/docs/fleet-api/authentication/partner-tokens
