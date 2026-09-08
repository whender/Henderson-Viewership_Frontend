# Henderson Football Model

The separate `/#/football-model` dashboard is powered by the CFBPREDICT V2 model,
initially imported from the September 8, 2026 artifact. `cfbpredict/` is the Python
model runtime from that project; `model.json` retains its fitted priors, calibration,
margin layers, and FBS/FCS components. No API credential is shipped to the browser.

The Top 25 is the model's symmetric neutral-field ranking, not a poll. All 138 FBS
teams have profiles. The hypothetical predictor uses precomputed outputs of the
actual model for every ordered pair at both home and neutral sites. Scheduled
games use `predict_game`, including rest/travel context. Completed games display
actual scores only, avoiding forecasts contaminated by their own outcomes.
ESPN logos use the same team IDs and existing Henderson logo helper.

## Automatic updates

The `Update football model` GitHub Actions workflow runs daily at 10:25 UTC and
can also be run manually. It needs the repository Actions secret `CFBD_API_KEY`.
It downloads current-season FBS/FCS games and advanced game statistics, refits
score and efficiency ratings with live completed results, and preserves the
trained preseason priors and margin/calibration layers. This is an in-season
rating update; it does not retrain the historical model architecture every day.
The workflow rejects empty responses or loss of previously completed games.
Failures leave the last published website data intact and appear in Actions.

The workflow commits the model artifact, schedule history, and public snapshot
together to main. The existing hosting integration must deploy main commits
(including github-actions bot commits). Clients revalidate the snapshot every
five minutes and on Refresh data. A three-day-old model receives a visible stale
data notice. Refresh data retrieves published data; it does not launch training.

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
