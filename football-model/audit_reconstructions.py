"""Recheck every published reconstructed margin and probability against the cutoff model."""
import gzip,json
from dataclasses import asdict
from pathlib import Path
from export import reconstruct_pregame
from cfbpredict.games import normalize_games
from cfbpredict.v2 import CollegeFootballV2Model
ROOT=Path(__file__).parent

def main():
    model=CollegeFootballV2Model.load(ROOT/'model.json')
    games=normalize_games(json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes())))
    advanced=json.loads(gzip.decompress((ROOT/'advanced.json.gz').read_bytes()))
    snapshot=json.loads((ROOT.parent/'public/football/model.json').read_text());lookup={g.id:g for g in games};cache={};checked=0
    for row in snapshot['games']:
        if row['predictionSource']!='reconstructed':continue
        game=lookup[row['id']]
        if game.start_date not in cache:cache[game.start_date]=reconstruct_pregame(model,games,advanced,game.start_date)
        p=asdict(cache[game.start_date].predict_game(game,[g for g in games if g.season==game.season]))
        for field in ('predicted_margin','home_win_probability','away_win_probability'):
            if abs(p[field]-row['prediction'][field])>1e-9:raise ValueError(f"Reconstruction mismatch: {game.id} {field}")
        checked+=1
    print(f'Verified {checked} reconstructed forecasts against cutoff models.')
if __name__=='__main__':main()
