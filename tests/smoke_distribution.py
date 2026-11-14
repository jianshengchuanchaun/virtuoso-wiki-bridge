"""Exercise an installed wheel without relying on the source checkout."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def main(wheel: Path) -> None:
    wheel = wheel.resolve()
    with zipfile.ZipFile(wheel) as archive:
        names = archive.namelist()
        assert len([n for n in names if n.endswith("/SKILL.md")]) == 3
        assert "virtuoso_wiki_bridge/templates/START_HERE.md" in names
        assert not any("local-config/" in n or "installation/" in n or n.endswith(".pdf") for n in names)
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    env.pop("PYTHONPATH", None)
    checkout = Path(__file__).resolve().parents[1]
    # Keep the temporary tree for diagnosis; no user vault or Desktop is used.
    root = Path(tempfile.mkdtemp(prefix="vwb-wheel-")) / "安装 demo"
    root.mkdir()

    def run(*args):
        result = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True,
                                encoding="utf-8", timeout=120, check=False)
        if result.returncode:
            raise RuntimeError(f"Command failed ({result.returncode}): {args}\n{result.stdout}\n{result.stderr}")
        return result.stdout

    run(sys.executable, "-m", "venv", str(root / ".venv"))
    python = root / ".venv" / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    run(str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel))
    if sys.platform == "win32":
        for name in ("Install-VirtuosoWiki.ps1", "Start-VirtuosoWiki.ps1", "vwb.cmd"):
            shutil.copy2(checkout / name, root / name)
        run("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(root / "Install-VirtuosoWiki.ps1"), "-SkipInstall", "-Desktop", "No")
    else:
        run(str(python), "-m", "virtuoso_wiki_bridge.cli", "setup", "--desktop", "no")
    vault = root / "个人知识库"
    assert (vault / "sources/books").is_dir()
    assert (vault / ".obsidian/app.json").is_file()
    assert len(list((vault / ".agents/skills").glob("*/SKILL.md"))) == 3
    (vault / "concepts/my-note.md").write_text("My knowledge: Miller compensation", encoding="utf-8")
    (vault / "START_HERE.md").write_text("My customized guide", encoding="utf-8")
    hashes = {p: hashlib.sha256(p.read_bytes()).digest() for p in vault.rglob("*") if p.is_file()}
    config = (root / ".env").read_bytes()
    run(str(python), "-m", "virtuoso_wiki_bridge.cli", "setup", "--desktop", "no")
    assert all(hashlib.sha256(p.read_bytes()).digest() == digest for p, digest in hashes.items())
    assert (root / ".env").read_bytes() == config
    output = run(str(python), "-m", "virtuoso_wiki_bridge.cli", "search", "Miller compensation")
    assert "my-note.md" in output
    if sys.platform == "win32":
        run("powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(root / "Start-VirtuosoWiki.ps1"), "-Offline", "-CheckOnly")
        desktop = root / "test desktop"
        run(str(python), "-m", "virtuoso_wiki_bridge.cli", "setup", "--desktop", "yes",
            "--desktop-dir", str(desktop))
        launcher = (desktop / "Start-VirtuosoWiki.cmd").read_text(encoding="ascii")
        # Only remove NoExit so this console integration check terminates.
        test_cmd = root / "check-launcher.cmd"
        test_cmd.write_text(launcher.replace(" -NoExit", ""), encoding="ascii")
        run("cmd.exe", "/d", "/c", str(test_cmd))
    print(f"Wheel smoke passed: install, complete setup, preserved user files, search and launcher. Workspace: {root}")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
