"""Publish one coherent model snapshot; optionally refresh CFBD results first."""
import argparse
import gzip
import json
import os
from copy import copy
from dataclasses import asdict, replace
from datetime import UTC, datetime
from pathlib import Path

from cfbpredict.cfbd import CFBDClient
from cfbpredict.efficiency import OpponentAdjustedEfficiencyModel
from cfbpredict.fcs import division_games
from cfbpredict.games import atomic_write_json, normalize_games
from cfbpredict.model import PointRatingModel
from cfbpredict.v2 import CollegeFootballV2Model

ROOT = Path(__file__).resolve().parent


def refresh(model, records):
    now = datetime.now(UTC)
    if now.year != model.season:
        raise ValueError('Install the new season model before refreshing a different year.')
    key = os.environ.get('CFBD_API_KEY')
    if not key:
        raise ValueError('Configure the CFBD_API_KEY repository secret to enable daily updates.')
    with CFBDClient(key) as client:
        fresh = client.get_games(model.season, classification='fbs', refresh=True)
        fresh += client.get_games(model.season, classification='fcs', refresh=True)
        advanced = client.get_advanced_game_stats(model.season, refresh=True)
    if not fresh or not advanced:
        raise ValueError('Incomplete CFBD response; keeping the last published snapshot.')
    old_finished = {r['id'] for r in records if r.get('season') == model.season and r.get('completed')}
    new_finished = {r['id'] for r in fresh if r.get('completed')}
    if not old_finished <= new_finished:
        raise ValueError('CFBD response lost completed games; refusing to publish.')
    records = [r for r in records if r.get('season') != model.season] + fresh
    games = normalize_games(records)
    for component in (model, model.fcs_model):
        if component is None:
            continue
        fitting_games = division_games(games) if not component.efficiency.config.fbs_only else games
        component.baseline = PointRatingModel(component.baseline.config).fit(
            fitting_games, as_of=now, live_results=True)
        component.efficiency = OpponentAdjustedEfficiencyModel(component.efficiency.config).fit(
            advanced, [g for g in fitting_games if g.season == model.season],
            as_of=now, priors=component.efficiency.priors.values(), live_results=True)
        component.as_of = now
    return records, advanced


def reconstruct_pregame(model, history, advanced, kickoff):
    """Refit score/efficiency before kickoff; retain the saved annual model layers."""
    reconstructed = copy(model)
    reconstructed.fcs_model = copy(model.fcs_model) if model.fcs_model else None
    for component in (reconstructed, reconstructed.fcs_model):
        if component is None:
            continue
        fitting = division_games(history) if not component.efficiency.config.fbs_only else history
        component.as_of = kickoff
        # Historical timing buffers exclude the target game and later outcomes.
        component.baseline = PointRatingModel(component.baseline.config).fit(fitting, as_of=kickoff)
        component.efficiency = OpponentAdjustedEfficiencyModel(component.efficiency.config).fit(
            advanced, [g for g in fitting if g.season == model.season], as_of=kickoff,
            priors=component.efficiency.priors.values())
    return reconstructed


def saved_pregame(previous, game, snapshot_as_of):
    """Reuse an actual prior forecast only when its cutoff predates this kickoff."""
    if not previous or not previous.get('prediction'):
        return None
    if (previous['home'], previous['away'], previous['neutral'], previous['date']) != (
            game.home_team, game.away_team, game.neutral_site, game.start_date.isoformat()):
        return None
    cutoff = previous.get('predictionAsOf') or snapshot_as_of
    if not cutoff:
        return None
    time = datetime.fromisoformat(cutoff)
    source = previous.get('predictionSource', 'current')
    if time > game.start_date or (time == game.start_date and source != 'reconstructed'):
        return None
    return previous['prediction'], 'reconstructed' if source == 'reconstructed' else 'archived', cutoff


def export(model, records, output, advanced):
    history = normalize_games(records)
    games = [g for g in history if g.season == model.season]
    previous_snapshot = json.loads(output.read_text()) if output.exists() else {}
    previous_games = {g['id']: g for g in previous_snapshot.get('games', [])}
    pregame_models = {}
    rankings = model.rankings()
    teams = []
    for rank, row in enumerate(rankings, 1):
        teams.append(dict(asdict(row), rank=rank,
                          logo=f'https://a.espncdn.com/i/teamlogos/ncaa/500/{row.team_id}.png'))
    scheduled = []
    fbs_names = {t["team"] for t in teams}
    for game in games:
        if game.home_team not in fbs_names and game.away_team not in fbs_names:
            continue
        source, cutoff = 'current', model.as_of.isoformat()
        if game.completed:
            saved = saved_pregame(previous_games.get(game.id), game, previous_snapshot.get('asOf'))
            if saved:
                prediction, source, cutoff = saved
            else:
                if game.start_date not in pregame_models:
                    pregame_models[game.start_date] = reconstruct_pregame(
                        model, history, advanced, game.start_date)
                pregame = pregame_models[game.start_date]
                prediction = asdict(pregame.predict_game(game, games))
                source, cutoff = 'reconstructed', game.start_date.isoformat()
        else:
            prediction = asdict(model.predict_game(game, games))
        scheduled.append(dict(id=game.id, week=game.week, date=game.start_date.isoformat(),
            home=game.home_team, away=game.away_team, neutral=game.neutral_site,
            homeLogo=f"https://a.espncdn.com/i/teamlogos/ncaa/500/{game.home_id}.png" if game.home_id else None,
            awayLogo=f"https://a.espncdn.com/i/teamlogos/ncaa/500/{game.away_id}.png" if game.away_id else None,
            completed=game.completed, homePoints=game.home_points, awayPoints=game.away_points,
            prediction=prediction, predictionSource=source, predictionAsOf=cutoff))
    # Use the actual Python model for every ordered matchup/site, not rating subtraction.
    matchups = {}
    for home in teams:
        for away in teams:
            if home['team_id'] == away['team_id']:
                continue
            for neutral in (False, True):
                p = model.predict(home['team'], away['team'], neutral_site=neutral)
                matchups[f"{home['team_id']}:{away['team_id']}:{int(neutral)}"] = [
                    round(p.predicted_margin, 6), round(p.home_win_probability, 8)]
    scheduled_matchups = {}
    # Earliest remaining meeting supplies the date/rest context for this pair.
    for game in sorted(games, key=lambda g: (g.start_date, g.id)):
        if game.completed or game.home_team not in fbs_names or game.away_team not in fbs_names:
            continue
        for swapped in (False, True):
            oriented = replace(
                game, home_team=game.away_team, home_id=game.away_id,
                away_team=game.home_team, away_id=game.home_id,
            ) if swapped else game
            for neutral in (False, True):
                key = f"{oriented.home_id}:{oriented.away_id}:{int(neutral)}"
                if key in scheduled_matchups:
                    continue
                p = model.predict_game(replace(oriented, neutral_site=neutral), games)
                scheduled_matchups[key] = dict(
                    gameId=game.id, date=game.start_date.isoformat(),
                    margin=p.predicted_margin, probability=p.home_win_probability,
                    actualHome=game.home_team, actualAway=game.away_team,
                    actualNeutral=game.neutral_site,
                )
    payload = dict(schemaVersion=1, season=model.season, asOf=model.as_of.isoformat(),
                   generatedAt=datetime.now(UTC).isoformat(), teams=teams, games=scheduled,
                   matchups=matchups, scheduledMatchups=scheduled_matchups)
    atomic_write_json(output, payload)
    print(f'Published {len(teams)} teams, {len(scheduled)} games, {len(matchups)} matchups.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--refresh', action='store_true')
    parser.add_argument('--model', type=Path, default=ROOT / 'model.json')
    parser.add_argument('--games', type=Path, default=ROOT / 'games.json.gz')
    parser.add_argument('--advanced', type=Path, default=ROOT / 'advanced.json.gz')
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'public/football/model.json')
    args = parser.parse_args()
    model = CollegeFootballV2Model.load(args.model)
    with gzip.open(args.games, 'rt') as f:
        records = json.load(f)
    with gzip.open(args.advanced, 'rt') as f:
        advanced = json.load(f)
    if args.refresh:
        records, advanced = refresh(model, records)
    export(model, records, args.output, advanced)
    if args.refresh:
        model.save(args.model)
        with gzip.open(args.advanced, 'wt') as f:
            json.dump(advanced, f, separators=(',', ':'))
        with gzip.open(args.games, 'wt') as f:
            json.dump(records, f, separators=(',', ':'))
