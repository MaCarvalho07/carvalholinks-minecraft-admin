import datetime as dt, json, os, pathlib, sqlite3, tempfile, unittest
from contextlib import closing
from unittest.mock import patch
import history as h

NOW=1800000000
def row(at=NOW,tps=20,players=1,**kwargs):return dict(observed=at,state='running',cpu=12,memory=256,memory_limit=4096,tps=tps,players=players,reason=None,**kwargs)

class HistoryTests(unittest.TestCase):
 def setUp(self):self.temp=tempfile.TemporaryDirectory();self.path=pathlib.Path(self.temp.name)/'private/history.sqlite'
 def tearDown(self):self.temp.cleanup()
 def test_empty_never_invents_samples(self):
  r=h.history('1h',self.path,NOW);self.assertEqual(r['points'],[]);self.assertIsNone(r['lastTs']);self.assertFalse(self.path.exists())
 def test_units_and_multicore_cpu(self):
  self.assertEqual(h.memory_mib('4GiB'),4096);self.assertEqual(h.memory_mib('2 MiB'),2);self.assertIsNone(h.memory_mib('invalid'))
  self.assertEqual(h.finite(234.5),234.5);self.assertIsNone(h.finite(float('nan')))
 def extract(self,age=0,started=None):
  start=dt.datetime.fromtimestamp(started or NOW-100,dt.timezone.utc).isoformat()
  return h.extract({'State':{'Status':'running','StartedAt':start}},{'CPUPerc':'245.5%','MemUsage':'256MiB / 4GiB'},{'available':True,'snapshot':{'at':(NOW-age)*1000,'players':[{'name':'PRIVATE-NAME','inventory':['PRIVATE-ITEM']}],'tickHealth':{'tps':20}}},NOW)
 def test_only_counts_no_inventory_persisted(self):
  r=self.extract();self.assertEqual(r['players'],1);self.assertEqual(r['cpu'],245.5);self.assertEqual(r['memory_limit'],4096);h.record(r,self.path)
  with closing(sqlite3.connect(self.path)) as db:stored=str(db.execute('SELECT * FROM samples').fetchall())
  self.assertNotIn('PRIVATE',stored)
 def test_stale_and_prior_run_are_missing_not_zero(self):
  for r in [self.extract(age=50),self.extract(age=10,started=NOW-5)]:self.assertIsNone(r['tps']);self.assertIsNone(r['players']);self.assertEqual(r['reason'],'bridge-stale')
 def test_stopped_has_no_fake_zero_tps(self):
  r=h.extract({'State':{'Status':'exited'}},{},{},NOW);self.assertEqual(r['players'],0);self.assertIsNone(r['tps'])
 def test_duplicate_slot_is_idempotent(self):
  h.record(row(),self.path);h.record(row(at=NOW+1,tps=5),self.path);r=h.history('1h',self.path,NOW+1);self.assertEqual(r['summary']['samples'],1);self.assertEqual(r['summary']['activeTpsMin'],20)
 def test_retention(self):
  h.record(row(at=NOW-h.RETENTION-30),self.path);h.record(row(),self.path)
  self.assertEqual(h.history('30d',self.path,NOW)['summary']['samples'],1)
  with closing(sqlite3.connect(self.path)) as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM samples').fetchone()[0],1)
 def test_downsample_preserves_dip_and_peak(self):
  h.record(row(at=NOW-40000),self.path)
  a=row(at=NOW-30,tps=7);a['cpu']=250
  h.record(a,self.path);h.record(row(at=NOW-15,tps=20),self.path);r=h.history('30d',self.path,NOW)
  self.assertEqual(min(p['tps'] for p in r['points']),7);self.assertEqual(r['summary']['cpuPeak'],250);self.assertEqual(r['summary']['activeTpsMin'],7)
  bucket=next(p for p in r['points'] if p['samples']==2);self.assertEqual(bucket['tps'],7);self.assertEqual(bucket['cpuPeak'],250);self.assertEqual(bucket['cpu'],131)
 def test_idle_samples_do_not_claim_gameplay_performance(self):
  h.record(row(tps=20,players=0),self.path);r=h.history('1h',self.path,NOW);self.assertIsNone(r['summary']['activeTpsMin']);self.assertEqual(r['events'],[])
 def test_dip_events_require_players(self):
  h.record(row(at=NOW-30,tps=5,players=0),self.path);h.record(row(tps=17,players=2),self.path);r=h.history('1h',self.path,NOW)
  self.assertEqual(len(r['events']),1);self.assertEqual(r['events'][0]['players'],2)
 def test_export_and_period_validation(self):
  h.record(row(),self.path);csv=h.export('1h',self.path,NOW)['csv'];self.assertIn('cpu_peak_percent',csv);self.assertIn('20.0',csv)
  with self.assertRaises(ValueError):h.history("1h;DROP TABLE samples",self.path,NOW)
 def test_permissions(self):
  h.record(row(),self.path)
  if os.name!='nt':self.assertEqual(self.path.stat().st_mode&0o777,0o600)
 def test_collector_failure_is_missing(self):
  fake=type('Admin',(),{'inspect':staticmethod(lambda:(_ for _ in ()).throw(RuntimeError('SECRET')))})
  with patch.dict('sys.modules',{'admin':fake}):r=h.collect()
  self.assertEqual(r['reason'],'collection-failed');self.assertNotIn('SECRET',json.dumps(r));self.assertIsNone(r['tps'])

if __name__=='__main__':unittest.main()
