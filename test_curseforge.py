import base64, hashlib, io, json, pathlib, tempfile, types, unittest, urllib.error, zipfile
from unittest.mock import patch, Mock
import curseforge as cf

def package():
    b=io.BytesIO()
    with zipfile.ZipFile(b,'w') as z:z.writestr('manifest.json','{}')
    return b.getvalue()

def file_meta(blob,**extra):
    return dict(id=4,modId=2,fileName='example.mcpack',displayName='Example',fileLength=len(blob),isAvailable=True,hashes=[dict(algo=1,value=hashlib.sha1(blob).hexdigest())],**extra)

class Response(io.BytesIO):
    def __init__(self,data,headers=None):super().__init__(data);self.headers=headers or {}

class ApiTests(unittest.TestCase):
    def client(self):
        with patch.object(cf,'key',return_value='test-placeholder-key'):return cf.Client()

    def test_no_key_no_network(self):
        with patch.object(cf,'key',return_value=None),patch.object(cf.urllib.request,'build_opener') as opener:
            self.assertFalse(cf.connection()['configured'])
            with self.assertRaises(cf.ApiError):cf.Client()
            opener.assert_not_called()

    def test_key_file(self):
        with tempfile.TemporaryDirectory() as t,patch.object(cf,'CONFIG',pathlib.Path(t)),patch.dict(cf.os.environ,{'CURSEFORGE_API_KEY':''}):
            p=pathlib.Path(t)/'curseforge.key';p.write_text('placeholder-test-key');p.chmod(0o600);self.assertEqual(cf.key(),'placeholder-test-key')
            p.write_text('invalid\nkey')
            with self.assertRaises(cf.ApiError):cf.key()

    def test_wrong_game_is_rejected(self):
        client=self.client();client.get=Mock(return_value={'data':{'id':432,'slug':'minecraft'}})
        with self.assertRaisesRegex(cf.ApiError,'Bedrock'):client.game(432)

    def test_game_discovery(self):
        client=self.client();client.get=Mock(return_value={'data':[{'id':7,'slug':'minecraft-bedrock'}]})
        with patch.dict(cf.os.environ,{'CURSEFORGE_GAME_ID':''}):self.assertEqual(client.game(),7)

    def test_restricted_distribution(self):
        client=self.client();blob=package();client.get=Mock(return_value={'data':file_meta(blob)})
        with self.assertRaisesRegex(cf.ApiError,'autor'):client.download({'id':2,'allowModDistribution':False},4)
        self.assertEqual(client.get.call_count,1)

    def test_bad_urls(self):
        for url in ('http://edge.forgecdn.net/files/x','https://127.0.0.1/files/a','https://evil.example/files/x','https://forgecdn.net.evil.example/files/x','https://user:pass@edge.forgecdn.net/files/x','https://edge.forgecdn.net:123/files/x','https://edge.forgecdn.net/other/x'):
            with self.subTest(url=url),self.assertRaises(cf.ApiError):cf.cdn_url(url)

    def test_unsafe_public_links(self):
        self.assertEqual(cf.public_url('javascript:alert(1)'), '')
        self.assertEqual(cf.public_url('https://www.curseforge.com/minecraft/mc-mods/java'), '')
        self.assertEqual(cf.public_url('https://evil.example/a','image'), '')

    def download_client(self,blob,meta=None):
        client=self.client();client.get=Mock(side_effect=[{'data':meta or file_meta(blob)},{'data':'https://edge.forgecdn.net/files/1/2/test.mcpack'}]);client.opener=Mock();client.opener.open.return_value=Response(blob)
        return client

    def test_verified_download(self):
        blob=package();client=self.download_client(blob);data,meta=client.download({'id':2},4)
        self.assertEqual(data,blob);self.assertEqual(meta['filename'],'example.mcpack');request=client.opener.open.call_args.args[0];self.assertEqual(request.get_header('X-api-key'),'test-placeholder-key')

    def test_bad_checksum(self):
        blob=package();meta=file_meta(blob);meta['hashes'][0]['value']='0'*40;client=self.download_client(blob,meta)
        with self.assertRaisesRegex(cf.ApiError,'Checksum'):client.download({'id':2},4)

    def test_size_mismatch(self):
        blob=package();meta=file_meta(blob);meta['fileLength']+=1;client=self.download_client(blob,meta)
        with self.assertRaisesRegex(cf.ApiError,'Tamanho'):client.download({'id':2},4)

    def test_redirect_does_not_leak_key(self):
        blob=package();client=self.download_client(blob);client.opener.open.side_effect=urllib.error.HTTPError('https://edge.forgecdn.net/files/x',302,'Redirect',{'Location':'https://evil.example/files/x'},None)
        with self.assertRaises(cf.ApiError):client.download({'id':2},4)
        self.assertEqual(client.opener.open.call_count,1)

    def test_unauthorized_does_not_expose_key(self):
        client=self.client();client.opener=Mock();client.opener.open.side_effect=urllib.error.HTTPError(cf.API,401,'test-placeholder-key',{},None)
        with self.assertRaises(cf.ApiError) as e:client.get('/v1/games')
        self.assertNotIn('test-placeholder-key',str(e.exception));self.assertIn('Chave',str(e.exception))

    def test_java_and_oversize_rejected(self):
        for name,size in [('file.jar',100),('file.mcpack',cf.MAX_DOWNLOAD+1)]:
            meta=file_meta(package());meta.update(fileName=name,fileLength=size)
            self.assertFalse(cf.file_view(meta,{'id':2})['eligible'])

    def test_pair_reuses_existing_installer(self):
        fake=Mock();fake.game.return_value=7;fake.project.return_value={'id':2};blob=package();fake.download.side_effect=[(blob,{'id':4,'filename':'bp.mcpack'}),(blob,{'id':5,'filename':'rp.mcpack'})]
        admin=types.SimpleNamespace(mutate=Mock(return_value={'message':'installed'}))
        with patch.object(cf,'Client',return_value=fake):cf.handle({'action':'cf_install','projectId':2,'fileIds':[4,5]},admin)
        req=admin.mutate.call_args.args[0];self.assertEqual(req['action'],'install')
        with zipfile.ZipFile(io.BytesIO(base64.b64decode(req['data']))) as z:self.assertEqual(len(z.namelist()),2)

    def test_failed_download_never_calls_installer(self):
        fake=Mock();fake.game.return_value=7;fake.project.return_value={'id':2};fake.download.side_effect=cf.ApiError('checksum mismatch');admin=types.SimpleNamespace(mutate=Mock())
        with patch.object(cf,'Client',return_value=fake),self.assertRaises(cf.ApiError):cf.handle({'action':'cf_install','projectId':2,'fileIds':[4]},admin)
        admin.mutate.assert_not_called()

    def test_number_rejects_injection(self):
        for value in (True,'1/../2','1?key=x','0','-1','1.2'):
            with self.subTest(value=value),self.assertRaises(cf.ApiError):cf.number(value)

if __name__=='__main__':unittest.main()
