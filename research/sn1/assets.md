# SN1 asset extraction

Sources: 12_sn1_assets.md "12 — SN1 prefab assets: bundles, prefabs, mesh/texture extra" (split 2026-11-28; old text: git show 7221ba9:research/<old file>)

## 12 — SN1 prefab assets: bundles, prefabs, mesh/texture extraction

How the render data of Subnautica 1 (SN1) decoration prefabs (plants, corals, rock doodads, resource outcrops) is extracted offline from the user's own install, and in what form.
Investigation 2026-11-26. Everything here was read offline (no game, no heavy lock). Tool: `src/tools/sn1_extract_prefabs.py`. Outputs go to `<Workspace>/sn1_assets/` only.
Legal: same model as the terrain (`research/sn1/legal.md` §9): the converter runs on each user's PC against their own SN1 install; SN1 meshes/textures are never committed or distributed.
Placement data (CellsCache transforms, ClassIds) is a separate topic: `research/sn1/objects.md` §5 and `src/tools/sn1_objects.py`.

### 1. Tooling
- UnityPy **1.25.4** (`pip install --user UnityPy`, approved 2026-11-26) pulled in: `archspec 0.2.8`, `astc-encoder-py 0.1.12`, `brotli 1.2.1`, `etcpak 0.9.15`, `fmod_toolkit 0.1.3`, `lz4 4.4.5`, `pyfmodex 0.7.2`, `texture2ddecoder 1.0.6`, `tpk_ar 0.2.4` (the last built from source, no compiler needed). numpy 2.5.4 and Pillow 10.2.0 were already installed. **VERIFIED (2026-11-26, pip output)**
- **`python -I` ignores the user site-packages**, so a plain `python -I script.py` cannot import UnityPy. The script appends `site.getusersitepackages()` to `sys.path` itself (appended last, so the script directory is still not importable). **VERIFIED (2026-11-26)**
- `ilspycmd` (see `research/sn1/README.md`) was used once to read the field layout of `PrefabPlaceholder`, `PrefabPlaceholdersGroup`, `LargeWorldEntity` (output `<Workspace>/sn1_decompiled/assets_types/*.cs`, outside the repo).

### 2. Resolving a prefab to bundles (Addressables catalog) — VERIFIED (2026-11-26)
`<SN1Dir>\Subnautica_Data\StreamingAssets\aa\catalog.json` is an Addressables `ContentCatalogData` with base64 binary tables. Decoder = class `Catalog` in the tool (0.1 s to load).
```
m_KeyDataString    : int32 keyCount, then keys at offsets given by the buckets. A key = byte type (0 ascii string, 1 utf16 string, 2 uint16, 3 uint32, 4 int32) + payload (strings: int32 len + bytes).
m_BucketDataString : int32 count, then per bucket: int32 keyOffset, int32 n, n x int32 entryIndex      (bucket i <-> key i)
m_EntryDataString  : int32 count, then per entry 7 x int32: internalIdIdx, providerIdx, depBucketIdx(-1 none), depHash, dataIdx, primaryKeyIdx, resourceTypeIdx
m_InternalIds / m_ProviderIds / m_resourceTypes : plain JSON arrays
```
- Prefab path (the `prefabs.db` string, e.g. `WorldEntities/Natural/limestone.prefab`) is a key (lower-case it for lookup). Its bucket holds one entry with provider `BundledAssetProvider` and internal id `Assets/AddressableResources/<path>`; that entry's `depBucketIdx` bucket lists **bundle entries** whose internal ids are `{UnityEngine.AddressableAssets.Addressables.RuntimePath}\StandaloneWindows64\<file>.bundle` (strip to the file name; folder is `aa\StandaloneWindows64\`).
- The dependency list is the prefab's own bundle first (`<name>.prefab_<hash>.bundle`), then shared `duplicateassetssorted_assets_bundle<N>_<hash>.bundle` files, then `...unitybuiltinshaders...bundle`. It is **bloated**: it includes every bundle reachable from MonoBehaviour references (limestone: 76 bundles, 128 MB, includes the `xlimestonebreak`/`xlimestonehit` prefabs). The tool loads only the primary bundle and pulls in a dependency bundle lazily when a PPtr to an unloaded external file fails to resolve (`deref()` + `CUR_DEPS`). A typical prefab then costs 1 to 3 s.
- The root GameObject is found through the primary bundle's `AssetBundle.m_Container` (name = internal id, `asset` PPtr).
- Cross-bundle PPtrs: `UnityPy.classes.PPtr.PPtr(m_FileID, m_PathID, assetsfile=sf).deref()` finds externals by CAB name among the files loaded into the same `UnityPy.Environment`.
- Bundles carry full TypeTrees, so `ObjectReader.read_typetree()` works for GameObject, Transform, MeshFilter/Renderer, Material, LODGroup, Light, AssetBundle. **MonoBehaviour typetrees are base-only** (`m_GameObject, m_Enabled, m_Script, m_Name`); `read_typetree()` raises `Expected to read 72 bytes, but only read 32 bytes` unless called with `check_read=False`. The script class comes from `m_Script` -> `MonoScript.m_ClassName`; script fields must be parsed from the raw bytes (UnityPy's `TypeTreeGeneratorAPI` is not installed). Raw layout after the base header: `m_GameObject(12) m_Enabled(1, pad to 4) m_Script(12) m_Name(int32 len + bytes, pad to 4)`, then the public fields in declaration order.
  - `PrefabPlaceholder` (child GameObject of a prefab; it spawns another prefab at its own local TRS under its parent, decompiled `PrefabPlaceholder.Spawn`): first field `string prefabClassId` (aligned string), then `bool highPriority`.
  - `LargeWorldEntity`: first field `int cellLevel`, enum `Near=0, Medium=1, Far=2, VeryFar=3, Batch=10, Global=100`.

### 3. What a prefab contains for rendering — VERIFIED (2026-11-26, 213 prefabs exported)
- A prefab is a GameObject tree. Rendering parts are `MeshFilter`+`MeshRenderer` (most), `SkinnedMeshRenderer` (jeweled disks, creatures, eggs; many have **0 bones**, i.e. rigid), `LODGroup`, `ParticleSystem`(+Renderer), `Light`, colliders. Game logic lives in MonoBehaviours (`PrefabIdentifier`, `LargeWorldEntity`, `LiveMixin`, `BreakableResource`, `ResourceTracker`, `EcoTarget`, `SkyApplier`, `WorldForces`, `PlantBehaviour`, `PickPrefab`, ...). The tool lists script class names and component counts in the manifest.
- **The root GameObject's own TRS is NOT part of the geometry.** Decoration roots in the assets carry arbitrary TRS (FBX import leftovers: `quat (-0.707,0,0,0.707)`, positions of several metres, scale 1.8 / 3.0 / 81.7). The placed instance replaces it: in the baked cells (`<Workspace>/sn1_objects/origin_cube.jsonl`) jeweled disks (asset root rot -90 deg about X) are placed with upright yaw-only quaternions, and **the placed scale already contains the asset root scale** (BrainCoral root 1.8 -> placed scales {1.2, 1.8}; `Coral_reef_small_deco_03` root 81.7 -> placed {46.55 ... 115.89}; `Crab_snake_Lower_plate_01_01` root 3.0 -> 2.31..3.53). **VERIFIED (2026-11-26, data comparison)**. So: exported geometry is in prefab-root space with the root TRS excluded; apply the placed pos/quat/scale unchanged. `Coral_reef_small_deco_03`'s exported mesh is only 1.6 x 0.9 x 0.7 *units* (cm in the file) because the 81.7 scale is carried by the instance. Manifest `root_local` records the asset's root TRS for reference.
- **LODGroups:** `m_LODs[i].renderers`. LOD0 is exported; other LODs are listed as `skipped` ("LOD n not exported"). Renderers whose `m_Mesh` is null (the LOD3 billboard quads of kelp, built at runtime) are skipped as "no mesh".
- **Nested prefabs (`PrefabPlaceholder`):** wrecks, `FloatingStone*_Floaters`, fragments consist of placeholder children. The tool lists them as `nested_instances` (class id, prefab path, root-space matrix) and with recursion (default) exports each distinct nested prefab into its own folder. Recursion on the Safe Shallows wrecks took 30 to 65 s each (many nested prefabs).
- Disabled renderers / inactive GameObjects are skipped (listed); `--keep-disabled` exports them.
- Meshes are `m_IsReadable = False` but UnityPy decodes the vertex buffers anyway (`UnityPy.helpers.MeshHelper.MeshHandler`: `m_Vertices, m_Normals, m_UV0, m_UV1, m_Colors, m_Tangents, m_BoneIndices, m_BoneWeights`, `get_triangles()` per submesh; `m_BindPose` from the Mesh object).

### 4. Materials and shaders — VERIFIED (2026-11-26, material properties read from the bundles)
Material typetree: `m_Shader` PPtr -> `Shader.m_ParsedForm.m_Name`; `m_ShaderKeywords` (space separated); `m_CustomRenderQueue`; `stringTagMap` (`RenderType`); `m_SavedProperties.m_TexEnvs / m_Floats / m_Colors`.
Shaders seen in the exported set (213 prefabs): `MarmosetUBER` (178; keywords `MARMO_SPECMAP`, `MARMO_EMISSION`, `UWE_WAVING`, `_ZWRITE_ON`), `UWE/SIG Triplanar with Capping` (7: rock/coral clumps), `UWE/SIG` (2), `UWE/SIG Terrain Grass` (1), `UWE/SIG AlphaCutout + Noisey Wave` (1). The full-database shader table is in §7.
- **MarmosetUBER** texture slots: `_MainTex` (albedo; DXT1/DXT5), `_BumpMap` (normal), `_SpecTex` (spec colour, gloss in alpha for DXT5), `_Illum` (emission). Floats worth keeping: `_Mode`, `_Cutoff`/`_EnableCutOff`, `_MyCullVariable` (UnityEngine CullMode: 0 two-sided, 2 back), `_Shininess`, `_SpecInt`, `_Fresnel`, `_EmissionLM`, `_EnableGlow`, `_GlowStrength`, `_EnableVertexColor`; colours `_Color`, `_SpecColor`, `_GlowColor`; wave/sway: keyword `UWE_WAVING` plus `_Frequency`, `_Scale`, `_Speed`, `_ObjectUp`, `_WaveUpMin`, `_minYpos`, `_maxYpos`. The material carries ~80 more floats and ~30 colours (all copied into the manifest) of which almost all are defaults.
- **UWE/SIG Triplanar with Capping** (rocks `Rock_pillar01`, `Coral_Clump*`): textures are projected from the world position, not from UV0: `_SideTexture`/`_SideBumpMap`/`_SideSIGMap` and `_CapTexture`/`_CapBumpMap`/`_CapSIGMap` (cap = faces pointing up). Vertex colours are present on some of them (`Coral_Clump01a` yes, `Rock_pillar01` no); their role is UNTESTED. **A UE material with world-aligned (triplanar) projection and an up-facing blend is needed for these.**
- **UWE/SIG family**: `_SIGMap` = a packed Spec/Illum/Gloss texture (channel meaning is a guess from the pixel statistics: R varies, G = 0, B constant; UNTESTED). `UWE/SIG Terrain Grass` (grass cards): `_MainTex` DXT5 with alpha (cutout), `_BumpMap`, `_Mask`, `_SIGMap`, two-sided. `UWE/SIG AlphaCutout + Noisey Wave`: cutout + vertex sway (red seaweed).
- Material identity for mesh sections is by (bundle CAB, path id); the manifest lists `materials[]` with `blend_guess` (`opaque|cutout|transparent` from keywords / `RenderType` / queue), `two_sided`, texture slots and all floats/colours.

### 5. Textures — VERIFIED (2026-11-26)
- `Texture2D.image` (UnityPy + `texture2ddecoder`) decodes DXT1, DXT5 (all formats met so far). UnityPy **flips the image to top-origin** (`FLIP_TOP_BOTTOM` in `Texture2DConverter`), so PNGs are top-origin and UE-style UVs need `v_ue = 1 - v_unity` (done in the mesh export).
- **Normal maps** (any slot whose name contains `bump`/`normal`): SN1 stores most as **DXT5nm: R = 1 (constant), G = Y, A = X** (Z is dropped). The tool detects it (format DXT5, red mean > 0.9 and std < 0.02, alpha std > 0.005) and writes an RGB PNG with `x = alpha`, `y = green`, `z = sqrt(1-x^2-y^2)`. Some normals are plain RGB inside DXT5 (mushrooms): they are used as is (`x = red`). Unity tangent space is OpenGL-style (green up); the tool **inverts green** so the PNG is DirectX-style for UE (UE uses v flipped, so green must be inverted once; this derivation is UNTESTED in UE, the PNG itself is VERIFIED to be the usual blue-ish map: mean R/G 0.5, B 0.96 to 0.99).
- Other textures are saved as RGB, or RGBA when alpha is used (alpha-clip albedo, `_SpecTex` gloss). Output: `<Workspace>/sn1_assets/_textures/<TextureName>.png` (shared by all prefabs, de-duplicated by (CAB, path id) through `_textures/index.json`).

### 6. Export format and recommendation (chosen 2026-11-26)
**One baked mesh per prefab, parts merged, material sections, in UE axes/cm, root TRS excluded; the manifest keeps the part list.**
Why baked (not one file per renderer): the SN2 side wants one static mesh per prefab with N material slots, used as an HISM/instanced mesh (22,290 instances of one connector prefab in the census); parts of a prefab are always placed together. The per-part transforms stay in `prefab.json` for anyone who wants separate pieces.
- Axes: `UE.X = 100*u.z, UE.Y = 100*u.x, UE.Z = 100*u.y` (cyclic, handedness kept). Normals use the inverse-transpose of the part matrix, permuted the same way.
- **Winding:** the triangle index order is the Unity order and is NOT changed. Check (VERIFIED 2026-11-26 on 213 prefabs): numeric `(b-a) x (c-a)` in UE axes agrees with the vertex normals for 100 % of triangles on solid meshes (0.96 to 0.99 on creatures, 0.5 on the one-sided-normal grass cards). So the numeric normal points outward exactly like the terrain OBJ, and **the importer must emit `a,d,b` like `sn1terrain_import.py`** (`research/terrain/legacy_lua.md` §3). Mirrored parts (negative determinant) get b/c swapped at export so this stays true.
- UV: `u` unchanged, `v = 1 - v_unity`; the PNGs are top-origin. UV1 and vertex colours are exported when present.
- `mesh.json` (primary; load with `json`):
```json
{"format":"sn1prefab-mesh-v1","units":"cm","vertex_count":384,"triangle_count":566,
 "bounds_cm":{"min":[x,y,z],"max":[x,y,z]},
 "sections":[{"first_triangle":0,"triangle_count":566,"material":"Limestone"}],
 "positions":[x,y,z, ...], "normals":[...], "uv0":[u,v, ...], "uv1":null, "colors":null,
 "triangles":[a,b,c, ...]}
```
  Triangles are sorted so that each section is one contiguous range (`first_triangle`, `triangle_count`, in triangles not indices); section name = material name (matches `prefab.json` `materials[].name`; duplicates get `__2`...). Editor Python: `unreal.GeometryScriptSimpleMeshBuffers` `vertices`, `normals`, `uv0`, `triangles = IntVector(a, d, b)`, material id per section.
- `mesh.obj` is written next to it (same geometry, `v/vt/vn`, `usemtl` per section, faces in the same order; OBJ `vt` v is bottom-origin, i.e. `1 - v_ue`). For viewers only.
- `prefab.json` manifest keys: `prefab, asset, bundles, root_local, lod_groups, class` (`static_mesh|skinned|particles|nested|no_mesh`), `flags` (interesting script classes), `scripts`, `cell_level`, `parts[]` (node path, kind, mesh name, vertices, triangles, materials, lod, local_to_root), `skipped[]`, `nested_prefabs[]`, `nested_instances[]` (UE-axes position + Unity root-space matrix + scale), `lights[]`, `colliders[]`, `particles[]`, `materials[]`, `shaders`, `blend`, `mesh{vertex_count, triangle_count, bounds_cm, winding_agrees_with_normals, sections}`, `section_materials`.
- **Skinned meshes:** with 0 bones (jeweled disks, creatures in the cache) the mesh is exported rigid with the renderer's transform. With bones the code skins the vertices into the rest pose (`sum w_i * bone_i_to_root * bindpose_i * v`); this path is UNTESTED (no decoration prefab with bones was in the test set).
- Preview: `<out>/<prefab>/preview.png` is a numpy z-buffer render of top/front/side/iso with the `_MainTex` applied (not for triplanar materials, which have none).

### 7. Results
(see below, filled in from the runs)

### Dead ends
- **FAILED (2026-11-26):** loading every bundle of the catalog dependency list per prefab (76 bundles, 128 MB for limestone) works but wastes RAM over a whole-database run; replaced by lazy loading.
- **FAILED (2026-11-26):** `MonoBehaviour.read()` / `read_typetree()` raises `ValueError: Expected to read 72 bytes, but only read 32 bytes` (no script TypeTree in the bundle). Use `read_typetree(check_read=False)` and raw bytes.
- **FAILED (2026-11-26):** first normal-map detection used the Unity format as an integer string ("12") instead of its name, so DXT5nm maps were exported un-decoded (R = 1 everywhere). Fixed by `UnityPy.enums.TextureFormat(int).name`; `_CapBumpMap/_SideBumpMap` were also missed because only `_BumpMap` was matched.
