"""Parse official AP rankings reproduced by College Poll Archive."""
import re,html,unicodedata
from datetime import datetime
ALIASES={'southerncalifornia':'usc','southerncal':'usc','miamifl':'miami','miamiflorida':'miami','miamiohio':'miamioh','brighamyoung':'byu','texaschristian':'tcu','louisianastate':'lsu','mississippi':'olemiss','pittsburghuniversity':'pittsburgh','pitt':'pittsburgh','appalachianstate':'appstate','sanjosestate':'sanjosestate','louisianalafayette':'louisiana','louisianamonroe':'ulmonroe','texaselpaso':'utep','pennsylvania':'penn','southernmethodist':'smu','centralflorida':'ucf','alabamabirmingham':'uab','bowlinggreenstate':'bowlinggreen','texassanantonio':'utsa','ncstate':'ncstate','northcarolinastate':'ncstate','calstatesacramento':'sacramentostate'}
ALIASES.update({'boston':'bostonuniversity','connecticut':'uconn','detroit':'detroitmercy','newyork':'newyorkuniversity','washingtonlee':'washingtonandlee','southwestern':'southwesternu','stmarys':'saintmarysca','stmaryspreflight':'saintmaryscapreflight','2ndairforce':'secondairforce','3rdairforce':'thirdairforce','bainbridgenaval':'bainbridgents','fortpiercenaval':'fortpierce','greatlakesnaval':'greatlakesnavy','memphisnaval':'memphisnavy','sandiegonaval':'sandiegonavy','normanpreflight':'normannavalairstation','marchfield4thaf':'marchfield'})
def token(s):
    t=''.join(c.lower() for c in unicodedata.normalize('NFKD',s) if c.isalnum() and not unicodedata.combining(c))
    return ALIASES.get(t,t)
def clean(s):return html.unescape(re.sub('<[^>]*>','',s)).strip()
def parse_options(text):
    m=re.search(r'<select name="appollid".*?</select>',text,re.S)
    if not m:raise ValueError('AP archive did not provide a poll selector')
    return [{'id':int(i),'label':clean(t)} for i,t in re.findall(r'<option value="(\d+)"[^>]*>(.*?)</option>',m.group(),re.S)]
def parse_entries(text):
    entries=[]
    for tr in re.findall(r'<tr[^>]*>(.*?)</tr>',text,re.S):
        cells=re.findall(r'<td[^>]*>(.*?)</td>',tr,re.S)
        if len(cells)<7 or not clean(cells[0]).isdigit():continue
        link=re.search(r'teams/by_season.cfm\?seasonid=\d+&(?:amp;)?teamid=(\d+)[^>]*>(.*?)</a>',cells[3],re.S)
        if link:entries.append({'rank':int(clean(cells[0])),'school':clean(link[2]),'archiveTeamId':int(link[1]),'conference':clean(cells[4]),'record':clean(cells[5]),'points':clean(cells[6])})
    if len(entries)<10:raise ValueError('Incomplete AP poll; keeping previous snapshot')
    return entries

def normalize_poll(p,lookup):
    year=p['season'];label=p['label'];kind='preseason' if label=='Preseason' else 'final' if label=='Final' else 'regular'
    cutoff=None;release=None
    if kind=='regular':
        dt=datetime.strptime(f'{label} {year}','%B %d %Y');dt=dt.replace(year=year+1 if dt.month<3 else year)
        cutoff=dt.strftime('%Y-%m-%dT16:00:00+00:00');release=dt.strftime('%Y-%m-%d')
    if kind=='preseason':cutoff=f'{year}-07-01T00:00:00+00:00'
    size=25 if year>=1989 else 10 if 1961<=year<=1967 else 20
    entries=[]
    for r in p['ranks']:
        key=token(r['school']);identity=lookup.get(key)
        entries.append({**r,'teamId':identity['teamId'] if identity else f"archive:{r['archiveTeamId']}", 'school':identity['team'] if identity else r['school']})
    return {**p,'ranks':entries,'kind':kind,'cutoff':cutoff,'releaseDate':release,'size':size}
