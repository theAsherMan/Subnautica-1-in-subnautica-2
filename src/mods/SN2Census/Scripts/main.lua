-- SN2Census — read-only measurement mod for the SN2EmptyWorld test (see research/09 "Empty world").
-- It never destroys, hides or changes anything. No hotkeys (removed 2026-11-23; recover with git show 40820f3).
--
--   No hotkeys (samples run on a timer; report file at t=15 s).
--   Arms itself on a ClientRestart whose world is L_Main; samples at 1,5,15,30,60,120 s, then every 120 s.
--   Sample = one log line "[SN2Census] t=... cvarSrc=... | mod: ..." ; report = census_<YYYYMMDD_HHMMSS>.txt next to this mod.
-- Nothing runs in the lobby: sampling is scheduled only after arming (ExecuteWithDelay chain), never from a LoopAsync.

local UEHelpers = require("UEHelpers")
local MOD = "SN2Census"

local function log(msg) print(string.format("[%s] %s\n", MOD, tostring(msg))) end

local function scriptDir()
    local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
    return src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
end
local MOD_DIR = scriptDir()

-- ---------------------------------------------------------------- guarded helpers
local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, v = pcall(function() return o:IsValid() end)
    return ok and v == true
end
local function nameOf(o)
    local ok, n = pcall(function() return o:GetFName():ToString() end)
    return ok and n or "?"
end
local function fullNameOf(o)
    local ok, n = pcall(function() return o:GetFullName() end)
    return ok and n or "?"
end
local function classNameOf(o)
    local ok, n = pcall(function() return o:GetClass():GetFName():ToString() end)
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
    return nil
end

-- ---------------------------------------------------------------- state
local gen = 0            -- bumped on every ClientRestart; stale scheduled samples compare against it
local armed = false
local armTime = 0
local armWorld = "?"

local function cvar(name)
    local ok, v = pcall(function()
        local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
        return ksl:GetConsoleVariableIntValue(name)
    end)
    if ok and type(v) == "number" then return v end
    return -999
end

local function worldLevelName()
    local ok, v = pcall(function()
        local st = StaticFindObject("/Script/UWELobby.Default__UWELobbyStatics")
        return st:GetWorldLevelName():ToString()
    end)
    if ok and type(v) == "string" then return v end
    return "?"
end

local function countOf(className)
    return #findAll(className)
end

local function findModActor()
    for _, o in ipairs(findAll("ModActor_C")) do
        local ok, cn = pcall(function() return o:GetClass():GetFullName() end)
        if ok and cn and cn:find("/Game/Mods/SN2EmptyWorld/", 1, true) then return o end
    end
    return nil
end
local function modInt(m, prop)
    local ok, v = pcall(function() return m[prop] end)
    if ok and type(v) == "number" then return v end
    return -999
end

-- returns line, data (data keeps lists for the report)
local function sample()
    local t = os.time() - armTime
    local actors = findAll("Actor")
    local uaidActors = {}
    for _, a in ipairs(actors) do
        if nameOf(a):find("_UAID_", 1, true) then uaidActors[#uaidActors + 1] = a end
    end
    local genLevels = {}
    for _, l in ipairs(findAll("Level")) do
        local fn = fullNameOf(l)
        if fn:find("/_Generated_/", 1, true) then genLevels[#genLevels + 1] = fn end
    end
    local px, py, pz = "?", "?", "?"
    local pawn = getPawn()
    if pawn then
        local ok, v = pcall(function() return pawn:K2_GetActorLocation() end)
        if ok and v then px, py, pz = string.format("%.0f", v.X), string.format("%.0f", v.Y), string.format("%.0f", v.Z) end
    end
    local m = findModActor()
    local modPart
    if m then
        modPart = string.format("mod: found=1 purges=%d map=%d creatures=%d storage=%d lastActors=%d srcBefore=%d src=%d hlodBefore=%d hlod=%d",
            modInt(m, "PurgeCount"), modInt(m, "MapActorsDestroyed"), modInt(m, "CreaturesDestroyed"), modInt(m, "ResourceStorageDestroyed"),
            modInt(m, "LastActorCount"), modInt(m, "CVarStreamingSourcesBefore"), modInt(m, "CVarStreamingSources"),
            modInt(m, "CVarHLODBefore"), modInt(m, "CVarHLOD"))
    else
        modPart = "mod: found=0 purges=-1 map=-1 creatures=-1 storage=-1 lastActors=-1 srcBefore=-1 src=-1 hlodBefore=-1 hlod=-1"
    end
    local body = string.format(
        "world=%s worldLevel=%s t=%d cvarSrc=%d cvarHLOD=%d genLevels=%d actors=%d uaid=%d sma=%d lsp=%d landscape=%d hlod=%d aiPawn=%d aiChar=%d placeable=%d wpResource=%d smc=%d ismc=%d skm=%d niagara=%d pawn=(%s,%s,%s) | %s",
        armWorld, worldLevelName(), t, cvar("wp.Runtime.UpdateStreamingSources"), cvar("wp.Runtime.HLOD"), #genLevels, #actors, #uaidActors,
        countOf("StaticMeshActor"), countOf("LandscapeStreamingProxy"), countOf("Landscape"), countOf("WorldPartitionHLOD"),
        countOf("UWEAIPawn"), countOf("UWEAICharacter"), countOf("UWEPlaceableProxy"), countOf("UWEWorldPopResourceBaseActor"),
        countOf("StaticMeshComponent"), countOf("InstancedStaticMeshComponent"), countOf("SkeletalMeshComponent"), countOf("NiagaraComponent"),
        px, py, pz, modPart)
    log(body)
    return "[" .. MOD .. "] " .. body, { actors = actors, uaid = uaidActors, genLevels = genLevels, mod = m }
end

local function transformOf(a)
    local function f3(fn, k1, k2, k3)
        local ok, v = pcall(function() local r = fn(); return string.format("(%.2f,%.2f,%.2f)", r[k1], r[k2], r[k3]) end)
        return ok and v or "?"
    end
    return "loc=" .. f3(function() return a:K2_GetActorLocation() end, "X", "Y", "Z")
        .. " | rot=" .. f3(function() return a:K2_GetActorRotation() end, "Pitch", "Yaw", "Roll")
        .. " | scale=" .. f3(function() return a:GetActorScale3D() end, "X", "Y", "Z")
end

local function writeReport(line, d)
    local stamp = os.date("%Y%m%d_%H%M%S")
    local name = "census_" .. stamp .. ".txt"
    local path = (MOD_DIR and (MOD_DIR .. "\\" .. name)) or name
    local f, err = io.open(path, "w")
    if not f then log("could not write " .. path .. ": " .. tostring(err)); return end
    f:write(line, "\n\n== actor class histogram (count, descending) ==\n")
    local hist = {}
    for _, a in ipairs(d.actors) do local c = classNameOf(a); hist[c] = (hist[c] or 0) + 1 end
    local arr = {}
    for c, n in pairs(hist) do arr[#arr + 1] = { c, n } end
    table.sort(arr, function(a, b) if a[2] ~= b[2] then return a[2] > b[2] end return a[1] < b[1] end)
    for _, e in ipairs(arr) do f:write(string.format("%6d  %s\n", e[2], e[1])) end
    f:write("\n== remaining _UAID_ actors (", #d.uaid, ") ==\n")
    for _, a in ipairs(d.uaid) do f:write(fullNameOf(a), " | ", classNameOf(a), " | ", transformOf(a), "\n") end
    f:write("\n== lifepod / water / sky / manager actors (world transform, root attach parent, socket) ==\n")
    local pats = { "Lifepod", "LifePod", "Ocean", "Sky", "WaterZone", "Biome", "Manager", "MeshBlend", "Scalability" }
    for _, a in ipairs(d.actors) do
        local cn = classNameOf(a)
        local hit = false
        for _, pt in ipairs(pats) do if cn:find(pt, 1, true) then hit = true end end
        if hit then
            local okp, par = pcall(function()
                local rc = a.RootComponent
                local pc = rc:GetAttachParent()
                if not isValid(pc) then return "none" end
                return pc:GetFullName() .. " socket=" .. rc:GetAttachSocketName():ToString()
            end)
            f:write(fullNameOf(a), " | ", cn, " | ", transformOf(a), " | attach=", okp and tostring(par) or "?", "\n")
        end
    end
    f:write("\n== PlayerStart actors ==\n")
    for _, a in ipairs(d.actors) do
        if classNameOf(a):find("PlayerStart", 1, true) then
            local ok, tag = pcall(function() return a.PlayerStartTag:ToString() end)
            f:write(fullNameOf(a), " | ", classNameOf(a), " | ", transformOf(a), " | tag=", ok and tostring(tag) or "?", "\n")
        end
    end
    f:write("\n== _Generated_ levels (", #d.genLevels, ") ==\n")
    for _, n in ipairs(d.genLevels) do f:write(n, "\n") end
    f:write("\n== ModActor DestroyedClassNames ==\n")
    if d.mod then
        local ok, e = pcall(function()
            local names = d.mod.DestroyedClassNames
            names:ForEach(function(i, elem)
                f:write(elem:get():ToString(), "\n")
            end)
        end)
        if not ok then f:write("ERROR reading DestroyedClassNames: ", tostring(e), "\n") end
    else
        f:write("(ModActor not found)\n")
    end
    f:close()
    log("wrote " .. name)
end

local function sampleNow(withReport)
    ExecuteInGameThread(function()
        local ok, err = pcall(function()
            local line, d = sample()
            if withReport then writeReport(line, d) end
        end)
        if not ok then log("sample error: " .. tostring(err)) end
    end)
end

-- ---------------------------------------------------------------- scheduling (only after arming)
local SCHEDULE = { 1, 5, 15, 30, 60, 120 }
local function scheduleAt(myGen, atSec)
    local delay = atSec - (os.time() - armTime)
    if delay < 0 then delay = 0 end
    ExecuteWithDelay(delay * 1000, function()
        if myGen ~= gen or not armed then return end
        sampleNow(atSec == 15)
        if atSec >= 120 then scheduleAt(myGen, atSec + 120) end
    end)
end

RegisterHook("/Script/Engine.PlayerController:ClientRestart", function(ctx)
    local ok, world = pcall(function() return ctx:get():GetWorld():GetFullName() end)
    gen = gen + 1
    if ok and type(world) == "string" and not world:find("L_ClientLobby", 1, true) then
        armed = true
        armTime = os.time()
        armWorld = world:match("([^%.:/ ]+)$") or world
        log("armed in " .. world)
        for _, s in ipairs(SCHEDULE) do scheduleAt(gen, s) end
        -- automated tests: one report 20 s after arming (besides F5)
        local myGen = gen
        ExecuteWithDelay(20000, function()
            if myGen == gen and armed then sampleNow(true) end
        end)
    else
        if armed then log("disarmed (world " .. tostring(world) .. ")") end
        armed = false
    end
end)

log("loaded (read-only census; arms in any world except L_ClientLobby)")

-- opt-in diagnostic census (diag.flag next to Scripts/ turns it on; see diag.lua)
local okd, errd = pcall(require, "diag")
if not okd then log("diag.lua not loaded: " .. tostring(errd)) end

-- opt-in test: set r.VT.IOPriority_HighPagePri early + read-back log (vtprio.flag next to Scripts/ turns it on; see vtprio.lua)
local okv, errv = pcall(require, "vtprio")
if not okv then log("vtprio.lua not loaded: " .. tostring(errv)) end
