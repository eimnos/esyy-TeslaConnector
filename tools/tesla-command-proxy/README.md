# Tesla Command Proxy Local Setup (Wave 10B prep)

This folder stores setup notes for running Tesla official Vehicle Command Proxy locally.

Scope of this step:

- prepare infrastructure only
- do not run automatic flows
- do not integrate proxy into controller yet

## 1) Prerequisites

- Docker installed locally
- OpenSSL available
- valid Tesla OAuth token with command scopes
- vehicle already authorized for the app

## 2) Create local config folder

```powershell
New-Item -ItemType Directory -Force tools/tesla-command-proxy/config | Out-Null
```

## 3) Generate Virtual Key pair

Private key (keep secret):

```powershell
openssl ecparam -name prime256v1 -genkey -noout -out tools/tesla-command-proxy/config/private-key.pem
```

Public key:

```powershell
openssl ec -in tools/tesla-command-proxy/config/private-key.pem -pubout -out tools/tesla-command-proxy/config/public-key.pem
```

Important:

- never commit `private-key.pem`
- by repository policy, `.pem` files are ignored by git

## 4) Create local TLS cert for proxy (dev only)

```powershell
openssl req -x509 -nodes -newkey ec `
  -pkeyopt ec_paramgen_curve:secp384r1 `
  -pkeyopt ec_param_enc:named_curve `
  -subj '/CN=localhost' `
  -keyout tools/tesla-command-proxy/config/tls-key.pem `
  -out tools/tesla-command-proxy/config/tls-cert.pem `
  -sha256 -days 3650 `
  -addext "extendedKeyUsage = serverAuth" `
  -addext "keyUsage = digitalSignature, keyCertSign, keyAgreement"
```

## 5) Run Tesla proxy locally (manual mode only)

```powershell
docker pull tesla/vehicle-command:latest
docker run --security-opt=no-new-privileges:true `
  -v ${PWD}/tools/tesla-command-proxy/config:/config `
  -p 127.0.0.1:4443:4443 `
  tesla/vehicle-command:latest `
  -tls-key /config/tls-key.pem `
  -cert /config/tls-cert.pem `
  -key-file /config/private-key.pem `
  -host 0.0.0.0 `
  -port 4443
```

## 6) Public key hosting and pairing plan

Target public URL:

- `https://esyy-tesla-connector.vercel.app/.well-known/appspecific/com.tesla.3p.public-key.pem`

Pairing link:

- `https://tesla.com/_ak/esyy-tesla-connector.vercel.app`

Before pairing, verify:

- the public key URL is publicly reachable over HTTPS
- partner account registration is completed for the same app domain

## 7) Safety notes

- no automatic commands in this phase
- do not wire proxy into controller loop
- keep `TESLA_COMMANDS_ENABLED=false` except short manual test windows
