-- SN2BugShot: press F1 in game to file a bug report. The game pauses and a popup (WBP_BugReport, modkit mod SN2BugShot) asks for a description:
-- Ctrl+Enter or the Submit button saves it, Esc or Cancel discards the text (the report is still saved with descriptionState=cancelled).
-- The watcher src/tools/bugshot_watch.sh adds a screenshot + log excerpts. Logic: popup.lua + bugshot.lua (also used by the SN2AutoTest verbs).
local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
local dir = src:match("^(.*)[\\/][^\\/]+$")
local okL, api = pcall(dofile, dir .. "\\popup.lua")
if not okL or type(api) ~= "table" then print("[SN2BugShot] load failed: " .. tostring(api) .. "\n"); return end
RegisterKeyBind(Key.F1, function()
    ExecuteInGameThread(function()
        if api.isOpen() then return end   -- F1 is ignored while the popup is open
        local ok, a, b = pcall(api.open, "F1")
        print("[SN2BugShot] F1 -> " .. tostring(ok) .. " " .. tostring(a) .. " " .. tostring(b) .. "\n")
    end)
end)
-- active only while the popup is open (the handlers return immediately otherwise)
RegisterKeyBind(Key.RETURN, { ModifierKey.CONTROL }, function()
    ExecuteInGameThread(function() if api.isOpen() then api.submit() end end)
end)
RegisterKeyBind(Key.ESCAPE, function()
    ExecuteInGameThread(function() if api.isOpen() then api.cancel() end end)
end)
print("[SN2BugShot] loaded; F1 opens the bug report popup\n")
