-- SN2IntroProbe: records what happens during a new game's intro, so it can be skipped.
-- Logs (prefix [SN2IntroProbe]) with seconds since the world started:
--   * story goals as they become unlocked (polls UWEStoryGoalsStatics:IsStoryGoalUnlocked over every loaded UWEStoryGoal)
--   * level sequences / media (FMV) starting, lifepod manager HUD calls
--   * data layer runtime state changes
--   * pawn class, location, attach parent and camera view target whenever they change (pawn location also every 10 s)
-- No keys, no world changes. Read-only.
local MOD = "SN2IntroProbe"
local function log(msg) print(string.format("[%s] %s\n", MOD, tostring(msg))) end

local t0 = os.clock()
local function stamp() return string.format("t=%6.1fs", os.clock() - t0) end

local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, r = pcall(function() return o:IsValid() end)
    return ok and r == true
end

local function nameOf(o)
    -- UE4SS hands back a null UObject wrapper for empty results; calling a method on it crashes UE4SS.dll (+0x2428xx) -> check first
    if not isValid(o) then return "none" end
    local ok, s = pcall(function() return o:GetFName():ToString() end)
    return ok and s or "?"
end

local function fullOf(o)
    -- UE4SS hands back a null UObject wrapper for empty results; calling a method on it crashes UE4SS.dll (+0x2428xx) -> check first
    if not isValid(o) then return "none" end
    local ok, s = pcall(function() return o:GetFullName() end)
    return ok and s or "?"
end

local function notCDO(o) return isValid(o) and not fullOf(o):find("Default__", 1, true) end

local function getPC()
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
        if notCDO(pc) then
            local okL, isLocal = pcall(function() return pc:IsLocalController() end)
            if not okL or isLocal then return pc end
        end
    end
    return nil
end

local function worldName()
    local pc = getPC()
    if not pc then return "?" end
    local ok, w = pcall(function() return pc:GetWorld():GetFullName() end)
    return ok and w or "?"
end

-- ---------------------------------------------------------------- story goals
local statics
local function getStatics()
    if isValid(statics) then return statics end
    for _, path in ipairs({ "/Script/UWEStoryGoals.Default__UWEStoryGoalsStatics" }) do
        local ok, o = pcall(StaticFindObject, path)
        if ok and isValid(o) then statics = o; return o end
    end
    for _, o in ipairs(FindAllOf("UWEStoryGoalsStatics") or {}) do
        if isValid(o) then statics = o; return o end
    end
    return nil
end

local unlocked = {}       -- goal name -> true
local goalsPrimed = false
local function pollGoals(pc)
    local st = getStatics()
    if not st then return end
    local ps
    pcall(function() ps = pc.PlayerState end)
    local world
    pcall(function() world = pc:GetWorld() end)
    local goals = FindAllOf("UWEStoryGoal") or {}
    local newOnes = {}
    for _, g in ipairs(goals) do
        if notCDO(g) then
            local n = nameOf(g)
            if not unlocked[n] then
                local ok, r = pcall(function() return st:IsStoryGoalUnlocked(world, g, ps) end)
                if ok and r then
                    unlocked[n] = true
                    newOnes[#newOnes + 1] = n
                end
            end
        end
    end
    if not goalsPrimed then
        goalsPrimed = true
        table.sort(newOnes)
        log(string.format("%s story goals already unlocked at start (%d of %d loaded): %s", stamp(), #newOnes, #goals, table.concat(newOnes, ", ")))
    else
        for _, n in ipairs(newOnes) do log(string.format("%s STORY GOAL unlocked: %s", stamp(), n)) end
    end
end

-- ---------------------------------------------------------------- data layers
local dlState = {}
local function pollDataLayers()
    local mgr
    for _, m in ipairs(FindAllOf("DataLayerManager") or {}) do
        if notCDO(m) then mgr = m end
    end
    for _, dl in ipairs(FindAllOf("DataLayerInstance") or {}) do
        if notCDO(dl) then
            local name = nameOf(dl)
            pcall(function()
                local a = dl:GetAsset()
                if isValid(a) then name = nameOf(a) end
            end)
            -- UDataLayerInstance has no callable state getter; ask the world's UDataLayerManager
            local okS, s = false, nil
            if mgr then okS, s = pcall(function() return mgr:GetDataLayerInstanceRuntimeState(dl) end) end
            local v = okS and tostring(s) or "?"
            if dlState[name] ~= v then
                if dlState[name] ~= nil or v ~= "0" then
                    log(string.format("%s DATA LAYER %s: %s -> %s (0=Unloaded 1=Loaded 2=Activated)", stamp(), name, tostring(dlState[name]), v))
                end
                dlState[name] = v
            end
        end
    end
end

-- ---------------------------------------------------------------- pawn / camera
local last = {}
local lastLocLog = 0
local function pollPawn(pc)
    local pawn
    pcall(function() pawn = pc.Pawn end)
    local pawnCls = isValid(pawn) and nameOf(pawn:GetClass()) or "none"
    local vt = "?"
    pcall(function() local v = pc:GetViewTarget(); if isValid(v) then vt = nameOf(v:GetClass()) end end)
    local parent = "none"
    pcall(function()
        local p = pawn:GetAttachParentActor()
        if isValid(p) then parent = nameOf(p) .. " (" .. nameOf(p:GetClass()) .. ")" end
    end)
    local x, y, z = 0, 0, 0
    pcall(function() local L = pawn:K2_GetActorLocation(); x, y, z = L.X, L.Y, L.Z end)
    local key = pawnCls .. "|" .. vt .. "|" .. parent
    if key ~= last.key then
        last.key = key
        log(string.format("%s PAWN %s | view target %s | attached to %s | at (%.0f, %.0f, %.0f) | world %s",
            stamp(), pawnCls, vt, parent, x, y, z, worldName()))
    elseif os.clock() - lastLocLog > 10 then
        log(string.format("%s pawn at (%.0f, %.0f, %.0f) attached to %s", stamp(), x, y, z, parent))
    else
        return
    end
    lastLocLog = os.clock()
end

-- ---------------------------------------------------------------- hooks (each optional)
local function hook(path, fn)
    local ok, err = pcall(RegisterHook, path, fn)
    log((ok and "hooked " or "hook FAILED ") .. path .. (ok and "" or (": " .. tostring(err))))
end

hook("/Script/MovieScene.MovieSceneSequencePlayer:Play", function(ctx)
    local p = ctx:get()
    local seq = "?"
    pcall(function() seq = fullOf(p:GetSequence()) end)
    log(string.format("%s SEQUENCE play: %s | player %s", stamp(), seq, fullOf(p)))
end)
hook("/Script/MediaAssets.MediaPlayer:OpenSource", function(ctx, src)
    local s = "?"
    pcall(function() s = fullOf(src:get()) end)
    log(string.format("%s MEDIA open: %s", stamp(), s))
end)
for _, fn in ipairs({ "HideHud", "ShowHUD", "LogLifepod" }) do
    hook("/Script/Subnautica2.SN2LifepodManager:" .. fn, function(ctx, a)
        local extra = ""
        if fn == "LogLifepod" then pcall(function() extra = " | " .. a:get():ToString() end) end
        log(string.format("%s LIFEPOD MANAGER %s on %s%s", stamp(), fn, fullOf(ctx:get()), extra))
    end)
end
hook("/Script/Engine.PlayerController:ClientRestart", function()
    t0 = os.clock()
    unlocked, goalsPrimed, dlState, last = {}, false, {}, {}
    log("---- ClientRestart (new world / respawn) | world " .. worldName())
end)

-- light load: pawn every 1 s; story goals (1,403 IsStoryGoalUnlocked calls) and data layers every 5 s, and only in L_Main
-- (a UE4SS.dll access violation at the menu on 2026-11-16 21:08 happened while this polled every 1 s everywhere — cause not proven)
local tick = 0
LoopAsync(1000, function()
    ExecuteInGameThread(function()
        local pc = getPC()
        if not pc then return end
        tick = tick + 1
        pcall(pollPawn, pc)
        if tick % 5 == 0 and worldName():find("L_Main", 1, true) then
            pcall(pollGoals, pc)
            pcall(pollDataLayers)
        end
    end)
    return false
end)

log("loaded: recording intro flow (story goals, sequences, media, data layers, pawn)")
