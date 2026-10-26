import base64, importlib.util, io, json, pathlib, sys, tempfile, types, unittest, uuid, zipfile
if sys.platform=='win32':sys.modules['fcntl']=types.SimpleNamespace()
spec=importlib.util.spec_from_file_location('admin',pathlib.Path(__file__).with_name('admin.py'));a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class SafetyTests(unittest.TestCase):
 def archive(self,files):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   for name,data in files.items():z.writestr(name,data)
  return b.getvalue()
 def test_traversal(self):
  for name in ('../oops','/etc/oops','C:/oops','a/../../oops'):
   with self.subTest(name=name),tempfile.TemporaryDirectory() as t:
    with self.assertRaises(ValueError):a.unpack(self.archive({name:'x'}),pathlib.Path(t))
 def test_reject_symlink(self):
  b=io.BytesIO()
  with zipfile.ZipFile(b,'w') as z:
   x=zipfile.ZipInfo('link');x.external_attr=0o120777<<16;z.writestr(x,'/etc/passwd')
  with tempfile.TemporaryDirectory() as t,self.assertRaises(ValueError):a.unpack(b.getvalue(),pathlib.Path(t))
 def test_nested_mcaddon(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);uid=str(uuid.uuid4());m={'header':{'uuid':uid,'version':[1,0,0],'name':'Sample'},'modules':[{'type':'resources'}]}
   a.budget[0]=0;a.unpack(self.archive({'sample.mcpack':self.archive({'manifest.json':json.dumps(m)})}),root)
   self.assertEqual(a.validate_stage(root)[0]['uuid'],uid)
 def test_missing_script(self):
  with tempfile.TemporaryDirectory() as t:
   root=pathlib.Path(t);(root/'manifest.json').write_text(json.dumps({'header':{'uuid':str(uuid.uuid4()),'version':[1,0,0]},'modules':[{'type':'script','entry':'../../outside.js'}]}))
   with self.assertRaises(ValueError):a.validate_stage(root)
 def test_missing_dependency(self):
  with self.assertRaises(ValueError):a.validate_refs([dict(uuid='a',name='A',version=[1,0,0],active=True,dependencies=[dict(uuid='b',version=[1,0,0])])])
 def test_telemetry(self):
  import time
  snapshot=dict(schema=1,at=time.time()*1000,players=[])
  self.assertTrue(a.bridge_data('[Scripting] [CARV_ADMIN_V1]'+json.dumps(snapshot))['available'])
  snapshot['at']=0
  self.assertFalse(a.bridge_data('[CARV_ADMIN_V1]'+json.dumps(snapshot))['available'])
 def test_invalid_archive(self):
  with tempfile.TemporaryDirectory() as t,self.assertRaises(zipfile.BadZipFile):a.unpack(b'not a zip',pathlib.Path(t))
 def test_backup_and_integrity(self):
  old=(a.ROOT,a.DATA)
  with tempfile.TemporaryDirectory() as t:
   a.ROOT=pathlib.Path(t);a.DATA=a.ROOT/'data';w=a.DATA/'worlds/Bedrock level';w.mkdir(parents=True);(w/'level.dat').write_bytes(b'world');(a.DATA/'server.properties').write_text('level-name=Bedrock level');(a.ROOT/'compose.yml').write_text('services: {}')
   try:
    b=a.backup();p=a.checked_backup(b['id']);self.assertTrue(p.is_file());p.write_bytes(b'tampered')
    with self.assertRaises(ValueError):a.checked_backup(b['id'])
   finally:a.ROOT,a.DATA=old
 def test_restore_preserves_runtime(self):
  old=(a.ROOT,a.DATA)
  with tempfile.TemporaryDirectory() as t:
   a.ROOT=pathlib.Path(t);a.DATA=a.ROOT/'data';w=a.DATA/'worlds/Main';w.mkdir(parents=True);(w/'level.dat').write_bytes(b'original');(a.DATA/'server.properties').write_text('level-name=Main');(a.ROOT/'compose.yml').write_text('current-runtime')
   try:
    b=a.backup();(w/'level.dat').write_bytes(b'changed');(a.ROOT/'compose.yml').write_text('new-runtime');a.restore_files(b['id']);self.assertEqual((w/'level.dat').read_bytes(),b'original');self.assertEqual((a.ROOT/'compose.yml').read_text(),'new-runtime')
   finally:a.ROOT,a.DATA=old

if __name__=='__main__':unittest.main()
