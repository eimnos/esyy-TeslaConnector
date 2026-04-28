# Grid Confirmation Session

- Session UTC: `2026-04-28T22:55:09.797028+00:00`
- Source CSV: `data\grid_confirmation_report.csv`

## Phase Results

| Phase | App Direction | Avg PV (W) | Avg Grid Raw (W) | Raw Sign | Samples OK | Errors | Note |
| --- | --- | ---: | ---: | --- | ---: | ---: | --- |
| baseline | import | 0.0 | 256.0 | positive | 2/2 | 0 | - |
| load_on | import | 0.0 | 257.5 | positive | 2/2 | 0 | - |
| load_off | import | 0.0 | 256.5 | positive | 2/2 | 0 | - |

## Sign Inference

- Status: `confirmed`
- Recommended `AFORE_GRID_SIGN_MODE`: `import_positive`
- Score import_positive: `3`
- Score export_positive: `0`
- Evidence phases used: `3`
- Reason: Miglior allineamento con annotazioni app: import positivo, export negativo.

## Interpretation

- `import_positive` means raw grid > 0 is import, raw grid < 0 is export.
- `export_positive` means raw grid > 0 is export, raw grid < 0 is import.
- If status is `partial`, keep mapping as partial and collect another session.

## Safety

- No Tesla command is sent by this script.
- Tesla ON/OFF phases are observational only.
