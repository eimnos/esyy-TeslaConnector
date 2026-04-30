# Afore Register Mapping

## Wave 9G Daytime Validation - Session Status (April 30, 2026)

Attivita eseguite:

- sync candidati avviato con `src.ha_candidates_sync` (cadence `60s`);
- campione raccolto per ~12 minuti (`data/ha_candidates_sync_log.csv`) e sync continuo attivo in background;
- verifica dashboard prevista su `/afore-candidates`.

Esito parziale attuale:

- nel campione corrente `PV candidate (553-554)` resta `0 W` per tutte le letture (fascia non diurna);
- ordine plausibile confermato dai numeri:
  - Grid: `[535,536]` (ordine inverso produce valori non fisici);
  - Load: `[547,548]` (ordine inverso produce valori non fisici);
- non e ancora possibile chiudere la validazione **diurna** richiesta (condizione `PV > 0` non presente nel run).

Decisione Wave 9G (temporanea):

- `535-536` e `547-548` restano `strong candidate`;
- stato finale `confirmed` rinviato alla sessione con sole e confronto minuto-su-minuto con Solarman Smart;
- `GRID_AUTOMATION_ENABLED` resta `false`.

## Wave 9C Grid Remapping (April 29, 2026)

Scenario reale osservato:

- carico EV aggregato > `4 kW` (Tesla + seconda EV);
- app inverter: acquisto rete istantaneo circa `4.7 kW`;
- registro candidato storico `524-525`: circa `+256 .. +277 W`.

Decisione Wave 9C:

- mapping `524-525` riportato da `confirmed` a `rejected/partial`;
- motivo: il valore non segue il carico reale EV ad alta potenza (errore ordine di grandezza).

Aggiornamento Wave 9D (ha-solarman + protocollo T6):

- documentazione T6 indica `524-525 = Qinv (reactive power)` e non `Pgrid`.
- nuovi candidati da validare per potenza istantanea:
  - `Pgrid`: `535-536` (profilo ha-solarman usa ordine `[536,535]` con valore signed)
  - `Pload`: `547-548` (profilo usa `[548,547]`)
  - `Ppv total`: `553-554` (profilo usa `[554,553]`)

## Wave 9E Target Test Setup (April 29, 2026)

Preparazione test mirato completata:

- parser dedicato: `src/afore_ha_candidates.py`
- sessione validazione: `src/ha_candidate_validation_session.py`
- scan mirati:
  - `data/scan_target_ha_afore_power_input.csv` (529..560)
  - `data/scan_target_ha_afore_meter_input.csv` (1002..1030)

Stato decisionale:

- `535-536`, `547-548`, `553-554`: restano `candidate` finche non c'e confronto app nello stesso istante con trend coerente.
- `524-525`: resta `rejected/partial` (Qinv).

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
| `535-536` | Grid Power attivo totale (nuovo candidato Wave 9D/9G) | `x1` | `W` | app: import variabile | ordine `[535,536]` plausibile; ordine inverso produce valori non fisici (M-range) | `int32_signed(high=reg535,low=reg536)` e confronto ordine inverso | candidate | Strong candidate. Conferma finale solo con run diurno `PV > 0` e confronto app istantaneo. |
| `547-548` | Load Power totale (nuovo candidato Wave 9D/9G) | `x1` | `W` | n/d | ordine `[547,548]` plausibile; ordine inverso produce valori non fisici (M-range) | `int32_signed(high=reg547,low=reg548)` e confronto ordine inverso | candidate | Strong candidate. Conferma finale solo con run diurno `PV > 0` e confronto app istantaneo. |
| `553-554` | PV total power (nuovo candidato Wave 9D) | `x1` | `W` | n/d | notturno/attuale `0` in scan target | `uint32(low=reg554,high=reg553)` | candidate | Da protocollo T6: `Ppv`. Da validare in fascia di produzione FV. |
| `1003` | Today Energy Import (nuovo candidato Wave 9D) | `x0.1` | `kWh` | n/d | `92..106` in scan recenti | `value*0.1` | candidate | Registro energia giornaliera, non potenza istantanea. |
| `1002` | Today Energy Export (nuovo candidato Wave 9D) | `x0.1` | `kWh` | n/d | `0` in scan recenti | `value*0.1` | candidate | Registro energia giornaliera, utile per bilanci ma non per controllo realtime amps. |
| `1021-1020` | Total Energy Import (nuovo candidato Wave 9D) | `x0.1` | `kWh` | n/d | `~38210` raw | `uint32(low=reg1021,high=reg1020)*0.1` | candidate | Coerente con contatore cumulativo, non sostituisce Grid power istantaneo. |
| `1019-1018` | Total Energy Export (nuovo candidato Wave 9D) | `x0.1` | `kWh` | n/d | `~8788` raw | `uint32(low=reg1019,high=reg1018)*0.1` | candidate | Coerente con contatore cumulativo. |
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
