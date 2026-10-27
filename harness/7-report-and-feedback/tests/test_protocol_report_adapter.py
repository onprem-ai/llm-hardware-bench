import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import pathlib
ROOT = next(a for a in pathlib.Path(__file__).resolve().parents
            if (a / '.git').exists())
PATH = ROOT / "harness/7-report-and-feedback/code/adapters/protocol_campaign.py"
spec = importlib.util.spec_from_file_location("protocol_report_adapter", PATH)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class ProtocolReportAdapterTests(unittest.TestCase):
    def test_prefill_per_user_metric_uses_prefill_throughput(self):
        self.assertEqual(
            module.APP["prefill_per_user_tps"],
            ("prefill_throughput_per_user", "avg", "input tokens/s/user"),
        )

    def test_canonical_records_include_imported_absolute_manifests(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            campaign = root / "campaign"
            local = campaign / "runs/decode/c0001/run-r01-local"
            imported = root / "qualification/runs/decode/c0008/run-r01-imported"
            local.mkdir(parents=True)
            imported.mkdir(parents=True)
            for path, run_id, concurrency in ((local, "local", 1), (imported, "imported", 8)):
                (path / "manifest.json").write_text(json.dumps({
                    "status": "complete", "run_id": run_id, "profile": "decode",
                    "concurrency": concurrency, "repetition": 1,
                    "artifacts": {"result": str(path / "measured/profile_export_aiperf.json")}
                }))
            (campaign / "campaign-manifest.json").write_text(json.dumps({"runs": [
                {"run_id": "local", "status": "complete", "profile": "decode", "concurrency": 1, "repetition": 1, "manifest": str(local.relative_to(campaign))},
                {"run_id": "imported", "status": "complete", "profile": "decode", "concurrency": 8, "repetition": 1, "manifest": str(imported), "imported": True}
            ]}))
            records = list(module.canonical_records(campaign))
            self.assertEqual(len(records), 2)
            self.assertEqual(records[1][1], imported / "manifest.json")
            self.assertTrue(records[1][0]["imported"])

    def test_artifact_paths_follow_manifest_result_and_canonical_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            run = Path(directory) / "run-r01"
            run.mkdir()
            result = run / "measured/profile_export_aiperf.json"
            manifest = {"artifacts": {"result": str(result)}}
            found, measured, telemetry, vm = module.artifact_paths(run / "manifest.json", manifest, "canonical")
            self.assertEqual(found, result)
            self.assertEqual(measured, result.parent)
            self.assertEqual(telemetry, run / "telemetry")
            self.assertIsNone(vm)

    def test_victoriametrics_pcie_aggregates_endpoint_rates_and_replays(self):
        with tempfile.TemporaryDirectory() as directory:
            telemetry=Path(directory);vm=telemetry/'victoriametrics';vm.mkdir()
            queries=[]
            for number,(name,values) in enumerate((('DCGM_FI_PROF_PCIE_RX_BYTES',[[1,1_000_000_000],[2,3_000_000_000]]),('DCGM_FI_PROF_PCIE_TX_BYTES',[[1,2_000_000_000],[2,4_000_000_000]]),('DCGM_FI_DEV_PCIE_REPLAY_COUNTER',[[1,2],[2,5]])),2):
                file=f'query-{number:03d}.json';(vm/file).write_text(json.dumps({'data':{'result':[{'values':values},{'values':values}]}}));queries.append({'query':name,'file':file})
            (vm/'manifest.json').write_text(json.dumps({'queries':queries}))
            result=module.victoriametrics_pcie(telemetry)
            self.assertEqual(result['pcie_rx'],4.0);self.assertEqual(result['pcie_tx'],6.0);self.assertEqual(result['pcie_replay_delta'],6)

    def test_host_fabric_summary_extracts_ranges(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'qualification-summary.json').write_text(json.dumps({'nccl':{'cases':36,'wrong_total':0,'comparisons':[{'collective':'all_reduce_perf','local_busbw_gbps':30,'cross_numa_busbw_gbps':21,'cross_numa_penalty_pct':30,'remote_cpu_penalty_pct':25}]},'p2p':[{'metric':'bandwidth','direction':'unidirectional','p2p_enabled':True,'min':34,'median':40,'max':42},{'metric':'bandwidth','direction':'bidirectional','p2p_enabled':True,'min':64,'median':73,'max':75}],'dcgm':{},'upi':{'status':'unavailable'},'limitations':['endpoint rates']}))
            (root/'fabric-qualification.json').write_text(json.dumps({'link_state':{'idle':'Gen1 x16','sustained_load':'Gen5 x16'}}))
            result=module.host_fabric_summary(str(root))
            self.assertEqual(result['same_numa_all_reduce_busbw_gbps'],{'minimum':30,'maximum':30});self.assertEqual(result['p2p_bidirectional_gbps']['median'],73);self.assertEqual(result['link_under_load'],'Gen5 x16')

    def test_server_metric_sum_supports_zero_and_multiple_series(self):
        document={"metrics":{"vllm:num_requests_waiting":{"series":[{"stats":{"avg":0.0}},{"stats":{"avg":2.0}}]}}}
        self.assertEqual(module.server_metric_sum(document,"vllm:num_requests_waiting","avg"),2.0)
        self.assertIsNone(module.server_metric_sum(document,"missing","avg"))

    def test_sglang_server_metrics(self):
        def metric(*values):
            return {"series":[{"stats":{"avg":value,"rate":value}} for value in values]}
        document={"metrics":{
            "sglang:num_running_reqs":metric(10,12),
            "sglang:num_queue_reqs":metric(2,3),
            "sglang:token_usage":metric(.25,.35),
            "sglang:mamba_usage":metric(.5,.7),
            "sglang:spec_accept_rate":metric(.4,.6),
            "sglang:prompt_tokens":metric(100,200),
            "sglang:generation_tokens":metric(300,400),
        }}
        result=module.sglang_server_metrics(document)
        self.assertEqual(result["running_requests"],22)
        self.assertEqual(result["waiting_requests"],5)
        self.assertAlmostEqual(result["kv_cache_usage"],30)
        self.assertAlmostEqual(result["mamba_usage"],60)
        self.assertAlmostEqual(result["speculative_acceptance"],50)
        self.assertEqual(result["server_prompt_rate"],300)
        self.assertEqual(result["server_decode_rate"],700)

    def test_haproxy_directional_metrics_and_backend_balance(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"haproxy.promjsonl"
            def body(front_in,front_out,retries,errors,a,b):
                return "\n".join((
                    f'haproxy_frontend_bytes_in_total{{proxy="qwen_frontend"}} {front_in}',
                    f'haproxy_frontend_bytes_out_total{{proxy="qwen_frontend"}} {front_out}',
                    f'haproxy_backend_bytes_in_total{{proxy="qwen_backends"}} {front_in}',
                    f'haproxy_backend_bytes_out_total{{proxy="qwen_backends"}} {front_out}',
                    'haproxy_backend_current_queue{proxy="qwen_backends"} 2',
                    f'haproxy_backend_retry_warnings_total{{proxy="qwen_backends"}} {retries}',
                    f'haproxy_frontend_request_errors_total{{proxy="qwen_frontend"}} {errors}',
                    'haproxy_backend_connection_errors_total{proxy="qwen_backends"} 0',
                    'haproxy_backend_response_errors_total{proxy="qwen_backends"} 0',
                    f'haproxy_server_sessions_total{{proxy="qwen_backends",server="a"}} {a}',
                    f'haproxy_server_sessions_total{{proxy="qwen_backends",server="b"}} {b}',
                ))
            path.write_text("\n".join(json.dumps({"timestamp_utc":t,"prometheus_text":body(*v)}) for t,v in (
                ("2026-01-01T00:00:00+00:00",(100,200,1,0,10,10)),
                ("2026-01-01T00:00:10+00:00",(1048676,2097352,3,1,20,30)),
            ))+"\n")
            result=module.haproxy_telemetry(Path(directory),10)
            self.assertAlmostEqual(result["haproxy_frontend_ingress"],.1)
            self.assertAlmostEqual(result["haproxy_frontend_egress"],.2)
            self.assertEqual(result["haproxy_retries"],2)
            self.assertEqual(result["haproxy_errors"],1)
            self.assertEqual(result["haproxy_queue"],2)
            self.assertAlmostEqual(result["haproxy_backend_imbalance"],66.6666667)

    def test_numeric_rows_repairs_unquoted_iso_timestamp_comma(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "telemetry.csv"
            path.write_text("timestamp_utc,value\n2026-08-30T06:37:19,351644000+00:00,42\n")
            rows = module.numeric_rows(path)
            self.assertEqual(rows, [{"timestamp_utc": "2026-08-30T06:37:19,351644000+00:00", "value": 42.0}])

    def test_process_memory_telemetry_uses_pss_and_components(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            (d/'process-memory.csv').write_text(
                'timestamp_utc,pid,comm,cmdline,rss_kib,pss_kib,pss_anon_kib,pss_file_kib,pss_shmem_kib,shared_clean_kib,shared_dirty_kib,private_clean_kib,private_dirty_kib,swap_kib,swappss_kib\n'
                't1,1,w,a,100,60,0,0,0,20,10,30,40,2,1\n'
                't1,2,w,b,200,120,0,0,0,40,20,50,60,3,1\n'
                't2,1,w,a,120,70,0,0,0,30,10,40,40,4,1\n'
                't2,2,w,b,220,130,0,0,0,50,20,60,60,4,1\n')
            result=module.process_memory_telemetry(d)
            self.assertAlmostEqual(result['process_rss'],320/2**20)
            self.assertAlmostEqual(result['process_pss'],190/2**20)
            self.assertAlmostEqual(result['process_private'],190/2**20)
            self.assertAlmostEqual(result['process_shared'],100/2**20)
            self.assertAlmostEqual(result['process_swap'],6.5/2**20)

    def test_process_memory_blank_fields_are_unavailable_not_zero(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Path(directory)
            (d/'process-memory.csv').write_text(
                'timestamp_utc,pid,comm,cmdline,rss_kib,pss_kib,private_clean_kib,private_dirty_kib,shared_clean_kib,shared_dirty_kib,swap_kib\n'
                't1,1,python,sglang.launch_server,,,,,,,\n')
            self.assertEqual(module.process_memory_telemetry(d),{})

    def test_local_canonical_telemetry(self):
        with tempfile.TemporaryDirectory() as directory:
            d = Path(directory)
            (d / "gpu.csv").write_text(
                "timestamp_utc,index,uuid,pci_bus_id,gpu_util_pct,memory_util_pct,memory_used_mib,memory_total_mib,power_w,temperature_c,sm_clock_mhz,memory_clock_mhz,pcie_gen,pcie_width\n"
                "2026-08-30T06:37:19,351644000+00:00,0,u,p,50,20,100,200,100,40,2000,1000,5,16\n"
                "2026-08-30T06:37:19,351644000+00:00,1,u,p,70,30,100,200,120,42,2200,1000,5,16\n")
            (d / "host.csv").write_text(
                "timestamp_utc,cpu_user,cpu_nice,cpu_system,cpu_idle,cpu_iowait,cpu_irq,cpu_softirq,cpu_steal,mem_total_kib,mem_available_kib,cached_kib,buffers_kib,swap_total_kib,swap_free_kib,load1,load5,load15\n"
                "2026-08-30T06:37:19,351644000+00:00,100,0,20,880,0,0,0,0,1048576,524288,0,0,0,0,2,2,2\n"
                "2026-08-30T06:37:20,351644000+00:00,200,0,40,1760,0,0,0,0,1048576,524288,0,0,0,0,4,3,2\n")
            result = module.local_telemetry(d, 2)
            self.assertEqual(result["gpu_utilization"], 60)
            self.assertEqual(result["gpu_board_power"], 220)
            self.assertAlmostEqual(result["host_cpu_busy"], 12, places=5)


if __name__ == "__main__":
    unittest.main()
