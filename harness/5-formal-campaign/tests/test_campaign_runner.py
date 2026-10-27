import pathlib
import json, pathlib, subprocess, sys, tempfile, unittest
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
RUNNER=ROOT/'harness/5-formal-campaign/code/run_campaign.py'; SPEC=ROOT/'harness/5-formal-campaign/code/examples/mock-campaign.json'
class CampaignRunnerTests(unittest.TestCase):
    def test_expansion_preserves_json_braces(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location("campaign_runner",RUNNER)
        module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
        self.assertEqual(module.expand(['{"temperature":0}', '{concurrency}'], {'concurrency':8}), ['{"temperature":0}', '8'])

    def test_mock_campaign_and_resume(self):
        with tempfile.TemporaryDirectory() as d:
            cmd=[sys.executable,str(RUNNER),str(SPEC),'--results-root',d]
            first=subprocess.run(cmd,cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(first.returncode,0,first.stderr)
            campaign=pathlib.Path(first.stdout.strip().splitlines()[-1]); manifest=campaign/'campaign-manifest.json'
            data=json.loads(manifest.read_text()); self.assertEqual(data['status'],'runs_complete'); self.assertEqual(data['counts']['complete_operating_points'],4)
            before=len(data['runs']); second=subprocess.run(cmd+['--resume'],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(second.returncode,0,second.stderr); after=json.loads(manifest.read_text())
            self.assertEqual(len(after['runs']),before); self.assertTrue((campaign/'RUNS_COMPLETE').exists()); self.assertFalse((campaign/'CAMPAIGN_COMPLETE').exists())
    def test_dry_run_does_not_execute(self):
        with tempfile.TemporaryDirectory() as d:
            result=subprocess.run([sys.executable,str(RUNNER),str(SPEC),'--results-root',d,'--dry-run'],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr); campaign=pathlib.Path(result.stdout.strip().splitlines()[-1]); manifests=list(campaign.glob('runs/*/c*/run-*/manifest.json'))
            self.assertEqual(len(manifests),4); self.assertTrue(all(json.loads(x.read_text())['status']=='dry_run' for x in manifests)); self.assertFalse((campaign/'CAMPAIGN_COMPLETE').exists())
    def test_warmup_request_cap(self):
        with tempfile.TemporaryDirectory() as d:
            d=pathlib.Path(d); spec=json.loads(SPEC.read_text()); spec['campaign']['id']='mock-warmup-cap'; spec['profiles'][0]['concurrency']=[64]; spec['profiles'][0]['warmup_requests_cap']=16
            spec_file=d/'spec.json'; spec_file.write_text(json.dumps(spec)+'\n')
            run=subprocess.run([sys.executable,str(RUNNER),str(spec_file),'--results-root',str(d/'results'),'--dry-run'],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr); campaign=pathlib.Path(run.stdout.strip().splitlines()[-1]); manifests=list(campaign.glob('runs/*/c*/run-*/manifest.json'))
            self.assertEqual(len(manifests),2)
            for manifest in manifests:
                command=json.loads(manifest.read_text())['warmup_command']; self.assertEqual(command[command.index('--request-count')+1],'16')

    def test_imported_complete_run_is_reused(self):
        with tempfile.TemporaryDirectory() as d:
            d=pathlib.Path(d); source=d/'source'; result=source/'measured/profile_export_aiperf.json'; result.parent.mkdir(parents=True)
            result.write_text('{}\n'); manifest=source/'manifest.json'
            manifest.write_text(json.dumps({'run_id':'prior','status':'complete','profile':'decode','concurrency':1,'repetition':1,'artifacts':{'result':str(result)}})+'\n')
            spec=json.loads(SPEC.read_text()); spec['campaign']['id']='mock-import'; spec['campaign']['imported_runs']=[{'profile':'decode','concurrency':1,'repetition':1,'manifest':str(manifest)}]
            spec_file=d/'spec.json'; spec_file.write_text(json.dumps(spec)+'\n')
            run=subprocess.run([sys.executable,str(RUNNER),str(spec_file),'--results-root',str(d/'results')],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stderr); campaign=pathlib.Path(run.stdout.strip().splitlines()[-1]); data=json.loads((campaign/'campaign-manifest.json').read_text())
            self.assertEqual(data['counts']['expected'],4); self.assertEqual(data['counts']['complete_operating_points'],4); self.assertEqual(len(data['runs']),4)
            imported=[x for x in data['runs'] if x.get('imported')]; self.assertEqual(len(imported),1); self.assertEqual(imported[0]['run_id'],'prior')
            self.assertTrue((campaign/'RUNS_COMPLETE').exists())
            aggregate=subprocess.run([sys.executable,str(ROOT/'harness/6-accept-and-publish/code/aggregate_campaign.py'),str(campaign)],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(aggregate.returncode,0,aggregate.stderr); summary=json.loads((campaign/'summaries/summary.json').read_text())
            self.assertEqual(len(summary['runs']),4); self.assertEqual(sum(bool(x['imported']) for x in summary['runs']),1)
            finalize=subprocess.run([sys.executable,str(ROOT/'harness/5-formal-campaign/code/finalize_campaign.py'),str(campaign),'--allow-missing-post-idle'],cwd=ROOT,text=True,capture_output=True)
            self.assertEqual(finalize.returncode,0,finalize.stderr); self.assertTrue((campaign/'CAMPAIGN_COMPLETE').exists())
if __name__=='__main__': unittest.main()
