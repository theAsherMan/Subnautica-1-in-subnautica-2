-- TEMPORARY diagnostic (2026-11-28, base-building investigation). Run by verb `buildprobe MODE` of SN2AutoTest. Read-only unless MODE says otherwise.
--   dump  : reflection dump (functions with parameters, properties with types) of the builder / placement / bounds classes, then the live
--           placement-related objects (counts, owners, scalar property values). Lines: BPROBE CLASS/FN/PROP/LIVE/VAL ...
local function P(s) log("BPROBE " .. s) end
local MODE = (ARGS or ""):match("^(%S+)") or "dump"

-- Type-specific accessors are called ONLY on their own property type: UE4SS casts unchecked, and calling GetPropertyClass on another type
-- crashed the game (run 20261128_120333_buildprobe_dump, after SN2BuilderTool.LogMissingRequirementAnalytics).
local OBJ_T = { ObjectProperty = true, ClassProperty = true, SoftObjectProperty = true, SoftClassProperty = true, WeakObjectProperty = true, LazyObjectProperty = true }
local function propType(p)
    local t = try(function() return p:GetClass():GetFName():ToString() end)
    local inner = nil
    if OBJ_T[t] then pcall(function() inner = p:GetPropertyClass():GetFName():ToString() end)
    elseif t == "StructProperty" then pcall(function() inner = p:GetStruct():GetFName():ToString() end)
    elseif t == "EnumProperty" then pcall(function() inner = p:GetEnum():GetFName():ToString() end)
    elseif t == "ArrayProperty" then pcall(function() inner = p:GetInner():GetClass():GetFName():ToString() end) end
    return inner and (t .. "<" .. inner .. ">") or t, t
end
local READ_T = { BoolProperty = true, IntProperty = true, Int64Property = true, FloatProperty = true, DoubleProperty = true, ByteProperty = true,
    EnumProperty = true, NameProperty = true, StrProperty = true, ObjectProperty = true, ClassProperty = true }

local function classChain(c, fn)
    for _ = 1, 16 do
        if not isValid(c) then break end
        local cn = nameOf(c)
        if cn == "Object" or cn == "Actor" or cn == "ActorComponent" or cn == "SceneComponent" or cn == "PrimitiveComponent" then break end
        fn(c, cn)
        local nxt = nil
        pcall(function() nxt = c:GetSuperStruct() end)
        c = nxt
    end
end

local function dumpClass(path)
    local c = nil
    pcall(function() c = StaticFindObject(path) end)
    if not isValid(c) then P("CLASS " .. path .. " NOT FOUND"); return end
    P("CLASS " .. path)
    classChain(c, function(k, kn)
        pcall(function()
            k:ForEachFunction(function(fn)
                local ps = {}
                pcall(function() fn:ForEachProperty(function(p) ps[#ps + 1] = nameOf(p) .. ":" .. propType(p) end) end)
                P(string.format("FN %s.%s(%s)", kn, nameOf(fn), table.concat(ps, ", ")))
            end)
        end)
        pcall(function() k:ForEachProperty(function(p) P(string.format("PROP %s.%s : %s", kn, nameOf(p), propType(p))) end) end)
    end)
end

local function scalar(v)
    local t = type(v)
    if t == "number" or t == "boolean" or t == "string" then return tostring(v) end
    if t == "userdata" then
        local s = nil
        pcall(function() s = v:GetFullName() end)
        if type(s) == "string" then return s end
        pcall(function() s = v:ToString() end)
        if type(s) == "string" then return s end
        pcall(function() s = string.format("(%.1f,%.1f,%.1f)", v.X, v.Y, v.Z) end)
        if s then return s end
        local n = nil
        pcall(function() n = #v end)
        if n then return "[n=" .. tostring(n) .. "]" end
        return "<ud>"
    end
    return "?"
end

local function dumpValues(o, tag)
    classChain(o:GetClass(), function(k, kn)
        pcall(function()
            k:ForEachProperty(function(p)
                local pn = nameOf(p)
                local full, t = propType(p)
                if READ_T[t] then
                    local v = nil
                    local ok = pcall(function() v = o[pn] end)
                    P(string.format("VAL %s %s.%s = %s", tag, kn, pn, ok and scalar(v) or "<err>"))
                else
                    P(string.format("VAL %s %s.%s : %s (not read)", tag, kn, pn, full))
                end
            end)
        end)
    end)
end

local function ownerOf(o)
    local s = "?"
    pcall(function() s = nameOf(o:GetOwner()) end)
    if s == "?" then pcall(function() s = nameOf(o:GetOuter()) end) end
    return s
end

if MODE == "dump" then
    local classes = {
        "/Script/Subnautica2.SN2BuilderTool", "/Script/Subnautica2.SN2BuilderGhost", "/Script/Subnautica2.SN2BuilderGhostPlacementComponent",
        "/Script/Subnautica2.SN2BuilderBlueprintFunctionLibrary", "/Script/Subnautica2.SN2SculpturalBaseBlueprintFunctionLibrary",
        "/Script/Subnautica2.SN2BuilderPlacementProfile", "/Script/Subnautica2.SN2BuilderConstructActionData", "/Script/Subnautica2.SN2BuilderActionData",
        "/Script/Subnautica2.SN2BuilderToolComponent", "/Script/Subnautica2.SN2BuilderActionAbility", "/Script/Subnautica2.SN2BuilderAbility",
        "/Script/Subnautica2.SN2AbilityTask_UpdatePlacementGhost", "/Script/Subnautica2.SN2OutOfBoundsCheckComponent",
        "/Script/Subnautica2.SN2BlockedPlacementReasonInterface", "/Script/Subnautica2.SN2BuilderMenuViewModel",
        "/Script/UWESculpturalBase.UWESculpturalBaseWorldSubsystem", "/Script/UWESculpturalBase.UWESculpturalBaseGlobalsComponent",
        "/Script/UWESculpturalBase.UWESculpturalBaseProxyStreamingSubsystem", "/Script/UWESculpturalBase.UWEPlacementVolumeComponent",
        "/Script/UWEEdgeOfWorld.UWEEdgeOfWorldSubsystem", "/Script/UWEEdgeOfWorld.UWEEdgeOfWorldStatics", "/Script/UWEEdgeOfWorld.UWEOutOfBoundsCheckComponent",
        "/Script/UWEInventory.UWEInventoryStatics", "/Script/UWEInventory.UWEInventoryComponent", "/Script/UWEInventory.UWEToolbarComponent",
    }
    for _, path in ipairs(classes) do dumpClass(path) end
    -- the placement-volume and edge-of-world classes may live in other modules: report where the short names resolve
    for _, short in ipairs({ "UWEPlacementVolumeComponent", "UWEOutOfBoundsCheckComponent", "SN2OutOfBoundsCheckComponent", "UWEEdgeOfWorldSubsystem",
        "UWESculpturalBaseWorldSubsystem", "UWESculpturalBaseGlobalsComponent", "UWEInventoryComponent", "UWEToolbarComponent", "SN2BuilderTool",
        "SN2BuilderGhost", "SN2BuilderGhostPlacementComponent", "UWEEdgeOfWorldSpline", "UWESculpturalBaseProxyStreamingSubsystem" }) do
        local all = {}
        pcall(function() all = FindAllOf(short) or {} end)
        local n, owners = 0, {}
        for _, o in ipairs(all) do
            if isValid(o) then
                n = n + 1
                if n <= 6 then owners[#owners + 1] = nameOf(o) .. "@" .. ownerOf(o) .. " cls=" .. try(function() return o:GetClass():GetFullName() end) end
            end
        end
        P(string.format("LIVE %s n=%d %s", short, n, table.concat(owners, " | ")))
        if n > 0 and (short:find("OutOfBounds") or short:find("Subsystem") or short:find("GlobalsComponent") or short == "SN2BuilderTool") then
            local k = 0
            for _, o in ipairs(all) do
                if isValid(o) and not nameOf(o):find("^Default__") then
                    k = k + 1
                    if k <= 2 then dumpValues(o, short .. "#" .. k) end
                end
            end
        end
    end
    return true, "dump done"
end
-- ---------------------------------------------------------------- check modes (2026-11-28, step 2)
local REST = (ARGS or ""):match("^%S+%s+(.*)$") or ""
local function V(x, y, z) return { X = x, Y = y, Z = z } end
local function pawnLoc()
    local l = getPawn(getPC()):K2_GetActorLocation()
    return l.X, l.Y, l.Z
end
local function cdo(path)
    local o = nil
    pcall(function() o = StaticFindObject(path) end)
    return isValid(o) and o or nil
end
local function call(label, fn)
    local ok, r = pcall(fn)
    P(string.format("CALL %s -> %s", label, ok and scalar(r) or ("ERR " .. tostring(r))))
    return ok and r or nil
end

-- describe a primitive component for placement purposes: owner, tags, collision profile / object type / enabled, phys material, IsGroundSurface
local function descComp(tag, comp)
    local bfl = cdo("/Script/Subnautica2.Default__SN2BuilderBlueprintFunctionLibrary")
    local own, cls, prof, otype, cen, tags, ground, pm = "?", "?", "?", "?", "?", {}, "?", "?"
    pcall(function() own = nameOf(comp:GetOwner()) end)
    pcall(function() cls = nameOf(comp:GetClass()) end)
    pcall(function() prof = comp:GetCollisionProfileName():ToString() end)
    pcall(function() otype = tostring(comp:GetCollisionObjectType()) end)
    pcall(function() cen = tostring(comp:GetCollisionEnabled()) end)
    pcall(function() comp:GetOwner().Tags:ForEach(function(_, t) tags[#tags + 1] = t:get():ToString() end) end)
    pcall(function() comp.ComponentTags:ForEach(function(_, t) tags[#tags + 1] = "c:" .. t:get():ToString() end) end)
    pcall(function() pm = scalar(comp.BodyInstance.PhysMaterialOverride) end)
    if bfl then pcall(function() ground = tostring(bfl:IsGroundSurface(comp)) end) end
    P(string.format("COMP %s owner=%s cls=%s profile=%s objType=%s collEnabled=%s physMatOverride=%s tags=[%s] IsGroundSurface=%s",
        tag, own, cls, prof, otype, cen, pm, table.concat(tags, ","), ground))
    -- responses to the builder channels (ECC_GameTraceChannel13 BuilderSculpt = 26, 14 BuilderBlocker = 27, 1 Visibility = 1); 0 Ignore, 1 Overlap, 2 Block
    local rs = {}
    for _, ch in ipairs({ 1, 26, 27 }) do
        local r = "?"
        pcall(function() r = tostring(comp:GetCollisionResponseToChannel(ch)) end)
        rs[#rs + 1] = ch .. "=" .. r
    end
    local pmat = "?"
    pcall(function() pmat = comp:GetMaterial(0):GetPhysicalMaterial():GetFullName() end)
    P(string.format("COMPRESP %s responses[%s] mat0physMat=%s", tag, table.concat(rs, ","), pmat))
end

local function trace(tag, from, to)
    local ksl = cdo("/Script/Engine.Default__KismetSystemLibrary")
    local hit = {}
    local any = false
    pcall(function()
        any = ksl:LineTraceSingle(getPawn(getPC()), from, to, 0, true, {}, 0, hit, true, { R = 0, G = 0, B = 0, A = 0 }, { R = 0, G = 0, B = 0, A = 0 }, 0)
    end)
    local comp = nil
    pcall(function() comp = hit.Component:Get() end)
    if not isValid(comp) then pcall(function() comp = hit.HitObjectHandle.ReferenceObject:Get() end) end
    local ip = "?"
    pcall(function() ip = string.format("(%.0f,%.0f,%.0f)", hit.ImpactPoint.X, hit.ImpactPoint.Y, hit.ImpactPoint.Z) end)
    P(string.format("TRACE %s hit=%s impact=%s", tag, tostring(any), ip))
    if any and isValid(comp) then descComp(tag, comp) end
end

if MODE == "eow" then
    local sub = nil
    pcall(function() sub = FindFirstOf("UWEEdgeOfWorldSubsystem") end)
    local x, y, z = pawnLoc()
    P(string.format("PAWN (%.0f,%.0f,%.0f)", x, y, z))
    if isValid(sub) then
        call("EOW.IsEdgeOfWorldEnabled", function() return sub:IsEdgeOfWorldEnabled() end)
        call("EOW.IsEdgeOfWorldCollisionEnabled", function() return sub:IsEdgeOfWorldCollisionEnabled() end)
        call("EOW.GetEdgeOfWorld", function() return sub:GetEdgeOfWorld() end)
        for _, d in ipairs({ { 0, 0, 0 }, { 0, 0, -1000 }, { 5000, 0, -1000 }, { 0, 0, 500 }, { 100000, 0, -1000 } }) do
            local p = V(x + d[1], y + d[2], z + d[3])
            call(string.format("EOW.IsPointOutOfBounds(+%d,+%d,+%d)", d[1], d[2], d[3]), function() return sub:IsPointOutOfBounds(p) end)
            call(string.format("EOW.IsPointWithinEdgeOfWorld(+%d,+%d,+%d)", d[1], d[2], d[3]), function() return sub:IsPointWithinEdgeOfWorld(p) end)
        end
    else
        P("EOW subsystem not found")
    end
    local st = cdo("/Script/UWEEdgeOfWorld.Default__UWEEdgeOfWorldStatics")
    if st then
        local pawn = getPawn(getPC())
        call("EOWStatics.IsActorOutOfBounds(pawn)", function() return st:IsActorOutOfBounds(pawn, pawn) end)
        call("EOWStatics.IsActorWithinEdgeOfWorld(pawn)", function() return st:IsActorWithinEdgeOfWorld(pawn, pawn) end)
        call("EOWStatics.IsEdgeOfWorldEnabled", function() return st:IsEdgeOfWorldEnabled(pawn) end)
    end
    for _, short in ipairs({ "BP_EdgeOfWorld_C", "BP_EdgeOfWorldVolume_C", "UWEEdgeOfWorldSpline", "UWEHabitationVolume", "BP_BoxVolume_C" }) do
        local n = 0
        pcall(function() for _, o in ipairs(FindAllOf(short) or {}) do if isValid(o) and not nameOf(o):find("^Default__") then n = n + 1 end end end)
        P(string.format("COUNT %s n=%d", short, n))
    end
    return true, "eow done"
end

if MODE == "ground" then
    local x, y, z = pawnLoc()
    trace("down40m", V(x, y, z), V(x, y, z - 4000))
    local pc = getPC()
    pcall(function()
        local cl = pc.PlayerCameraManager:GetCameraLocation()
        local fw = pc.PlayerCameraManager:GetActorForwardVector()
        trace("camfwd30m", V(cl.X, cl.Y, cl.Z), V(cl.X + fw.X * 3000, cl.Y + fw.Y * 3000, cl.Z + fw.Z * 3000))
    end)
    -- every SN1 terrain actor's components: how many count as ground surface
    local nAct, nComp, nGround, shown = 0, 0, 0, 0
    pcall(function()
        for _, a in ipairs(FindAllOf("StaticMeshActor") or {}) do
            local isSN1 = false
            pcall(function() a.Tags:ForEach(function(_, t) if t:get():ToString() == "SN1Terrain" then isSN1 = true end end) end)
            if isValid(a) and isSN1 then
                nAct = nAct + 1
                local c = a.StaticMeshComponent
                if isValid(c) then
                    nComp = nComp + 1
                    local g = false
                    pcall(function() g = cdo("/Script/Subnautica2.Default__SN2BuilderBlueprintFunctionLibrary"):IsGroundSurface(c) end)
                    if g then nGround = nGround + 1 end
                    if shown < 2 then shown = shown + 1; descComp("sn1#" .. shown, c) end
                end
            end
        end
    end)
    P(string.format("SN1TERRAIN actors=%d comps=%d groundSurface=%d", nAct, nComp, nGround))
    return true, string.format("sn1 ground %d/%d", nGround, nComp)
end

-- udata (2026-11-28, from the static analysis of IsGroundSurface, exe rva 0x6fbfe30): a StaticMeshComponent counts as ground when its StaticMesh asset carries a
-- UWEAssetUserData whose DataAssets contains a UWESurfaceSpawnData with a ground tag. In-memory test: read the tags of DA_Sand/DA_Rock SurfaceData, give every SN1Terrain
-- mesh a UWEAssetUserData(DataAssets=[DA]) via AddAssetUserDataOfClass, re-test IsGroundSurface per component. REST = "sand" (default) | "rock" | "none" (read only).
if MODE == "udata" then
    local bfl = cdo("/Script/Subnautica2.Default__SN2BuilderBlueprintFunctionLibrary")
    local function loadObj(path)
        local o = cdo(path)
        if not o then pcall(function() o = LoadAsset(path) end) end
        if not isValid(o) then o = cdo(path) end
        return isValid(o) and o or nil
    end
    local function tagsOf(da)
        local out = {}
        pcall(function()
            local c = da.TagsToApplyToSpawnPoints
            c.GameplayTags:ForEach(function(_, t)
                local tv = t:get()
                local s = nil
                pcall(function() s = tv.TagName:ToString() end)
                out[#out + 1] = tostring(s)
            end)
        end)
        return table.concat(out, ",")
    end
    local das = {}
    for _, nm in ipairs({ "DA_SandSurfaceData", "DA_RockSurfaceData", "DA_RockScreeSurfaceData" }) do
        local da = loadObj("/Game/Data/SurfaceSpawnData/" .. nm .. "." .. nm)
        das[nm] = da
        P(string.format("UDATA %s -> %s class=%s tags=[%s]", nm, da and da:GetFullName() or "none", da and try(function() return da:GetClass():GetFullName() end) or "?", da and tagsOf(da) or ""))
    end
    local which = (REST ~= "" and REST) or "sand"
    local da = (which == "rock") and das["DA_RockSurfaceData"] or das["DA_SandSurfaceData"]
    local cls = cdo("/Script/UWEAssetRegistry.UWEAssetUserData")
    P("UDATA class UWEAssetUserData -> " .. (cls and cls:GetFullName() or "none"))
    local comps = {}
    pcall(function()
        for _, a in ipairs(FindAllOf("StaticMeshActor") or {}) do
            local isSN1 = false
            pcall(function() a.Tags:ForEach(function(_, t) if t:get():ToString():find("^SN1Terrain") then isSN1 = true end end) end)
            if isSN1 and isValid(a) and isValid(a.StaticMeshComponent) then comps[#comps + 1] = a.StaticMeshComponent end
        end
    end)
    local function count()
        local n = 0
        for _, c in ipairs(comps) do
            local g = false
            pcall(function() g = bfl:IsGroundSurface(c) end)
            if g then n = n + 1 end
        end
        return n
    end
    P(string.format("UDATA comps=%d groundBefore=%d", #comps, count()))
    if which == "none" or not da or not cls then return true, "read only" end
    local done, firstDump = 0, true
    local seen = {}
    for _, c in ipairs(comps) do
        local mesh = nil
        pcall(function() mesh = c.StaticMesh end)
        if isValid(mesh) and not seen[mesh:GetFullName()] then
            seen[mesh:GetFullName()] = true
            local ok1, r1 = pcall(function() return mesh:AddAssetUserDataOfClass(cls) end)
            local ud = nil
            pcall(function() ud = mesh:GetAssetUserDataOfClass(cls) end)
            local ok2 = false
            if isValid(ud) then ok2 = pcall(function() ud.DataAssets[1] = da end) end
            local n = -1
            pcall(function() n = #ud.DataAssets end)
            if done < 3 then P(string.format("UDATA mesh=%s add=%s/%s get=%s setDA=%s #DataAssets=%d", nameOf(mesh), tostring(ok1), tostring(r1), tostring(isValid(ud)), tostring(ok2), n)) end
            if isValid(ud) and ok2 then done = done + 1 end
        end
    end
    P(string.format("UDATA meshes patched=%d groundAfter=%d (of %d)", done, count(), #comps))
    -- sample: the component under the 40 m down trace
    local x, y, z = pawnLoc()
    trace("down40m_after", V(x, y, z), V(x, y, z - 4000))
    return true, "udata " .. which
end

local function pawnComp(short)
    local pawn = getPawn(getPC())
    for _, c in ipairs(findAll(short)) do
        local ok = false
        pcall(function() ok = c:GetOwner():GetFullName() == pawn:GetFullName() end)
        if ok then return c end
    end
    return nil
end
local function loadObj(path)
    local o = cdo(path)
    if not o then pcall(function() o = LoadAsset(path) end) end
    if not isValid(o) then o = cdo(path) end
    return isValid(o) and o or nil
end

if MODE == "give" then
    -- TEST ONLY, in-memory: builder + building materials into the pawn inventory, builder on toolbar slot 0 and equipped
    local inv, tb = pawnComp("UWEInventoryComponent"), pawnComp("UWEToolbarComponent")
    P("INV " .. (inv and inv:GetFullName() or "none") .. " TB " .. (tb and tb:GetFullName() or "none"))
    if not inv then return false, "no pawn inventory" end
    local it = loadObj("/Game/Data/ItemType/Tools/DA_Builder_ItemType.DA_Builder_ItemType")
    P("ITEMTYPE builder " .. (it and it:GetFullName() or "none"))
    if not it then return false, "no builder item type" end
    call("inv.AddItemTypeToInventory(builder)", function() return inv:AddItemTypeToInventory(it, 1) end)
    local stat = cdo("/Script/UWEInventory.Default__UWEInventoryStatics")
    for _, nm in ipairs({ "Titanium", "Copper", "Quartz", "Silver", "Lead" }) do
        local t = nil
        pcall(function() t = stat:GetItemTypeFromName(nm, true, {}) end)
        if isValid(t) then call("inv.AddAsMuchAsPossibleToInventory(" .. nm .. " x20)", function() return inv:AddAsMuchAsPossibleToInventory(t, 20) end)
        else P("ITEMTYPE " .. nm .. " not found") end
    end
    if tb then call("tb.AddToolbarItemTypeFromInventory(builder,0,equip)", function() return tb:AddToolbarItemTypeFromInventory(it, 0, true, inv) end) end
    return true, "given"
end

local function builderTool()
    for _, t in ipairs(findAll("SN2BuilderTool")) do
        if not nameOf(t):find("^Default__") then return t end
    end
    return nil
end

if MODE == "place" then
    local tool = builderTool()
    if not tool then return false, "no builder tool actor" end
    local nm = REST ~= "" and REST or "DA_Room_ItemBrushData"
    local path = nm:find("/") and nm or ("/Game/Data/BaseBuilding/BuilderActions/ItemBrushData/" .. nm .. "." .. nm)
    local da = loadObj(path)
    P("ACTION " .. path .. " -> " .. (da and da:GetFullName() or "none"))
    if not da then return false, "no action asset" end
    call("tool.ActivateAction", function() return tool:ActivateAction(da) end)
    call("tool.HasActiveAction", function() return tool:HasActiveAction() end)
    return true, "activated " .. nm
end

if MODE == "ghost" then
    local tool = builderTool()
    if not tool then return false, "no builder tool actor" end
    call("tool.HasActiveAction", function() return tool:HasActiveAction() end)
    local g = nil
    pcall(function() g = tool.Ghost:Get() end)
    if not isValid(g) then pcall(function() g = FindFirstOf("SN2BuilderGhost") end) end
    P("GHOST " .. (isValid(g) and (g:GetFullName() .. " at " .. fmtV(g:K2_GetActorLocation()) .. " hidden=" .. tostring(g.bHidden)) or "none"))
    if isValid(g) then
        local pc = nil
        pcall(function() pc = g.PlacementComponent end)
        if isValid(pc) then dumpValues(pc, "placement") end
    end
    -- what the builder's construct trace currently hits
    pcall(function()
        local h = tool.ConstructTraceResult
        local c = nil
        pcall(function() c = h.Component:Get() end)
        P(string.format("CONSTRUCTTRACE blocking=%s impact=(%.0f,%.0f,%.0f)", tostring(h.bBlockingHit), h.ImpactPoint.X, h.ImpactPoint.Y, h.ImpactPoint.Z))
        if isValid(c) then descComp("constructTrace", c) end
    end)
    return true, "ghost " .. tostring(isValid(g))
end

P("unknown mode " .. MODE)
return false, "unknown mode"
