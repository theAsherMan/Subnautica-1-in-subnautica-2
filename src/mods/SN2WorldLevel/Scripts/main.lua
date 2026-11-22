-- SN2WorldLevel — key-press-only test: change the lobby's custom "world level" (map opened by New Game).
--   F8  read GetWorldLevelName/IsCustomWorldLevel, SetWorldLevel(L_GameplayZoo_SupplyCrates in the same format), log before/after
--   F9  SetWorldLevel back to the value remembered at the first F8
-- No hooks, nothing periodic. Never calls GetWorldLevel() (returns a TSoftObjectPtr struct).
local MOD = "SN2WorldLevel"
local function log(m) print(string.format("[%s] %s\n", MOD, tostring(m))) end

local remembered = nil

local function statics()
    local ok, s = pcall(StaticFindObject, "/Script/UWELobby.Default__UWELobbyStatics")
    if ok and s ~= nil and type(s) == "userdata" then
        local ok2, v = pcall(function() return s:IsValid() end)
        if ok2 and v then return s end
    end
    log("UWELobbyStatics CDO not found")
    return nil
end

local function readState(s)
    local ok, name = pcall(function() return s:GetWorldLevelName():ToString() end)
    if not ok then log("GetWorldLevelName error: " .. tostring(name)); name = "?" end
    local ok2, custom = pcall(function() return s:IsCustomWorldLevel() end)
    if not ok2 then log("IsCustomWorldLevel error: " .. tostring(custom)); custom = "?" end
    return name, custom
end

RegisterKeyBind(Key.F8, function()
    local s = statics()
    if not s then return end
    local cur, c1 = readState(s)
    if remembered == nil then remembered = cur end
    local target
    if cur:find(".", 1, true) then target = "/Game/Maps/GameplayZoos/L_GameplayZoo_SupplyCrates.L_GameplayZoo_SupplyCrates"
    elseif cur:sub(1, 1) == "/" then target = "/Game/Maps/GameplayZoos/L_GameplayZoo_SupplyCrates"
    else target = "L_GameplayZoo_SupplyCrates" end
    local ok, err = pcall(function() s:SetWorldLevel(target) end)
    if not ok then log("SetWorldLevel error: " .. tostring(err)) end
    local after, c2 = readState(s)
    log(string.format("F8 before=%s custom=%s -> set %s -> after=%s custom=%s", cur, tostring(c1), target, after, tostring(c2)))
end)

RegisterKeyBind(Key.F9, function()
    local s = statics()
    if not s then return end
    if remembered == nil then log("F9: nothing remembered (press F8 first)"); return end
    local ok, err = pcall(function() s:SetWorldLevel(remembered) end)
    if not ok then log("SetWorldLevel error: " .. tostring(err)) end
    local after, c = readState(s)
    log(string.format("F9 restored %s -> after=%s custom=%s%s", remembered, after, tostring(c), ok and "" or " (error)"))
end)

log("loaded (F8 set dev map, F9 restore)")
