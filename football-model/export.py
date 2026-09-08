"""Publish one coherent model snapshot; optionally refresh CFBD results first."""
import argparse
import gzip
import json
import os
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
    return records


def export(model, records, output):
    games = [g for g in normalize_games(records) if g.season == model.season]
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
        # Finished games show actual results, never a hindsight forecast.
        prediction = None if game.completed else asdict(model.predict_game(game, games))
        scheduled.append(dict(id=game.id, week=game.week, date=game.start_date.isoformat(),
            home=game.home_team, away=game.away_team, neutral=game.neutral_site,
            homeLogo=f"https://a.espncdn.com/i/teamlogos/ncaa/500/{game.home_id}.png" if game.home_id else None,
            awayLogo=f"https://a.espncdn.com/i/teamlogos/ncaa/500/{game.away_id}.png" if game.away_id else None,
            completed=game.completed, homePoints=game.home_points, awayPoints=game.away_points,
            prediction=prediction))
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
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'public/football/model.json')
    args = parser.parse_args()
    model = CollegeFootballV2Model.load(args.model)
    with gzip.open(args.games, 'rt') as f:
        records = json.load(f)
    if args.refresh:
        records = refresh(model, records)
    export(model, records, args.output)
    if args.refresh:
        model.save(args.model)
        with gzip.open(args.games, 'wt') as f:
            json.dump(records, f, separators=(',', ':'))
