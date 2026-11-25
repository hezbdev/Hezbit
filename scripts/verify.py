"""Run runnable `done` items (cmd :: expected) without a shell, return trimmed evidence."""
import json, os, re, shlex, shutil, subprocess, time
from glib import *

ANSI = re.compile(r"\x1b\[[0-9;]*m")
ERR = re.compile(r"(error|exception|fail|assert|traceback|✕|✗|×)", re.I)
MSG = re.compile(r"(Error|Exception|expected|Expected|!=|received|Received)")
SUMMARY = re.compile(r"(\d+ (passed|failed)|Tests?:|Ran \d+|FAILED|BUILD (SUCCESS|FAILURE))")
PATHTOK = re.compile(r"[\w@./\\-]+\.(?:%s)" % "|".join(e.lstrip(".") for e in CODE_EXT))


def is_project_ref(line):
    for m in PATHTOK.finditer(line):
        tok = m.group(0)
        cand = tok if os.path.isabs(tok) else os.path.join(ROOT, tok)
        if os.path.isfile(cand):
            r = rel(cand)
            if not outside(r) and not any(x in SKIP for x in r.split("/")):
                return True
    return False


def trim(out, maxl=8):
    lines = [ANSI.sub("", l).rstrip() for l in out.splitlines() if l.strip()]
    if not lines:
        return ["(no output)"]
    idx = next((i for i, l in enumerate(lines) if ERR.search(l)), None)
    if idx is None:
        return [l[:160] for l in lines[-3:]]
    res, msgs = [lines[idx][:160]], 0
    for l in lines[idx + 1: idx + 60]:
        if len(res) >= maxl - 1:
            break
        if is_project_ref(l):
            res.append(l.strip()[:160])
        elif msgs < 2 and MSG.search(l):
            res.append(l.strip()[:160]); msgs += 1
    summ = [l for l in lines if SUMMARY.search(l)]
    if summ and summ[-1][:160] not in res:
        res.append(summ[-1][:160])
    return res


def run_verify():
    b = parse_brief()
    lines, npass, ntotal, nskip, nmanual, nlate = [], 0, 0, 0, 0, 0
    deadline = time.time() + VERIFY_BUDGET
    for i, d in enumerate(b["done"] if b else [], 1):
        if " :: " not in d:
            nmanual += 1
            lines.append(f"MANUAL {i}. {d[:100]} (you must check this yourself)")
            continue
        cmd, exp = [x.strip() for x in d.split(" :: ", 1)]
        if not allowed_cmd(cmd):
            nskip += 1
            lines.append(f"SKIP {i}. not allowlisted: {cmd[:80]}")
            continue
        limit = min(VERIFY_ITEM_MAX, deadline - time.time())
        if limit < 5:  # shared budget keeps the whole run under the Stop hook timeout
            nlate += 1
            lines.append(f"LATE {i}. not run: verify time budget ({VERIFY_BUDGET}s) used up: {cmd[:60]}")
            continue
        ntotal += 1
        try:
            argv = split_cmd(cmd)
            argv[0] = shutil.which(argv[0]) or argv[0]
            r = subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=limit, errors="replace")
            out, rc = (r.stdout or "") + "\n" + (r.stderr or ""), r.returncode
        except subprocess.TimeoutExpired:
            out, rc = f"timeout after {int(limit)}s", 124
        except (OSError, ValueError) as e:
            out, rc = f"cannot run: {e}", 127
        want_text = exp and not exp.lower().startswith("exit")
        good = rc == 0 and (not want_text or exp.lower() in out.lower())
        if good:
            npass += 1
            lines.append(f"PASS {i}. {cmd[:80]}")
        else:
            lines.append(f"FAIL {i}. {cmd[:80]} (exit {rc})")
            if rc == 0 and want_text:
                lines.append(f'  expected text not found: "{exp[:60]}"')
            lines += ["  " + x for x in trim(out)]
    # FAIL: a runnable item failed. INCOMPLETE: nothing failed but something was not checked
    # (no runnable item, SKIP, or MANUAL). PASS only when every done item ran and passed.
    if npass < ntotal:
        status = "FAIL"
    elif ntotal == 0 or nskip or nmanual or nlate:
        status = "INCOMPLETE"
    else:
        status = "PASS"
    head = f"verify: {status} {npass}/{ntotal} run" if ntotal else f"verify: {status} no runnable done items"
    if status == "INCOMPLETE":
        head += f"; unchecked: {nskip} skipped, {nmanual} manual, {nlate} late"
    lines.append(head)
    if len(lines) > 15:
        lines = lines[:14] + [lines[-1]]
    write(p("verify.txt"), "\n".join(lines) + "\n")
    write(p("verify.json"), json.dumps({"status": status, "pass": npass, "total": ntotal,
                                        "skip": nskip, "manual": nmanual, "late": nlate, "t": time.time()}))
    if status != "FAIL" and os.path.isfile(p("stop_retries")):
        os.remove(p("stop_retries"))
    return status, lines, npass, ntotal
