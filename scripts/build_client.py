"""Build the PolyMC / MultiMC instance zip for players.

The zip contains *no mods*. It ships packwiz-installer-bootstrap.jar and a pre-launch command
that syncs mods + configs from the hosted pack.toml every time the player presses Play, so the
download link never has to change.

    python scripts/build_client.py --pack-url URL --bootstrap packwiz-installer-bootstrap.jar
"""
from __future__ import annotations

import argparse
import io
import json
import struct
import subprocess
import tempfile
import urllib.request
import zipfile
from pathlib import Path

import yaml

from common import CLIENT_DIR, DIST_DIR, PACK_NAME, ROOT, load_pack

OUT_NAME = f"{PACK_NAME}-client.zip"
WRAPPER_SRC = ROOT / "scripts" / "KreatopolisBootstrap.java"


def build_wrapped_bootstrap(bootstrap_jar: Path) -> bytes:
    """Compile KreatopolisBootstrap.java and inject it as Main-Class of packwiz-installer-bootstrap.jar."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        subprocess.run(
            [
                "javac",
                "--release", "8",
                "-cp", str(bootstrap_jar),
                "-d", str(tmp_path),
                str(WRAPPER_SRC),
            ],
            check=True,
        )
        buf = io.BytesIO()
        with zipfile.ZipFile(bootstrap_jar, "r") as src_zip, \
             zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as dst_zip:
            for item in src_zip.infolist():
                data = src_zip.read(item.filename)
                if item.filename == "META-INF/MANIFEST.MF":
                    manifest = data.decode("utf-8").replace(
                        "Main-Class: link.infra.packwiz.installer.bootstrap.Main",
                        "Main-Class: link.infra.packwiz.installer.bootstrap.KreatopolisBootstrap",
                    )
                    dst_zip.writestr(item, manifest.encode("utf-8"))
                else:
                    dst_zip.writestr(item, data)
            for cls_file in sorted(tmp_path.rglob("*.class")):
                rel = cls_file.relative_to(tmp_path).as_posix()
                dst_zip.write(cls_file, rel)
        return buf.getvalue()


# --- minimal NBT writer for servers.dat (uncompressed, big-endian) -------------------------
def _str(s: str) -> bytes:
    b = s.encode("utf-8")
    return struct.pack(">H", len(b)) + b


def servers_dat(servers: list[dict]) -> bytes:
    out = bytearray()
    out += b"\x0a" + _str("")                       # root TAG_Compound ""
    out += b"\x09" + _str("servers") + b"\x0a" + struct.pack(">i", len(servers))
    for s in servers:
        out += b"\x08" + _str("ip") + _str(s["ip"])
        out += b"\x08" + _str("name") + _str(s["name"])
        out += b"\x00"                               # end of server compound
    out += b"\x00"                                   # end of root
    return bytes(out)


def fetch_neoforge_patch(uid: str, version: str) -> str | None:
    url = f"https://meta.polymc.org/v1/{uid}/{version}.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kreatopolis-build/1.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.read().decode("utf-8")
    except Exception:
        return None


def build(pack_url: str, bootstrap: Path, out_dir: Path) -> Path:
    pack = load_pack()
    cfg = yaml.safe_load((CLIENT_DIR / "client.yml").read_text(encoding="utf-8"))
    mc = pack["versions"]["minecraft"]
    neo = pack["versions"]["neoforge"]
    neo_uid = cfg["neoforge_uid"]

    mmc_pack = {
        "formatVersion": 1,
        "components": [
            {
                "cachedName": "LWJGL 3",
                "cachedVersion": "3.3.3",
                "cachedVolatile": True,
                "dependencyOnly": True,
                "uid": "org.lwjgl3",
                "version": "3.3.3",
            },
            {
                "cachedName": "Minecraft",
                "cachedRequires": [{"suggests": "3.3.3", "uid": "org.lwjgl3"}],
                "cachedVersion": mc,
                "important": True,
                "uid": "net.minecraft",
                "version": mc,
            },
            {
                "cachedName": "NeoForge",
                "cachedRequires": [{"equals": mc, "uid": "net.minecraft"}],
                "cachedVersion": neo,
                "uid": neo_uid,
                "version": neo,
            },
        ],
    }

    # PolyMC runs the pre-launch command in the instance's .minecraft folder.
    # Point --multimc-folder at $INST_MC_DIR so packwiz-installer does not rewrite ../mmc-pack.json
    # with Prism Launcher's "net.neoforged" UID or reorder PolyMC's components.
    sync = (f'"$INST_JAVA" -jar "$INST_MC_DIR/packwiz-installer-bootstrap.jar" -g -s client '
            f'--pack-folder "$INST_MC_DIR" --multimc-folder "$INST_MC_DIR" {pack_url}')
    mem = cfg["memory"]
    instance = {
        "InstanceType": "OneSix",
        "name": cfg["instance"]["name"],
        "iconKey": cfg["instance"].get("icon", "default"),
        "OverrideCommands": "true",
        "PreLaunchCommand": sync,
        "OverrideMemory": "true",
        "MinMemAlloc": mem["min"],
        "MaxMemAlloc": mem["max"],
    }
    if cfg.get("java_args"):
        instance["OverrideJavaArgs"] = "true"
        instance["JvmArgs"] = cfg["java_args"]
    instance.update(cfg.get("extra_instance_cfg") or {})
    instance_cfg = "[General]\n" + "".join(f"{k}={v}\n" for k, v in instance.items())

    patch_json = fetch_neoforge_patch(neo_uid, neo)
    wrapped_bootstrap = build_wrapped_bootstrap(bootstrap)

    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / OUT_NAME
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("instance.cfg", instance_cfg)
        z.writestr("mmc-pack.json", json.dumps(mmc_pack, indent=2) + "\n")
        if patch_json:
            z.writestr(f"patches/{neo_uid}.json", patch_json)
        z.writestr(".minecraft/packwiz-installer-bootstrap.jar", wrapped_bootstrap)
        if cfg.get("servers"):
            z.writestr(".minecraft/servers.dat", servers_dat(cfg["servers"]))
        overrides = CLIENT_DIR / "overrides"
        for f in sorted(p for p in overrides.rglob("*") if p.is_file() and p.name != ".gitkeep"):
            z.write(f, ".minecraft/" + f.relative_to(overrides).as_posix())
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--pack-url", required=True, help="public URL of pack/pack.toml (raw, stable)")
    ap.add_argument("--bootstrap", required=True, type=Path)
    ap.add_argument("--out-dir", type=Path, default=DIST_DIR)
    a = ap.parse_args()
    path = build(a.pack_url, a.bootstrap, a.out_dir)
    print(f"built {path} ({path.stat().st_size} bytes)")
