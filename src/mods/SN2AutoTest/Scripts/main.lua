-- SN2AutoTest - OBSERVE-ONLY test helper (design 2026-11-18: every player action is simulated OS input from src/tools/autotest_driver.py).
-- Armed only when <mod>\run\active_plan.lua exists (written by the driver; renamed to active_plan.consumed.lua at once); otherwise one log line, no hooks.
-- Logs:   [SN2AutoTest] WORLD <name>   on every map load,  PAWN possessed (+ spawn location),  STATE ... on Ctrl+F11
-- Keys:   Ctrl+Shift+Z/X/C/V/B = teleport to waypoint 1..5 of the plan (lifepod + offset, or the recorded spawn); Ctrl+F11 = log STATE.
-- Only non-observing action: if plan.worldLevel is set, UWELobbyStatics.SetWorldLevel 2 s after WORLD L_ClientLobby (test setup, no menu exists for it).
-- Also (observe-only reads): `BASE comp=.. owner=.. loc=.. rot=..` after every STATE and at SETTLED (what the pawn stands on). The old SETTLED pod
-- component dump (PODDUMP) was removed 2026-11-26 (it crashed UE4SS while the world streamed; recover: git show a3fa5e5:src/mods/SN2AutoTest/Scripts/main.lua).
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

local logBase, logOceanBody   -- defined below (observe-only: BASE line + ocean body line)
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
            end
        end)
        return
    end
    after(1, function() waitPawn(myGen) end)
end

-- TEST-ONLY object census (plan.lobbyCensus = {sec,...} seconds after the lobby WORLD line; plan.worldCensus = sec after PAWN possessed). One sample at a
-- time, never per frame. Purpose: find what the ~11.4k lobby SphereComponents are (GC-watchdog diagnosis, research/crashes/gc_watchdog_logs_2026-11-23.md, "GC-watchdog analysis").
-- Lines: CENSUS <tag> n=.. SphereComponent=.. BodySetup=.. StaticMeshComponent=.. PrimitiveComponent=.. took=..s ; CENSUS <tag> OWNERS/OUTERS/OUTERCLS k=v | ... ;
-- CENSUS <tag> SAMPLE i=.. comp=.. outer=.. owner=.. ownerClass=.. valid=..  ; CENSUS DONE lobby / CENSUS DONE world (the driver waits for these).
local function histTop(h, n)
    local arr = {}
    for k, v in pairs(h) do arr[#arr + 1] = { k = k, v = v } end
    table.sort(arr, function(a, b) if a.v ~= b.v then return a.v > b.v end return a.k < b.k end)
    local out = {}
    for i = 1, math.min(n, #arr) do out[#out + 1] = string.format("%s=%d", arr[i].k, arr[i].v) end
    return table.concat(out, " | ") .. string.format(" (distinct=%d)", #arr)
end
local chr9, chr10, chr13 = string.char(9), string.char(10), string.char(13)
local function fullOf(o)
    local ok, v = pcall(function() return o:GetFullName() end)
    return ok and (tostring(v):gsub("[" .. chr9 .. chr10 .. chr13 .. "]", " ")) or "?"
end
local function classOf(o)
    local ok, v = pcall(function() return o:GetClass():GetFName():ToString() end)
    return ok and tostring(v) or "?"
end
local function takeCensus(tag)
    local t0 = os.clock()
    local world = "?"
    pcall(function() world = getPC():GetWorld():GetFName():ToString() end)
    local counts, took = {}, {}
    local sph = nil
    for _, cls in ipairs({ "SphereComponent", "BodySetup", "StaticMeshComponent", "PrimitiveComponent" }) do
        local c0 = os.clock()
        local okF, t = pcall(FindAllOf, cls)
        if okF and type(t) == "table" then
            counts[cls] = #t
            if cls == "SphereComponent" then sph = t end
        else counts[cls] = -1 end
        took[cls] = os.clock() - c0
    end
    log(string.format("CENSUS %s world=%s SphereComponent=%d BodySetup=%d StaticMeshComponent=%d PrimitiveComponent=%d took=%.2fs (sphere %.2fs)",
        tag, world, counts.SphereComponent, counts.BodySetup, counts.StaticMeshComponent, counts.PrimitiveComponent, os.clock() - t0, took.SphereComponent))
    if not sph then return end
    local owners, outerCls, outers, noOwner, invalid = {}, {}, {}, 0, 0
    local nSamples, step = 0, 250
    for i, o in ipairs(sph) do
        local ok, err = pcall(function()
            if not isValid(o) then invalid = invalid + 1 end
            local own = o:GetOwner()
            local oc
            if isValid(own) then oc = classOf(own) else oc = "<none>"; noOwner = noOwner + 1 end
            owners[oc] = (owners[oc] or 0) + 1
            local out = o:GetOuter()
            local ocls = isValid(out) and classOf(out) or "<none>"
            outerCls[ocls] = (outerCls[ocls] or 0) + 1
            local lvl = "<none>"
            if isValid(own) then
                local lo = own:GetOuter()
                if isValid(lo) then lvl = classOf(lo) .. ":" .. nameOf(lo) end
            elseif isValid(out) then lvl = "(outer) " .. ocls .. ":" .. nameOf(out) end
            outers[lvl] = (outers[lvl] or 0) + 1
            if (i - 1) % step == 0 and nSamples < 50 then
                nSamples = nSamples + 1
                local ownFull = isValid(own) and fullOf(own) or "<none>"
                log(string.format("CENSUS %s SAMPLE i=%d comp=%s outer=%s owner=%s ownerClass=%s valid=%s", tag, i, fullOf(o),
                    isValid(out) and fullOf(out) or "<none>", ownFull, oc, tostring(isValid(o))))
            end
        end)
        if not ok then owners["<error>"] = (owners["<error>"] or 0) + 1 end
    end
    log(string.format("CENSUS %s OWNERS noOwner=%d invalid=%d %s", tag, noOwner, invalid, histTop(owners, 20)))
    log(string.format("CENSUS %s OUTERCLS %s", tag, histTop(outerCls, 20)))
    log(string.format("CENSUS %s OUTERS %s", tag, histTop(outers, 20)))
    log(string.format("CENSUS %s END total_took=%.2fs", tag, os.clock() - t0))
end
local censusGen = 0   -- bumped on every non-lobby ClientRestart so pending lobby samples are dropped
local function scheduleLobbyCensus()
    local list = plan.lobbyCensus
    if type(list) ~= "table" or #list == 0 then return end
    local myGen = censusGen
    log("CENSUS lobby scheduled at s=" .. table.concat(list, ","))
    for i, sec in ipairs(list) do
        after(sec, function()
            if myGen ~= censusGen then log("CENSUS lobby sample s=" .. sec .. " skipped (left the lobby)"); return end
            takeCensus(string.format("lobby_s%d", sec))
            if i == #list then log("CENSUS DONE lobby") end
        end)
    end
end
local worldCensusDone = false
local function scheduleWorldCensus()
    if type(plan.worldCensus) ~= "number" or worldCensusDone then return end
    worldCensusDone = true
    after(plan.worldCensus, function()
        takeCensus(string.format("world_s%d", plan.worldCensus))
        log("CENSUS DONE world")
    end)
end

RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(ctx)
    local ok, world = pcall(function() return ctx:get():GetWorld():GetFullName() end)
    if not ok or type(world) ~= "string" then return end
    local short = world:match("%.([^%.:/ ]+)$") or world
    log("WORLD " .. short)
    if short == "L_ClientLobby" then
        if not lobbySeen then
            lobbySeen = true
            scheduleLobbyCensus()
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
        censusGen = censusGen + 1
        spawnLoc = nil
        scheduleWorldCensus()
        waitPawn(gen)
    end
end)

local camOffset = nil   -- camera minus pawn location (cm), measured once for absolute ("at") waypoints
local function teleportTo(n)
    local pawn = getPawn()
    local wp = plan.waypoints[n]
    if not pawn or not wp then log(string.format("TELEPORT %d failed: pawn=%s wp=%s", n, tostring(pawn ~= nil), tostring(wp ~= nil))); return end
    local t
    if wp.at then
        -- absolute UE world position (cm) of the CAMERA: move the pawn by (at - camera offset). The offset (camera minus pawn) is measured
        -- once, before the first absolute teleport (right after a teleport the camera location is stale for a frame).
        if not camOffset then
            local okc, cl = pcall(function() return getPC().PlayerCameraManager:GetCameraLocation() end)
            local pl = pawn:K2_GetActorLocation()
            if okc and cl then camOffset = { X = cl.X - pl.X, Y = cl.Y - pl.Y, Z = cl.Z - pl.Z } else camOffset = { X = 0, Y = 0, Z = 0 } end
            log(string.format("CAMOFFSET camera-pawn=(%.1f,%.1f,%.1f)", camOffset.X, camOffset.Y, camOffset.Z))
        end
        t = { X = wp.at[1] - camOffset.X, Y = wp.at[2] - camOffset.Y, Z = wp.at[3] - camOffset.Z }
    elseif wp.offset then
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

-- ---------------------------------------------------------------- shared read helpers (observe-only; each in pcall)
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

-- TEST ONLY: horizontal field of view for the shots. Tries PlayerCameraManager.LockedFOV (overrides the view FOV), DefaultFOV, SetFOV(), and every
-- CameraComponent's FieldOfView; logs FOVSET with what worked and the resulting GetFOVAngle. Verb 'fov 91.49'.
function verbs.fov(args)
    local v = tonumber(args)
    if not v then return false, "usage: fov DEGREES" end
    local pc = getPC()
    if not pc then return false, "no pc" end
    local pcm = pc.PlayerCameraManager
    local worked = {}
    local before = "?"
    pcall(function() before = string.format("%.2f", pcm:GetFOVAngle()) end)
    if pcall(function() pcm.LockedFOV = v end) then worked[#worked + 1] = "LockedFOV" end
    if pcall(function() pcm.DefaultFOV = v end) then worked[#worked + 1] = "DefaultFOV" end
    if pcall(function() pcm:SetFOV(v) end) then worked[#worked + 1] = "SetFOV" end
    local nc = 0
    for _, c in ipairs(findAll("CameraComponent")) do
        if isValid(c) and pcall(function() c.FieldOfView = v end) then nc = nc + 1 end
    end
    if nc > 0 then worked[#worked + 1] = "CameraComponent x" .. nc end
    local after = "?"
    pcall(function() after = string.format("%.2f", pcm:GetFOVAngle()) end)
    log(string.format("FOVSET target=%.2f before=%s after=%s via=%s", v, before, after, table.concat(worked, ",")))
    return true, string.format("after=%s", after)
end

-- Per-shot camera log: camera location, camera rotation, control rotation, FOV angle. The driver calls it before every shot ('camlog LABEL').
function verbs.camlog(args)
    local pc = getPC()
    if not pc then return false, "no pc" end
    local pcm = pc.PlayerCameraManager
    local cl, cr, ctl, fv = "?", "?", "?", "?"
    pcall(function() local l = pcm:GetCameraLocation(); cl = string.format("%.1f,%.1f,%.1f", l.X, l.Y, l.Z) end)
    pcall(function() local r = pcm:GetCameraRotation(); cr = string.format("p%.2f,y%.2f", r.Pitch, r.Yaw) end)
    pcall(function() local r = pc:GetControlRotation(); ctl = string.format("p%.2f,y%.2f", r.Pitch, r.Yaw) end)
    pcall(function() fv = string.format("%.2f", pcm:GetFOVAngle()) end)
    log(string.format("CAMLOG %s camloc=(%s) camrot=%s ctlrot=%s fov=%s", tostring(args), cl, cr, ctl, fv))
    return true, ""
end
function verbs.frame()
    local n = -1
    pcall(function() n = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):GetFrameCount() end)
    log(string.format("FRAME %d", n))
    return true, tostring(n)
end
-- DIAGNOSTIC (test only, read-only): 'sn1probe LABEL' - are the SN1 terrain tile actors in the loaded world, are they visible, what is under the camera,
-- and how many shaders does the HUD still say it is compiling. One log line per item, every call in its own pcall. Plan waypoint fields
-- "probe": "sn1" (before the shots) and "probeAfter": "sn1" (after) call it.
function verbs.sn1probe(args)
    local label = tostring(args ~= "" and args or "probe")
    local function P(s) log("SN1PROBE " .. label .. " " .. s) end
    local function tagHas(a, want)
        local found = false
        pcall(function()
            local tags = a.Tags
            local n = tags:GetArrayNum()
            for i = 1, n do
                local okT, s = pcall(function() return tags[i]:ToString() end)
                if okT and s == want then found = true end
            end
        end)
        return found
    end
    -- 1. shader count (HUD text) + a couple of cvars
    local shaderTxt = "none"
    pcall(function()
        for _, cls in ipairs({ "CommonTextBlock", "TextBlock", "RichTextBlock" }) do
            for _, tb in ipairs(findAll(cls)) do
                local t = "?"
                pcall(function() t = tb:GetText():ToString() end)
                if type(t) == "string" and t:lower():find("shaders", 1, true) then
                    shaderTxt = string.format("%s|%s", nameOf(tb), (t:gsub("[\r\n\t]", " ")))
                    return
                end
            end
        end
    end)
    P("SHADERTEXT " .. shaderTxt)
    local ksl = nil
    pcall(function() ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end)
    for _, cv in ipairs({ "r.Nanite", "r.PSOPrecaching", "r.ShaderPipelineCache.Enabled" }) do
        local v = "?"
        pcall(function() v = tostring(ksl:GetConsoleVariableIntValue(cv)) end)
        P("CVAR " .. cv .. "=" .. v)
    end
    -- 2. tile actors
    local all, tagged = 0, 0
    local okA, errA = pcall(function()
        for _, a in ipairs(findAll("StaticMeshActor")) do
            all = all + 1
            local nm = nameOf(a)
            if tagHas(a, "SN1Terrain") or nm:find("spot1_tile", 1, true) then
                tagged = tagged + 1
                local loc, hid, mesh, mat, vis, hig, col, reg = "?", "?", "nil", "nil", "?", "?", "?", "?"
                local comp = nil
                pcall(function() comp = a.StaticMeshComponent end)
                pcall(function() local l = a:K2_GetActorLocation(); loc = string.format("%.0f,%.0f,%.0f", l.X, l.Y, l.Z) end)
                pcall(function() hid = tostring(a.bHidden) end)
                if isValid(comp) then
                    pcall(function() mesh = comp.StaticMesh:GetFullName() end)
                    pcall(function() mat = comp:GetMaterial(0):GetFullName() end)
                    pcall(function() vis = tostring(comp:IsVisible()) end)
                    pcall(function() hig = tostring(comp.bHiddenInGame) end)
                    pcall(function() col = tostring(comp:GetCollisionEnabled()) end)
                    pcall(function() reg = tostring(comp:IsRegistered()) end)
                else
                    mesh = "NOCOMP"
                end
                P(string.format("TILE %s loc=(%s) bHidden=%s mesh=%s mat=%s isVisible=%s hiddenInGame=%s collision=%s registered=%s", nm, loc, hid, mesh, mat, vis, hig, col, reg))
            end
        end
    end)
    if not okA then P("TILE scan error " .. shortErr(errA)) end
    P(string.format("COUNT staticMeshActors=%d tagged_or_named=%d", all, tagged))
    -- 3. line trace straight down 40 m from the camera
    pcall(function()
        local pc = getPC()
        local cl = pc.PlayerCameraManager:GetCameraLocation()
        local hit = {}
        local pawn = getPawn(pc)
        local hitAny = ksl:LineTraceSingle(pawn, { X = cl.X, Y = cl.Y, Z = cl.Z }, { X = cl.X, Y = cl.Y, Z = cl.Z - 4000 }, 0, true, {}, 0, hit, true,
            { R = 0, G = 0, B = 0, A = 0 }, { R = 0, G = 0, B = 0, A = 0 }, 0)
        local comp = nil
        pcall(function() comp = hit.Component:Get() end)
        if not isValid(comp) then pcall(function() comp = hit.HitObjectHandle.ReferenceObject:Get() end) end
        if not isValid(comp) then pcall(function() comp = hit.Component end) end
        if hitAny and isValid(comp) then
            local oname, z, dist, ip = "?", "?", "?", "?"
            pcall(function() oname = comp:GetOwner():GetFName():ToString() end)
            pcall(function() z = string.format("%.1f", hit.ImpactPoint.Z) end)
            pcall(function() ip = string.format("%.0f,%.0f,%.0f", hit.ImpactPoint.X, hit.ImpactPoint.Y, hit.ImpactPoint.Z) end)
            pcall(function() dist = string.format("%.1f", hit.Distance) end)
            P(string.format("TRACE cam=(%.0f,%.0f,%.0f) HIT owner=%s comp=%s impact=(%s) dist=%s", cl.X, cl.Y, cl.Z, oname, comp:GetFullName(), ip, dist))
        else
            P(string.format("TRACE cam=(%.0f,%.0f,%.0f) NOHIT ret=%s", cl.X, cl.Y, cl.Z, tostring(hitAny)))
        end
    end)
    return true, string.format("tiles=%d/%d shader=%s", tagged, all, shaderTxt)
end
-- ---------------------------------------------------------------- test-only oxygen refill + environment probe (2026-11-22)
-- Numeric GAS attributes of the player pawn: list of { set=<attribute set>, name=<property>, data=<FGameplayAttributeData>, cur=, base= }.
local function pawnAttrs()
    local out = {}
    local pawn = getPawn()
    if not pawn then return out, "no pawn" end
    local asc = nil
    for _, pn in ipairs({ "UWEAbilitySystemComponent", "AbilitySystemComponent" }) do
        if not isValid(asc) then pcall(function() asc = pawn[pn] end) end
    end
    if not isValid(asc) then pcall(function() asc = pawn:GetAbilitySystemComponent() end) end
    if not isValid(asc) then return out, "no ASC" end
    local sets = {}
    pcall(function() sets = toList(asc.SpawnedAttributes) end)
    for _, s in ipairs(sets) do
        if isValid(s) then
            pcall(function()
                s:GetClass():ForEachProperty(function(p)
                    local pname = "?"
                    pcall(function() pname = p:GetFName():ToString() end)
                    local okd, d = pcall(function() return s[pname] end)
                    if okd and type(d) == "userdata" then
                        local cur, base
                        pcall(function() cur = d.CurrentValue end)
                        pcall(function() base = d.BaseValue end)
                        if type(cur) == "number" then out[#out + 1] = { set = s, name = pname, data = d, cur = cur, base = base } end
                    end
                end)
            end)
        end
    end
    return out, "asc=" .. nameOf(asc) .. " sets=" .. #sets
end
local o2calls = 0
local o2cheatCalled = false
function verbs.o2fill(args)
    o2calls = o2calls + 1
    local verbose = o2calls <= 2
    local okAny, msgs = false, {}
    -- method 1: the game's own cheat manager function SN2CheatManager:Oxygen()
    local cm = nil
    pcall(function() local c = FindFirstOf("SN2CheatManager"); if isValid(c) then cm = c end end)
    if not cm then pcall(function() local c = getPC().CheatManager; if isValid(c) then cm = c end end) end
    if cm and o2cheatCalled then
        msgs[#msgs + 1] = "cheat=already toggled once (Oxygen() is a TOGGLE: HUD shows 'Oxygen cheat enabled/disabled')"
    elseif cm then
        o2cheatCalled = true
        local ok, err = pcall(function() cm:Oxygen() end)
        msgs[#msgs + 1] = "cheat=" .. (ok and "called" or shortErr(err))
        if ok then okAny = true end
    else
        msgs[#msgs + 1] = "cheat=no SN2CheatManager instance"
    end
    -- method 2: set the oxygen attribute's CurrentValue to its maximum
    local attrs, why = pawnAttrs()
    local oxy, maxv = nil, nil
    for _, a in ipairs(attrs) do
        local l = a.name:lower()
        if l == "maxoxygen" then maxv = a elseif l == "oxygen" then oxy = a end
        if verbose then log(string.format("O2ATTR %s set=%s cur=%s base=%s", a.name, nameOf(a.set), tostring(a.cur), tostring(a.base))) end
    end
    if oxy then
        local target = (maxv and maxv.cur) or oxy.base or oxy.cur
        local before = oxy.cur
        local ok, err = pcall(function() oxy.data.CurrentValue = target; oxy.data.BaseValue = target end)
        local after = nil
        pcall(function() after = oxy.data.CurrentValue end)
        msgs[#msgs + 1] = string.format("attr=%s %s %s->%s target=%s", oxy.name, ok and "set" or shortErr(err), tostring(before), tostring(after), tostring(target))
        if ok then okAny = true end
    else
        msgs[#msgs + 1] = "attr=no oxygen attribute (" .. tostring(why) .. ", numeric attrs=" .. #attrs .. ")"
    end
    local m = table.concat(msgs, " | ")
    if verbose or not okAny then log("O2FILL " .. m) end
    return okAny, m
end
-- fallback for the driver: back to the pod start (surface air)
function verbs.podtp()
    local pawn = getPawn()
    local t = spawnLoc
    if not pawn or not t then return false, "no pawn or spawn" end
    local ok, err = pcall(function() pawn:K2_SetActorLocation({ X = t.X, Y = t.Y, Z = t.Z }, false, {}, true) end)
    return ok, ok and "ok" or shortErr(err)
end
-- Read-only: biome regions, water light settings, height fog, post-process volumes, attributes. Label = args.
function verbs.envprobe(args)
    local label = tostring(args ~= "" and args or "env")
    local function P(s) log("ENVPROBE " .. label .. " " .. s) end
    local function rd(o, names)
        local parts = {}
        for _, n in ipairs(names) do
            local v = "?"
            pcall(function()
                local x = o[n]
                if type(x) == "userdata" then
                    local r = nil
                    pcall(function() r = string.format("(%.3g,%.3g,%.3g,%.3g)", x.R, x.G, x.B, x.A) end)
                    if not r then pcall(function() r = string.format("(%.3g,%.3g,%.3g)", x.X, x.Y, x.Z) end) end
                    v = r or str(x)
                else v = tostring(x) end
            end)
            parts[#parts + 1] = n .. "=" .. v
        end
        return table.concat(parts, " ")
    end
    local pc = getPC()
    local pawn = getPawn(pc)
    local cl = nil
    pcall(function() cl = pc.PlayerCameraManager:GetCameraLocation() end)
    if cl then P(string.format("CAM (%.0f,%.0f,%.0f)", cl.X, cl.Y, cl.Z)) end
    if pawn then pcall(function() P("PHYSVOL " .. volStr(pawn:GetPhysicsVolume())) end) end
    -- biome regions
    local nreg = 0
    for _, cn in ipairs({ "BP_UWEOceanBiomeRegionActor_C", "BP_UWEWaterBiomeRegionActor_C" }) do
        for _, a in ipairs(findAll(cn)) do
            nreg = nreg + 1
            local loc, ext, inside = "?", "?", "?"
            pcall(function() loc = fmtV(a:K2_GetActorLocation()) end)
            pcall(function()
                local o, ex = {}, {}
                a:GetActorBounds(false, o, ex)
                ext = fmtV(ex)
                if cl then inside = tostring(math.abs(cl.X - o.X) <= ex.X and math.abs(cl.Y - o.Y) <= ex.Y and math.abs(cl.Z - o.Z) <= ex.Z) end
            end)
            local da = "?"
            pcall(function() da = str(a.BiomeData) end)
            P(string.format("REGION %s class=%s loc=(%s) boundsExtent=(%s) cameraInBounds=%s bIsOcean=%s BiomeData=%s", nameOf(a), cn, loc, ext, inside, tostring(try(function() return a.bIsOcean end)), da))
            pcall(function()
                local bvc = a.BiomeVolumeComponent
                local wls = bvc.WaterLightSettings
                P("REGION " .. nameOf(a) .. " WLS " .. rd(wls, { "WaterFogDistance", "WaterFogThickness", "WaterFogBaseThickness", "WaterFogOpacityWeight", "BiomeExtinction", "BiomeExtinctionSkylight", "BiomeNeutralColor", "BiomeAlbedo", "BiomeNeutralStrengthNear", "BiomeNeutralStrengthFar", "BiomeBlendDistance" }))
            end)
        end
    end
    P("REGIONS " .. nreg)
    pcall(function()
        for _, oc in ipairs(findAll("BP_Ocean_C")) do
            P("OCEAN " .. nameOf(oc) .. " " .. rd(oc, { "WaterLinePPMThreshold", "PPUnderwaterBlur" }))
            pcall(function() P("OCEAN WaterLightingSettings " .. rd(oc.WaterLightingSettings, { "WaterFogDistance", "WaterFogThickness", "WaterFogBaseThickness", "WaterFogOpacityWeight", "BiomeExtinction", "BiomeAlbedo" })) end)
        end
    end)
    -- height fog components
    local nf = 0
    for _, f in ipairs(findAll("ExponentialHeightFogComponent")) do
        nf = nf + 1
        local own = "?"
        pcall(function() own = f:GetOwner():GetFName():ToString() end)
        P(string.format("HEIGHTFOG owner=%s %s", own, rd(f, { "FogDensity", "FogHeightFalloff", "StartDistance", "FogMaxOpacity", "FogCutoffDistance", "bEnableVolumetricFog", "VolumetricFogDistance" })))
    end
    P("HEIGHTFOG count " .. nf)
    local npp, nunb = 0, 0
    for _, v in ipairs(findAll("PostProcessVolume")) do
        npp = npp + 1
        if try(function() return v.bUnbound end) == true then nunb = nunb + 1 end
    end
    P(string.format("POSTPROCESSVOLUMES count=%d unbound=%d", npp, nunb))
    local fogs = findAll("BP_Fog_Sphere_C")
    P("FOGSPHERES count=" .. #fogs)
    -- numeric attributes of the pawn (to find oxygen)
    local attrs, why = pawnAttrs()
    P("ATTRS " .. tostring(why) .. " numeric=" .. #attrs)
    for i, a in ipairs(attrs) do
        if i > 80 then break end
        P(string.format("ATTR %s.%s cur=%s base=%s", nameOf(a.set), a.name, tostring(a.cur), tostring(a.base)))
    end
    return true, string.format("regions=%d fog=%d pp=%d attrs=%d", nreg, nf, npp, #attrs)
end
-- watersys <label>: read-only (2026-11-26, brownwater diagnostic). Biome tracker subsystem, biome map components, MPC values, sky, volume trackers.
-- Queries specific classes only (never sweeps all objects).
function verbs.watersys(args)
    local label = tostring(args ~= "" and args or "ws")
    local function P(s) log("WATERSYS " .. label .. " " .. s) end
    local function rd1(x)
        if type(x) ~= "userdata" then return tostring(x) end
        local r
        pcall(function() r = string.format("(%.4g,%.4g,%.4g,%.4g)", x.R, x.G, x.B, x.A) end)
        if not r then pcall(function() r = string.format("(%.4g,%.4g,%.4g,%.4g)", x.X, x.Y, x.Z, x.W) end) end
        if not r then pcall(function() r = string.format("(%.4g,%.4g,%.4g)", x.X, x.Y, x.Z) end) end
        return r or str(x)
    end
    local pc = getPC()
    local world = nil
    pcall(function() world = pc:GetWorld() end)
    pcall(function() P("WORLD " .. str(world:GetFullName())) end)
    local nsub = 0
    local mpcSeen = {}
    for _, s in ipairs(findAll("UWEBiomeTrackerSubsystem")) do
        nsub = nsub + 1
        P("SUBSYS " .. nameOf(s))
        pcall(function() P("SUBSYS SkyActor=" .. str(s.SkyActor:GetFullName())) end)
        local vols = nil
        pcall(function() vols = s.Volumes end)
        local n = 0
        pcall(function() n = vols:GetArrayNum() end)
        P("SUBSYS Volumes num=" .. tostring(n))
        for i = 1, math.min(n, 60) do
            pcall(function()
                local v = vols[i]
                local own = "?"
                pcall(function() own = v:GetOwner():GetFName():ToString() end)
                local wls = v.WaterLightSettings
                local loc = "?"
                pcall(function() loc = fmtV(v:K2_GetComponentLocation()) end)
                P(string.format("VOL[%d] %s owner=%s loc=(%s) fogDist=%.5g albedo=%s", i, nameOf(v), own, loc, wls.WaterFogDistance, rd1(wls.BiomeAlbedo)))
            end)
        end
        local mpc = nil
        pcall(function() mpc = s.BiomeMaterialParameterCollection end)
        P("SUBSYS BiomeMPC=" .. (isValid(mpc) and str(mpc:GetFullName()) or "NULL"))
        pcall(function() P("SUBSYS BiomeNiagaraPC=" .. str(s.BiomeNiagaraParameterCollection:GetFullName())) end)
        if isValid(mpc) then mpcSeen[#mpcSeen + 1] = mpc end
    end
    P("SUBSYS count=" .. nsub)
    -- MPC parameter names + live values
    local kml = nil
    pcall(function() kml = StaticFindObject("/Script/Engine.Default__KismetMaterialLibrary") end)
    for _, mpc in ipairs(mpcSeen) do
        pcall(function()
            local sp = mpc.ScalarParameters
            local n = sp:GetArrayNum()
            P("MPC scalar params=" .. n)
            for i = 1, n do
                local nm = sp[i].ParameterName
                local def = sp[i].DefaultValue
                local live = "?"
                pcall(function() live = tostring(kml:GetScalarParameterValue(world, mpc, nm)) end)
                P(string.format("MPC S %s default=%s live=%s", str(nm), tostring(def), live))
            end
        end)
        pcall(function()
            local vp = mpc.VectorParameters
            local n = vp:GetArrayNum()
            P("MPC vector params=" .. n)
            for i = 1, n do
                local nm = vp[i].ParameterName
                local live = "?"
                pcall(function() live = rd1(kml:GetVectorParameterValue(world, mpc, nm)) end)
                P(string.format("MPC V %s default=%s live=%s", str(nm), rd1(vp[i].DefaultValue), live))
            end
        end)
    end
    -- biome map components
    local nbm = 0
    for _, c in ipairs(findAll("UWEBiomeMapComponent")) do
        nbm = nbm + 1
        local own = "?"
        pcall(function() own = c:GetOwner():GetFName():ToString() end)
        P(string.format("BIOMEMAP %s owner=%s CaptureRadius=%s W2B=%s", nameOf(c), own, tostring(try(function() return c.CaptureRadius end)), try(function() return rd1(c.WorldToBiomeMapScaleAndOffset) end)))
        pcall(function() P("BIOMEMAP loc=" .. fmtV(c:K2_GetComponentLocation()) .. " scale=" .. fmtV(c:K2_GetComponentScale())) end)
        pcall(function()
            local rt = c.RenderTarget
            if isValid(rt) then P(string.format("BIOMEMAP RT=%s size=%sx%s", str(rt:GetFullName()), tostring(rt.SizeX), tostring(rt.SizeY)))
            else P("BIOMEMAP RT=NULL") end
        end)
        pcall(function() local d = c.DefaultVolumeSettings; P(string.format("BIOMEMAP DefaultVolumeSettings albedo=%s density=%s", rd1(d.Albedo), tostring(d.Density))) end)
    end
    P("BIOMEMAP count=" .. nbm)
    -- sky actor basics
    for _, a in ipairs(findAll("BP_UWESky_C")) do
        P(string.format("SKY %s %s", nameOf(a), (function() local r = {}
            for _, k in ipairs({ "TimeOfDay", "NormalizedDaylight", "TransitionAlpha" }) do r[#r + 1] = k .. "=" .. tostring(try(function() return a[k] end)) end
            return table.concat(r, " ") end)()))
        pcall(function() P("SKY Sun intensity=" .. tostring(a.SunLightComponent.Intensity) .. " color=" .. rd1(a.SunLightComponent.LightColor) .. " rot=" .. fmtV(a.SunLightComponent:K2_GetComponentRotation())) end)
    end
    -- all PostProcessComponents (owners + enabled + priority)
    local npc = 0
    for _, c in ipairs(findAll("PostProcessComponent")) do
        npc = npc + 1
        local own = "?"
        pcall(function() own = c:GetOwner():GetFName():ToString() end)
        P(string.format("PPC %s owner=%s enabled=%s unbound=%s priority=%s blendw=%s", nameOf(c), own, tostring(try(function() return c.bEnabled end)), tostring(try(function() return c.bUnbound end)), tostring(try(function() return c.Priority end)), tostring(try(function() return c.BlendWeight end))))
    end
    P("PPC count=" .. npc)
    -- level / ocean actors by class
    for _, cn in ipairs({ "BP_Ocean_C", "UWEWaterBodyOcean" }) do
        for _, a in ipairs(findAll(cn)) do
            local loc, sc = "?", "?"
            pcall(function() loc = fmtV(a:K2_GetActorLocation()) end)
            pcall(function() sc = fmtV(a:GetActorScale3D()) end)
            P(string.format("OCEANACTOR %s class=%s loc=(%s) scale=(%s) level=%s", nameOf(a), cn, loc, sc, tostring(try(function() return a:GetLevel():GetFullName() end))))
        end
    end
    pcall(function() verbs.envprobe(label) end)
    return true, "watersys done"
end
-- ppwatch <label>: TEMPORARY diagnostic (2026-11-26, brownwater PP BlendWeight question). Never calls the VolumeTracker query (it hung the game
-- thread). Logs PPW lines: the pawn location, region component properties of the ocean region and of the region box that contains the pawn, and then
-- a time series of every UWEBiomePostProcessComponent BlendWeight (count > 0, max, ocean, the region containing the pawn).
function verbs.ppwatch(args)
    local label = tostring(args ~= "" and args or "pw")
    local function P(s) log("PPW " .. label .. " " .. s) end
    local pawn = getPawn(getPC())
    local ploc = nil
    pcall(function() ploc = pawn:K2_GetActorLocation() end)
    P("pawn=" .. fmtV(ploc))
    local function inside(a)
        local ok, r = pcall(function()
            local c = a.WaterBoxVolumeComponent
            local e = c.BoxExtent
            local o = c:K2_GetComponentLocation()
            local s = c:K2_GetComponentScale()
            return math.abs(ploc.X - o.X) <= e.X * s.X and math.abs(ploc.Y - o.Y) <= e.Y * s.Y and math.abs(ploc.Z - o.Z) <= e.Z * s.Z
        end)
        return ok and r == true
    end
    local function dumpRegion(a)
        local nm = nameOf(a)
        for _, k in ipairs({ "BiomeRegionVolumeType", "BiomeRegionType", "bIsOcean", "bHasWaterSurface", "bUseDistanceFieldMask", "bMaskOceanSurface" }) do
            P(nm .. " ACTOR " .. k .. "=" .. tostring(try(function() return a[k] end)))
        end
        pcall(function() P(nm .. " ACTOR loc=" .. fmtV(a:K2_GetActorLocation()) .. " scale=" .. fmtV(a:GetActorScale3D())) end)
        for _, cn in ipairs({ "WaterBoxVolumeComponent", "WaterBrushVolumeComponent" }) do
            local c = nil
            pcall(function() c = a[cn] end)
            if isValid(c) then
                P(string.format("%s %s class=%s", nm, cn, tostring(try(function() return c:GetClass():GetFName():ToString() end))))
                P(string.format("%s %s BoxExtent=%s scale=%s loc=%s", nm, cn, fmtV(try(function() return c.BoxExtent end)), fmtV(try(function() return c:K2_GetComponentScale() end)), fmtV(try(function() return c:K2_GetComponentLocation() end))))
                P(string.format("%s %s VolumeType=%s Priority=%s", nm, cn, tostring(try(function() return c.VolumeData.VolumeType end)), tostring(try(function() return c.VolumeData.Priority end))))
                P(string.format("%s %s profile=%s collEnabled=%s genOverlap=%s objType=%s visible=%s regd=%s", nm, cn,
                    str(try(function() return c.BodyInstance.CollisionProfileName end)), tostring(try(function() return c:GetCollisionEnabled() end)),
                    tostring(try(function() return c:GetGenerateOverlapEvents() end)), tostring(try(function() return c:GetCollisionObjectType() end)),
                    tostring(try(function() return c:IsVisible() end)), tostring(try(function() return c:IsRegistered() end))))
            else
                P(nm .. " " .. cn .. " = nil")
            end
        end
        pcall(function() P(nm .. " BiomeVolumeComponent bAutoActivate/active=" .. tostring(a.BiomeVolumeComponent:IsActive()) .. " visible=" .. tostring(a.BiomeVolumeComponent:IsVisible())) end)
        pcall(function() P(nm .. " PP active=" .. tostring(a.PostProcessComponent:IsActive()) .. " enabled=" .. tostring(a.PostProcessComponent.bEnabled) .. " blendRadius=" .. tostring(a.PostProcessComponent.BlendRadius) .. " blendw=" .. tostring(a.PostProcessComponent.BlendWeight)) end)
    end
    local regs = {}
    for _, cn in ipairs({ "BP_UWEOceanBiomeRegionActor_C", "BP_UWEWaterBiomeRegionActor_C" }) do
        for _, a in ipairs(findAll(cn)) do regs[#regs + 1] = a end
    end
    local mine, nIn = nil, 0
    for _, a in ipairs(regs) do
        local n = nameOf(a)
        if n:find("^BP_UWEOceanBiomeRegionActor") then dumpRegion(a) end
        if n:find("^BP_UWEWaterBiomeRegionActor") and ploc and inside(a) then
            nIn = nIn + 1
            if not mine then mine = a; dumpRegion(a) end
            P("INSIDE " .. n)
        end
    end
    P("regions=" .. #regs .. " containingPawn=" .. nIn)
    local t0 = os.clock()
    local function sample(tag)
        local n, npos, mx, oc, mine_w = 0, 0, 0, "?", "?"
        for _, c in ipairs(findAll("UWEBiomePostProcessComponent")) do
            n = n + 1
            local w = tonumber(try(function() return c.BlendWeight end)) or 0
            if w > 0 then npos = npos + 1 end
            if w > mx then mx = w end
            local own = ""
            pcall(function() own = c:GetOwner():GetFName():ToString() end)
            if own:find("^BP_UWEOceanBiomeRegionActor_C_1$") then oc = tostring(w) end
            if mine and own == nameOf(mine) then mine_w = tostring(w) end
        end
        local pl = "?"
        pcall(function() pl = fmtV(getPawn(getPC()):K2_GetActorLocation()) end)
        P(string.format("SERIES %s t=%.1f pawn=%s n=%d weightPositive=%d max=%.3f ocean=%s containing=%s", tag, os.clock() - t0, pl, n, npos, mx, oc, mine_w))
    end
    sample("t0")
    for _, d in ipairs({ 1, 2, 4, 8, 15, 25 }) do
        after(d, function() sample("d" .. d) end)
    end
    return true, "ppwatch armed"
end
-- uwprobe <label>: TEMPORARY read-only diagnostic (2026-11-27, investigator-water: why does the view under water render like dry land).
-- Same lines in L_Main and L_SN2World (diff the UWPROBE lines). Reads only: engine WaterSubsystem camera state, ocean water body component,
-- water zones, ocean/biome region mesh components, sky/time of day/weather, lights, fog, post process components, a few cvars.
-- Never touches the VolumeTracker query. Each read is in its own pcall.
function verbs.uwprobe(args)
    local label = tostring(args ~= "" and args or "uw")
    local function P(s) log("UWPROBE " .. label .. " " .. s) end
    local function f1(x)
        local t = type(x)
        if t == "nil" then return "nil" end
        if t == "number" then return string.format("%.6g", x) end
        if t == "boolean" or t == "string" then return tostring(x) end
        if t == "userdata" then
            local r
            pcall(function() r = string.format("(%.5g,%.5g,%.5g,%.5g)", x.R, x.G, x.B, x.A) end)
            if r then return r end
            pcall(function() r = string.format("(%.5g,%.5g,%.5g)", x.X, x.Y, x.Z) end)
            if r then return r end
            pcall(function() r = string.format("(P%.4g,Y%.4g,R%.4g)", x.Pitch, x.Yaw, x.Roll) end)
            if r then return r end
            return str(x)
        end
        return tostring(x)
    end
    local function rd(o, names)
        local parts = {}
        for _, n in ipairs(names) do
            local v = "?"
            local ok, x = pcall(function() return o[n] end)
            if ok then v = f1(x) end
            parts[#parts + 1] = n .. "=" .. v
        end
        return table.concat(parts, " ")
    end
    local function call0(o, fn, ...)
        local a = { ... }
        local ok, r = pcall(function() return o[fn](o, table.unpack(a)) end)
        if ok then return f1(r) end
        return "ERR"
    end
    local function matParams(m, tag)
        if not isValid(m) then return end
        pcall(function() P(tag .. " MATERIAL " .. str(m:GetFullName())) end)
        pcall(function()
            local sp = m.ScalarParameterValues
            local n = sp:GetArrayNum()
            local parts = {}
            for i = 1, math.min(n, 60) do
                pcall(function() parts[#parts + 1] = str(sp[i].ParameterInfo.Name) .. "=" .. f1(sp[i].ParameterValue) end)
            end
            P(tag .. " MAT scalars(" .. n .. ") " .. table.concat(parts, " "))
        end)
        pcall(function()
            local vp = m.VectorParameterValues
            local n = vp:GetArrayNum()
            local parts = {}
            for i = 1, math.min(n, 40) do
                pcall(function() parts[#parts + 1] = str(vp[i].ParameterInfo.Name) .. "=" .. f1(vp[i].ParameterValue) end)
            end
            P(tag .. " MAT vectors(" .. n .. ") " .. table.concat(parts, " "))
        end)
        pcall(function() P(tag .. " MAT parent=" .. str(m.Parent:GetFullName())) end)
    end
    local pc = getPC()
    local world = nil
    pcall(function() world = pc:GetWorld() end)
    pcall(function() P("WORLD " .. str(world:GetFullName())) end)
    local cl = nil
    pcall(function() cl = pc.PlayerCameraManager:GetCameraLocation() end)
    if cl then P(string.format("CAM (%.1f,%.1f,%.1f)", cl.X, cl.Y, cl.Z)) end
    -- 1. engine water subsystem: camera underwater state (the engine's underwater post process is driven by this)
    for _, s in ipairs(findAll("WaterSubsystem")) do
        P("WATERSUBSYS " .. nameOf(s) .. " class=" .. str(try(function() return s:GetClass():GetFName():ToString() end)))
        for _, fn in ipairs({ "GetCameraUnderwaterDepth", "IsUnderwaterPostProcessEnabled", "IsWaterRenderingEnabled", "GetOceanBaseHeight", "GetOceanFloodHeight", "GetOceanTotalHeight", "GetWaterTimeSeconds" }) do
            P("WATERSUBSYS " .. fn .. "=" .. call0(s, fn))
        end
        pcall(function() P("WATERSUBSYS MPC=" .. str(s.MaterialParameterCollection:GetFullName())) end)
    end
    local ksl = nil
    pcall(function() ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end)
    if ksl then
        local parts = {}
        for _, cv in ipairs({ "r.Water.Enabled", "r.Water.EnableUnderwaterPostProcess", "r.Water.WaterMesh.EnableRendering", "r.Water.EnableShallowWaterSimulation", "r.Water.WaterInfo.RenderMethod", "r.VolumetricFog", "r.Lumen.DiffuseIndirect.Allow", "r.SkyLight.RealTimeReflectionCapture", "r.DefaultFeature.AutoExposure", "r.EyeAdaptationQuality" }) do
            local ok, v = pcall(function() return ksl:GetConsoleVariableIntValue(cv) end)
            parts[#parts + 1] = cv .. "=" .. (ok and tostring(v) or "?")
        end
        P("CVARS " .. table.concat(parts, " "))
    end
    -- 2. water body ocean component(s)
    for _, b in ipairs(findAll("WaterBodyOceanComponent")) do
        local own = "?"
        pcall(function() own = b:GetOwner():GetFName():ToString() end)
        P("OCEANBODY " .. nameOf(b) .. " owner=" .. own)
        P("OCEANBODY " .. rd(b, { "CollisionExtents", "CollisionHeightOffset", "OceanExtents", "HeightOffset", "bCenterOnWaterZone", "WaterBodyIndex", "OverlapMaterialPriority", "bAffectsLandscape", "ShapeDilation", "FixedWaterDepth", "TargetWaveMaskDepth", "MaxWaveHeightOffset", "WaterLOD0MaterialDistance", "bHiddenInGame" }))
        P("OCEANBODY ShouldRender=" .. call0(b, "ShouldRender") .. " IsVisible=" .. call0(b, "IsVisible") .. " IsRegistered=" .. call0(b, "IsRegistered") .. " IsActive=" .. call0(b, "IsActive"))
        for _, k in ipairs({ "UnderwaterPostProcessMaterial", "WaterMaterial", "WaterStaticMeshMaterial", "WaterInfoMaterial", "WaterHLODMaterial", "UnderwaterPostProcessMID", "WaterMID", "WaterStaticMeshMID", "OwningWaterZone", "WaterZoneOverride", "WaterMeshOverride" }) do
            local ok, v = pcall(function() return b[k] end)
            local s = "?"
            if ok then
                if type(v) == "userdata" then
                    local okv, valid = pcall(function() return v:IsValid() end)
                    if okv and valid then s = str(v:GetFullName()) elseif okv then s = "INVALID/NULL" else s = f1(v) end
                else s = f1(v) end
            end
            P("OCEANBODY " .. k .. "=" .. s)
        end
        pcall(function()
            local u = b.UnderwaterPostProcessSettings
            P("OCEANBODY UPPS " .. rd(u, { "bEnabled", "Priority", "BlendRadius", "BlendWeight" }) .. " mat=" .. str(try(function() return u.UnderwaterPostProcessMaterial:GetFullName() end)))
        end)
        pcall(function()
            local comps = toList(b:GetCollisionComponents(false))
            P("OCEANBODY collisionComponents=" .. #comps)
            for i, c in ipairs(comps) do
                if i > 8 then break end
                P(string.format("OCEANBODY COLL[%d] %s class=%s collEnabled=%s objType=%s profile=%s registered=%s loc=(%s) scale=(%s) extent=%s", i, nameOf(c),
                    str(try(function() return c:GetClass():GetFName():ToString() end)), call0(c, "GetCollisionEnabled"), call0(c, "GetCollisionObjectType"),
                    str(try(function() return c.BodyInstance.CollisionProfileName end)), call0(c, "IsRegistered"),
                    fmtV(try(function() return c:K2_GetComponentLocation() end)), fmtV(try(function() return c:K2_GetComponentScale() end)), f1(try(function() return c.BoxExtent end))))
            end
        end)
        pcall(function() P("OCEANBODY CollisionBoxes=" .. tostring(b.CollisionBoxes:GetArrayNum()) .. " CollisionHullSets=" .. tostring(b.CollisionHullSets:GetArrayNum())) end)
        local mids = {}
        for _, k in ipairs({ "UnderwaterPostProcessMID", "WaterMID", "WaterStaticMeshMID" }) do
            pcall(function() local m = b[k]; if isValid(m) then matParams(m, "OCEANBODY " .. k) end end)
        end
    end
    -- 3. water zones, water body actors
    for _, z in ipairs(findAll("WaterZone")) do
        P("WATERZONE " .. nameOf(z) .. " " .. rd(z, { "ZoneExtent", "WaterZoneIndex", "OverlapPriority", "CaptureZOffset", "RenderTargetResolution" }) .. " loc=" .. fmtV(try(function() return z:K2_GetActorLocation() end)) .. " owned=" .. tostring(try(function() return z.OwnedWaterBodies:GetArrayNum() end)))
        pcall(function() P("WATERZONE WaterMesh visible=" .. call0(z.WaterMesh, "IsVisible") .. " registered=" .. call0(z.WaterMesh, "IsRegistered")) end)
    end
    for _, a in ipairs(findAll("BP_Ocean_C")) do
        P("OCEANACTOR " .. nameOf(a) .. " " .. rd(a, { "BodySize", "WaterLinePPMThreshold", "UnderwaterStateUpdateRate", "bDirty", "WaterBodyType", "WaterBodyIndex" }))
        pcall(function() P("OCEANACTOR PPUnderwaterBlur " .. rd(a.PPUnderwaterBlur, { "bEnabled", "bUnbound", "Priority", "BlendWeight", "BlendRadius" }) .. " active=" .. call0(a.PPUnderwaterBlur, "IsActive")) end)
        pcall(function() P("OCEANACTOR WaterBodyComponent=" .. str(a.WaterBodyComponent:GetFullName())) end)
        pcall(function() P("OCEANACTOR WaterInfoMeshComponent visible=" .. call0(a.WaterInfoMeshComponent, "IsVisible") .. " registered=" .. call0(a.WaterInfoMeshComponent, "IsRegistered")) end)
    end
    -- 4. ocean + camera-containing biome region mesh components
    local function regionInfo(a)
        local nm = nameOf(a)
        P("REGION " .. nm .. " " .. rd(a, { "BiomeRegionType", "BiomeRegionVolumeType", "bIsOcean", "bHasWaterSurface", "bMaskOceanSurface", "bUseDistanceFieldMask", "bHidden" }))
        for _, cn in ipairs({ "WaterStaticMeshComponent", "WaterSurfaceMeshComponent", "BiomeVolumeComponent", "PostProcessComponent", "WaterBoxVolumeComponent", "WaterBrushVolumeComponent" }) do
            local c = nil
            pcall(function() c = a[cn] end)
            if isValid(c) then
                local line = string.format("REGION %s %s class=%s visible=%s registered=%s active=%s", nm, cn, str(try(function() return c:GetClass():GetFName():ToString() end)), call0(c, "IsVisible"), call0(c, "IsRegistered"), call0(c, "IsActive"))
                if cn == "WaterStaticMeshComponent" or cn == "WaterSurfaceMeshComponent" then
                    line = line .. " " .. rd(c, { "bHiddenInGame", "bVisible", "bRenderInMainPass", "bRenderInDepthPass", "bCastDynamicShadow", "bAffectDistanceFieldLighting", "CastShadow", "bUseAsOccluder", "LDMaxDrawDistance", "TranslucencySortPriority" })
                    line = line .. " mesh=" .. str(try(function() return c.StaticMesh:GetFullName() end)) .. " nMats=" .. call0(c, "GetNumMaterials")
                    line = line .. " scale=(" .. fmtV(try(function() return c:K2_GetComponentScale() end)) .. ") loc=(" .. fmtV(try(function() return c:K2_GetComponentLocation() end)) .. ")"
                end
                P(line)
                if cn == "WaterStaticMeshComponent" or cn == "WaterSurfaceMeshComponent" then
                    pcall(function()
                        local n = c:GetNumMaterials()
                        for i = 0, math.min(n, 3) - 1 do
                            local m = c:GetMaterial(i)
                            if isValid(m) then matParams(m, "REGION " .. nm .. " " .. cn .. "[" .. i .. "]") end
                        end
                    end)
                end
                if cn == "PostProcessComponent" then
                    P(string.format("REGION %s PP %s", nm, rd(c, { "bEnabled", "bUnbound", "Priority", "BlendWeight", "BlendRadius" })))
                end
            else
                P("REGION " .. nm .. " " .. cn .. " = nil")
            end
        end
    end
    local seenReg = {}
    for _, a in ipairs(findAll("BP_UWEOceanBiomeRegionActor_C")) do
        local n = nameOf(a)
        if not seenReg[n] then seenReg[n] = true; regionInfo(a) end
    end
    local nWater = 0
    for _, a in ipairs(findAll("BP_UWEWaterBiomeRegionActor_C")) do
        nWater = nWater + 1
        local n = nameOf(a)
        if not seenReg[n] and not n:find("^BP_UWEOcean") and not n:find("^WaterVolumeComponent_") then
            -- only the first plain water region (placed SN1 box) and any with "CAT" are dumped in full
            if nWater <= 1 then seenReg[n] = true; regionInfo(a) end
        end
    end
    P("REGION count water=" .. nWater)
    -- 5. sky: time of day, weather, day sequence
    for _, a in ipairs(findAll("BP_UWESky_C")) do
        P("SKY " .. nameOf(a) .. " " .. rd(a, { "TimeOfDay", "NormalizedDaylight", "TransitionAlpha" }))
        pcall(function() P("SKY SkyPayloads=" .. tostring(a.SkyPayloads:GetArrayNum()) .. " AllDaySequenceCollectionAssets=" .. tostring(a.AllDaySequenceCollectionAssets:GetArrayNum())) end)
        pcall(function() P("SKY PostProcessComponentSky " .. rd(a.PostProcessComponentSky, { "bEnabled", "bUnbound", "Priority", "BlendWeight" }) .. " active=" .. call0(a.PostProcessComponentSky, "IsActive")) end)
        pcall(function() P("SKY SunLightMaterialLightFunction=" .. str(a.SunLightMaterialLightFunction:GetFullName())) end)
        pcall(function() matParams(a.SunLightMaterialLightFunction, "SKY SunLF") end)
        pcall(function() P("SKY MoonLightMaterialLightFunction=" .. str(a.MoonLightMaterialLightFunction:GetFullName())) end)
        pcall(function() P("SKY DaySequenceModifier " .. rd(a.DaySequenceModifierComponent, { "bEnabled", "bIsEnabled", "DayNightCycleTime", "bIgnoreBias", "BlendWeight", "Priority", "bHasActiveSequence" })) end)
        pcall(function() local c = a.PrimaryCelestialBody:Get(); P("SKY PrimaryCelestialBody " .. rd(c, { "OrbitPeriodSeconds", "OrbitPhaseSeconds", "AxialRotationPeriodSeconds", "AxialTilt" })) end)
    end
    for _, c in ipairs(findAll("UWETimeOfDayComponent")) do
        P("TIMEOFDAY " .. nameOf(c) .. " " .. rd(c, { "InitialNumGameDays", "WorldTimeAtInitialValue", "WorldTimeAtTimeFrozen", "DayLengthMinutes", "HourStartDawn", "HourStartDay", "HourStartDusk", "HourStartNight", "InitialHour" }))
        P("TIMEOFDAY GetTimeOfDayFraction=" .. call0(c, "GetTimeOfDayFraction") .. " GetNormalizedDaylight=" .. call0(c, "GetNormalizedDaylight") .. " GetDayPhase=" .. call0(c, "GetDayPhase") .. " GetNumGameDays=" .. call0(c, "GetNumGameDays") .. " GetDayNumber=" .. call0(c, "GetDayNumber") .. " IsDay=" .. call0(c, "IsDay") .. " IsNight=" .. call0(c, "IsNight"))
        pcall(function() local t = c:GetTimeOfDay(); P("TIMEOFDAY hour/min=" .. rd(t, { "Hour", "Minute" })) end)
    end
    for _, c in ipairs(findAll("UWEWeatherSyncComponent")) do
        P("WEATHER " .. nameOf(c) .. " " .. rd(c, { "bWeatherWasLoaded", "CurrentForecastTime", "CurrentWeatherStartTime", "TimeToNextWeather", "TimeToStartTransition", "TransitionAlphaOverride", "NextForecastIndex", "TransitionAlpha", "PreviousTransitionAlpha" }))
        for _, k in ipairs({ "WeatherForecast", "CurrentWeather", "NextWeather", "CurrentWeatherOverride", "NextWeatherOverride" }) do
            pcall(function() local v = c[k]; P("WEATHER " .. k .. "=" .. (isValid(v) and str(v:GetFullName()) or "NULL")) end)
        end
        P("WEATHER GetIsWeatherEnabled=" .. call0(c, "GetIsWeatherEnabled"))
    end
    -- 6. lights
    for _, l in ipairs(findAll("DirectionalLightComponent")) do
        local own = "?"
        pcall(function() own = l:GetOwner():GetFName():ToString() end)
        P("DIRLIGHT " .. nameOf(l) .. " owner=" .. own .. " " .. rd(l, { "Intensity", "LightColor", "bUseTemperature", "Temperature", "IndirectLightingIntensity", "VolumetricScatteringIntensity", "bAtmosphereSunLight", "AtmosphereSunLightIndex", "CastShadows", "bAffectsWorld", "Mobility", "bUseRayTracedDistanceFieldShadows", "bEnableLightShaftOcclusion", "bEnableLightShaftBloom", "BloomScale", "bEnableLightFunctionOnLumen" }) .. " visible=" .. call0(l, "IsVisible") .. " rot=" .. f1(try(function() return l:K2_GetComponentRotation() end)))
        pcall(function() P("DIRLIGHT " .. nameOf(l) .. " LightFunctionMaterial=" .. (isValid(l.LightFunctionMaterial) and str(l.LightFunctionMaterial:GetFullName()) or "NULL") .. " LightFunctionScale=" .. f1(l.LightFunctionScale) .. " DisabledBrightness=" .. f1(l.DisabledBrightness)) end)
    end
    for _, l in ipairs(findAll("SkyLightComponent")) do
        local own = "?"
        pcall(function() own = l:GetOwner():GetFName():ToString() end)
        P("SKYLIGHT " .. nameOf(l) .. " owner=" .. own .. " " .. rd(l, { "Intensity", "LightColor", "SourceType", "bRealTimeCapture", "bLowerHemisphereIsBlack", "LowerHemisphereColor", "bAffectsWorld", "IndirectLightingIntensity", "VolumetricScatteringIntensity", "OcclusionExponent", "MinOcclusion", "Mobility" }) .. " visible=" .. call0(l, "IsVisible"))
    end
    for _, c in ipairs(findAll("SkyAtmosphereComponent")) do P("SKYATMOS " .. nameOf(c) .. " visible=" .. call0(c, "IsVisible") .. " " .. rd(c, { "TransformMode", "BottomRadius", "AtmosphereHeight", "AerialPespectiveViewDistanceScale", "HeightFogContribution", "AerialPerspectiveStartDepth", "bHoldout" })) end
    for _, c in ipairs(findAll("VolumetricCloudComponent")) do P("VCLOUD " .. nameOf(c) .. " visible=" .. call0(c, "IsVisible") .. " " .. rd(c, { "LayerBottomAltitude", "LayerHeight", "ViewSampleCountScale", "bHoldout" })) end
    for _, f in ipairs(findAll("ExponentialHeightFogComponent")) do
        local own = "?"
        pcall(function() own = f:GetOwner():GetFName():ToString() end)
        P("FOG owner=" .. own .. " visible=" .. call0(f, "IsVisible") .. " active=" .. call0(f, "IsActive") .. " z=" .. f1(try(function() return f:K2_GetComponentLocation().Z end)))
        P("FOG " .. rd(f, { "FogDensity", "FogHeightFalloff", "FogInscatteringLuminance", "SkyAtmosphereAmbientContributionColorScale", "FullyDirectionalInscatteringColorDistance", "NonDirectionalInscatteringColorDistance", "DirectionalInscatteringLuminance", "DirectionalInscatteringExponent", "DirectionalInscatteringStartDistance", "StartDistance", "FogCutoffDistance", "FogMaxOpacity" }))
        P("FOG VOL " .. rd(f, { "bEnableVolumetricFog", "VolumetricFogScatteringDistribution", "VolumetricFogAlbedo", "VolumetricFogEmissive", "VolumetricFogExtinctionScale", "VolumetricFogDistance", "VolumetricFogStartDistance", "VolumetricFogNearFadeInDistance", "bHoldout", "bRenderInMainPass" }))
        pcall(function() local d = f.SecondFogData; P("FOG SECOND " .. rd(d, { "FogDensity", "FogHeightFalloff", "FogHeightOffset" })) end)
    end
    -- 7. post process components / volumes: exposure and the unbound ones
    local npc = 0
    for _, c in ipairs(findAll("PostProcessComponent")) do
        npc = npc + 1
        local own = "?"
        pcall(function() own = c:GetOwner():GetFName():ToString() end)
        local isReg = own:find("^BP_UWEWaterBiomeRegionActor") ~= nil
        local bw = tonumber(try(function() return c.BlendWeight end)) or 0
        if (not isReg) or bw > 0 then
            P(string.format("PPC %s owner=%s enabled=%s unbound=%s prio=%s blendw=%s blendr=%s", nameOf(c), own, f1(try(function() return c.bEnabled end)), f1(try(function() return c.bUnbound end)), f1(try(function() return c.Priority end)), f1(bw), f1(try(function() return c.BlendRadius end))))
            pcall(function()
                local s = c.Settings
                P("PPC " .. nameOf(c) .. " EXPOSURE " .. rd(s, { "bOverride_AutoExposureBias", "AutoExposureBias", "bOverride_AutoExposureMinBrightness", "AutoExposureMinBrightness", "bOverride_AutoExposureMaxBrightness", "AutoExposureMaxBrightness", "bOverride_AutoExposureMethod", "AutoExposureMethod", "bOverride_SceneColorTint", "SceneColorTint", "bOverride_ColorGain", "ColorGain", "bOverride_BloomIntensity", "BloomIntensity" }))
            end)
        end
    end
    P("PPC count=" .. npc)
    local nv, nub = 0, 0
    for _, v in ipairs(findAll("PostProcessVolume")) do
        nv = nv + 1
        if try(function() return v.bUnbound end) == true then
            nub = nub + 1
            pcall(function() P("PPV unbound " .. nameOf(v) .. " prio=" .. f1(v.Priority) .. " blendw=" .. f1(v.BlendWeight) .. " enabled=" .. f1(v.bEnabled) .. " EXPOSURE " .. rd(v.Settings, { "bOverride_AutoExposureBias", "AutoExposureBias", "bOverride_AutoExposureMinBrightness", "AutoExposureMinBrightness", "bOverride_AutoExposureMaxBrightness", "AutoExposureMaxBrightness" })) end)
        end
    end
    P("PPV count=" .. nv .. " unbound=" .. nub)
    -- 8. pawn camera POV post process (what the player camera actually carries)
    pcall(function() P("CAMMGR " .. rd(pc.PlayerCameraManager, { "ViewTarget" }) .. " fov=" .. call0(pc.PlayerCameraManager, "GetFOVAngle")) end)
    return true, "uwprobe done"
end
-- DIAGNOSTIC (engine mode only, exploration): run run\<FILE>.lua in the game thread with the mod helpers in scope; its return value is logged.
-- Lets an input-injection experiment be changed without relaunching the game (UE4SS reads the mod Lua only at launch).
-- ---------------------------------------------------------------- story goal verbs + terrain census (test-only, 2026-11-23, vanish_proof)
local function findGoal(name)
    for _, g in ipairs(findAll("UWEStoryGoal")) do
        if nameOf(g) == name then return g end
    end
    return nil
end
local function goalStatics()
    local st = nil
    pcall(function() st = StaticFindObject("/Script/UWEStoryGoals.Default__UWEStoryGoalsStatics") end)
    if not isValid(st) then
        for _, o in ipairs(FindAllOf("UWEStoryGoalsStatics") or {}) do if isValid(o) then st = o; break end end
    end
    return isValid(st) and st or nil
end
-- storygoalstate <DA name>: logs and returns whether the goal is unlocked (UWEStoryGoalsStatics:IsStoryGoalUnlocked)
function verbs.storygoalstate(args)
    local name = tostring(args or ""):match("^%s*([%w_%-]+)%s*$")
    if not name then return false, "usage: storygoalstate DA_Name" end
    local g, st, pc = findGoal(name), goalStatics(), getPC()
    if not g then log("STORYGOAL state " .. name .. " NOT_LOADED"); return false, "goal not loaded" end
    if not st or not pc then return false, "no statics or pc" end
    local okr, r = pcall(function() return st:IsStoryGoalUnlocked(pc:GetWorld(), g, pc.PlayerState) end)
    log(string.format("STORYGOAL state %s ok=%s unlocked=%s", name, tostring(okr), tostring(r)))
    return okr, "unlocked=" .. tostring(r)
end
-- storygoal <DA name>: unlocks the goal. Method order: UWEStoryGoalsWorldSubsystem:UnlockStoryGoal(goal, pawn, true),
-- UWEStoryGoalsStatics:UnlockPlayerStoryGoal(world, goal, PlayerState), UnlockWorldStoryGoal(world, goal). Logs the method that did not raise.
function verbs.storygoal(args)
    local name = tostring(args or ""):match("^%s*([%w_%-]+)%s*$")
    if not name then return false, "usage: storygoal DA_Name" end
    local g = findGoal(name)
    if not g then log("STORYGOAL unlock " .. name .. " NOT_LOADED"); return false, "goal not loaded" end
    local pc = getPC()
    if not pc then return false, "no pc" end
    local pawn = getPawn(pc)
    local sub, st = nil, goalStatics()
    pcall(function() local s = FindFirstOf("UWEStoryGoalsWorldSubsystem"); if isValid(s) then sub = s end end)
    local world, ps = nil, nil
    pcall(function() world = pc:GetWorld() end)
    pcall(function() ps = pc.PlayerState end)
    local attempts = {
        { "subsystem", function() sub:UnlockStoryGoal(g, pawn, true) end },
        { "player", function() st:UnlockPlayerStoryGoal(world, g, ps) end },
        { "world", function() st:UnlockWorldStoryGoal(world, g) end },
    }
    for _, a in ipairs(attempts) do
        local ok, err = pcall(a[2])
        log(string.format("STORYGOAL unlock %s via %s ok=%s %s", name, a[1], tostring(ok), ok and "" or shortErr(err)))
        if ok then return true, "via " .. a[1] end
    end
    return false, "all methods failed"
end
-- terraincensus <label>: read-only, one line per prefix (SM_origin_tile_, SM_spot1_tile_) + the lifepod. Distinguishes gone / hidden / not rendered.
function verbs.terraincensus(args)
    local label = tostring(args ~= "" and args or "census")
    local function P(s) log("TCENSUS " .. label .. " " .. s) end
    local now = nil
    pcall(function() now = StaticFindObject("/Script/Engine.Default__GameplayStatics"):GetTimeSeconds(getPC():GetWorld()) end)
    local function stats(a, S)
        S.found = S.found + 1
        if isValid(a) then S.valid = S.valid + 1 else return end
        local okh, h = pcall(function() return a.bHidden end)
        if okh and h then S.hidden = S.hidden + 1 end
        local comp = nil
        pcall(function() comp = a.StaticMeshComponent end)
        if not isValid(comp) then pcall(function() comp = a.RootComponent end) end
        if isValid(comp) then
            local okv, v = pcall(function() return comp:IsVisible() end)
            if okv and v then S.vis = S.vis + 1 end
            local okg, hg = pcall(function() return comp.bHiddenInGame end)
            if okg and hg then S.hig = S.hig + 1 end
            local okR, rg = pcall(function() return comp:IsRegistered() end)
            if okR and rg then S.reg = S.reg + 1 end
        else
            S.nocomp = S.nocomp + 1
        end
        local okw, w = pcall(function() return a:WasRecentlyRendered(1.0) end)
        if okw then S.rcallable = S.rcallable + 1; if w then S.recent = S.recent + 1 end end
        local okl, lt = pcall(function() return a:GetLastRenderTime() end)
        if okl and type(lt) == "number" and now then
            S.lcallable = S.lcallable + 1
            local age = now - lt
            if S.minAge == nil or age < S.minAge then S.minAge = age end
        end
    end
    local prefixes = { "SM_origin_tile_", "SM_spot1_tile_" }
    local S = {}
    for _, p in ipairs(prefixes) do S[p] = { found = 0, valid = 0, hidden = 0, vis = 0, hig = 0, reg = 0, nocomp = 0, recent = 0, rcallable = 0, lcallable = 0 } end
    local okA, errA = pcall(function()
        for _, a in ipairs(findAll("StaticMeshActor")) do
            -- imported tiles are named StaticMeshActor_N; only the MESH asset is SM_origin_tile_* (research/terrain/README.md), so match the mesh name too
            local nm = nameOf(a)
            local mnm = ""
            pcall(function()
                local m = a.StaticMeshComponent.StaticMesh
                if isValid(m) then mnm = nameOf(m) end
            end)
            for _, p in ipairs(prefixes) do
                if nm:sub(1, #p) == p or mnm:sub(1, #p) == p then stats(a, S[p]) end
            end
        end
    end)
    if not okA then P("scan error " .. shortErr(errA)) end
    for _, p in ipairs(prefixes) do
        local s = S[p]
        P(string.format("%s found=%d valid=%d bHidden=%d compVisible=%d hiddenInGame=%d registered=%d nocomp=%d wasRecentlyRendered(1s)=%d/%d minRenderAge=%s (callable %d) tnow=%s",
            p, s.found, s.valid, s.hidden, s.vis, s.hig, s.reg, s.nocomp, s.recent, s.rcallable, s.minAge and string.format("%.1f", s.minAge) or "n/a", s.lcallable, now and string.format("%.1f", now) or "?"))
    end
    local pods, podInfo = 0, ""
    pcall(function()
        for _, a in ipairs(findAll("BP_StaticLifepod_Surface_C")) do
            pods = pods + 1
            local hid, rec, vis = "?", "?", "?"
            pcall(function() hid = tostring(a.bHidden) end)
            pcall(function() rec = tostring(a:WasRecentlyRendered(1.0)) end)
            pcall(function() vis = tostring(a.RootComponent:IsVisible()) end)
            local hull = "?"
            pcall(function() hull = tostring(a.Hull:IsVisible()) end)
            podInfo = podInfo .. string.format(" [%s bHidden=%s rootVisible=%s hullVisible=%s wasRecentlyRendered=%s]", nameOf(a), hid, vis, hull, rec)
        end
    end)
    P(string.format("LIFEPOD count=%d%s", pods, podInfo))
    local pc = getPC()
    local pawnz = "?"
    pcall(function() local l = getPawn(pc):K2_GetActorLocation(); pawnz = string.format("%.0f,%.0f,%.0f", l.X, l.Y, l.Z) end)
    P("PAWN " .. pawnz)
    return true, string.format("origin=%d/%d spot1=%d/%d pods=%d", S[prefixes[1]].valid, S[prefixes[1]].found, S[prefixes[2]].valid, S[prefixes[2]].found, pods)
end
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
-- Diagnostic verbs uwa1 (effective MID values per region) and uwa21 (tracker/region table: idx, volType, order), kept 2026-11-27; each runs data/uwaN.lua of this mod with the local helpers in scope
-- (cmdAfter in a plan has no args; run/ is wiped by autotest.sh).
for _, n in ipairs({ "uwa1", "uwa21" }) do
    verbs[n] = function()
        local chunk, err = loadfile(MOD_DIR .. "\\data\\uwa.lua")
        if not chunk then return false, shortErr(err) end
        local env = setmetatable({ log = log, getPC = getPC, getPawn = getPawn, findAll = findAll, nameOf = nameOf, isValid = isValid, str = str, try = try,
            toList = toList, fmtV = fmtV, after = after, verbs = verbs, MODE = n }, { __index = _G })
        debug.setupvalue(chunk, 1, env)
        local ok, res = pcall(chunk)
        log("UWA " .. n .. " ok=" .. tostring(ok) .. " " .. tostring(res))
        return ok, shortErr(res)
    end
end
-- TEMPORARY (2026-11-28, investigator-lum): lum_* verbs run data/lum.lua (lines LUM ...): exposure readout + in-memory exposure A/B. Delete with data/lum.lua when the investigation ends.
for _, n in ipairs({ "lum_read", "lum_bias", "lum_bias_hi", "lum_unclamp", "lum_nocurve", "lum_b15", "lum_b20", "lum_b25", "lum_b30" }) do
    verbs[n] = function()
        local chunk, err = loadfile(MOD_DIR .. "\\data\\lum.lua")
        if not chunk then return false, shortErr(err) end
        local env = setmetatable({ log = log, getPC = getPC, getPawn = getPawn, findAll = findAll, nameOf = nameOf, isValid = isValid, str = str, try = try,
            toList = toList, fmtV = fmtV, after = after, verbs = verbs, MODE = n }, { __index = _G })
        debug.setupvalue(chunk, 1, env)
        local ok, res = pcall(chunk)
        log("LUM " .. n .. " ok=" .. tostring(ok) .. " " .. tostring(res))
        return ok, shortErr(res)
    end
end
-- Base-building diagnostic (2026-11-28): verb 'buildprobe MODE [args]' runs data/buildprobe.lua (lines BPROBE ...).
function verbs.buildprobe(args)
    local chunk, err = loadfile(MOD_DIR .. "\\data\\buildprobe.lua")
    if not chunk then return false, shortErr(err) end
    local env = setmetatable({ log = log, getPC = getPC, getPawn = getPawn, findAll = findAll, nameOf = nameOf, isValid = isValid, str = str, try = try,
        toList = toList, fmtV = fmtV, after = after, verbs = verbs, MOD_DIR = MOD_DIR, ARGS = args or "" }, { __index = _G })
    debug.setupvalue(chunk, 1, env)
    local ok, a, b = pcall(chunk)
    if not ok then log("BPROBE ERROR " .. tostring(a)) end
    return ok and a ~= false, shortErr(ok and (b or a) or a)
end
-- TEST TRIGGER ONLY: runs the SN2Tadpole spawn logic (same code as its F4 key); result lines are logged by SN2Tadpole as [SN2Tadpole] ...
function verbs.tadpole()
    local chunk, err = loadfile(MOD_DIR .. "\\..\\SN2Tadpole\\Scripts\\tadpole_spawn.lua")
    if not chunk then return false, shortErr(err) end
    local okc, spawn = pcall(chunk)
    if not okc or type(spawn) ~= "function" then return false, shortErr(spawn) end
    local ok, a, b = pcall(spawn)
    return ok and a and true or false, tostring(b or a)
end
-- TEST TRIGGER ONLY: runs the SN2BugShot report code (same as its F1 key); result line [SN2BugShot] REPORT <id> ...
function verbs.bugshot()
    local chunk, err = loadfile(MOD_DIR .. "\\..\\SN2BugShot\\Scripts\\bugshot.lua")
    if not chunk then return false, shortErr(err) end
    local okc, report = pcall(chunk)
    if not okc or type(report) ~= "function" then return false, shortErr(report) end
    local ok, a, b = pcall(report, "test")
    return ok and a and true or false, tostring(b or a)
end
-- TEST TRIGGERS for the SN2BugShot popup (same code path as F1 / Ctrl+Enter / Esc; real keys are not simulated)
local bugPopup = nil
local function popupApi()
    if bugPopup then return bugPopup end
    local chunk, err = loadfile(MOD_DIR .. "\\..\\SN2BugShot\\Scripts\\popup.lua")
    if not chunk then return nil, shortErr(err) end
    local okc, api = pcall(chunk)
    if not okc or type(api) ~= "table" then return nil, shortErr(api) end
    bugPopup = api
    return api
end
function verbs.bugreport_open()
    local api, err = popupApi()
    if not api then return false, err end
    local ok, a, b = pcall(api.open, "test")
    return ok and a and true or false, tostring(b or a)
end
function verbs.bugreport_type(args)
    local api, err = popupApi()
    if not api then return false, err end
    local ok = api.setText(tostring(args or ""))
    return ok, ok and "typed" or "popup not open"
end
function verbs.bugreport_submit()
    local api, err = popupApi()
    if not api then return false, err end
    local ok = api.submit()
    return ok and true or false, ok and "submitted" or "popup not open"
end
function verbs.bugreport_cancel()
    local api, err = popupApi()
    if not api then return false, err end
    local ok = api.cancel()
    return ok and true or false, ok and "cancelled" or "popup not open"
end
-- detail: "open=<bool> phase=<p> paused=<bool> time=<game s> result=<n> cursor=<bool> text=<box text>"
function verbs.bugreport_state()
    local api, err = popupApi()
    if not api then return false, err end
    local s = api.state()
    return true, string.format("open=%s phase=%s paused=%s time=%s result=%s cursor=%s text=%s", tostring(s.open), tostring(s.phase),
        tostring(s.paused), s.time and string.format("%.3f", s.time) or "?", tostring(s.result), tostring(s.cursor), tostring(s.text or ""))
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
-- death screen ("YOU HAVE BEEN REPRINTED"): the pawn is respawned at once by USN2RespawnComponent, but WBP_RespawnScreen_C stays up until CONTINUE
-- (BackButton) is clicked and blocks look input. Signal = that widget visible + rooted (hidden in normal play: BackButton chainVisible=false).
function verbs.death()
    local scr, btn = false, false
    for _, w in ipairs(findAll("WBP_RespawnScreen_C")) do
        local vis, rooted = chainVisible(w)
        if vis and rooted then scr = true end
    end
    if scr then
        for _, b in ipairs(findAll("WBP_GenericButtonBig_C")) do
            if nameOf(b) == "BackButton" and widgetPath(b):find("WBP_RespawnScreen", 1, true) then
                local vis, rooted = chainVisible(b)
                if vis and rooted then btn = true end
            end
        end
    end
    log(string.format("DEATHCHK screen=%s continueButton=%s pawn=%s", tostring(scr), tostring(btn), tostring(getPawn() ~= nil)))
    return true, scr and "dead" or "alive"
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

-- ---------------------------------------------------------------- command poll (100 ms, cheap: one failed io.open when idle)
if ENGINE then
    local CMD_FILE = RUN_DIR .. "\\cmd.txt"
    local lastSeq = 0
    LoopAsync(100, function()
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
    log("ENGINE input mode armed: polling " .. CMD_FILE .. " every 100 ms")
end

-- Q2 monitor (hidden-desktop investigation 2026-11-22, passive): while run\q2.txt exists, log every 500 ms
-- "Q2 <HH:MM:SS> world=.. pawn=(x,y,z) yaw=.. pitch=.." so real input leaking into the game shows up as unexplained changes
if ENGINE then
    local Q2_FILE = RUN_DIR .. "\\q2.txt"
    LoopAsync(500, function()
        local f = io.open(Q2_FILE, "r")
        if not f then return false end
        f:close()
        ExecuteInGameThread(function()
            pcall(function()
                local pc = getPC(); local pawn = getPawn(pc)
                local px, py, pz = 0, 0, 0
                if pawn then local l = pawn:K2_GetActorLocation(); px, py, pz = l.X, l.Y, l.Z end
                local y, p = camRot()
                local w = "?"
                if pc then pcall(function() w = pc:GetWorld():GetFName():ToString() end) end
                local ui = {}
                pcall(function() for _, r in ipairs(viewportRoots()) do if r.vis then ui[#ui + 1] = r.cls end end end)
                log(string.format("Q2 %s world=%s pawn=(%.1f,%.1f,%.1f) yaw=%.2f pitch=%.2f ui=%s", os.date("%H:%M:%S"), w, px, py, pz, y or 0, p or 0, table.concat(ui, ",")))
            end)
        end)
        return false
    end)
end

-- TEST-ONLY keys: this whole file returns early ("idle (no plan)") unless the harness armed a plan, so these binds never exist in normal play.
-- F8 (and probably F9/F10) are bound by the game itself (F8 opens the Feedback panel), so the teleports use Ctrl+Shift+Z/X/C/V/B
local FKEYS = { Key.Z, Key.X, Key.C, Key.V, Key.B }
for n, k in ipairs(FKEYS) do
    RegisterKeyBind(k, { ModifierKey.CONTROL, ModifierKey.SHIFT }, function() teleportTo(n) end)
end
RegisterKeyBind(Key.F11, { ModifierKey.CONTROL }, logState)
log("loaded; Ctrl+Shift+Z/X/C/V/B teleport, Ctrl+F11 state")
