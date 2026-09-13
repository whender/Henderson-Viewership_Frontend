import unittest
from ap_official_updates import merge_updates
class OfficialUpdateTests(unittest.TestCase):
 def test_add_once_and_replace_when_archive_catches_up(self):
  p={'id':10.5,'season':2026,'releaseDate':'2026-09-13','provisionalId':True};u={'poll':p,'votes':[{'teamId':1,'points':100}]}
  polls,votes=merge_updates([],{},[u]);self.assertEqual(len(polls),1)
  polls,votes=merge_updates(polls,votes,[u]);self.assertEqual(len(polls),1)
  real={**p,'id':11};real.pop('provisionalId');polls,votes=merge_updates(polls+[real],votes,[u])
  self.assertEqual(polls,[real]);self.assertEqual(votes['11'],u['votes'])
