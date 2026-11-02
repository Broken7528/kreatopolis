"""Version management and change detection script for Kreatopolis modpack.

Determines modpack versioning across CI builds and releases.
Change detection rules:
  - If no modpack files (pack/**, client/**, server/**, build scripts) changed -> should_build = false
  - If new mods are added in pack/mods/ -> bump MINOR version (e.g. 1.0.0 -> 1.1.0), should_build = true
  - If mods/configs are modified or removed -> bump PATCH version (e.g. 1.1.0 -> 1.1.1), should_build = true
  - If pack/pack.toml was manually bumped to a higher version -> respect it, should_build = true
  - If manual workflow_dispatch -> should_build = true
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PACK_TOML = ROOT / "pack" / "pack.toml"

# Directories and files that directly affect the modpack builds
MODPACK_BUILD_PREFIXES = (
    "pack/",
    "client/",
    "server/",
)

MODPACK_BUILD_FILES = {
    "scripts/build_client.py",
    "scripts/build_server.py",
    "scripts/common.py",
    "scripts/gen_players.py",
    "scripts/KreatopolisBootstrap.java",
    "scripts/modlist.py",
    "scripts/requirements.txt",
}


def is_modpack_file(path: str) -> bool:
    """Return True if path affects modpack artifacts (client or server builds)."""
    norm = path.replace("\\", "/").strip()
    if any(norm.startswith(prefix) for prefix in MODPACK_BUILD_PREFIXES):
        return True
    if norm in MODPACK_BUILD_FILES:
        return True
    return False


def parse_semver(v: str) -> tuple[int, int, int]:
    """Parse '1.2.3' or 'v1.2.3-build.4' into (1, 2, 3)."""
    m = re.search(r"(\d+)\.(\d+)\.(\d+)", v.strip())
    if not m:
        return (1, 0, 0)
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def format_semver(t: tuple[int, int, int]) -> str:
    return f"{t[0]}.{t[1]}.{t[2]}"


def get_current_pack_version() -> str:
    if not PACK_TOML.exists():
        return "1.0.0"
    try:
        with open(PACK_TOML, "rb") as f:
            data = tomllib.load(f)
        return data.get("version", "1.0.0")
    except Exception:
        return "1.0.0"


def get_version_at_commit(commit_sha: str) -> str | None:
    try:
        out = subprocess.check_output(
            ["git", "show", f"{commit_sha}:pack/pack.toml"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(ROOT),
        )
        data = tomllib.loads(out)
        return data.get("version")
    except Exception:
        return None


def get_latest_release_info() -> tuple[str, str] | None:
    """Return (version_str, commit_sha_or_tag) for the latest release."""
    try:
        out = subprocess.check_output(
            ["gh", "release", "list", "--exclude-drafts", "--exclude-pre-releases", "--limit", "30"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(ROOT),
        )
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 3:
                tag = parts[2].strip()
                if tag != "latest" and re.search(r"\d+\.\d+\.\d+", tag):
                    ver = format_semver(parse_semver(tag))
                    return (ver, tag)
    except Exception:
        pass

    try:
        out = subprocess.check_output(
            ["git", "tag", "-l", "v*"],
            stderr=subprocess.DEVNULL,
            text=True,
            cwd=str(ROOT),
        )
        tags = [t.strip() for t in out.splitlines() if t.strip() != "latest" and re.search(r"\d+\.\d+\.\d+", t.strip())]
        if tags:
            sorted_tags = sorted(tags, key=parse_semver, reverse=True)
            latest_tag = sorted_tags[0]
            return (format_semver(parse_semver(latest_tag)), latest_tag)
    except Exception:
        pass

    return None


def commit_exists(sha: str) -> bool:
    if not sha or re.match(r"^0+$", sha):
        return False
    try:
        subprocess.check_call(
            ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(ROOT),
        )
        return True
    except Exception:
        return False


def determine_version_and_changes(
    before_sha: str | None = None,
    is_manual: bool = False,
) -> tuple[str, str, bool, bool]:
    """
    Returns: (resolved_version, reason, was_bumped, should_build)
    """
    current_pack_ver = get_current_pack_version()
    current_pack_tuple = parse_semver(current_pack_ver)

    base_version = "1.0.0"
    base_ref = None

    if before_sha and commit_exists(before_sha):
        base_ref = before_sha
        v_at_commit = get_version_at_commit(before_sha)
        if v_at_commit:
            base_version = v_at_commit
    else:
        rel_info = get_latest_release_info()
        if rel_info:
            base_version, base_ref = rel_info

    base_tuple = parse_semver(base_version)

    new_mods = []
    changed_mods = []
    config_changes = []
    all_modpack_changes = []

    if base_ref:
        try:
            diff_out = subprocess.check_output(
                ["git", "diff", "--name-status", f"{base_ref}..HEAD"],
                stderr=subprocess.DEVNULL,
                text=True,
                cwd=str(ROOT),
            )
            for line in diff_out.splitlines():
                parts = line.split("\t")
                if len(parts) >= 2:
                    status = parts[0].strip()
                    for p in parts[1:]:
                        p_clean = p.strip()
                        if is_modpack_file(p_clean):
                            all_modpack_changes.append((status, p_clean))
                            if p_clean.startswith("pack/mods/") and (p_clean.endswith(".pw.toml") or p_clean.endswith(".jar")):
                                if "A" in status:
                                    new_mods.append(p_clean)
                                elif "M" in status or "D" in status or "R" in status:
                                    changed_mods.append(p_clean)
                            elif p_clean.startswith(("pack/config/", "config/", "server/", "client/client.yml")):
                                config_changes.append(p_clean)
        except Exception:
            pass

    # Determine whether a build is required:
    # 1. Manual trigger (workflow_dispatch) always builds.
    # 2. If no base reference exists (e.g. initial repo push), build.
    # 3. Otherwise, only build if files affecting modpacks were modified.
    should_build = False
    if is_manual:
        should_build = True
    elif not base_ref:
        should_build = True
    elif all_modpack_changes:
        should_build = True

    # Version bump calculation:
    calculated_tuple = base_tuple
    bumped = False
    reason = "no modpack changes"

    if new_mods:
        calculated_tuple = (base_tuple[0], base_tuple[1] + 1, 0)
        bumped = True
        mod_names = [Path(p).name.replace(".pw.toml", "").replace(".jar", "") for p in new_mods[:3]]
        reason = f"new mods added ({len(new_mods)}): {', '.join(mod_names)}"
    elif changed_mods or config_changes:
        calculated_tuple = (base_tuple[0], base_tuple[1], base_tuple[2] + 1)
        bumped = True
        reason = f"mod/config changes ({len(changed_mods) + len(config_changes)} files)"
    elif is_manual:
        reason = "manual workflow dispatch"
    elif not should_build:
        reason = "no modpack or build files modified in this push"

    final_tuple = max(current_pack_tuple, calculated_tuple)
    if final_tuple > base_tuple:
        bumped = True
    elif final_tuple == current_pack_tuple and current_pack_tuple > base_tuple:
        reason = f"manually specified in pack.toml ({current_pack_ver})"
        bumped = True

    final_version = format_semver(final_tuple)
    return (final_version, reason, bumped, should_build)


def update_pack_toml(new_version: str) -> bool:
    if not PACK_TOML.exists():
        return False
    content = PACK_TOML.read_text(encoding="utf-8")
    new_content = re.sub(
        r'^version\s*=\s*"[^"]*"',
        f'version = "{new_version}"',
        content,
        flags=re.MULTILINE,
    )
    if new_content != content:
        PACK_TOML.write_text(new_content, encoding="utf-8")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Kreatopolis version manager and change detector")
    parser.add_argument("--before", help="Git commit SHA before the push (e.g. ${{ github.event.before }})")
    parser.add_argument("--manual", action="store_true", help="Indicates workflow_dispatch manual run")
    parser.add_argument("--set", dest="set_version", help="Directly set version in pack/pack.toml")
    parser.add_argument("--apply", action="store_true", help="Update pack/pack.toml in-place with resolved version")
    parser.add_argument("--github-output", action="store_true", help="Write step outputs to $GITHUB_OUTPUT")
    args = parser.parse_args()

    if args.set_version:
        v = format_semver(parse_semver(args.set_version))
        update_pack_toml(v)
        print(v)
        return

    version, reason, bumped, should_build = determine_version_and_changes(
        before_sha=args.before,
        is_manual=args.manual,
    )

    if args.apply and should_build:
        updated = update_pack_toml(version)
        if updated:
            try:
                subprocess.run(["packwiz", "refresh"], cwd=str(ROOT / "pack"), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    if args.github_output:
        gh_out = os.environ.get("GITHUB_OUTPUT")
        if gh_out:
            with open(gh_out, "a", encoding="utf-8") as f:
                f.write(f"version={version}\n")
                f.write(f"tag=v{version}\n")
                f.write(f"bumped={str(bumped).lower()}\n")
                f.write(f"should_build={str(should_build).lower()}\n")
                f.write(f"reason={reason}\n")

    print(f"version={version} should_build={str(should_build).lower()} reason={reason}")


if __name__ == "__main__":
    main()
