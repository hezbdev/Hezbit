# Contributing to Hezbit

Contributions are welcome: bug reports, fixes, new guards, docs, benchmark results. By contributing you agree that your work is released under the [MIT License](LICENSE).

## Ground rules

- **Scripts do the work, the model fills a form.** A feature that needs more model tokens must justify itself with a benchmark.
- **Standard library only.** No third-party Python dependencies.
- **Fail open, never fail loud on the user.** A hook that crashes must not block Claude Code. Guards decide with `ask` or exit code 2 only when they are sure.
- **Be honest in verify.** Anything not actually checked is `INCOMPLETE`, never `PASS`.
- **Windows is a first-class platform.** Test paths with spaces, backslashes, other drives and non-ASCII text.

## Setup

```bash
git clone https://github.com/hezbdev/hezbit
cd hezbit
python -m unittest discover -s tests     # all tests must pass
claude --plugin-dir .                    # try your change live
```

## Making a change

1. Open an issue first for anything bigger than a small fix, so we can agree on the approach.
2. Write a failing test, then the fix. Every bug fixed so far has a regression test in `tests/test_core.py`.
3. Keep the change focused. One concern per pull request.
4. Update `README.md` if behaviour, commands or configuration change.
5. Run the full test suite on your platform and say which one in the pull request.

## Reporting a bug

Please include: OS, Python version, Claude Code version (`claude --version`), the brief (`hz path brief` shows where it is), and the exact hook output. For a wrong block or a wrong prompt, the command or path that triggered it is the most useful detail.

## Sharing benchmark results

Results from `bench/ab.py` on real repositories are very welcome, positive or negative. Include the task file (without private code), `--runs`, the model, and `summary.md`.

## Security

If you find a way to bypass a guard or to make `verify` run something outside the allowlist, please report it privately through GitHub's *Report a vulnerability* feature on the repository instead of opening a public issue.
