import json, os, subprocess, sys, tempfile, unittest

BENCH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bench", "ab.py")

FAKE = r'''
import json, os, sys
a = sys.argv[1:]
sys.stdin.read()
plugin = "--plugin-dir" in a
open("src/a.py", "w").write("fixed = True\n")
if not plugin:
    open("db.sql", "w").write("x")  # baseline arm wanders outside scope
print(json.dumps({"type": "result", "is_error": False, "num_turns": 3 if plugin else 6,
                  "total_cost_usd": 0.05 if plugin else 0.10, "session_id": "s",
                  "usage": {"input_tokens": 10, "output_tokens": 20, "cache_creation_input_tokens": 30, "cache_read_input_tokens": 40}}))
'''


def run(*args, cwd=None):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, encoding="utf-8")


class Bench(unittest.TestCase):
    def test_end_to_end_with_fake_claude(self):
        t = tempfile.mkdtemp()
        repo = os.path.join(t, "repo")
        os.makedirs(os.path.join(repo, "src"))
        with open(os.path.join(repo, "src", "a.py"), "w") as f:
            f.write("fixed = False\n")
        with open(os.path.join(repo, "check.py"), "w") as f:
            f.write("import sys\nsys.exit(0 if 'True' in open('src/a.py').read() else 1)\n")
        run("git", "init", "-q", repo)
        run("git", "-C", repo, "add", "-A")
        run("git", "-C", repo, "-c", "user.email=a@b", "-c", "user.name=t", "commit", "-qm", "i")
        fake = os.path.join(t, "fake_claude.py")
        with open(fake, "w") as f:
            f.write(FAKE)
        tasks = os.path.join(t, "tasks.json")
        with open(tasks, "w") as f:
            json.dump({"repo": repo, "tasks": [{
                "id": "t1", "kind": "small", "prompt": "fix it", "check": f'"{sys.executable}" check.py',
                "allowed": ["src/"],
                "brief": {"type": "FIX", "scope": "src/", "out": "none", "done": ["manual"], "reply": "x"}}]}, f)
        out = os.path.join(t, "out")
        r = run(sys.executable, BENCH, tasks, "--runs", "2", "--arms", "base,seeded", "--out", out,
                "--claude-cmd", json.dumps([sys.executable, fake]))
        self.assertEqual(r.returncode, 0, r.stderr + r.stdout)
        rows = [json.loads(l) for l in open(os.path.join(out, "results.jsonl"), encoding="utf-8")]
        self.assertEqual(len(rows), 4)
        base = [x for x in rows if x["arm"] == "base"]
        seeded = [x for x in rows if x["arm"] == "seeded"]
        self.assertTrue(all(x["success"] for x in rows))
        self.assertEqual([x["out_of_scope"] for x in base], [["db.sql"], ["db.sql"]])
        self.assertEqual([x["out_of_scope"] for x in seeded], [[], []])
        self.assertEqual(sum(x["cost"] for x in base), 0.20)
        self.assertEqual(base[0]["in"] + base[0]["out"] + base[0]["cache_w"], 60)
        summary = open(os.path.join(out, "summary.md"), encoding="utf-8").read()
        self.assertIn("| small | base | 2 | 100% |", summary)
        self.assertIn("| small | seeded | 2 | 100% |", summary)
        self.assertEqual(run("git", "-C", repo, "status", "--porcelain").stdout.strip(), "")  # source repo untouched
        self.assertNotIn("hz-ab-", run("git", "-C", repo, "worktree", "list").stdout)  # worktrees cleaned
        # rerun resumes: nothing left to do
        r2 = run(sys.executable, BENCH, tasks, "--runs", "2", "--arms", "base,seeded", "--out", out,
                 "--claude-cmd", json.dumps([sys.executable, fake]))
        self.assertIn("0 runs to do", r2.stdout)


if __name__ == "__main__":
    unittest.main()
