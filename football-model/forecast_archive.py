"""Server-only, content-addressed pregame forecast history in Henderson Firestore."""
import hashlib,json,os,gzip
from pathlib import Path
from google.api_core.retry import Retry
from datetime import datetime,timezone
from google.cloud import firestore
from google.cloud.firestore_v1.base_query import FieldFilter
from google.oauth2 import service_account

COLLECTION='football-pregame-forecasts'
def timestamp(value):return datetime.fromisoformat(value.replace('Z','+00:00'))

def client():
    raw=os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if not raw:raise ValueError('FIREBASE_CREDENTIALS_JSON is required for the forecast archive')
    info=json.loads(raw)
    if info['project_id']!='hendersonviewership':raise ValueError('Unexpected forecast archive Firebase project')
    return firestore.Client(project=info['project_id'],credentials=service_account.Credentials.from_service_account_info(info))

def records(snapshot,observed_at,provenance):
    """Require forecast generation AND independent observation strictly before kickoff."""
    output=[]
    for g in snapshot['games']:
        cutoff=g.get('predictionAsOf') or snapshot['asOf']
        if not g.get('prediction') or g.get('predictionSource','current')!='current' or g['completed']:continue
        if max(timestamp(cutoff),timestamp(snapshot.get('generatedAt',snapshot['asOf'])),timestamp(observed_at))>=timestamp(g['date']):continue
        payload={k:g[k] for k in ['id','date','home','away','neutral','prediction']}
        payload.update(season=snapshot['season'],predictionAsOf=cutoff,predictionSource='archived',observedAt=observed_at,provenance=provenance)
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        output.append({**payload,'archiveId':digest})
    return output

def load(db,season):
    return {int(d.to_dict()['id']):d.to_dict() for d in db.collection(COLLECTION).where(filter=FieldFilter('season','==',season)).stream()}

def save(db,entries):
    """Identical IDs have identical content; retries cannot rewrite forecast values."""
    entries=list({e['archiveId']:e for e in entries}.values())
    latest={}
    for e in entries:
        key=(e['season'],e['id'])
        if key not in latest or timestamp(e['observedAt'])>timestamp(latest[key]['observedAt']):latest[key]=e
    # Version documents are deterministic and never altered to a different prediction.
    for offset in range(0,len(entries),400):
        group=entries[offset:offset+400]
        refs=[db.collection(COLLECTION).document(f"{e['season']}_{e['id']}").collection('versions').document(e['archiveId']) for e in group]
        existing={d.id for d in db.get_all(refs) if d.exists}
        batch=db.batch();count=0
        for ref,e in zip(refs,group):
            if ref.id not in existing:batch.create(ref,e);count+=1
        if count:batch.commit(retry=Retry(timeout=5),timeout=10)
    @firestore.transactional
    def advance(transaction,group):
        refs=[db.collection(COLLECTION).document(f"{e['season']}_{e['id']}") for e in group]
        old={d.id:d.to_dict() for d in db.get_all(refs,transaction=transaction) if d.exists}
        for ref,e in zip(refs,group):
            prior=old.get(ref.id)
            if not prior or timestamp(prior['observedAt'])<timestamp(e['observedAt']):transaction.set(ref,e)
    newest=list(latest.values())
    for offset in range(0,len(newest),200):advance(db.transaction(),newest[offset:offset+200])
    return len(entries)


def read_queue(path):
    return json.loads(gzip.decompress(Path(path).read_bytes())) if Path(path).exists() else []

def write_queue(path,entries):
    Path(path).write_bytes(gzip.compress(json.dumps(entries,separators=(',',':')).encode(),mtime=0))

def merge_latest(entries):
    output={}
    for e in entries:
        if e['id'] not in output or timestamp(e['observedAt'])>timestamp(output[e['id']]['observedAt']):output[e['id']]=e
    return output
