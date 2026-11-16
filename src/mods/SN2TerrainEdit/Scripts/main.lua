-- SN2TerrainEdit — first terrain-editing mod for Subnautica 2 (UE4SS Lua).
-- Places static rock meshes at fixed world coordinates whenever the main world loads.
-- Edit the PLACEMENTS table; each entry is one rock. Press F4 in-game to (re)place them by hand.

local MOD = "SN2TerrainEdit"
local function log(msg) print(string.format("[%s] %s\n", MOD, tostring(msg))) end

-- ------------------------------------------------------------------ config

local PLACEMENTS = {
    {
        name  = "first_rock",
        -- a medium coral-garden rubble boulder (~3-4 m); any SM_* path from the game's content works
        mesh  = "/Game/Art/Environment/Biome/CoralGarden/Rocks/SM_CG_RockBoulderMed_02a.SM_CG_RockBoulderMed_02a",
        -- ~20 m in front of where you were standing at the end of the probe session (open water, Coral Gardens)
        loc   = { X = -200350, Y = 433900, Z = -26450 },
        yaw   = 35,          -- degrees
        scale = 1.0,
    },
}
local WORLD_MATCH = "L_Main"      -- only place in the main world, not the lobby
local DELAY_MS    = 4000          -- wait for the world to settle after the player appears

-- ------------------------------------------------------------------ helpers

-- pcall: indexing a wrapper whose object died mid-sweep throws "System: Global for __index doesn't exist." (seen 2026-11-16)
local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, r = pcall(function() return o:IsValid() end)
    return ok and r == true
end

local function getPC()
    local ok, UEHelpers = pcall(require, "UEHelpers")
    if ok then
        local okP, pc = pcall(UEHelpers.GetPlayerController)
        if okP and isValid(pc) then return pc end
    end
    return nil
end

local function getWorld()
    local pc = getPC()
    if not pc then return nil end
    local ok, w = pcall(function() return pc:GetWorld() end)
    if ok and isValid(w) then return w end
    return nil
end

local function worldName()
    local w = getWorld()
    if not w then return "" end
    local ok, n = pcall(function() return w:GetFullName() end)
    return ok and n or ""
end

-- rocks known to be resident around the Coral Gardens / Axum border; used if the configured mesh is not available
local FALLBACK_MESHES = {
    "/Game/Art/Environment/Biome/CoralGarden/Rocks/SM_CG_RockBoulderMed_02a.SM_CG_RockBoulderMed_02a",
    "/Game/Art/Environment/Biome/OvergrownRuins/Inorganic/SM_OR_LimestoneRubbleBoulder_02a.SM_OR_LimestoneRubbleBoulder_02a",
    "/Game/Art/Environment/Biome/CoralGarden/Rocks/SM_CG_RockRubble_ScreePile_2a.SM_CG_RockRubble_ScreePile_2a",
}

local function tryLoad(path)
    local m = StaticFindObject(path)
    if isValid(m) then return m, "resident" end
    local ok, loaded = pcall(LoadAsset, path)
    if ok and isValid(loaded) then return loaded, "LoadAsset" end
    return nil, ok and "LoadAsset returned nothing" or ("LoadAsset error: " .. tostring(loaded))
end

local function loadMesh(path)
    local m, how = tryLoad(path)
    if m then return m end
    log("configured mesh unavailable (" .. tostring(how) .. "), trying fallbacks")
    for _, fp in ipairs(FALLBACK_MESHES) do
        m, how = tryLoad(fp)
        if m then log("using fallback " .. fp:match("[^/.]+$") .. " (" .. how .. ")"); return m end
    end
    -- last resort: any loaded SM_ rock
    local ok, all = pcall(FindAllOf, "StaticMesh")
    if ok and type(all) == "table" then
        for _, sm in ipairs(all) do
            local okN, n = pcall(function() return sm:GetFName():ToString() end)
            if okN and n:find("^SM_") and (n:find("Rock") or n:find("Boulder")) and not n:find("Collision") then
                log("using any loaded rock: " .. n); return sm
            end
        end
    end
    return nil
end

local function quatFromYaw(deg)
    local half = math.rad(deg) / 2
    return { X = 0, Y = 0, Z = math.sin(half), W = math.cos(half) }
end

-- ------------------------------------------------------------------ placement

local placed = {}   -- name -> actor

local function placeOne(p)
    if placed[p.name] and isValid(placed[p.name]) then
        log(p.name .. " already placed, skipping")
        return
    end
    local world = getWorld()
    local gs = StaticFindObject("/Script/Engine.Default__GameplayStatics")
    local smaClass = StaticFindObject("/Script/Engine.StaticMeshActor")
    if not world or not isValid(gs) or not isValid(smaClass) then log("world / GameplayStatics / StaticMeshActor missing"); return end
    local mesh = loadMesh(p.mesh)
    if not mesh then log("mesh not found or not loadable: " .. p.mesh); return end

    local T = {
        Rotation = quatFromYaw(p.yaw or 0),
        Translation = { X = p.loc.X, Y = p.loc.Y, Z = p.loc.Z },
        Scale3D = { X = p.scale or 1, Y = p.scale or 1, Z = p.scale or 1 },
    }
    local ok, err = pcall(function()
        local pawn = getPC().Pawn
        local okA, actor = pcall(function() return gs:BeginDeferredActorSpawnFromClass(world, smaClass, T, 1, pawn, 0) end)
        if not okA then actor = gs:BeginDeferredActorSpawnFromClass(world, smaClass, T, 1, pawn) end
        if not isValid(actor) then error("spawn returned nothing") end
        local comp = actor.StaticMeshComponent
        pcall(function() comp:SetMobility(2) end)                      -- Movable so the mesh can be assigned post-spawn
        if not pcall(function() gs:FinishSpawningActor(actor, T, 0) end) then gs:FinishSpawningActor(actor, T) end
        local setOk = comp:SetStaticMesh(mesh)
        pcall(function() comp:SetCollisionEnabled(3) end)              -- QueryAndPhysics
        placed[p.name] = actor
        local r = 0
        pcall(function() r = mesh:GetBounds().SphereRadius end)
        local used = "?"
        pcall(function() used = mesh:GetFName():ToString() end)
        log(string.format("placed %s: %s at (%.0f, %.0f, %.0f) yaw %d scale %.2f radius %.1f m (SetStaticMesh=%s)",
            p.name, used, p.loc.X, p.loc.Y, p.loc.Z, p.yaw or 0, p.scale or 1, r / 100, tostring(setOk)))
    end)
    if not ok then log("placing " .. p.name .. " failed: " .. tostring(err)) end
end

local function placeAll(reason)
    local wn = worldName()
    if not wn:find(WORLD_MATCH, 1, true) then
        log("not in " .. WORLD_MATCH .. " (" .. wn .. "), nothing placed [" .. reason .. "]")
        return
    end
    log("placing " .. #PLACEMENTS .. " rock(s) [" .. reason .. "]")
    for _, p in ipairs(PLACEMENTS) do placeOne(p) end
end

-- ------------------------------------------------------------------ custom shapes (F3)
-- Geometry not present in Subnautica 2, built at runtime. Three strategies, tried in order.

local function cameraRay()
    local pc = getPC()
    local ox, oy, oz, fx, fy, fz = 0, 0, 0, 1, 0, 0
    local ok = pcall(function()
        local cam = pc.PlayerCameraManager
        local cl, cr = cam:GetCameraLocation(), cam:GetCameraRotation()
        local f = StaticFindObject("/Script/Engine.Default__KismetMathLibrary"):GetForwardVector(cr)
        ox, oy, oz, fx, fy, fz = cl.X, cl.Y, cl.Z, f.X, f.Y, f.Z
    end)
    return ok, ox, oy, oz, fx, fy, fz
end

local function spawnActorOfClass(classPath, T)
    local world, gs = getWorld(), StaticFindObject("/Script/Engine.Default__GameplayStatics")
    local cls = StaticFindObject(classPath)
    if not world or not isValid(gs) or not isValid(cls) then error("missing world/GameplayStatics/class " .. classPath) end
    local pawn = getPC().Pawn
    local okA, actor = pcall(function() return gs:BeginDeferredActorSpawnFromClass(world, cls, T, 1, pawn, 0) end)
    if not okA then actor = gs:BeginDeferredActorSpawnFromClass(world, cls, T, 1, pawn) end
    if not isValid(actor) then error("spawn of " .. classPath .. " returned nothing") end
    if not pcall(function() gs:FinishSpawningActor(actor, T, 0) end) then gs:FinishSpawningActor(actor, T) end
    return actor
end

local function rockMaterial()
    -- borrow a material from any resident rock so the shape is lit/textured like the world
    local ok, all = pcall(FindAllOf, "StaticMesh")
    if ok and type(all) == "table" then
        for _, sm in ipairs(all) do
            local okN, n = pcall(function() return sm:GetFName():ToString() end)
            if okN and n:find("^SM_") and n:find("Rock") and not n:find("Collision") then
                local okM, m = pcall(function() return sm:GetMaterial(0) end)
                if okM and isValid(m) then return m, n end
            end
        end
    end
    return nil
end

-- 1) Geometry Script: star prism in a DynamicMeshActor
local function shape_GeometryScript(T)
    local lib = StaticFindObject("/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_MeshPrimitiveFunctions")
    if not isValid(lib) then error("GeometryScriptLibrary_MeshPrimitiveFunctions not found") end
    local actor = spawnActorOfClass("/Script/GeometryFramework.DynamicMeshActor", T)
    local comp = actor.DynamicMeshComponent
    local dm = comp:GetDynamicMesh()
    if not isValid(dm) then error("GetDynamicMesh returned nothing") end
    -- five-pointed star, outer radius 3 m, inner 1.2 m, extruded 8 m
    local poly = {}
    for i = 0, 9 do
        local r = (i % 2 == 0) and 300 or 120
        local a = math.rad(i * 36 - 90)
        table.insert(poly, { X = r * math.cos(a), Y = r * math.sin(a) })
    end
    local opts = { PolygroupMode = 0, bFlipOrientation = false, UVMode = 0 }
    local identity = { Rotation = { X = 0, Y = 0, Z = 0, W = 1 }, Translation = { X = 0, Y = 0, Z = 0 }, Scale3D = { X = 1, Y = 1, Z = 1 } }
    local okE, errE = pcall(function() lib:AppendSimpleExtrudePolygon(dm, opts, identity, poly, 800.0, 0, true, 1, nil) end)
    if not okE then
        log("AppendSimpleExtrudePolygon failed (" .. tostring(errE) .. "), trying AppendBox")
        lib:AppendBox(dm, opts, identity, 300.0, 300.0, 800.0, 0, 0, 0, 1, nil)
    end
    pcall(function()
        local nlib = StaticFindObject("/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_MeshNormalsFunctions")
        if isValid(nlib) then nlib:RecomputeNormals(dm, { bAngleWeighted = true, bAreaWeighted = true, bUseMeshSmoothingGroups = false, bAutoDetectHardEdges = true, HardEdgeAngleThreshold = 60 }, nil) end
    end)
    local mat, from = rockMaterial()
    if mat then pcall(function() comp:SetMaterial(0, mat) end) end
    pcall(function() comp:SetCollisionEnabled(3); comp:EnableComplexAsSimpleCollision(); comp:NotifyMeshUpdated() end)
    local tris = -1
    pcall(function() tris = dm:GetTriangleCount() end)
    return string.format("GeometryScript star prism: %s, %d triangles, material from %s", actor:GetFName():ToString(), tris, tostring(from))
end

-- 2) ProceduralMeshComponent: a pyramid from raw vertices
local function shape_ProceduralMesh(T)
    local actor = spawnActorOfClass("/Script/Engine.Actor", T)
    local pmcClass = StaticFindObject("/Script/ProceduralMeshComponent.ProceduralMeshComponent")
    if not isValid(pmcClass) then error("ProceduralMeshComponent class not found") end
    local identity = { Rotation = { X = 0, Y = 0, Z = 0, W = 1 }, Translation = { X = 0, Y = 0, Z = 0 }, Scale3D = { X = 1, Y = 1, Z = 1 } }
    local comp = actor:AddComponentByClass(pmcClass, false, identity, false)
    if not isValid(comp) then error("AddComponentByClass returned nothing") end
    local h, b = 600, 300
    local V = { { X = -b, Y = -b, Z = 0 }, { X = b, Y = -b, Z = 0 }, { X = b, Y = b, Z = 0 }, { X = -b, Y = b, Z = 0 }, { X = 0, Y = 0, Z = h } }
    local I = { 0, 2, 1, 0, 3, 2, 0, 1, 4, 1, 2, 4, 2, 3, 4, 3, 0, 4 }
    comp:CreateMeshSection_LinearColor(0, V, I, {}, {}, {}, {}, true)
    local mat = rockMaterial()
    if mat then pcall(function() comp:SetMaterial(0, mat) end) end
    return "ProceduralMeshComponent pyramid: " .. actor:GetFName():ToString()
end

-- 3) Engine primitives: stepped pyramid of cubes
local function shape_CubeStack(T)
    local cube = StaticFindObject("/Engine/BasicShapes/Cube.Cube")
    if not isValid(cube) then local ok, l = pcall(LoadAsset, "/Engine/BasicShapes/Cube.Cube"); if ok then cube = l end end
    if not isValid(cube) then error("Engine Cube mesh not loadable") end
    local mat = rockMaterial()
    local n = 0
    for level = 0, 3 do
        local size = (4 - level) * 150          -- 600, 450, 300, 150 cm wide
        local z = T.Translation.Z + level * 150
        local a = spawnActorOfClass("/Script/Engine.StaticMeshActor", {
            Rotation = T.Rotation, Translation = { X = T.Translation.X, Y = T.Translation.Y, Z = z },
            Scale3D = { X = size / 100, Y = size / 100, Z = 1.5 },
        })
        local c = a.StaticMeshComponent
        pcall(function() c:SetMobility(2) end)
        c:SetStaticMesh(cube)
        if mat then pcall(function() c:SetMaterial(0, mat) end) end
        pcall(function() c:SetCollisionEnabled(3) end)
        n = n + 1
    end
    return "cube-stack pyramid: " .. n .. " cubes"
end

local function spawnCustomShape()
    local okC, ox, oy, oz, fx, fy, fz = cameraRay()
    local dist = 1500
    local T = {
        Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
        Translation = { X = ox + fx * dist, Y = oy + fy * dist, Z = oz + fz * dist - 300 },
        Scale3D = { X = 1, Y = 1, Z = 1 },
    }
    log(string.format("custom shape target (%.0f, %.0f, %.0f), camera-based=%s", T.Translation.X, T.Translation.Y, T.Translation.Z, tostring(okC)))
    for _, s in ipairs({ { "GeometryScript", shape_GeometryScript }, { "ProceduralMesh", shape_ProceduralMesh }, { "CubeStack", shape_CubeStack } }) do
        local ok, res = pcall(s[2], T)
        if ok then log("SUCCESS via " .. s[1] .. ": " .. tostring(res)); return end
        log("strategy " .. s[1] .. " failed: " .. tostring(res))
    end
    log("all custom-shape strategies failed")
end

pcall(RegisterKeyBind, Key.F3, function()
    ExecuteInGameThread(function()
        local ok, err = pcall(spawnCustomShape)
        if not ok then log("F3 failed: " .. tostring(err)) end
    end)
end)

-- ------------------------------------------------------------------ terrain removal (F2)
-- F2        identify what is under the crosshair
-- Shift+F2  hide + disable collision on the actor under the crosshair (press again with nothing new targeted = restore last)
-- Ctrl+F2   toggle ALL loaded landscape (proxies, components, Nanite landscape, heightfield collision)

local function notCDO(o)
    local ok, n = pcall(function() return o:GetFName():ToString() end)
    return ok and not n:find("^Default__")
end

local function crosshairHit()
    local pc = getPC()
    if not pc then error("no player controller") end
    local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local kml = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
    local cam = pc.PlayerCameraManager
    local start = cam:GetCameraLocation()
    local fwd = kml:GetForwardVector(cam:GetCameraRotation())
    local finish = { X = start.X + fwd.X * 50000, Y = start.Y + fwd.Y * 50000, Z = start.Z + fwd.Z * 50000 }
    local col = { R = 0, G = 0, B = 0, A = 0 }
    local hit = {}
    local ok = ksl:LineTraceSingle(pc.Pawn, start, finish, 0, true, {}, 0, hit, true, col, col, 0.0)
    if not ok then return nil end
    local actor, comp
    pcall(function() actor = hit.HitObjectHandle.ReferenceObject:Get() end)
    if not isValid(actor) then pcall(function() actor = hit.HitObjectHandle.Actor:Get() end) end
    pcall(function() comp = hit.Component:Get() end)
    -- UE 5.4+: ReferenceObject can be the hit component (not the actor); walk up to the owning actor
    local okIsComp, owner = pcall(function() return actor:GetOwner() end)
    if okIsComp and isValid(owner) then
        local cname = ""
        pcall(function() cname = actor:GetClass():GetFName():ToString() end)
        if cname:find("Component") then
            if not isValid(comp) then comp = actor end
            actor = owner
        end
    end
    local dist = -1
    pcall(function() dist = hit.Distance end)
    return actor, comp, dist
end

local function describe(actor, comp, dist)
    local acls, aname, ccls, mesh = "?", "?", "?", ""
    pcall(function() acls = actor:GetClass():GetFName():ToString() end)
    pcall(function() aname = actor:GetFullName() end)
    pcall(function() ccls = comp:GetClass():GetFName():ToString() end)
    pcall(function() mesh = " mesh=" .. comp.StaticMesh:GetFName():ToString() end)
    local kind = "OTHER"
    if acls:find("Landscape") or ccls:find("Landscape") then kind = "LANDSCAPE (heightmap terrain)"
    elseif acls == "StaticMeshActor" then kind = "STATIC MESH (rock/terrain kit piece)"
    elseif acls:find("Prefab") then kind = "PREFAB (group of meshes)"
    elseif acls:find("HLOD") then kind = "HLOD (merged distant proxy)"
    elseif acls:find("^BP_") then kind = "BLUEPRINT ACTOR" end
    return string.format("%s | %.1f m | actor %s | component %s%s | %s", kind, dist / 100, acls, ccls, mesh, aname)
end

local removedStack = {}

local function setRemoved(actor, removed)
    actor:SetActorHiddenInGame(removed)
    actor:SetActorEnableCollision(not removed)
end

local function identify()
    local actor, comp, dist = crosshairHit()
    if not isValid(actor) then log("F2: nothing under the crosshair within 500 m"); return end
    log("F2 target: " .. describe(actor, comp, dist))
end

local function removeTarget()
    local actor, comp, dist = crosshairHit()
    if isValid(actor) then
        setRemoved(actor, true)
        table.insert(removedStack, actor)
        log("REMOVED: " .. describe(actor, comp, dist) .. "  (Shift+F2 at empty water restores the last one)")
    else
        local last = table.remove(removedStack)
        if last and isValid(last) then
            setRemoved(last, false)
            log("RESTORED last removed actor: " .. (pcall(function() return last:GetFullName() end) and last:GetFullName() or "?"))
        else
            log("Shift+F2: nothing targeted and nothing to restore")
        end
    end
end

local allLandscapeHidden = false

local function toggleAllLandscape()
    allLandscapeHidden = not allLandscapeHidden
    local hide = allLandscapeHidden
    local counts = {}
    local function each(className, fn)
        local ok, list = pcall(FindAllOf, className)
        local n = 0
        if ok and type(list) == "table" then
            for _, o in ipairs(list) do
                if isValid(o) and notCDO(o) and pcall(fn, o) then n = n + 1 end
            end
        end
        counts[#counts + 1] = className .. "=" .. n
    end
    each("LandscapeStreamingProxy", function(a) setRemoved(a, hide) end)
    each("Landscape", function(a) setRemoved(a, hide) end)
    each("LandscapeComponent", function(c) c:SetHiddenInGame(hide, false); c:SetVisibility(not hide, false) end)
    each("LandscapeNaniteComponent", function(c) c:SetHiddenInGame(hide, false); c:SetVisibility(not hide, false) end)
    each("LandscapeHeightfieldCollisionComponent", function(c) c:SetCollisionEnabled(hide and 0 or 3) end)
    log(string.format("Ctrl+F2: ALL landscape %s  [%s]", hide and "REMOVED" or "RESTORED", table.concat(counts, ", ")))
end

local function bindMod(key, mods, label, fn)
    local ok, err = pcall(RegisterKeyBind, key, mods, function()
        ExecuteInGameThread(function()
            local okF, e = pcall(fn)
            if not okF then log(label .. " failed: " .. tostring(e)) end
        end)
    end)
    if not ok then log("could not bind " .. label .. ": " .. tostring(err)) end
end

bindMod(Key.F2, {}, "F2 identify", identify)
bindMod(Key.F2, { ModifierKey.SHIFT }, "Shift+F2 remove target", removeTarget)
bindMod(Key.F2, { ModifierKey.CONTROL }, "Ctrl+F2 all landscape", toggleAllLandscape)

-- ------------------------------------------------------------------ removal regions (automatic)
-- Landscape tiles whose bounds touch a region are removed as soon as they stream in (swept every SWEEP_MS),
-- so the area never shows. mode = "destroy" frees the actor + components (then garbage-collects);
-- mode = "hide" only hides them (everything stays in RAM).

-- 2026-11-16: region clearing moved into the cooked SN2Terrain ModActor graph (LogicMods). Set true to use the Lua sweep again.
local LUA_REGION_REMOVAL = false
local REMOVE_REGIONS = LUA_REGION_REMOVAL and {
    -- where the test save loads (estimated from the tiles streamed in around the player, 2026-11-15)
    { name = "spawn_hole", center = { X = -331747, Y = 420670 }, radius = 30000, mode = "destroy",
      clearDressing = true, fillWithTestPatch = false },  -- terrain now comes from the cooked SN2Terrain mod
} or {}
-- the cooked SN2Terrain patch: centre XY + highest point (-6224 + 1607 cm), used by F1
local COOKED_PATCH = { X = -331747, Y = 420670, TopZ = -4617 }
local SWEEP_MS = 1500

local regionStats = { destroyed = 0, hidden = 0, sweeps = 0 }
local pendingGC = false

local function boundsXY(actor)
    local O, E = {}, {}
    local ok = pcall(function() actor:GetActorBounds(false, O, E, false) end)
    if not ok or not O.X then return nil end
    return O.X, O.Y, E.X, E.Y
end

local function regionFor(actor)
    local ox, oy, ex, ey = boundsXY(actor)
    if not ox then return nil end
    for _, r in ipairs(REMOVE_REGIONS) do
        -- distance from circle centre to the tile's XY box
        local dx = math.max(math.abs(r.center.X - ox) - ex, 0)
        local dy = math.max(math.abs(r.center.Y - oy) - ey, 0)
        if dx * dx + dy * dy <= r.radius * r.radius then return r end
    end
    return nil
end

local seenHidden = {}

local function countOf(cls)
    local ok, t = pcall(FindAllOf, cls)
    if not ok or type(t) ~= "table" then return 0 end
    local n = 0
    for _, o in ipairs(t) do if isValid(o) and notCDO(o) then n = n + 1 end end
    return n
end

local function landscapeCounts()
    return string.format("proxies=%d components=%d nanite=%d collision=%d",
        countOf("LandscapeStreamingProxy"), countOf("LandscapeComponent"),
        countOf("LandscapeNaniteComponent"), countOf("LandscapeHeightfieldCollisionComponent"))
end

local function hideProxyComponents(proxy)
    -- components belonging to this proxy: match on outer name
    local pname = ""
    pcall(function() pname = proxy:GetFullName():match("[^ ]+$") end)
    for _, cls in ipairs({ "LandscapeComponent", "LandscapeNaniteComponent" }) do
        local ok, list = pcall(FindAllOf, cls)
        if ok and type(list) == "table" then
            for _, c in ipairs(list) do
                if isValid(c) and notCDO(c) then
                    local okO, owner = pcall(function() return c:GetOwner() end)
                    if okO and owner == proxy then
                        pcall(function() c:SetHiddenInGame(true, false); c:SetVisibility(false, false) end)
                    end
                end
            end
        end
    end
end

local lastProxySet = ""

-- log every proxy's bounds and match result whenever the loaded set changes
local function diagnoseProxies(proxies, force)
    local names, lines = {}, {}
    for _, proxy in ipairs(proxies) do
        if isValid(proxy) and notCDO(proxy) then
            local n = "?"
            pcall(function() n = proxy:GetFName():ToString() end)
            table.insert(names, n)
            local ox, oy, ex, ey = boundsXY(proxy)
            local lx, ly = 0, 0
            pcall(function() local L = proxy:K2_GetActorLocation(); lx, ly = L.X, L.Y end)
            local r = regionFor(proxy)
            table.insert(lines, string.format("  %s loc(%.0f,%.0f) bounds centre(%s,%s) extent(%s,%s) -> %s",
                n:gsub("LandscapeStreamingProxy_", ""), lx, ly,
                ox and string.format("%.0f", ox) or "nil", oy and string.format("%.0f", oy) or "nil",
                ex and string.format("%.0f", ex) or "nil", ey and string.format("%.0f", ey) or "nil",
                r and ("IN " .. r.name) or "out"))
        end
    end
    table.sort(names)
    local key = table.concat(names, "|")
    if force or key ~= lastProxySet then
        lastProxySet = key
        log(string.format("proxy set changed: %d loaded", #names))
        table.sort(lines)
        for _, l in ipairs(lines) do if l:find("-> IN ", 1, true) then log(l) end end
    end
end

local function sweepRegions()
    if not worldName():find(WORLD_MATCH, 1, true) then return end
    regionStats.sweeps = regionStats.sweeps + 1
    local ok, proxies = pcall(FindAllOf, "LandscapeStreamingProxy")
    if not ok or type(proxies) ~= "table" then return end
    pcall(diagnoseProxies, proxies, false)
    if regionStats.sweeps % 20 == 1 then
        local px, py, pz = "?", "?", "?"
        pcall(function()
            local L = getPC().Pawn:K2_GetActorLocation()
            px, py, pz = string.format("%.0f", L.X), string.format("%.0f", L.Y), string.format("%.0f", L.Z)
        end)
        log(string.format("sweep #%d alive | player at (%s, %s, %s) | destroyed so far %d", regionStats.sweeps, px, py, pz, regionStats.destroyed))
    end
    local acted = 0
    for _, proxy in ipairs(proxies) do
        if isValid(proxy) and notCDO(proxy) then
            local r = regionFor(proxy)
            if r then
                local pname = "?"
                pcall(function() pname = proxy:GetFName():ToString() end)
                if r.mode == "destroy" then
                    pcall(function()
                        local O, E = {}, {}
                        proxy:GetActorBounds(false, O, E, false)
                        if O.Z and E.X and E.X < 20000 then   -- fine tiles only (coarse far tiles are not representative)
                            r.landZsum = (r.landZsum or 0) + O.Z
                            r.landZn = (r.landZn or 0) + 1
                        end
                    end)
                    hideProxyComponents(proxy)
                    pcall(function() proxy:SetActorEnableCollision(false) end)
                    local okD = pcall(function() proxy:K2_DestroyActor() end)
                    if okD then
                        regionStats.destroyed = regionStats.destroyed + 1
                        acted = acted + 1
                        pendingGC = true
                        log(string.format("region %s: DESTROYED %s", r.name, pname))
                    end
                elseif not seenHidden[proxy:GetAddress()] then
                    setRemoved(proxy, true)
                    hideProxyComponents(proxy)
                    seenHidden[proxy:GetAddress()] = true
                    regionStats.hidden = regionStats.hidden + 1
                    acted = acted + 1
                    log(string.format("region %s: HIDDEN %s", r.name, pname))
                end
            end
        end
    end
    if pendingGC then
        pendingGC = false
        local before = landscapeCounts()
        local okGC = pcall(function()
            StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):CollectGarbage()
        end)
        log(string.format("GC requested=%s | before: %s", tostring(okGC), before))
        ExecuteWithDelay(3000, function()
            ExecuteInGameThread(function()
                log("after GC: " .. landscapeCounts() .. string.format(" | total destroyed %d", regionStats.destroyed))
            end)
        end)
    end
end

-- ------------------------------------------------------------------ full clear (dressing)
-- Also destroy terrain dressing inside removal regions: rock/plateau StaticMeshActors, PrefabActors, and
-- Blueprint actors whose class lives under /Game/Art/Environment/ (flora, corals, rock BPs) or is a BP_PCG_* scatter.
-- Everything else (bases, lifepod, resource deposits, story actors, creatures) is kept: allow-list, not deny-list.

local dressingChecked = {}      -- address -> true for actors already judged (outside region or not dressing)
local ourActors = {}            -- addresses of actors this mod spawned (never remove)
local dressingStats = { destroyed = 0, byKind = {} }

local function isDressing(actor)
    local cname, cpath = "", ""
    pcall(function() cname = actor:GetClass():GetFName():ToString() end)
    if cname == "StaticMeshActor" then return true, "StaticMeshActor" end
    if cname == "PrefabActor" then return true, "PrefabActor" end
    if cname:find("^BP_PCG_") then return true, "PCG scatter" end
    pcall(function() cpath = actor:GetClass():GetFullName() end)
    if cpath:find("/Game/Art/Environment/Set/", 1, true) then return false, cname end   -- structures: keep
    if cpath:find("/Game/Art/Environment/", 1, true) then return true, "environment BP" end
    return false, cname
end

local function inRegionPoint(x, y)
    for _, r in ipairs(REMOVE_REGIONS) do
        if r.clearDressing ~= false and r.mode == "destroy" then
            local dx, dy = x - r.center.X, y - r.center.Y
            if dx * dx + dy * dy <= r.radius * r.radius then return r end
        end
    end
    return nil
end

local function sweepDressing()
    local ok, actors = pcall(FindAllOf, "Actor")
    if not ok or type(actors) ~= "table" then return 0 end
    local n = 0
    for _, a in ipairs(actors) do
        if isValid(a) then
            local addr = a:GetAddress()
            if not dressingChecked[addr] and not ourActors[addr] then
                local x, y
                pcall(function() local L = a:K2_GetActorLocation(); x, y = L.X, L.Y end)
                local r = x and inRegionPoint(x, y)
                if not r then
                    dressingChecked[addr] = true
                else
                    local yes, kind = isDressing(a)
                    if not yes then
                        dressingChecked[addr] = true
                    elseif notCDO(a) then
                        pcall(function() a:SetActorHiddenInGame(true); a:SetActorEnableCollision(false) end)
                        if pcall(function() a:K2_DestroyActor() end) then
                            n = n + 1
                            dressingStats.destroyed = dressingStats.destroyed + 1
                            dressingStats.byKind[kind] = (dressingStats.byKind[kind] or 0) + 1
                        end
                    end
                end
            end
        end
    end
    if n > 0 and not dressingStats.survivorsLogged then
        dressingStats.survivorsLogged = true
        local surv = {}
        for _, a in ipairs(actors) do
            if isValid(a) and notCDO(a) and not ourActors[a:GetAddress()] then
                local x, y
                pcall(function() local L = a:K2_GetActorLocation(); x, y = L.X, L.Y end)
                if x and inRegionPoint(x, y) and not isDressing(a) then
                    local key = "?"
                    pcall(function() key = a:GetClass():GetFullName():gsub("^%S+%s+", "") end)
                    surv[key] = (surv[key] or 0) + 1
                end
            end
        end
        local list = {}
        for k, v in pairs(surv) do table.insert(list, { k = k, v = v }) end
        table.sort(list, function(a, b) return a.v > b.v end)
        log(string.format("region survivors (kept, not dressing): %d classes", #list))
        for i = 1, math.min(40, #list) do log(string.format("  keep %4d  %s", list[i].v, list[i].k)) end
    end
    if n > 0 then
        local parts = {}
        for k, v in pairs(dressingStats.byKind) do table.insert(parts, k .. "=" .. v) end
        table.sort(parts)
        log(string.format("region dressing: destroyed %d this sweep (total %d: %s)", n, dressingStats.destroyed, table.concat(parts, ", ")))
        pendingGC = true
    end
    return n
end

-- ------------------------------------------------------------------ generated seafloor patch
-- Reads data\seafloor_test.txt (see src\tools\make_test_heightfield.py) and builds a
-- DynamicMeshActor heightfield in the first destroy region, at the height the old landscape had.

local function modDir()
    local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
    return src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
end

local function readHeightfield(path)
    local f = io.open(path, "r")
    if not f then return nil, "cannot open " .. path end
    local header = f:read("l")
    local n, spacing = header:match("^(%d+)%s+([%d%.]+)")
    n, spacing = tonumber(n), tonumber(spacing)
    local body = f:read("a")
    f:close()
    local h = {}
    for num in body:gmatch("%-?%d+") do h[#h + 1] = tonumber(num) end
    if not n or #h ~= n * n then return nil, string.format("bad file: n=%s heights=%d", tostring(n), #h) end
    return { n = n, spacing = spacing, h = h }
end

local patchBuilt = false
local generatedPatch = nil

local function buildPatch(r)
    local t0 = os.clock()
    local hf, err = readHeightfield(modDir() .. "\\data\\seafloor_test.txt")
    if not hf then error(err) end
    local tRead = os.clock() - t0
    local n, sp = hf.n, hf.spacing
    local half = (n - 1) * sp / 2
    local baseZ = r.landZn and (r.landZsum / r.landZn) or -5000
    local T = {
        Rotation = { X = 0, Y = 0, Z = 0, W = 1 },
        Translation = { X = r.center.X, Y = r.center.Y, Z = baseZ },
        Scale3D = { X = 1, Y = 1, Z = 1 },
    }
    local actor = spawnActorOfClass("/Script/GeometryFramework.DynamicMeshActor", T)
    ourActors[actor:GetAddress()] = true
    local comp = actor.DynamicMeshComponent
    local dm = comp:GetDynamicMesh()

    -- vertex / triangle buffers
    local V, UV, Tri = {}, {}, {}
    for j = 0, n - 1 do
        for i = 0, n - 1 do
            V[#V + 1] = { X = i * sp - half, Y = j * sp - half, Z = hf.h[j * n + i + 1] }
            UV[#UV + 1] = { X = i * sp / 400, Y = j * sp / 400 }
        end
    end
    for j = 0, n - 2 do
        for i = 0, n - 2 do
            local a = j * n + i
            local b, c, d = a + 1, a + n, a + n + 1
            Tri[#Tri + 1] = { X = a, Y = c, Z = b }
            Tri[#Tri + 1] = { X = b, Y = c, Z = d }
        end
    end
    local tBuf = os.clock() - t0

    local method
    local edit = StaticFindObject("/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_MeshBasicEditFunctions")
    local okB, errB = pcall(function()
        local buffers = { Vertices = V, UV0 = UV, Triangles = Tri }
        edit:AppendBuffersToMesh(dm, buffers, {}, 0, false, nil)
    end)
    local tris = -1
    pcall(function() tris = dm:GetTriangleCount() end)
    if okB and tris > 0 then
        method = "AppendBuffersToMesh"
    else
        log("AppendBuffersToMesh failed (" .. tostring(errB) .. ", tris=" .. tris .. "), falling back to rectangle + SetVertexPosition")
        local prim = StaticFindObject("/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_MeshPrimitiveFunctions")
        local query = StaticFindObject("/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_MeshQueryFunctions")
        local identity = { Rotation = { X = 0, Y = 0, Z = 0, W = 1 }, Translation = { X = 0, Y = 0, Z = 0 }, Scale3D = { X = 1, Y = 1, Z = 1 } }
        prim:AppendRectangleXY(dm, { PolygroupMode = 0, bFlipOrientation = false, UVMode = 0 }, identity, (n - 1) * sp, (n - 1) * sp, n - 1, n - 1, nil)
        local vc = 0
        pcall(function() vc = query:GetVertexCount(dm) end)
        for vid = 0, vc - 1 do
            local okV = {}
            local p = query:GetVertexPosition(dm, vid, okV)
            local i = math.floor((p.X + half) / sp + 0.5)
            local j = math.floor((p.Y + half) / sp + 0.5)
            local z = hf.h[j * n + i + 1] or 0
            -- defer notifications for all but the last vertex; the last one pushes the whole edit to render + collision
            edit:SetVertexPosition(dm, vid, { X = p.X, Y = p.Y, Z = z }, {}, vid < vc - 1)
        end
        method = "AppendRectangleXY + SetVertexPosition"
        pcall(function() tris = dm:GetTriangleCount() end)
    end
    local tMesh = os.clock() - t0

    pcall(function()
        local nlib = StaticFindObject("/Script/GeometryScriptingCore.Default__GeometryScriptLibrary_MeshNormalsFunctions")
        nlib:RecomputeNormals(dm, { bAngleWeighted = true, bAreaWeighted = true }, false, nil)
    end)
    pcall(function() comp:MarkRenderStateDirty() end)
    local bstr = "?"
    pcall(function()
        local O, E = {}, {}
        actor:GetActorBounds(false, O, E, false)
        bstr = string.format("centre (%.0f, %.0f, %.0f) extent (%.0f, %.0f, %.0f)", O.X, O.Y, O.Z, E.X, E.Y, E.Z)
    end)
    local vis = "?"
    pcall(function() vis = string.format("visible=%s hiddenInGame=%s", tostring(comp:IsVisible()), tostring(actor.bHidden)) end)
    log("generated seafloor bounds: " .. bstr .. " | " .. vis)
    generatedPatch = actor
    local mat, from = rockMaterial()
    if mat then pcall(function() comp:SetMaterial(0, mat) end) end
    local collision = {}
    for _, step in ipairs({
        { "SetCollisionEnabled", function() comp:SetCollisionEnabled(3) end },
        { "EnableComplexAsSimpleCollision", function() comp:EnableComplexAsSimpleCollision() end },
        { "UpdateCollision", function() comp:UpdateCollision(false) end },
        { "NotifyMeshUpdated", function() comp:NotifyMeshUpdated() end },
    }) do
        collision[#collision + 1] = step[1] .. "=" .. tostring((pcall(step[2])))
    end
    local tAll = os.clock() - t0
    log(string.format("generated seafloor: %s | %d tris via %s | at (%.0f, %.0f, %.0f) | read %.0f ms, buffers %.0f ms, mesh %.0f ms, total %.0f ms | material from %s | %s",
        actor:GetFName():ToString(), tris, method, T.Translation.X, T.Translation.Y, T.Translation.Z,
        tRead * 1000, (tBuf - tRead) * 1000, (tMesh - tBuf) * 1000, tAll * 1000, tostring(from), table.concat(collision, " ")))
end

local function maybeBuildPatch()
    if patchBuilt then return end
    for _, r in ipairs(REMOVE_REGIONS) do
        if r.fillWithTestPatch and (r.landZn or 0) > 0 and regionStats.sweeps > 4 then
            patchBuilt = true
            local ok, err = pcall(buildPatch, r)
            if not ok then log("generated seafloor failed: " .. tostring(err)) end
            return
        end
    end
end

pcall(RegisterKeyBind, Key.F1, function()
    ExecuteInGameThread(function()
        local ok, err = pcall(function()
            local target
            if isValid(generatedPatch) then
                local L = generatedPatch:K2_GetActorLocation()
                target = { X = L.X, Y = L.Y, Z = L.Z + 1000 }
            else   -- cooked SN2Terrain patch
                target = { X = COOKED_PATCH.X, Y = COOKED_PATCH.Y, Z = COOKED_PATCH.TopZ + 1000 }
            end
            getPC().Pawn:K2_SetActorLocation(target, false, {}, true)
            log(string.format("F1: teleported player to (%.0f, %.0f, %.0f), 10 m above the generated seafloor", target.X, target.Y, target.Z))
        end)
        if not ok then log("F1 failed: " .. tostring(err)) end
    end)
end)

pcall(RegisterHook, "/Script/Engine.PlayerController:ClientRestart", function()
    dressingChecked, patchBuilt, generatedPatch = {}, false, nil
    dressingStats.survivorsLogged = false
    for _, r in ipairs(REMOVE_REGIONS) do r.landZsum, r.landZn = nil, nil end
end)

-- Logs the cooked SN2Terrain ModActor's public counters (its graph does the clearing now) + landscape counts, when they change.
local lastModActorLine, modActorTick = nil, 0
local function logModActor()
    modActorTick = modActorTick + 1
    if modActorTick % 3 ~= 0 then return end          -- every ~4.5 s
    local found
    for _, a in ipairs(FindAllOf("ModActor_C") or {}) do
        local okN, full = pcall(function() return a:GetFullName() end)
        if okN and full:find("/Game/Mods/SN2Terrain/", 1, true) and not full:find("Default__", 1, true) and isValid(a) then found = a end
    end
    local line
    if not found then
        line = "SN2Terrain ModActor: not present in this world"
    else
        local v = {}
        for _, k in ipairs({ "bActive", "SweepCount", "ScanCount", "TilesDestroyed", "DressingDestroyed", "LastStaticMeshCount" }) do
            local okV, val = pcall(function() return found[k] end)
            v[#v + 1] = k .. "=" .. tostring(okV and val or "?")
        end
        line = "SN2Terrain ModActor: " .. table.concat(v, " ")
    end
    local counts = ""
    pcall(function() counts = landscapeCounts() end)
    local key = line:gsub("SweepCount=%d+ ", "")      -- don't log just because the sweep ticked
    if key ~= lastModActorLine then
        lastModActorLine = key
        log(line .. " | " .. counts)
    end
end

LoopAsync(SWEEP_MS, function()
    ExecuteInGameThread(function()
        pcall(logModActor)
        local ok, err = pcall(sweepRegions)
        if not ok then log("region sweep failed: " .. tostring(err)) end
        if worldName():find(WORLD_MATCH, 1, true) then
            local okD, errD = pcall(sweepDressing)
            if not okD then log("dressing sweep failed: " .. tostring(errD)) end
            pcall(maybeBuildPatch)
        end
    end)
    return false   -- keep looping
end)

-- ------------------------------------------------------------------ wiring

pcall(RegisterHook, "/Script/Engine.PlayerController:ClientRestart", function()
    placed = {}   -- a new world: old actors are gone
    ExecuteWithDelay(DELAY_MS, function()
        -- the delay callback is off the game thread; spawning and LoadAsset must run on it
        ExecuteInGameThread(function()
            local ok, err = pcall(placeAll, "world start")
            if not ok then log("auto-place failed: " .. tostring(err)) end
        end)
    end)
end)

pcall(RegisterKeyBind, Key.F4, function()
    local ok, err = pcall(placeAll, "F4")
    if not ok then log("F4 failed: " .. tostring(err)) end
end)

log(string.format("removal regions: %d (sweep every %d ms)", #REMOVE_REGIONS, SWEEP_MS))
log(string.format("loaded: %d placement(s); auto-place %d ms after the player appears in %s; F4 = place now, F3 = custom shape, F2 = identify / Shift+F2 remove target / Ctrl+F2 all landscape",
    #PLACEMENTS, DELAY_MS, WORLD_MATCH))
