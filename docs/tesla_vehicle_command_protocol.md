# Tesla Vehicle Command Protocol Assessment (Wave 10B)

## Context and current status

Wave 10A confirmed:

- OAuth flow and command scopes are now correct (`vehicle_cmds`, `vehicle_charging_cmds`).
- Direct REST call `POST /api/1/vehicles/{id}/command/set_charging_amps` still fails with:
  - `403 Tesla Vehicle Command Protocol required`.

Why this happens:

- Tesla documents that commands must be signed with a virtual key on vehicles that require the protocol.
- If a command is not signed, vehicle-side validation rejects it.
- Tesla announcement timeline deprecated direct REST command usage for most vehicles.

## What is a Virtual Key

A Virtual Key is an application key pair:

- private key: kept on our command server/proxy, used to sign commands
- public key: published on our HTTPS domain and paired on the car

Only when both OAuth authorization and key pairing are valid, the vehicle executes commands.

## What is the Vehicle Command Proxy

Tesla `vehicle-command` SDK includes `tesla-http-proxy`:

- exposes REST-like endpoints compatible with Fleet API command paths
- signs commands with the private key
- forwards signed commands to Fleet API/vehicle

In practice:

`our app/scripts -> local tesla-http-proxy -> Fleet API -> vehicle`

## OAuth token vs Virtual Key

OAuth token and Virtual Key solve different trust layers:

- OAuth token: proves user/app API authorization to Tesla backend.
- Virtual Key signature: proves command authenticity to the vehicle itself.

Both are required for vehicles that enforce Vehicle Command Protocol.

## Pairing prerequisites

1. Generate EC key pair on `prime256v1` curve.
2. Keep private key secret, never host it publicly.
3. Host public key at:
   - `https://<app-domain>/.well-known/appspecific/com.tesla.3p.public-key.pem`
4. Register partner account/public key domain via Tesla Partner `register` flow.
5. Ensure user OAuth grant includes command scopes.
6. Pair key on vehicle with deep link:
   - `https://tesla.com/_ak/<developer-domain>`
7. Confirm pairing from Tesla app/vehicle Locks screen.

## Recommended option for this project

Recommended Wave 10B path:

- run official Tesla `tesla-http-proxy` locally (manual mode only);
- keep current controller logic unchanged (no auto integration yet);
- continue using manual smoke test CLI until protocol path is validated.

Rationale:

- minimal changes to existing Python controller;
- preserves safety guardrails;
- aligns with Tesla recommended migration path.

## Technical decision: where to host public key

Decision for Esyy Tesla Connector:

- host public key on project HTTPS domain used for app identity:
  - `https://esyy-tesla-connector.vercel.app/.well-known/appspecific/com.tesla.3p.public-key.pem`
- do not commit `.pem` files in Git.

Operational note:

- publish the public key as deployment artifact/config-managed asset;
- private key remains local/server-side only.

## Implementation plan (next wave, not executed in Wave 10B)

1. Generate key pair locally.
2. Publish public key on HTTPS path.
3. Validate key visibility from internet.
4. Run Partner `register` checks and verify registered key.
5. Pair key on vehicle via `_ak` link.
6. Start local `tesla-http-proxy`.
7. Re-run `set_charging_amps` manual smoke test through proxy endpoint.

## Explicit non-goals in Wave 10B

- no real command execution through proxy yet;
- no automatic controller integration;
- no Tesla start/stop automation.

## Wave 10C outcome (2026-04-29)

### Key generation and Git safety

- Generated locally:
  - `tools/tesla-command-proxy/config/private-key.pem`
  - `tools/tesla-command-proxy/config/public-key.pem`
- `private-key.pem` is local-only and ignored by git (`*.pem`, `private-key.pem` in `.gitignore`).
- Public key published in web app at:
  - `web/public/.well-known/appspecific/com.tesla.3p.public-key.pem`

### Vercel hosting verification

Published URL:

- `https://esyy-tesla-connector.vercel.app/.well-known/appspecific/com.tesla.3p.public-key.pem`

Result:

- HTTPS endpoint reachable and serving the expected PEM.

### Partner registration and pairing

Actions performed:

1. Verified `public_key` endpoint for domain `esyy-tesla-connector.vercel.app`.
2. Re-ran partner registration endpoint to align Tesla partner account with the hosted key.
3. Opened pairing URL:
   - `https://tesla.com/_ak/esyy-tesla-connector.vercel.app?vin=LRW3E7ES5PC901288`
4. Verified pairing status via `fleet_status`:
   - `key_paired_vins` contains `LRW3E7ES5PC901288`
   - `unpaired_vins` is empty

### Safety confirmation

- No real Tesla commands were sent during Wave 10C.
- No automatic controller integration was enabled.

## Official references

- Vehicle Commands: https://developer.tesla.com/docs/fleet-api/endpoints/vehicle-commands
- Virtual Keys overview: https://developer.tesla.com/docs/fleet-api/virtual-keys/overview
- Virtual Keys developer guide: https://developer.tesla.com/docs/fleet-api/virtual-keys/developer-guide
- Partner Endpoints (`register` / public key hosting requirement): https://developer.tesla.com/docs/fleet-api/endpoints/partner-endpoints
- Announcements (command protocol deprecation): https://developer.tesla.com/docs/fleet-api/announcements
- Tesla vehicle-command SDK: https://github.com/teslamotors/vehicle-command
