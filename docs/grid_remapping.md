# Wave 9C - Grid Power Remapping

## Context

- Obiettivo: trovare il registro istantaneo reale di import/export rete.
- Problema osservato: con carico reale EV > `4 kW`, il candidato precedente `524-525` resta circa `+259 W`.
- Safety: nessun comando Tesla automatico; `TESLA_COMMANDS_ENABLED=false`.

## Scan Executed (UTC)

1. `py -m src.scan_afore_registers --start 0 --end 2000 --block-size 50 --output data/scan_ev_load_on.csv --register-type holding`
   - Rows: `2001`
   - Timestamp window: `2026-04-29T00:14:07Z .. 2026-04-29T00:14:09Z`
2. `py -m src.scan_afore_registers --start 0 --end 2000 --block-size 50 --output data/scan_ev_load_on_input.csv --register-type input`
   - Rows: `2001`
   - Timestamp window: `2026-04-29T00:14:15Z .. 2026-04-29T00:14:16Z`
3. `py -m src.scan_afore_registers --start 0 --end 2000 --block-size 50 --output data/scan_ev_load_off.csv --register-type holding`
   - Rows: `2001`
   - Timestamp window: `2026-04-29T00:14:32Z .. 2026-04-29T00:14:36Z`
4. `py -m src.scan_afore_registers --start 0 --end 2000 --block-size 50 --output data/scan_ev_load_off_input.csv --register-type input`
   - Rows: `1951` (blocco `0..49` fallito una volta)
   - Timestamp window: `2026-04-29T00:15:32Z .. 2026-04-29T00:15:33Z`

## Differential Analysis

Comando:

`py -m src.analyze_register_changes data/scan_ev_load_off_input.csv data/scan_ev_load_on_input.csv --min-abs-delta 1 --output data/diff_ev_load.csv --signed32-pairs 524-525,526-527,528-529 --pairs-output data/diff_ev_load_pairs.csv --find-grid-candidates --candidate-targets 4700,470,47,47000 --candidate-max-error-ratio 0.10 --candidate-track-threshold-w 500 --candidate-limit 0 --candidate-output data/grid_candidates_ev_load.csv`

Output:

- `data/diff_ev_load.csv`
- `data/diff_ev_load_pairs.csv`
- `data/grid_candidates_ev_load.csv`

## Key Findings

- Su scansione `holding`, la maggior parte dei registri risulta `0`: canale non utile per questo mapping.
- Su scansione `input`, il candidato storico `524-525` passa da `256` a `277` (`+21 W`) tra OFF/ON: delta troppo basso rispetto all'atteso `~4700 W`.
- Pair signed32:
  - `524-525`: `256 -> 277` (`+21`)
  - `526-527`: `-3276800 -> -3670016`
  - `528-529`: `16777216 -> 18219008`
- Candidati euristici piu vicini ai target numerici (`4700/470/47/47000`) esistono, ma senza correlazione robusta al cambio carico:
  - esempi: registri `500`, `513`, `550`, `1509` (e relative coppie)
  - nessuna evidenza forte che rappresentino import/export rete istantaneo in modo affidabile.

## Conclusion Wave 9C

- `524-525` declassato da `confirmed` a `rejected/partial`.
- Stato mapping Grid Power: **non confermato**.
- `AFORE_GRID_SIGN_MODE` deve restare `unknown` finche non viene isolato il vero registro rete.

## Next Recommended Session

Per chiusura definitiva:

1. Eseguire baseline + EV ON + EV OFF con step temporali separati di almeno 2-3 minuti.
2. Annotare nello stesso minuto i valori app inverter (`grid import/export` istantaneo).
3. Ripetere analisi su input registers con delta minimo atteso > `1500 W`.
4. Confermare solo un candidato che segua chiaramente l'andamento ON/OFF del carico reale.

