# Wave 9E - HA/Afore Candidate Validation

- Generated at: `2026-04-29T00:48:23.385179+00:00`
- Sample rows: `3`
- Samples with app grid annotation: `0`
- Samples with app load annotation: `0`

## Order Comparison

- Grid MAE [535,536] (A=high,B=low): `None`
- Grid MAE [536,535] (HA order): `None`
- Grid best order by MAE: `unknown`

- Load MAE [547,548] (A=high,B=low): `None`
- Load MAE [548,547] (HA order): `None`
- Load best order by MAE: `unknown`

## Decision Rule

- Mark Grid Power as `confirmed` only if app-matched MAE is consistently low and trend is coherent.
- Otherwise keep status `candidate` or `rejected`.
