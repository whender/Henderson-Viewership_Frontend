# Henderson Football Model

The separate `/#/football-model` dashboard is powered by the CFBPREDICT V2 model,
initially imported from the September 8, 2026 artifact. `cfbpredict/` is the Python
model runtime from that project; `model.json` retains its fitted priors, calibration,
margin layers, and FBS/FCS components. No API credential is shipped to the browser.

The Top 25 is the model's symmetric neutral-field ranking, not a poll. All 138 FBS
teams have profiles. The hypothetical predictor uses precomputed outputs of the
actual model for every ordered pair at both home and neutral sites. Home-site hypothetical predictions include venue travel. For an upcoming scheduled
matchup, the predictor defaults to the earliest remaining meeting’s date/rest
context and the user’s selected venue. Turning scheduled context off uses equal
rest. Selecting the actual venue reproduces the team schedule exactly. Scheduled
games use `predict_game`, including rest/travel context. Neutral FBS forecasts
average both label orientations, canceling home-label margin and probability
intercepts; swapping teams preserves the favorite, spread, and team probabilities.
The cross-division model retains its canonical FBS/FCS orientation. Completed games display actual scores alongside pregame spreads and probabilities.
The exporter preserves eligible predictions from the previous published snapshot
when a game finishes (archived). If none exists, it reconstructs score/efficiency
ratings before kickoff using historical timing buffers and labels the forecast
reconstructed. Reconstructions retain the saved annual priors and calibration;
they are not archived predictions or a substitute for historical backtesting.
`advanced.json.gz` holds the advanced game records needed for reconstruction and
is refreshed together with the other model data.
ESPN logos use the same team IDs and existing Henderson logo helper.

## Automatic updates

The `Update football model` GitHub Actions workflow runs every 30 minutes throughout Saturday
in America/New_York time (including daylight-saving changes), and at 10:25 UTC
Sunday through Friday. It can also be run manually. GitHub scheduled runs may
start later than their scheduled time when runners are busy. It needs the repository Actions secret `CFBD_API_KEY`.
It downloads current-season FBS/FCS games and advanced game statistics, refits
score and efficiency ratings with live completed results, and preserves the
trained preseason priors and margin/calibration layers. This is an in-season
rating update; it does not retrain the historical model architecture every day.
The workflow rejects empty responses or loss of previously completed games.
Failures leave the last published website data intact and appear in Actions.

The workflow commits the model artifact, schedule history, and public snapshot
together to main. The existing hosting integration must deploy main commits
(including github-actions bot commits). Clients revalidate the snapshot every
five minutes. A three-day-old model receives a visible stale
data notice.

The next season needs a newly trained annual model and matching schedule history;
the updater fails explicitly rather than silently applying old annual priors.

## Local export

```sh
pip install -r football-model/requirements.txt
python football-model/export.py             # exact saved-model export
CFBD_API_KEY=... python football-model/export.py --refresh
python -m unittest discover -s football-model -p 'test_*.py'
```

To publish a newly trained CFBPREDICT artifact, replace `football-model/model.json`
with `models/cfbpredict-v2.json` from that project, then run the exporter and commit
the artifact and public snapshot together. `games.json.gz` contains the historical
CFBD schedule/results used by the score model and current season schedule.

## Weekly predictions

`/#/football-model/weekly` groups the shared game forecasts by season type and
week. It defaults to the earliest unfinished game’s week; the selected week is
stored in the URL. Each row includes ESPN logos, model spread, probability-based
winner pick, final score, pick outcome, and absolute margin error.

Season and weekly summaries show winner record/accuracy, mean absolute margin
error, root mean square error, and Brier score. Only completed games with valid
scores and an eligible archived or reconstructed pregame forecast are graded.
Even picks and tied results are excluded from winner accuracy; tied results are
also excluded from binary Brier scoring. Archived-only filtering separates the
published record from retrospective reconstruction. Search and result filters
affect the game list only; summary scopes are explicitly labeled. All data uses
the existing automatic model refresh without a public refresh control.

## AP Poll Predictor

The separate `/football-model/ap-poll` dashboard tab predicts AP voting order,
not the football model's power ratings. It includes a projected next-release
scenario, a completed-results-only alternative, a latest-poll comparison,
searchable Top 25/bubble teams, the full AP archive, and historical validation.
Team logos use ESPN IDs. No API key is present in browser code or public data.

### Data and model

`ap/polls.json.gz` contains all 1,269 archived AP releases from 1936 through
September 8, 2026. College Poll Archive supplies rankings and release labels;
CFBD supplies historical game results and reconciled team identities. CFBD's
rankings endpoint was cross-checked, but missing polls and mismatched postseason
labels made it unsafe as the sole poll source. `ap/coverage.json` records coverage.
Historical source pages use `https://www.collegepollarchive.com/football/ap/seasons.cfm?appollid=ID`.

`ap_model.py` is a standardized weighted ridge model for normalized ranking
position, using prior AP positions/movement, preseason and previous-year rankings,
record, clipped scoring margins, opponent winning percentages, ranked results,
recent outcomes, interactions with the previous ranking, and three-year poll
presence. Every season contributes, with a 20-year weight half-life. It does not
train on a target poll's ranks as features or ingest the strength model's ratings.
The next-release scenario alone uses the strength model's game forecasts to form
hypothetical results. The displayed records explicitly distinguish this scenario.

Training normalizes Top 10/20/25 formats and preserves ties. Rank labels are
normalized ordinal positions, not vote shares; no fake vote totals or calibrated
rank probabilities are displayed. Historical final polls lacking exact release
dates use poll-history features with game results masked rather than guessed.
Preseason polls use no current-season results. Dated polls use a conservative
16:00 UTC cutoff with a four-hour game buffer. Games released later are excluded.
Four wartime polls with unmatched game-universe teams remain in the archive and
lagged history but are excluded as supervised targets. Training through 2025 uses
1,263 polls; 2026 is excluded from fitting.

Evaluation fits a fresh model on strictly earlier seasons for each 2019–2025
in-season test year (102 polls). Results: 1.623 average rank error versus 2.313 for
retaining the previous poll; 89.85% Top 25 membership versus 89.54% for that baseline.
This is chronological historical validation, not an archived live track record.
Rank error scores actual ranked teams and caps unranked model predictions at 26.
Tied published ranks remain ties. Coefficient displays are associations per one
historical standard deviation, not causal explanations.

### Reproduction and updates

```sh
python football-model/train_ap.py --through 2025
python football-model/export_ap.py
python football-model/export_ap.py --refresh
python -m unittest discover -s football-model -p 'test_*.py'
```

Training and publication are independent: the daily football workflow refreshes
AP releases and rebuilds `public/football/ap.json` from the frozen fitted model.
It reads game data from the football snapshot and deduplicates FBS/FCS overlap by
game ID. Failed or unmapped poll downloads abort publication rather than silently
inventing a ranking. The AP refresh does not require or expose an additional key.

The next release date is an estimate of the next Sunday, not an official schedule.
The projected scenario assumes each remaining game is won by the football model's
probability favorite, using its absolute margin (at least one point). These
synthetic outcomes are feature inputs only; they never overwrite actual games.
Daily forecasts are retained when a new official poll arrives, provided the saved
forecast timestamp predates that release. Until such an archive exists, the latest
poll check is explicitly labeled a reconstruction. This is independent of the
completed football-game forecast archive.

When installing a new season's football model, train the AP model through the
previous season after importing its completed poll/result archive. Publication
rejects an AP artifact whose training season does not match that boundary.

## CFP next-release simulations

“Project to next release” defaults to the most likely complete outcome slate:
the favored winner in each game, under independent game outcomes. Left/right
controls browse 25 seeded projections and return to that main scenario.
Completed games stay fixed. Only games whose kickoff plus four hours is at or
before the release cutoff are included, including unfinished in-progress games.
These use saved pregame probabilities, not live win odds. Future injuries and
changes in the game win probabilities are not simulated.

Users can override individual game winners for the 25 teams most frequently in
the next-release Top 25 across 1,000 unmodified simulations. Ties use average rank,
then team name. Eligibility stays fixed while editing. A game has one shared
winner override even when both opponents are eligible. Overrides apply across
all projections and can be cleared individually or together. A new published
snapshot resets local edits and selection. This frequency is not playoff odds.

The shared `src/cfpScenario.mjs` engine rebuilds power ratings, opponent records,
schedule/record strength, quality wins, losses, head-to-head and common-opponent
comparisons. `cfp_scenarios.py` exports the linear response of the Python ridge
fit so browser edits reproduce the same power fit without solving a matrix in
the browser. Cross-language tests check rankings, records, strengths and logos
against the original Python implementation, including forced upsets.

Every scenario uses coherent whole-number records. Hypothetical margin
magnitudes use the football-model estimates rounded to at least one point; the
winner determines the sign. These are not predicted final scores. Game assumptions
remain inspectable. The main scenario is not an average ranking or an expected
win total, and sampled projections may coincide when few uncertain games remain.

`export_cfp.py` now requires Node.js (22 in CI) as well as Python. It invokes
`generate_cfp_scenarios.cjs` to publish the same results and eligibility rules
used in the browser. Model publications regenerate the pool automatically.

Best-win logos show up to three strongest opponents beaten; worst-loss logos
show up to three weakest opponents lost to. Ordering uses opponent-adjusted
strength from that same resume snapshot, with the committee model's division
fallback for opponents without FBS ratings. No results displays as “None.”

AP and CFP next-release projections include unfinished games even after kickoff,
provided they fit before the release cutoff. Partial scores never become final
resume results: the saved football prediction supplies the projected outcome
until the feed marks the game completed. AP custom scenarios inherit these
defaults; the score editor still only permits edits to games before kickoff.

## Pregame spread archive and reconstruction audit

The updater writes to the existing `hendersonviewership` Firestore project in a
separate `football-pregame-forecasts` collection; viewership documents are untouched.
Each `{season}_{gameId}` document holds the latest verified pregame forecast, with
all timestamped versions under its `versions` subcollection. Content-derived IDs
make retries idempotent. Versions store the complete margin/probability output,
teams, venue flag, kickoff, model cutoff, observation time, and provenance.
The server credential is the GitHub secret `FIREBASE_CREDENTIALS_JSON`; it is never
included in browser files. A missing credential stops the scheduled publisher.

A live forecast must be generated and observed strictly before kickoff to enter
the archive. Historical imports require a pre-kickoff Git commit as well as a
pre-kickoff generation and model timestamp. Reconstructed forecasts are never
imported as originals. The parent document advances transactionally only to a
later observation; previous versions remain available.

Once kickoff passes, the schedule freezes the latest eligible archived forecast,
even while the game remains in progress. Firestore can restore it if the previous
JSON snapshot loses it. Original lines take priority over reconstruction. The
public row carries its archive ID and provenance when available.

Reconstruction refits score and efficiency ratings at kickoff using historical
availability buffers and excludes target/later outcomes and advanced statistics.
It retains the installed annual priors, calibration and margin layers, and may
use subsequently corrected historical source data. It is therefore a retrospective
estimate, not proof of a line actually published at that time. Run
`python football-model/audit_reconstructions.py` to compare every displayed
reconstruction to its cutoff-model calculation. Tests also perturb target/later
scores and efficiency data to verify that those cannot affect the result.

If Firebase reports quota exhaustion, `forecast-archive-pending.json.gz` keeps
all unacknowledged versions in Git. Every refresh merges that queue with new
forecasts, retries missing version writes, and transactionally advances the
latest pointers. Already stored versions are skipped. The queue clears only
after both versions and pointers succeed. The exporter can restore historical
lines directly from the queue while Firebase is unavailable. The September 13
backfill hit Firebase's quota; increasing Firebase capacity may be necessary
for every-half-hour archiving of the full future schedule.
