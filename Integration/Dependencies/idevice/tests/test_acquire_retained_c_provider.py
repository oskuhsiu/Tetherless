"""Read-only acquisition boundary fixtures; no network or native execution."""
from __future__ import annotations
import copy
import io
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import urllib.error
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(Path(__file__).parent))
import acquire_retained_c_provider as a
import retained_c_provider as c
from retained_c_fixture import make_fixture,FixtureAPI,raw

class Response(io.BytesIO):
    def __init__(self,data,status=200):super().__init__(data);self.status=status

class TransportTests(unittest.TestCase):
    def setUp(self):
        t=tempfile.TemporaryDirectory();self.addCleanup(t.cleanup);self.root=Path(t.name)
    def test_authenticated_api_routes_are_bounded_to_exact_repo_and_read_paths(self):
        api=a.ActionsRead('synthetic test token')
        class Open:
            def __init__(self):self.requests=[]
            def open(self,request,timeout):self.requests.append(request);return Response(b'{}')
        op=Open();api.opener=op
        api.get('actions/runs/1001')
        self.assertEqual(op.requests[0].get_header('Authorization'),'Bearer synthetic test token')
        for route in ('https://evil.invalid/','actions/runs/1001?evil=1','../other/actions/runs/1','actions/runs/1/jobs','git/blobs/'+'a'*40):
            with self.subTest(route=route),self.assertRaises(ValueError):api.get(route)
        self.assertEqual(len(op.requests),1)
    def test_storage_redirect_never_receives_token(self):
        api=a.ActionsRead('synthetic test token');requests=[]
        class Open:
            def open(self,request,timeout):
                requests.append(request)
                if len(requests)==1:raise urllib.error.HTTPError(request.full_url,302,'redirect',{'Location':'https://fixture.blob.core.windows.net/artifact?signature=synthetic'},None)
                return Response(b'zip')
        api.opener=Open();api.download(1003,self.root/'artifact.zip',3)
        self.assertEqual(requests[0].get_header('Authorization'),'Bearer synthetic test token')
        self.assertIsNone(requests[1].get_header('Authorization'))
        self.assertEqual((self.root/'artifact.zip').read_bytes(),b'zip')
    def test_redirect_outside_storage_or_with_userinfo_or_http_fails_before_follow(self):
        for target in ('https://evil.invalid/x','https://blob.core.windows.net.evil.invalid/x','http://fixture.blob.core.windows.net/x',
                       'https://user@fixture.blob.core.windows.net/x','https://fixture.blob.core.windows.net:444/x','https://fixture.blob.core.windows.net/x#fragment'):
            with self.subTest(target=target):
                api=a.ActionsRead('synthetic');requests=[]
                class Open:
                    def open(self,request,timeout):
                        requests.append(request)
                        raise urllib.error.HTTPError(request.full_url,302,'redirect',{'Location':target},None)
                api.opener=Open()
                with self.assertRaises(ValueError):api.download(1,self.root/'artifact.zip',3)
                self.assertEqual(len(requests),1)
    def test_redirect_handler_never_automatically_follows(self):
        self.assertIsNone(a.NoRedirect().redirect_request(None,None,302,'',{},'https://elsewhere.invalid'))
    def test_short_or_overlong_download_rejected(self):
        for data in (b'x',b'long'):
            with self.subTest(data=data):
                api=a.ActionsRead('synthetic');requests=[]
                class Open:
                    def open(self,request,timeout):
                        requests.append(request)
                        if len(requests)==1:raise urllib.error.HTTPError(request.full_url,302,'',{'Location':'https://fixture.actions.githubusercontent.com/x'},None)
                        return Response(data)
                api.opener=Open();out=self.root/('bytes-'+str(len(data)))
                with self.assertRaises(ValueError):api.download(1,out,3)
    def test_api_json_and_time_bounds(self):
        api=a.ActionsRead('synthetic')
        with patch.object(api,'open',return_value=Response(b'{' + b'x'*(c.MAX_JSON))):
            with self.assertRaisesRegex(ValueError,'JSON exceeds'):api.get('actions/runs/1')
        api.deadline=time.monotonic()-1
        with self.assertRaisesRegex(ValueError,'600 seconds'):api.open(api.base+'actions/runs/1',authenticated=True)
    def test_listing_completes_multiple_pages_and_rejects_duplicates_omission_instability(self):
        first=[{'id':i} for i in range(1,101)]
        class API:
            def __init__(self,pages):self.pages=iter(pages)
            def get(self,_):return next(self.pages)
        d=self.root/'pages';d.mkdir()
        rows=a.listing(API([{'total_count':101,'jobs':first},{'total_count':101,'jobs':[{'id':101}]}]),'path','jobs',d,'jobs')
        self.assertEqual(len(rows),101);self.assertEqual(len(list(d.iterdir())),2)
        cases=[([{'total_count':2,'jobs':[{'id':1}]},{'total_count':2,'jobs':[{'id':1}]}]),
               ([{'total_count':2,'jobs':[{'id':1}]},{'total_count':2,'jobs':[]}]),
               ([{'total_count':2,'jobs':[{'id':1}]},{'total_count':3,'jobs':[{'id':2}]}]),
               ([{'total_count':2001,'jobs':[]}])]
        for index,pages in enumerate(cases):
            with self.subTest(index=index):
                out=self.root/str(index);out.mkdir()
                with self.assertRaises(ValueError):a.listing(API(pages),'path','jobs',out,'jobs')
    def test_racing_run_and_artifact_changes_fail(self):
        for kind in ('run','artifact','job'):
            with self.subTest(kind=kind):
                f=make_fixture();selection=self.root/(kind+'.json');selection.write_bytes(raw({'schema':1,'selection':f['selection']}))
                class RacingAPI(FixtureAPI):
                    def __init__(self,f):super().__init__(f);self.counts={}
                    def get(self,path):
                        row=super().get(path);self.counts[path]=self.counts.get(path,0)+1
                        if self.counts[path]==2:
                            if kind=='run' and path=='actions/runs/1001':row['run_attempt']=2
                            if kind=='artifact' and path=='actions/artifacts/1003':row['expired']=True
                            if kind=='job' and path=='actions/jobs/1002':row['conclusion']='failure'
                        return row
                with patch.object(c,'ARCHIVE_SHA256',f['original_digest']),self.assertRaises(ValueError):
                    a.acquire(RacingAPI(f),f['selection'],self.root/kind,selection_path=selection)
                self.assertFalse((self.root/kind/'handoff.json').exists())
    def test_exact_artifact_name_ambiguity_is_rejected(self):
        f=make_fixture()
        class API(FixtureAPI):
            def get(self,path):
                row=super().get(path)
                if path=='actions/runs/1001/artifacts?per_page=100&page=1':
                    other=copy.deepcopy(f['artifact']);other['id']=1004
                    return {'total_count':2,'artifacts':[f['artifact'],other]}
                return row
        with self.assertRaisesRegex(ValueError,'absent or ambiguous'):a.acquire(API(f),f['selection'],self.root/'out')
        self.assertFalse((self.root/'out/actions-artifact.zip').exists())

if __name__=='__main__':unittest.main()
