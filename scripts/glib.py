"""hezbit shared helpers. State lives in <project>/.claude/hezbit/."""
import hashlib, json, os, re, shlex, shutil, subprocess, sys, tempfile, time

# Windows consoles default to cp125x: force UTF-8 so Vietnamese text survives stdin/stdout.
for _s in (sys.stdin, sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

ROOT = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
GL_BASE = os.path.join(ROOT, ".claude", "hezbit")
GL = GL_BASE  # per-session state dir, set by init_session()


def _safe(sid):
    return re.sub(r"[^\w.-]", "_", str(sid))[:64] or "default"


def resolve_session(sid=None):
    """Hooks pass the exact session id. The CLI uses -s/HEZBIT_SESSION, else the most recently active one."""
    if sid:
        return _safe(sid)
    env = os.environ.get("HEZBIT_SESSION")
    if env:
        return _safe(env)
    sd = os.path.join(GL_BASE, "sessions")
    best, best_t = None, -1.0
    try:
        for n in os.listdir(sd):
            d = os.path.join(sd, n)
            if not os.path.isdir(d):
                continue
            t = _last_active(d)
            if t > best_t:
                best, best_t = n, t
    except OSError:
        pass
    return best or "default"


def init_session(sid=None):
    global GL
    s = resolve_session(sid)
    GL = os.path.join(GL_BASE, "sessions", s)
    return s


def touch_session():
    """Mark this session as the most recently active (only if it already has state)."""
    try:
        if os.path.isdir(GL):
            with open(os.path.join(GL, ".ping"), "w") as f:
                f.write("1")
    except OSError:
        pass


def _last_active(d):
    ping = os.path.join(d, ".ping")
    return max(os.path.getmtime(d), os.path.getmtime(ping) if os.path.isfile(ping) else 0)


def prune_sessions(days=14):
    """Delete sessions idle for `days`. Idle = neither the dir nor its .ping heartbeat changed."""
    sd = os.path.join(GL_BASE, "sessions")
    try:
        for n in os.listdir(sd):
            d = os.path.join(sd, n)
            if os.path.isdir(d) and d != GL and time.time() - _last_active(d) > days * 86400:
                shutil.rmtree(d, ignore_errors=True)
    except OSError:
        pass


init_session()
SKIP = {".git", "node_modules", "dist", "build", ".next", "target", "__pycache__",
        ".venv", "venv", "coverage", ".idea", ".gradle", "out"}
CODE_EXT = {".js", ".ts", ".tsx", ".jsx", ".vue", ".java", ".kt", ".py", ".go", ".rs", ".php",
            ".cs", ".rb", ".sql", ".css", ".scss", ".html", ".xml", ".yml", ".yaml", ".json",
            ".md", ".properties", ".gradle"}
TYPES = ("FIX", "ADD", "CHANGE", "EXPLAIN", "REVIEW")
NEEDS_SCOPE = ("FIX", "ADD", "CHANGE")
SAFE_SCRIPTS = ("test", "lint", "typecheck", "check", "tsc")
VERIFY_BUDGET = int(os.environ.get("HEZBIT_VERIFY_BUDGET", 240))  # total seconds; Stop hook limit is 300
VERIFY_ITEM_MAX = 120
NEG = re.compile(r"(?<!\w)(không|đừng|chớ|chỉ|trừ|cấm|don't|dont|do not|never|only|except|without|must not|avoid)(?!\w)", re.I)


def p(name):
    return os.path.join(GL, name)


def read(path):
    try:
        with open(path, encoding="utf-8", errors="ignore") as f:
            return f.read()
    except OSError:
        return ""


def read_lines(path):
    return [l.rstrip("\n") for l in read(path).splitlines() if l.strip()]


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def rel(path):
    # realpath on both sides: Windows 8.3 short names (USERNA~1) and symlinks must not look like "outside"
    ap = os.path.realpath(path if os.path.isabs(path) else os.path.join(ROOT, path))
    try:
        return os.path.relpath(ap, os.path.realpath(ROOT)).replace("\\", "/")
    except ValueError:  # Windows: different drive
        return ap.replace("\\", "/")


def outside(r):
    """True if a rel() result points outside the project (incl. another drive)."""
    return r == ".." or r.startswith("../") or os.path.isabs(r) or re.match(r"^[A-Za-z]:", r) is not None


def split_cmd(cmd):
    """shlex.split that keeps backslashes on Windows."""
    if os.name != "nt":
        return shlex.split(cmd)
    out = []
    for t in shlex.split(cmd, posix=False):
        if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'":
            t = t[1:-1]
        out.append(t)
    return out


def request_text():
    return read(p("request.md")).strip()


def brief_hash():
    return hashlib.md5((read(p("brief.md")) + "\0" + read(p("request.md"))).encode()).hexdigest()


def stat(kind, text="", sid="x"):
    """Append an injection record (chars only). Only if the project already uses hezbit."""
    if not os.path.isdir(GL_BASE):
        return
    try:
        path = os.path.join(GL_BASE, "stats.log")
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{int(time.time())}\t{sid}\t{kind}\t{len(text)}\n")
        lines = read_lines(path)
        if len(lines) > 2000:
            write(path, "\n".join(lines[-1000:]) + "\n")
    except OSError:
        pass


def marker(sid):
    return os.path.join(tempfile.gettempdir(), "hz-inj-" + str(sid))


# ---------- brief ----------
def parse_brief():
    t = read(p("brief.md"))
    if not t.strip():
        return None
    b, cur = {"done": []}, None
    for line in t.splitlines():
        s = line.rstrip()
        m = re.match(r"^(type|scope|out|reply|done):\s*(.*)$", s, re.I)
        if m:
            cur, v = m.group(1).lower(), m.group(2).strip()
            if cur == "done":
                if v:
                    b["done"].append(v)
            else:
                b[cur] = v
        elif cur == "done" and s.lstrip().startswith("-"):
            b["done"].append(s.lstrip()[1:].strip())
    b["type"] = b.get("type", "").upper()
    b["scope_list"] = [x.strip() for x in b.get("scope", "").split(",") if x.strip()]
    return b


# ---------- command allowlist (verify runs without a shell, only these) ----------
def allowed_cmd(cmd):
    extra = [x.strip() for x in os.environ.get("HEZBIT_ALLOW", "").split(",") if x.strip()]
    if any(cmd == x or cmd.startswith(x + " ") for x in extra):  # whole-word prefix, not "npm" -> "npm-evil"
        return True
    try:
        a = split_cmd(cmd)
    except ValueError:
        return False
    if not a:
        return False
    exe = os.path.basename(a[0]).lower().replace(".cmd", "").replace(".exe", "")
    rest = [x for x in a[1:] if not x.startswith("-")]
    first = rest[0] if rest else ""
    if exe in ("npm", "pnpm", "yarn"):
        if first in ("test", "t"):
            return True
        if first in ("run", "run-script"):  # `run <any>` would execute whatever package.json says
            script = rest[1] if len(rest) > 1 else ""
            return script in SAFE_SCRIPTS or script.startswith("test:")
        return False
    if exe == "npx":
        return first in ("jest", "vitest", "tsc", "eslint")
    if exe in ("pytest", "py.test"):
        return True
    if exe in ("python", "python3", "py"):
        return len(a) >= 3 and a[1] == "-m" and a[2] in ("pytest", "unittest")
    if exe in ("mvn", "mvnw"):
        return first in ("test", "verify", "compile", "package")
    if exe in ("gradle", "gradlew"):
        return first in ("test", "check", "build")
    if exe == "go":
        return first in ("test", "vet", "build")
    if exe == "cargo":
        return first in ("test", "check", "build", "clippy")
    if exe == "dotnet":
        return first in ("test", "build")
    if exe == "make":
        return first in ("test", "check", "lint")
    return False


def constraint_snips(text, n=2):
    out = []
    for m in NEG.finditer(text):
        tail = re.split(r"[.;\n!?]", text[m.start():])[0].split()[:7]
        out.append(" ".join(tail))
        if len(out) >= n:
            break
    return out


def lint(b):
    errs, notes = [], []
    if not b:
        return ["no brief: write the file printed by `hz path brief` (see /hezbit:brief)"], notes
    t = b["type"]
    if t not in TYPES:
        errs.append("type must be one of: " + "|".join(TYPES))
    req = request_text()
    if not req:
        errs.append("request missing: run  hz request \"<the user's exact words>\"")
    if t in NEEDS_SCOPE:
        if not b["scope_list"]:
            errs.append("scope is empty: list the files/dirs allowed to change")
        for s in b["scope_list"]:
            if any(c in s for c in "*?["):
                continue
            full = os.path.join(ROOT, s)
            if not (os.path.exists(full) or os.path.isdir(os.path.dirname(full.rstrip("/")))):
                errs.append("scope path not found: " + s)
        snips = constraint_snips(req)
        if snips and (not b.get("out") or b["out"].strip().lower() in ("none", "n/a", "-")):
            errs.append('request has constraints (e.g. "%s") but out is empty: copy them into out:' % snips[0])
    if not b["done"]:
        errs.append("done needs >=1 item. Best form:  command :: expected text")
    if not b.get("reply"):
        errs.append("reply is missing (example: 'diff-only, <=10 lines')")
    for d in b["done"]:
        if " :: " in d and not allowed_cmd(d.split(" :: ", 1)[0].strip()):
            notes.append("not auto-run (not allowlisted): " + d.split(" :: ", 1)[0][:60])
    if t in NEEDS_SCOPE and not any(" :: " in d for d in b["done"]):
        notes.append("no runnable done item ('cmd :: expected'): end-of-task auto-check is off")
    return errs, notes


def glob_re(pat):
    """Glob -> regex. `*` and `?` stop at '/', `**` crosses it, `[!x]` negates."""
    i, n, out = 0, len(pat), ""
    while i < n:
        c = pat[i]
        if c == "*":
            if pat[i:i + 2] == "**":
                i += 2
                if pat[i:i + 1] == "/":
                    i += 1
                    out += "(?:.*/)?"
                else:
                    out += ".*"
                continue
            out += "[^/]*"
        elif c == "?":
            out += "[^/]"
        elif c == "[" and pat.find("]", i + 2) != -1:
            j = pat.find("]", i + 2)
            body = pat[i + 1:j].replace("\\", "\\\\")
            out += "[" + ("^" + body[1:] if body.startswith("!") else body) + "]"
            i = j
        else:
            out += re.escape(c)
        i += 1
    return re.compile("^" + out + "$", re.I if os.name == "nt" else 0)


def is_state_path(r):
    return r.startswith(".claude/hezbit/")


def in_scope(path, scope):
    """Outside-project paths and hezbit's own state are not this check's business (scope_guard handles state)."""
    r = rel(path)
    if outside(r) or is_state_path(r):
        return True
    parts = r.split("/")
    prefixes = ["/".join(parts[:k]) for k in range(1, len(parts) + 1)]
    for s in scope:
        s = s.replace("\\", "/").strip()
        if s.startswith("./"):
            s = s[2:]
        base = s.rstrip("/")
        if not base:
            continue
        if base in prefixes:  # exact file, or a directory containing it
            return True
        if any(c in base for c in "*?["):
            rx = glob_re(base)
            if "/" not in base:  # bare pattern like *.py matches by file name at any depth
                if rx.match(parts[-1]):
                    return True
            elif any(rx.match(x) for x in prefixes):  # glob may name a file or a directory
                return True
    return False


# ---------- what a tool call is about to write ----------
_SEG = re.compile(r"\|\||&&|;|\||\n")
_REDIR = re.compile(r"(?<![<>&\w])(?:\d?>>?|&>>?)\s*(?!&)([^\s;&|<>()]+)")
_WRAP = ("sudo", "command", "env", "time", "nohup", "exec")


def bash_write_targets(cmd):
    """Best-effort: paths a shell command is likely to write or delete. Cannot see python -c, node -e, etc."""
    out = [m.group(1) for m in _REDIR.finditer(cmd or "")]
    for seg in _SEG.split(cmd or ""):
        try:
            a = shlex.split(seg)
        except ValueError:
            continue
        while a and re.match(r"^\w+=", a[0]):
            a = a[1:]
        while a and os.path.basename(a[0]) in _WRAP:
            a = a[1:]
        if not a:
            continue
        exe, args = os.path.basename(a[0]), a[1:]
        if exe == "git" and args:
            exe, args = "git-" + args[0], args[1:]
        pos, skip = [], False
        for x in args:
            if skip:
                skip = False
            elif x in ("-e", "-f", "--expression", "--file"):
                skip = True
            elif x.startswith("of="):
                out.append(x[3:])
            elif not x.startswith("-") or x == "--":
                if x != "--":
                    pos.append(x)
        flags = [x for x in args if x.startswith("-")]
        if exe in ("sed", "gsed", "perl"):
            if any(re.match(r"^-[A-Za-z]*i", f) or f.startswith("--in-place") for f in flags):
                has_script = any(x in ("-e", "--expression") for x in args)
                out += pos if has_script else pos[1:]
        elif exe in ("tee", "rm", "touch", "mkdir", "rmdir", "truncate", "mv", "git-rm", "git-mv", "unlink", "shred"):
            out += pos
        elif exe in ("cp", "install", "ln"):
            out += pos[-1:]
        elif exe in ("chmod", "chown", "chgrp"):
            out += pos[1:]
        elif exe == "git-checkout":  # `git checkout main` / `-b x` name refs; only paths after `--` are written
            out += args[args.index("--") + 1:] if "--" in args else []
        elif exe == "git-restore":
            if "--" in args:
                out += args[args.index("--") + 1:]
            else:  # `--source X` / `-s X` take a ref, not a path
                skip, paths = False, []
                for x in args:
                    if skip:
                        skip = False
                    elif x in ("--source", "-s"):
                        skip = True
                    elif not x.startswith("-"):
                        paths.append(x)
                out += paths
    return [t.strip("\"'") for t in out if t.strip("\"'") and not re.search(r"[$`]|^/dev/", t.strip("\"'"))]


# ---------- git-based change tracking (sees edits made by any means, incl. shell) ----------
def _file_sig(fp):
    try:
        st = os.stat(fp)
        if st.st_size > 2_000_000:  # do not read huge files, size+mtime is enough
            return f"{st.st_size}:{st.st_mtime_ns}"
        with open(fp, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except OSError:
        return "deleted"


def git_state():
    """{path: content signature} of every file git sees as changed or untracked; None if not a git repo."""
    try:
        r = subprocess.run(["git", "-C", ROOT, "status", "--porcelain", "-z", "--untracked-files=all"],
                           capture_output=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    try:  # porcelain paths are relative to the repo top, which may be above the project root
        top = subprocess.run(["git", "-C", ROOT, "rev-parse", "--show-toplevel"],
                             capture_output=True, timeout=15).stdout.decode("utf-8", "replace").strip() or ROOT
    except (OSError, subprocess.SubprocessError):
        top = ROOT
    entries, st, i = r.stdout.decode("utf-8", "replace").split("\0"), {}, 0
    while i < len(entries):
        e, i = entries[i], i + 1
        if len(e) < 4:
            continue
        if e[0] in "RC":  # rename/copy entries carry the original path as one more field
            i += 1
        fp = os.path.join(top, e[3:])
        path = rel(fp)
        if not outside(path) and not is_state_path(path):
            st[path] = _file_sig(fp)
    return st


def save_git_baseline():
    st = git_state()
    if st is not None:
        write(p("git_baseline.json"), json.dumps(st))


def git_changed():
    """{path: signature} changed since the session baseline. {} if no baseline or no git."""
    try:
        base = json.loads(read(p("git_baseline.json")) or "null")
    except ValueError:
        base = None
    cur = git_state()
    if base is None or cur is None:
        return {}
    return {f: cur.get(f, "deleted") for f in set(cur) | set(base) if cur.get(f, "deleted") != base.get(f, "deleted")}


def change_sig(changed):
    return hashlib.md5(json.dumps(sorted(changed.items())).encode()).hexdigest()


def tool_targets(data):
    """Paths a PreToolUse/PostToolUse payload will modify (Edit, Write, MultiEdit, NotebookEdit, Bash)."""
    name, ti = data.get("tool_name", ""), data.get("tool_input") or {}
    if name == "Bash":
        raw = bash_write_targets(ti.get("command", ""))
    else:
        v = ti.get("notebook_path") if name == "NotebookEdit" else ti.get("file_path")
        raw = [v] if v else []
    cwd = data.get("cwd")
    return [t if os.path.isabs(t) or not cwd else os.path.join(cwd, t) for t in raw]


def plan_items():
    out = []
    for l in read_lines(p("plan.md")):
        m = re.match(r"^\[( |x)\]\s*(.*)$", l)
        if m:
            out.append((m.group(1) == "x", m.group(2)))
    return out


def next_step():
    items = plan_items()
    for i, (done, text) in enumerate(items, 1):
        if not done:
            return i, len(items), text
    return None


def summary(with_next=False):
    b = parse_brief()
    if not b:
        return ""
    req = " ".join(request_text().split())
    s = f"[hz] {b['type']} | request: {req[:160] or '(none saved)'}"
    if len(req) > 160:
        s += "... (full: hz request)"
    s += f" | scope: {b.get('scope','')[:90]}"
    if b.get("out"):
        s += f" | out: {b['out'][:80]}"
    s += " | done: " + "; ".join(b["done"])[:130]
    s += f" | reply: {b.get('reply','')[:40]}"
    n = next_step() if with_next else None
    if n:
        s += f" | next: step {n[0]}/{n[1]} {n[2][:50]}"
    return s
