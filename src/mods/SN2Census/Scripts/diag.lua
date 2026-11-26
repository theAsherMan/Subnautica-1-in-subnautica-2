-- SN2Census diagnostic census (opt-in, 2026-11-24): "what are the ~22.8k objects in the lobby -> L_SN2World FinishDestroy queue".
-- Enabled ONLY when the flag file <mod dir>/diag.flag exists; its first line is the output directory (forward slashes). Without the flag nothing is hooked
-- into any behaviour (the hooks below return at once). Read-only: walks GUObjectArray with ForEachUObject, never changes an object.
--   1. lobby_baseline: 10 s after the lobby LoadMap (only if the current world is L_ClientLobby): class counts (top 30) + worlds.
--   2. pre_travel: in RegisterLoadMapPreHook while the current world is still L_ClientLobby (= the lobby -> L_SN2World travel):
--      class counts (top 30) + detail (outer-world / outer-class split, RF_ flags, 20 sample names) for SphereComponent, BodySetup and the top 5 classes.
-- Reports: <dir>/census_<label>.txt, summary lines in UE4SS.log ([SN2Census] diag ...). Timing of each walk logged (os.clock) - the walk delays the game thread.
local M = {}
local MOD = "SN2Census"
local function log(msg) print(string.format("[%s] diag %s\n", MOD, tostring(msg))) end

local function scriptDir()
    local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
    return src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
end
local MOD_DIR = scriptDir()

local function outDir()
    if not MOD_DIR then return nil end
    local f = io.open(MOD_DIR .. "/diag.flag", "r")
    if not f then return nil end
    local d = f:read("*l"); f:close()
    if not d or d == "" then return nil end
    return (d:gsub("\\", "/"):gsub("%s+$", ""))
end

-- second line of diag.flag "nocensus" = thread-sampler runs: no census at all (the walks would perturb the game thread)
local function noCensus()
    if not MOD_DIR then return false end
    local f = io.open(MOD_DIR .. "/diag.flag", "r")
    if not f then return false end
    f:read("*l"); local l2 = f:read("*l"); f:close()
    return l2 ~= nil and l2:find("nocensus", 1, true) ~= nil
end

-- diag.flag line 2 containing "classmap" (with nocensus): the lobby baseline writes only <dir>/classmap.tsv (stack-sampler tier 2)
local function wantClassmap()
    if not MOD_DIR then return false end
    local f = io.open(MOD_DIR .. "/diag.flag", "r")
    if not f then return false end
    f:read("*l"); local l2 = f:read("*l"); f:close()
    return l2 ~= nil and l2:find("classmap", 1, true) ~= nil
end

local function currentWorldName()
    local ok, n = pcall(function() return require("UEHelpers").GetWorld():GetFullName() end)
    if ok and type(n) == "string" then return n end
    return ""
end

local RF = { Transient = 0x2, BeginDestroyed = 0x8000, FinishDestroyed = 0x10000, MirroredGarbage = 0x40000000 }
local PRESET = { SphereComponent = true, BodySetup = true }

local function top(tbl, n)
    local arr = {}
    for k, v in pairs(tbl) do arr[#arr + 1] = { k = k, v = v } end
    table.sort(arr, function(a, b) if a.v ~= b.v then return a.v > b.v end return tostring(a.k) < tostring(b.k) end)
    local out = {}
    for i = 1, math.min(n, #arr) do out[i] = arr[i] end
    return out
end

local function classNameOfObj(o)
    local ok, n = pcall(function() return o:GetClass():GetFName():ToString() end)
    return ok and n or "<noclass>"
end

-- outer chain of o: returns first outer's class, world name, outermost name, chain string
local function chainOf(o)
    local first, world, last, parts = "-", "-", "-", {}
    local cur, depth = nil, 0
    local ok = pcall(function() cur = o:GetOuter() end)
    while ok and cur and depth < 10 do
        local valid = false
        pcall(function() valid = cur:IsValid() end)
        if not valid then break end
        local cn = classNameOfObj(cur)
        local nm = "?"
        pcall(function() nm = cur:GetFName():ToString() end)
        if depth == 0 then first = cn end
        parts[#parts + 1] = cn
        if cn == "World" then world = nm end
        last = nm
        local nxt = nil
        local ok2 = pcall(function() nxt = cur:GetOuter() end)
        if not ok2 then break end
        cur = nxt; depth = depth + 1
    end
    return first, world, last, table.concat(parts, "<")
end

local function hasFlag(o, mask)
    local ok, v = pcall(function() return o:HasAnyFlags(mask) end)
    if not ok then return nil end
    return v == true
end

local function census(label, full)
    local dir = outDir()
    if not dir then return end
    local out = {}
    local function w(s) out[#out + 1] = s end
    local t0 = os.clock()
    w(string.format("# SN2Census diag census '%s' at UTC %s (game-log clock), world before: %s", label, os.date("!%H.%M.%S"), currentWorldName()))
    -- walk 1: counts per class (key = class address)
    local counts, names, worlds, total, noclass = {}, {}, {}, 0, 0
    ForEachUObject(function(obj)
        total = total + 1
        local ok, c = pcall(function() return obj:GetClass() end)
        if not ok or c == nil then noclass = noclass + 1; return end
        local okA, a = pcall(function() return c:GetAddress() end)
        if not okA then noclass = noclass + 1; return end
        local n = counts[a]
        if n then counts[a] = n + 1 else
            counts[a] = 1
            local okN, nm = pcall(function() return c:GetFName():ToString() end)
            names[a] = okN and nm or "?"
            if names[a] == "World" then worlds[#worlds + 1] = obj end
        end
    end)
    local t1 = os.clock()
    local byName = {}
    for a, n in pairs(counts) do byName[names[a]] = (byName[names[a]] or 0) + n end
    w(string.format("# walk1 (class counts): %.2f s, objects %d, without readable class %d, distinct classes %d", t1 - t0, total, noclass, (function() local k = 0 for _ in pairs(counts) do k = k + 1 end return k end)()))
    w("## top 30 classes by count")
    for _, e in ipairs(top(byName, 30)) do w(string.format("%8d  %s", e.v, e.k)) end
    w(string.format("## SphereComponent=%d BodySetup=%d World=%d", byName.SphereComponent or 0, byName.BodySetup or 0, byName.World or 0))
    w("## World objects (class World; first 20 seen)")
    for i = 1, math.min(20, #worlds) do
        local ok, fn = pcall(function() return worlds[i]:GetFullName() end)
        w("  " .. (ok and fn or "?"))
    end
    if full then
        -- walk 2: detail for SphereComponent, BodySetup, top 5 classes
        local focus = {}
        for nm in pairs(PRESET) do focus[nm] = true end
        for _, e in ipairs(top(byName, 5)) do focus[e.k] = true end
        local focusAddr = {}
        for a, nm in pairs(names) do if focus[nm] then focusAddr[a] = nm end end
        local split, flags, samples, fcount = {}, {}, {}, {}
        local sphereSamples = 0
        ForEachUObject(function(obj)
            local ok, c = pcall(function() return obj:GetClass() end)
            if not ok or c == nil then return end
            local okA, a = pcall(function() return c:GetAddress() end)
            if not okA then return end
            local nm = focusAddr[a]
            if not nm then return end
            fcount[nm] = (fcount[nm] or 0) + 1
            local first, world, last = chainOf(obj)
            local key = nm .. " | world=" .. world .. " | outer1=" .. first .. " | outermost=" .. last
            split[key] = (split[key] or 0) + 1
            local fl = flags[nm]
            if not fl then fl = { n = 0 }; flags[nm] = fl end
            fl.n = fl.n + 1
            for fname, mask in pairs(RF) do
                local h = hasFlag(obj, mask)
                if h == nil then fl[fname] = -1 elseif h then fl[fname] = (fl[fname] or 0) + 1 end
            end
            if nm == "SphereComponent" and sphereSamples < 20 then
                sphereSamples = sphereSamples + 1
                local okF, fn = pcall(function() return obj:GetFullName() end)
                local ownerCls = "?"
                pcall(function() ownerCls = classNameOfObj(obj:GetOuter()) end)
                local _, _, _, chain = chainOf(obj)
                samples[#samples + 1] = string.format("  %s | owner class %s | chain %s", okF and fn or "?", ownerCls, chain)
            end
        end)
        local t2 = os.clock()
        w(string.format("# walk2 (detail): %.2f s", t2 - t1))
        w("## detail classes: " .. (function() local l = {} for k in pairs(focus) do l[#l + 1] = k .. "=" .. tostring(fcount[k] or 0) end table.sort(l) return table.concat(l, ", ") end)())
        w("## flags per class (HasAnyFlags; -1 = call failed; masks Transient 0x2, BeginDestroyed 0x8000, FinishDestroyed 0x10000, MirroredGarbage 0x40000000)")
        for nm, fl in pairs(flags) do
            local l = {}
            for fname in pairs(RF) do l[#l + 1] = fname .. "=" .. tostring(fl[fname] or 0) end
            table.sort(l)
            w(string.format("  %s n=%d %s", nm, fl.n, table.concat(l, " ")))
        end
        w("## split by class | world | first outer class | outermost (top 15 per class)")
        for nm in pairs(focus) do
            local sub = {}
            for k, v in pairs(split) do if k:sub(1, #nm + 3) == nm .. " | " then sub[k] = v end end
            w("# " .. nm)
            for _, e in ipairs(top(sub, 15)) do w(string.format("%8d  %s", e.v, e.k)) end
        end
        w("## 20 SphereComponent samples (full name | owner class | outer chain)")
        for _, s in ipairs(samples) do w(s) end
    end
    local tEnd = os.clock()
    w(string.format("# total census time %.2f s", tEnd - t0))
    local f = io.open(dir .. "/census_" .. label .. ".txt", "w")
    if f then f:write(table.concat(out, "\n") .. "\n"); f:close() end
    log(string.format("%s: %d objects, %.2f s total, SphereComponent=%d BodySetup=%d (report census_%s.txt)", label, total, tEnd - t0, byName.SphereComponent or 0, byName.BodySetup or 0, label))
    -- also the first lines to UE4SS.log in case the report file cannot be written
    for i = 1, math.min(12, #out) do log(out[i]) end
end

-- classmap.tsv: one row per distinct ClassPrivate seen (hex GetAddress() of the UClass TAB class full name); objaddrs.tsv: first 40 objects
-- (hex object address, hex class address, class name) so the stack sampler can verify the UObjectBase offsets (ClassPrivate at +0x10).
local function classmap()
    local dir = outDir()
    if not dir then return end
    local t0 = os.clock()
    local seen, rows, objs, total = {}, {}, {}, 0
    ForEachUObject(function(obj)
        total = total + 1
        local ok, c = pcall(function() return obj:GetClass() end)
        if not ok or c == nil then return end
        local okA, a = pcall(function() return c:GetAddress() end)
        if not okA or not a then return end
        if not seen[a] then
            seen[a] = true
            local okN, nm = pcall(function() return c:GetFullName() end)
            rows[#rows + 1] = string.format("%X\t%s", a, okN and nm or "?")
        end
        if #objs < 40 and total % 997 == 0 then
            local okO, oa = pcall(function() return obj:GetAddress() end)
            if okO and oa then objs[#objs + 1] = string.format("%X\t%X\t%s", oa, a, classNameOfObj(obj)) end
        end
    end)
    local f = io.open(dir .. "/classmap.tsv", "w")
    if f then f:write(table.concat(rows, "\n") .. "\n"); f:close() end
    local g = io.open(dir .. "/objaddrs.tsv", "w")
    if g then g:write(table.concat(objs, "\n") .. "\n"); g:close() end
    log(string.format("classmap: %d objects, %d classes, %d object addresses, %.2f s", total, #rows, #objs, os.clock() - t0))
end

local baselineScheduled, baselineDone, preDone = false, false, false

RegisterLoadMapPostHook(function(...)
    if not outDir() or baselineScheduled then return end
    local cmapOnly = noCensus() and wantClassmap()
    if noCensus() and not cmapOnly then return end
    baselineScheduled = true
    log("lobby LoadMap done, baseline " .. (cmapOnly and "classmap" or "census") .. " in 10 s")
    ExecuteWithDelay(10000, function()
        ExecuteInGameThread(function()
            if currentWorldName():find("L_ClientLobby", 1, true) then
                local ok, e = pcall(cmapOnly and classmap or census, "lobby_baseline", false)
                if not ok then log("baseline census error: " .. tostring(e)) end
                baselineDone = true
            else
                log("baseline skipped, current world " .. currentWorldName())
                baselineScheduled = false
            end
        end)
    end)
end)

RegisterLoadMapPreHook(function(...)
    if not outDir() or preDone or noCensus() then return end
    local w = currentWorldName()
    log("LoadMap pre-hook, current world " .. w .. " baselineDone=" .. tostring(baselineDone))
    if w:find("L_ClientLobby", 1, true) then
        preDone = true
        local ok, e = pcall(census, "pre_travel", true)
        if not ok then log("pre_travel census error: " .. tostring(e)) end
    end
end)

log("loaded (opt-in: active only while diag.flag exists)")
return M
