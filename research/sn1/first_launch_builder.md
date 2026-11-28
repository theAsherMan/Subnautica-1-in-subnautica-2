# SN1 open questions and the first-launch builder

Sources: 10_sn1_world_data.md "8. Open questions for SN2 (UNTESTED)", 10_sn1_world_data.md "10. First-launch builder (design, 2026-11-19, UNTESTED unles" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## 8. Open questions for SN2 (UNTESTED)
- **Ocean depth.** `BP_Ocean_C.BodySize` Z = 1 km (`research/sn2/world_systems.md`), but SN1 goes down to about −1.9 km. Check whether swim physics, pressure and fog work below 1 km, or whether `BodySize` can be raised.
  Note: L_SN2World currently has no water physics outside the pod (FAIL, `research/status.md` / `research/sn2/README.md`).
- **Map footprint.** SN1 is 4.1 × 4.1 km. It fits inside the 10 × 10 km ocean body; the edge-of-world ring (`BP_EdgeOfWorldVolume_C`) needs to move to the SN1 void edge.
- **Streaming.** A plain (non-WP) level with thousands of Nanite meshes plus collision keeps everything loaded. Decide between World Partition in a modkit level and level streaming, for the "no hidden map in RAM" rule.
- **Triangle and disk budget** after decimation, and cook time and RAM for thousands of assets.
- **Lifepod.** Align the SN1 lifepod start (Safe Shallows, near Unity origin) with SN2's lifepod (`research/sn2/README.md`).

## 10. First-launch builder (design, 2026-11-19, UNTESTED unless marked)
User proposal (2026-11-19): ship a program, not a map. On first launch the mod finds the user's SN1 install and builds the SN1 world locally before
the player reaches the menu. No modkit or editor on the user's machine. Everything that does not contain SN1 content is built by us in advance and shipped.

**Constraint that shapes the design:** SN2 only loads cooked assets (IoStore paks) or meshes built at runtime. Cooking and Nanite building need the
editor, so the user's machine cannot produce cooked or Nanite assets. The builder therefore writes **our own cache format**, and a native runtime
loader turns it into meshes while the game runs.

**Runtime mesh APIs present in the SN2 shipping exe** (grep of `<GameDir>\Subnautica2\Binaries\Win64\Subnautica2-Win64-Shipping.exe`, 2026-11-19; the
string is present, callability UNTESTED): `BuildFromStaticMeshDescriptions` (1 line hit), `CreateStaticMeshDescription` (1), `StaticMeshDescription` (3),
`DynamicMeshComponent` (4), `NaniteBuilder` (0, as expected: no Nanite building at runtime). So `UStaticMesh::BuildFromStaticMeshDescriptions` is very
likely compiled in. Runtime-built static meshes are non-Nanite and need our own LODs. Underwater fog keeps draw distance short, which helps.

### What runs where
| Part | Who builds it | Ships? |
|---|---|---|
| Our level (ocean, sky, post-process, biome volumes from our rules, not SN1 data), materials, progress widget, streaming manager Blueprint | Us, modkit cook, IoStore pak | Yes |
| UE4SS C++ mod `SN1WorldLoader.dll`: reads the cache, builds meshes on worker threads, spawns/destroys chunks around the player | Us | Yes |
| Builder `sn1build.exe` (native C++ or Rust; Python would need a bundled interpreter and is slow) | Us | Yes |
| ClassId → SN2 asset mapping table (our choice of look-alike SN2 assets) | Us | Yes (low risk, see below) |
| Manifest of expected SN1 files (relative path, size, SHA-256) for `Build18` | Us | Yes (hashes are not content) |
| Terrain meshes, LODs, collision, object positions, biome map | Builder on the user's PC, from their SN1 files | **Never** |

The mapping table holds SN1 ClassId GUIDs plus our SN2 asset paths. Identifiers like these are low risk. If that is ever in doubt, key the table on
`prefabs.db` path patterns instead (e.g. `*/Coral/*` → an SN2 coral), resolved at build time.

### First-launch flow
1. **Mod start (before the menu):** `SN1WorldLoader.dll` checks `%LOCALAPPDATA%\Subnautica2\Saved\SN1World\cache.json`, keyed by (SN1 manifest hash,
   builder version). Valid → done. Missing or stale → step 2. The cache is outside the game folder, so SN2 updates and Steam verify leave it alone.
2. **Find SN1:** Steam `libraryfolders.vdf` → appid 264710; Epic `%PROGRAMDATA%\Epic\EpicGamesLauncher\Data\Manifests\*.item`; otherwise ask for the
   folder. Game Pass installs (`WindowsApps`, access-restricted) are unsupported. Verify the files against the manifest. A mismatch (a different SN1
   build) stops the build with a clear message.
3. **Build:** the dll starts `sn1build.exe` as a **separate process**. This isolates crashes and frees all its RAM when it exits. The game shows the
   cooked progress widget. Do not block the game thread: a frozen window gets a Windows "Not responding" prompt. Either the menu appears with "play SN1
   world" disabled until the build finishes, or startup is held before the menu behind a loading screen that keeps the window responsive.
4. **Builder per batch** (5,416 octree files, 1,164 MB). It streams one batch per worker; worker count = min(cores - 1, RAM budget / per-batch peak).
   1. Read the `.optoctrees` → density grid → surface extraction (surface nets / dual contouring, matching SN1's look) → simplify → 2-3 LODs.
   2. Write `chunks\<x>-<y>-<z>.bin`: positions and normals quantised to 16 bits, indices, material ids, collision proxy.
   3. Objects: cells + batch objects → per-batch instance lists via the mapping table. Unmapped ClassIds are logged and skipped.
   4. Biome map → per-batch biome id (fog, colour, ambience in our level).
   5. Write each file to a temp name, then rename. Write `cache.json` last. An interrupted build then resumes per batch.

   Estimate: minutes in native code, cache a few hundred MB (both UNTESTED).
5. **Play:** the streaming manager loads chunks within a radius. The dll builds a `UStaticMesh` via `BuildFromStaticMeshDescriptions` (or fills a
   `DynamicMeshComponent`) on worker threads; only component registration runs on the game thread. Out-of-range chunks are destroyed, not hidden
   (project RAM rule).

### Why a C++ UE4SS mod and not Lua
- Lua cannot read binary files fast.
- Per-vertex reflected calls cost 0.27 s per chunk on the game thread (`research/terrain/README.md`).
- `AppendBuffersToMesh` FAILED from Lua (`research/terrain/README.md`).
- A cooked Blueprint cannot read files outside the pak.

Only native code can read the cache.

### Risks and open questions
- `BuildFromStaticMeshDescriptions` may be usable only from native code. Runtime collision cooking (Chaos) in the shipping exe is UNTESTED.
  Fallback: `DynamicMeshComponent` with complex-as-simple collision.
- UE4SS C++ mods depend on the UE4SS SDK and the game's engine version. Early Access patches can break them, like the Lua mods.
- Draw calls and RAM at a large radius without Nanite or HLOD need measuring. Distant batches could use a coarse LOD merged per 2×2×2 batches.
- Multiplayer: out of scope. **Local only, decided 2026-11-19 (user)**, see `research/status.md` "Distribution target".
  - The mod disables or hides host/join while the SN1 world is active.
  - The solo session's own server-side movement checks against our terrain are UNTESTED.
- **Stretch (avoids runtime building):** the builder writes cooked, non-Nanite `StaticMesh` packages into a local IoStore pak, from templates cooked by
  us plus UAssetAPI/retoc-style serialisation, so SN2 streams them like any asset. This is hard and tied to the exact engine version. Research it only
  if the runtime path hits a wall.

### First experiments (cheap, in order)
1. Prove runtime `UStaticMesh::BuildFromStaticMeshDescriptions` from a minimal UE4SS C++ mod: one mesh, visible, with collision.
2. Prototype the builder in Python on one batch (12-18-12) to settle the octree decode (§4 open points), then port the hot loop to native code.
3. Time and measure memory for one batch in native code, then extrapolate to all 5,416.
