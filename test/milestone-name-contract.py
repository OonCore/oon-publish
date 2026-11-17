#!/usr/bin/env python3
"""I-14 da especificação do marco: o nome único é "marco 0.3.0" (com Core 0.8.0).

O nome antigo, com a versão do Core no lugar da do marco, não pode entrar em
nenhum arquivo versionado do oon-publish (README, workflows e testes). O
detector pega também a versão com "v", hífen ou sublinhado e a âncora sem
pontos; as grafias proibidas são montadas por partes para que este arquivo
não acuse a si mesmo.
"""
import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent.parent
OLD = re.compile(r"marco[\s _-]*v?0[.,_-]?8(?!\d)|marco[\s_-]*v?080\b", re.IGNORECASE)

m = "marco"
for bad in (f"{m} 0.8.0", f"{m.upper()} 0.8", f"{m} v0.8.0", f"{m}-0.8.0", f"{m}_0_8", f"#{m}-080", f"{m} 0.8"):
    assert OLD.search(bad), bad
for good in ("marco 0.3.0 (Core 0.8.0)", "#marco-030-core-080", "OonCore 0.8.0", "marco-0.3.0-ecossistemas.md"):
    assert not OLD.search(good), good

files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, check=True, capture_output=True, text=True).stdout.split("\0")
files = [name for name in files if name]
assert "README.md" in files and any(name.startswith(".github/workflows/") for name in files)
hits = []
for name in files:
    path = ROOT / name
    if not path.is_file():
        continue
    data = path.read_bytes()
    if b"\0" in data:
        continue
    for number, line in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
        if OLD.search(line):
            hits.append(f"{name}:{number}")
assert not hits, "nome antigo do marco: " + ", ".join(hits)
print(f"milestone name ok ({len(files)} arquivos versionados)")
