-- SN2Tadpole spawn logic. Returns function spawn(). Loaded by main.lua (F4) and by the SN2AutoTest verb `tadpole` (test trigger).
-- Order: (a) SN2CheatManager:Spawn("Tadpole"), then move the new SN2Tadpole to the target spot; (b) direct spawn of BP_Tadpole_C.
local TAG = "[SN2Tadpole] "
local function log(m) print(TAG .. tostring(m) .. "\n") end
local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, v = pcall(function() return o:IsValid() end)
    return ok and v == true
end
local function nameOf(o)
    local ok, n = pcall(function() return o:GetFName():ToString() end)
    return ok and n or "?"
end
local function findAll(cn)
    local ok, t = pcall(FindAllOf, cn)
    if not ok or type(t) ~= "table" then return {} end
    local out = {}
    for _, o in ipairs(t) do
        if isValid(o) and not nameOf(o):find("^Default__") then out[#out + 1] = o end
    end
    return out
end
local function loc(a)
    local ok, l = pcall(function() return a:K2_GetActorLocation() end)
    if ok and l then return { X = l.X, Y = l.Y, Z = l.Z } end
    return nil
end
local function fmt(l) return l and string.format("(%.0f,%.0f,%.0f)", l.X, l.Y, l.Z) or "(?)" end
local UEHelpers = require("UEHelpers")
local function pawn()
    local ok, pc = pcall(UEHelpers.GetPlayerController)
    if ok and isValid(pc) then
        local ok2, p = pcall(function() return pc.Pawn end)
        if ok2 and isValid(p) then return p end
    end
    return nil
end
local function allTadpoles()
    local out, seen = {}, {}
    for _, cn in ipairs({ "SN2Tadpole", "BP_Tadpole_C" }) do
        for _, a in ipairs(findAll(cn)) do
            local k = a:GetFullName()
            if not seen[k] then seen[k] = true; out[#out + 1] = a end
        end
    end
    return out
end
local function dist(a, b) local dx, dy, dz = a.X - b.X, a.Y - b.Y, a.Z - b.Z; return math.sqrt(dx * dx + dy * dy + dz * dz) end

-- energy / power diagnostics: property values whose name looks power-related, on the actor and its components
local function powerProbe(a)
    local n = 0
    local function scan(obj, label)
        pcall(function()
            local cls = obj:GetClass()
            while cls and isValid(cls) and n < 40 do
                local cn = nameOf(cls)
                if cn == "Actor" or cn == "Object" then break end
                cls:ForEachProperty(function(p)
                    local pn = nameOf(p)
                    local l = pn:lower()
                    if n < 40 and (l:find("energy") or l:find("power") or l:find("battery") or l:find("charge") or l:find("fuel")) then
                        local okv, v = pcall(function() return obj[pn] end)
                        local s = okv and tostring(v) or "?"
                        log(string.format("POWER %s.%s [%s] = %s", label, pn, cn, s)); n = n + 1
                    end
                end)
                cls = cls:GetSuperStruct()
            end
        end)
    end
    scan(a, nameOf(a))
    pcall(function()
        for _, c in ipairs(a:K2_GetComponentsByClass(StaticFindObject("/Script/Engine.ActorComponent"))) do scan(c, nameOf(c)) end
    end)
    if n == 0 then log("POWER no power-like properties found on " .. nameOf(a)) end
end

local function place(a, target, yaw)
    local ok, err = pcall(function() a:K2_SetActorLocation(target, false, {}, true) end)
    if not ok then log("move failed: " .. tostring(err)) end
    pcall(function() a:K2_SetActorRotation({ Pitch = 0, Yaw = yaw, Roll = 0 }, false) end)
    return ok
end

local function finish(a, how, target, yaw)
    place(a, target, yaw)
    log(string.format("RESULT method=%s class=%s name=%s loc=%s", how, nameOf(a:GetClass()), nameOf(a), fmt(loc(a))))
    powerProbe(a)
end

local function spawn()
    local p = pawn()
    local pod = findAll("BP_StaticLifepod_Surface_C")[1]
    local podLoc, podYaw
    if pod then
        podLoc = loc(pod)
        pcall(function() podYaw = pod:K2_GetActorRotation().Yaw end)
    end
    local src = "lifepod"
    if not podLoc and p then podLoc = loc(p); src = "pawn(fallback)" end
    if not podLoc then log("no lifepod and no pawn; abort"); return false, "no anchor" end
    podYaw = podYaw or 0
    -- already one near the pod?
    local before, beforeSet = allTadpoles(), {}
    for _, t in ipairs(before) do
        beforeSet[t:GetFullName()] = true
        local l = loc(t)
        if l and dist(l, podLoc) <= 10000 then
            log(string.format("Tadpole already within 100 m of the pod: %s at %s; nothing to do", nameOf(t), fmt(l))); return true, "exists"
        end
    end
    -- target: 12 m from the pod, horizontally, opposite the pod's forward axis (best guess for "away from the door"), 3 m below the water surface
    -- (measured 2026-11-23: BP_StaticLifepod_Surface_C actor Z=100 in L_SN2World, BP_Ocean_C at Z=0, so surface = pod Z - 100)
    local yawRad = math.rad(podYaw + 180)
    local target = { X = podLoc.X + 1200 * math.cos(yawRad), Y = podLoc.Y + 1200 * math.sin(yawRad), Z = podLoc.Z - 400 }
    log(string.format("anchor=%s pod=%s podYaw=%.1f target=%s existing=%d", src, fmt(podLoc), podYaw, fmt(target), #before))
    local function direct()
        local cls = StaticFindObject("/Game/Blueprints/Vehicle/BP_Tadpole.BP_Tadpole_C")
        if not isValid(cls) then
            pcall(function() LoadAsset("/Game/Blueprints/Vehicle/BP_Tadpole") end)
            cls = StaticFindObject("/Game/Blueprints/Vehicle/BP_Tadpole.BP_Tadpole_C")
        end
        if not isValid(cls) then log("direct: BP_Tadpole_C class not found"); return end
        local world = UEHelpers.GetWorld()
        local gs = StaticFindObject("/Script/Engine.Default__GameplayStatics")
        local h = math.rad(podYaw + 180) / 2
        local T = { Translation = target, Rotation = { X = 0, Y = 0, Z = math.sin(h), W = math.cos(h) }, Scale3D = { X = 1, Y = 1, Z = 1 } }
        local okA, actor = pcall(function() return gs:BeginDeferredActorSpawnFromClass(world, cls, T, 1, nil, 0) end)
        if not okA or not isValid(actor) then
            okA, actor = pcall(function() return gs:BeginDeferredActorSpawnFromClass(world, cls, T, 1, nil) end)
        end
        if not okA or not isValid(actor) then log("direct: deferred spawn failed: " .. tostring(actor)); return end
        if not pcall(function() gs:FinishSpawningActor(actor, T, 0) end) then pcall(function() gs:FinishSpawningActor(actor, T) end) end
        finish(actor, "direct BP_Tadpole_C", target, podYaw + 180)
    end
    -- (a) the game's cheat
    local cm
    pcall(function() local c = FindFirstOf("SN2CheatManager"); if isValid(c) then cm = c end end)
    if not cm then
        log("no SN2CheatManager; using direct spawn"); direct(); return true, "direct"
    end
    local okC, errC = pcall(function() cm:Spawn("Tadpole") end)
    log("cheat Spawn(\"Tadpole\") " .. (okC and "called" or ("failed: " .. tostring(errC))))
    ExecuteWithDelay(2000, function()
        ExecuteInGameThread(function()
            local new = {}
            for _, t in ipairs(allTadpoles()) do if not beforeSet[t:GetFullName()] then new[#new + 1] = t end end
            log("cheat produced " .. #new .. " new Tadpole actor(s)")
            if #new >= 1 then finish(new[1], "cheat SN2CheatManager:Spawn(Tadpole)", target, podYaw + 180)
            else direct() end
        end)
    end)
    return true, "started"
end
return spawn
