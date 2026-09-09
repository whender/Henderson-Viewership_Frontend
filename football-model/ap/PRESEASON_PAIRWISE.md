# Preseason selection and ordering

The preseason model first selects 25 teams using the existing roster-informed ridge model. A separate pairwise logistic model orders those teams. Teams outside the selected 25 retain the original order. No current-year poll labels or game results enter predictions.

The comparison model uses the original 25 offseason features plus eight features derived only from prior AP polls: previous preseason rank strength, two-year preseason strength, three- and five-year average strength, five-year preseason presence, previous preseason minus final strength, best recent preseason strength, and previous final × preseason strength. Ridge penalty is 80. Every ranked pair and ranked-versus-unranked pair contributes to training, with equal total weight per season before recency decay.

Run `python football-model/train_preseason.py --season 2026` to rebuild. The original selection model, comparison model, and immutable current-year input vectors are stored together in `preseason_model.json`. Publishing reads those vectors without current-season poll or result inputs. Missing roster snapshots retain the existing history-only fallback.

2019–2024 walk-forward development rank error improved from 3.473 to 3.187, with unchanged 87.3% Top 25 overlap. Top-10 rank error improved from 2.00 to 1.65, but top-10 overlap decreased from 86.7% to 85.0%. The already-examined 2025 follow-up improved from 5.12 to 4.24. The 2026 reconstruction changed from 2.36 to 2.40. These are exploratory comparisons, not untouched holdouts; the combined method was tested after observing the standalone pairwise model's membership tradeoff. Selection among nine variants used the 2019–2024 results.

The dashboard's seven-poll validation includes 2019–2025: rank error 3.337, Top 25 overlap 87.4%. Error caps predictions outside the Top 25 at No. 26. The method cannot fix membership misses. Offseason snapshot availability retains the previously reviewed pre-poll availability assumption. The weekly AP movement model and CFP model are unchanged.
