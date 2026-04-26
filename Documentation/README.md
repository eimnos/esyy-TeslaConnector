# Tesla Solar Smart Charging

## Overview

Sistema per la gestione intelligente della ricarica Tesla basata sul surplus fotovoltaico.

Il sistema:

* legge i dati dell’inverter Afore via collector (LAN)
* calcola il surplus energetico disponibile
* regola automaticamente la ricarica Tesla
* salva dati e storico su Supabase
* espone dashboard web su Vercel con KPI energetici e automotive

---

## Architettura

```text
Afore Inverter + Collector
        ↓
Controller locale (Python)
        ↓
 ┌───────────────┬──────────────────┐
 ↓               ↓                  ↓
Tesla API     Supabase DB      Logs locali
        ↓
Web App (Next.js su Vercel)
```

---

## Tech Stack

### Backend (Controller)

* Python 3.11+
* pysolarmanv5
* requests
* supabase-py

### Frontend

* Next.js
* Supabase client
* Recharts / Tremor

### Infrastruttura

* Supabase (DB + Auth + Realtime)
* Vercel (hosting frontend)

---

## Tesla API – Modello e Costi

Tesla utilizza un modello **pay-per-use** con credito gratuito mensile.

### Costi indicativi

```text
500 richieste dati → ~1$
1000 comandi → ~1$
150.000 segnali streaming → ~1$
50 wake-up → ~1$
Credito gratuito → 10$/mese
```

### Impatto sul progetto

Scenario NON ottimizzato:

```text
Polling ogni minuto → ~43.000 chiamate/mese → ~80$
```

Scenario ottimizzato (target progetto):

```text
Polling intelligente → 2–5$/mese → coperto da credito gratuito
Costo reale → 0€
```

---

## Strategia Anti-Costo (CRITICA)

### Regole obbligatorie

```text
✔ evitare polling continuo
✔ evitare wake-up auto
✔ usare polling dinamico
✔ inviare comandi solo se necessari
✔ caching stato locale
```

### Frequenze operative

```text
Auto inattiva → polling ogni 10–15 minuti
Auto in carica → polling ogni 30–60 secondi
Auto offline → nessuna chiamata
```

### Ottimizzazione comandi

```text
✔ cambiare ampere solo se variazione ≥ 2A
✔ evitare comandi duplicati
✔ limitare start/stop
```

---

## Dati Tesla disponibili

Il sistema raccoglierà:

```text
✔ stato batteria (SOC)
✔ stato ricarica
✔ ampere attuali e target
✔ energia caricata
✔ limite carica
✔ odometro (km)
✔ velocità (opzionale)
✔ posizione (opzionale)
✔ stato veicolo
```

---

## KPI previsti

### Energia

```text
kWh caricati totali
kWh da fotovoltaico
kWh da rete
% autoconsumo
% autosufficienza
```

### Economici

```text
costo energia stimato
risparmio rispetto rete
risparmio mensile
```

### Automotive

```text
km percorsi
consumo medio kWh/100km
efficienza ricarica
tempo totale ricarica
numero sessioni
```

---

## Logica di controllo

### Calcolo surplus

```text
surplus = -grid_power (se export)
amps = surplus / 230
```

### Regole

```text
< 1400W → stop
1400–2000W → 6–8A
2000–3000W → 8–13A
> 3000W → 13–16A
```

### Protezioni

```text
✔ aggiornamento max 1/minuto
✔ isteresi start/stop
✔ modalità dry-run
✔ limite ampere configurabile
```

---

## Modalità operative

```text
AUTO → controllo automatico
MANUAL → controllo utente
DRY_RUN → simulazione senza comandi reali
```

---

## Database (Supabase)

### inverter_samples

```text
timestamp
pv_power_w
grid_power_w
export_w
load_power_w
```

### tesla_samples

```text
timestamp
battery_level
charging_state
actual_amps
target_amps
odometer_km
energy_added_kwh
```

### controller_decisions

```text
timestamp
export_w
target_amps
action_sent
reason
```

### controller_settings

```text
auto_mode
dry_run
min_amps
max_amps
start_threshold_w
stop_threshold_w
poll_interval
```

---

## Web App (Vercel)

### Dashboard Live

```text
✔ produzione FV
✔ import/export rete
✔ surplus
✔ stato Tesla
✔ ampere attuali/target
✔ modalità sistema
```

### Storico

```text
✔ grafico produzione
✔ grafico export/import
✔ grafico ricarica Tesla
✔ storico km e consumi
```

### Configurazione

```text
✔ soglie
✔ limiti ampere
✔ modalità auto/manuale
✔ dry-run
```

---

## Struttura progetto

```text
src/
  read_afore.py
  tesla_client.py
  solar_logic.py
  controller.py

web/
  Next.js app

docs/
  architecture.md
  tesla_api.md
  supabase_schema.md
```

---

## Decisioni chiave

```text
✔ controllo ricarica sempre locale
✔ Tesla API usata in modo ottimizzato
✔ cloud solo per visualizzazione/config
✔ evitare dipendenze da cloud inverter
✔ sistema modulare e scalabile
```

---

## Rischi

```text
- mappa registri Afore non documentata
- limiti Tesla API
- wake-up involontari auto
- costi API se polling errato
```

---

## Roadmap

### Fase 1

* lettura inverter
* mapping registri

### Fase 2

* integrazione Tesla API
* test comandi

### Fase 3

* automazione ricarica

### Fase 4

* integrazione Supabase

### Fase 5

* dashboard Vercel

---

## Output finale

```text
✔ ricarica Tesla automatica da fotovoltaico
✔ costo API ≈ 0€
✔ dashboard completa
✔ storico energia + auto
✔ KPI avanzati
```

---

## Licenza

MIT
