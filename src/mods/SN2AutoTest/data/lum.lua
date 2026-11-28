-- TEMPORARY diagnostic (2026-11-28, investigator-lum): why does the underwater picture's mean luminance not respond to the region water values?
-- Run by the verbs lum_read / lum_bias / lum_bias_hi / lum_unclamp (MODE) of SN2AutoTest. Lines: LUM <mode> ...
--   lum_read    : READ-ONLY. exposure settings of every non-region PostProcessComponent, the camera's PP, exposure cvars, then the effective region MID values (uwa1)
--   lum_bias    : IN-MEMORY A/B: sky PostProcessComponent Settings.AutoExposureBias = 3.5 (baseline 0.5). Nothing is saved.
--   lum_bias_hi : same, bias 6.5
--   lum_unclamp : bias back to 0.5 and AutoExposureMaxBrightness 0 -> 20 (tests whether the max-EV clamp is active)
local function P(s) log("LUM " .. MODE .. " " .. s) end

local function rd(o, names)
    local parts = {}
    for _, n in ipairs(names) do
        local v = "?"
        pcall(function()
            local x = o[n]
            if type(x) == "userdata" then
                local r = nil
                pcall(function() r = string.format("(%.3g,%.3g,%.3g)", x.R, x.G, x.B) end)
                v = r or str(x)
            else v = tostring(x) end
        end)
        parts[#parts + 1] = n .. "=" .. v
    end
    return table.concat(parts, " ")
end

local EXP = { "bOverride_AutoExposureBias", "AutoExposureBias", "bOverride_AutoExposureMinBrightness", "AutoExposureMinBrightness",
    "bOverride_AutoExposureMaxBrightness", "AutoExposureMaxBrightness", "bOverride_AutoExposureMethod", "AutoExposureMethod",
    "AutoExposureSpeedUp", "AutoExposureSpeedDown", "AutoExposureLowPercent", "AutoExposureHighPercent",
    "HistogramLogMin", "HistogramLogMax", "bOverride_AutoExposureBiasCurve", "bOverride_AutoExposureApplyPhysicalCameraExposure", "AutoExposureApplyPhysicalCameraExposure",
    "bOverride_AutoExposureMeterMask", "bOverride_AutoExposureCalibrationConstant_DEPRECATED", "bOverride_FilmSlope", "FilmSlope", "FilmToe", "FilmShoulder",
    "bOverride_VignetteIntensity", "VignetteIntensity", "bOverride_BloomIntensity", "BloomIntensity" }

local function skyPP()
    for _, c in ipairs(findAll("PostProcessComponent")) do
        local own = "?"
        pcall(function() own = c:GetOwner():GetFName():ToString() end)
        if own:find("^BP_UWESky_C") then return c, own end
    end
    return nil, nil
end

if MODE == "lum_read" then
    local n = 0
    for _, c in ipairs(findAll("PostProcessComponent")) do
        local own = "?"
        pcall(function() own = c:GetOwner():GetFName():ToString() end)
        local isReg = own:find("^BP_UWEWaterBiomeRegionActor") ~= nil
        local bw = tonumber(try(function() return c.BlendWeight end)) or 0
        if (not isReg) or bw > 0 then
            n = n + 1
            P(string.format("PPC %s owner=%s enabled=%s unbound=%s prio=%s blendw=%s", nameOf(c), own, tostring(try(function() return c.bEnabled end)),
                tostring(try(function() return c.bUnbound end)), tostring(try(function() return c.Priority end)), tostring(bw)))
            pcall(function() P("PPC " .. nameOf(c) .. " " .. rd(c.Settings, EXP)) end)
        end
    end
    P("PPC shown=" .. n)
    -- camera manager view-target PP (the pawn/camera's own PostProcessSettings)
    pcall(function()
        local pc = getPC()
        local pov = pc.PlayerCameraManager:GetCameraCachePOV()
        P("CAMPOV PP " .. rd(pov.PostProcessSettings, EXP))
        P("CAMPOV PPBlendWeight=" .. tostring(pov.PostProcessBlendWeight))
    end)
    -- cvars
    local ksl = nil
    pcall(function() ksl = StaticFindObject("/Script/Engine.Default__KismetSystemLibrary") end)
    if ksl then
        local parts = {}
        for _, cv in ipairs({ "r.DefaultFeature.AutoExposure", "r.DefaultFeature.AutoExposure.Method", "r.DefaultFeature.AutoExposure.ExtendDefaultLuminanceRange",
            "r.EyeAdaptationQuality", "r.EyeAdaptation.MethodOveride", "r.EyeAdaptation.ExponentialTransition", "r.EyeAdaptation.LensAttenuation",
            "r.Tonemapper.Quality", "r.TonemapperGamma", "r.Lumen.Reflections.Allow", "r.VolumetricFog.GridPixelSize", "r.VolumetricFog.GridSizeZ", "r.VolumetricFog.HistoryWeight" }) do
            local ok, v = pcall(function() return ksl:GetConsoleVariableIntValue(cv) end)
            local okf, vf = pcall(function() return ksl:GetConsoleVariableFloatValue(cv) end)
            parts[#parts + 1] = cv .. "=" .. (ok and tostring(v) or "?") .. "/" .. (okf and string.format("%.4g", vf) or "?")
        end
        P("CVARS " .. table.concat(parts, " "))
    end
    -- effective region MID values (same as uwa1)
    if verbs and verbs.uwa1 then pcall(verbs.uwa1) end
    return true
end

-- the sky PostProcessComponent is rewritten every frame by the day sequence (DS_Main_Day animates Settings.AutoExposureBias / MaxBrightness), so the A/B
-- goes through the pawn's BasePostProcess (unbound, priority 0 > sky -1000, normally disabled) instead.
local function basePP()
    for _, c in ipairs(findAll("PostProcessComponent")) do
        if nameOf(c) == "BasePostProcess" then return c end
    end
    return nil
end
local c = basePP()
if not c then P("no BasePostProcess found"); return false, "no BasePostProcess" end
local s = c.Settings
P("before enabled=" .. tostring(c.bEnabled) .. " unbound=" .. tostring(c.bUnbound) .. " prio=" .. tostring(c.Priority) .. " " .. rd(s, { "bOverride_AutoExposureBias", "AutoExposureBias", "AutoExposureMinBrightness", "AutoExposureMaxBrightness", "bOverride_AutoExposureBiasCurve" }))
c.bEnabled = true
c.BlendWeight = 1.0
if MODE == "lum_bias" then
    s.bOverride_AutoExposureBias = true
    s.AutoExposureBias = 3.5
elseif MODE:match("^lum_b%d%d$") then
    s.bOverride_AutoExposureBias = true
    s.AutoExposureBias = tonumber(MODE:sub(6, 6) .. "." .. MODE:sub(7, 7))
elseif MODE == "lum_bias_hi" then
    s.bOverride_AutoExposureBias = true
    s.AutoExposureBias = 6.5
elseif MODE == "lum_unclamp" then
    s.bOverride_AutoExposureBias = true
    s.AutoExposureBias = 0.5
    s.bOverride_AutoExposureMaxBrightness = true
    s.AutoExposureMaxBrightness = 20
elseif MODE == "lum_nocurve" then
    s.bOverride_AutoExposureMaxBrightness = false
    s.bOverride_AutoExposureBias = true
    s.AutoExposureBias = 0.5
    s.bOverride_AutoExposureBiasCurve = true
    local okc, errc = pcall(function() s.AutoExposureBiasCurve = nil end)
    P("curve nil set ok=" .. tostring(okc) .. " " .. tostring(errc))
end
P("after enabled=" .. tostring(c.bEnabled) .. " " .. rd(c.Settings, { "bOverride_AutoExposureBias", "AutoExposureBias", "AutoExposureMinBrightness", "AutoExposureMaxBrightness", "bOverride_AutoExposureBiasCurve" }))
return true
