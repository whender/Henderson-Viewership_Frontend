# AP weekly movement model

Production in-season forecasts use `ap-movement-v1`, trained on 158 regular AP polls from 2015–2025. Preseason rankings continue using the separate roster-informed model. The complete historical archive remains available.

Run `OPENBLAS_NUM_THREADS=1 python football-model/train_movement.py --through 2025` to retrain. Update validation when promoting a new season/version. The exporter rejects a model not trained through the preceding season. No daily retraining or target-poll labels enter predictions.

The model learns change from previous normalized AP rank score using 100 depth-three histogram trees (learning rate .05, minimum leaf 20). Eightfold training weight applies to historical Top10 teams dropping at least three places despite winning every game since the previous poll. Those labels are used only within training seasons. Features include pregame AP opponent buckets, game margins and home-game interactions, Vegas expectations, early-season interactions, and performances of teams within five prior AP places. All peers are selected using the previous poll. Histogram boundaries are fitted only on training inputs.

Historical expectations use median CFBD closing lines, with sportsbook spelling aliases deduplicated. Future game scenarios use currently available quotes. CFBD documents closing lines but supplies no independently auditable quote timestamps. Game outcomes in the lines response are discarded. Results need the existing four-hour AP buffer; pregame polls become available at the end of their release date. Missing lines have explicit feature indicators, with no substitution from the football model. Scenario results themselves still use football-model forecasts and are labeled as assumptions. Daily refresh requires CFBD_API_KEY in the AP workflow step; keys are never included in public artifacts.

`movement_validation.json` records the promotion experiment: 2019–2024 walk-forward selection, with a previously examined 2025 follow-up. Every fold trains strictly on earlier years. This is not a new untouched holdout. Compared with the AP-tier/Vegas regression, rank error improved from 1.457 to 1.190 across 87 development polls and 1.416 to 1.147 across 15 follow-up polls. Three of eleven development big drops were detected, with four false alarms among 566 other winning Top10 cases. The sole 2025 big-drop case was still missed. Validation rank error caps predictions outside the Top25 at 26.

The dashboard displays input facts for individual teams, not linear coefficients or causal explanations. Forecast versions accompany newly archived live forecasts, preserving earlier models' predictions instead of rewriting them as current-model successes. The latest reconstruction and scenario are produced using the active model.

Promotion checks include persisted-model round trips, production Oregon parity (#5 for September 8, 2026), target-rank immunity, provider deduplication, missing lines, and the existing preseason/export checks. Experiment chronology, feature, tree, and false-alarm tests also passed before porting. Prior `ap/model.json` is retained for comparison; runtime publication uses `ap/movement_model.json`.

## Comfortable wins (ap-movement-v2)

After scoring, negative movement is reduced linearly as the minimum margin across games since the previous poll grows from 14 to 42 points. Positive score movement is unchanged. A team with no new games, a loss, or a win of 14 points or fewer receives no adjustment. This calibrates normalized AP score movement; it does not lock a team's rank, because peers may pass it. It uses only buffered pre-release results, including clearly labeled scenario scores in hypothetical forecasts. The raw Vegas residual remains visible in team factors.

Four fixed variants were compared in 87 walk-forward polls across 2019–2024. The selected taper reduced overall rank error from 1.1904 to 1.1821 and comfortable-win Top10 error from 0.450 to 0.404 across 240 cases. Top25 membership, three detected large drops, and four false alarms were unchanged. The already-examined 2025 follow-up regressed slightly: overall error 1.1467 to 1.1573; comfortable-win error 0.459 to 0.514. These are exploratory results, not fresh holdouts. Full summary is in `comfortable_win_validation.json`.

September 8, 2026 reconstruction: Indiana moves from predicted No.8 to No.6 (actual No.5); Oregon remains No.5 (actual No.6). No team-specific adjustment is used. The preseason model is unchanged.
