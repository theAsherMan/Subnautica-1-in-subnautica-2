-- SN2BugShot shared report code. Returns report(source) -> ok, id_or_err. Used by main.lua (F1) and by the SN2AutoTest verb `bugshot`.
-- Writes <mod>\reports\<id>.json atomically (tmp + rename); src/tools/bugshot_watch.sh collects it (screenshot + logs) and removes it.
-- Every read is pcall-wrapped: a missing field is fine. No game state is changed except the optional engine screenshot console command.
local MOD = "SN2BugShot"
local ENGINE_SHOT = true   -- also ask the engine for a screenshot (HighResShot); the watcher captures the window regardless
local function log(m) print(string.format("[%s] %s\n", MOD, tostring(m))) end

local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
local MOD_DIR = src:match("^(.*)[\\/]Scripts[\\/][^\\/]+$")
local REPORT_DIR = MOD_DIR and (MOD_DIR .. "\\reports") or "reports"

local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, v = pcall(function() return o:IsValid() end)
    return ok and v == true
end
local function nameOf(o)
    local ok, n = pcall(function() return o:GetFName():ToString() end)
    return ok and n or "?"
end
local function fullOf(o)
    local ok, n = pcall(function() return o:GetFullName() end)
    return ok and n or "?"
end
local UEHelpers = require("UEHelpers")
local function getPC()
    local ok, pc = pcall(UEHelpers.GetPlayerController)
    if ok and isValid(pc) then return pc end
    return nil
end

-- ---------------------------------------------------------------- minimal JSON encoder (arrays = tables with t[1]; keys sorted)
local function jstr(s)
    s = tostring(s)
    s = s:gsub('[%c"\\]', function(c)
        if c == '"' then return '\\"' elseif c == "\\" then return "\\\\" elseif c == "\n" then return "\\n" end
        return string.format("\\u%04x", c:byte())
    end)
    return '"' .. s .. '"'
end
local function jenc(v)
    local t = type(v)
    if t == "number" then
        if v ~= v or v == math.huge or v == -math.huge then return "null" end
        if v == math.floor(v) and math.abs(v) < 1e15 then return string.format("%d", v) end
        return string.format("%.4f", v)
    elseif t == "boolean" then return tostring(v)
    elseif t == "string" then return jstr(v)
    elseif t == "table" then
        if v[1] ~= nil then
            local o = {}
            for i = 1, #v do o[i] = jenc(v[i]) end
            return "[" .. table.concat(o, ",") .. "]"
        end
        local keys = {}
        for k in pairs(v) do keys[#keys + 1] = tostring(k) end
        table.sort(keys)
        local o = {}
        for _, k in ipairs(keys) do o[#o + 1] = jstr(k) .. ":" .. jenc(v[k]) end
        return "{" .. table.concat(o, ",") .. "}"
    end
    return "null"
end

local function vec(v)
    if v == nil then return nil end
    local ok, r = pcall(function() return { x = v.X, y = v.Y, z = v.Z } end)
    if ok and type(r.x) == "number" then return r end
    return nil
end
local function rot(r)
    local ok, o = pcall(function() return { pitch = r.Pitch, yaw = r.Yaw, roll = r.Roll } end)
    if ok and type(o.pitch) == "number" then return o end
    return nil
end
local function toUnity(l) return { x = l.y / 100, y = l.z / 100, z = l.x / 100 } end

local function toList(arr)
    local out = {}
    if arr == nil then return out end
    pcall(function()
        arr:ForEach(function(_, e)
            local v = e
            pcall(function() local g = e:get(); if g ~= nil then v = g end end)
            out[#out + 1] = v
        end)
    end)
    return out
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

local function hasTag(a, want)
    local found = false
    pcall(function()
        local n = a.Tags:GetArrayNum()
        for i = 1, n do
            local okT, s = pcall(function() return a.Tags[i]:ToString() end)
            if okT and s == want then found = true; break end
        end
    end)
    return found
end

-- crosshair trace (from SN2TerrainEdit crosshairHit, extended): returns table or nil
local function crosshair(pc)
    local ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary")
    local kml = StaticFindObject("/Script/Engine.Default__KismetMathLibrary")
    local cam = pc.PlayerCameraManager
    local start = cam:GetCameraLocation()
    local fwd = kml:GetForwardVector(cam:GetCameraRotation())
    local finish = { X = start.X + fwd.X * 100000, Y = start.Y + fwd.Y * 100000, Z = start.Z + fwd.Z * 100000 }
    local col = { R = 0, G = 0, B = 0, A = 0 }
    local hit = {}
    local ok = ksl:LineTraceSingle(pc.Pawn, start, finish, 0, true, {}, 0, hit, true, col, col, 0.0)
    if not ok then return { hit = false } end
    local actor, comp
    pcall(function() actor = hit.HitObjectHandle.ReferenceObject:Get() end)
    if not isValid(actor) then pcall(function() actor = hit.HitObjectHandle.Actor:Get() end) end
    pcall(function() comp = hit.Component:Get() end)
    local okO, owner = pcall(function() return actor:GetOwner() end)
    if okO and isValid(owner) then
        local cname = ""
        pcall(function() cname = actor:GetClass():GetFName():ToString() end)
        if cname:find("Component") then
            if not isValid(comp) then comp = actor end
            actor = owner
        end
    end
    local r = { hit = true }
    if isValid(actor) then
        r.actor = nameOf(actor)
        pcall(function() r.class = actor:GetClass():GetFName():ToString() end)
        r.snTerrain = hasTag(actor, "SN1Terrain")
        pcall(function()
            local l = actor:K2_GetActorLocation(); r.actorLoc = vec(l)
        end)
    end
    if isValid(comp) then
        r.component = nameOf(comp)
        pcall(function() r.mesh = comp.StaticMesh:GetFullName() end)
    end
    pcall(function() r.distance = hit.Distance end)
    pcall(function() r.impact = vec(hit.ImpactPoint) end)
    pcall(function() r.normal = vec(hit.ImpactNormal) end)
    return r
end

local function attrs(pawn)
    local asc
    for _, pn in ipairs({ "UWEAbilitySystemComponent", "AbilitySystemComponent" }) do
        if not isValid(asc) then pcall(function() asc = pawn[pn] end) end
    end
    if not isValid(asc) then pcall(function() asc = pawn:GetAbilitySystemComponent() end) end
    if not isValid(asc) then return nil end
    local want = { Oxygen = "oxygen", MaxOxygen = "maxOxygen", Health = "health", MaxHealth = "maxHealth", Food = "food", Water = "water" }
    local out = {}
    for _, s in ipairs(toList(asc.SpawnedAttributes)) do
        if isValid(s) then
            pcall(function()
                s:GetClass():ForEachProperty(function(p)
                    local pname = "?"
                    pcall(function() pname = p:GetFName():ToString() end)
                    local key = want[pname]
                    if key and out[key] == nil then
                        local okd, d = pcall(function() return s[pname] end)
                        if okd and type(d) == "userdata" then
                            local cur
                            pcall(function() cur = d.CurrentValue end)
                            if type(cur) == "number" then out[key] = cur end
                        end
                    end
                end)
            end)
        end
    end
    return out
end

local seq = 0
local lastT = 0
local function capture(source)
    local now = os.clock()
    if source ~= "test" and now - lastT < 1.0 then return nil, "debounce" end
    lastT = now
    seq = seq + 1
    local id = string.format("%s_%03d", os.date("%Y%m%d_%H%M%S"), seq)
    local R = { id = id, source = source or "key", wallTime = os.date("%Y-%m-%d %H:%M:%S"), captureEpoch = os.time(), errors = {} }
    local function try(name, fn)
        local ok, err = pcall(fn)
        if not ok then R.errors[#R.errors + 1] = name .. ": " .. tostring(err):sub(1, 120) end
    end
    local pc = getPC()
    local pawn
    if pc then try("pawn", function() pawn = pc.Pawn end) end
    if not isValid(pawn) then pawn = nil end
    local world
    try("world", function() world = pc:GetWorld() end)
    try("map", function()
        R.map = world:GetFName():ToString()
        R.mapFull = world:GetFullName()
    end)
    try("gameTime", function()
        R.gameTime = StaticFindObject("/Script/Engine.Default__GameplayStatics"):GetTimeSeconds(world)
    end)
    try("ue4ss", function() R.ue4ssVersion = UE4SS and UE4SS.GetVersion and table.concat({ UE4SS.GetVersion() }, ".") or nil end)
    local loc
    if pawn then
        try("pawnLoc", function()
            loc = vec(pawn:K2_GetActorLocation())
            R.ue = loc
            R.unity = toUnity(loc)
            R.depth = -loc.z / 100
        end)
        try("pawnRot", function() R.pawnRot = rot(pawn:K2_GetActorRotation()) end)
        try("velocity", function() R.velocity = vec(pawn:GetVelocity()) end)
        try("attrs", function() R.attrs = attrs(pawn) end)
        try("moveMode", function() R.movementMode = pawn.CharacterMovement.MovementMode end)
    else
        R.errors[#R.errors + 1] = "no pawn"
    end
    if pc then
        try("camera", function()
            local cam = pc.PlayerCameraManager
            R.camera = { loc = vec(cam:GetCameraLocation()), rot = rot(cam:GetCameraRotation()) }
        end)
        try("crosshair", function() R.crosshair = crosshair(pc) end)
    end
    -- vehicle: nearest Tadpole + whether the pawn is attached to / seated in something
    try("vehicle", function()
        local v = { inVehicle = false }
        if pawn then
            pcall(function()
                local p = pawn:GetAttachParentActor()
                if isValid(p) then v.attachedTo = nameOf(p); v.inVehicle = true end
            end)
        end
        local best, bd
        for _, t in ipairs(findAll("SN2Tadpole")) do
            pcall(function()
                local l = vec(t:K2_GetActorLocation())
                local d = loc and math.sqrt((l.x - loc.x) ^ 2 + (l.y - loc.y) ^ 2 + (l.z - loc.z) ^ 2) or 0
                if not bd or d < bd then best, bd = l, d end
            end)
        end
        if best then v.tadpoleLoc = best; v.tadpoleDistance = bd end
        R.vehicle = v
    end)
    -- nearest SN1Terrain tile + class histogram within 50 m
    if loc then
        try("nearby", function()
            local hist, bestName, bestD = {}, nil, nil
            for _, a in ipairs(findAll("Actor")) do
                pcall(function()
                    local l = a:K2_GetActorLocation()
                    local dx, dy, dz = l.X - loc.x, l.Y - loc.y, l.Z - loc.z
                    local d = math.sqrt(dx * dx + dy * dy + dz * dz)
                    if d <= 5000 then
                        local cn = a:GetClass():GetFName():ToString()
                        hist[cn] = (hist[cn] or 0) + 1
                    end
                    if hasTag(a, "SN1Terrain") and (not bestD or d < bestD) then bestName, bestD = nameOf(a), d end
                end)
            end
            local arr = {}
            for k, n in pairs(hist) do arr[#arr + 1] = { class = k, n = n } end
            table.sort(arr, function(a, b) if a.n ~= b.n then return a.n > b.n end return a.class < b.class end)
            local top = {}
            for i = 1, math.min(10, #arr) do top[i] = arr[i] end
            R.nearbyClasses50m = top
            R.nearestSN1Terrain = bestName and { name = bestName, distanceM = bestD / 100 } or nil
        end)
    end
    -- engine screenshot request (asynchronous: the file appears a frame or more later)
    if ENGINE_SHOT and pc then
        local ok, err = pcall(function()
            StaticFindObject("/Script/Engine.Default__KismetSystemLibrary"):ExecuteConsoleCommand(world, "HighResShot 1", pc)
        end)
        R.engineShot = { cmd = "HighResShot 1", called = ok, err = (not ok) and tostring(err):sub(1, 120) or nil }
    end
    R.loc = loc
    return R, id
end

local function writeFile(path, text)
    local f = io.open(path, "w")
    if not f then
        pcall(os.execute, 'mkdir "' .. REPORT_DIR .. '" >nul 2>&1')
        f = io.open(path, "w")
    end
    if not f then return false end
    f:write(text); f:close()
    return true
end

-- <id>.json.pending marks a report whose popup is still open (the watcher ignores it); finalize replaces it with <id>.json
local function pending(R)
    local ok = writeFile(REPORT_DIR .. "\\" .. R.id .. ".json.pending", jenc({ id = R.id, pending = true, wallTime = R.wallTime }))
    if not ok then log("PENDING " .. R.id .. " cannot write") end
    return ok
end

local function finalize(R, description, state)
    local id = R.id
    local loc = R.loc
    R.loc = nil
    R.description = description or ""
    R.descriptionState = state or "nopopup"
    if #R.errors == 0 then R.errors = nil end
    local text = jenc(R)
    local path = REPORT_DIR .. "\\" .. id .. ".json"
    if not writeFile(path .. ".tmp", text) then log("REPORT " .. id .. " FAILED cannot write " .. path); return false, "cannot write" end
    pcall(os.remove, path)
    local okR, errR = os.rename(path .. ".tmp", path)
    if not okR then log("REPORT " .. id .. " FAILED rename " .. tostring(errR)); return false, "rename" end
    pcall(os.remove, path .. ".pending")
    log(string.format("REPORT %s map=%s ue=%s depth=%s hit=%s desc=%s len=%d", id, tostring(R.map),
        loc and string.format("(%.0f,%.0f,%.0f)", loc.x, loc.y, loc.z) or "?",
        R.depth and string.format("%.1f", R.depth) or "?",
        R.crosshair and (R.crosshair.actor or (R.crosshair.hit and "?" or "none")) or "?",
        R.descriptionState, #R.description))
    return true, id
end

-- synchronous report without popup (SN2AutoTest verb `bugshot`)
local function report(source)
    local R, id = capture(source)
    if not R then return false, id end
    return finalize(R, "", "nopopup")
end

return report, { capture = capture, pending = pending, finalize = finalize, getPC = getPC, isValid = isValid, log = log }
