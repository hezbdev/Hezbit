#!/usr/bin/env python3
"""hz: tiny CLI so the model calls tools instead of re-reading/rewriting prose.
Usage: hz.py [-s <session>] request|lint|status|plan|next|step|scope-add|check|verify|last|map|find|stats|close|path"""
import os, re, shutil, sys, time
from glib import *


MAX_STEPS = 5  # matches /hezbit:plan ("max 5 steps")


def cmd_request(args):
    if args:
        write(p("request.md"), " ".join(args).strip() + "\n")
        print("request saved")
        return
    t = request_text()
    print(t[:1500] if t else "no request saved")


def cmd_lint():
    errs, notes = lint(parse_brief())
    for n in notes:
        print("NOTE: " + n)
    print("\n".join("ERROR: " + e for e in errs) if errs else "ok")
    return 1 if errs else 0


def cmd_status():
    b = parse_brief()
    if not b:
        print("no brief")
        return
    print(summary(with_next=True))
    items = plan_items()
    if items:
        print("plan: " + " ".join(f"{'x' if d else '.'}{i}" for i, (d, _) in enumerate(items, 1)))


def cmd_plan(args):
    if not args:
        print('usage: hz plan "step 1" "step 2" ...')
        return 1
    write(p("plan.md"), "\n".join(f"[ ] {a.strip()[:200]}" for a in args[:MAX_STEPS]) + "\n")
    print(f"plan saved: {len(args[:MAX_STEPS])} steps" + (f" (max {MAX_STEPS}; {len(args) - MAX_STEPS} dropped)" if len(args) > MAX_STEPS else ""))


def cmd_next():
    n = next_step()
    print(f"step {n[0]}/{n[1]}: {n[2]}" if n else "no pending step")


def cmd_step(note):
    lines = read_lines(p("plan.md"))
    for i, l in enumerate(lines):
        if l.startswith("[ ]"):
            lines[i] = "[x]" + l[3:] + (f" -> {note.strip()[:80]}" if note.strip() else "")
            write(p("plan.md"), "\n".join(lines) + "\n")
            cmd_next()
            return
    print("no pending step")


def cmd_scope_add(paths):
    b = parse_brief()
    if not b or not paths:
        print("usage: hz scope-add <path>  (needs a brief)")
        return 1
    new = b["scope_list"] + [x for x in paths if x not in b["scope_list"]]
    t = read(p("brief.md"))
    line = "scope: " + ", ".join(new)
    # callable replacement: a plain string would treat the backslashes in src\auth as escapes
    t, n = re.subn(r"^scope:.*$", lambda _m: line, t, count=1, flags=re.M | re.I)
    if not n:  # brief had no scope line: add it instead of dropping the path silently
        t = t.rstrip("\n") + "\n" + line + "\n"
    write(p("brief.md"), t)
    print("scope: " + ", ".join(new))


def cmd_check():
    b = parse_brief()
    if not b:
        print("no brief")
        return
    touched = read_lines(p("touched.txt"))
    touched += sorted(f for f in git_changed() if f not in touched)  # shell edits the hooks could not see
    out = [f for f in touched if b["type"] in NEEDS_SCOPE and not in_scope(f, b["scope_list"])]
    print(f"touched: {len(touched)} files" + (": " + ", ".join(touched[:10]) if touched else ""))
    print("out-of-scope: " + (", ".join(out) if out else "none"))
    items = plan_items()
    if items:
        left = [t for d, t in items if not d]
        print(f"plan: {len(items)-len(left)}/{len(items)} steps done" + (f"; left: {left[0][:60]}" if left else ""))


def cmd_verify():
    from verify import run_verify
    if not parse_brief():
        print("no brief")
        return 1
    status, lines, _, _ = run_verify()
    print("\n".join(lines))
    return 0 if status == "PASS" else 1


def cmd_last():
    t = read(p("verify.txt"))
    print(t.strip() if t else "no verify result yet: run hz verify")


def cmd_map(budget=60):
    dirs = {}
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in SKIP and not x.startswith(".")]
        code = sorted(f for f in fs if os.path.splitext(f)[1] in CODE_EXT)
        if code:
            dirs[rel(d)] = code
    rows = sorted(dirs.items(), key=lambda kv: (kv[0].count("/") if kv[0] != "." else -1, kv[0]))
    lines = [f"{r}/ ({len(f)}): " + ", ".join(f[:6]) + ("..." if len(f) > 6 else "") for r, f in rows[:budget]]
    if len(rows) > budget:
        lines.append(f"(+{len(rows)-budget} dirs omitted: use `hz find <term>`)")
    write(p("map.md"), "\n".join(lines) + "\n")
    print("\n".join(lines))


DEF = re.compile(r"^\s{0,4}(?:export\s+(?:default\s+)?)?(?:async\s+)?"
                 r"(?:def|class|function|interface|enum|struct|fn|func|type|const|let)\s+\w")
DEF_METHOD = re.compile(r"^\s{0,8}(?:public|private|protected)\b.*\w\s*\(")


def source_files():
    """Candidate files: git's own list (respects .gitignore) when available, else a pruned walk."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                           capture_output=True, timeout=15)
        if r.returncode == 0:
            for rp in r.stdout.decode("utf-8", "replace").split("\0"):
                if rp and os.path.splitext(rp)[1] in CODE_EXT and not is_state_path(rp):
                    yield os.path.join(ROOT, rp)
            return
    except (OSError, subprocess.SubprocessError):
        pass
    for d, ds, fs in os.walk(ROOT):
        ds[:] = [x for x in ds if x not in SKIP and not x.startswith(".")]
        for f in fs:
            if os.path.splitext(f)[1] in CODE_EXT:
                yield os.path.join(d, f)


def cmd_find(term, mx=12):
    if not term:
        print("usage: hz find <term-or-regex>")
        return 1
    try:
        rx = re.compile(term, re.I)
    except re.error:
        rx = re.compile(re.escape(term), re.I)
    hits = []
    for fp in source_files():
        try:
            if os.path.getsize(fp) > 300_000:
                continue
        except OSError:
            continue
        for i, l in enumerate(read(fp).splitlines(), 1):
            if rx.search(l):
                hits.append((0 if DEF.match(l) or DEF_METHOD.match(l) else 1, rel(fp), i, l.strip()[:100]))
        if len(hits) > 5000:
            break
    hits.sort(key=lambda h: (h[0], h[1], h[2]))
    for _, f, i, l in hits[:mx]:
        print(f"{f}:{i}: {l}")
    print(f"({len(hits)} matches, showing {min(mx, len(hits))})" if hits else "no matches")


def cmd_stats():
    rows = [l.split("\t") for l in read_lines(os.path.join(GL_BASE, "stats.log"))]
    rows = [r for r in rows if len(r) == 4]
    if not rows:
        print("no data yet")
        return
    kinds, sess = {}, set()
    for _, sid, k, n in rows:
        c = kinds.setdefault(k, [0, 0])
        c[0] += 1
        c[1] += int(n)
        sess.add(sid)
    total = sum(v[1] for v in kinds.values())
    prompts = kinds.get("prompt0", [0, 0])[0] + kinds.get("reinject", [0, 0])[0]
    print(f"sessions: {len(sess)}; prompts seen: {prompts}")
    for k, (cnt, ch) in sorted(kinds.items()):
        if ch:
            print(f"  {k}: {cnt}x, {ch} chars (~{ch//4} tokens)")
    print(f"total injected: {total} chars (~{total//4} tokens, rough 4 chars/token)")
    if prompts:
        print(f"avg per prompt: ~{total//4//prompts} tokens")


def cmd_close():
    names = ["brief.md", "request.md", "plan.md", "touched.txt", "verify.json", "verify.txt"]
    if not os.path.isfile(p("brief.md")):
        print("nothing to close")
        return
    save_git_baseline()  # the next task starts from a clean slate
    dest = os.path.join(GL_BASE, "archive", time.strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for n in names:
        if os.path.isfile(p(n)):
            shutil.move(p(n), os.path.join(dest, n))
    for n in ("stop_retries",):
        if os.path.isfile(p(n)):
            os.remove(p(n))
    arch = os.path.join(GL_BASE, "archive")
    for o in sorted(os.listdir(arch))[:-10]:
        shutil.rmtree(os.path.join(arch, o), ignore_errors=True)
    print("closed: brief archived. Suggest the user run /clear.")


def cmd_path(args):
    n = args[0] if args else "brief"
    print(p(n if "." in n else n + ".md"))


def main():
    a = sys.argv[1:]
    if len(a) >= 2 and a[0] in ("-s", "--session"):
        init_session(a[1])
        a = a[2:]
    c = a[0] if a else ""
    r = {
        "request": lambda: cmd_request(a[1:]), "lint": cmd_lint, "status": cmd_status,
        "plan": lambda: cmd_plan(a[1:]), "next": cmd_next, "step": lambda: cmd_step(" ".join(a[1:])),
        "scope-add": lambda: cmd_scope_add(a[1:]), "check": cmd_check, "verify": cmd_verify,
        "last": cmd_last, "map": cmd_map, "find": lambda: cmd_find(" ".join(a[1:])),
        "stats": cmd_stats, "close": cmd_close, "path": lambda: cmd_path(a[1:]),
    }.get(c)
    if not r:
        print(__doc__)
        return 1
    return r() or 0


if __name__ == "__main__":
    sys.exit(main())
