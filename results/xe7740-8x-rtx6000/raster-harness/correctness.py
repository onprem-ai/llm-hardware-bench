"""Deterministic exact-match quality gate for expert-execution mode changes.

Coarse gate: detects gross behavioural change between A16, A8 and native W4A4.
NOT a distributional quality test (no KLD harness on this host); passing does not
establish numerical equivalence.

Check modes:
  plain "x"      -> require substring x (case-insensitive)
  "letters:x"    -> compare letters only, so letter-by-letter spelling passes
  ""             -> require any non-empty output

Run with --self-test to validate the gate logic without a server.
"""
import json, re, sys, urllib.request

PROMPTS = [
    ("arith", "What is 17*23? Answer with only the number.", "391"),
    ("arith2", "Compute 4096/8 + 12. Answer with only the number.", "524"),
    ("extract", "Extract the city from: 'The parcel arrived in Utrecht on Tuesday.' Answer with only the city.", "Utrecht"),
    ("code", "Output exactly this JSON with no prose: {\"ok\": true, \"n\": 5}", "ok"),
    ("spell", "Spell the word 'supercalifragilisticexpialidocious'.",
     "letters:supercalifragilisticexpialidocious"),
    ("logic", "If all Bloops are Razzies and all Razzies are Lazzies, are all Bloops definitely Lazzies? Answer yes or no.", "yes"),
    ("repeat", "Repeat exactly: the quick brown fox jumps over the lazy dog", "quick brown fox"),
]


def check(content, expect):
    """Pure comparison, unit-testable without a server."""
    if not expect:
        return bool(content)
    if expect.lower().startswith('letters:'):
        word = re.sub('[^a-z]', '', expect[len('letters:'):].lower())
        return word in re.sub('[^a-z]', '', content.lower())
    return expect.lower() in content.lower()


def self_test():
    """A gate that cannot fail is worse than no gate; prove it discriminates."""
    cases = [
        ("spell", "supercalifragilisticexpialidocious", True, "echoed"),
        ("spell", "S-U-P-E-R-C-A-L-I-F-R-A-G-I-L-I-S-T-I-C-E-X-P-I-A-L-I-D-O-C-I-O-U-S", True, "letter-spaced"),
        ("spell", "The spelling is: supercalifragilisticexpialidocious", True, "framed echo"),
        ("spell", "supercalifragilistik expialidocious", False, "misspelled"),
        ("spell", "I cannot spell that word.", False, "refusal"),
        ("arith", "391", True, "correct"),
        ("arith", "392", False, "wrong number"),
        ("arith", "", False, "empty output"),
        ("logic", "Yes.", True, "yes"),
        ("logic", "No.", False, "no"),
        ("repeat", "The QUICK BROWN FOX JUMPS", True, "case-insensitive"),
        ("repeat", "a rolling stone", False, "unrelated text"),
        ("code", '{"ok": true, "n": 5}', True, "json ok"),
        ("code", "no data here", False, "missing key"),
    ]
    by_id = {i: (p, e) for i, p, e in PROMPTS}
    bad = 0
    for cid, content, want, label in cases:
        got = check(content, by_id[cid][1])
        if got != want:
            bad += 1
            print(f"  BAD  {cid:<8} {label:<18} -> {got}, wanted {want}")
    print(f"self-test: {len(cases)-bad}/{len(cases)} behaved correctly")
    return 0 if bad == 0 else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == '--self-test':
        sys.exit(self_test())
    URL, OUT = sys.argv[1], sys.argv[2]
    rows = []
    for name, prompt, expect in PROMPTS:
        body = {"model": "glm-5.3-nvfp4-radixark",
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0, "max_tokens": 64}
        req = urllib.request.Request(
            URL + '/v1/chat/completions', method='POST',
            headers={'Content-Type': 'application/json'},
            data=json.dumps(body).encode())
        try:
            r = json.load(urllib.request.urlopen(req, timeout=300))
            content = (r['choices'][0]['message'].get('content') or '').strip()
        except Exception as exc:
            content = f'ERROR {type(exc).__name__}: {exc}'
        rows.append({'id': name, 'prompt': prompt, 'expect': expect,
                     'output': content, 'pass': check(content, expect)})
    report = {'checks': len(rows), 'passed': sum(1 for r in rows if r['pass']),
              'failed': [r['id'] for r in rows if not r['pass']], 'rows': rows}
    with open(OUT, 'w') as fh:
        fh.write(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('checks', 'passed', 'failed')}))
    sys.exit(0 if report['passed'] == report['checks'] else 1)


if __name__ == '__main__':
    main()
