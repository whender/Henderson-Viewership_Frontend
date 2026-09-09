# Preseason AP model

Production uses two models: `ap/model.json` for weekly voting and `ap/preseason_model.json` for preseason voting. The latter is a separate ridge model (alpha 80) trained only on earlier preseason polls, using 25 features: prior AP history, roster-informed offense/defense, talent, recruiting, continuity, portal and coaching information. Model parameters and input matrices are versioned together.

## Dates and source assumptions

`preseason_dates.json` records published dates from College Poll Archive. Cutoffs use midnight UTC at the start of the release day, conservatively excluding release-day events when an exact time is unavailable. Unknown preseason dates are null, never July 1. Add a verified date before preparing a new season.

Annual offseason records are accepted as information known before the poll, per the data owner's confirmation. Collection timestamps indicate refresh times. The current historical inputs were reconstructed; they are not immutable snapshots collected before the historical poll. The dashboard calls the 2026 output a historical reconstruction and reports preseason backtests separately from in-season results.

## Frozen inputs and training

`preseason_features.json.gz` holds the reviewed preseason feature matrices for 2016–2026, team identities, labels, release dates and the named schema. The AP target rankings are labels only; current-year labels and features cannot influence fitting through the previous year. The source football model's preseason priors were also rebuilt using only earlier outcomes. Explicit post-cutoff hires and portal entries were filtered; coaching season outcomes were removed.

The input builder lives with the main CFBPREDICT data pipeline (`scripts/experiment_ap_preseason.py --separate-preseason`). It exports `data/processed/ap_preseason_features.json.gz`. When importing that output, attach/verify each observation's `releaseDate` and retain `dateSource` from this repository's verified date table. No API key or player-level personal data is stored in the AP feature artifact.

Reproduce training from repository inputs:

```sh
python football-model/train_preseason.py --season 2026
python football-model/export_ap.py
python -m unittest discover -s football-model -p 'test_*.py'
```

For a new season, add its verified release date, generate and review the new annual input observation from the main model, commit those inputs, then train with `--season YEAR` (or use the Prepare preseason AP model workflow). The importer rejects mismatched dates/schema, duplicate teams/seasons and nonfinite values. Keep regular-model training through YEAR-1 current as well. Do not regenerate a historical season's inputs to silently change a forecast that was already published.

The stored candidate artifact contains the season, training cutoff, coefficients, scalers, immutable season input vector, source basis, backtest results and a separately fitted history-only fallback. Missing roster snapshots invoke that labeled fallback; corrupt snapshots or mismatched model seasons stop publication and preserve the existing public JSON. A new season cannot silently reuse last year's roster model.

## Publication

The daily workflow calls `export_ap.py`. Before the first current-season AP poll it publishes preseason predictions using the prepared artifact and verified release date. After the first poll it switches next-poll forecasts to the weekly model. The Preseason view remains available throughout the season. Daily publication does not rebuild the frozen preseason input snapshot.

Current corrected-date validation: 2019–2025, seven preseason polls, 3.709 capped rank error and 87.43% Top 25 membership. The 2026 reconstruction has 2.36 error and 22/25 membership. These are historical backtests, not guaranteed future accuracy. Regular-poll validation remains separate.
