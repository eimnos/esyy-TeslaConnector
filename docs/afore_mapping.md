# Afore Register Mapping

## Wave 2B Confirmation (April 26, 2026)

Conferma effettuata con scansioni `input registers` (`0..1000`) nei file:

- `data/confirm_baseline.csv`
- `data/confirm_load_on.csv`
- `data/confirm_load_off.csv`
- `data/diff_confirm_load.csv`

Le scansioni sono state eseguite in sequenza con finestra di circa 2 minuti tra baseline e load-on.

### Stato mapping

| Registro | Nome ipotizzato | Scala | Unita | Valore app | Valore letto | Formula | Stato | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `560` | PV Power (candidato) | `x1` | `W` | n/d | baseline `3777`, load_on `3775`, load_off `3764` | `value` | partial | Registro stabile e plausibile per potenza FV, ma manca confronto istantaneo con app/display inverter. |
| `524-525` | Grid Power import/export (candidato) | `x1` | `W` | n/d | baseline `-104`, load_on `-143`, load_off `-143` | `int32_signed=(reg524<<16)+reg525` | partial | Parsing signed32 coerente (valori con segno), ma test ON/OFF non ha mostrato transizione netta verso import. |
| `528` | Load Power (candidato precedente) | `x1` | `W` | n/d | baseline `4474`, load_on `4443`, load_off `4477` | `value` | rejected | Con il test carico non emerge correlazione robusta con aumento di assorbimento. |
| `538` | Load/PV dynamic metric (nuovo candidato) | `x1` | `W` | n/d | baseline `1074`, load_on `806`, load_off `938` | `value` | partial | Varia sensibilmente durante il test, ma la semantica esatta non e ancora certa. |
| `540` | Load/PV dynamic metric (nuovo candidato) | `x1` | `W` | n/d | baseline `1075`, load_on `806`, load_off `938` | `value` | partial | Andamento quasi identico a `538`; possibile registro duplicato/canale correlato. |
| `526-527` | Pair signed32 vicino a grid (test sperimentale) | `x1` | `unknown` | n/d | `65470464` costante | `int32_signed=(reg526<<16)+reg527` | rejected | Nessuna variazione utile durante i test. |
| `528-529` | Pair signed32 vicino a load (test sperimentale) | `x1` | `unknown` | n/d | load_off `293470207`, load_on `291241983` | `int32_signed=(reg528<<16)+reg529` | partial | Cambia molto ma non e ancora interpretabile fisicamente con affidabilita. |
| `TBD` | Daily Production | TBD | `kWh` | n/d | n/d | TBD | partial | Non ancora identificato con certezza in questa finestra temporale. |
| `TBD` | Total Production | TBD | `kWh` | n/d | n/d | TBD | partial | Non ancora identificato con certezza in questa finestra temporale. |

## Osservazioni tecniche

- Il confronto `load_off` vs `load_on` e stato esportato in `data/diff_confirm_load.csv`.
- Parsing signed32 sperimentale su coppie richieste esportato in `data/diff_confirm_pairs.csv`.
- Per la chiusura definitiva dei criteri Wave 2B servono ancora:
  - verifica istantanea dei valori con app inverter (soprattutto PV power);
  - almeno un evento ON/OFF con delta netto e noto del carico in quel preciso istante;
  - un caso con transizione import/export chiaramente osservabile per confermare il segno grid.
