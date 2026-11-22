-- SN2AutoTest - OBSERVE-ONLY test helper (design 2026-11-18: every player action is simulated OS input from src/tools/autotest_driver.py).
-- Armed only when <mod>\run\active_plan.lua exists (written by the driver; renamed to active_plan.consumed.lua at once); otherwise one log line, no hooks.
-- Logs:   [SN2AutoTest] WORLD <name>   on every map load,  PAWN possessed (+ spawn location),  STATE ... on Ctrl+F11
-- Keys:   Ctrl+Shift+Z/X/C/V/B = teleport to waypoint 1..5 of the plan (lifepod + offset, or the recorded spawn); Ctrl+F11 = log STATE.
-- Only non-observing action: if plan.worldLevel is set, UWELobbyStatics.SetWorldLevel 2 s after WORLD L_ClientLobby (test setup, no menu exists for it).
-- Also (observe-only reads): `BASE comp=.. owner=.. loc=.. rot=..` after every STATE and at SETTLED (what the pawn stands on); at SETTLED a pod component
-- dump run\poddump_<world>_<ts>.txt (components of actors near the lifepod + BP_LifepodManager_C properties; see src/tools/pod_diff.py).
-- OS mode never calls StartNewLocalGame*, LoadLocalGame, SetControlRotation, QuitGame or console commands. ENGINE mode (plan.inputMode=engine, see the block
-- 'ENGINE INPUT MODE' below) polls run\cmd.txt and does menu clicks / look injection from inside the game (nothing is sent through the OS).
local MOD = "SN2AutoTest"
local function log(m) print(string.format("[%s] %s\n", MOD, tostring(m))) end

local function scriptDir()
    local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
    return src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
end
local MOD_DIR = scriptDir()
local RUN_DIR = MOD_DIR and (MOD_DIR .. "\\run") or "run"
local PLAN_FILE = RUN_DIR .. "\\active_plan.lua"
local CONSUMED = RUN_DIR .. "\\active_plan.consumed.lua"

local fp = io.open(PLAN_FILE, "r")
if not fp then log("idle (no plan)"); return end
fp:close()
local okPlan, plan = pcall(dofile, PLAN_FILE)
pcall(os.remove, CONSUMED)
local okRen, renErr = os.rename(PLAN_FILE, CONSUMED)
if not okPlan or type(plan) ~= "table" then log("plan load failed: " .. tostring(plan)); return end
if not okRen then log("WARNING could not rename plan: " .. tostring(renErr)) end
plan.waypoints = plan.waypoints or {}
log(string.format("armed plan=%s worldLevel=%s waypoints=%d", tostring(plan.name), tostring(plan.worldLevel), #plan.waypoints))

local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, v = pcall(function() return o:IsValid() end)
    return ok and v == true
end
local function nameOf(o)
    local ok, n = pcall(function() return o:GetFName():ToString() end)
    return ok and n or "?"
end
local function findAll(className)
    local ok, t = pcall(FindAllOf, className)
    if not ok or type(t) ~= "table" then return {} end
    local out = {}
    for _, o in ipairs(t) do
        if isValid(o) and not nameOf(o):find("^Default__") then out[#out + 1] = o end
    end
    return out
end
local UEHelpers = require("UEHelpers")
local function getPC()
    local ok, pc = pcall(UEHelpers.GetPlayerController)
    if ok and isValid(pc) then return pc end
    return nil
end
local function getPawn(pc)
    pc = pc or getPC()
    if not pc then return nil end
    local ok, pawn = pcall(function() return pc.Pawn end)
    if ok and isValid(pawn) then return pawn end
    return nil
end
local function lobbyStatics() return StaticFindObject("/Script/UWELobby.Default__UWELobbyStatics") end
local function worldLevelName()
    local ok, v = pcall(function() return lobbyStatics():GetWorldLevelName():ToString() end)
    return ok and tostring(v) or "?"
end
local function after(sec, fn)
    ExecuteWithDelay(math.floor(sec * 1000), function()
        ExecuteInGameThread(function()
            local ok, err = pcall(fn)
            if not ok then log("step error: " .. tostring(err)) end
        end)
    end)
end

local logBase, dumpPod, logOceanBody   -- defined below (observe-only: BASE line + pod component dump)
local gen = 0
local spawnLoc = nil
local lobbySeen = false

local function podLocation()
    local pods = findAll("BP_StaticLifepod_Surface_C")
    if #pods > 0 then
        local l = pods[1]:K2_GetActorLocation()
        return { X = l.X, Y = l.Y, Z = l.Z }
    end
    return nil
end

local function waitPawn(myGen)
    if myGen ~= gen then return end
    local pawn = getPawn()
    if pawn then
        local l = pawn:K2_GetActorLocation()
        spawnLoc = { X = l.X, Y = l.Y, Z = l.Z }
        log(string.format("PAWN possessed spawn=(%.0f,%.0f,%.0f)", l.X, l.Y, l.Z))
        -- the pawn settles (falls onto the pod floor) in the first seconds: record the settled position too, and use it for "spawn" waypoints
        after(12, function()
            if myGen ~= gen then return end
            local p2 = getPawn()
            if p2 then
                local l2 = p2:K2_GetActorLocation()
                spawnLoc = { X = l2.X, Y = l2.Y, Z = l2.Z }
                log(string.format("SETTLED spawn=(%.0f,%.0f,%.0f)", l2.X, l2.Y, l2.Z))
                logBase()
                pcall(logOceanBody, "settled")
                local okd, errd = pcall(dumpPod)
                if not okd then log("PODDUMP failed: " .. tostring(errd)) end
            end
        end)
        return
    end
    after(1, function() waitPawn(myGen) end)
end

RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(ctx)
    local ok, world = pcall(function() return ctx:get():GetWorld():GetFullName() end)
    if not ok or type(world) ~= "string" then return end
    local short = world:match("%.([^%.:/ ]+)$") or world
    log("WORLD " .. short)
    if short == "L_ClientLobby" then
        if not lobbySeen then
            lobbySeen = true
            if plan.worldLevel then
                after(2, function()
                    local before = worldLevelName()
                    local ok2, err = pcall(function() lobbyStatics():SetWorldLevel(plan.worldLevel) end)
                    log(string.format("worldLevel set %s -> %s%s", before, worldLevelName(), ok2 and "" or (" ERROR " .. tostring(err))))
                end)
            end
        end
    else
        gen = gen + 1
        spawnLoc = nil
        waitPawn(gen)
    end
end)

local function teleportTo(n)
    local pawn = getPawn()
    local wp = plan.waypoints[n]
    if not pawn or not wp then log(string.format("TELEPORT %d failed: pawn=%s wp=%s", n, tostring(pawn ~= nil), tostring(wp ~= nil))); return end
    local t
    if wp.offset then
        local pod = podLocation() or spawnLoc
        if not pod then log("TELEPORT " .. n .. " failed: no lifepod/spawn"); return end
        t = { X = pod.X + wp.offset[1], Y = pod.Y + wp.offset[2], Z = pod.Z + wp.offset[3] }
    else
        t = spawnLoc
        if not t then log("TELEPORT " .. n .. " failed: no spawn recorded"); return end
    end
    local ok, err = pcall(function() pawn:K2_SetActorLocation({ X = t.X, Y = t.Y, Z = t.Z }, false, {}, true) end)
    log(string.format("TELEPORT %d %s (%.0f,%.0f,%.0f) %s", n, tostring(wp.name), t.X, t.Y, t.Z, ok and "ok" or tostring(err)))
end

-- ---------------------------------------------------------------- BASE line (what the pawn stands on)
local function fmtV(v)
    if type(v) ~= "userdata" and type(v) ~= "table" then return "?" end
    local ok, r = pcall(function() return string.format("%.2f,%.2f,%.2f", v.X, v.Y, v.Z) end)
    return ok and r or "?"
end
local function fmtR(r0)
    if type(r0) ~= "userdata" and type(r0) ~= "table" then return "?" end
    local ok, r = pcall(function() return string.format("%.2f,%.2f,%.2f", r0.Pitch, r0.Yaw, r0.Roll) end)
    return ok and r or "?"
end
function logBase()
    local pawn = getPawn()
    if not pawn then log("BASE none"); return end
    local base = nil
    local e1, e2
    local ok1, err1 = pcall(function() base = pawn:GetMovementBase() end)
    if not ok1 then e1 = tostring(err1) end
    if not isValid(base) then
        local ok2, err2 = pcall(function() base = pawn.BasedMovement.MovementBase end)
        if not ok2 then e2 = tostring(err2) end
    end
    if not isValid(base) then
        log("BASE none")
        -- extra info (read-only): what a line trace straight down from the pawn hits
        local okT, errT = pcall(function()
            local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
            local l = pawn:K2_GetActorLocation()
            local hit = {}
            local hitAny = ksl:LineTraceSingle(pawn, { X = l.X, Y = l.Y, Z = l.Z }, { X = l.X, Y = l.Y, Z = l.Z - 400 }, 0, false, {}, 0, hit, true,
                { R = 0, G = 0, B = 0, A = 0 }, { R = 0, G = 0, B = 0, A = 0 }, 0)
            local comp = nil
            pcall(function() comp = hit.Component:Get() end)
            if not isValid(comp) then pcall(function() comp = hit.HitObjectHandle.ReferenceObject:Get() end) end
            if not isValid(comp) then pcall(function() comp = hit.Component end) end
            if isValid(comp) then
                local oname, floc = "?", "?"
                pcall(function() oname = comp:GetOwner():GetFName():ToString() end)
                pcall(function() floc = fmtV(comp:K2_GetComponentLocation()) end)
                local z = "?"
                pcall(function() z = string.format("%.1f", hit.ImpactPoint.Z) end)
                log(string.format("BASEFLOOR comp=%s owner=%s loc=(%s) impactZ=%s via=linetrace(visibility) ret=%s", comp:GetFullName(), oname, floc, z, tostring(hitAny)))
            else
                log("BASEFLOOR none via=linetrace(visibility) ret=" .. tostring(hitAny))
            end
        end)
        if not okT then log("BASEFLOOR trace error: " .. tostring(errT)) end
        return
    end
    local full, owner, loc, rot = "?", "?", "?,?,?", "?,?,?"
    pcall(function() full = base:GetFullName() end)
    pcall(function() owner = base:GetOwner():GetFName():ToString() end)
    pcall(function() loc = fmtV(base:K2_GetComponentLocation()) end)
    pcall(function() rot = fmtR(base:K2_GetComponentRotation()) end)
    log(string.format("BASE comp=%s owner=%s loc=(%s) rot=(%s)", full, owner, loc, rot))
end

-- Read-only water diagnostics (2026-11-19 v2). Every UE call in its own pcall; failures are logged with the error text (first 70 chars).
local function shortErr(e) return (tostring(e):gsub("[\r\n\t]", " ")):sub(1, 70) end
local function volStr(v)
    if not isValid(v) then return "none" end
    local fn, cn, wv = "?", "?", "?"
    pcall(function() fn = v:GetFullName() end)
    pcall(function() cn = v:GetClass():GetFName():ToString() end)
    pcall(function() wv = tostring(v.bWaterVolume) end)
    return string.format("%s|class=%s|bWaterVolume=%s", fn, cn, wv)
end
local function logWater(pawn)
    local errs = {}
    local function try1(label, fn)
        local ok, r = pcall(fn)
        if ok then return r end
        errs[#errs + 1] = label .. "=" .. shortErr(r)
        return nil
    end
    if not pawn then log("WATER no pawn"); return end
    local cm = try1("CharacterMovement", function() local c = pawn.CharacterMovement; if isValid(c) then return c end; return nil end)
    local mm = cm and try1("MovementMode", function() return tostring(cm.MovementMode) end) or "?"
    local sw = cm and try1("IsSwimming", function() return tostring(cm:IsSwimming()) end) or "?"
    local iw = cm and try1("IsInWater", function() return tostring(cm:IsInWater()) end) or "?"
    local pvA = cm and try1("cm:GetPhysicsVolume", function() return volStr(cm:GetPhysicsVolume()) end) or "?"
    local pvB = cm and try1("UpdatedComponent.PhysicsVolume", function() return volStr(cm.UpdatedComponent.PhysicsVolume) end) or "?"
    local pvC = try1("pawn:GetPhysicsVolume", function() return volStr(pawn:GetPhysicsVolume()) end) or "?"
    log(string.format("WATER movementMode=%s swimming=%s inWater=%s pvCM=%s pvUpdated=%s pvPawn=%s errs=[%s]", mm, sw, iw, pvA, pvB, pvC, table.concat(errs, "; ")))
end

-- BP_Ocean_C runtime BodySize + water volume transform (read-only). Called at SETTLED and from the first STATE.
logOceanBody = function(tag)
    local oceans = findAll("BP_Ocean_C")
    if #oceans == 0 then log("OCEAN " .. tostring(tag) .. " no BP_Ocean_C"); return end
    for _, oc in ipairs(oceans) do
        local bs, rl, rs, ch, cws = "?", "?", "?", "none", "?"
        pcall(function() local v = oc.BodySize; bs = string.format("(%.0f,%.0f,%.0f)", v.X, v.Y, v.Z) end)
        local wvc = nil
        pcall(function() wvc = oc.WaterVolumeComponent end)
        if isValid(wvc) then
            pcall(function() rl = fmtV(wvc.RelativeLocation) end)
            pcall(function() rs = fmtV(wvc.RelativeScale3D) end)
            pcall(function()
                local c = wvc.ChildActor
                if isValid(c) then
                    ch = nameOf(c)
                    cws = fmtV(c.WaterBoxVolumeComponent:K2_GetComponentScale())
                end
            end)
        end
        log(string.format("OCEAN %s %s BodySize=%s WVC relLoc=%s relScale=%s child=%s WaterBoxVolume worldScale=%s", tostring(tag), nameOf(oc), bs, rl, rs, ch, cws))
    end
end

-- One-time water census (first STATE): PhysicsVolumes (+bWaterVolume), BP_BoxVolume_C, BP_Ocean_C, BP_UWEOceanBiomeRegionActor_C, WaterZone.
local censusDone = false
local function waterCensus()
    if censusDone then return end
    censusDone = true
    local want, list = {}, {}
    local function add(a, why)
        local ok, key = pcall(function() return a:GetFullName() end)
        if ok and not want[key] then want[key] = a; list[#list + 1] = { a = a, why = why, key = key } end
    end
    for _, cn in ipairs({ "BP_BoxVolume_C", "BP_Ocean_C", "BP_UWEOceanBiomeRegionActor_C", "WaterZone" }) do
        for _, a in ipairs(findAll(cn)) do add(a, cn) end
    end
    for _, a in ipairs(findAll("PhysicsVolume")) do
        local wv = "?"
        pcall(function() wv = tostring(a.bWaterVolume) end)
        add(a, "PhysicsVolume bWaterVolume=" .. wv)
    end
    log(string.format("WATERCENSUS actors=%d", #list))
    -- primitive components grouped by owner (only for census actors)
    local comps = {}
    for _, c in ipairs(findAll("PrimitiveComponent")) do
        local okO, ok2 = pcall(function() return c:GetOwner():GetFullName() end)
        if okO and ok2 and want[ok2] then
            local l = comps[ok2]; if not l then l = {}; comps[ok2] = l end
            l[#l + 1] = c
        end
    end
    for i, e in ipairs(list) do
        if i > 60 then log("WATERCENSUS truncated at 60 actors"); break end
        local a = e.a
        local cn, loc, sc, bo, be = "?", "?", "?", "?", "?"
        pcall(function() cn = a:GetClass():GetFName():ToString() end)
        pcall(function() loc = fmtV(a:K2_GetActorLocation()) end)
        pcall(function() sc = fmtV(a:GetActorScale3D()) end)
        pcall(function()
            local o, ex = {}, {}
            a:GetActorBounds(false, o, ex)
            bo, be = fmtV(o), fmtV(ex)
        end)
        log(string.format("WATERCENSUS actor=%s class=%s why=%s loc=(%s) scale=(%s) boundsOrigin=(%s) boundsExtent=(%s)", nameOf(a), cn, e.why, loc, sc, bo, be))
        for j, c in ipairs(comps[e.key] or {}) do
            if j > 12 then break end
            local prof, ov, ce, ws = "?", "?", "?", "?"
            pcall(function() prof = c.BodyInstance.CollisionProfileName:ToString() end)
            pcall(function() ov = tostring(c.bGenerateOverlapEvents) end)
            pcall(function() ce = tostring(c:GetCollisionEnabled()) end)
            pcall(function() ws = fmtV(c:K2_GetComponentScale()) end)
            log(string.format("WATERCENSUS   comp=%s class=%s profile=%s overlapEvents=%s collisionEnabled=%s worldScale=(%s)", nameOf(c),
                (function() local r = "?"; pcall(function() r = c:GetClass():GetFName():ToString() end); return r end)(), prof, ov, ce, ws))
        end
    end
end

local function logState()
    local pc = getPC()
    local pawn = getPawn(pc)
    local px, py, pz = 0, 0, 0
    if pawn then local l = pawn:K2_GetActorLocation(); px, py, pz = l.X, l.Y, l.Z end
    local cx, cy, cz = 0, 0, 0
    local yaw, pitch = 0, 0
    if pc then
        pcall(function() local v = pc.PlayerCameraManager:GetCameraLocation(); cx, cy, cz = v.X, v.Y, v.Z end)
        local okc = pcall(function() local r = pc.PlayerCameraManager:GetCameraRotation(); yaw, pitch = r.Yaw, r.Pitch end)
        if not okc then pcall(function() local r = pc:GetControlRotation(); yaw, pitch = r.Yaw, r.Pitch end) end
    end
    local pod = podLocation() or { X = 0, Y = 0, Z = 0 }
    local w = "?"
    if pc then pcall(function() w = pc:GetWorld():GetFName():ToString() end) end
    log(string.format("STATE world=%s pawn=(%.1f,%.1f,%.1f) cam=(%.1f,%.1f,%.1f) yaw=%.2f pitch=%.2f lifepod=(%.1f,%.1f,%.1f)",
        w, px, py, pz, cx, cy, cz, yaw, pitch, pod.X, pod.Y, pod.Z))
    logBase()
    logWater(pawn)
    if not censusDone then pcall(logOceanBody, "firstState"); pcall(waterCensus) end
end

-- ---------------------------------------------------------------- pod component dump (observe-only; read calls only, each in pcall)
local function str(v)
    local t = type(v)
    if t == "nil" then return "?" end
    if t == "number" or t == "boolean" then return tostring(v) end
    if t == "string" then return v end
    if t == "userdata" then
        local ok, r = pcall(function() return v:ToString() end)
        if ok and type(r) == "string" then return r end
        ok, r = pcall(function() return v:GetFullName() end)
        if ok and type(r) == "string" then return r end
    end
    return "?"
end
local function try(fn, ...)
    local ok, r = pcall(fn, ...)
    if not ok or r == nil then return "?" end
    return r
end
local function toList(arr)
    local out = {}
    if arr == nil or type(arr) ~= "userdata" and type(arr) ~= "table" then return out end
    pcall(function()
        arr:ForEach(function(_, e)
            local v = e
            pcall(function() local g = e:get(); if g ~= nil then v = g end end)   -- RemoteUnrealParam -> the UObject
            out[#out + 1] = v
        end)
    end)
    if #out == 0 then pcall(function() for i = 1, #arr do out[#out + 1] = arr[i] end end) end
    return out
end
local function isA(o, cls)
    if cls == nil then return false end
    local ok, r = pcall(function() return o:IsA(cls) end)
    return ok and r == true
end

function dumpPod()
    local pods = findAll("BP_StaticLifepod_Surface_C")
    local pod = pods[1]
    if not pod then log("PODDUMP skipped: no BP_StaticLifepod_Surface_C"); return end
    local pl = pod:K2_GetActorLocation()
    local sceneCls = StaticFindObject("/Script/Engine.SceneComponent")
    local primCls = StaticFindObject("/Script/Engine.PrimitiveComponent")
    local smCls = StaticFindObject("/Script/Engine.StaticMeshComponent")
    local ismCls = StaticFindObject("/Script/Engine.InstancedStaticMeshComponent")
    local caCls = StaticFindObject("/Script/Engine.ChildActorComponent")

    -- actors in scope
    local scope, order, seen = {}, {}, {}
    local function add(a)
        local ok, key = pcall(function() return a:GetFullName() end)
        if ok and not seen[key] then seen[key] = true; scope[#scope + 1] = a end
    end
    local all = findAll("Actor")
    local podKey = try(function() return pod:GetFullName() end)
    for _, a in ipairs(all) do
        local destroyed = false
        pcall(function() destroyed = a:IsActorBeingDestroyed() end)
        if not destroyed then
            local near = false
            pcall(function()
                local l = a:K2_GetActorLocation()
                local dx, dy, dz = l.X - pl.X, l.Y - pl.Y, l.Z - pl.Z
                near = (dx * dx + dy * dy + dz * dz) <= 1500 * 1500
            end)
            local attached = false
            pcall(function()
                local cur = a
                for _ = 1, 25 do
                    cur = cur:GetAttachParentActor()
                    if not isValid(cur) then break end
                    if cur:GetFullName() == podKey then attached = true; break end
                end
            end)
            local water = false   -- always include the ocean / biome region / WaterZone whatever their distance
            pcall(function()
                local cn = a:GetClass():GetFName():ToString()
                water = (cn == "BP_Ocean_C" or cn == "BP_UWEOceanBiomeRegionActor_C" or cn == "WaterZone")
            end)
            if near or attached or water then add(a) end
        end
    end
    for _, m in ipairs(findAll("BP_LifepodManager_C")) do add(m) end

    local world = "?"
    pcall(function() world = pod:GetWorld():GetFName():ToString() end)
    local path = string.format("%s\\poddump_%s_%s.txt", RUN_DIR, world, os.date("%Y%m%d_%H%M%S"))
    local f, err = io.open(path, "w")
    if not f then log("PODDUMP cannot open " .. path .. ": " .. tostring(err)); return end
    local cols = { "actor", "actorClass", "actorHidden", "actorCollision", "comp", "compClass", "parent", "parentOwner", "socket",
        "relLoc", "relRot", "relScale", "worldLoc", "worldRot", "worldScale", "mobility", "visible", "hiddenInGame",
        "collisionEnabled", "collisionProfile", "mesh", "instances", "childActor", "dataLayers", "isRoot" }
    f:write(table.concat(cols, "\t") .. "\n")
    local byOwner = {}
    for _, c in ipairs(findAll("SceneComponent")) do
        local okO, ok2 = pcall(function() return c:GetOwner():GetFullName() end)
        if okO and ok2 then
            local l = byOwner[ok2]
            if not l then l = {}; byOwner[ok2] = l end
            l[#l + 1] = c
        end
    end
    local rows = 0
    local diagN = 0
    local mgr = nil
    log(string.format("PODDUMP scope actors=%d (of %d Actor instances), pod at (%.0f,%.0f,%.0f)", #scope, #all, pl.X, pl.Y, pl.Z))
    for _, a in ipairs(scope) do
        local aname = nameOf(a)
        local aclass = try(function() return a:GetClass():GetFName():ToString() end)
        if aclass == "BP_LifepodManager_C" then mgr = a end
        local ahidden = str(try(function() return a.bHidden end))
        local acoll = str(try(function() return a:GetActorEnableCollision() end))
        local layers = "?"
        pcall(function()
            local t = {}
            for _, dl in ipairs(toList(a:GetDataLayerAssets())) do t[#t + 1] = nameOf(dl) end
            layers = (#t > 0) and table.concat(t, ",") or "-"
        end)
        local root = nil
        pcall(function() root = a.RootComponent end)
        local rootKey = isValid(root) and try(function() return root:GetFullName() end) or ""
        -- components come from FindAllOf("SceneComponent") grouped by owner: K2_GetComponentsByClass returns RemoteUnrealParam elements here
        -- (element :get() did not yield usable UObjects, 2026-11-18), the FindAllOf tables hold real UObjects
        local okc, errc = true, nil
        local comps = byOwner[try(function() return a:GetFullName() end)] or {}
        diagN = diagN + 1
        if diagN <= 2 or aclass == "BP_StaticLifepod_Surface_C" or (#comps > 0 and not isValid(comps[1])) then
            local nvalid = 0
            for _, c in ipairs(comps) do if isValid(c) then nvalid = nvalid + 1 end end
            local c1 = comps[1]
            local w1, w2, w3 = "?", "?", "?"
            if c1 ~= nil then
                local o1, r1 = pcall(function() local v = c1:K2_GetComponentLocation(); return string.format("%.1f,%.1f,%.1f", v.X, v.Y, v.Z) end); w1 = o1 and r1 or ("ERR " .. tostring(r1))
                local o2, r2 = pcall(function() local v = c1.ComponentToWorld.Translation; return string.format("%.1f,%.1f,%.1f", v.X, v.Y, v.Z) end); w2 = o2 and r2 or ("ERR " .. tostring(r2))
                local o3, r3 = pcall(function() local v = c1.RelativeLocation; return string.format("%.1f,%.1f,%.1f", v.X, v.Y, v.Z) end); w3 = o3 and r3 or ("ERR " .. tostring(r3))
            end
            log(string.format("PODDUMP diag actor=%s class=%s ok=%s err=%s comps=%d valid=%d type1=%s K2loc=%s CtW=%s rel=%s", aname, aclass, tostring(okc), tostring(errc), #comps, nvalid, type(c1), w1, w2, w3))
        end
        for _, c in ipairs(comps) do
            if isValid(c) then
                local parent, powner = "none", "none"
                pcall(function()
                    local ap = c:GetAttachParent()
                    if isValid(ap) then parent = nameOf(ap); powner = ap:GetOwner():GetFName():ToString() end
                end)
                local prim = isA(c, primCls)
                local mesh, inst, child, ce, cp = "-", "-", "-", "-", "-"
                if prim then
                    ce = str(try(function() return c:GetCollisionEnabled() end))
                    cp = str(try(function() return c:GetCollisionProfileName() end))
                end
                if isA(c, smCls) then
                    mesh = try(function() return c.StaticMesh:GetFullName() end)
                    if isA(c, ismCls) then inst = str(try(function() return c:GetInstanceCount() end)) end
                end
                if isA(c, caCls) then child = try(function() return nameOf(c.ChildActor) end) end
                local row = {
                    aname, aclass, ahidden, acoll,
                    nameOf(c), try(function() return c:GetClass():GetFName():ToString() end),
                    parent, powner, str(try(function() return c:GetAttachSocketName() end)),
                    fmtV(try(function() return c.RelativeLocation end)), fmtR(try(function() return c.RelativeRotation end)), fmtV(try(function() return c.RelativeScale3D end)),
                    fmtV(try(function() return c:K2_GetComponentLocation() end)), fmtR(try(function() return c:K2_GetComponentRotation() end)), fmtV(try(function() return c:K2_GetComponentScale() end)),
                    str(try(function() return c.Mobility end)), str(try(function() return c:IsVisible() end)), str(try(function() return c.bHiddenInGame end)),
                    ce, cp, str(mesh), inst, str(child), layers,
                    (rootKey ~= "" and try(function() return c:GetFullName() end) == rootKey) and "1" or "0",
                }
                for i = 1, #row do row[i] = tostring(row[i]):gsub("[\t\r\n]", " ") end
                f:write(table.concat(row, "\t") .. "\n")
                rows = rows + 1
            end
        end
    end
    -- lifepod manager: every property of its class chain up to (excluding) Actor
    f:write("\n## MANAGER_PROPERTIES\tname\tpropertyClass\tvalue\n")
    if mgr then
        local c = nil
        pcall(function() c = mgr:GetClass() end)
        for _ = 1, 20 do
            if not c or not isValid(c) then break end
            local cname = nameOf(c)
            if cname == "Actor" then break end
            pcall(function()
                c:ForEachProperty(function(prop)
                    local pn = try(function() return prop:GetFName():ToString() end)
                    local pc = try(function() return prop:GetClass():GetFName():ToString() end)
                    local v = "?"
                    pcall(function()
                        local raw = mgr[pn]
                        local t = type(raw)
                        if t == "number" or t == "boolean" then v = tostring(raw)
                        elseif t == "userdata" and (pc == "ObjectProperty" or pc == "NameProperty" or pc == "StrProperty" or pc == "TextProperty" or pc == "EnumProperty" or pc == "ByteProperty") then
                            local okn, nm = pcall(function() return raw:GetFullName() end)
                            if okn and type(nm) == "string" then v = nm
                            else
                                local okt, tn = pcall(function() return raw:ToString() end)
                                if okt and type(tn) == "string" and (pc == "NameProperty" or pc == "StrProperty" or pc == "TextProperty") then v = tn end
                            end
                        end
                    end)
                    f:write(string.format("%s\t%s\t%s\t%s\n", cname, pn, pc, tostring(v):gsub("[\t\r\n]", " ")))
                end)
            end)
            local nxt = nil
            pcall(function() nxt = c:GetSuperStruct() end)
            c = nxt
        end
    else
        f:write("none\t-\t-\tno BP_LifepodManager_C found\n")
    end
    f:close()
    log(string.format("PODDUMP written %s rows=%d", path, rows))
end

-- ================================================================ ENGINE INPUT MODE (plan.inputMode == "engine"; 2026-11-22)
-- The driver sends commands through run\cmd.txt ("<seq> <verb> <args>", written atomically by os.replace); this block polls it every 250 ms and runs each new
-- command in the game thread. Result lines: "CMD <seq> <verb> ok|fail <detail>". In OS mode (default) none of this is armed: no poll, no hooks.
-- Verbs: state | teleport N | look YAW PITCH [fallback] | frame | inputs | inject NAME [frames] | widgets TAG | buttons | screen | funcs LABEL
--        | click METHOD LABEL...  (METHOD = bcast | bcast0 | fn:<Name> | auto) | quit
-- Player-like order (user decision 2026-11-19): look = Enhanced Input injection (InjectInputVectorForAction on the look action, closed loop);
-- SetControlRotation only with the explicit "fallback" argument or when injection never moves the camera (logged LOOKMODE).
local ENGINE = (plan.inputMode == "engine")
local verbs = {}

local function camRot()
    local pc = getPC()
    if not pc then return nil end
    local y, p
    local okc = pcall(function() local r = pc.PlayerCameraManager:GetCameraRotation(); y, p = r.Yaw, r.Pitch end)
    if not okc or y == nil then pcall(function() local r = pc:GetControlRotation(); y, p = r.Yaw, r.Pitch end) end
    if y == nil then return nil end
    return y, p
end
local function wrap180(a)
    while a > 180 do a = a - 360 end
    while a <= -180 do a = a + 360 end
    return a
end
local function clamp(v, lo, hi) if v < lo then return lo elseif v > hi then return hi end return v end
local function lc(s) return tostring(s):lower() end

-- ---------------------------------------------------------------- Enhanced Input
local function inputSubsystem()
    local ok, s = pcall(FindFirstOf, "EnhancedInputLocalPlayerSubsystem")
    if ok and isValid(s) then return s end
    return nil
end
local function findInputAction(pattern)
    local best
    for _, a in ipairs(findAll("InputAction")) do
        local n = nameOf(a)
        if lc(n):find(lc(pattern), 1, true) then
            -- prefer the plain mouse/keyboard action over gamepad variants
            if not best or (lc(n):find("gamepad") == nil and lc(nameOf(best)):find("gamepad") ~= nil) or #n < #nameOf(best) then best = a end
        end
    end
    return best
end
function verbs.inputs()
    local acts = findAll("InputAction")
    local names = {}
    for _, a in ipairs(acts) do names[#names + 1] = nameOf(a) end
    table.sort(names)
    local f = io.open(RUN_DIR .. "\\inputs.txt", "w")
    if f then f:write(table.concat(names, "\n") .. "\n"); f:close() end
    for _, n in ipairs(names) do log("INPUTACTION " .. n) end
    return true, string.format("%d actions, subsystem=%s", #names, tostring(inputSubsystem() ~= nil))
end
-- hold an action for N frames (value 1.0) then release: used for button-like actions (pause, interact)
function verbs.inject(args)
    local name, frames = args:match("^(%S+)%s*(%d*)")
    frames = tonumber(frames) or 3
    local sub = inputSubsystem()
    local act = name and findInputAction(name)
    if not sub then return false, "no EnhancedInputLocalPlayerSubsystem" end
    if not act then return false, "no InputAction matching " .. tostring(name) end
    local left = frames
    local function step()
        if left <= 0 then return end
        left = left - 1
        pcall(function() sub:InjectInputForAction(act, 1.0, {}, {}) end)
        ExecuteWithDelay(16, function() ExecuteInGameThread(step) end)
    end
    step()
    return true, "action=" .. nameOf(act) .. " frames=" .. frames
end

local lookJob = nil
local lookGain = { yaw = nil, pitch = nil }   -- degrees per injected unit, signed, measured
local function lookFinish(job, status)
    local y, p = camRot()
    log(string.format("LOOK seq=%d %s yaw=%.2f pitch=%.2f target=(%.2f,%.2f) iters=%d mode=%s gain=(%s,%s)", job.seq, status, y or 0, p or 0, job.ty, job.tp,
        job.iters, job.mode, tostring(lookGain.yaw), tostring(lookGain.pitch)))
    if lookJob == job then lookJob = nil end
end
local function lookStep(job)
    if lookJob ~= job then return end
    local y, p = camRot()
    if not y then lookFinish(job, "fail(no camera)"); return end
    job.iters = job.iters + 1
    -- measure the effect of the last injection
    if job.lastY ~= nil and job.v then
        local dy, dp = wrap180(y - job.lastY), p - job.lastP
        if math.abs(job.v.x) > 1e-3 and math.abs(dy) > 0.02 then
            local g = dy / job.v.x
            if math.abs(g) > 2 and math.abs(g) < 25 then lookGain.yaw = lookGain.yaw and (0.5 * lookGain.yaw + 0.5 * g) or g end
        end
        if math.abs(job.v.y) > 1e-3 and math.abs(dp) > 0.02 then
            local g = dp / job.v.y
            if math.abs(g) > 2 and math.abs(g) < 25 then lookGain.pitch = lookGain.pitch and (0.5 * lookGain.pitch + 0.5 * g) or g end
        end
    end
    local ey, ep = wrap180(job.ty - y), job.tp - p
    if math.abs(ey) <= job.tol and math.abs(ep) <= job.tol then
        job.ok = (job.ok or 0) + 1
        if job.ok >= 3 then lookFinish(job, "done"); return end
    else
        job.ok = 0
    end
    if job.iters > job.maxIters then
        if job.mode == "inject" and job.allowFallback then
            job.mode = "fallback"
        else
            lookFinish(job, "timeout"); return
        end
    end
    job.lastY, job.lastP = y, p
    if job.mode == "fallback" then
        local ok, err = pcall(function() getPC():SetControlRotation({ Pitch = clamp(job.tp, -89, 89), Yaw = job.ty, Roll = 0 }) end)
        if not ok then lookFinish(job, "fail(SetControlRotation " .. shortErr(err) .. ")"); return end
        job.v = nil
    else
        local sub, act = inputSubsystem(), job.act
        if not sub or not isValid(act) then lookFinish(job, "fail(no subsystem/action)"); return end
        local gy, gp = lookGain.yaw or job.gy0, lookGain.pitch or job.gp0
        local vx = clamp(ey * 0.5 / gy, -job.vmax, job.vmax)
        local vy = clamp(ep * 0.5 / gp, -job.vmax, job.vmax)
        if math.abs(ey) <= job.tol then vx = 0 end
        if math.abs(ep) <= job.tol then vy = 0 end
        job.v = { x = vx, y = vy }
        local okI, errI = pcall(function() sub:InjectInputVectorForAction(act, { X = vx, Y = vy, Z = 0 }, {}, {}) end)
        if not okI then lookFinish(job, "fail(inject " .. shortErr(errI) .. ")"); return end
        -- no response at all after many frames: injection does not reach the camera
        if job.iters == 60 and not lookGain.yaw and not lookGain.pitch and math.abs(ey) > job.tol then
            log(string.format("LOOKMODE seq=%d injection produced no camera movement in 60 frames", job.seq))
            if job.allowFallback then job.mode = "fallback" end
        end
    end
    ExecuteWithDelay(16, function() ExecuteInGameThread(function() local ok, e = pcall(lookStep, job); if not ok then log("LOOK step error " .. tostring(e)) end end) end)
end
function verbs.look(args, seq)
    local ty, tp, rest = args:match("^(%-?[%d.]+)%s+(%-?[%d.]+)%s*(.*)$")
    ty, tp = tonumber(ty), tonumber(tp)
    if not ty then return false, "usage: look YAW PITCH [fallback]" end
    local fb = rest and rest:find("fallback", 1, true) ~= nil
    local act = findInputAction("look")
    local job = { seq = seq, ty = wrap180(ty), tp = clamp(tp, -89, 89), iters = 0, maxIters = 400, tol = 1.5, vmax = 150, gy0 = 0.1, gp0 = 0.1,
                  allowFallback = (plan.lookFallback == true) or fb, mode = "inject", act = act }
    -- measured 2026-11-22 (exec experiment): one IA_Look injection of (X,Y) turns yaw +6.25*X and pitch -6.25*Y degrees (default sensitivity);
    -- values of 150 per frame (the first guess) spun the camera many times per frame and wrapped to +-180. Keep each step <= ~30 degrees.
    job.vmax, job.gy0, job.gp0 = 5, 6.25, -6.25
    if fb then job.mode = "fallback" end
    if not act and job.mode == "inject" then
        if job.allowFallback then job.mode = "fallback" else return false, "no look InputAction found (run 'inputs')" end
    end
    lookJob = job
    log(string.format("LOOKMODE seq=%d start mode=%s action=%s", seq, job.mode, act and nameOf(act) or "none"))
    lookStep(job)
    return true, "started mode=" .. job.mode
end

-- ---------------------------------------------------------------- misc verbs
function verbs.state() logState(); return true, "" end
function verbs.teleport(args) teleportTo(tonumber(args) or 0); return true, "" end
function verbs.frame()
    local n = -1
    pcall(function() n = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):GetFrameCount() end)
    log(string.format("FRAME %d", n))
    return true, tostring(n)
end
-- DIAGNOSTIC (engine mode only, exploration): run run\<FILE>.lua in the game thread with the mod helpers in scope; its return value is logged.
-- Lets an input-injection experiment be changed without relaunching the game (UE4SS reads the mod Lua only at launch).
function verbs.exec(args)
    local name = args:match("^([%w_%-%.]+)$")
    if not name then return false, "usage: exec FILE (file name inside run\\)" end
    local chunk, err = loadfile(RUN_DIR .. "\\" .. name)
    if not chunk then return false, shortErr(err) end
    local env = setmetatable({ log = log, getPC = getPC, findAll = findAll, nameOf = nameOf, isValid = isValid, verbs = verbs,
        inputSubsystem = inputSubsystem, camRot = camRot, findInputAction = findInputAction, shortErr = shortErr, lookJobGet = function() return lookJob end }, { __index = _G })
    setfenv = setfenv or nil
    if setfenv then setfenv(chunk, env) else debug.setupvalue(chunk, 1, env) end
    local ok, res = pcall(chunk)
    return ok, shortErr(res)
end
function verbs.quit()
    local pc = getPC()
    local ok, err = pcall(function() StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):QuitGame(pc, nil, 0, false) end)
    return ok, ok and "QuitGame called (fallback, not the menu path)" or shortErr(err)
end

-- ---------------------------------------------------------------- UMG discovery
local widgetClass = nil
local function isWidget(o)
    if not isValid(widgetClass) then widgetClass = StaticFindObject("/Script/UMG.Widget") end
    return isA(o, widgetClass)
end
local function parentOf(o)
    local ok, p = pcall(function() return o:GetParent() end)
    if ok and isValid(p) then return p end
    local ok2, ou = pcall(function() return o:GetOuter() end)
    if ok2 and isValid(ou) then return ou end
    return nil
end
-- true when no widget on the way up is collapsed/hidden; second result = reached a viewport root
-- Also: a widget under a WidgetSwitcher is only shown when its branch is the switcher's ACTIVE child (inactive branches keep Visibility=Visible
-- but are not arranged, which is why the old test listed Remove/StartButton/Confirm buttons of screens that were not on screen). Fails closed:
-- when the switcher's active child cannot be read the widget counts as not visible. Third result = reason for a false (diagnostics).
local switcherClass = nil
local function chainVisible(w)
    local cur, prev, rooted = w, nil, false
    for _ = 1, 80 do
        if not isValid(cur) then break end
        if isWidget(cur) then
            local okv, v = pcall(function() return cur:IsVisible() end)
            if okv and v == false then return false, false, "hidden:" .. nameOf(cur) end
            if prev ~= nil then
                if not isValid(switcherClass) then switcherClass = StaticFindObject("/Script/UMG.WidgetSwitcher") end
                if isA(cur, switcherClass) then
                    local oka, act = pcall(function() return cur:GetActiveWidget() end)
                    if not oka or not isValid(act) then return false, false, "switcher-unreadable:" .. nameOf(cur) end
                    local same = false
                    pcall(function() same = (act:GetFullName() == prev:GetFullName()) end)
                    if not same then return false, false, "inactive-branch:" .. nameOf(cur) end
                end
            end
            local oki, inv = pcall(function() return cur:IsInViewport() end)
            if oki and inv == true then rooted = true; break end
        end
        prev = cur
        cur = parentOf(cur)
    end
    return true, rooted
end
local function textOf(tb)
    local t = "?"
    pcall(function() t = tb:GetText():ToString() end)
    return t
end
local function widgetPath(w)
    local parts, cur = {}, w
    for _ = 1, 18 do
        if not isValid(cur) then break end
        parts[#parts + 1] = nameOf(cur)
        cur = parentOf(cur)
    end
    return table.concat(parts, "<")
end
-- all buttons (CommonButtonBase + UMG Button) with label text collected from descendant text widgets
local function collectButtons()
    local btns, list = {}, {}
    for _, cls in ipairs({ "CommonButtonBase", "Button" }) do
        for _, b in ipairs(findAll(cls)) do
            local key = b:GetFullName()
            if not btns[key] then btns[key] = { w = b, cls = cls, labels = {}, key = key }; list[#list + 1] = btns[key] end
        end
    end
    for _, cls in ipairs({ "CommonTextBlock", "TextBlock", "RichTextBlock" }) do
        for _, tb in ipairs(findAll(cls)) do
            local txt = textOf(tb)
            local cur = tb
            for _ = 1, 40 do
                cur = parentOf(cur)
                if not isValid(cur) then break end
                local ent = btns[cur:GetFullName()]
                if ent then ent.labels[#ent.labels + 1] = txt end
            end
        end
    end
    for _, e in ipairs(list) do
        e.vis, e.rooted, e.why = chainVisible(e.w)
        e.vis = e.vis and e.rooted   -- must also reach a widget that is in the viewport
        pcall(function() e.enabled = e.w:GetIsEnabled() end)
        e.label = table.concat(e.labels, "|")
    end
    return list
end
function verbs.buttons()
    local n = 0
    for _, e in ipairs(collectButtons()) do
        if e.vis then
            n = n + 1
            log(string.format("BTN class=%s name=%s label=%s enabled=%s rooted=%s path=%s", nameOf(e.w:GetClass()), nameOf(e.w), e.label, tostring(e.enabled), tostring(e.rooted), widgetPath(e.w)))
        end
    end
    return true, n .. " visible buttons"
end
local function viewportRoots()
    local out = {}
    for _, w in ipairs(findAll("UserWidget")) do
        local ok, inv = pcall(function() return w:IsInViewport() end)
        if ok and inv == true then
            local vis = chainVisible(w)
            out[#out + 1] = { name = nameOf(w), cls = nameOf(w:GetClass()), vis = vis }
        end
    end
    table.sort(out, function(a, b) return a.name < b.name end)
    return out
end
function verbs.screen()
    local parts = {}
    for _, r in ipairs(viewportRoots()) do if r.vis then parts[#parts + 1] = r.cls end end
    log("SCREEN " .. table.concat(parts, ","))
    return true, #parts .. " visible viewport widgets"
end
-- full dump to run\widgets_<tag>.txt: viewport roots, every visible UserWidget (class + path), buttons with labels, text blocks
function verbs.widgets(args)
    local tag = (args and args ~= "") and args or "x"
    local f = io.open(RUN_DIR .. "\\widgets_" .. tag .. ".txt", "w")
    if not f then return false, "cannot open dump file" end
    f:write("== viewport roots (IsInViewport) class name visible ==\n")
    for _, r in ipairs(viewportRoots()) do f:write(string.format("%s\t%s\t%s\n", r.cls, r.name, tostring(r.vis))) end
    f:write("== buttons (class name label enabled visibleChain rooted path) ==\n")
    local nb = 0
    for _, e in ipairs(collectButtons()) do
        nb = nb + 1
        f:write(string.format("%s\t%s\t%s\t%s\t%s\t%s\t%s\twhy=%s\n", nameOf(e.w:GetClass()), nameOf(e.w), e.label, tostring(e.enabled), tostring(e.vis), tostring(e.rooted), widgetPath(e.w), tostring(e.why)))
    end
    f:write("== visible text blocks (text, path) ==\n")
    for _, cls in ipairs({ "CommonTextBlock", "TextBlock" }) do
        for _, tb in ipairs(findAll(cls)) do
            local vis, rooted = chainVisible(tb)
            if vis and rooted then f:write(string.format("%s\t%s\n", textOf(tb), widgetPath(tb))) end
        end
    end
    f:write("== all UserWidgets visible+rooted (class name) ==\n")
    for _, w in ipairs(findAll("UserWidget")) do
        local vis, rooted = chainVisible(w)
        if vis and rooted then f:write(string.format("%s\t%s\n", nameOf(w:GetClass()), nameOf(w))) end
    end
    f:close()
    return true, "buttons=" .. nb .. " file=widgets_" .. tag .. ".txt"
end
-- function names of the first visible button matching LABEL (class chain) -> log FUNCS lines
function verbs.funcs(args)
    for _, e in ipairs(collectButtons()) do
        if e.vis and lc(e.label):find(lc(args), 1, true) then
            local c, n = e.w:GetClass(), 0
            for _ = 1, 12 do
                if not isValid(c) then break end
                local cn = nameOf(c)
                if cn == "Object" then break end
                pcall(function() c:ForEachFunction(function(fn) n = n + 1; log(string.format("FUNCS %s %s", cn, nameOf(fn))) end) end)
                local nxt = nil
                pcall(function() nxt = c:GetSuperStruct() end)
                c = nxt
            end
            return true, string.format("button %s label=%s functions=%d", nameOf(e.w), e.label, n)
        end
    end
    return false, "no visible button with label " .. args
end
-- click a visible button: METHOD LABEL. label match is a case-insensitive substring ("name:<x>" matches the widget name instead)
local CLICK_DENY = { RemoveButton = true, ConfirmRed = true, RenameButton = true, UploadButton = true, ConvertButton = true, UpgradeButton = true, ImportSaveButton = true }
local CLICK_FNS = { "BP_OnClicked", "HandleButtonClicked", "NativeOnClicked", "OnClicked_Internal", "SimulateClick", "ClickButton", "Click", "OnClickedHandler", "HandleClick" }
function verbs.click(args)
    local method, label = args:match("^(%S+)%s+(.+)$")
    if not method then return false, "usage: click METHOD LABEL" end
    -- label forms: "text", "name:Widget", "name:Widget@Screen" (the widget path must contain Screen: same-named buttons exist on several screens)
    local under = nil
    do
        local base, u = label:match("^(.-)@(%S+)$")
        if base then label, under = base, u end
    end
    local target
    for _, e in ipairs(collectButtons()) do
        local hit
        if label:sub(1, 5) == "name:" then hit = lc(nameOf(e.w)):find(lc(label:sub(6)), 1, true) else hit = lc(e.label):find(lc(label), 1, true) end
        if e.vis and hit and (not under or lc(widgetPath(e.w)):find(lc(under), 1, true)) then
            -- hard denylist: never activate destructive / save-management buttons, whatever the plan says
            local nm, lb = nameOf(e.w), lc(e.label)
            if CLICK_DENY[nm] or lb:find("remove", 1, true) or lb:find("delete", 1, true) then
                log(string.format("DENIED click on %s label=%s", nm, e.label))
                return false, string.format("denied: %s (%s)", nm, e.label)
            end
            target = e; break
        end
    end
    if not target then return false, "no visible button for " .. label .. (under and ("@" .. under) or "") end
    local w = target.w
    local function try(m)
        if m == "bcast" or m == "bcast0" then
            local ok, err = pcall(function() if m == "bcast" then w.OnClicked:Broadcast(w) else w.OnClicked:Broadcast() end end)
            return ok, ok and "" or shortErr(err)
        elseif m:sub(1, 3) == "fn:" then
            local name = m:sub(4)
            local ok, err = pcall(function() w[name](w) end)
            return ok, ok and "" or shortErr(err)
        end
        return false, "unknown method " .. m
    end
    if method ~= "auto" then
        local ok, d = try(method)
        return ok, string.format("method=%s button=%s label=%s %s", method, nameOf(w), target.label, d)
    end
    local tried = {}
    for _, m in ipairs({ "bcast", "bcast0" }) do
        local ok, d = try(m)
        tried[#tried + 1] = m .. "=" .. (ok and "ok" or d)
        if ok then return true, string.format("method=%s button=%s label=%s", m, nameOf(w), target.label) end
    end
    for _, fnn in ipairs(CLICK_FNS) do
        local present = false
        pcall(function() present = type(w[fnn]) == "function" or type(w[fnn]) == "userdata" end)
        if present then
            local ok, d = try("fn:" .. fnn)
            tried[#tried + 1] = fnn .. "=" .. (ok and "ok" or d)
            if ok then return true, string.format("method=fn:%s button=%s label=%s", fnn, nameOf(w), target.label) end
        end
    end
    return false, "all methods failed: " .. table.concat(tried, "; ")
end

-- ---------------------------------------------------------------- command poll (250 ms, cheap: one failed io.open when idle)
if ENGINE then
    local CMD_FILE = RUN_DIR .. "\\cmd.txt"
    local lastSeq = 0
    LoopAsync(250, function()
        local f = io.open(CMD_FILE, "r")
        if not f then return false end
        local txt = f:read("*l")
        f:close()
        if not txt then return false end
        local seq, verb, args = txt:match("^%s*(%d+)%s+(%S+)[ \t]*(.-)%s*$")
        seq = tonumber(seq)
        if not seq or seq <= lastSeq then return false end
        lastSeq = seq
        ExecuteInGameThread(function()
            local fn = verbs[verb]
            if not fn then log(string.format("CMD %d %s fail unknown verb", seq, verb)); return end
            local ok, a, b = pcall(fn, args or "", seq)
            if not ok then log(string.format("CMD %d %s fail lua error: %s", seq, verb, shortErr(a)))
            else log(string.format("CMD %d %s %s %s", seq, verb, a and "ok" or "fail", tostring(b or ""))) end
        end)
        return false
    end)
    log("ENGINE input mode armed: polling " .. CMD_FILE .. " every 250 ms")
end

-- F8 (and probably F9/F10) are bound by the game itself (F8 opens the Feedback panel), so the teleports use Ctrl+Shift+Z/X/C/V/B
local FKEYS = { Key.Z, Key.X, Key.C, Key.V, Key.B }
for n, k in ipairs(FKEYS) do
    RegisterKeyBind(k, { ModifierKey.CONTROL, ModifierKey.SHIFT }, function() teleportTo(n) end)
end
RegisterKeyBind(Key.F11, { ModifierKey.CONTROL }, logState)
log("loaded; Ctrl+Shift+Z/X/C/V/B teleport, Ctrl+F11 state")
