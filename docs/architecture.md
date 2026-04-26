# Architecture

## Scope

Questa architettura separa chiaramente il controllo locale (critico) dai servizi cloud (osservabilita e UI).

## Flusso principale

```text
Afore Inverter + Solarman Collector (LAN)
                |
                v
Controller locale Python
                |
                +--> Dry-run decision engine (Wave 1)
                +--> Supabase (future wave)
                +--> Tesla Fleet API (future wave)
                +--> Web app Next.js/Vercel (future wave)
```

## Principio chiave

Il controllo reale della ricarica deve restare locale, vicino ai dati energetici e indipendente dal cloud.

## Evoluzione per wave

- Wave 1: sola lettura collector e test locale.
- Wave 2-3: mapping registri e logica surplus.
- Wave 4+: integrazione storage cloud, poi Tesla API e dashboard.
