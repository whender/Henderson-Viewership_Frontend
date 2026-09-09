import unittest
import numpy as np
import ap_poll_context as c

class PollContextTests(unittest.TestCase):
    def test_only_previous_votes_used_and_flags_distinguish_unranked(self):
        p={'id':1,'season':2026,'ranks':[{'teamId':1,'rank':25}]};target={'id':2,'season':2026}
        teams=[{'teamId':2,'conference':'ACC'},{'teamId':3,'conference':'Mid-American'}]
        votes={'1':[{'teamId':1,'rank':25,'points':100},{'teamId':2,'rank':None,'points':50}]}
        a,b=c.features(teams,p,target,votes);votes['2']=[{'teamId':3,'rank':1,'points':1600}]
        x,y=c.features(teams,p,target,votes);np.testing.assert_array_equal(a,x);np.testing.assert_array_equal(b,y)
        self.assertEqual(a[0,1],1);self.assertEqual(a[0,3],.5);self.assertEqual(a[1,1],0)
        self.assertEqual(b[0,c.GROUPS.index('ACC')],1);self.assertEqual(b[1,c.GROUPS.index('MAC')],1)

    def test_target_poll_cannot_be_previous(self):
        p={'id':2,'season':2026,'ranks':[]}
        with self.assertRaises(ValueError):c.features([],p,p,{})

    def test_conference_uses_historical_metadata(self):
        p={'id':1,'season':2020,'ranks':[]};target={'id':2,'season':2020}
        _,a=c.features([{'teamId':2483,'conference':'Pac-12'}],p,target,{})
        self.assertEqual(a[0,c.GROUPS.index('Pac-12')],1)
        self.assertEqual(a[0,c.GROUPS.index('Big Ten')],0)

    def test_rv_parser_preserves_points_and_unranked_status(self):
        def tr(rank,i):return f'<tr><td>{rank}</td><td></td><td></td><td><a href="teams/by_season.cfm?seasonid=2026&amp;teamid={i}">Team{i}</a></td><td>ACC</td><td>0-0</td><td>5</td></tr>'
        ids={c.token(f'Team{i}'):{'teamId':i,'team':f'Team{i}'} for i in range(1,27)}
        rows=c.parse_votes(''.join(tr(i,i) for i in range(1,26))+tr('RV',26),ids)
        self.assertEqual(len(rows),26);self.assertIsNone(rows[-1]['rank']);self.assertEqual(rows[-1]['points'],5)

if __name__=='__main__':unittest.main()
