# Contributing

Contributions are welcome, especially focused bug fixes, safety tests, documentation corrections, and compatibility improvements.

## Development setup

```powershell
git clone https://github.com/jianshengchuanchaun/virtuoso-wiki-bridge.git
Set-Location .\virtuoso-wiki-bridge
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev,books]"
```

Before opening a pull request:

```powershell
ruff check .
python -m pytest -q
python -m pytest --cov=virtuoso_wiki_bridge --cov-branch --cov-fail-under=70
python -m build
python -m twine check dist\*
```

The `dev` extra includes the `build` and `twine` release checks used above.

## Change guidelines

- Preserve private-by-default behavior for raw sources, `.env`, PDK material, netlists, logs, and simulator outputs.
- Add a regression test before or with every bug fix.
- Treat filesystem paths as hostile input at containment and overwrite boundaries.
- Never make `organize-sources --apply` regenerate its own plan.
- Keep no-clobber and full-digest checks in any organizer refactor.
- Do not follow symlinks, junctions, or reparse points inside controlled write trees.
- Preserve upstream and child-process return codes.
- Keep network operations bounded by timeouts.
- Do not make retrieved source text executable.
- Avoid tests that require proprietary Cadence software or a private host. Mock command construction in public CI and document any private smoke test separately.

For a behavior change, update the README, command help, and changelog together. If the change alters a path layout or CLI argument contract, include a migration note.

## Pull requests

Keep pull requests narrow and explain:

- the user-visible problem;
- the security or compatibility boundary, if any;
- the implementation;
- the tests run and their result;
- what was not tested, especially live Virtuoso/Spectre behavior.

Do not include credentials, copyrighted books, PDK files, private hostnames, customer designs, or real simulation artifacts.
