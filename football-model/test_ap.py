import gzip,json,unittest
from pathlib import Path
import numpy as np
from ap_model import matrix,FEATURES,fit,predict,finished,timestamp
from ap_data import normalize_poll
ROOT=Path(__file__).resolve().parent

def poll(id,day,rank=1):
 return {'id':id,'season':2025,'kind':'regular','cutoff':f'2025-09-{day:02d}T16:00:00+00:00','size':25,'ranks':[{'teamId':1,'school':'A','rank':rank}]}
GAME={'id':1,'season':2025,'week':1,'seasonType':'regular','startDate':'2025-09-06T20:00:00Z','completed':True,'homeId':1,'awayId':2,'homeTeam':'A','awayTeam':'B','homePoints':28,'awayPoints':14,'homeClassification':'fbs','awayClassification':'fbs'}
class APTests(unittest.TestCase):
 def test_target_poll_rank_cannot_change_features(self):
  previous=poll(1,1);target=poll(2,7)
  a,teams=matrix(target,previous,[previous],[GAME]);b,_=matrix({**target,'ranks':[{'teamId':2,'rank':1}]},previous,[previous],[GAME])
  np.testing.assert_array_equal(a,b);self.assertEqual(teams[0]['wins'],1)
 def test_future_results_do_not_enter_features(self):
  p=poll(2,7);prev=poll(1,1);future={**GAME,'id':2,'startDate':'2025-09-13T20:00:00Z','homePoints':100}
  a,_=matrix(p,prev,[prev],[GAME,future]);b,_=matrix(p,prev,[prev],[GAME,{**future,'homePoints':0}]);np.testing.assert_array_equal(a,b)
  self.assertFalse(finished(GAME,timestamp('2025-09-06T22:00:00Z')))
 def test_undated_final_masks_results(self):
  p={**poll(2,7),'kind':'final','cutoff':None};x,t=matrix(p,poll(1,1),[poll(1,1)],[GAME]);self.assertTrue(np.all(x[:,FEATURES.index('results_unavailable')]==1));self.assertEqual(t[0]['wins'],0)
 def test_training_excludes_later_year_labels(self):
  rng=np.random.default_rng(1);x=rng.normal(size=(50,len(FEATURES)))
  early={'season':2024,'x':x,'y':np.linspace(0,1,50)};late={'season':2025,'x':x,'y':np.ones(50)}
  a=fit([early,late],2024);b=fit([early,{**late,'y':np.zeros(50)}],2024);np.testing.assert_array_equal(a['coefficients'],b['coefficients']);self.assertTrue(np.isfinite(predict(a,x)).all())
 def test_complete_archive_and_known_final(self):
  polls=json.loads(gzip.decompress((ROOT/'ap/polls.json.gz').read_bytes()))
  self.assertEqual(min(p['season'] for p in polls),1936);self.assertGreaterEqual(len(polls),1269);self.assertEqual(len({p['id'] for p in polls}),len(polls))
  final=next(p for p in polls if p['season']==2002 and p['kind']=='final');self.assertEqual(next(r['school'] for r in final['ranks'] if r['rank']==1),'Ohio State')
  self.assertEqual(next(p for p in polls if p['season']==1961)['size'],10)
 def test_snapshot_has_unique_games_and_ranked_teams(self):
  data=json.loads((ROOT.parent/'public/football/ap.json').read_text());self.assertLess(data['trainingThrough'],data['season'])
  self.assertEqual(len({g['id'] for g in data['next']['assumptions']}),len(data['next']['assumptions']))
  for field in ['rows','resultsSoFar']:
   rows=data['next'][field];self.assertEqual([r['rank'] for r in rows],list(range(1,41)));self.assertEqual(len({r['teamId'] for r in rows}),40)
  self.assertGreaterEqual(data['overallEvaluation']['polls'],100)
 def test_alias_and_date_alignment(self):
  p=normalize_poll({'season':1936,'id':1,'label':'October 19','ranks':[{'rank':1,'school':'Minnesota','archiveTeamId':1}]},{'minnesota':{'teamId':135,'team':'Minnesota'}})
  self.assertEqual(p['releaseDate'],'1936-10-19');self.assertEqual(p['ranks'][0]['teamId'],135)
if __name__=='__main__':unittest.main()
