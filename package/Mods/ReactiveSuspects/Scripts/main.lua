-- ReactiveSuspects r12 | shot-direction proximity + native movement | host / standalone only
local VERSION = "r12"
local Config = {
    Enabled = true,
    EnableMovement = true,     -- restore native navigation after r11 fire verification
    OverrideCombatTarget = true,
    ReactionSeconds = 8.0,       -- renewed by every hit / bullet near-pass
    TickMs = 50,
    ImpactRadiusCm = 250.0,
    ShotPathLengthCm = 10000.0, -- directional sensing, deliberately not clipped by walls
    MaxQueuedImpacts = 64,
    MaxSuspectsForImpact = 128,
    FireRefreshSeconds = 0.6,
    MoveIntervalSeconds = 0.9,
    SidestepCm = 180.0,
    AdvanceCm = 100.0,
    ChaseBeyondCm = 1000.0,
    AcceptanceRadiusCm = 45.0,
    MaxActiveSuspects = 64,
    MaxEventsPerTick = 32,
    SummaryEveryTicks = 200,
}

local PREFIX = "[ReactiveSuspects] "
local CHAR = "/Script/ReadyOrNot.ReadyOrNotCharacter:"
local COMBAT = "/Script/ReadyOrNot.BaseCombatActivity:"
local CTRL = "/Script/ReadyOrNot.CyberneticController:"
local TARGET = "/Script/ReadyOrNot.TargetingComponent:"
local PROJECTILE = "/Script/ReadyOrNot.Projectile:"
local BULLET = "/Script/ReadyOrNot.BulletProjectile:"
local MAGAZINE = "/Script/ReadyOrNot.BaseMagazineWeapon:"
local active, pending = {}, {}
local impacts, suspects, nextSuspectRefresh = {}, {}, 0
local functions = {}
local epoch, ticks, count, pendingCount = 0, 0, 0, 0
local reactionTickEnded, reactionTickResumed = false, false
local ready, installed, warned = false, false, {}
local counters = { hits = 0, near = 0, impactEvents = 0, impactNear = 0,
    rawImpacts = 0, rawNear = 0, respawns = 0, validations = 0,
    rawHitscans = 0, rawFires = 0, rawHitReports = 0, shotPaths = 0, shotNear = 0,
    droppedImpacts = 0, starts = 0, fireRequests = 0,
    moveRequests = 0, rejectedMoves = 0, stops = 0 }

local function log(s) print(PREFIX .. s .. "\n") end
local function warnOnce(key, message)
    if not warned[key] then warned[key] = true; log(message) end
end
local function valid(o) return o ~= nil and o:IsValid() end
local function same(a, b)
    return valid(a) and valid(b) and a:GetAddress() == b:GetAddress()
end
-- Hook arguments are RemoteUnrealParam. Copy their values while the call exists.
local function value(p)
    local t = type(p)
    if p == nil or t == "number" or t == "boolean" or t == "string" then return p end
    return p:get()
end
local function actorOK(o)
    return valid(o) and o:IsA("/Script/ReadyOrNot.ReadyOrNotCharacter")
        and not o:IsDeadOrUnconscious() and not o:IsArrested()
end
local function key(o) return tostring(o:GetAddress()) end
local function name(o) return valid(o) and o:GetFName():ToString() or "invalid" end
local function age(o) return o:GetGameTimeSinceCreation() end
local setupStage = "idle"

-- Borrow public UObject helpers from an actor whose IsA lookup has succeeded.
-- Helpers receive their UObject explicitly; do not modify any metatable.
local function isKind(o, path, prototype)
    local fn = prototype.IsA
    return type(fn) == "function" and fn(o, path)
end
local function describe(o, prototype)
    if not valid(o) then return "invalid" end
    local fn = (prototype or o).GetFullName
    if type(fn) == "function" then
        local ok, result = pcall(fn, o)
        if ok then return tostring(result) end
    end
    return "unavailable_full_name"
end
local function bindingSample(label, o, prototype)
    -- All diagnostics are optional and bounded; they cannot block a reaction.
    pcall(function()
        local mt = getmetatable(o)
        log(label .. " object=" .. describe(o, prototype)
            .. " GetClass=" .. type(o.GetClass) .. " IsA=" .. type(o.IsA)
            .. " CallFunction=" .. type(o.CallFunction)
            .. " metatable=" .. type(mt))
    end)
end

local function traced(s, stage, fn)
    s.traced = s.traced or {}
    local first = not s.traced[stage]
    s.traced[stage] = true
    if first then log("CALL_BEGIN " .. s.label .. " " .. stage) end
    local result = table.pack(fn())
    if first then log("CALL_END " .. s.label .. " " .. stage) end
    return table.unpack(result, 1, result.n)
end

local function stop(s, reason)
    if valid(s.pawn) and s.pawn:HasAuthority() and same(s.world, s.pawn:GetWorld())
            and valid(s.controller) and valid(s.combat) then
        -- Do not cancel another script's newer target or another activity's move.
        if s.didFire and same(s.combat.CurrentScriptedFireAt.FireAtActor, s.attacker) then
            functions[COMBAT.."StopScriptedFire"](s.combat)
            functions[COMBAT.."StopScriptedLook"](s.combat)
        end
        if s.moveId and s.moveId > 0 and s.controller:IsMovingForRequest(s.moveId) then
            s.controller:AbortMove(false)
        end
    end
    counters.stops = counters.stops + 1
    log("STOP " .. s.label .. " reason=" .. reason)
end

local function allowedAttacker(controller, attacker)
    -- Preserve the game's factions; bullets from friendly suspects do not create
    -- a forced gang war. Host and remote SWAT players are both accepted.
    return attacker:IsOnSWATTeam() or controller:IsCharacterEnemy(attacker)
end

local function accept(event)
    setupStage = "actor_checks"
    if event.epoch ~= epoch or not Config.Enabled then return end
    local pawn, attacker = event.pawn, event.attacker
    if not actorOK(pawn) or not pawn:HasAuthority() or not pawn:IsSuspect()
            or not actorOK(attacker) or same(pawn, attacker) then return end
    if not same(pawn:GetWorld(), attacker:GetWorld()) then return end
    local controller = pawn:GetCyberneticsController()
    if not valid(controller) or not controller:HasAuthority()
            or not allowedAttacker(controller, attacker) then return end
    local id, now = key(pawn), age(pawn)
    local s = active[id]
    if s and (not same(s.pawn, pawn) or not same(s.attacker, attacker)) then
        pcall(stop, s, "target_changed")
        active[id] = nil; count = count - 1; s = nil
    end
    if s then
        s.untilAge = now + Config.ReactionSeconds
        return
    end
    if count >= Config.MaxActiveSuspects then
        warnOnce("capacity", "Active suspect limit reached; raise MaxActiveSuspects if required.")
        return
    end
    local combat = controller:GetCombatActivity()
    if not valid(combat) then
        warnOnce("no_combat", "No original CombatActivity on a hit suspect; reaction skipped.")
        return
    end
    local targeting = controller.TargetingComponent
    if not valid(targeting) then return end
    setupStage = "receiver_checks"
    if not warned.targeting_binding then
        warned.targeting_binding = true
        bindingSample("TARGETING", targeting, pawn)
        bindingSample("COMBAT", combat, pawn)
    end
    if not isKind(targeting, "/Script/ReadyOrNot.TargetingComponent", pawn) then
        warnOnce("targeting_mismatch", "TargetingComponent receiver class mismatch; reaction skipped.")
        return
    end
    if not isKind(combat, "/Script/ReadyOrNot.BaseCombatActivity", pawn) then
        warnOnce("combat_mismatch", "CombatActivity receiver class mismatch; reaction skipped.")
        return
    end
    -- StaticFindObject returns callable UFunctions. Pass their verified receiver
    -- explicitly, avoiding the receiver's failing member/method lookup.
    setupStage = "AddKnownEnemy"
    functions[TARGET.."AddKnownEnemy"](targeting, attacker, true)
    setupStage = "SetLastTrackedTarget"
    functions[TARGET.."SetLastTrackedTarget"](targeting, attacker)
    setupStage = "AbortCover"
    controller:AbortCover()
    controller:AbortCoverLandmark()
    -- CombatActivity is the controller's separate combat component. Its fire
    -- checks delegate to CurrentActivity. Adding combat as that main activity
    -- makes those checks recurse into themselves (r7/r9 stack overflow).
    -- Leave the original activity hierarchy under the game's control.
    s = { pawn = pawn, attacker = attacker, controller = controller, combat = combat,
        world = pawn:GetWorld(), untilAge = now + Config.ReactionSeconds,
        nextFire = 0, nextMove = 0, side = 1, failures = 0, label = name(pawn),
        lastPosition = nil, stuck = 0 }
    active[id] = s; count = count + 1; counters.starts = counters.starts + 1
    log("START " .. s.label .. " target=" .. name(attacker) .. " trigger=" .. event.kind)
end

local function move(s, now)
    local p = traced(s, "GetPawnLocation", function() return s.pawn:K2_GetActorLocation() end)
    local t = traced(s, "GetAttackerLocation", function() return s.attacker:K2_GetActorLocation() end)
    local dx, dy = t.X - p.X, t.Y - p.Y
    local distance = math.sqrt(dx * dx + dy * dy)
    if distance < 1 then return end
    dx, dy = dx / distance, dy / distance
    if s.lastPosition then
        local mx, my = p.X - s.lastPosition.X, p.Y - s.lastPosition.Y
        s.stuck = (mx * mx + my * my < 25 * 25) and (s.stuck + 1) or 0
    end
    s.lastPosition = { X = p.X, Y = p.Y, Z = p.Z }
    if s.stuck >= 2 then s.chaseUntil = now + 2.5 end
    if (s.chaseUntil and now < s.chaseUntil) or distance > Config.ChaseBeyondCm then
        -- Let the original navigation system find a route around obstructions.
        s.moveId = traced(s, "RequestMoveAsync", function()
            return s.controller:RequestMoveAsync({X=t.X,Y=t.Y,Z=t.Z}, true, 220.0)
        end)
        s.stuck = 0
    else
        local lateral = Config.SidestepCm * s.side
        local advance = distance > 300 and Config.AdvanceCm or -Config.AdvanceCm * 0.5
        local destination = { X = p.X + dx * advance - dy * lateral,
            Y = p.Y + dy * advance + dx * lateral, Z = p.Z }
        s.moveId = traced(s, "RequestMoveAsync", function()
            return s.controller:RequestMoveAsync(destination, true, Config.AcceptanceRadiusCm)
        end)
    end
    s.side = -s.side
    counters.moveRequests = counters.moveRequests + 1
    if not s.moveId or s.moveId <= 0 then
        counters.rejectedMoves = counters.rejectedMoves + 1
    end
    s.nextMove = now + Config.MoveIntervalSeconds
end

local function step(s)
    if not s.firstStep then s.firstStep = true; log("STEP_BEGIN " .. s.label) end
    if not actorOK(s.pawn) or not s.pawn:HasAuthority() or not actorOK(s.attacker)
            or not valid(s.controller) or not valid(s.combat)
            or not same(s.world, s.pawn:GetWorld())
            or not same(s.world, s.attacker:GetWorld()) then return "invalid_or_inactive" end
    local now = age(s.pawn)
    if now >= s.untilAge or not Config.Enabled then return "expired" end
    -- Do not issue fire requests into the specific invalid hierarchy observed
    -- in r7/r9. A fresh r10 session never installs this self-parent relation.
    if same(s.controller.CurrentActivity, s.combat) then
        return "combat_is_current_activity"
    end
    if not s.activeLogged then
        s.activeLogged = true
        log("COMBAT_COMPONENT " .. s.label .. " main_activity=" .. describe(s.controller.CurrentActivity, s.pawn))
    end
    if now >= s.nextFire then
        local weapon = traced(s, "GetEquippedWeapon", function() return s.pawn:GetEquippedWeapon() end)
        if valid(weapon) then
            traced(s, "ScriptedLookAtActor", function()
                functions[COMBAT.."ScriptedLookAtActor"](s.combat, s.attacker, Config.FireRefreshSeconds + 0.4)
            end)
            -- Original aim and weapon execution, current ammo, original accuracy.
            traced(s, "ScriptedFireAtActor", function()
                functions[COMBAT.."ScriptedFireAtActor"](s.combat, s.attacker, Config.FireRefreshSeconds + 0.4, Config.OverrideCombatTarget, 1.0, false)
            end)
            s.didFire = true
            counters.fireRequests = counters.fireRequests + 1
        else
            traced(s, "DrawWeapon", function() s.pawn:DrawWeapon() end)
        end
        s.nextFire = now + Config.FireRefreshSeconds
    end
    if Config.EnableMovement and now >= s.nextMove then move(s, now) end
    if not s.stepEnded then s.stepEnded = true; log("STEP_END " .. s.label) end
end

local function enqueue(pawn, attacker, kind)
    if not ready or not Config.Enabled or not valid(pawn) or not valid(attacker) then return end
    -- Client installs remain passive; authority is checked again before changes.
    if not pawn:HasAuthority() or not pawn:IsSuspect() then return end
    local id = key(pawn)
    if not pending[id] and pendingCount >= Config.MaxActiveSuspects then return end
    if not pending[id] then pendingCount = pendingCount + 1 end
    pending[id] = {pawn=pawn, attacker=attacker, kind=kind, epoch=epoch}
end

local function onDamage(context, damage, isPoint, damageType, instigator, causer)
    local ok, err = pcall(function()
        if value(isPoint) ~= true then return end
        local dtype = value(damageType)
        local bullet = StaticFindObject("/Script/ReadyOrNot.BulletDamageType")
        if not valid(dtype) or not valid(bullet) or not dtype:IsChildOf(bullet) then return end
        local pawn, attacker = value(context), value(instigator)
        if valid(pawn) and pawn:HasAuthority() and pawn:IsSuspect() then
            counters.hits = counters.hits + 1
            enqueue(pawn, attacker, "bullet_hit")
        end
    end)
    if not ok then warnOnce("hit_error", "Hit hook error: " .. tostring(err)) end
end

local function onNearPass(context, suppression, cameraShake, lessLethal)
    counters.rawNear = counters.rawNear + 1
    local ok, err = pcall(function()
        local pawn, data = value(context), value(suppression)
        if valid(pawn) and pawn:HasAuthority() and pawn:IsSuspect() then
            -- This is the game's actual bullet-suppression/near-pass event.
            -- No sound listener, no search for the nearest player, no guessed shooter.
            counters.near = counters.near + 1
            enqueue(pawn, data.Instigator, "bullet_near_pass")
        end
    end)
    if not ok then warnOnce("near_error", "Near-pass hook error: " .. tostring(err)) end
end

local function shooterOf(source)
    local attacker = source:GetInstigator()
    if actorOK(attacker) then return attacker end
    local owner = source:GetOwner()
    if not valid(owner) then return nil end
    if actorOK(owner) then return owner end
    attacker = owner:GetInstigator()
    if actorOK(attacker) then return attacker end
    attacker = owner:GetOwner()
    if actorOK(attacker) then return attacker end
end

local function shotWeapon(context)
    local weapon = value(context)
    if not valid(weapon) or not weapon:HasAuthority()
            or not weapon:IsA("/Script/ReadyOrNot.BaseMagazineWeapon") then return nil end
    local attacker = shooterOf(weapon)
    if actorOK(attacker) and attacker:HasAuthority() then return attacker end
end

local function queuePath(attacker, start, finish, kind)
    if #impacts >= Config.MaxQueuedImpacts then
        counters.droppedImpacts = counters.droppedImpacts + 1
        return
    end
    -- Copy struct coordinates inside the hook. Never retain RemoteUnrealParam.
    impacts[#impacts+1] = {attacker=attacker, ax=start.X, ay=start.Y, az=start.Z,
        x=finish.X, y=finish.Y, z=finish.Z, kind=kind}
    counters.shotPaths = counters.shotPaths + 1
end

local function queueDirection(attacker, start, direction)
    local dx, dy, dz = direction.X, direction.Y, direction.Z
    local length = math.sqrt(dx*dx + dy*dy + dz*dz)
    if length < 0.000001 then return end
    local scale = Config.ShotPathLengthCm / length
    -- This is the actual fired direction extended into a sensing corridor,
    -- not a claim to have sampled every physical bullet/penetration position.
    queuePath(attacker, start,
        {X=start.X+dx*scale,Y=start.Y+dy*scale,Z=start.Z+dz*scale}, "shot_direction_near")
end

local function onHitscan(context, shot, localOnly, seed)
    counters.rawHitscans = counters.rawHitscans + 1
    local ok, err = pcall(function()
        local attacker = shotWeapon(context)
        if not attacker then return end
        local data = value(shot)
        queueDirection(attacker, data.Location, data.Direction)
        if counters.rawHitscans <= 4 then log("SHOT_SAMPLE hitscan shooter=" .. name(attacker)) end
    end)
    if not ok then warnOnce("hitscan_error", "Hitscan hook error: " .. tostring(err)) end
end

local function onMagazineFire(context, direction, start, seed)
    counters.rawFires = counters.rawFires + 1
    local ok, err = pcall(function()
        local attacker = shotWeapon(context)
        if not attacker then return end
        queueDirection(attacker, value(start), value(direction))
        if counters.rawFires <= 4 then log("SHOT_SAMPLE fire shooter=" .. name(attacker)) end
    end)
    if not ok then warnOnce("fire_event_error", "Weapon fire hook error: " .. tostring(err)) end
end

local function onHitscanHit(context, hit, time, start, distance, penetration, ammoIndex, seed)
    counters.rawHitReports = counters.rawHitReports + 1
    local ok, err = pcall(function()
        local attacker = shotWeapon(context)
        if not attacker then return end
        queuePath(attacker, value(start), value(hit).ImpactPoint, "hitscan_report_near")
        if counters.rawHitReports <= 4 then log("SHOT_SAMPLE hit_report shooter=" .. name(attacker)) end
    end)
    if not ok then warnOnce("hit_report_error", "Hitscan report hook error: " .. tostring(err)) end
end

local function onImpact(context, hit)
    counters.rawImpacts = counters.rawImpacts + 1
    local ok, err = pcall(function()
        local projectile = value(context)
        if counters.rawImpacts <= 4 then bindingSample("IMPACT_RAW", projectile) end
        if not valid(projectile) or not projectile:HasAuthority()
                or not projectile:IsA("/Script/ReadyOrNot.BulletProjectile") then return end
        counters.impactEvents = counters.impactEvents + 1
        local attacker = shooterOf(projectile)
        if not valid(attacker) or not attacker:IsA("/Script/ReadyOrNot.ReadyOrNotCharacter") then
            warnOnce("impact_no_shooter", "Bullet impact has no character in its Instigator/Owner chain; skipped.")
            return
        end
        local point = value(hit).ImpactPoint
        if #impacts >= Config.MaxQueuedImpacts then
            counters.droppedImpacts = counters.droppedImpacts + 1
            return
        end
        -- Copy coordinates before the transient projectile/hit parameters expire.
        impacts[#impacts+1] = {attacker=attacker, x=point.X, y=point.Y, z=point.Z}
    end)
    if not ok then warnOnce("impact_error", "Impact hook error: " .. tostring(err)) end
end

-- Diagnostic probes only: a respawn/validation is not counted as an impact.
local function onBulletRespawn(context)
    counters.respawns = counters.respawns + 1
    if counters.respawns <= 4 then bindingSample("BULLET_RESPAWN", value(context)) end
end
local function onBulletValidated(context)
    counters.validations = counters.validations + 1
    if counters.validations <= 4 then bindingSample("BULLET_VALIDATED", value(context)) end
end

local function processImpacts()
    if #impacts == 0 then return end
    if ticks >= nextSuspectRefresh then
        suspects = {}
        for _, pawn in ipairs(FindAllOf("ReadyOrNotCharacter") or {}) do
            if actorOK(pawn) and pawn:HasAuthority() and pawn:IsSuspect() then
                suspects[#suspects+1] = pawn
                if #suspects >= Config.MaxSuspectsForImpact then break end
            end
        end
        nextSuspectRefresh = ticks + math.ceil(1000 / Config.TickMs)
    end
    local positions = {}
    for _, pawn in ipairs(suspects) do
        if actorOK(pawn) and pawn:HasAuthority() then
            local pos = pawn:K2_GetActorLocation()
            positions[#positions+1] = {pawn=pawn, world=pawn:GetWorld(), x=pos.X, y=pos.Y, z=pos.Z}
        end
    end
    local limit = math.min(#impacts, Config.MaxEventsPerTick)
    for i = 1, limit do
        local event = impacts[i]
        if actorOK(event.attacker) then
            local world = event.attacker:GetWorld()
            for _, pos in ipairs(positions) do
                local dx, dy, dz = pos.x-event.x, pos.y-event.y, pos.z-event.z
                if event.ax then
                    local vx, vy, vz = event.x-event.ax, event.y-event.ay, event.z-event.az
                    local length2 = vx*vx+vy*vy+vz*vz
                    local t = length2 > 0 and ((pos.x-event.ax)*vx+(pos.y-event.ay)*vy+(pos.z-event.az)*vz)/length2 or 0
                    t = math.max(0,math.min(1,t))
                    dx,dy,dz = pos.x-(event.ax+t*vx), pos.y-(event.ay+t*vy), pos.z-(event.az+t*vz)
                end
                if same(world,pos.world) and dx*dx+dy*dy+dz*dz <= Config.ImpactRadiusCm^2 then
                    if event.ax then counters.shotNear = counters.shotNear + 1
                    else counters.impactNear = counters.impactNear + 1 end
                    enqueue(pos.pawn, event.attacker, event.kind or "bullet_impact_near")
                end
            end
        end
    end
    local remaining = {}
    for i = limit+1, #impacts do remaining[#remaining+1] = impacts[i] end
    impacts = remaining
end

local signatures = {
    [CHAR.."Multicast_TakeDamage"] = {"Damage","bIsPointDamage","DamageTypeClass","InstigatorCharacter","DamageCauser"},
    [CHAR.."Multicast_InflictSuppression"] = {"SuppressionData","CameraShake","bLessLethal"},
    [CHAR.."Multicast_InflictSuppression_NoLineOfSight"] = {"SuppressionData","CameraShake","bLessLethal"},
    [COMBAT.."ScriptedFireAtActor"] = {"InActor","InTime","bOverrideTarget","AccuracyPenaltyMultiplier","bInfiniteAmmo"},
    [COMBAT.."ScriptedLookAtActor"] = {"InActor","InTime"},
    [COMBAT.."StopScriptedFire"] = {}, [COMBAT.."StopScriptedLook"] = {},
    [CTRL.."GetCombatActivity"] = {"ReturnValue"},
    [CTRL.."RequestMoveAsync"] = {"Location","bProjectToNavigation","AcceptanceRadius","ReturnValue"},
    [CTRL.."AbortCover"] = {}, [CTRL.."AbortCoverLandmark"] = {},
    [CTRL.."AbortMove"] = {"bKeepVelocity"}, [CTRL.."IsMovingForRequest"] = {"RequestID","ReturnValue"},
    [TARGET.."AddKnownEnemy"] = {"Enemy","bForce"},
    [TARGET.."SetLastTrackedTarget"] = {"Target"},
    [PROJECTILE.."Multicast_SpawnImpactEffects"] = {"Hit","EffectsClass","DecalScale","bExitImpact","bArmorImpact"},
}

-- Offsets are parameter metadata checks, never raw-memory reads/writes.
-- These distinguish the current five-argument damage event from the old one.
local signatureOffsets = {
    [CHAR.."Multicast_TakeDamage"] = {0,4,8,16,24},
    [CHAR.."Multicast_InflictSuppression"] = {0,64,72},
    [CHAR.."Multicast_InflictSuppression_NoLineOfSight"] = {0,64,72},
    [COMBAT.."ScriptedFireAtActor"] = {0,8,12,16,20},
    [COMBAT.."ScriptedLookAtActor"] = {0,8},
    [CTRL.."RequestMoveAsync"] = {0,24,28,32},
    [MAGAZINE.."Multicast_PerformHitscan"] = {0,56,60},
    [MAGAZINE.."Multicast_OnFire"] = {0,24,48},
    [MAGAZINE.."Server_HitscanHit"] = {0,232,240,264,268,272,276},
}
local initStage = "start"
local function checkSignature(path, expected)
        initStage = "find " .. path
        local fn = StaticFindObject(path)
        if not valid(fn) then return false, "Missing UFunction: " .. path end
        functions[path] = fn
        -- In UE4SS 3.0.1 a UFunction Lua wrapper inherits UObject, not UStruct.
        -- It has Reflection(), but not ForEachProperty().
        initStage = "reflection " .. path
        local reflection = fn:Reflection()
        for i, n in ipairs(expected) do
            initStage = "parameter " .. path .. ":" .. n
            local prop = reflection:GetProperty(n)
            if not valid(prop) then
                return false, "Signature mismatch: " .. path .. " missing " .. n
            end
            if signatureOffsets[path] and prop:GetOffset_Internal() ~= signatureOffsets[path][i] then
                return false, "Signature mismatch: " .. path .. " offset of " .. n
            end
        end
    return true
end
local function checkSignatures()
    for path, expected in pairs(signatures) do
        local ok, why = checkSignature(path, expected)
        if not ok then return false, why end
    end
    return true
end

local function initialise()
    local ok, why = checkSignatures()
    if not ok then return false, why end
    local registered = {}
    local success, err = pcall(function()
        for _, entry in ipairs({
            {CHAR.."Multicast_TakeDamage", onDamage},
            {CHAR.."Multicast_InflictSuppression", onNearPass},
            {CHAR.."Multicast_InflictSuppression_NoLineOfSight", onNearPass},
            {PROJECTILE.."Multicast_SpawnImpactEffects", onImpact},
        }) do
            initStage = "hook " .. entry[1]
            local pre, post = RegisterHook(entry[1], function() end, entry[2])
            registered[#registered+1] = {entry[1],pre,post}
        end
    end)
    if not success then
        for _, h in ipairs(registered) do pcall(UnregisterHook, h[1], h[2], h[3]) end
        return false, tostring(err)
    end
    -- Current weapon hitscan/fire RPCs cover the route that never spawns the
    -- legacy BulletProjectile actor. Each hook is checked and logged separately.
    for _, entry in ipairs({
        {MAGAZINE.."Multicast_PerformHitscan", onHitscan, {"HitscanShot","bLocalOnly","Seed"}},
        {MAGAZINE.."Multicast_OnFire", onMagazineFire, {"DirectionNet","SpawnLoc","Seed"}},
        {MAGAZINE.."Server_HitscanHit", onHitscanHit,
            {"HitResult","Time","TraceBegin","Distance","Penetration","AmmoTypeIndex","Seed"}},
    }) do
        local checked, available, reason = pcall(checkSignature, entry[1], entry[3])
        if checked and available then
            local hooked, hookError = pcall(RegisterHook, entry[1], function() end, entry[2])
            if hooked then log("SHOT_HOOK_READY " .. entry[1])
            else log("SHOT_HOOK_SKIPPED " .. entry[1] .. ": " .. tostring(hookError)) end
        else
            log("SHOT_HOOK_SKIPPED " .. entry[1] .. ": " .. tostring(checked and reason or available))
        end
    end
    -- These probes only record lifecycle events. A missing/incompatible probe
    -- must not disable the four validated behavior hooks.
    for _, entry in ipairs({
        {BULLET.."OnProjectileValidated", onBulletValidated, {}},
        {BULLET.."OnRespawnProjectile", onBulletRespawn,
            {"RespawnLocation","RespawnRotation","newSpeed","newDamage","projectileReaction"}},
    }) do
        local checked, available, reason = pcall(checkSignature, entry[1], entry[3])
        if checked and available then
            local hooked, hookError = pcall(RegisterHook, entry[1], function() end, entry[2])
            if not hooked then log("PROBE_SKIPPED " .. entry[1] .. ": " .. tostring(hookError)) end
        else
            log("PROBE_SKIPPED " .. entry[1] .. ": " .. tostring(checked and reason or available))
        end
    end
    ready = true
    log("READY " .. VERSION .. " | host-only | movement=" .. tostring(Config.EnableMovement)
        .. " | override_target=" .. tostring(Config.OverrideCombatTarget)
        .. " | hit + shot-direction proximity | radius_cm=" .. Config.ImpactRadiusCm
        .. " | path_cm=" .. Config.ShotPathLengthCm)
    return true
end

local attempts = 0
local function tick()
    if not installed then
        attempts = attempts + 1
        local ok, result, reason = xpcall(initialise, function(err)
            return "stage=" .. initStage .. " error=" .. tostring(err) .. "\n" .. debug.traceback("", 2)
        end)
        if ok and result then installed = true
        else
            local message = tostring(ok and reason or result)
            warnOnce("init_" .. initStage, "INIT_FAILED " .. message)
            if attempts >= 20 then
                installed = true; ready = false
                log("DISABLED: " .. message)
            end
        end
    end
    if not ready then return end
    if reactionTickEnded and not reactionTickResumed then
        reactionTickResumed = true
        log("REACTION_TICK_RESUMED")
    end
    local impactOK, impactError = pcall(processImpacts)
    if not impactOK then warnOnce("impact_processing", "Impact processing error: " .. tostring(impactError)) end
    local processed = 0
    for id, event in pairs(pending) do
        pending[id] = nil; pendingCount = pendingCount - 1
        local ok, err = pcall(accept, event)
        if not ok then warnOnce("accept_" .. setupStage, "Reaction setup error stage=" .. setupStage .. ": " .. tostring(err)) end
        processed = processed + 1
        if processed >= Config.MaxEventsPerTick then break end
    end
    for id, s in pairs(active) do
        local ok, reason = pcall(step, s)
        if not ok then
            s.failures = s.failures + 1
            warnOnce("step", "Reaction update error: " .. tostring(reason))
            reason = s.failures >= 3 and "api_error" or nil
        else s.failures = 0 end
        if reason then
            local stopped, err = pcall(stop, s, reason)
            if not stopped then warnOnce("stop", "Cleanup error: " .. tostring(err)) end
            active[id] = nil; count = count - 1
        end
    end
    ticks = ticks + 1
    if ticks % Config.SummaryEveryTicks == 0 then
        log(string.format("STATUS active=%d hit=%d near=%d raw_near=%d raw_impacts=%d respawns=%d validations=%d impacts=%d impact_near=%d dropped_impacts=%d starts=%d fire_requests=%d move_requests=%d rejected_moves=%d raw_hitscans=%d raw_fires=%d raw_hit_reports=%d shot_paths=%d shot_near=%d",
            count,counters.hits,counters.near,counters.rawNear,counters.rawImpacts,counters.respawns,counters.validations,
            counters.impactEvents,counters.impactNear,counters.droppedImpacts,
            counters.starts,counters.fireRequests,counters.moveRequests,counters.rejectedMoves,
            counters.rawHitscans,counters.rawFires,counters.rawHitReports,counters.shotPaths,counters.shotNear))
    end
    if count > 0 and not reactionTickEnded then
        reactionTickEnded = true
        log("REACTION_TICK_END")
    end
end

log("Loading " .. VERSION .. ". No client assets or PAK required.")
-- 3.0.1 LoadMapPre has broken marshalling; LoadMapPost returns after its first
-- subscriber (normally BPModLoaderMod). InitGameState iterates all subscribers.
-- Register from the persistent main Lua state, never a temporary callback.
RegisterInitGameStatePreHook(function()
    -- Drop old references without calling into actors from the previous map.
    epoch = epoch + 1; active = {}; pending = {}; count = 0; pendingCount = 0
    impacts = {}; suspects = {}; nextSuspectRefresh = 0
    reactionTickEnded = false; reactionTickResumed = false
    log("GameState initializing: reaction state cleared.")
end)
if type(LoopInGameThreadWithDelay) == "function" then
    LoopInGameThreadWithDelay(Config.TickMs, tick)
else
    -- Older UE4SS: the async callback only queues work; all UObject access stays
    -- on the game thread. Never enqueue an unbounded backlog of game-thread jobs.
    local queued = false
    LoopAsync(Config.TickMs, function()
        if not queued then
            queued = true
            ExecuteInGameThread(function() queued = false; tick() end)
        end
        return false
    end)
end
