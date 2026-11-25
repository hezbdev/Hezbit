import json, os, subprocess, sys, tempfile, unittest

SCRIPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts")


def run_py(code, root, **extra):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, PYTHONPATH=SCRIPTS, PYTHONUTF8="1", **extra)
    return subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, encoding="utf-8")


def read_guard(path, root):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root)
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, "read_guard.py")],
                          input=json.dumps({"tool_input": {"file_path": path}}),
                          env=env, capture_output=True, text=True).returncode


class ReadGuard(unittest.TestCase):
    def test_parent_build_dir_not_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            root = os.path.join(t, "build", "myapp")
            os.makedirs(os.path.join(root, "src"))
            f = os.path.join(root, "src", "a.py")
            open(f, "w").write("x=1\n")
            self.assertEqual(read_guard(f, root), 0)

    def test_inner_build_dir_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, "dist"))
            f = os.path.join(t, "dist", "a.js")
            open(f, "w").write("x")
            self.assertEqual(read_guard(f, t), 2)

    def test_lock_file_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            self.assertEqual(read_guard(os.path.join(t, "package-lock.json"), t), 2)


class Verify(unittest.TestCase):
    def status(self, done, **extra):
        with tempfile.TemporaryDirectory() as t:
            os.makedirs(os.path.join(t, ".claude", "hezbit", "sessions", "default"))
            with open(os.path.join(t, ".claude", "hezbit", "sessions", "default", "brief.md"), "w") as f:
                f.write("type: FIX\nscope: a\nout: none\ndone:\n" + "".join(f"- {d}\n" for d in done) + "reply: x\n")
            r = run_py("import verify,json;print(verify.run_verify()[0])", t, **extra)
            return r.stdout.strip(), r.stderr

    def test_all_runnable_pass_is_pass(self):
        self.assertEqual(self.status(["python -m unittest -h :: usage"])[0], "PASS")

    def test_budget_exhausted_is_incomplete(self):
        self.assertEqual(self.status(["python -m unittest -h :: usage"], HEZBIT_VERIFY_BUDGET="0")[0], "INCOMPLETE")

    def py(self, code):
        return f'python -m unittest {code}'

    def test_only_manual_is_incomplete(self):
        self.assertEqual(self.status(["manual: look"])[0], "INCOMPLETE")

    def test_skip_is_incomplete(self):
        self.assertEqual(self.status(["rm -rf x :: ok"])[0], "INCOMPLETE")

    def test_unrunnable_failure_is_fail(self):
        self.assertEqual(self.status(["python -m unittest nosuchmodule :: exit 0"])[0], "FAIL")


class Allowlist(unittest.TestCase):
    def ok(self, cmd, **extra):
        r = run_py(f"import glib;print(glib.allowed_cmd({cmd!r}))", tempfile.gettempdir(), **extra)
        return r.stdout.strip() == "True"

    def test_npm(self):
        self.assertTrue(self.ok("npm test -- auth"))
        self.assertTrue(self.ok("npm run lint"))
        self.assertTrue(self.ok("npm run test:unit"))
        self.assertFalse(self.ok("npm run deploy"))
        self.assertFalse(self.ok("npm install"))

    def test_others(self):
        self.assertTrue(self.ok("python -m pytest -q"))
        self.assertFalse(self.ok("python -c print(1)"))
        self.assertFalse(self.ok("rm -rf x"))

    def test_extra_is_whole_word(self):
        self.assertTrue(self.ok("mytool check", HEZBIT_ALLOW="mytool"))
        self.assertFalse(self.ok("mytool-evil", HEZBIT_ALLOW="mytool"))


class Regressions(unittest.TestCase):
    def test_scope_add_backslash_path_and_missing_line(self):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, ".claude", "hezbit", "sessions", "t1")
            os.makedirs(d)
            brief = os.path.join(d, "brief.md")
            env = dict(os.environ, CLAUDE_PROJECT_DIR=t, PYTHONUTF8="1")

            def add(path):
                return subprocess.run([sys.executable, os.path.join(SCRIPTS, "hz.py"), "-s", "t1", "scope-add", path],
                                      env=env, capture_output=True, text=True, encoding="utf-8")

            with open(brief, "w", encoding="utf-8") as f:
                f.write("type: FIX\nscope: src/\nout: none\ndone:\n- x\nreply: y\n")
            r = add("src\\auth")
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn("scope: src/, src\\auth", open(brief, encoding="utf-8").read())
            with open(brief, "w", encoding="utf-8") as f:
                f.write("type: FIX\nout: none\ndone:\n- x\nreply: y\n")
            add("lib/")
            self.assertIn("scope: lib/", open(brief, encoding="utf-8").read())

    def test_big_pdf_and_image_not_blocked(self):
        with tempfile.TemporaryDirectory() as t:
            for n in ("a.pdf", "b.PNG"):
                with open(os.path.join(t, n), "wb") as f:
                    f.write(b"0" * 200_000)
                self.assertEqual(read_guard(os.path.join(t, n), t), 0)
            with open(os.path.join(t, "big.txt"), "wb") as f:
                f.write(b"0" * 200_000)
            self.assertEqual(read_guard(os.path.join(t, "big.txt"), t), 2)

    def test_git_checkout_refs_are_not_paths(self):
        def targets(cmd):
            r = run_py(f"import glib,json;print(json.dumps(glib.bash_write_targets({cmd!r})))", tempfile.gettempdir())
            return json.loads(r.stdout)
        self.assertEqual(targets("git checkout main"), [])
        self.assertEqual(targets("git checkout -b feature/x"), [])
        self.assertEqual(targets("git checkout -- src/a.py"), ["src/a.py"])
        self.assertEqual(targets("git checkout main -- src/a.py"), ["src/a.py"])
        self.assertEqual(targets("git restore src/a.py"), ["src/a.py"])


def git(root, *args):
    subprocess.run(["git", "-C", root, *args], capture_output=True, check=True)


class GitTracking(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        git(self.t, "init", "-q")
        os.makedirs(os.path.join(self.t, "src"))
        for n in ("src/a.py", "src/dirty.py"):
            with open(os.path.join(self.t, n), "w") as f:
                f.write("x = 1\n")
        git(self.t, "add", "-A")
        git(self.t, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "init")
        with open(os.path.join(self.t, "src", "dirty.py"), "w") as f:  # already dirty before the session
            f.write("x = 2\n")
        self.sd = os.path.join(self.t, ".claude", "hezbit", "sessions", "g1")
        os.makedirs(self.sd)
        with open(os.path.join(self.sd, "brief.md"), "w", encoding="utf-8") as f:
            f.write("type: FIX\nscope: src/\nout: none\ndone:\n- python -m unittest -h :: usage\nreply: x\n")

    def changed(self):
        r = run_py("import glib,json;glib.init_session('g1');print(json.dumps(sorted(glib.git_changed())))", self.t)
        return json.loads(r.stdout)

    def baseline(self):
        run_py("import glib;glib.init_session('g1');glib.save_git_baseline()", self.t)

    def test_shell_edit_seen_and_preexisting_dirt_ignored(self):
        self.baseline()
        self.assertEqual(self.changed(), [])
        with open(os.path.join(self.t, "src", "a.py"), "w") as f:  # edit outside any edit tool
            f.write("x = 99\n")
        with open(os.path.join(self.t, "new.txt"), "w") as f:
            f.write("n")
        self.assertEqual(self.changed(), ["new.txt", "src/a.py"])
        with open(os.path.join(self.t, "src", "dirty.py"), "w") as f:  # further edit of an already-dirty file
            f.write("x = 3\n")
        self.assertIn("src/dirty.py", self.changed())

    def test_stop_hook_verifies_after_shell_only_edit(self):
        self.baseline()
        with open(os.path.join(self.t, "src", "a.py"), "w") as f:
            f.write("x = 99\n")
        out = hook("stop_check.py", {"session_id": "g1"}, self.t)
        self.assertEqual(out, "")  # verify ran and passed, so no block
        self.assertTrue(os.path.isfile(os.path.join(self.sd, "verify.json")))

    def test_check_reports_shell_edit_out_of_scope(self):
        self.baseline()
        with open(os.path.join(self.t, "db.sql"), "w") as f:
            f.write("x")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=self.t, PYTHONUTF8="1")
        out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "hz.py"), "-s", "g1", "check"],
                             env=env, capture_output=True, text=True, encoding="utf-8").stdout
        self.assertIn("out-of-scope: db.sql", out)


class Find(unittest.TestCase):
    def test_find_respects_gitignore_and_ranks_definitions(self):
        t = tempfile.mkdtemp()
        git(t, "init", "-q")
        os.makedirs(os.path.join(t, "src"))
        os.makedirs(os.path.join(t, "gen"))
        with open(os.path.join(t, ".gitignore"), "w") as f:
            f.write("gen/\n")
        with open(os.path.join(t, "src", "m.py"), "w") as f:
            f.write("    x = login(1)\ndef login(u):\n    pass\n")
        with open(os.path.join(t, "gen", "m.py"), "w") as f:
            f.write("def login(u): pass\n")
        env = dict(os.environ, CLAUDE_PROJECT_DIR=t, PYTHONUTF8="1")
        out = subprocess.run([sys.executable, os.path.join(SCRIPTS, "hz.py"), "find", "login"],
                             env=env, capture_output=True, text=True, encoding="utf-8").stdout.splitlines()
        self.assertEqual(out[0], "src/m.py:2: def login(u):")
        self.assertFalse(any(l.startswith("gen/") for l in out))

    def test_git_restore_source_ref_not_a_path(self):
        r = run_py("import glib,json;print(json.dumps(glib.bash_write_targets('git restore --source HEAD~1 src/a.py')))",
                   tempfile.gettempdir())
        self.assertEqual(json.loads(r.stdout), ["src/a.py"])


class Prune(unittest.TestCase):
    def test_old_dir_with_fresh_ping_survives(self):
        import time
        t = tempfile.mkdtemp()
        base = os.path.join(t, ".claude", "hezbit", "sessions")
        old = time.time() - 30 * 86400
        for name, ping in (("idle", False), ("active", True), ("current", False)):
            d = os.path.join(base, name)
            os.makedirs(d)
            if ping:
                open(os.path.join(d, ".ping"), "w").close()
            os.utime(d, (old, old))
        run_py("import glib;glib.init_session('current');glib.prune_sessions()", t)
        self.assertEqual(sorted(os.listdir(base)), ["active", "current"])


class Lint(unittest.TestCase):
    def lint(self, request, brief):
        with tempfile.TemporaryDirectory() as t:
            d = os.path.join(t, ".claude", "hezbit", "sessions", "default")
            os.makedirs(os.path.join(t, "src"))
            os.makedirs(d)
            with open(os.path.join(d, "request.md"), "w", encoding="utf-8") as f:
                f.write(request)
            with open(os.path.join(d, "brief.md"), "w", encoding="utf-8") as f:
                f.write(brief)
            return run_py("import glib;print(glib.lint(glib.parse_brief())[0])", t).stdout

    def test_ok_brief(self):
        out = self.lint("fix login", "type: FIX\nscope: src/\nout: none\ndone:\n- pytest :: exit 0\nreply: diff\n")
        self.assertEqual(out.strip(), "[]")

    def test_constraint_needs_out(self):
        out = self.lint("fix login, don't touch the db", "type: FIX\nscope: src/\nout: none\ndone:\n- pytest :: exit 0\nreply: diff\n")
        self.assertIn("constraints", out)

    def test_missing_fields(self):
        out = self.lint("x", "type: FIX\nscope:\nout: none\ndone:\n")
        self.assertIn("scope is empty", out)
        self.assertIn("done needs", out)
        self.assertIn("reply is missing", out)


class Cli(unittest.TestCase):
    def hz(self, root, *args):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=root, PYTHONUTF8="1")
        return subprocess.run([sys.executable, os.path.join(SCRIPTS, "hz.py"), "-s", "t1", *args],
                              env=env, capture_output=True, text=True, encoding="utf-8").stdout

    def test_plan_cap_and_step_note(self):
        with tempfile.TemporaryDirectory() as t:
            out = self.hz(t, "plan", *[f"s{i}" for i in range(8)])
            self.assertIn("5 steps", out)
            self.assertIn("3 dropped", out)
            self.hz(t, "step", "changed a.py")
            plan = open(os.path.join(t, ".claude", "hezbit", "sessions", "t1", "plan.md"), encoding="utf-8").read()
            self.assertIn("[x] s0 -> changed a.py", plan)


class Scope(unittest.TestCase):
    def test_outside_and_other_drive(self):
        r = run_py("import glib;print(glib.in_scope('/etc/x',['src/']), glib.outside('D:/x'), glib.outside('src/a'))", tempfile.gettempdir())
        self.assertEqual(r.stdout.strip(), "True True False")


class Glob(unittest.TestCase):
    def check(self, path, scope):
        r = run_py(f"import glib;print(glib.in_scope({path!r},{scope!r}))", tempfile.gettempdir())
        return r.stdout.strip() == "True"

    def p(self, rel):
        return os.path.join(tempfile.gettempdir(), rel)

    def test_star_does_not_cross_slash(self):
        self.assertTrue(self.check(self.p("src/a.py"), ["src/*.py"]))
        self.assertFalse(self.check(self.p("src/a/b.py"), ["src/*.py"]))

    def test_double_star_crosses(self):
        self.assertTrue(self.check(self.p("src/a/b.py"), ["src/**/*.py"]))
        self.assertTrue(self.check(self.p("src/b.py"), ["src/**/*.py"]))

    def test_dir_and_bare_pattern(self):
        self.assertTrue(self.check(self.p("src/deep/x.txt"), ["src/"]))
        self.assertTrue(self.check(self.p("a/b/c.py"), ["*.py"]))
        self.assertFalse(self.check(self.p("a/b/c.js"), ["*.py"]))


class BashTargets(unittest.TestCase):
    def targets(self, cmd):
        r = run_py(f"import glib,json;print(json.dumps(glib.bash_write_targets({cmd!r})))", tempfile.gettempdir())
        return json.loads(r.stdout)

    def test_redirect_and_sed(self):
        self.assertEqual(self.targets("echo hi > out.txt"), ["out.txt"])
        self.assertEqual(self.targets("sed -i 's/a/b/' src/x.py"), ["src/x.py"])
        self.assertEqual(self.targets("sed -i -e 's/a/b/' src/x.py"), ["src/x.py"])

    def test_pipeline_and_readonly(self):
        self.assertEqual(self.targets("cat a.txt | grep x"), [])
        self.assertEqual(self.targets("ls 2>&1 | tee log.txt"), ["log.txt"])
        self.assertEqual(self.targets("rm -rf build && cp a.txt b.txt"), ["build", "b.txt"])


def hook(script, payload, root):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=root, PYTHONUTF8="1")
    r = subprocess.run([sys.executable, os.path.join(SCRIPTS, script)], input=json.dumps(payload),
                       env=env, capture_output=True, text=True, encoding="utf-8")
    return r.stdout.strip()


class Session(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.mkdtemp()
        for sid, scope in (("s1", "src/"), ("s2", "docs/")):
            d = os.path.join(self.t, ".claude", "hezbit", "sessions", sid)
            os.makedirs(d)
            with open(os.path.join(d, "brief.md"), "w", encoding="utf-8") as f:
                f.write(f"type: FIX\nscope: {scope}\nout: none\ndone:\n- manual\nreply: x\n")

    def edit(self, sid, path, tool="Write", **ti):
        ti.setdefault("file_path", os.path.join(self.t, path))
        return hook("scope_guard.py", {"session_id": sid, "tool_name": tool, "tool_input": ti}, self.t)

    def test_sessions_have_own_scope(self):
        self.assertEqual(self.edit("s1", "src/a.py"), "")
        self.assertIn("outside the brief scope", self.edit("s2", "src/a.py"))

    def test_bash_and_notebook_checked(self):
        self.assertIn("outside", self.edit("s1", "x", tool="Bash", command="sed -i 's/a/b/' docs/x.md"))
        self.assertEqual(self.edit("s1", "x", tool="Bash", command="sed -i 's/a/b/' src/x.py"), "")
        self.assertIn("outside", self.edit("s1", "x", tool="NotebookEdit", notebook_path=os.path.join(self.t, "n.ipynb")))

    def test_brief_rewrite_asks_but_other_state_is_isolated(self):
        brief = os.path.join(self.t, ".claude", "hezbit", "sessions", "s1", "brief.md")
        self.assertIn("task contract", self.edit("s1", "x", file_path=brief))
        track = {"session_id": "s1", "tool_name": "Write", "tool_input": {"file_path": os.path.join(self.t, "src", "a.py")}}
        hook("track_edit.py", track, self.t)
        base = os.path.join(self.t, ".claude", "hezbit", "sessions")
        self.assertTrue(os.path.isfile(os.path.join(base, "s1", "touched.txt")))
        self.assertFalse(os.path.isfile(os.path.join(base, "s2", "touched.txt")))


if __name__ == "__main__":
    unittest.main()
