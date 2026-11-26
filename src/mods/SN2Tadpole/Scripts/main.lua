-- SN2Tadpole: press F4 to spawn one drivable Tadpole ~12 m from the lifepod, 3 m below the water surface. Logic: tadpole_spawn.lua.
local src = (debug.getinfo(1, "S").source or ""):gsub("^@", "")
local dir = src:match("^(.*)[\\/][^\\/]+$")
local okL, spawn = pcall(dofile, dir .. "\\tadpole_spawn.lua")
if not okL or type(spawn) ~= "function" then print("[SN2Tadpole] load failed: " .. tostring(spawn) .. "\n"); return end
RegisterKeyBind(Key.F4, function()
    ExecuteInGameThread(function()
        local ok, a, b = pcall(spawn)
        print("[SN2Tadpole] F4 -> " .. tostring(ok) .. " " .. tostring(a) .. " " .. tostring(b) .. "\n")
    end)
end)
print("[SN2Tadpole] loaded; F4 spawns a Tadpole near the lifepod\n")
