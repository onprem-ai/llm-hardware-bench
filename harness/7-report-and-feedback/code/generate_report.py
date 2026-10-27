#!/usr/bin/env python3
from __future__ import annotations
import pathlib
"""One-command comparable report generation for a supported campaign layout."""
import argparse, subprocess, sys
from pathlib import Path

ROOT = next(_a for _a in pathlib.Path(__file__).resolve().parents
            if (_a / '.git').exists())
ADAPTERS={"protocol":ROOT/"harness/7-report-and-feedback/code/adapters/protocol_campaign.py"}

def run(command):
    print("+", " ".join(map(str,command)))
    subprocess.run([str(x) for x in command],check=True)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("campaign",type=Path)
    p.add_argument("config",type=Path)
    p.add_argument("--adapter",choices=sorted(ADAPTERS),default="protocol")
    p.add_argument("--output-dir",type=Path)
    a=p.parse_args(); output=(a.output_dir or a.campaign/"report").resolve()
    output.mkdir(parents=True,exist_ok=True)
    run([sys.executable,ADAPTERS[a.adapter],a.campaign,a.config,"--output",output])
    config=output/"report-config.json";data=output/"normalized-report-data.json"
    run([sys.executable,ROOT/"harness/7-report-and-feedback/code/validate_report_inputs.py",config,data])
    run([sys.executable,ROOT/"harness/7-report-and-feedback/code/render_report.py",config,data,"--output-dir",output])
    print(f"comparable report artifacts: {output}")
if __name__=="__main__":main()
