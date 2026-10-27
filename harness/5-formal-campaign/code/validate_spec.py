#!/usr/bin/env python3
"""Validate YAML/JSON records against a repository JSON Schema."""
import argparse,json,pathlib,sys
try:
 import yaml
 import jsonschema
except ImportError as e:
 raise SystemExit(f"missing dependency {e.name}; install harness/2-preflight-conformance/code/bootstrap/requirements.in")
def main():
 p=argparse.ArgumentParser(); p.add_argument('document',type=pathlib.Path); p.add_argument('--schema',required=True,type=pathlib.Path); a=p.parse_args()
 data=json.loads(a.document.read_text()) if a.document.suffix=='.json' else yaml.safe_load(a.document.read_text())
 schema=json.loads(a.schema.read_text()); validator=jsonschema.Draft202012Validator(schema,format_checker=jsonschema.FormatChecker()); errors=sorted(validator.iter_errors(data),key=lambda e:list(e.path))
 for e in errors: print(f"{'.'.join(map(str,e.absolute_path)) or '<root>'}: {e.message}",file=sys.stderr)
 if errors:return 1
 print(f"valid: {a.document} against {a.schema}"); return 0
if __name__=='__main__': raise SystemExit(main())
