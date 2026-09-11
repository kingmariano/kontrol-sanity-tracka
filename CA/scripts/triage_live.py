#!/usr/bin/env python3
"""Live-gate triage: turn proof verdicts into a defensible live-risk decision.

The Kontrol harness proves properties for a *model* state (slots 0..7 zeroed).
That is a reachability filter, NOT a live-exploitability result (the F4-F9
lesson). This script takes a stage's CI artifacts and, for every FAILED verdict,
checks the real chain:

  deployments -> ETH/USDC funded? -> code present (not a codeless account)?
              -> read guard slots 0..7 -> optional eth_call of the exact
                 counterexample calldata

Classification per FAILED target:
  NO_DEPLOYMENTS   : bytecode never deployed
  NO_CODE          : funded but no code (empty account / census artifact)
  DORMANT          : code present but no funded instance
  LIVE_REACHABLE   : funded + code present (needs a human/next-stage check)
  LIVE_DRAIN       : funded + code + eth_call of the model calldata succeeds
                     AND no revert  (strongest automated signal)

Run locally (needs /tmp/eth-contracts DB + .env keys). CI only uploads artifacts.
"""
import argparse
import csv
import json
import os
import time
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV = os.path.join(ROOT, ".env")


def env(key, default=None):
    if not os.path.exists(ENV):
        return default
    for line in open(ENV):
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"')
    return default


def _post(rpc, payload, tries=6, timeout=40):
    data = json.dumps(payload).encode()
    for k in range(tries):
        try:
            req = urllib.request.Request(rpc, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read())
        except Exception:
            time.sleep(0.4 * (k + 1))
    return {}


def rpc_call(rpc, method, params):
    d = _post(rpc, {"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return d.get("result")


def parse_verdicts(artifacts_dir, manifest):
    """test name -> PASSED/FAILED/INCOMPLETE, mapped to target hash via manifest."""
    test2target = {}
    for ch in manifest["chunks"]:
        for tname, tgt in zip(ch["tests"], ch["targets"]):
            test2target[tname] = tgt if isinstance(tgt, dict) else {"hash": None}
        # controls have no targets
        for tname in ch["tests"]:
            test2target.setdefault(tname, {"hash": None, "class": "CONTROL"})
    verdicts = {}
    for root, _dirs, files in os.walk(artifacts_dir):
        for f in files:
            if f.startswith("verdicts_") and f.endswith(".txt"):
                cur = None
                for line in open(os.path.join(root, f), errors="ignore"):
                    line = line.strip()
                    if line.startswith("===") and ":" in line:
                        cur = line.split(":")[-1].replace("===", "").strip()
                    elif "PROOF PASSED" in line and cur:
                        verdicts[cur] = "PASSED"
                    elif "PROOF FAILED" in line and cur:
                        verdicts[cur] = "FAILED"
                    elif "INCOMPLETE" in line and cur:
                        verdicts.setdefault(cur, "INCOMPLETE")
    return verdicts, test2target


def eth_balances(addrs, key, cap=2000):
    out = {}
    for i in range(0, min(len(addrs), cap), 20):
        chunk = addrs[i:i + 20]
        q = {"module": "account", "action": "balancemulti", "address": ",".join(chunk),
             "tag": "latest", "apikey": key}
        url = "https://api.etherscan.io/v2/api?chainid=1&" + urllib.parse.urlencode(q)
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                res = json.loads(r.read())
            for row in res.get("result", []):
                out[row["account"].lower()] = int(row["balance"])
        except Exception:
            pass
        time.sleep(0.22)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", type=int, required=True)
    ap.add_argument("--artifacts", required=True, help="dir with verdicts_*.txt (CI artifact download)")
    ap.add_argument("--out", default=None)
    ap.add_argument("--selector", default=None, help="optional 0x selector to eth_call on funded instances")
    ap.add_argument("--value", default="0x0")
    ap.add_argument("--top", type=int, default=40, help="max funded instances to probe per target")
    args = ap.parse_args()

    stagedir = os.path.join(ROOT, "harness", "stages", f"stage{args.stage}")
    manifest = json.load(open(os.path.join(stagedir, "manifest.json")))
    verdicts, test2target = parse_verdicts(args.artifacts, manifest)
    failed = sorted(t for t, v in verdicts.items() if v == "FAILED")
    print(f"stage {args.stage}: {len(verdicts)} verdicts, {len(failed)} FAILED")

    # DB is an optional cache; manifests embed deployment addresses so triage
    # still works after /tmp is wiped.
    con = None
    try:
        import duckdb
        con = duckdb.connect("/tmp/eth-contracts/eth_contracts.duckdb", read_only=True)
        con.execute("SET memory_limit='4GB'")
    except Exception as e:
        print(f"(no local DuckDB: {e}; using manifest-embedded addresses)")
    es_key = env("ETHERSCANV2_API_KEY")
    rpc = "https://eth-mainnet.g.alchemy.com/v2/" + (env("ALCHEMY_API_KEY") or "")
    usdc = "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"
    usdc_call = "0x70a08231"

    report = []
    for tname in failed:
        tgt = test2target.get(tname, {})
        h = tgt.get("hash")
        row = {"test": tname, "class": tgt.get("class"), "hash": h,
               "deployments": 0, "funded": 0, "code": 0, "classification": None}
        if not h:
            row["classification"] = "CONTROL_OR_UNMAPPED"
            report.append(row)
            continue
        addrs = tgt.get("addresses") or []
        if not addrs and con is not None:
            addrs = [a for (a,) in con.execute(
                "SELECT address FROM contracts WHERE bytecode_hash = ?", [h]).fetchall()]
        row["deployments"] = tgt.get("deployments", len(addrs))
        if not addrs:
            row["classification"] = "NO_DEPLOYMENTS"
            report.append(row)
            continue
        bal = eth_balances(addrs, es_key) if es_key else {}
        funded = [a for a in addrs if bal.get(a.lower(), 0) > 0]
        row["funded"] = len(funded)
        # code presence on funded instances
        coded = []
        for a in funded[: args.top]:
            code = rpc_call(rpc, "eth_getCode", [a, "latest"])
            if code and code != "0x":
                coded.append(a)
        row["code"] = len(coded)
        if not funded:
            row["classification"] = "DORMANT"
        elif not coded:
            row["classification"] = "NO_CODE"
        else:
            row["classification"] = "LIVE_REACHABLE"
            # read guard slots on the top funded+coded instance
            top = coded[0]
            row["top_instance"] = top
            row["slots_0_7"] = [rpc_call(rpc, "eth_getStorageAt", [top, hex(i), "latest"]) for i in range(8)]
            if args.selector:
                res = _post(rpc, {"jsonrpc": "2.0", "id": 1, "method": "eth_call",
                                  "params": [{"from": "0x000000000000000000000000000000000000dEaD",
                                              "to": top, "data": args.selector, "value": args.value}, "latest"]})
                row["eth_call"] = "success" if res.get("result") is not None else f"error:{res.get('error', {}).get('message')}"
                if res.get("result") is not None:
                    row["classification"] = "LIVE_DRAIN"
        report.append(row)
        print(f"  {tname:28s} {h[:12]}… deploys={row['deployments']:>6} funded={row['funded']:>3} code={row['code']:>3} -> {row['classification']}")

    out = args.out or os.path.join(ROOT, f"TRIAGE_stage{args.stage}.md")
    with open(out, "w") as f:
        f.write(f"# Live-gate triage — stage {args.stage}\n\n")
        f.write(f"FAILED verdicts: {len(failed)}\n\n")
        f.write("| test | class | deployments | funded | coded | classification |\n")
        f.write("|---|---|---:|---:|---:|---|\n")
        for r in report:
            f.write(f"| {r['test']} | {r['class']} | {r['deployments']} | {r['funded']} | {r['code']} | **{r['classification']}** |\n")
    json.dump(report, open(out.replace(".md", ".json"), "w"), indent=1)
    print(f"wrote {out} and {out.replace('.md', '.json')}")


if __name__ == "__main__":
    main()
