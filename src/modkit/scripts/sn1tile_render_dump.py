"""Runs INSIDE the Unreal editor (Python). READ-ONLY dump of render settings of the SN1 terrain tile actors/meshes in L_SN2World.
Output: <Workspace>/reports/origin_tile_render_settings.txt (all tagged SN1Terrain actors, every set). Changes nothing, saves nothing.
Run: python -I src/modkit/tools/ue_run.py src/modkit/scripts/sn1tile_render_dump.py
"""
import os
import unreal

MAP = "/Game/Mods/SN2EmptyWorld/L_SN2World"


def _workspace():
    w = os.environ.get("SN2_WORKSPACE")
    if w:
        return w
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    with open(os.path.join(repo, "local.config"), encoding="utf-8") as f:
        for line in f:
            if line.startswith("SN2_WORKSPACE="):
                return line.split("=", 1)[1].strip().strip('"')
    raise RuntimeError("SN2_WORKSPACE not set and not in local.config")


WS = _workspace()
OUT = os.path.join(WS, "reports", "origin_tile_render_settings.txt")
lines = []


def w(s):
    lines.append(s)


def prop(obj, name):
    try:
        v = obj.get_editor_property(name)
        return v
    except Exception as e:
        return f"<n/a {type(e).__name__}>"


def props(obj, names, indent="    "):
    for n in names:
        w(f"{indent}{n} = {prop(obj, n)}")


cur = unreal.EditorLevelLibrary.get_editor_world() if hasattr(unreal.EditorLevelLibrary, "get_editor_world") else None
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
actors = [a for a in eas.get_all_level_actors() if a.actor_has_tag("SN1Terrain") or a.get_actor_label().startswith("SM_")]
w(f"level actors considered: {len(actors)}")
for a in sorted(actors, key=lambda x: x.get_actor_label()):
    if not isinstance(a, unreal.StaticMeshActor):
        continue
    comp = a.static_mesh_component
    sm = comp.static_mesh
    w("=" * 100)
    w(f"ACTOR {a.get_actor_label()}  class={a.get_class().get_name()}  tags={[str(t) for t in a.tags]}")
    loc = a.get_actor_location()
    w(f"  location = ({loc.x:.1f},{loc.y:.1f},{loc.z:.1f})  scale = {a.get_actor_scale3d()}  rot = {a.get_actor_rotation()}")
    props(a, ["hidden", "is_editor_only_actor", "actor_hidden_in_game", "can_be_damaged", "replicates", "tags"], "  ACTOR.")
    for fn in ["get_data_layer_assets", "get_data_layer_instances"]:
        try:
            w(f"  {fn} = {getattr(a, fn)()}")
        except Exception as e:
            w(f"  {fn} -> n/a ({type(e).__name__})")
    for n in ["is_spatially_loaded", "runtime_grid", "data_layers", "data_layer_assets", "hlod_layer", "is_main_world_only"]:
        w(f"  ACTOR.{n} = {prop(a, n)}")
    w("  COMPONENT (StaticMeshComponent)")
    props(comp, ["visible", "hidden_in_game", "mobility", "ld_max_draw_distance", "cached_max_draw_distance", "min_draw_distance",
                 "never_distance_cull", "bounds_scale", "use_as_occluder", "render_in_main_pass", "render_in_depth_pass",
                 "cast_shadow", "visible_in_ray_tracing", "render_custom_depth", "collision_enabled",
                 "collision_profile_name", "generate_overlap_events", "include_in_hlod", "enable_auto_lod_generation",
                 "hlod_batching_policy", "override_min_lod", "min_lod", "force_nanite_for_masked", "evaluate_world_position_offset",
                 "is_nanite_proxy", "world_position_offset_disable_distance", "exclude_from_light_attachment_group",
                 "allow_cull_distance_volume", "visible_in_reflection_captures", "bound_scale"], "    ")
    try:
        w(f"    BOUNDS (component, world) = {comp.get_local_bounds() if hasattr(comp, 'get_local_bounds') else 'n/a'}")
    except Exception as e:
        w(f"    local bounds n/a {e}")
    try:
        o, e, r = unreal.SystemLibrary.get_component_bounds(comp)
        w(f"    BOUNDS world origin=({o.x:.1f},{o.y:.1f},{o.z:.1f}) extent=({e.x:.1f},{e.y:.1f},{e.z:.1f}) sphere_radius={r:.1f}")
    except Exception as ex:
        w(f"    get_component_bounds n/a ({type(ex).__name__}: {ex})")
    try:
        cp = comp.get_collision_profile_name()
        w(f"    collision profile (getter) = {cp}  complex_as_simple = {prop(sm.get_editor_property('body_setup'), 'collision_trace_flag')}")
    except Exception as ex:
        w(f"    collision getter n/a ({ex})")
    if sm is None:
        w("  MESH none")
        continue
    w(f"  MESH {sm.get_path_name()}")
    try:
        ns = sm.get_editor_property("nanite_settings")
        w(f"    nanite_settings.enabled = {prop(ns, 'enabled')}  position_precision={prop(ns, 'position_precision')}  fallback_relative_error={prop(ns, 'fallback_relative_error')}  keep_percent_triangles={prop(ns, 'keep_percent_triangles')}")
    except Exception as ex:
        w(f"    nanite_settings n/a ({ex})")
    try:
        w(f"    num_lods = {sm.get_num_lods()}  num_sections(lod0) = {sm.get_num_sections(0)}  num_triangles(lod0) = {unreal.ProceduralMeshLibrary if False else 'n/a'}")
    except Exception as ex:
        w(f"    lod count n/a ({ex})")
    try:
        for i in range(sm.get_num_lods()):
            w(f"    LOD{i}: screen_size = {sm.get_lod_screen_size(i) if hasattr(sm, 'get_lod_screen_size') else 'n/a'}  verts={sm.get_num_vertices(i)}  tris~{sm.get_num_triangles(i) if hasattr(sm, 'get_num_triangles') else 'n/a'}")
    except Exception as ex:
        w(f"    per-lod n/a ({ex})")
    props(sm, ["auto_compute_lod_screen_size", "min_lod", "num_streamed_lods", "support_ray_tracing", "allow_cpu_access", "is_built_at_runtime",
               "lod_group", "light_map_resolution", "generate_mesh_distance_field", "hi_res_source_model", "support_gpu_uniformly_distributed_sampling",
               "negative_bounds_extension", "positive_bounds_extension"], "    MESH.")
    try:
        bx = sm.get_bounds()
        w(f"    MESH.get_bounds origin=({bx.origin.x:.1f},{bx.origin.y:.1f},{bx.origin.z:.1f}) box_extent=({bx.box_extent.x:.1f},{bx.box_extent.y:.1f},{bx.box_extent.z:.1f}) sphere_radius={bx.sphere_radius:.1f}")
    except Exception as ex:
        w(f"    MESH.get_bounds n/a ({ex})")
    try:
        bs = sm.get_editor_property("body_setup")
        w(f"    body_setup.collision_trace_flag = {prop(bs, 'collision_trace_flag')}  default_instance.collision_profile_name = {prop(bs.get_editor_property('default_instance'), 'collision_profile_name') if bs else 'n/a'}")
        w(f"    never_needs_cooked_collision_data = {prop(bs, 'never_needs_cooked_collision_data')}  support_uv_from_hit_results = {prop(bs, 'support_uv_from_hit_results')}")
    except Exception as ex:
        w(f"    body_setup n/a ({ex})")

# World-level info
w("=" * 100)
try:
    ws = unreal.EditorLevelLibrary.get_editor_world()
    w(f"WORLD {ws.get_path_name()}  class={ws.get_class().get_name()}")
    wp = unreal.WorldPartitionBlueprintLibrary if hasattr(unreal, "WorldPartitionBlueprintLibrary") else None
    w(f"  WorldPartitionBlueprintLibrary available = {wp is not None}")
    ws_settings = ws.get_world_settings()
    w(f"  world settings class = {ws_settings.get_class().get_name()}  enable_world_partition? = {prop(ws_settings, 'enable_world_partition')}")
    for n in ["kill_z", "enable_world_bounds_checks", "world_gravity_z"]:
        w(f"  WorldSettings.{n} = {prop(ws_settings, n)}")
except Exception as ex:
    w(f"world info n/a ({ex})")
# Other actors that could affect culling: CullDistanceVolume, PostProcess, HLOD
for a in eas.get_all_level_actors():
    cn = a.get_class().get_name()
    if any(k in cn for k in ("CullDistance", "HierarchicalLOD", "WorldPartition", "DataLayer", "LODActor", "PostProcess", "PrecomputedVisibility", "Occlusion")):
        w(f"OTHER ACTOR {a.get_actor_label()} class={cn}")
os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(str(l) for l in lines) + "\n")
unreal.log(f"[SN1TileDump] wrote {OUT} ({len(lines)} lines)")
print(f"[SN1TileDump] wrote {OUT} ({len(lines)} lines)")
