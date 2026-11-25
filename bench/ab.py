#!/usr/bin/env python3
"""A/B benchmark: does hezbit save tokens (and keep quality) compared with plain Claude Code?

For every task x run x arm it creates a clean git worktree, runs `claude -p` headless, then measures
cost/tokens/turns from Claude's JSON result and quality from the worktree itself (check command passes,
files changed outside the allowed scope, diff size).

Arms
  base    no plugin
  seeded  plugin on, brief pre-written from the task's "brief" (measures guards, read-size limits, verify;
          does NOT include the cost of the /hezbit:brief and /hezbit:plan conversation)
  full    plugin on, real workflow in 2 turns: /hezbit:brief <task>, then approve and implement (experimental)

Usage
  python ab.py tasks.json --repo H:\\path\\to\\repo --runs 5 --arms base,seeded --out results/run1
Needs: git, claude on PATH (or --claude-cmd), and a task file (see tasks.example.json).
Real runs bill your account: start with --runs 1 --tasks <one id>.
"""
import argparse, fnmatch, json, os, random, re, shlex, shutil, statistics, subprocess, sys, tempfile, time, uuid

PLUGIN_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
TOOLS = "Bash,Read,Edit,Write,MultiEdit,Grep,Glob"


def long_path(path):
    """Windows 8.3 names (C:\\Users\\USERNA~1) make Claude Code deny edits as 'suspicious path': expand them."""
    if os.name != "nt":
        return path
    import ctypes
    buf = ctypes.create_unicode_buffer(32768)
    n = ctypes.windll.kernel32.GetLongPathNameW(path, buf, 32768)
    return buf.value if 0 < n < 32768 else path


def sh(cmd, cwd, timeout=900, input=None):
    return subprocess.run(cmd, cwd=cwd, shell=isinstance(cmd, str), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout, input=input)


def git(repo, *args):
    r = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", errors="replace")
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.strip()}")
    return r.stdout


def claude_cmd(spec):
    if spec.lstrip().startswith("["):
        return json.loads(spec)
    c = shlex.split(spec, posix=(os.name != "nt"))
    c[0] = shutil.which(c[0]) or c[0]
    return c


def in_allowed(path, allowed):
    path = path.replace("\\", "/")
    for a in allowed:
        a = a.replace("\\", "/").lstrip("./")
        if path == a.rstrip("/") or path.startswith(a.rstrip("/") + "/") or fnmatch.fnmatch(path, a):
            return True
    return False


def seed_brief(wt, sid, task):
    b = task.get("brief")
    if not b:
        return False
    d = os.path.join(wt, ".claude", "hezbit", "sessions", re.sub(r"[^\w.-]", "_", sid))
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "request.md"), "w", encoding="utf-8") as f:
        f.write(task["prompt"] + "\n")
    with open(os.path.join(d, "brief.md"), "w", encoding="utf-8") as f:
        f.write(f"type: {b.get('type', 'CHANGE')}\nscope: {b.get('scope', '')}\nout: {b.get('out', 'none')}\n"
                "done:\n" + "".join(f"- {x}\n" for x in b.get("done", [])) + f"reply: {b.get('reply', 'diff-only')}\n")
    return True


def one_turn(cmd, wt, prompt, args, model, plugin, timeout):
    c = cmd + ["-p", "--output-format", "json", "--permission-mode", "acceptEdits", "--allowedTools", TOOLS]
    if model:
        c += ["--model", model]
    if plugin:
        c += ["--plugin-dir", PLUGIN_DIR]
    c += args
    t0 = time.time()
    try:
        r = sh(c, wt, timeout=timeout, input=prompt)
    except subprocess.TimeoutExpired:
        return {"error": "timeout", "wall_s": time.time() - t0}
    try:
        j = json.loads(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "{}")
    except ValueError:
        return {"error": f"bad json (rc={r.returncode}): {(r.stdout or r.stderr)[:200]}", "wall_s": time.time() - t0}
    u = j.get("usage") or {}
    return {"cost": j.get("total_cost_usd") or 0.0, "turns": j.get("num_turns") or 0, "is_error": bool(j.get("is_error")),
            "in": u.get("input_tokens", 0), "out": u.get("output_tokens", 0),
            "cache_w": u.get("cache_creation_input_tokens", 0), "cache_r": u.get("cache_read_input_tokens", 0),
            "denied": len(j.get("permission_denials") or []),
            "session": j.get("session_id"), "wall_s": time.time() - t0}


def measure(wt, task):
    check = sh(task["check"], wt, timeout=600) if task.get("check") else None
    sh(["git", "add", "-A", "--", ".", ":!.claude"], wt)
    names = [l for l in sh(["git", "diff", "--cached", "--name-only"], wt).stdout.splitlines() if l]
    added = deleted = 0
    for l in sh(["git", "diff", "--cached", "--numstat"], wt).stdout.splitlines():
        a, d, *_ = l.split("\t")
        added += int(a) if a.isdigit() else 0
        deleted += int(d) if d.isdigit() else 0
    allowed = task.get("allowed", [])
    return {"success": bool(check and check.returncode == 0) if check else None,
            "files": len(names), "lines": added + deleted,
            "out_of_scope": [n for n in names if allowed and not in_allowed(n, allowed)]}


def run_one(cfg, task, arm, run_no):
    wt = os.path.join(cfg["tmp"], f"{task['id']}-{arm}-{run_no}")
    git(cfg["repo"], "worktree", "add", "--detach", wt, cfg["ref"])
    try:
        if task.get("setup"):
            sh(task["setup"], wt, timeout=900)
        rec = {"task": task["id"], "kind": task.get("kind", ""), "arm": arm, "run": run_no}
        sid = str(uuid.uuid4())
        plugin = arm != "base"
        if arm == "seeded" and not seed_brief(wt, sid, task):
            return dict(rec, error="task has no brief; seeded arm skipped")
        if arm == "full":
            turns = [one_turn(cfg["cmd"], wt, f"/hezbit:brief {task['prompt']}", ["--session-id", sid],
                              cfg["model"], True, cfg["timeout"])]
            turns.append(one_turn(cfg["cmd"], wt, "OK to proceed. Implement it now, then run /hezbit:done.",
                                  ["--resume", turns[0].get("session") or sid], cfg["model"], True, cfg["timeout"]))
        else:
            extra = ["--session-id", sid] if plugin else []
            turns = [one_turn(cfg["cmd"], wt, task["prompt"], extra, cfg["model"], plugin, cfg["timeout"])]
        errs = [t["error"] for t in turns if "error" in t]
        if errs:
            return dict(rec, error="; ".join(errs))
        for k in ("cost", "turns", "in", "out", "cache_w", "cache_r", "wall_s", "denied"):
            rec[k] = sum(t[k] for t in turns)
        rec["is_error"] = any(t["is_error"] for t in turns)
        rec.update(measure(wt, task))
        return rec
    finally:
        subprocess.run(["git", "-C", cfg["repo"], "worktree", "remove", "--force", wt], capture_output=True)


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else float("nan")


def summarize(rows):
    ok = [r for r in rows if "error" not in r]
    lines = [f"runs: {len(ok)} ok, {len(rows) - len(ok)} failed to run", ""]
    head = "| group | arm | n | success | cost $ (med) | tokens in+out+cache write (med) | cache read (med) | turns (med) | out-of-scope files (avg) | denied tool calls (avg) | $ per success |"
    sep = "|" + "---|" * 11

    def table(title, keyf):
        out, groups = [f"### {title}", "", head, sep], {}
        for r in ok:
            groups.setdefault((keyf(r), r["arm"]), []).append(r)
        for (g, arm), rs in sorted(groups.items()):
            succ = [r for r in rs if r.get("success")]
            tot = sum(r["cost"] for r in rs)
            out.append(f"| {g} | {arm} | {len(rs)} | {100 * len(succ) // len(rs)}% | {med([r['cost'] for r in rs]):.3f} | "
                       f"{int(med([r['in'] + r['out'] + r['cache_w'] for r in rs]))} | {int(med([r['cache_r'] for r in rs]))} | "
                       f"{med([r['turns'] for r in rs]):.0f} | {sum(len(r['out_of_scope']) for r in rs) / len(rs):.1f} | "
                       f"{sum(r.get('denied', 0) for r in rs) / len(rs):.1f} | "
                       f"{(tot / len(succ)) if succ else float('nan'):.3f} |")
        return out + [""]

    return "\n".join(lines + table("By task kind", lambda r: r["kind"] or "-") + table("By task", lambda r: r["task"]))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tasks")
    ap.add_argument("--repo", help="git repo to benchmark (default: 'repo' in the task file)")
    ap.add_argument("--ref", default=None, help="commit/branch every run starts from (default: HEAD)")
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--arms", default="base,seeded")
    ap.add_argument("--tasks-only", default="", help="comma separated task ids")
    ap.add_argument("--model", default="")
    ap.add_argument("--claude-cmd", default="claude", help='command or JSON list, e.g. \'["python","fake.py"]\'')
    ap.add_argument("--timeout", type=int, default=1800)
    ap.add_argument("--out", default="ab-results")
    ap.add_argument("--seed", type=int, default=1)
    a = ap.parse_args()

    spec = json.load(open(a.tasks, encoding="utf-8-sig"))  # -sig: PowerShell writes a BOM
    repo = os.path.abspath(a.repo or spec["repo"])
    tasks = [t for t in spec["tasks"] if not a.tasks_only or t["id"] in a.tasks_only.split(",")]
    arms = a.arms.split(",")
    os.makedirs(a.out, exist_ok=True)
    rfile = os.path.join(a.out, "results.jsonl")
    rows = [json.loads(l) for l in open(rfile, encoding="utf-8")] if os.path.isfile(rfile) else []
    done = {(r["task"], r["arm"], r["run"]) for r in rows if "error" not in r}
    rows = [r for r in rows if "error" not in r]
    cfg = {"repo": repo, "ref": a.ref or spec.get("ref") or "HEAD", "model": a.model, "timeout": a.timeout,
           "cmd": claude_cmd(a.claude_cmd), "tmp": long_path(tempfile.mkdtemp(prefix="hz-ab-"))}
    git(repo, "rev-parse", "--verify", cfg["ref"])
    plan = [(t, arm, n) for t in tasks for n in range(1, a.runs + 1) for arm in arms if (t["id"], arm, n) not in done]
    random.Random(a.seed).shuffle(plan)  # interleave arms so time of day and cache state hit both equally
    print(f"{len(plan)} runs to do ({len(done)} already done) in {cfg['tmp']}")
    try:
        for i, (t, arm, n) in enumerate(plan, 1):
            print(f"[{i}/{len(plan)}] {t['id']} / {arm} / run {n}", flush=True)
            r = run_one(cfg, t, arm, n)
            if "error" in r:
                print("   skipped:", r["error"])
            elif r.get("denied"):
                print(f"   warning: {r['denied']} tool call(s) were denied by permissions (task may not be completable)")
            rows.append(r)
            with open(rfile, "a", encoding="utf-8") as f:
                f.write(json.dumps(r) + "\n")
    finally:
        shutil.rmtree(cfg["tmp"], ignore_errors=True)
        subprocess.run(["git", "-C", repo, "worktree", "prune"], capture_output=True)
    s = summarize(rows)
    with open(os.path.join(a.out, "summary.md"), "w", encoding="utf-8") as f:
        f.write(s)
    print("\n" + s)


if __name__ == "__main__":
    sys.exit(main())
