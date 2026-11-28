-- SN2BugShot popup flow. Returns an api table: open(source), submit(), cancel(), setText(s), state(), isOpen().
-- Used by main.lua (F1, Ctrl+Enter, Esc) and by the SN2AutoTest verbs bugreport_*.
-- Flow (research/process/bug_reports.md "SN2BugShot popup"): capture report + HighResShot request -> <id>.json.pending -> ~0.4 s later create WBP_BugReport,
-- AddToViewport, pause, UI-only input focused on DescBox, cursor on -> poll widget.Result (0 open / 1 submit / 2 cancel) every 100 ms ->
-- read DescBox text, remove widget, unpause, game-only input, cursor off -> write <id>.json (description + descriptionState).
local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
local dir = src:match("^(.*)[\\/][^\\/]+$")
local okL, report, core = pcall(dofile, dir .. "\\bugshot.lua")
if not okL or type(core) ~= "table" then
    print("[SN2BugShot] popup: bugshot.lua load failed: " .. tostring(report) .. "\n")
    return nil
end
local log, isValid, getPC = core.log, core.isValid, core.getPC

local WBP_ASSET = "/Game/Mods/SN2BugShot/WBP_BugReport"
local WBP_CLASS = WBP_ASSET .. "." .. "WBP_BugReport_C"
local SHOT_DELAY_MS = 400
local POLL_MS = 100
local ZORDER = 10000

local st = { open = false, phase = "idle", R = nil, widget = nil, pc = nil, world = nil }

local function gs() return StaticFindObject("/Script/Engine.Default__GameplayStatics") end
local function wbl() return StaticFindObject("/Script/UMG.Default__WidgetBlueprintLibrary") end

local function widgetClass()
    local c = StaticFindObject(WBP_CLASS)
    if isValid(c) then return c end
    -- the cooked widget blueprint is not loaded until something asks for it; LoadAsset wants the full object path
    for _, p in ipairs({ WBP_ASSET .. ".WBP_BugReport", WBP_CLASS, WBP_ASSET }) do
        local ok, err = pcall(function() LoadAsset(p) end)
        c = StaticFindObject(WBP_CLASS)
        log("POPUP LoadAsset(" .. p .. ") ok=" .. tostring(ok) .. " err=" .. tostring(err) .. " classFound=" .. tostring(isValid(c)))
        if isValid(c) then return c end
    end
    return nil
end

local api = {}

function api.isOpen() return st.open end

function api.state()
    local s = { open = st.open, phase = st.phase }
    pcall(function() s.paused = gs():IsGamePaused(st.world or getPC():GetWorld()) end)
    pcall(function() s.time = gs():GetTimeSeconds(st.world or getPC():GetWorld()) end)
    pcall(function() if isValid(st.widget) then s.result = st.widget.Result end end)
    pcall(function() if isValid(st.widget) then s.text = st.widget.DescBox:GetText():ToString() end end)
    pcall(function() if isValid(st.pc) then s.cursor = st.pc.bShowMouseCursor end end)
    return s
end

local function close(state)
    if st.phase ~= "open" then return false end
    st.phase = "closing"
    local text = ""
    pcall(function() text = st.widget.DescBox:GetText():ToString() end)
    pcall(function() st.widget:RemoveFromParent() end)
    pcall(function() gs():SetGamePaused(st.world, false) end)
    pcall(function() wbl():SetInputMode_GameOnly(st.pc) end)
    pcall(function() st.pc.bShowMouseCursor = false end)
    local R = st.R
    local ok, err = core.finalize(R, state == "submitted" and text or "", state)
    log(string.format("POPUP closed state=%s textLen=%d finalize=%s %s", state, #text, tostring(ok), tostring(err)))
    st.open, st.phase, st.widget, st.R = false, "idle", nil, nil
    return true
end

local function poll()
    if st.phase ~= "open" then return end
    ExecuteInGameThread(function()
        if st.phase ~= "open" then return end
        local r = 0
        local okR = pcall(function() r = st.widget.Result end)
        if not okR or not isValid(st.widget) then
            log("POPUP widget lost -> treating as cancelled")
            close("cancelled")
        elseif r == 1 then close("submitted")
        elseif r == 2 then close("cancelled") end
    end)
    ExecuteWithDelay(POLL_MS, poll)
end

local function showPopup()
    ExecuteInGameThread(function()
        if st.phase ~= "capturing" then return end
        local pc = getPC()
        local cls = widgetClass()
        if not pc or not cls then
            log("POPUP unavailable (" .. (pc and "widget class WBP_BugReport_C not found" or "no player controller") .. ") -> report without description (nopopup)")
            local R = st.R
            st.open, st.phase, st.R = false, "idle", nil
            core.finalize(R, "", "nopopup")
            return
        end
        st.pc = pc
        pcall(function() st.world = pc:GetWorld() end)
        local ok, err = pcall(function()
            local w = wbl():Create(st.world, cls, pc)
            if not isValid(w) then error("Create returned invalid widget") end
            st.widget = w
            w:AddToViewport(ZORDER)
            gs():SetGamePaused(st.world, true)
            pc.bShowMouseCursor = true
            wbl():SetInputMode_UIOnlyEx(pc, w.DescBox, 0)
        end)
        if not ok then
            log("POPUP create failed: " .. tostring(err))
            pcall(function() if isValid(st.widget) then st.widget:RemoveFromParent() end end)
            pcall(function() gs():SetGamePaused(st.world, false) end)
            local R = st.R
            st.open, st.phase, st.widget, st.R = false, "idle", nil, nil
            core.finalize(R, "", "nopopup")
            return
        end
        st.phase = "open"
        log("POPUP opened id=" .. tostring(st.R.id))
        poll()
    end)
end

-- F1 / test: returns ok, id_or_reason
function api.open(source)
    if st.open then return false, "popup already open" end
    local R, id = core.capture(source or "F1")
    if not R then return false, id end
    st.open, st.phase, st.R = true, "capturing", R
    core.pending(R)
    ExecuteWithDelay(SHOT_DELAY_MS, showPopup)
    return true, id
end

function api.submit()
    if st.phase ~= "open" then return false end
    return close("submitted")
end

function api.cancel()
    if st.phase ~= "open" then return false end
    return close("cancelled")
end

-- test hook: put text in the box (same as typing it)
function api.setText(text)
    if st.phase ~= "open" or not isValid(st.widget) then return false end
    local ok, err = pcall(function() st.widget.DescBox:SetText(FText(text)) end)
    if not ok then log("setText failed: " .. tostring(err)) end
    return ok
end

return api
