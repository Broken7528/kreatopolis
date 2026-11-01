"""Build the dedicated-server pack.

Mods/configs are fetched with packwiz-installer (side=server) from a pack.toml URL - in CI this is
a local `packwiz serve`, so PRs and main are both built from the exact checked-out tree.
The result is a drop-in server directory: install NeoForge, accept the EULA, run.

    python scripts/build_server.py --pack-url http://localhost:18080/pack.toml \
        --bootstrap packwiz-installer-bootstrap.jar
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import zipfile
from pathlib import Path

from common import DIST_DIR, PACK_NAME, ROOT, SERVER_DIR, load_pack
from gen_players import generate

OUT_NAME = f"{PACK_NAME}-server.zip"
# installer bookkeeping that must not ship in the server zip
JUNK = {"packwiz.json", "packwiz-installer.jar", "packwiz-installer-bootstrap.jar"}


def build(pack_url: str, bootstrap: Path, out_dir: Path, work: Path) -> Path:
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    subprocess.run(
        ["java", "-jar", str(bootstrap.resolve()), "-g", "-s", "server",
         "--pack-folder", str(work), pack_url],
        check=True,
    )
    for name in JUNK:
        (work / name).unlink(missing_ok=True)

    shutil.copy2(SERVER_DIR / "server.properties", work / "server.properties")
    shutil.copy2(SERVER_DIR / "user_jvm_args.txt", work / "user_jvm_args.txt")
    generate(work)

    overrides = SERVER_DIR / "overrides"
    for f in sorted(p for p in overrides.rglob("*") if p.is_file() and p.name != ".gitkeep"):
        dest = work / f.relative_to(overrides)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, dest)

    jars = sorted((work / "mods").glob("*.jar"))
    if not jars:
        raise SystemExit("server build produced no mods - installer failed silently?")
    pack = load_pack()
    (work / "PACK_INFO.txt").write_text(
        f"{PACK_NAME} {pack['version']}\nMinecraft {pack['versions']['minecraft']}\n"
        f"NeoForge {pack['versions']['neoforge']}\nmods: {len(jars)}\n",
        encoding="utf-8",
    )

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / OUT_NAME
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(p for p in work.rglob("*") if p.is_file()):
            z.write(f, f.relative_to(work).as_posix())
    print(f"server mods: {len(jars)}")
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-url", required=True)
    ap.add_argument("--bootstrap", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=DIST_DIR)
    ap.add_argument("--work-dir", type=Path, default=ROOT / "build" / "server")
    a = ap.parse_args()
    path = build(a.pack_url, a.bootstrap, a.out_dir, a.work_dir)
    print(f"built {path} ({path.stat().st_size} bytes)")
