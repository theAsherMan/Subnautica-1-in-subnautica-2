-- TEMPORARY diagnostic (2026-11-27, investigator-water2). Run by the verbs uwa1..uwa4 (MODE = "uwaN") of SN2AutoTest. In-memory only.
--   uwa1 : read the EFFECTIVE parameter values (walks ScalarParameterValues/VectorParameterValues up the parent chain; @N = depth where found) + parent chain of each region material
--   uwa2 : hide every region's WaterStaticMeshComponent (SetVisibility false)
--   uwa3 : show them again, give every region a new MID whose parent is the baked MIC MI_WV_Ocean (loaded by LoadAsset), then read back
--   uwa4 : show again; every region gets a fresh MID of the game's MI_OceanVolume (skipping our baked MIC) with the L_Main values pushed via Set*ParameterValue(FName), then read back
local function P(s) log("UWA " .. MODE .. " " .. s) end
local S = { "BiomeExtinctionDistanceDirectionalLight", "BiomeExtinctionDistanceSkylight", "BiomeAlbedoDesaturation", "BiomeAlbedoBrightness",
    "BiomeNeutralizationNear", "BiomeNeutralizationFar", "WaterFogDistanceRcp", "WaterFogDistance", "WaterFogThickness", "BaseWaterFogThickness",
    "WaterFogOpacityWeight", "CurrentWaterBodyIndex", "CurrentWaterBodyBlendType" }
local V = { "BiomeExtinctionColorDirectionalLight", "BiomeExtinctionColorSkylight", "BiomeAlbedo", "BiomeAlbedoPower", "BiomeAlbedoTint", "BiomeEmissive" }
local SV = { BiomeExtinctionDistanceDirectionalLight = 12.5, BiomeExtinctionDistanceSkylight = 17.5, BiomeAlbedoDesaturation = 0, BiomeAlbedoBrightness = 1,
    BiomeNeutralizationNear = 0, BiomeNeutralizationFar = 0, WaterFogDistanceRcp = 1 / 7500, WaterFogDistance = 7500, WaterFogThickness = 10,
    BaseWaterFogThickness = 4, WaterFogOpacityWeight = 1, CurrentWaterBodyIndex = 0, CurrentWaterBodyBlendType = 1 }
local VV = { BiomeExtinctionColorDirectionalLight = { 0.90725, 0.94516, 0.955, 1 }, BiomeExtinctionColorSkylight = { 0.90725, 0.94516, 0.955, 1 },
    BiomeAlbedo = { 0.1, 0.295, 1, 1 }, BiomeAlbedoPower = { 1, 1, 1, 1 }, BiomeAlbedoTint = { 1, 1, 1, 1 }, BiomeEmissive = { 0, 0, 0, 1 } }

local regions = {}
local seen = {}
for _, cls in ipairs({ "BP_UWEOceanBiomeRegionActor_C", "BP_UWEWaterBiomeRegionActor_C" }) do
    for _, a in ipairs(findAll(cls)) do
        local n = nameOf(a)
        if not seen[n] then
            seen[n] = true
            local c = nil
            pcall(function() c = a.WaterStaticMeshComponent end)
            if isValid(c) then regions[#regions + 1] = { name = n, actor = a, comp = c } end
        end
    end
end
P("regions=" .. #regions)

local function chain(m)
    local parts = {}
    local cur = m
    for _ = 1, 6 do
        if not isValid(cur) then break end
        local o = ""
        pcall(function()
            local bo = cur.BasePropertyOverrides
            o = string.format(" [ovrBlend=%s blend=%s]", tostring(bo.bOverride_BlendMode), tostring(bo.BlendMode))
        end)
        parts[#parts + 1] = str(cur:GetFullName()):gsub("^%S+ ", "") .. o
        local nxt = nil
        pcall(function() nxt = cur.Parent end)
        cur = nxt
    end
    return table.concat(parts, " -> ")
end

local function readEff(r)
    local m = nil
    pcall(function() m = r.comp:GetMaterial(0) end)
    if not isValid(m) then P(r.name .. " no material"); return end
    P(r.name .. " class=" .. str(try(function() return m:GetClass():GetFName():ToString() end)) .. " chain: " .. chain(m))
    pcall(function() P(r.name .. " base=" .. str(m:GetBaseMaterial():GetFullName())) end)
    -- effective value = own override, else parent's, ... (arrays read directly: K2_GetScalarParameterValue hung the game thread, run 20261127_173849)
    local function lookup(arrName, key)
        local cur = m
        for depth = 0, 5 do
            if not isValid(cur) then break end
            local arr = nil
            pcall(function() arr = cur[arrName] end)
            if arr then
                local n = 0
                pcall(function() n = arr:GetArrayNum() end)
                for i = 1, n do
                    local nm, val = nil, nil
                    pcall(function() nm = str(arr[i].ParameterInfo.Name); val = arr[i].ParameterValue end)
                    if nm == key then return val, depth end
                end
            end
            local nxt = nil
            pcall(function() nxt = cur.Parent end)
            cur = nxt
        end
        return nil, -1
    end
    local parts = {}
    for _, k in ipairs(S) do
        local v, d = lookup("ScalarParameterValues", k)
        parts[#parts + 1] = k .. "=" .. (v and string.format("%.6g", v) or "MISSING") .. "@" .. d
    end
    P(r.name .. " EFF scalars " .. table.concat(parts, " "))
    parts = {}
    for _, k in ipairs(V) do
        local v, d = lookup("VectorParameterValues", k)
        local s2 = "MISSING"
        if v then pcall(function() s2 = string.format("(%.4g,%.4g,%.4g,%.4g)", v.R, v.G, v.B, v.A) end) end
        parts[#parts + 1] = k .. "=" .. s2 .. "@" .. d
    end
    P(r.name .. " EFF vectors " .. table.concat(parts, " "))
end

-- which regions to read: the ocean ones + the first 2 others
local function toRead()
    local out, others = {}, 0
    for _, r in ipairs(regions) do
        if r.name:find("Ocean") or r.name:find("CAT_0") then out[#out + 1] = r
        elseif others < 2 then others = others + 1; out[#out + 1] = r end
    end
    return out
end

-- ---- uwa8..uwa12 (investigator-water3): component-state diff and in-memory A/B of a fresh cube
local function dumpProps(tag, obj)
    -- every primitive-typed UPROPERTY (bool/int/float/enum read as number/boolean) up the class hierarchy
    local n = 0
    local cls = nil
    pcall(function() cls = obj:GetClass() end)
    local guard = 0
    while cls and isValid(cls) and guard < 12 do
        guard = guard + 1
        local cn = nameOf(cls)
        if cn == "Object" then break end
        pcall(function()
            cls:ForEachProperty(function(p)
                local pn = nameOf(p)
                local okv, v = pcall(function() return obj[pn] end)
                if okv and (type(v) == "number" or type(v) == "boolean") then
                    P(tag .. " PROP " .. cn .. "." .. pn .. "=" .. tostring(v)); n = n + 1
                end
            end)
        end)
        local nxt = nil
        pcall(function() nxt = cls:GetSuperStruct() end)
        cls = nxt
    end
    return n
end
local function dumpComp(tag, c)
    P(tag .. " fullname=" .. str(try(function() return c:GetFullName() end)))
    P(tag .. " mesh=" .. str(try(function() return c:GetStaticMesh():GetFullName() end)) .. " nMats=" .. tostring(try(function() return c:GetNumMaterials() end)))
    P(tag .. " compScale=" .. fmtV(try(function() return c:K2_GetComponentScale() end)) .. " compLoc=" .. fmtV(try(function() return c:K2_GetComponentLocation() end))
        .. " relScale=" .. fmtV(try(function() return c.RelativeScale3D end)) .. " relLoc=" .. fmtV(try(function() return c.RelativeLocation end)))
    P(tag .. " bounds origin=" .. fmtV(try(function() return c.Bounds.Origin end)) .. " extent=" .. fmtV(try(function() return c.Bounds.BoxExtent end))
        .. " radius=" .. tostring(try(function() return c.Bounds.SphereRadius end)))
    P(tag .. " mobility=" .. tostring(try(function() return c.Mobility end)) .. " isVisible=" .. tostring(try(function() return c:IsVisible() end))
        .. " isRegistered=" .. tostring(try(function() return c:IsRegistered() end)) .. " renderStateCreated=" .. tostring(try(function() return c:IsRenderStateCreated() end))
        .. " hasValidSceneProxy=" .. tostring(try(function() return c:HasValidSceneProxy() end)))
    P(tag .. " attachParent=" .. str(try(function() return c:GetAttachParent():GetFullName() end)) .. " owner=" .. str(try(function() return c:GetOwner():GetFullName() end)))
    P(tag .. " ownerHidden=" .. tostring(try(function() return c:GetOwner().bHidden end)) .. " ownerMobilityRoot=" .. tostring(try(function() return c:GetOwner().RootComponent.Mobility end))
        .. " ownerLoc=" .. fmtV(try(function() return c:GetOwner():K2_GetActorLocation() end)))
    local n = dumpProps(tag .. " COMP", c)
    local o = nil
    pcall(function() o = c:GetOwner() end)
    local m = 0
    if isValid(o) then m = dumpProps(tag .. " ACTOR", o) end
    P(tag .. " propsDumped comp=" .. n .. " actor=" .. m)
end
local function pickRegions()
    -- the standalone ocean region (or CAT_0 in L_Main), one SN1 box, the ocean's CAT_0
    local out, seenBox = {}, false
    for _, r in ipairs(regions) do
        if r.name:find("CAT_0") then out[#out + 1] = { tag = "CAT0", r = r }
        elseif r.name:find("Ocean") then out[#out + 1] = { tag = "STANDALONE", r = r }
        elseif not seenBox then seenBox = true; out[#out + 1] = { tag = "BOX", r = r } end
    end
    return out
end
local function dumpMID(tag, m)
    local cur = m
    for depth = 0, 5 do
        if not isValid(cur) then break end
        P(tag .. " MID depth" .. depth .. " " .. str(try(function() return cur:GetFullName() end)))
        for _, an in ipairs({ "ScalarParameterValues", "VectorParameterValues", "TextureParameterValues" }) do
            local arr = nil
            pcall(function() arr = cur[an] end)
            local n = 0
            if arr then pcall(function() n = arr:GetArrayNum() end) end
            local parts = {}
            for i = 1, n do
                local nm, v = nil, nil
                pcall(function() nm = str(arr[i].ParameterInfo.Name) end)
                pcall(function()
                    local pv = arr[i].ParameterValue
                    if type(pv) == "number" then v = string.format("%.6g", pv)
                    elseif an == "VectorParameterValues" then v = string.format("(%.4g,%.4g,%.4g,%.4g)", pv.R, pv.G, pv.B, pv.A)
                    else v = str(pv:GetFullName()) end
                end)
                parts[#parts + 1] = tostring(nm) .. "=" .. tostring(v)
            end
            P(tag .. " MID depth" .. depth .. " " .. an .. "(" .. n .. ") " .. table.concat(parts, " "))
        end
        pcall(function()
            local bo = cur.BasePropertyOverrides
            P(tag .. " MID depth" .. depth .. " BasePropertyOverrides ovrBlend=" .. tostring(bo.bOverride_BlendMode) .. " blend=" .. tostring(bo.BlendMode) .. " ovrTwoSided=" .. tostring(bo.bOverride_TwoSided) .. " twoSided=" .. tostring(bo.TwoSided))
        end)
        local nxt = nil
        pcall(function() nxt = cur.Parent end)
        cur = nxt
    end
end
local function getWorld()
    local pc = getPC()
    local w = nil
    pcall(function() w = pc:GetWorld() end)
    return w, pc
end
local function lmainValuesOn(mid)
    for k, v in pairs(SV) do pcall(function() mid:SetScalarParameterValue(FName(k), v) end) end
    for k, v in pairs(VV) do pcall(function() mid:SetVectorParameterValue(FName(k), { R = v[1], G = v[2], B = v[3], A = v[4] }) end) end
end
local function hideAll()
    for _, r in ipairs(regions) do pcall(function() r.comp:SetVisibility(false, false) end) end
end
local function gameMI()
    local mi = nil
    pcall(function() mi = StaticFindObject("/Game/Materials/Water/MI_OceanVolume.MI_OceanVolume") end)
    if not isValid(mi) then pcall(function() mi = LoadAsset("/Game/Materials/Water/MI_OceanVolume") end) end
    return mi
end
local function stdMesh()
    local mesh = nil
    pcall(function() mesh = StaticFindObject("/Engine/EngineMeshes/s_cube_1cm.s_cube_1cm") end)
    if not isValid(mesh) then pcall(function() mesh = LoadAsset("/Engine/EngineMeshes/s_cube_1cm") end) end
    return mesh
end


-- ---- uwa21..uwa23 (investigator-water4, 2026-11-27): tracker pair table, tracker/water props, (index, blend) sweep on an untracked cube
local function rd0(m, key)
    local arr = nil
    pcall(function() arr = m.ScalarParameterValues end)
    local n = 0
    if arr then pcall(function() n = arr:GetArrayNum() end) end
    for i = 1, n do
        local nm, v = nil, nil
        pcall(function() nm = str(arr[i].ParameterInfo.Name); v = arr[i].ParameterValue end)
        if nm == key then return v end
    end
    return nil
end
if MODE == "uwa21" then
    local pawn = getPawn(getPC())
    local cam = nil
    pcall(function() cam = pawn:K2_GetActorLocation() end)
    local cx, cy, cz = 0, 0, 0
    pcall(function() cx, cy, cz = cam.X, cam.Y, cam.Z end)
    P("CAM " .. fmtV(cam))
    local order, nvol = {}, 0
    for _, s in ipairs(findAll("UWEBiomeTrackerSubsystem")) do
        local vols = nil
        pcall(function() vols = s.Volumes end)
        local n = 0
        pcall(function() n = vols:GetArrayNum() end)
        nvol = n
        for i = 1, n do
            pcall(function() order[nameOf(vols[i]:GetOwner())] = i end)
        end
        P("TRACKER " .. nameOf(s) .. " volumes=" .. n)
    end
    for _, r in ipairs(regions) do
        local m = nil
        pcall(function() m = r.comp:GetMaterial(0) end)
        local idx, blend = "?", "?"
        if isValid(m) then idx = tostring(rd0(m, "CurrentWaterBodyIndex")); blend = tostring(rd0(m, "CurrentWaterBodyBlendType")) end
        local loc = nil
        pcall(function() loc = r.comp:K2_GetComponentLocation() end)
        local dx, dy, dz = 0, 0, 0
        pcall(function() dx, dy, dz = loc.X - cx, loc.Y - cy, loc.Z - cz end)
        local dist = math.sqrt(dx * dx + dy * dy + dz * dz)
        local bvc, wls = nil, nil
        pcall(function() bvc = r.actor.BiomeVolumeComponent; wls = bvc.WaterLightSettings end)
        P(string.format("ROW %s idx=%s blend=%s order=%s volType=%s regType=%s tsp=%s ppPrio=%s ppW=%s vis=%s loc=(%s) dist=%.0f blendType=%s blendDist=%s fogW=%s",
            r.name, idx, blend, tostring(order[r.name]), tostring(try(function() return r.actor.BiomeRegionVolumeType end)), tostring(try(function() return r.actor.BiomeRegionType end)),
            tostring(try(function() return r.comp.TranslucencySortPriority end)), tostring(try(function() return r.actor.PostProcessComponent.Priority end)),
            tostring(try(function() return r.actor.PostProcessComponent.BlendWeight end)), tostring(try(function() return r.comp:IsVisible() end)),
            fmtV(loc), dist, tostring(try(function() return wls.BiomeBlendType end)), tostring(try(function() return wls.BiomeBlendDistance end)),
            tostring(try(function() return wls.WaterFogOpacityWeight end))))
    end
    -- engine water bodies / zones
    local seenWB = {}
    for _, cls in ipairs({ "UWEWaterBodyOcean", "WaterBodyOcean", "WaterBodyLake", "WaterBodyRiver", "WaterBodyCustom", "WaterBody" }) do
        for _, a in ipairs(findAll(cls)) do
            local n = nameOf(a)
            if not seenWB[n] then
                seenWB[n] = true
                local c = nil
                pcall(function() c = a.WaterBodyComponent end)
                P(string.format("WATERBODY %s class=%s actorIdx=%s compIdx=%s type=%s loc=(%s) comp=%s", n, str(try(function() return a:GetClass():GetFName():ToString() end)),
                    tostring(try(function() return a.WaterBodyIndex end)), tostring(try(function() return c.WaterBodyIndex end)), tostring(try(function() return a.WaterBodyType end)),
                    fmtV(try(function() return a:K2_GetActorLocation() end)), isValid(c) and str(c:GetFullName()) or "NONE"))
            end
        end
    end
    for _, z in ipairs(findAll("WaterZone")) do
        P(string.format("WATERZONE %s loc=(%s) extent=%s,%s", nameOf(z), fmtV(try(function() return z:K2_GetActorLocation() end)),
            tostring(try(function() return z.ZoneExtent.X end)), tostring(try(function() return z.ZoneExtent.Y end))))
    end
    P("TABLE done regions=" .. #regions .. " trackerVolumes=" .. nvol)
    return true, "table"
end

if MODE == "uwa1" then
    for _, r in ipairs(toRead()) do readEff(r) end
end
return true, "regions=" .. #regions
