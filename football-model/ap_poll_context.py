"""Previous AP vote support and season-specific conference indicators."""
import re
import numpy as np
from ap_data import clean,token
GROUPS=['ACC','Big Ten','Big 12','SEC','Pac-12','AAC','MWC','MAC','CUSA','Sun Belt','Independent','Other']
VOTE_FEATURES=['prior_points_share','prior_receiving_votes','prior_unranked_points_share','prior_points_vs_25','prior_votes_missing']
CONF_FEATURES=['conference_'+k for k in GROUPS]+['unranked_conference_'+k for k in GROUPS]


def parse_votes(text,identities):
    out=[]
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',text,re.S):
        cells=re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)
        if len(cells)<7:continue
        rank=clean(cells[0])
        if rank!='RV' and not rank.isdigit():continue
        link=re.search(r'teams/by_season.cfm\?seasonid=\d+&(?:amp;)?teamid=(\d+)[^>]*>(.*?)</a>',cells[3],re.S)
        if not link:continue
        school=clean(link[2]);identity=identities.get(token(school));points=clean(cells[6]).replace(',','')
        if not identity or not points.isdigit():raise ValueError(f'Unmapped team or missing vote total: {school}')
        out.append({'teamId':identity['teamId'],'team':identity['team'],'rank':None if rank=='RV' else int(rank),'points':int(points)})
    if sum(r['rank'] is not None for r in out)<25:raise ValueError('Incomplete Top25 vote table')
    if len({str(r['teamId']) for r in out})!=len(out):raise ValueError('Duplicate vote entries')
    return out


def conference_group(value):
    return {'ACC':'ACC','Atlantic Coast':'ACC','Big Ten':'Big Ten','Big 12':'Big 12','SEC':'SEC','Southeastern':'SEC','Pac-12':'Pac-12','Pac-10':'Pac-12','American Athletic':'AAC','American':'AAC','AAC':'AAC','Mountain West':'MWC','MWC':'MWC','Mid-American':'MAC','MAC':'MAC','Conference USA':'CUSA','CUSA':'CUSA','C-USA':'CUSA','Sun Belt':'Sun Belt','FBS Independents':'Independent','Independent':'Independent','Ind':'Independent'}.get(value,'Other')


def features(teams,previous,target,votes):
    # Explicit ID/season check guards against accidentally passing the target poll.
    if previous and ((target.get('id') is not None and previous['id']>=target['id']) or previous['season']>target['season']):raise ValueError('Prior poll must precede target')
    entries=votes.get(str(previous['id'])) if previous else None
    points={str(r['teamId']):r['points'] for r in entries or []}
    ranked={str(r['teamId']) for r in previous['ranks'] if r['rank']<=25} if previous else set()
    total=sum(points.values());maxpoints=total/13 if total else 1
    threshold=min((r['points'] for r in entries or [] if r['rank'] is not None and r['rank']<=25),default=1)
    rv=[];conf=[]
    for t in teams:
        key=str(t['teamId']);p=points.get(key,0);unranked=key not in ranked;group=conference_group(t.get('conference'));one=[float(group==g) for g in GROUPS]
        rv.append([p/maxpoints,float(unranked and p>0),p/maxpoints*unranked,min(p/max(threshold,1),3),float(entries is None)])
        conf.append(one+[v*unranked for v in one])
    return np.asarray(rv),np.asarray(conf)


