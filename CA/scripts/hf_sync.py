#!/usr/bin/env python3
"""Sync campaign artifacts to the private HuggingFace dataset.

Large/derived artifacts live on HF (LFS) rather than in git, so a Codespace
restart (which wipes /tmp and cannot hold 20+ GB in /workspaces) never loses
work. Requires HF_TOKEN in the environment.

  HF_TOKEN=... python3 scripts/hf_sync.py                 # radar + stages + controls
  HF_TOKEN=... python3 scripts/hf_sync.py --with-db       # + the 23.6 GB DuckDB
  HF_TOKEN=... python3 scripts/hf_sync.py --download radar # restore into /tmp/eth-contracts
"""
import argparse
import os

REPO = os.environ.get("HF_REPO", "Mariano234/kontrol-campaign-data")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-db", action="store_true", help="also upload the 23.6 GB DuckDB")
    ap.add_argument("--download", choices=["radar", "db", "stages"], default=None)
    ap.add_argument("--dest", default="/tmp/eth-contracts-restore")
    args = ap.parse_args()

    from huggingface_hub import HfApi, hf_hub_download
    api = HfApi()
    if not os.environ.get("HF_TOKEN"):
        raise SystemExit("set HF_TOKEN")

    if args.download:
        os.makedirs(args.dest, exist_ok=True)
        paths = {
            "radar": ["radar/opcode_features.parquet", "radar/RADAR.md"],
            "db": ["db/eth_contracts.duckdb"],
            "stages": ["stages"],
        }[args.download]
        for p in paths:
            try:
                local = hf_hub_download(repo_id=REPO, repo_type="dataset", filename=p,
                                        local_dir=args.dest)
                print("downloaded", local)
            except Exception as e:
                print("skip", p, str(e)[:160])
        return

    api.upload_file(path_or_fileobj=f"{ROOT}/data/opcode_features.parquet",
                    path_in_repo="radar/opcode_features.parquet", repo_id=REPO, repo_type="dataset")
    api.upload_file(path_or_fileobj=f"{ROOT}/data/RADAR.md",
                    path_in_repo="radar/RADAR.md", repo_id=REPO, repo_type="dataset")
    api.upload_folder(folder_path=f"{ROOT}/harness/stages", path_in_repo="stages",
                      repo_id=REPO, repo_type="dataset")
    api.upload_folder(folder_path=f"{ROOT}/harness/controls", path_in_repo="controls",
                      repo_id=REPO, repo_type="dataset")
    print("radar + stages + controls uploaded")
    if args.with_db:
        db = "/tmp/eth-contracts/eth_contracts.duckdb"
        if os.path.exists(db):
            print("uploading DuckDB (%.1f GB) — this takes a while" % (os.path.getsize(db) / 1e9))
            api.upload_file(path_or_fileobj=db, path_in_repo="db/eth_contracts.duckdb",
                            repo_id=REPO, repo_type="dataset")
            print("DuckDB uploaded")
        else:
            print("no DuckDB at", db)


if __name__ == "__main__":
    main()
