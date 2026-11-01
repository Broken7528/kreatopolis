"""Render the mod list (from pack/mods/*.pw.toml) as Markdown.

    python scripts/modlist.py            # print to stdout
    python scripts/modlist.py -o FILE    # write to FILE
"""
from __future__ import annotations

import argparse

from common import PACK_NAME, load_mods, load_pack


def render() -> str:
    pack = load_pack()
    versions = pack["versions"]
    mods = load_mods()
    counts = {s: sum(1 for m in mods if m["side"] == s) for s in ("both", "client", "server")}
    lines = [
        f"# {PACK_NAME} {pack['version']} mod list",
        "",
        f"Minecraft **{versions['minecraft']}** / NeoForge **{versions['neoforge']}** "
        f"- {len(mods)} mods ({counts['both']} both sides, {counts['client']} client-only, "
        f"{counts['server']} server-only)",
        "",
        "| Mod | Side | Source | File |",
        "| --- | --- | --- | --- |",
    ]
    for m in mods:
        lines.append(f"| {m['name']} | {m['side']} | {m['source']} | `{m['filename']}` |")
    lines.append("")
    return "\n".join(lines)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--output")
    args = ap.parse_args()
    text = render()
    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
    else:
        print(text)
