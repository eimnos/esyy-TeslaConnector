# Afore Register Mapping

Rilevazioni iniziali Wave 2 eseguite via `input registers` (range 0..1000).  
Stato: mapping in corso, da validare con confronti in momenti distinti della giornata e con carico artificiale reale.

| Registro | Nome ipotizzato | Scala | Unita | Valore app | Valore letto | Formula | Confermato | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `560` | PV Power (candidato) | `x1` | `W` | n/d | `~3681..3867` | `value` | PARZIALE | Varia nel tempo in modo compatibile con produzione; da confermare contro app/display inverter. |
| `524-525` | Grid Power Import/Export (candidato) | `x1` | `W` | n/d | `~ -315 .. +282` | `int32_signed = (reg_hi<<16) + reg_lo` | PARZIALE | Segno coerente con possibile import/export; serve test controllato con carico ON/OFF. |
| `528` | Load Power (candidato) | `x1` | `W` | n/d | `~4297..4564` | `value` | PARZIALE | Delta coerente con variazioni di carico, ma non ancora allineato con misura esterna. |
| `TBD` | Daily Production | TBD | `kWh` | n/d | n/d | TBD | NO | Nessun contatore monotono identificato con certezza nelle scansioni correnti. |
| `TBD` | Total Production | TBD | `kWh` | n/d | n/d | TBD | NO | Da ricercare con scansioni distanziate (mattino/mezzogiorno/sera) e confronto app inverter. |

## Note operative

- Le scansioni `holding` 0..500 sono risultate quasi statiche.
- La telemetria piu utile e emersa su `input registers`.
- I file `scan_morning/scan_midday/scan_load_off/scan_load_on` in questa sessione sono stati acquisiti in finestra ravvicinata per validare pipeline e parsing.
- Per la conferma finale servono:
  - confronto con valori reali app/inverter nello stesso istante;
  - test con carico artificiale chiaramente noto (es. forno/phon);
  - verifica segno import/export.
