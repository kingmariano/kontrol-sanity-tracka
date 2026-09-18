#!/usr/bin/env python3
"""Triage non-control PROOF FAILED verdicts by replaying them on-chain.

For every FAIL in a target chunk (chunk > 0):
  1. map (stage, chunk, idx) -> bytecode_hash -> deployment addresses
  2. replay the probe's calldata (selector + two 32-byte words) from a
     non-privileged EOA via eth_call against each deployment
  3. ALL replicas revert  -> FALSE POSITIVE (record reason)
     ANY replica succeeds -> CANDIDATE (needs manual review)

Two encodings are tried: zero args (mirrors the probe) and a real contract as
the first argument (in case a zero arg reverts for unrelated reasons).

Output: data/funds/triage.json + a printed table.
"""
import argparse
import glob
import json
import os
import re
import urllib.request

import duckdb

WETH = "c02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
EOA = "0x1111111111111111111111111111111111111111"


def rpc(url, method, params, timeout=30):
    body = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        d = json.load(urllib.request.urlopen(req, timeout=timeout))
    except Exception as e:
        try:
            d = json.load(e)
        except Exception:
            return None, str(e)[:100]
    if d.get("result") is not None:
        return d["result"], None
    err = d.get("error") or {}
    return None, f"{err.get('message', '')} {err.get('data', '')}".strip()[:140]


def replay(url, addr, selector):
    for arg in ("0" * 64, WETH + "0" * 24):
        res, err = rpc(url, "eth_call",
                       [{"from": EOA, "to": addr, "data": selector + arg}, "latest"])
        if res is not None:
            return "SUCCESS", ""
    return "REVERT", err


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--verdicts", default="/tmp/allverd")
    ap.add_argument("--waves", nargs="+", default=["/tmp/wave_b0", "/tmp/wave_b1", "/tmp/wb2"])
    ap.add_argument("--addresses", default="data/funds/tracka_addresses.parquet")
    ap.add_argument("--targets", default="data/funds/targets_usd.parquet")
    ap.add_argument("--out", default="data/funds/triage.json")
    args = ap.parse_args()

    env = {}
    for line in open(os.path.join(os.path.dirname(__file__), "..", ".env")):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k] = v.strip().strip('"').strip("'")
    url = f"https://eth-mainnet.g.alchemy.com/v2/{env['ALCHEMY_API_KEY']}"

    man = {}
    for root in args.waves:
        for d in glob.glob(os.path.join(root, "stage*")):
            m = json.load(open(os.path.join(d, "manifest.json")))
            man[m["stage"]] = m

    con = duckdb.connect()
    vals = dict(con.execute(
        f"SELECT bytecode_hash, total_usd FROM read_parquet('{args.targets}')").fetchall())

    fails = {}
    for f in glob.glob(os.path.join(args.verdicts, "*.txt")):
        stage_m = re.search(r"(fundedb[012])_(\w+)_(\d+)", os.path.basename(f))
        if not stage_m:
            continue
        for line in open(f, errors="ignore"):
            m = re.search(r"=== (test_\w+?)_c(\d+)_(\d+)_([0-9a-f]{8})_([ze]) .*?"
                          r"(PROOF FAILED|FAILED)", line)
            if not m or int(m.group(2)) == 0:
                continue
            stage = f"{stage_m.group(1)}_{stage_m.group(2)}"
            fails[(stage, int(m.group(2)), int(m.group(3)))] = (m.group(4), m.group(5),
                                                               os.path.basename(f))

    out, rows = [], []
    for (stage, chunk, idx), (sel, model, src) in sorted(fails.items()):
        m = man.get(stage)
        if not m:
            continue
        ch = [c for c in m["chunks"] if c["chunk"] == chunk]
        if not ch or idx >= len(ch[0]["targets"]):
            continue
        h = ch[0]["targets"][idx]["hash"]
        addrs = [a for (a,) in con.execute(
            f"SELECT address FROM read_parquet('{args.addresses}') "
            f"WHERE bytecode_hash='{h}' ORDER BY blocknum DESC LIMIT 3").fetchall()]
        verdicts, reasons = [], []
        for a in addrs:
            v, why = replay(url, a, "0x" + sel)
            verdicts.append(v)
            reasons.append(why)
        cls = "CANDIDATE" if "SUCCESS" in verdicts else "FALSE_POSITIVE"
        rec = {"stage": stage, "chunk": chunk, "idx": idx, "selector": sel,
               "model": model, "target": h, "value_usd": vals.get(h, 0),
               "addresses": addrs, "replay": verdicts,
               "revert_reason": next((r for r in reasons if r), ""),
               "class": cls, "source": src}
        out.append(rec)
        rows.append(rec)

    with open(args.out, "w") as fh:
        json.dump(out, fh, indent=1)
    print(f"triaged {len(rows)} non-control FAILs -> {args.out}")
    for r in rows:
        print(f"  [{r['class']:14s}] {r['stage']} c{r['chunk']}[{r['idx']}] "
              f"sel={r['selector']} ${r['value_usd']:>15,.0f} "
              f"replay={','.join(r['replay'])} reason={r['revert_reason'][:60]}")


if __name__ == "__main__":
    main()
