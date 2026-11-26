import json
import tempfile
import unittest
from pathlib import Path
from token_usage import TokenUsage,extract
from unittest.mock import Mock,patch


class TokenUsageTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.ledger=TokenUsage(self.tmp.name)
        self.path=Path(self.tmp.name)/'result'

    def test_provider_formats_and_cache_not_double_counted(self):
        fixtures=[('codex',{'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':20,'cached_input_tokens':50}},120),
                  ('claude',{'usage':{'input_tokens':10,'output_tokens':20,'cache_read_input_tokens':50,'cache_creation_input_tokens':5}},85),
                  ('gemini',{'stats':{'models':{'flash':{'tokens':{'prompt':100,'candidates':20,'thoughts':30,'cached':50,'total':150}}}}},150)]
        for provider,payload,total in fixtures:
            self.path.write_text(json.dumps(payload),encoding='utf-8')
            u=extract(provider,self.path)
            self.assertEqual(u.get('total',u['input']+u['output']),total)

    def test_missing_usage_is_unknown(self):
        self.path.write_text('{}',encoding='utf-8')
        for p in ('codex','claude','gemini'):self.assertIsNone(extract(p,self.path))

    def test_month_limit_persists_and_blocks_next_run(self):
        self.ledger.set_limit('fe',100)
        key=self.ledger.start('fe','codex','gpt',{'task':196})
        self.ledger.finish(key,dict(input=90,output=20,cached=10),'completed')
        self.assertEqual(TokenUsage(self.tmp.name).snapshot()['runs'][0]['usage']['total'],110)
        with self.assertRaises(ValueError):self.ledger.start('fe','codex','gpt',{})
        self.ledger.start('be','gemini','flash',{})

    def test_unknown_or_running_blocks_when_limit_enabled(self):
        self.ledger.set_limit('fe',100)
        key=self.ledger.start('fe','codex','',{})
        with self.assertRaises(ValueError):self.ledger.start('fe','codex','',{})
        self.ledger.finish(key,None,'failed')
        with self.assertRaises(ValueError):self.ledger.start('fe','codex','',{})
        self.ledger.set_limit('fe',0)
        self.ledger.start('fe','codex','',{})

    def test_invalid_limits(self):
        for value in (-1,True,1.5,'100',1_000_000_001):
            with self.assertRaises(ValueError):self.ledger.set_limit('fe',value)

    def test_runtime_records_failed_generation_and_blocks_before_next_call(self):
        from office import Office
        office=Office.__new__(Office);office.runtime=Path(self.tmp.name);office.agents=Mock()
        office.agents.get.return_value={'runtime':{'adapter':'codex','model':'test'}}
        def failed(role,cwd,context,output,**kwargs):
            output.with_suffix('.jsonl').write_text(json.dumps({'type':'turn.completed','usage':{'input_tokens':100,'output_tokens':20}}),encoding='utf-8')
            raise RuntimeError('Malformed handoff')
        office._execute=Mock(side_effect=failed)
        self.ledger.set_limit('fe',100)
        with self.assertRaises(RuntimeError):office._call('fe',self.tmp.name,{'task':196})
        self.assertEqual(self.ledger.snapshot()['runs'][0]['state'],'failed')
        with self.assertRaises(ValueError):office._call('fe',self.tmp.name,{})
        self.assertEqual(office._execute.call_count,1)

    def test_api_limits_require_local_origin_and_integer(self):
        from office import make_server
        from urllib.request import Request,urlopen
        from urllib.error import HTTPError
        import threading
        manager=Mock();manager.office.return_value.runtime=Path(self.tmp.name)
        server=make_server(manager,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        url='http://127.0.0.1:'+str(server.server_address[1])+'/lending-api/agents/tokens'
        def post(origin,value):
            return urlopen(Request(url,data=json.dumps({'agent':'fe','limit':value}).encode(),headers={'Origin':origin,'Content-Type':'application/json'}))
        try:
            with self.assertRaises(HTTPError):post('https://evil.test',100)
            with self.assertRaises(HTTPError):post('http://localhost:8766',-1)
            with post('http://localhost:8766',100) as response:self.assertEqual(json.load(response)['limits']['fe'],100)
            with urlopen(url) as response:self.assertEqual(json.load(response)['scope'],'office-runtime')
        finally:server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()
