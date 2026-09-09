"""Fit all historical CFP polls; evaluate each later season without future labels."""
import gzip,json
from pathlib import Path
from cfbpredict.games import Game
from cfbpredict.committee import CommitteeModel
from cfbpredict.committee_data import load_committee_polls
from cfbpredict.committee_history import build_historical_committee_snapshots,build_committee_training_observations,evaluate_committee_model
from cfbpredict.committee_training import fit_committee_model,CommitteeTrainingConfig
ROOT=Path(__file__).parent

def main():
    polls=load_committee_polls(ROOT/'cfp/polls.json')
    games=[Game.from_cfbd(g) for g in json.loads(gzip.decompress((ROOT/'games.json.gz').read_bytes()))]
    snapshots=build_historical_committee_snapshots(polls,games)
    through=max(p.season for p in polls);evaluation=[];reconstructed={}
    for year in range(2019,through+1):
        earlier=[s for s in snapshots if s.poll.season<year]
        target=[s for s in snapshots if s.poll.season==year]
        model=fit_committee_model(build_committee_training_observations(earlier),config=CommitteeTrainingConfig(ridge_alpha=800.),provenance=f'CFP polls through {year-1}')
        result={'season':year,**evaluate_committee_model(model,target)}
        result['baseline']=evaluate_committee_model(CommitteeModel.protocol_default(),target)
        evaluation.append(result);print('CFP validation',result,flush=True)
        for snapshot in target:
            reconstructed[snapshot.poll.release_date.isoformat()]=[{'team':r.team,'key':r.key,'rank':r.rank} for r in model.rank(snapshot.resumes,snapshot.results)]
    model=fit_committee_model(build_committee_training_observations(snapshots),config=CommitteeTrainingConfig(ridge_alpha=800.),provenance=f'CFP weekly polls 2014–{through}, {len(polls)}-poll archive; outcome-only historical fits')
    model.save(ROOT/'cfp/model.json')
    report={'trainingThrough':through,'trainingPolls':len(polls),'startYear':min(p.season for p in polls),'evaluation':evaluation,'reconstructed':reconstructed}
    (ROOT/'cfp/validation.json').write_text(json.dumps(report,separators=(',',':'),allow_nan=False)+'\n')
    print('Trained CFP model on',len(polls),'polls',flush=True)
if __name__=='__main__':main()
