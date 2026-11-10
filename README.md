# Kreatopolis — Minecraft 1.21.1 (NeoForge 21.1.265)

Version-controlled modpack and server configuration repository for **Kreatopolis**. Pushing changes to `main` triggers GitHub Actions to build separate **Client (PolyMC instance)** and **Server** modpack zips and publish them to a rolling `latest` release with permanent URLs alongside an immutable versioned release.

---

## Stable Download & Auto-Sync Links

Once this repository is pushed to GitHub (`https://github.com/Broken7528/kreatopolis`), the workflow maintains these permanent URLs on the `latest` release:

| Artifact | Permanent URL | Purpose |
| :--- | :--- | :--- |
| **Client Instance (PolyMC)** | `https://github.com/Broken7528/kreatopolis/releases/download/latest/Kreatopolis-client.zip` | Paste directly into **PolyMC ➔ Add Instance ➔ Import from zip (URL)**. Auto-syncs mods on every game launch. |
| **Dedicated Server Pack** | `https://github.com/Broken7528/kreatopolis/releases/download/latest/Kreatopolis-server.zip` | Drop-in server bundle containing all server mods, configs, `server.properties`, `whitelist.json`, `ops.json`, `user_jvm_args.txt`, and default gamerules datapack. |
| **Packwiz Manifest** | `https://raw.githubusercontent.com/Broken7528/kreatopolis/main/pack/pack.toml` | Live manifest queried by `packwiz-installer-bootstrap.jar` on client launch. |

### How Client Auto-Sync Works
1. A player imports `Kreatopolis-client.zip` into PolyMC **once** using the permanent release link above.
2. The instance contains `mmc-pack.json` (`net.minecraft` `1.21.1` + `net.neoforged.neoforge` `21.1.265`), `patches/net.neoforged.neoforge.json`, `instance.cfg`, and `.minecraft/packwiz-installer-bootstrap.jar`.
3. Every time the player clicks **Launch**, PolyMC's `PreLaunchCommand` runs `packwiz-installer-bootstrap.jar -g -s client` against the `main` branch's `pack/pack.toml`, automatically downloading new/updated client & shared mods and pruning removed ones—without requiring players to have `packwiz` installed or ever re-import the zip.

---

## Repository Layout

```text
kreatopolis/
├── .github/workflows/
│   └── build.yml               # CI/CD: verifies packwiz index, builds client & server zips, publishes releases
├── pack/                       # Packwiz source of truth
│   ├── pack.toml               # Minecraft (1.21.1) & NeoForge (21.1.262) version definition
│   ├── index.toml              # SHA-256 index of all mod metadata & config files
│   ├── mods/                   # *.pw.toml mod descriptors (+ bundled JARs excluded from 3rd-party CF API)
│   └── config/                 # Shared & mod configuration files synced to clients and server
├── server/                     # Dedicated server configuration
│   ├── server.properties       # Creative, Easy, Large Biomes, seed 9006026852704370239, view/sim 25, no mobs
│   ├── players.yml             # Declarative whitelist & OP levels (generates whitelist.json & ops.json)
│   ├── user_jvm_args.txt       # Tuned Java 21 Aikar's G1GC flags
│   └── overrides/              # Extra server-only files copied into the server build
│       └── world/datapacks/kreatopolis_settings/  # Enforces gamerule spawnRadius 0 & doMobSpawning false
├── client/                     # PolyMC instance settings
│   ├── client.yml              # Instance name, memory allocation, NeoForge UID, pre-populated servers
│   └── overrides/              # Extra client-only files copied into .minecraft/
├── scripts/
│   ├── common.py               # Shared pack metadata loader
│   ├── build_client.py         # Compiles dist/Kreatopolis-client.zip
│   ├── build_server.py         # Runs packwiz-installer (-s server) + bundles server configs into dist/Kreatopolis-server.zip
│   ├── gen_players.py          # Compiles server/players.yml -> whitelist.json & ops.json
│   └── modlist.py              # Renders MODLIST.md from pack/mods/
└── MODLIST.md                  # Generated table of all mods, sides, and sources
```

---

## Server Configuration Summary

Configured in [`server/server.properties`](server/server.properties) and [`server/overrides/world/datapacks/kreatopolis_settings`](server/overrides/world/datapacks/kreatopolis_settings):

* **Minecraft / Loader**: `1.21.1` / NeoForge `21.1.265`
* **Gamemode**: `creative` (`force-gamemode=true`)
* **Difficulty**: `easy`
* **World Type**: `minecraft:large_biomes`
* **World Seed**: `9006026852704370239`
* **Respawn Radius**: `0` (enforced via built-in datapack `gamerule spawnRadius 0` on world load + `spawn-protection=0`)
* **Mob Spawning**: Enabled (`spawn-monsters=true`, `spawn-animals=true`, `spawn-npcs=true`)
* **View & Simulation Distance**: View distance 25 chunks (`view-distance=25`), entity loading/simulation distance 20 chunks (`simulation-distance=20`)

### Whitelist & Operator Levels ([`server/players.yml`](server/players.yml))

| Player | UUID | Whitelisted | OP Level |
| :--- | :--- | :---: | :---: |
| `clarity200` | `8045742e-3d79-4143-b2eb-f9617ee363f3` | Yes | **4** |
| `iconoclasmic` | `7a97e331-4f09-44a3-9e43-a2fd480e5771` | Yes | **4** |
| `coronabeth` | `434950c6-be59-4f52-9688-ff82cafa86c3` | Yes | **2** |
| `TallHercules60` | `a8670e8c-0d8c-4945-af0a-23009af7e2e3` | Yes | **2** |
| `LilsyG` | `3b5ec7fc-4314-49c2-b9d1-00646a18ebc9` | Yes | **2** |
| `pcndas` | `a4f3b538-7bb4-4cde-a6c8-3d1e898a176b` | Yes | **2** |

---

## Managing Mods & Configurations

### Adding / Removing / Updating Mods
Run `packwiz` inside the [`pack/`](pack) directory:

```bash
cd pack

# Add a mod from Modrinth or CurseForge
packwiz modrinth add <slug>
packwiz curseforge add <slug>

# Remove a mod
packwiz remove <slug>

# Refresh index after editing configs or adding bundled jars
packwiz refresh
```

> **Server-only vs Client-only mods:** Set `side = "server"`, `side = "client"`, or `side = "both"` in `pack/mods/<mod>.pw.toml` followed by `packwiz refresh`.

### Updating the Mod Table
```bash
python scripts/modlist.py -o MODLIST.md
```

See [`MODLIST.md`](MODLIST.md) for the complete list of 45 mods (25 shared gameplay/content mods, 3 client rendering mods, and 17 server-side compute/network/memory optimization mods).
