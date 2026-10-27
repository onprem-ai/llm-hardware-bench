#!/usr/bin/env python3
"""Sample Prometheus endpoints into one timestamped JSONL stream.

Each interval emits one record per endpoint with the same timestamp. This makes
multi-replica aggregation reproducible while preserving endpoint identity.
Missing scrapes are recorded with an error and empty body, never as zero.
"""
from __future__ import annotations
import argparse, datetime as dt, json, signal, time, urllib.request
from pathlib import Path

STOP=False

def stop(*_):
    global STOP
    STOP=True

def main():
    p=argparse.ArgumentParser()
    p.add_argument("output",type=Path)
    p.add_argument("interval",nargs="?",type=float,default=1.0)
    p.add_argument("urls",nargs="+")
    a=p.parse_args()
    if a.interval<=0:p.error("interval must be positive")
    a.output.parent.mkdir(parents=True,exist_ok=True)
    signal.signal(signal.SIGTERM,stop);signal.signal(signal.SIGINT,stop)
    with a.output.open("w") as stream:
        while not STOP:
            stamp=dt.datetime.now(dt.timezone.utc).isoformat()
            for url in a.urls:
                body="";error=None
                try:
                    with urllib.request.urlopen(url,timeout=min(5,max(1,a.interval))) as response:
                        body=response.read().decode(errors="replace")
                except Exception as exc:error=f"{type(exc).__name__}: {exc}"
                stream.write(json.dumps({"timestamp_utc":stamp,"endpoint_url":url,"prometheus_text":body,"error":error},separators=(",",":"))+"\n")
            stream.flush()
            deadline=time.monotonic()+a.interval
            while not STOP and time.monotonic()<deadline:time.sleep(min(.1,deadline-time.monotonic()))

if __name__=="__main__":main()
