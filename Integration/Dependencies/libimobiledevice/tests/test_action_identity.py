import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
HERE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(HERE))
import acquire

class Response:
    def __init__(self,value):self.data=json.dumps(value).encode()
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,count):return self.data[:count]

class ActionIdentityTests(unittest.TestCase):
    def setUp(self):
        self.env={'GITHUB_REPOSITORY':'oskuhsiu/Tetherless','GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2','GITHUB_SHA':'a'*40,'GH_READ_TOKEN':'synthetic-test-token'}
        self.run={'head_sha':'a'*40,'head_branch':'verify/staged-pairing-native','run_attempt':2,
                  'path':'.github/workflows/c-provider-native.yml','event':'push','html_url':'https://github.com/oskuhsiu/Tetherless/actions/runs/123'}
        self.jobs={'total_count':1,'jobs':[{'name':'c-provider','head_sha':'a'*40,'run_attempt':2,'id':987,'html_url':'https://github.com/oskuhsiu/Tetherless/actions/runs/123/job/987','status':'in_progress'}]}
    def invoke(self):
        with patch.dict(os.environ,self.env,clear=True),patch.object(acquire.urllib.request,'urlopen',side_effect=[Response(self.run),Response(self.jobs)]) as request:
            value=acquire.action_identity()
            self.assertEqual(request.call_count,2)
            self.assertTrue(all(call.args[0].full_url.startswith('https://api.github.com/repos/oskuhsiu/Tetherless/actions/runs/123') for call in request.call_args_list))
            return value
    def test_exact_run_attempt_job_and_no_false_success(self):
        r=self.invoke();self.assertEqual(r['job_id'],987);self.assertFalse(r['success_at_acquisition']);self.assertTrue(r['later_api_success_verification_required']);self.assertNotIn('synthetic-test-token',json.dumps(r))
    def test_wrong_branch_rejected(self):
        self.run['head_branch']='develop'
        with self.assertRaises(ValueError):self.invoke()
    def test_wrong_source_rejected(self):
        self.run['head_sha']='b'*40
        with self.assertRaises(ValueError):self.invoke()
    def test_wrong_workflow_rejected(self):
        self.run['path']='.github/workflows/native.yml'
        with self.assertRaises(ValueError):self.invoke()
    def test_wrong_attempt_rejected(self):
        self.run['run_attempt']=1
        with self.assertRaises(ValueError):self.invoke()
    def test_ambiguous_job_rejected(self):
        self.jobs['jobs']*=2
        with self.assertRaises(ValueError):self.invoke()
    def test_incomplete_pagination_rejected(self):
        self.jobs['total_count']=101
        with self.assertRaises(ValueError):self.invoke()
    def test_other_repository_rejected_before_network(self):
        self.env['GITHUB_REPOSITORY']='some/other'
        with patch.dict(os.environ,self.env,clear=True),patch.object(acquire.urllib.request,'urlopen') as request:
            with self.assertRaises(ValueError):acquire.action_identity()
            request.assert_not_called()

if __name__=='__main__':unittest.main()
