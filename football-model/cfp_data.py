"""Read dated rankings from the CFP's official history page; never execute scripts."""
import json,re
from datetime import datetime
from cfbpredict.committee_history import build_resume_state,_team_token

HISTORY_URL='https://collegefootballplayoff.com/sports/2026/8/9/wk-x-wk-rankings'

def parse_rankings(text, known=(), season_filter=None):
    marker=re.search(r'const\s+RANKINGS_DATA\s*=\s*',text)
    if not marker:raise ValueError('Official CFP archive format changed')
    # Quote object keys while preserving string literals. Parse data, never eval JS.
    source=re.sub(r'("(?:\\.|[^"\\])*")|([A-Za-z_]\w*)(?=\s*:)',
        lambda m:m[1] if m[1] else json.dumps(m[2]),text[marker.end():])
    source=re.sub(r',([\s]*[}\]])',r'\1',source)
    data,_=json.JSONDecoder().raw_decode(source)
    polls={}
    for season in data:
        year=int(season['label'])
        if season_filter is not None and year!=season_filter:continue
        for i,week in enumerate(season['weeks']):
            label=week['sub'] if week.get('isSelection') else week['label']
            day=datetime.strptime(f'{year} {label}','%Y %B %d').date().isoformat()
            if (year,day) in known:continue
            entries=[{'team':team['name'],'rank':int(team['ranks'][i])} for team in season['teams'] if str(team['ranks'][i]).isdigit()]
            if len(entries)!=25 or {e['rank'] for e in entries}!=set(range(1,26)) or len({e['team'] for e in entries})!=25:
                raise ValueError('Incomplete or duplicate official CFP ranking')
            polls[(year,day)]=sorted(entries,key=lambda e:e['rank'])
    return polls

def import_new_polls(text,existing,games,now):
    known={(p['season'],p['release_date']) for p in existing};output=list(existing)
    for (year,day),entries in sorted(parse_rankings(text,known,now.year).items()):
        if (year,day) in known or day>now.date().isoformat():continue
        cutoff=datetime.fromisoformat(day+'T12:00:00+00:00')
        resumes,_=build_resume_state([g for g in games if g.season==year],cutoff)
        lookup={_team_token(r.team):r for r in resumes.values()}
        normalized=[]
        for entry in entries:
            resume=lookup.get(_team_token(entry['team']))
            if resume is None:raise ValueError('CFP ranked team missing from game results: '+entry['team'])
            normalized.append({**entry,'record':f'{resume.wins}-{resume.losses}'})
        output.append({'season':year,'release_date':day,'week':1+sum(p['season']==year for p in output),'entries':normalized})
    return sorted(output,key=lambda p:p['release_date'])
