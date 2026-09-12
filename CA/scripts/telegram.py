#!/usr/bin/env python3
"""Kontrol campaign Telegram bot helper (GitHub Actions friendly, stdlib only).

Modes:
  board             build + send/edit the live status board (URL buttons)
  notify-completed  send a completion notice for a finished run
  stale             alert on runs that look stuck (in_progress/queued too long)
  poll              consume getUpdates (commands from the user) and reply
  fallback          resume incomplete runs the GitHub watchdog missed

Requires TELEGRAM_BOT_TOKEN (+ TELEGRAM_CHAT_ID for pushes). Without a token it
degrades to printing, so `board` can be validated locally.
"""
import argparse
import datetime
import hashlib
import json
import os
import subprocess
import sys
import urllib.parse
import urllib.request

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT = os.environ.get("TELEGRAM_CHAT_ID", "")
STATE = os.environ.get("TG_STATE", ".tg_state.json")
OWNER = os.environ.get("CAMPAIGN_OWNER", "kingmariano")
STALE_MIN = int(os.environ.get("STALE_MIN", "120"))
QUEUE_MIN = int(os.environ.get("QUEUE_MIN", "45"))

REPOS = {
    "kontrol-stage1-sweep": ["stage1-cheap"],
    "kontrol-stage2-deepauth": ["stage2-deepauth"],
    "kontrol-stage3-math": ["stage3-math"],
    "kontrol-sanity-tracka": ["tracka-batch1", "tracka-batch2", "tracka-batch3"],
}


def gh(*a):
    return subprocess.check_output(["gh", *a], text=True)


def load_state():
    try:
        return json.load(open(STATE))
    except Exception:
        return {}


def save_state(s):
    json.dump(s, open(STATE, "w"))


def api(method, payload):
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def resolved_chat():
    return CHAT or load_state().get("chat_id")


def tg_send(text, buttons=None, chat=None, reply_to=None):
    if not TOKEN:
        print("[no-token] would send:\n" + text)
        return None
    payload = {"chat_id": chat or resolved_chat(), "text": text, "disable_web_page_preview": True}
    if reply_to:
        payload["reply_to_message_id"] = reply_to
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return api("sendMessage", payload)


def tg_edit(message_id, text, buttons=None):
    if not TOKEN:
        return None
    payload = {"chat_id": CHAT, "message_id": message_id, "text": text,
               "disable_web_page_preview": True}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    return api("editMessageText", payload)


def mins_since(iso):
    t = datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return int((datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() // 60)


def run_row(run):
    return {
        "id": run["databaseId"], "name": run["name"], "status": run["status"],
        "conclusion": run.get("conclusion"), "sha": run["headSha"][:7],
        "created": run["createdAt"], "mins": mins_since(run["createdAt"]),
    }


def latest_runs():
    out = []
    for repo, wfs in REPOS.items():
        for wf in wfs:
            try:
                r = json.loads(gh("run", "list", "-R", f"{OWNER}/{repo}", "-w", wf, "-L", "1",
                                  "--json", "databaseId,name,status,conclusion,headSha,createdAt"))
            except subprocess.CalledProcessError:
                continue
            if r:
                row = run_row(r[0]); row["repo"] = repo; row["wf"] = wf
                out.append(row)
    return out


def job_counts(repo, rid):
    try:
        j = json.loads(gh("run", "view", str(rid), "-R", f"{OWNER}/{repo}", "--json", "jobs"))["jobs"]
        st = [x["status"] for x in j]
        return len(st), st.count("completed"), st.count("in_progress"), st.count("queued")
    except subprocess.CalledProcessError:
        return 0, 0, 0, 0


def board_buttons():
    rows = []
    for repo in REPOS:
        rows.append([{"text": f"▶ {repo}", "url": f"https://github.com/{OWNER}/{repo}/actions"}])
    return rows


def build_board():
    runs = latest_runs()
    active = [r for r in runs if r["status"] in ("in_progress", "queued")]
    done = [r for r in runs if r["status"] == "completed"]
    lines = [f"📊 Kontrol campaign — {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC", ""]
    if active:
        lines.append(f"🟢 Active / queued ({len(active)}):")
        for r in sorted(active, key=lambda x: x["name"]):
            n, c, ip, q = job_counts(r["repo"], r["id"])
            eta = ""
            lines.append(f"  • {r['name']} #{r['id']} [{r['status']}] "
                         f"{c}/{n} done, {ip} run, {q} queued — {r['mins']}m")
    else:
        lines.append("🟢 Active / queued: none")
    lines.append("")
    lines.append("✅ Latest completed:")
    for r in sorted(done, key=lambda x: x["mins"])[:6]:
        lines.append(f"  • {r['name']} #{r['id']} {r['conclusion']} ({r['mins']}m ago)")
    return "\n".join(lines)


CMD_HELP = ("Commands: /board /active /queued /repos /id /help")


def handle_update(state, upd):
    msg = upd.get("message") or {}
    text = (msg.get("text") or "").strip().lower()
    chat = msg.get("chat", {}).get("id")
    if chat:
        state["chat_id"] = chat
    if not text.startswith("/"):
        return
    if text == "/id":
        tg_send(f"chat_id = {chat}", chat=chat)
    elif text in ("/start", "/help"):
        tg_send(CMD_HELP, chat=chat)
    elif text in ("/board", "/status"):
        tg_send(build_board(), buttons=board_buttons(), chat=chat)
    elif text == "/active":
        runs = [r for r in latest_runs() if r["status"] in ("in_progress", "queued")]
        tg_send("Active/queued:\n" + ("\n".join(
            f"• {r['name']} #{r['id']} [{r['status']}] {r['mins']}m" for r in runs) or "none"), chat=chat)
    elif text == "/queued":
        runs = [r for r in latest_runs() if r["status"] == "queued"]
        tg_send("Queued:\n" + ("\n".join(f"• {r['name']} #{r['id']} {r['mins']}m" for r in runs) or "none"), chat=chat)
    elif text == "/repos":
        tg_send("Campaign repos:\n" + "\n".join(f"• {r}" for r in REPOS), chat=chat)


def poll():
    state = load_state()
    off = state.get("update_offset")
    params = urllib.parse.urlencode({"timeout": 0, "allowed_updates": "[\"message\"]"})
    if off is not None:
        params += f"&offset={off}"
    if not TOKEN:
        print("[no-token] poll skipped")
        return
    res = api("getUpdates", {"timeout": 0, "offset": off} if off is not None else {"timeout": 0,
              "allowed_updates": ["message"]})
    for upd in res.get("result", []):
        off = upd["update_id"] + 1
        try:
            handle_update(state, upd)
        except Exception as e:
            print("update error:", e)
    state["update_offset"] = off
    save_state(state)


def stale():
    alerts = []
    for r in latest_runs():
        if r["status"] == "in_progress":
            n, c, ip, q = job_counts(r["repo"], r["id"])
            if r["mins"] > STALE_MIN and ip > 0:
                alerts.append(f"⚠️ {r['name']} #{r['id']} running {r['mins']}m "
                              f"({c}/{n} done, {ip} running). Still within the 350m cap.")
        elif r["status"] == "queued" and r["mins"] > QUEUE_MIN:
            alerts.append(f"⏳ {r['name']} #{r['id']} queued {r['mins']}m "
                          f"(runners saturated). Watchdog will resume when it starts.")
    if alerts:
        tg_send("🚨 Kontrol CI checks\n\n" + "\n".join(alerts), buttons=board_buttons())
    else:
        print("[stale] nothing to alert")
    return bool(alerts)


def fallback():
    """Resume incomplete runs the GitHub watchdog hasn't picked up (best-effort)."""
    import re
    acted = 0
    for repo, wfs in REPOS.items():
        for wf in wfs:
            runs = json.loads(gh("run", "list", "-R", f"{OWNER}/{repo}", "-w", wf, "-L", "5",
                                 "--json", "databaseId,status,headSha,createdAt,name"))
            if any(r["status"] in ("in_progress", "queued") for r in runs):
                continue
            if not runs:
                continue
            r0 = runs[0]
            if r0["status"] != "completed" or mins_since(r0["createdAt"]) > 720:
                continue
            stage = {"stage1-cheap": "1", "stage2-deepauth": "2", "stage3-math": "3"}.get(wf)
            if not stage:
                continue  # tracka handled by its own callers
            try:
                arts = json.loads(gh("api", f"repos/{OWNER}/{repo}/actions/runs/{r0['databaseId']}/artifacts?per_page=100"))["artifacts"]
            except subprocess.CalledProcessError:
                continue
            got = sorted(int(m.group(1)) for a in arts
                         for m in [re.search(rf"stage{stage}-results-chunk-(\d+)$", a["name"])] if m)
            if len(got) <= 1:
                continue
            # incomplete = manifest chunks without a result artifact
            man = json.load(open(f"CA/harness/stages/stage{stage}/manifest.json"))
            missing = [c["chunk"] for c in man["chunks"] if c["chunk"] not in got]
            if not missing:
                continue
            tg_send(f"🛟 Fallback resume: {wf} #{r0['databaseId']} missing {len(missing)} chunks "
                    f"→ re-dispatching", buttons=board_buttons())
            gh("workflow", "run", wf, "-R", f"{OWNER}/{repo}",
               "-f", "mode=full", "-f", f"chunks={','.join(map(str, missing))}",
               "-f", f"resume_run_id={r0['databaseId']}")
            acted += 1
    print(f"[fallback] dispatched={acted}")
    return acted


def notify_completed(repo, rid, name, conclusion):
    tg_send(f"✅ Workflow finished\n• {name} #{rid}\n• {repo}\n• result: {conclusion}",
            buttons=board_buttons())


def detect_completions(state):
    """Central completion detection: notify for runs that finished since last tick."""
    new = []
    seen = state.setdefault("seen", {})
    for r in latest_runs():
        key = f"{r['wf']}:{r['id']}"
        if r["status"] == "completed" and key not in seen:
            seen[key] = r["conclusion"]
            new.append(r)
    # prune to keep state small
    if len(seen) > 300:
        state["seen"] = dict(list(seen.items())[-150:])
    return new


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=["board", "poll", "stale", "fallback", "notify-completed", "send"])
    ap.add_argument("--repo")
    ap.add_argument("--run-id")
    ap.add_argument("--name")
    ap.add_argument("--conclusion")
    ap.add_argument("--text")
    ap.add_argument("--text-file")
    ap.add_argument("--send", action="store_true", help="board: also send (not just print)")
    a = ap.parse_args()
    if a.mode == "board":
        state = load_state()
        for r in detect_completions(state):
            notify_completed(r["repo"], r["id"], r["name"], r["conclusion"])
        text = build_board()
        if a.send and TOKEN:
            if state.get("board_id"):
                try:
                    tg_edit(state["board_id"], text, board_buttons())
                except Exception:
                    state["board_id"] = tg_send(text, board_buttons())["result"]["message_id"]
            else:
                state["board_id"] = tg_send(text, board_buttons())["result"]["message_id"]
        else:
            print(text)
        save_state(state)
    elif a.mode == "poll":
        poll()
    elif a.mode == "stale":
        stale()
    elif a.mode == "fallback":
        fallback()
    elif a.mode == "notify-completed":
        notify_completed(a.repo, a.run_id, a.name, a.conclusion)
    elif a.mode == "send":
        text = a.text or (open(a.text_file).read() if a.text_file and os.path.exists(a.text_file) else "")
        if text.strip():
            tg_send(text, buttons=board_buttons())
        else:
            print("[send] nothing to send")


if __name__ == "__main__":
    main()
