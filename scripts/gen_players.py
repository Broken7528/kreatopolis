"""Generate whitelist.json and ops.json from server/players.yml.

    python scripts/gen_players.py OUTPUT_DIR
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

from common import SERVER_DIR

UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")


def generate(out_dir: Path) -> tuple[int, int]:
    with open(SERVER_DIR / "players.yml", encoding="utf-8") as fh:
        players = yaml.safe_load(fh)["players"]

    whitelist, ops, seen = [], [], set()
    for p in players:
        uuid = str(p["uuid"]).lower()
        if not UUID_RE.match(uuid):
            raise SystemExit(f"players.yml: invalid UUID for {p.get('name')!r}: {uuid}")
        if uuid in seen:
            raise SystemExit(f"players.yml: duplicate UUID {uuid}")
        seen.add(uuid)

        if p.get("whitelist", True):
            whitelist.append({"uuid": uuid, "name": p["name"]})
        level = p.get("op_level")
        if level:
            if level not in (1, 2, 3, 4):
                raise SystemExit(f"players.yml: op_level for {p['name']} must be 1-4")
            ops.append({"uuid": uuid, "name": p["name"], "level": level, "bypassesPlayerLimit": False})

    out_dir.mkdir(parents=True, exist_ok=True)
    for fname, data in (("whitelist.json", whitelist), ("ops.json", ops)):
        with open(out_dir / fname, "w", encoding="utf-8", newline="\n") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
    return len(whitelist), len(ops)


if __name__ == "__main__":
    wl, op = generate(Path(sys.argv[1] if len(sys.argv) > 1 else "."))
    print(f"whitelist: {wl} players, ops: {op} players")
