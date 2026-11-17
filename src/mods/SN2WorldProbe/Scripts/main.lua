-- SN2WorldProbe — a UE4SS Lua mod for Subnautica 2.
--
-- Purpose: find out how the world is actually built at runtime, and test whether
-- terrain / fog can be changed live. It does not change the game until you press a key.
--
--   F5   world report: streaming cells, landscape pieces, every actor class loaded, and the
--        world-system actors (biome / water / temperature / weather / fog / zones) with their
--        property NAMES and types (no values are read — reading arbitrary values crashed once)
--   F6   REMOVE terrain: hide the nearest landscape piece and turn off its collision
--        (press again on the same piece to restore it)
--   F7   ADD terrain: spawn a rock mesh (one the game already has loaded) 8 m ahead of you
--   F8   toggle fog density x6 on every ExponentialHeightFog actor, and count post-process volumes
--   F9   list every console command (FUNC_Exec UFunction) the game exposes
--   F11  property VALUES of the world-system actors, only for simple property types
--
-- Reports are written next to this mod: probe_report.txt, exec_functions.txt, probe_values.txt.
-- The report file is flushed after every section and every step is logged to UE4SS.log,
-- so if the game dies you can see exactly which step did it.

local UEHelpers = require("UEHelpers")

local MOD = "SN2WorldProbe"

local function log(msg)
    print(string.format("[%s] %s\n", MOD, tostring(msg)))
end

local function step(s) log("step: " .. s) end

-- ---------------------------------------------------------------- paths

local function scriptDir()
    local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
    return src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
end
local REPORT_DIR = scriptDir()

local function reportPath(name)
    if REPORT_DIR then return REPORT_DIR .. "\\" .. name end
    return name
end

-- Incremental report writer: every add() is flushed to disk immediately.
local function openReport(name)
    local p = reportPath(name)
    local f, err = io.open(p, "w")
    if not f then log("could not write " .. p .. ": " .. tostring(err)); return nil end
    local R = { path = p, f = f }
    function R.add(s) f:write(tostring(s), "\n"); f:flush() end
    function R.close() f:close(); log("wrote " .. p) end
    return R
end

-- ---------------------------------------------------------------- safe helpers

local function isValid(obj)
    return obj ~= nil and type(obj) == "userdata" and obj.IsValid ~= nil and obj:IsValid()
end

local function nameOf(obj)
    -- UE4SS hands back a null UObject wrapper for empty results; calling a method on it crashes UE4SS.dll (+0x2428xx) -> check first
    if not isValid(obj) then return "none" end
    local ok, n = pcall(function() return obj:GetFName():ToString() end)
    return ok and n or "?"
end

local function fullNameOf(obj)
    local ok, n = pcall(function() return obj:GetFullName() end)
    return ok and n or "?"
end

local function classNameOf(obj)
    local ok, n = pcall(function() return obj:GetClass():GetFName():ToString() end)
    return ok and n or "?"
end

local function isCDO(obj)
    return nameOf(obj):find("^Default__") ~= nil
end

local function loc(actor)
    -- never call into the engine for an actor without a root component (CDOs, half-built actors)
    local okR, root = pcall(function() return actor.RootComponent end)
    if not okR or not isValid(root) then return nil end
    local ok, v = pcall(function() return actor:K2_GetActorLocation() end)
    if ok and v then return v.X, v.Y, v.Z end
    return nil
end

local function fmtLoc(actor)
    local x, y, z = loc(actor)
    if x then return string.format("(%.0f, %.0f, %.0f)", x, y, z) end
    return "(no location)"
end

-- FindAllOf, minus class default objects and invalid objects
local function findAll(className)
    local ok, t = pcall(FindAllOf, className)
    if not ok or type(t) ~= "table" then return {} end
    local out = {}
    for _, o in ipairs(t) do
        if isValid(o) and not isCDO(o) then table.insert(out, o) end
    end
    return out
end

local function getPC()
    local ok, pc = pcall(UEHelpers.GetPlayerController)
    if ok and isValid(pc) then return pc end
    return nil
end

local function getPawn()
    local pc = getPC()
    if not pc then return nil end
    local ok, pawn = pcall(function() return pc.Pawn end)
    if ok and isValid(pawn) then return pawn end
    ok, pawn = pcall(function() return pc:K2_GetPawn() end)
    if ok and isValid(pawn) then return pawn end
    return nil
end

local function getWorld()
    local ok, w = pcall(UEHelpers.GetWorld)
    if ok and isValid(w) then return w end
    local pc = getPC()
    if pc then
        ok, w = pcall(function() return pc:GetWorld() end)
        if ok and isValid(w) then return w end
    end
    return nil
end

local function getGameplayStatics()
    local ok, gs = pcall(UEHelpers.GetGameplayStatics)
    if ok and isValid(gs) then return gs end
    gs = StaticFindObject("/Script/Engine.Default__GameplayStatics")
    if isValid(gs) then return gs end
    return nil
end

local function matchesAny(name, patterns)
    for _, p in ipairs(patterns) do
        if name:find(p, 1, true) then return true end
    end
    return false
end

-- ---------------------------------------------------------------- property schema / values

local STOP_AT = { Actor = true, Pawn = true, Volume = true, Object = true, Info = true, Character = true }

-- Walk own class + parents, calling fn(prop, pname, ptype, ownerClassName). Reflection only, no value reads.
local function forEachProp(obj, fn, maxLevels)
    local ok, err = pcall(function()
        local cls = obj:GetClass()
        for _ = 1, (maxLevels or 3) do
            if not isValid(cls) then break end
            local cname = nameOf(cls)
            if STOP_AT[cname] then break end
            cls:ForEachProperty(function(prop)
                fn(prop, nameOf(prop), classNameOf(prop), cname)
            end)
            local okS, super = pcall(function() return cls:GetSuperStruct() end)
            if not okS then break end
            cls = super
        end
    end)
    return ok, err
end

-- Property names + types only. Safe: touches reflection data, never the instance.
local function dumpSchema(obj, R, maxProps)
    local n = 0
    local ok, err = forEachProp(obj, function(prop, pname, ptype, owner)
        if n >= (maxProps or 120) then return end
        local extra = ""
        if ptype == "StructProperty" then
            local okS, s = pcall(function() return prop:GetStruct() end)
            if okS and isValid(s) then extra = " <" .. nameOf(s) .. ">" end
        end
        R.add(string.format("        %-46s %s%s   [%s]", pname, ptype, extra, owner))
        n = n + 1
    end)
    if not ok then R.add("        (schema dump failed: " .. tostring(err) .. ")") end
end

-- Value reads, restricted to simple property types.
local SIMPLE = {
    BoolProperty = true, IntProperty = true, Int64Property = true, UInt32Property = true, Int8Property = true,
    Int16Property = true, UInt16Property = true, UInt64Property = true, FloatProperty = true,
    DoubleProperty = true, ByteProperty = true, EnumProperty = true, StrProperty = true, NameProperty = true,
    ObjectProperty = true, ClassProperty = true, SoftObjectProperty = true, SoftClassProperty = true,
}
local VEC_STRUCTS = { Vector = "XYZ", Vector3f = "XYZ", Vector3d = "XYZ", Rotator = "PYR", LinearColor = "RGBA", Color = "RGBA", Vector2D = "XY" }

local function dumpValues(obj, R, maxProps)
    local n = 0
    local ok, err = forEachProp(obj, function(prop, pname, ptype, owner)
        if n >= (maxProps or 120) then return end
        local structName
        if ptype == "StructProperty" then
            local okS, s = pcall(function() return prop:GetStruct() end)
            if okS and isValid(s) then structName = nameOf(s) end
            if not structName or not VEC_STRUCTS[structName] then return end
        elseif not SIMPLE[ptype] then
            return
        end
        local vstr = "?"
        local okv, v = pcall(function() return obj[pname] end)
        if okv then
            if type(v) == "userdata" then
                if structName then
                    local layout = VEC_STRUCTS[structName]
                    local okx = pcall(function()
                        if layout == "XYZ" then vstr = string.format("{%.3f, %.3f, %.3f}", v.X, v.Y, v.Z)
                        elseif layout == "XY" then vstr = string.format("{%.3f, %.3f}", v.X, v.Y)
                        elseif layout == "PYR" then vstr = string.format("{P=%.2f, Y=%.2f, R=%.2f}", v.Pitch, v.Yaw, v.Roll)
                        elseif layout == "RGBA" then vstr = string.format("{%.3f, %.3f, %.3f, %.3f}", v.R, v.G, v.B, v.A) end
                    end)
                    if not okx then vstr = "<" .. structName .. ">" end
                else
                    local okn, s = pcall(function() return v:GetFullName() end)
                    vstr = (okn and type(s) == "string") and s or "<object>"
                end
            else
                vstr = tostring(v)
            end
        else
            vstr = "<unreadable>"
        end
        R.add(string.format("        %-46s %-18s = %s", pname, structName and ("S:" .. structName) or ptype, vstr))
        n = n + 1
    end)
    if not ok then R.add("        (value dump failed: " .. tostring(err) .. ")") end
end

-- ---------------------------------------------------------------- F5: world report

local DETAIL = {
    "Biome", "Temperature", "WorldZone", "BoxWorld", "Weather", "Fog", "UWESky", "Ocean",
    "MusicVolume", "WorldPop", "EdgeOfWorld", "Ambien", "PostProcess", "Blight", "SkyLight",
    "DirectionalLight", "SkyAtmosphere", "VolumetricCloud", "WaterBody", "WaterVolume",
    "SpawnZone", "Region", "AIDirector", "SpawnSystem", "DynamicEvent",
}

local function landscapeSection(R, px, py, pz)
    local proxies = findAll("LandscapeStreamingProxy")
    local landscapes = findAll("Landscape")
    local comps = findAll("LandscapeComponent")
    local hlods = findAll("WorldPartitionHLOD")
    R.add(string.format(
        "Landscape: %d   LandscapeStreamingProxy: %d   LandscapeComponent: %d   WorldPartitionHLOD actors: %d",
        #landscapes, #proxies, #comps, #hlods))
    local list = {}
    for _, p in ipairs(proxies) do
        local x, y, z = loc(p)
        if x then
            table.insert(list, { a = p, d = math.sqrt((x - px) ^ 2 + (y - py) ^ 2 + (z - pz) ^ 2) })
        end
    end
    table.sort(list, function(a, b) return a.d < b.d end)
    R.add("Nearest landscape pieces:")
    for i = 1, math.min(15, #list) do
        local e = list[i]
        R.add(string.format("   %7.0f m  %s  origin %s", e.d / 100, fullNameOf(e.a), fmtLoc(e.a)))
    end
end

local function streamingSection(R)
    local ls = findAll("LevelStreaming")
    local cells = findAll("WorldPartitionRuntimeCell")
    local dls = findAll("DataLayerInstance")
    R.add(string.format("LevelStreaming objects: %d   WorldPartitionRuntimeCell: %d   DataLayerInstance: %d",
        #ls, #cells, #dls))
    if #dls > 0 then
        R.add("Data layers:")
        for i, dl in ipairs(dls) do
            if i > 80 then R.add("   ..."); break end
            R.add("   " .. fullNameOf(dl))
        end
    end
end

local function actorHistogram()
    local counts, instances = {}, {}
    local actors = findAll("Actor")
    for _, a in ipairs(actors) do
        local c = classNameOf(a)
        counts[c] = (counts[c] or 0) + 1
        instances[c] = instances[c] or {}
        if #instances[c] < 25 then table.insert(instances[c], a) end
    end
    return counts, instances, #actors
end

local function sortedKeys(counts)
    local keys = {}
    for k in pairs(counts) do table.insert(keys, k) end
    table.sort(keys, function(a, b)
        if counts[a] ~= counts[b] then return counts[a] > counts[b] end
        return a < b
    end)
    return keys
end

local function doReport()
    local R = openReport("probe_report.txt")
    if not R then return end
    R.add("# SN2WorldProbe report  " .. os.date())

    step("world + player")
    local world = getWorld()
    R.add("World: " .. (world and fullNameOf(world) or "?"))
    local pawn = getPawn()
    local px, py, pz = 0, 0, 0
    if pawn then
        px, py, pz = loc(pawn)
        px, py, pz = px or 0, py or 0, pz or 0
        R.add(string.format("Player pawn: %s at %s", fullNameOf(pawn), fmtLoc(pawn)))
    else
        R.add("Player pawn: not found (load into a world first)")
    end
    R.add("")

    step("streaming")
    R.add("## Streaming")
    local ok, err = pcall(streamingSection, R)
    if not ok then R.add("   (streaming section failed: " .. tostring(err) .. ")") end
    R.add("")

    step("terrain")
    R.add("## Terrain")
    ok, err = pcall(landscapeSection, R, px, py, pz)
    if not ok then R.add("   (landscape section failed: " .. tostring(err) .. ")") end
    R.add("")

    step("actor histogram")
    local counts, instances, total = actorHistogram()
    local keys = sortedKeys(counts)
    R.add(string.format("## Actor classes currently loaded (%d actors, %d classes)", total, #keys))
    for i = 1, math.min(300, #keys) do
        R.add(string.format("%7d  %s", counts[keys[i]], keys[i]))
    end
    R.add("")

    step("world-system actors")
    R.add("## World-system actors (biome / water / temperature / weather / fog / zones)")
    for _, k in ipairs(keys) do
        if matchesAny(k, DETAIL) then
            R.add(string.format("### %s  x%d", k, counts[k]))
            for i, a in ipairs(instances[k]) do
                if i > 10 then R.add("   ..."); break end
                R.add(string.format("   %s  at %s", fullNameOf(a), fmtLoc(a)))
            end
            step("schema of " .. k)
            R.add("     properties (names/types):")
            dumpSchema(instances[k][1], R, 120)
        end
    end
    R.close()
end

-- ---------------------------------------------------------------- F11: property values

local function doValues()
    local R = openReport("probe_values.txt")
    if not R then return end
    R.add("# SN2WorldProbe property values (simple types only)  " .. os.date())
    local counts, instances = actorHistogram()
    for _, k in ipairs(sortedKeys(counts)) do
        if matchesAny(k, DETAIL) then
            R.add(string.format("### %s  x%d", k, counts[k]))
            for i, a in ipairs(instances[k]) do
                if i > 2 then break end
                step("values of " .. fullNameOf(a))
                R.add(string.format("   %s  at %s", fullNameOf(a), fmtLoc(a)))
                dumpValues(a, R, 120)
            end
        end
    end
    R.close()
end

-- ---------------------------------------------------------------- F6: remove terrain

local hiddenPieces = {}

local function toggleNearestTerrain()
    local pawn = getPawn()
    if not pawn then log("no player pawn yet - load into the world first"); return end
    local px, py, pz = loc(pawn)
    if not px then log("could not read player location"); return end
    local best, bestD
    for _, cname in ipairs({ "LandscapeStreamingProxy", "Landscape" }) do
        for _, p in ipairs(findAll(cname)) do
            local x, y, z = loc(p)
            if x then
                local d = (x - px) ^ 2 + (y - py) ^ 2 + (z - pz) ^ 2
                if not bestD or d < bestD then best, bestD = p, d end
            end
        end
    end
    if not best then log("no Landscape / LandscapeStreamingProxy actors are loaded here"); return end
    local key = fullNameOf(best)
    local hide = not hiddenPieces[key]
    hiddenPieces[key] = hide
    local ok, err = pcall(function()
        best:SetActorHiddenInGame(hide)
        best:SetActorEnableCollision(not hide)
    end)
    log(string.format("%s terrain piece %s (origin %.0f m away): %s",
        hide and "HID" or "RESTORED", key, math.sqrt(bestD) / 100, ok and "ok" or tostring(err)))
    -- also hide/restore every static mesh within 20 m, so the test is visible wherever the player stands
    local n, byClass = 0, {}
    for _, sm in ipairs(findAll("StaticMeshActor")) do
        local x, y, z = loc(sm)
        if x and (x - px) ^ 2 + (y - py) ^ 2 + (z - pz) ^ 2 < 2000 ^ 2 then
            local okM = pcall(function()
                sm:SetActorHiddenInGame(hide)
                sm:SetActorEnableCollision(not hide)
            end)
            if okM then
                n = n + 1
                local okMesh, mname = pcall(function() return nameOf(sm.StaticMeshComponent.StaticMesh) end)
                mname = okMesh and mname or "?"
                byClass[mname] = (byClass[mname] or 0) + 1
            end
        end
    end
    local parts = {}
    for k, v in pairs(byClass) do table.insert(parts, k .. " x" .. v) end
    table.sort(parts)
    log(string.format("%s %d static meshes within 20 m: %s", hide and "HID" or "RESTORED", n, table.concat(parts, ", "):sub(1, 600)))
end

-- ---------------------------------------------------------------- F7: add terrain

local function pickRockMesh()
    local fallback
    for _, m in ipairs(findAll("StaticMesh")) do
        local n = nameOf(m)
        if n:find("^SM_") and not n:find("Collision") and not n:find("LOD") then
            if n:find("Rock") or n:find("Boulder") or n:find("Plateau") or n:find("Cave") then
                return m
            end
            fallback = fallback or m
        end
    end
    return fallback
end

local spawned = {}

local function spawnTerrainPiece()
    local pawn = getPawn()
    if not pawn then log("no player pawn yet - load into the world first"); return end
    local world, gs = getWorld(), getGameplayStatics()
    if not world or not gs then log("world or GameplayStatics not found"); return end
    local smaClass = StaticFindObject("/Script/Engine.StaticMeshActor")
    if not isValid(smaClass) then log("StaticMeshActor class not found"); return end
    local mesh = pickRockMesh()
    if not mesh then log("no SM_ static mesh is loaded right now, nothing to spawn"); return end

    local px, py, pz = loc(pawn)
    local fx, fy, fz = 1, 0, 0
    -- aim along the camera, not the pawn: in a vehicle or base the pawn forward can point anywhere
    local okC, errC = pcall(function()
        local cam = getPC().PlayerCameraManager
        local cl = cam:GetCameraLocation()
        local cr = cam:GetCameraRotation()
        local KML = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
        local f = KML:GetForwardVector(cr)
        px, py, pz = cl.X, cl.Y, cl.Z
        fx, fy, fz = f.X, f.Y, f.Z
    end)
    if not okC then
        pcall(function() local f = pawn:GetActorForwardVector(); fx, fy, fz = f.X, f.Y, f.Z end)
    end
    log(string.format("spawn origin (%.0f, %.0f, %.0f) forward (%.2f, %.2f, %.2f) camera-based=%s %s",
        px, py, pz, fx, fy, fz, tostring(okC), okC and "" or tostring(errC)))
    -- place the rock so its whole bounding sphere is in front of the camera (not around it)
    local radius = 500
    pcall(function() radius = mesh:GetBounds().SphereRadius or radius end)
    local scale = 1
    local dist = radius * scale * 1.1 + 300
    log(string.format("mesh radius %.0f cm -> placing centre %.1f m ahead at scale %d", radius, dist / 100, scale))
    local T = {
        Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
        Translation = { X = px + fx * dist, Y = py + fy * dist, Z = pz + fz * dist },
        Scale3D = { X = scale, Y = scale, Z = scale },
    }

    step("spawn: BeginDeferredActorSpawnFromClass")
    local ok, err = pcall(function()
        local actor
        local okA, res = pcall(function() return gs:BeginDeferredActorSpawnFromClass(world, smaClass, T, 1, pawn, 0) end)
        if okA then actor = res else
            actor = gs:BeginDeferredActorSpawnFromClass(world, smaClass, T, 1, pawn)
        end
        if not isValid(actor) then error("BeginDeferredActorSpawnFromClass returned nothing") end
        step("spawn: SetMobility + FinishSpawningActor")
        local comp = actor.StaticMeshComponent
        pcall(function() comp:SetMobility(2) end)
        local okFin = pcall(function() gs:FinishSpawningActor(actor, T, 0) end)
        if not okFin then gs:FinishSpawningActor(actor, T) end
        step("spawn: SetStaticMesh")
        local setOk = comp:SetStaticMesh(mesh)
        pcall(function() comp:SetCollisionEnabled(3) end)
        table.insert(spawned, actor)
        log(string.format("spawned %s with mesh %s at %s (SetStaticMesh=%s)",
            fullNameOf(actor), fullNameOf(mesh), fmtLoc(actor), tostring(setOk)))
        pcall(function()
            local b = mesh:GetBounds()
            log(string.format("diag: actor hidden=%s comp visible=%s comp mobility=%s mesh radius=%.0f cm",
                tostring(actor.bHidden), tostring(comp:IsVisible()), tostring(comp.Mobility), b.SphereRadius or -1))
        end)
    end)
    if not ok then log("spawn failed: " .. tostring(err)) end
end

-- ---------------------------------------------------------------- F8: fog / atmosphere

local fogBoost = false

local function toggleFog()
    fogBoost = not fogBoost
    local fogs = findAll("ExponentialHeightFog")
    for _, f in ipairs(fogs) do
        local ok, err = pcall(function()
            local c = f.Component
            local d = c.FogDensity
            local nd = fogBoost and d * 6 or d / 6
            c:SetFogDensity(nd)
            log(string.format("fog %s density %.5f -> %.5f", fullNameOf(f), d, nd))
        end)
        if not ok then log("fog change failed: " .. tostring(err)) end
    end
    if #fogs == 0 then
        log("no ExponentialHeightFog actors loaded - the underwater look is driven by something else (see F5 report)")
    end
    log(string.format("PostProcessVolume: %d   SkyAtmosphere: %d   VolumetricCloud: %d   SkyLight: %d   DirectionalLight: %d",
        #findAll("PostProcessVolume"), #findAll("SkyAtmosphere"), #findAll("VolumetricCloud"),
        #findAll("SkyLight"), #findAll("DirectionalLight")))
end

-- ---------------------------------------------------------------- F9: console commands

-- parameter list of a UFunction (reflection only)
local function paramsOf(fn)
    local parts = {}
    pcall(function()
        fn:ForEachProperty(function(prop)
            local pt = classNameOf(prop):gsub("Property$", "")
            local pn = nameOf(prop)
            local function has(flag)
                local ok, r = pcall(function() return prop:HasAnyPropertyFlags(flag) end)
                return ok and r == true
            end
            local isParm, isOut, isRet = has(0x80), has(0x100), has(0x400)
            local prefix = isRet and "returns " or (isOut and "out " or "")
            table.insert(parts, prefix .. pt .. " " .. pn .. (isParm and "" or "?"))
        end)
    end)
    return table.concat(parts, ", ")
end

local function dumpExecFunctions()
    local game, engine = {}, {}
    local fns = findAll("Function")
    step(string.format("scanning %d UFunctions for FUNC_Exec", #fns))
    for _, fn in ipairs(fns) do
        local ok, flags = pcall(function() return fn:GetFunctionFlags() end)
        if ok and type(flags) == "number" and (flags & 0x200) ~= 0 then
            local name = fullNameOf(fn)
            if name:find("UWE", 1, true) or name:find("SN2", 1, true) or name:find("Cheat", 1, true)
                or name:find("/Game/", 1, true) then
                table.insert(game, name .. "  (" .. paramsOf(fn) .. ")")
            else
                table.insert(engine, name)
            end
        end
    end
    table.sort(game)
    table.sort(engine)
    local R = openReport("exec_functions.txt")
    if not R then return end
    R.add("# Console-callable UFunctions (FUNC_Exec)  " .. os.date())
    R.add("")
    R.add(string.format("## Game-specific (%d)", #game))
    for _, n in ipairs(game) do R.add(n) end
    R.add("")
    R.add(string.format("## Engine / plugins (%d)", #engine))
    for _, n in ipairs(engine) do R.add(n) end
    R.close()
    log(string.format("exec functions: %d game-specific, %d engine", #game, #engine))
end

-- ---------------------------------------------------------------- F12: deep schema of key world-system actors
-- For the first loaded instance of each target class: property schema, the fields of every struct
-- property (2 levels), the schema + simple values of every component it owns, and its own simple values.

local DEEP_TARGETS = {
    "UWEBoxWorldZone", "BP_UWEWaterBiomeRegionActor_C", "BP_UWEOceanBiomeRegionActor_C",
    "BP_AreaTemperature_Proto_C", "BP_TemperatureRegionVolume_SpireHeat_Med_Proto_C",
    "UWEMusicVolume", "UWEHabitationVolume", "UWEVolumeActor", "BP_UWESky_C", "BP_Ocean_C",
    "BP_Fog_Sphere_C", "PostProcessVolume", "BP_EdgeOfWorldVolume_C", "BP_BO_HeatVent_Medium_C",
    "BP_WaterSlugWorldPopProxy_C", "UWEPlaceableProxy", "PrefabActor", "RuntimeVirtualTextureVolume",
    "BP_WaterCurrent_Tier_I_C", "BP_BO_CurrentVent_Medium_C", "MercunaNavGridVolume",
    "UWEWorldPopGlobalResourcesDataStorage", "BP_BlightZone_C", "FMODAmbientSound", "BP_SpineyTail_C",
}
local SKIP_STRUCTS = { PointerToUberGraphFrame = true, TimerHandle = true, Guid = true, Transform = true }
local COMPONENT_STOP = {
    ActorComponent = true, SceneComponent = true, PrimitiveComponent = true, ShapeComponent = true,
    MeshComponent = true, StaticMeshComponent = true, Object = true,
}

local ActorComponentClass
local function isComponent(obj)
    if not ActorComponentClass then ActorComponentClass = StaticFindObject("/Script/Engine.ActorComponent") end
    if not isValid(ActorComponentClass) then return false end
    local ok, r = pcall(function() return obj:IsA(ActorComponentClass) end)
    return ok and r == true
end

local function dumpStructSchema(structObj, R, indent, depth)
    if not isValid(structObj) or depth > 2 then return end
    pcall(function()
        structObj:ForEachProperty(function(p)
            local pn, pt = nameOf(p), classNameOf(p)
            local inner, extra = nil, ""
            if pt == "StructProperty" then
                local okS, s = pcall(function() return p:GetStruct() end)
                if okS and isValid(s) then extra = " <" .. nameOf(s) .. ">"; inner = s end
            end
            R.add(string.format("%s%-40s %s%s", indent, pn, pt, extra))
            if inner and not SKIP_STRUCTS[nameOf(inner)] then dumpStructSchema(inner, R, indent .. "    ", depth + 1) end
        end)
    end)
end

-- like forEachProp but with a component-oriented stop list
local function forEachCompProp(obj, fn)
    return pcall(function()
        local cls = obj:GetClass()
        for _ = 1, 4 do
            if not isValid(cls) then break end
            local cname = nameOf(cls)
            if COMPONENT_STOP[cname] then break end
            cls:ForEachProperty(function(prop) fn(prop, nameOf(prop), classNameOf(prop), cname) end)
            local okS, super = pcall(function() return cls:GetSuperStruct() end)
            if not okS then break end
            cls = super
        end
    end)
end

local function deepDumpActor(a, R)
    local components = {}
    R.add("     properties:")
    local n = 0
    forEachProp(a, function(prop, pname, ptype, owner)
        if n > 160 then return end
        n = n + 1
        local extra = ""
        local structObj
        if ptype == "StructProperty" then
            local okS, s = pcall(function() return prop:GetStruct() end)
            if okS and isValid(s) then extra = " <" .. nameOf(s) .. ">"; structObj = s end
        end
        R.add(string.format("        %-44s %s%s   [%s]", pname, ptype, extra, owner))
        if structObj and not SKIP_STRUCTS[nameOf(structObj)] then
            dumpStructSchema(structObj, R, "            . ", 1)
        elseif ptype == "ObjectProperty" then
            local okv, v = pcall(function() return a[pname] end)
            if okv and isValid(v) then
                R.add("            -> " .. fullNameOf(v))
                if isComponent(v) then table.insert(components, { name = pname, obj = v }) end
            end
        end
    end, 4)
    for _, c in ipairs(components) do
        step("component " .. c.name)
        R.add(string.format("     component %s : %s", c.name, classNameOf(c.obj)))
        forEachCompProp(c.obj, function(prop, pname, ptype, owner)
            local extra, structObj = "", nil
            if ptype == "StructProperty" then
                local okS, s = pcall(function() return prop:GetStruct() end)
                if okS and isValid(s) then extra = " <" .. nameOf(s) .. ">"; structObj = s end
            end
            R.add(string.format("            %-40s %s%s   [%s]", pname, ptype, extra, owner))
            if structObj and not SKIP_STRUCTS[nameOf(structObj)] then
                dumpStructSchema(structObj, R, "                . ", 1)
            end
        end)
        R.add("          values:")
        -- simple values of the component (own + parents up to the stop list)
        local saveStop = STOP_AT
        STOP_AT = COMPONENT_STOP
        dumpValues(c.obj, R, 100)
        STOP_AT = saveStop
    end
    step("values of actor")
    R.add("     values:")
    dumpValues(a, R, 120)
end

local function doDeepSchema()
    local R = openReport("probe_deep.txt")
    if not R then return end
    R.add("# SN2WorldProbe deep schema  " .. os.date())
    local counts, instances = actorHistogram()
    for _, target in ipairs(DEEP_TARGETS) do
        if instances[target] then
            local a = instances[target][1]
            step("deep: " .. target)
            R.add("")
            R.add(string.format("### %s  x%d   %s  at %s", target, counts[target], fullNameOf(a), fmtLoc(a)))
            local ok, err = pcall(deepDumpActor, a, R)
            if not ok then R.add("     (deep dump failed: " .. tostring(err) .. ")") end
        else
            R.add("")
            R.add("### " .. target .. "  (none loaded here)")
        end
    end
    R.close()
end

-- ---------------------------------------------------------------- wiring

local function bind(key, label, fn)
    local ok, err = pcall(RegisterKeyBind, key, function()
        log(label)
        local okF, e = pcall(fn)
        if not okF then log(label .. " failed: " .. tostring(e)) end
    end)
    if not ok then log("could not bind " .. label .. ": " .. tostring(err)) end
end

bind(Key.F5, "F5 world report", doReport)
bind(Key.F6, "F6 toggle nearest terrain piece", toggleNearestTerrain)
bind(Key.F7, "F7 spawn terrain piece", spawnTerrainPiece)
bind(Key.F8, "F8 toggle fog", toggleFog)
bind(Key.F9, "F9 dump console commands", dumpExecFunctions)
bind(Key.F11, "F11 property values", doValues)
bind(Key.F12, "F12 deep schema", doDeepSchema)

pcall(RegisterHook, "/Script/Engine.PlayerController:ClientRestart", function()
    log("player (re)started in a world - F5 report, F6 remove terrain, F7 add terrain, F8 fog, F9 console commands, F11 values, F12 deep schema")
end)

log("loaded. report dir: " .. tostring(REPORT_DIR))
log("keys: F5 report | F6 remove terrain | F7 add terrain | F8 fog | F9 console commands | F11 values | F12 deep schema")
