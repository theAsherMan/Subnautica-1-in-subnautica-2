-- SN2Census test-only helper (2026-11-26): set r.VT.IOPriority_HighPagePri early and log the read-back (GC-watchdog fix test 1, research/crashes/gc_watchdog_renderpipe_2026-11-25.md, "H8 series").
-- Active ONLY while <mod dir>/vtprio.flag exists (written by src/tools/gc_ab_test.sh --vt-prio N, removed afterwards). Line 1 = value, line 2 = output dir
-- (forward slashes). Without the flag nothing is hooked, so the product behaviour is unchanged.
-- Steps: (1) from mod start, every 0.5 s (game thread) until the cvar reads back as the wanted value: ExecuteConsoleCommand("r.VT.IOPriority_HighPagePri N")
-- through a PlayerController's world, then GetConsoleVariableIntValue. (2) at every LoadMap pre-hook: log the read-back + world. All lines go to the UE4SS log
-- and to <outdir>/vtprio.txt as "<epoch> <what> <readback> ...".
local MOD = "SN2Census"
local CVAR = "r.VT.IOPriority_HighPagePri"
local function log(msg) print(string.format("[%s] vtprio: %s\n", MOD, tostring(msg))) end

local function scriptDir()
    local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
    return src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
end
local MOD_DIR = scriptDir()

local function readFlag()
    if not MOD_DIR then return nil end
    local f = io.open(MOD_DIR .. "/vtprio.flag", "r")
    if not f then return nil end
    local v = tonumber((f:read("*l") or ""):match("%-?%d+"))
    local dir = (f:read("*l") or ""):gsub("%s+$", "")
    f:close()
    if not v then return nil end
    return v, dir
end

local WANT, OUTDIR = readFlag()
if not WANT then return {} end

local function out(line)
    log(line)
    if OUTDIR and OUTDIR ~= "" then
        local f = io.open(OUTDIR .. "/vtprio.txt", "a")
        if f then f:write(string.format("%d %s\n", os.time(), line)); f:close() end
    end
end

local function ksl() return StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end
local function readBack()
    local ok, v = pcall(function() return ksl():GetConsoleVariableIntValue(CVAR) end)
    if ok and type(v) == "number" then return v end
    return nil
end
-- FindFirstOf / GetWorld never return nil: with no instance they return an INVALID UObject wrapper (null pointer). Calling any method that reaches
-- UObject::GetWorld on it is a native null dereference (UE4SS.dll+0x350206, crash 2026-11-26 at the first Browse, no PlayerController yet); pcall cannot catch it.
-- Always test :IsValid() first.
local function valid(o)
    if o == nil then return false end
    local ok, v = pcall(function() return o:IsValid() end)
    return ok and v == true
end
local function worldName()
    local pc = nil
    pcall(function() pc = FindFirstOf("PlayerController") end)
    if not valid(pc) then return "no-pc" end
    local w = nil
    pcall(function() w = pc:GetWorld() end)
    if not valid(w) then return "no-world" end
    local ok, n = pcall(function() return w:GetFName():ToString() end)
    return ok and n or "?"
end

local done, tries = false, 0
local function attempt()
    tries = tries + 1
    local pc = nil
    pcall(function() pc = FindFirstOf("PlayerController") end)
    if not valid(pc) then pc = nil end
    local world = nil
    if pc then pcall(function() world = pc:GetWorld() end) end
    if not valid(world) then world = nil; pcall(function() world = FindFirstOf("World") end) end
    if not valid(world) then world = nil end
    local before = readBack()
    if world then
        local ok, e = pcall(function() ksl():ExecuteConsoleCommand(world, CVAR .. " " .. tostring(WANT), pc) end)
        if not ok then out("try " .. tries .. " ExecuteConsoleCommand error: " .. tostring(e)) end
    end
    local after = readBack()
    if tries <= 3 or after == WANT then
        out(string.format("try %d set want=%d before=%s after=%s world=%s hasWorld=%s hasPC=%s", tries, WANT, tostring(before), tostring(after), worldName(), tostring(world ~= nil), tostring(pc ~= nil)))
    end
    if after == WANT then done = true; out(string.format("SET_OK readback=%d world=%s tries=%d", after, worldName(), tries)) end
end

local function loop()
    if done or tries >= 400 then
        if not done then out("GAVE_UP after " .. tries .. " tries, readback=" .. tostring(readBack())) end
        return
    end
    ExecuteInGameThread(function() pcall(attempt) end)
    ExecuteWithDelay(500, loop)
end
out(string.format("armed want=%d (no engine call at mod start)", WANT))
local started = false

RegisterLoadMapPostHook(function(...)
    if not started then started = true; ExecuteWithDelay(500, loop) end
    out(string.format("LOADMAP_POST readback=%s world=%s", tostring(readBack()), worldName()))
end)
RegisterLoadMapPreHook(function(...)
    out(string.format("LOADMAP_PRE readback=%s world=%s", tostring(readBack()), worldName()))
end)
return {}
