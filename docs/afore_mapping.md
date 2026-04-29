# Afore Register Mapping

## Wave 9C Grid Remapping (April 29, 2026)

Scenario reale osservato:

- carico EV aggregato > `4 kW` (Tesla + seconda EV);
- app inverter: acquisto rete istantaneo circa `4.7 kW`;
- registro candidato storico `524-525`: circa `+256 .. +277 W`.

Decisione Wave 9C:

- mapping `524-525` riportato da `confirmed` a `rejected/partial`;
- motivo: il valore non segue il carico reale EV ad alta potenza (errore ordine di grandezza).

## Wave 9B Grid Confirmation (April 29, 2026)

Sessione guidata eseguita con `src/grid_confirmation_session.py`.

Output prodotti:

- `data/grid_confirmation_report.csv` (locale, non versionato per `.gitignore`)
- `docs/grid_confirmation.md`

Esito storico (ora superato da Wave 9C):

- `AFORE_GRID_SIGN_MODE` confermato su `import_positive`.
- Interpretazione confermata: raw `> 0` = import, raw `< 0` = export.

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
| `524-525` | Grid Power import/export (candidato) | `x1` | `W` | app: ~`4700 W` import (Wave 9C) | Wave 9C: `+256 .. +277` con EV load elevato | `int32_signed=(reg524<<16)+reg525` | rejected/partial | Non segue carico reale > `4 kW`. Segno storico import/export non piu affidabile finche non viene trovato il registro corretto. |
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
  - almeno un evento ON/OFF con delta netto e noto del carico in quel preciso istante.

Aggiornamento Wave 9B:

- requisito segno grid chiuso: `confirmed` su `import_positive`.

## Wave 3 Dry-Run (30 minuti) - April 26, 2026

- Comando eseguito: `python -m src.controller_loop_dry_run --duration-minutes 30 --log-path data/controller_dry_run_log.csv`
- Esito run 30 minuti: completato senza crash (`cycle 1..30` presenti, nessun ciclo mancante).
- Range PV osservato (registro candidato `560`): `3459 W .. 3680 W`.
- Range Grid raw osservato (coppia candidata `524-525`, signed int32): `-857 W .. +274 W`.
- Flag `GRID_SIGN_UNKNOWN`: sempre presente su tutte le righe non in errore.
- Chiamate Tesla/Supabase: non rilevate durante il run (solo loop locale + lettura collector Afore).
- Anomalie: 2 errori sporadici di lettura (`READ_ERROR`, cicli `6` e `9`, messaggio `Empty:`), con recupero automatico ai cicli successivi.
