"""Shared helpers for the Kreatopolis build scripts."""
from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK_DIR = ROOT / "pack"
SERVER_DIR = ROOT / "server"
CLIENT_DIR = ROOT / "client"
DIST_DIR = ROOT / "dist"

PACK_NAME = "Kreatopolis"


def load_pack() -> dict:
    with open(PACK_DIR / "pack.toml", "rb") as fh:
        return tomllib.load(fh)


def load_mods() -> list[dict]:
    """Return every mod in pack/mods (*.pw.toml metadata + bundled *.jar), sorted by name."""
    mods = []
    tracked_jars = set()
    mods_dir = PACK_DIR / "mods"
    for path in sorted(mods_dir.glob("*.pw.toml")):
        with open(path, "rb") as fh:
            data = tomllib.load(fh)
        update = data.get("update", {})
        if "modrinth" in update:
            source = "Modrinth"
        elif "curseforge" in update:
            source = "CurseForge"
        else:
            source = "URL"
        tracked_jars.add(data["filename"])
        mods.append(
            {
                "id": path.name[: -len(".pw.toml")],
                "name": data["name"],
                "filename": data["filename"],
                "side": data.get("side", "both"),
                "source": source,
            }
        )
    for jar in sorted(mods_dir.glob("*.jar")):
        if jar.name not in tracked_jars:
            mods.append(
                {
                    "id": jar.stem,
                    "name": jar.stem,
                    "filename": jar.name,
                    "side": "both",
                    "source": "Bundled",
                }
            )
    return sorted(mods, key=lambda m: m["name"].lower())
