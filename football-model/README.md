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

“Project to next release” uses 10,000 seeded simulations of the eligible remaining
games, sampling each outcome from its current football-model win probability.
Completed games stay fixed. Only games whose kickoff plus four hours precedes the
release cutoff are included. Probabilities remain fixed through each simulation;
future injuries and rating changes are not modeled.

The exporter rounds simulated mean remaining wins to whole numbers, then selects
the sampled result slate with the smallest total squared deviation from those
team targets. Ties favor the more probable slate. A single consistent slate is
necessary for head-to-head results, quality wins, opponent records and losses;
individual records may differ from independently rounded means. The CFP model
ranks that slate's resumes, not averaged rankings. Scoring-margin magnitudes use
the football model estimates, rounded to at least one point, with the sampled
winner determining the sign. These are hypothetical margins, not predicted final
scores. The selected results remain inspectable under Game assumptions.

The seed and simulation count are published in `next.simulation`. Refreshes
regenerate the projection as actual results and game probabilities change.

The projected CFP table exposes up to 25 distinct representative outcomes from
that simulation pool. “Refresh simulation” randomly selects a different saved
outcome, updating rankings, whole-number records, game assumptions, and opponent
logos together. It does not contact an API or generate a fresh pool on each click.
The pool is regenerated during normal model publication. Duplicate Top 40
rank/record combinations are removed; if only one outcome exists, the button is
hidden. Completed-only rankings remain independent of this selection.

Best-win logos show up to three strongest opponents beaten; worst-loss logos
show up to three weakest opponents lost to. Ordering uses opponent-adjusted
strength from that same resume snapshot, with the committee model's division
fallback for opponents without FBS ratings. No results displays as “None.”

AP and CFP next-release projections include unfinished games even after kickoff,
provided they fit before the release cutoff. Partial scores never become final
resume results: the saved football prediction supplies the projected outcome
until the feed marks the game completed. AP custom scenarios inherit these
defaults; the score editor still only permits edits to games before kickoff.
