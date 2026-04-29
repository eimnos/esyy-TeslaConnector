# Wave 9D - ha-solarman Investigation

Data: April 29, 2026

## Scope

Analisi tecnica del repository `davidrapan/ha-solarman` per verificare:

- presenza di profili Afore;
- mapping registri Grid/Load/Import/Export utili;
- eventuali differenze rispetto ai nostri candidati attuali.

Repository analizzato:

- https://github.com/davidrapan/ha-solarman

## Cartelle analizzate

- `custom_components/solarman`
- `custom_components/solarman/inverter_definitions`
- `tools`

File Afore trovati in `inverter_definitions`:

- `afore_2mppt.yaml`
- `afore_BNTxxxKTL-2mppt.yaml`
- `afore_hybrid.yaml`

## Discovery / profile logic

- La discovery rete logger (LSWx) usa UDP broadcast su porta `48899` (`WIFIKIT-214028-READ`, `HF-A11ASSISTHREAD`).
- L’autodetection profilo in codice risulta focalizzata su Deye (`lookup_profile` in `common.py`).
- Per Afore non emerge una autodetection dedicata equivalente: il profilo sembra da selezionare/configurare.

## Evidenze importanti dai profili Afore

### Afore T6 / Hybrid (coerente con documento T6)

Riferimenti principali emersi:

- `Grid Power`: `0x0218, 0x0217` -> decimali `536, 535` (signed, rule 2)
- `Load Power`: `0x0224, 0x0223` -> decimali `548, 547` (signed, rule 2)
- `PV total power`: `0x022A, 0x0229` -> decimali `554, 553` (U32)
- `PV2 power`: `0x0230` -> decimale `560` (U16)
- `Today Production`: `0x03EF, 0x03EE` -> `1007, 1006`
- `Total Production`: `0x0403, 0x0402` -> `1027, 1026`
- `Total Production B`: `0x03F7, 0x03F6` -> `1015, 1014`
- `Today Energy Export`: `0x03EA` -> `1002`
- `Today Energy Import`: `0x03EB` -> `1003`
- `Total Energy Export`: `0x03FB, 0x03FA` -> `1019, 1018`
- `Total Energy Import`: `0x03FD, 0x03FC` -> `1021, 1020`

### Confronto critico con il candidato storico 524-525

Dal file T6 condiviso (`211208 - Afore T6 communication protocol V1.0-211109`):

- `522-523`: Total active power `Pinv` (inverter output)
- `524-525`: **Total reactive power `Qinv`**
- `535-536`: **Total grid-connected active power `Pgrid`**
- `547-548`: **Total load active power `Pload`**

Implicazione:

- l’uso di `524-525` come Grid Power è probabilmente errato (reattiva, non attiva), coerente con il comportamento osservato in campo.

## Confronto con i nostri CSV (Wave 9C/9D)

Dataset usati:

- `data/scan_ev_load_on_input.csv`
- `data/scan_ev_load_off_input.csv`
- `data/scan_target_ha_afore_power_input.csv`
- `data/scan_target_ha_afore_meter_input.csv`

Osservazioni rapide:

- `524-525`: delta piccolo (`+21` tra OFF/ON EV), non rappresenta `~4.7kW` app.
- `536/535` (candidato `Pgrid`): valori nell’ordine `~3246..3325` (plausibili come potenza attiva rete in alcuni scenari), da validare con test sincronizzato con app.
- `548/547` (candidato `Pload`): valori simili (`~3248..3325`), coerenti con metrica di carico totale ma non ancora confermati con scenario ON/OFF controllato.
- blocco meter `1002..1027`: valori coerenti con contatori energia (import/export/production), non con potenza istantanea.

## Google Drive references (fornite dal team)

Fonti utili aperte:

- T6 protocol spreadsheet: contiene mapping `Pgrid 535-536`, `Pload 547-548`, `Ppv 553-554`.
- DTSD422-D3 spreadsheet: mapping meter esterno (energia/registri dedicati), utile in caso di architettura con contatore esterno.
- PDF T4: disponibile come link ma non completamente parsabile da questa sessione (pagina viewer dinamica).

## Esito Wave 9D

- `ha-solarman` fornisce mapping Afore utile e coerente con il protocollo T6.
- Emergono candidati alternativi migliori rispetto a `524-525`:
  - Grid active power: `535-536` (profilo usa ordine `[536,535]`)
  - Load active power: `547-548` (profilo usa ordine `[548,547]`)
  - PV total power: `553-554` (profilo usa `[554,553]`)
- Necessaria validazione in tempo reale con scenario carico controllato nello stesso minuto dell’app inverter.

## Test mirato eseguito (Wave 9D)

Comandi lanciati:

- `py -m src.scan_afore_registers --start 529 --end 560 --block-size 16 --output data/scan_target_ha_afore_power_input.csv --register-type input`
- `py -m src.scan_afore_registers --start 1000 --end 1030 --block-size 16 --output data/scan_target_ha_afore_meter_input.csv --register-type input`

Nota sicurezza:

- nessuna riabilitazione `GRID_AUTOMATION_ENABLED`;
- nessun comando Tesla inviato.
