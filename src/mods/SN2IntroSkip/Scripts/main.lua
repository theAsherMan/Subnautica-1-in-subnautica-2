-- SN2IntroSkip v3: a NEW game starts in the lifepod at the surface. Character selection still happens first.
-- Trigger: the player character spawns in L_Main attached to the intro biobed and "entered lifepod" is not unlocked (= fresh intro).
-- Sequence (found by testing, research/09_intro_and_world_replacement.md):
--   1. BP_LifepodManager_C:ApplyCreativeModeStart(pawn)   - creative-mode story state (unlocks the arrival goals over ~30 s)
--   2. unlock the deep-start goals (PDA, door, NoA, adaptation tutorial, biolock, medkit ...) so their tutorials don't gate the player
--   3. move the pawn into the lifepod at the surface
--   4. RemoveDeepStartTags(pawn)  - also removes the missing-breathing tag => breathing adaptation works
--   5. SetLifepodRideCompleted(pawn), unassign biobed + detach, reset input flags, view target, ShowAllPlayers + ShowHUD
-- Not used: unlocking the lifepod/ride goals (starts the 58 s ride FMV), adaptation component calls (UE4SS crash / bad object).
-- Manual keys (top-row numbers): Ctrl+1 dump state, Ctrl+4 unstick again.
local MOD = "SN2IntroSkip"
local function log(msg) print(string.format("[%s] %s\n", MOD, tostring(msg))) end

local LIFEPOD_END = { X = -336997, Y = 433246, Z = 322 }   -- lifepod end-of-intro position (+80 cm)
local DONE_GOAL = "DA_Storygoal_Player_Ch2_EnteredLifepod_StoryGoal"
local DEEPSTART_GOALS = {
    "DA_Tools_PDA_StoryGoal",
    "DA_StoryGoal_Player_Ch1_FirstPrint",
    "DA_Storygoal_Player_Ch1_FirstPrint3_StoryGoal",
    "DA_StoryGoal_NarrativeSignal_Investigation_CoralGardens_1_Unknown",
    "DA_Deepstart_OpenFirstDoor_StoryGoal",
    "DA_Storygoal_Player_Ch1_NoA_Uploaded_StoryGoal",
    "DA_Storygoal_Player_Ch1_AdaptationTutorial1",
    "DA_Storygoal_Player_Ch1_AdaptationTutorial2",
    "DA_Storygoal_Player_Ch1_AdaptationTutorial_Interact",
    "DA_Storygoal_Player_Ch1_AdaptationTutorial_Insert",
    "DA_Adaptation_BreathingAdaptation_StoryGoal",
    "DA_Storygoal_Player_Ch1_AdaptationTutorial_Adapt",
    "DA_Storygoal_Player_Ch1_BiolockScanning",
    "DA_Storygoal_Player_Ch1_BiolockApproved",
    "DA_Tools_MedKit_StoryGoal",
    "DA_Storygoal_Player_Ch1_UnexpectedDepth",
    "DA_StoryGoal_Player_Ch1_SeriousAccident_StoryGoal",
    "DA_BlackBox_Investigation_DeepStart_Unknown_StoryGoal",
}

-- ---------------------------------------------------------------- helpers
local function isValid(o)
    if o == nil or type(o) ~= "userdata" then return false end
    local ok, r = pcall(function() return o:IsValid() end)
    return ok and r == true
end
local function nameOf(o)
    -- UE4SS hands back a null UObject wrapper for empty results; calling a method on it crashes UE4SS.dll (+0x2428xx) -> check first
    if not isValid(o) then return "none" end
    local ok, s = pcall(function() return o:GetFName():ToString() end)
    return ok and s or "?"
end
local function fullOf(o)
    -- UE4SS hands back a null UObject wrapper for empty results; calling a method on it crashes UE4SS.dll (+0x2428xx) -> check first
    if not isValid(o) then return "none" end
    local ok, s = pcall(function() return o:GetFullName() end)
    return ok and s or "?"
end
local function notCDO(o) return isValid(o) and not fullOf(o):find("Default__", 1, true) end
local function firstOf(cls)
    for _, o in ipairs(FindAllOf(cls) or {}) do
        if notCDO(o) then return o end
    end
    return nil
end
local function cdoOf(short)
    for _, x in ipairs(FindAllOf(short) or {}) do
        if isValid(x) and fullOf(x):find("Default__", 1, true) then return x end
    end
    return nil
end
local function getPC()
    for _, pc in ipairs(FindAllOf("PlayerController") or {}) do
        if notCDO(pc) then
            local okL, isLocal = pcall(function() return pc:IsLocalController() end)
            if not okL or isLocal then return pc end
        end
    end
    return nil
end
local function step(name, fn)
    local ok, err = pcall(fn)
    log((ok and "OK   " or "FAIL ") .. name .. (ok and "" or (": " .. tostring(err))))
    return ok
end
local function try(label, fn)
    local ok, r = pcall(fn)
    return string.format("%s=%s", label, ok and tostring(r) or ("ERR " .. tostring(r)))
end
local function goalsByName()
    local m = {}
    for _, g in ipairs(FindAllOf("UWEStoryGoal") or {}) do
        if notCDO(g) then m[nameOf(g)] = g end
    end
    return m
end
local function manager() return firstOf("BP_LifepodManager_C") end

-- ---------------------------------------------------------------- story goals
local function unlockGoals(pc, pawn, names)
    local goals = goalsByName()
    local sub = firstOf("UWEStoryGoalsWorldSubsystem")
    local st = cdoOf("UWEStoryGoalsStatics")
    local world = pc:GetWorld()
    local ps = pc.PlayerState
    local n, how, problems = 0, {}, {}
    for _, name in ipairs(names) do
        local g = goals[name]
        if not g then
            problems[#problems + 1] = name .. "(not loaded)"
        else
            local done, lastErr = false, ""
            local attempts = {
                { "subsystem", function() sub:UnlockStoryGoal(g, pawn, true) end },
                { "player", function() st:UnlockPlayerStoryGoal(world, g, ps) end },
                { "world", function() st:UnlockWorldStoryGoal(world, g) end },
            }
            for _, a in ipairs(attempts) do
                local ok, err = pcall(a[2])
                if ok then done = true; how[a[1]] = (how[a[1]] or 0) + 1; break end
                lastErr = tostring(err)
            end
            if done then n = n + 1 else problems[#problems + 1] = name .. "(" .. lastErr .. ")" end
        end
    end
    local hows = {}
    for k, v in pairs(how) do hows[#hows + 1] = k .. "=" .. v end
    log(string.format("  goals unlocked %d/%d [%s] subsystem=%s statics=%s; problems: %s", n, #names, table.concat(hows, " "),
        tostring(sub ~= nil), tostring(st ~= nil), table.concat(problems, ", ")))
end

-- ---------------------------------------------------------------- the skip
local function unstick(pc, pawn)
    local m = manager()
    if m then
        step("RemoveDeepStartTags(pawn)  [also restores breathing]", function() m:RemoveDeepStartTags(pawn) end)
        step("SetLifepodRideCompleted(pawn)", function() m:SetLifepodRideCompleted(pawn) end)
    else
        log("FAIL no BP_LifepodManager_C")
    end
    step("unassign biobed + detach", function()
        local st = cdoOf("UWEBioBedStatics")
        if st then st:UnassignPawnFromBioBed(pawn) end
        pawn:K2_DetachFromActor(1, 1, 1)
    end)
    step("reset input flags", function()
        pc:ResetIgnoreInputFlags()
        pc:SetIgnoreMoveInput(false)
        pc:SetIgnoreLookInput(false)
    end)
    step("view target = pawn", function() pc:SetViewTargetWithBlend(pawn, 0, 0, 0, false) end)
    if m then step("ShowAllPlayers + ShowHUD", function() m:ShowAllPlayers(); m:ShowHUD() end) end
end

-- phase A (right after spawn): story state only. The player stays on the biobed while its wake-up animation plays;
-- moving the pawn before that animation ends left it unable to move (v3, 2026-11-16).
local function skipStoryState(pc, pawn)
    log("fresh intro detected -> phase A: story state (player stays in the bed until the wake-up animation ends)")
    local m = manager()
    if m then step("ApplyCreativeModeStart(pawn)", function() m:ApplyCreativeModeStart(pawn) end) end
    step("unlock deep-start goals", function() unlockGoals(pc, pawn, DEEPSTART_GOALS) end)
end

-- phase B (after the pawn left the biobed by itself): move + unstick
local function skipMove(pc, pawn)
    log("phase B: player is out of the bed -> move into the lifepod")
    step("move into lifepod", function()
        pawn:K2_SetActorLocation(LIFEPOD_END, false, {}, true)
        local L = pawn:K2_GetActorLocation()
        log(string.format("  pawn at (%.0f, %.0f, %.0f)", L.X, L.Y, L.Z))
    end)
    unstick(pc, pawn)
    log("done - if the player still can't move, a tutorial step (e.g. open the PDA) may be waiting; Ctrl+4 re-runs the unstick")
end

local function parentClass(pawn)
    local p
    pcall(function() p = pawn:GetAttachParentActor() end)
    if not isValid(p) then return "none" end          -- never call methods on an empty result (UE4SS crash)
    return nameOf(p:GetClass())
end

local function dump(pc, pawn)
    log("dump: " .. table.concat({
        try("MoveIgnored", function() return pc:IsMoveInputIgnored() end),
        try("LookIgnored", function() return pc:IsLookInputIgnored() end),
        try("ViewTarget", function() return nameOf(pc:GetViewTarget()) end),
        try("AttachParent", function() return parentClass(pawn) end),
        try("Location", function() local L = pawn:K2_GetActorLocation(); return string.format("(%.0f,%.0f,%.0f)", L.X, L.Y, L.Z) end),
    }, " "))
end

-- ---------------------------------------------------------------- keys (top-row number keys)
local function bind(key, label, fn)
    local ok = pcall(RegisterKeyBind, key, { ModifierKey.CONTROL }, function()
        ExecuteInGameThread(function()
            log("== " .. label)
            local ok2, err = pcall(function()
                local pc = getPC()
                fn(pc, pc.Pawn)
            end)
            if not ok2 then log(label .. " failed: " .. tostring(err)) end
        end)
    end)
    if not ok then log("could not bind " .. label) end
end
bind(Key.ONE, "Ctrl+1 dump", dump)
bind(Key.FOUR, "Ctrl+4 unstick", function(pc, pawn) unstick(pc, pawn); dump(pc, pawn) end)

-- ---------------------------------------------------------------- trigger
local armed, seen = false, 0
local waitingGetUp, waitTicks = false, 0
-- Arm only when the restarting controller is in L_Main, decided from the hook's own controller (no FindAllOf): scanning every UObject twice a second
-- in the lobby while the engine tears it down (22.8k SphereComponents, 20 s FinishDestroy budget) is the suspected cause of the GC-watchdog crashes
-- on 2026-11-17. In the lobby this mod now does nothing at all.
pcall(RegisterHook, "/Script/Engine.PlayerController:ClientRestart", function(ctx)
    armed, seen, waitingGetUp = false, 0, false
    local ok, w = pcall(function() return ctx:get():GetWorld():GetFullName() end)
    if ok and type(w) == "string" and w:find("L_Main", 1, true) then armed = true end
end)
LoopAsync(500, function()
    ExecuteInGameThread(function()
        if waitingGetUp then
            waitTicks = waitTicks + 1
            local pc = getPC()
            local pawn
            if pc then pcall(function() pawn = pc.Pawn end) end
            if not isValid(pawn) then return end
            local parent = parentClass(pawn)
            if not parent:find("BioBed", 1, true) or waitTicks > 90 then   -- out of bed, or 45 s timeout
                waitingGetUp = false
                log(string.format("player left the bed after %.1f s (attached to %s)", waitTicks / 2, parent))
                local ok, err = pcall(skipMove, pc, pawn)
                if not ok then log("phase B failed: " .. tostring(err)) end
            end
            return
        end
        if not armed then return end
        local pc = getPC()
        if not pc then return end
        local okW, w = pcall(function() return pc:GetWorld():GetFullName() end)
        if not okW or not w:find("L_Main", 1, true) then armed = false; return end   -- never act in the lobby
        local pawn
        pcall(function() pawn = pc.Pawn end)
        if not isValid(pawn) or nameOf(pawn:GetClass()) == "UWESpectatorPawn" then return end   -- still in character selection
        seen = seen + 1
        if seen < 3 then return end                                                  -- let biobed attach settle (~1 s)
        armed = false
        local parent = parentClass(pawn)
        local done = false
        local st = cdoOf("UWEStoryGoalsStatics")
        local g = goalsByName()[DONE_GOAL]
        if st and g then pcall(function() done = st:IsStoryGoalUnlocked(pc:GetWorld(), g, pc.PlayerState) end) end
        log(string.format("player spawned, attached to %s, intro already done: %s", parent, tostring(done)))
        if parent:find("BioBed", 1, true) and not done then
            local ok, err = pcall(skipStoryState, pc, pawn)
            if not ok then log("phase A failed: " .. tostring(err)) end
            waitingGetUp, waitTicks = true, 0
        end
    end)
    return false
end)

log("loaded (v4): new games skip the intro and start in the lifepod (after the bed wake-up); Ctrl+1 dump, Ctrl+4 unstick")
