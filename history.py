"""Private, bounded performance history. Collects even when Cockpit is closed."""
import argparse, csv, datetime as dt, io, json, math, os, pathlib, re, sqlite3, sys, time

INTERVAL=15
RETENTION=30*86400
PERIODS={'1h':3600,'6h':21600,'24h':86400,'7d':7*86400,'30d':RETENTION}
ROOT=pathlib.Path(os.environ.get('CARV_MC_ROOT',str(pathlib.Path.home()/'minecraft-bedrock')))
DB=ROOT/'admin-state/performance.sqlite'

def connection(path=DB,write=False):
    path=pathlib.Path(path)
    if write:
        path.parent.mkdir(parents=True,exist_ok=True)
        # The file is never placed inside the Cockpit package or a public web root.
        fd=os.open(path,os.O_CREAT|os.O_RDWR,0o600);os.close(fd)
        db=sqlite3.connect(path,timeout=5)
        db.execute('PRAGMA journal_mode=WAL')
        db.execute('CREATE TABLE IF NOT EXISTS samples(ts INTEGER PRIMARY KEY, observed REAL NOT NULL, state TEXT NOT NULL, cpu REAL, memory REAL, memory_limit REAL, tps REAL, players INTEGER, reason TEXT)')
        db.commit();return db
    if not path.exists():return None
    return sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True,timeout=5)

def memory_mib(text):
    m=re.fullmatch(r'\s*([0-9]+(?:\.[0-9]+)?)\s*(B|kB|KB|KiB|MB|MiB|GB|GiB|TB|TiB)\s*',str(text))
    if not m:return None
    scales={'B':1,'kB':1000,'KB':1000,'KiB':1024,'MB':1000**2,'MiB':1024**2,'GB':1000**3,'GiB':1024**3,'TB':1000**4,'TiB':1024**4}
    return float(m[1])*scales[m[2]]/1048576

def finite(value,low=0,high=None):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or value<low or high is not None and value>high:return None
    return value

def extract(info,stats,bridge,at):
    state=info['State']['Status'];row=dict(observed=at,state=state,cpu=None,memory=None,memory_limit=None,tps=None,players=None,reason=None)
    if state!='running':row['players']=0;row['reason']='server-stopped';return row
    try:row['cpu']=finite(float(str(stats.get('CPUPerc','')).rstrip('%')))
    except ValueError:pass
    mem=str(stats.get('MemUsage','')).split('/')
    if len(mem)==2:row['memory'],row['memory_limit']=map(memory_mib,mem)
    snapshot=bridge.get('snapshot') or {}
    started=dt.datetime.fromisoformat(info['State']['StartedAt'].replace('Z','+00:00')).timestamp()
    fresh=bridge.get('available') and snapshot.get('at',0)/1000>=started and 0<=at-snapshot.get('at',0)/1000<45
    if fresh:
        row['players']=len(snapshot.get('players',[]))
        row['tps']=finite((snapshot.get('tickHealth') or {}).get('tps'),high=20)
        if row['tps'] is None:row['reason']='tick-unavailable'
    else:row['reason']='bridge-stale'
    if row['cpu'] is None or row['memory'] is None:row['reason']='stats-unavailable'
    return row

def collect():
    import admin
    now=time.time()
    try:
        info=admin.inspect();stats={};bridge={}
        if info['State']['Running']:
            try:stats=json.loads(admin.run(['docker','stats','--no-stream','--format','{{json .}}',admin.CONTAINER],timeout=10).strip())
            except Exception:stats={}
            bridge=admin.bridge_data(admin.logs())
        return extract(info,stats,bridge,time.time())
    except Exception:
        # Never store raw Docker logs, inventories, credentials or exception payloads.
        return dict(observed=now,state='unavailable',cpu=None,memory=None,memory_limit=None,tps=None,players=None,reason='collection-failed')

def record(row,path=DB):
    db=connection(path,True)
    try:
        slot=int(row['observed']//INTERVAL)*INTERVAL
        db.execute('INSERT OR IGNORE INTO samples VALUES(?,?,?,?,?,?,?,?,?)',(slot,row['observed'],row['state'],row.get('cpu'),row.get('memory'),row.get('memory_limit'),row.get('tps'),row.get('players'),row.get('reason')))
        db.execute('DELETE FROM samples WHERE ts < ?',(int(row['observed']-RETENTION),));db.commit()
    finally:db.close()

def history(period='1h',path=DB,now=None):
    if period not in PERIODS:raise ValueError('Período inválido')
    now=int(time.time() if now is None else now);duration=PERIODS[period]
    step=max(INTERVAL,int(math.ceil(duration/240/INTERVAL))*INTERVAL)
    empty=dict(period=period,fromTs=now-duration,toTs=now,interval=INTERVAL,retentionDays=30,bucketSeconds=step,points=[],summary={},events=[],firstTs=None,lastTs=None,startedTs=None)
    db=connection(path)
    if db is None:return empty
    try:
        db.row_factory=sqlite3.Row
        bounds=db.execute('SELECT MIN(ts),MAX(ts) FROM samples').fetchone()
        empty['startedTs'],empty['lastTs']=bounds
        if bounds[0] is not None:
            available=min(duration,max(INTERVAL,now-max(bounds[0],now-duration)))
            step=max(INTERVAL,int(math.ceil(available/240/INTERVAL))*INTERVAL)
            empty['bucketSeconds']=step
        rows=db.execute('SELECT CAST(ts / ? AS INTEGER)*? AS ts, AVG(cpu) AS cpu, MAX(cpu) AS cpuPeak, MAX(memory) AS memory, MAX(memory_limit) AS memoryLimit, MIN(tps) AS tps, AVG(tps) AS tpsAvg, MAX(players) AS players, COUNT(*) AS samples, COUNT(tps) AS tickSamples FROM samples WHERE ts>=? AND ts<=? GROUP BY 1 ORDER BY 1',(step,step,now-duration,now)).fetchall()
        empty['points']=[dict(r) for r in rows]
        summary=db.execute('SELECT COUNT(*) AS samples, MIN(ts) AS firstTs, MAX(cpu) AS cpuPeak, MAX(memory) AS memoryPeak, MAX(players) AS playersPeak, MIN(CASE WHEN players>0 THEN tps END) AS activeTpsMin, SUM(CASE WHEN players>0 AND tps IS NOT NULL THEN 1 ELSE 0 END) AS activeSamples, SUM(CASE WHEN reason IS NOT NULL THEN 1 ELSE 0 END) AS missingSamples FROM samples WHERE ts>=? AND ts<=?',(now-duration,now)).fetchone()
        empty['summary']=dict(summary);empty['firstTs']=summary['firstTs']
        events=db.execute('SELECT ts,tps,cpu,memory,players FROM samples WHERE ts>=? AND ts<=? AND players>0 AND tps<18 ORDER BY ts DESC LIMIT 20',(now-duration,now)).fetchall()
        empty['events']=[dict(r) for r in events]
        return empty
    finally:db.close()

def export(period,path=DB,now=None):
    data=history(period,path,now);out=io.StringIO();writer=csv.writer(out)
    writer.writerow(['bucket_utc','cpu_avg_percent','cpu_peak_percent','memory_peak_mib','memory_limit_mib','tps_min','tps_avg','players_peak','samples','valid_tick_samples'])
    for p in data['points']:writer.writerow([dt.datetime.fromtimestamp(p['ts'],dt.timezone.utc).isoformat(),p['cpu'],p['cpuPeak'],p['memory'],p['memoryLimit'],p['tps'],p['tpsAvg'],p['players'],p['samples'],p['tickSamples']])
    return dict(csv=out.getvalue(),filename='minecraft-history-'+period+'.csv')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--collect-minute',action='store_true');args=parser.parse_args()
    start=time.monotonic()
    for index in range(4 if args.collect_minute else 1):
        deadline=start+index*INTERVAL
        if index and time.monotonic()>deadline+INTERVAL:continue
        time.sleep(max(0,deadline-time.monotonic()));record(collect())

if __name__=='__main__':main()
