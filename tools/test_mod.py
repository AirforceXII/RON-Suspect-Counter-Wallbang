"""Execute the shipped Lua in Lua 5.4 with a UE4SS test host, not in the game."""
import json
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'tools/runtime'))
from lupa.lua54 import LuaRuntime

source = (ROOT/'package/Mods/ReactiveSuspects/Scripts/main.lua').read_text(encoding='utf-8')
interfaces = json.loads((ROOT/'evidence/interfaces.json').read_text(encoding='utf-8'))
shot_interfaces = json.loads((ROOT/'evidence/r11-static/shot-interfaces.json').read_text(encoding='utf-8'))
owners = {'0x1448c8d30':'ReadyOrNotCharacter', '0x14478e7e0':'BaseCombatActivity',
          '0x144801d30':'CyberneticController', '0x144959900':'TargetingComponent',
          '0x1448bbf70':'Projectile', '0x1447ce300':'BulletProjectile',
          '0x144798e90':'BaseMagazineWeapon'}

def host(legacy=False, mismatch=False, offset_mismatch=False, missing_probe=False, movement=False):
    lua = LuaRuntime(unpack_returned_tuples=True)
    lua.execute(r'''
        logs, hooks, signatures, calls, pawnList = {}, {}, {}, {}, {}
        clock, gameThread = 0, true
        registrationPhase, mapRegistrations = 'main', 0
        function print(s) logs[#logs+1]=s end
        function call(name, ...)
            assert(gameThread, 'UObject access outside game thread')
            calls[#calls+1]={name=name,args={...}}
        end
        function object(id)
            return {id=id, alive=true,
                IsValid=function(s) return s.alive end,
                GetAddress=function(s) return s.id end,
                GetFullName=function(s) return (s.ueClass or 'Object')..' obj'..s.id end,
                GetFName=function(s) return {ToString=function() return 'obj'..s.id end} end}
        end
        world=object(1); weapon=object(2); bulletClass=object(3); otherClass=object(4)
        function bulletClass:IsChildOf(c) return c==self end
        function otherClass:IsChildOf(c) return false end
        parameterOffsets={
            Multicast_TakeDamage={0,4,8,16,24},
            Multicast_InflictSuppression={0,64,72},
            Multicast_InflictSuppression_NoLineOfSight={0,64,72},
            ScriptedFireAtActor={0,8,12,16,20},
            ScriptedLookAtActor={0,8}, RequestMoveAsync={0,24,28,32},
            Multicast_PerformHitscan={0,56,60}, Multicast_OnFire={0,24,48},
            Server_HitscanHit={0,232,240,264,268,272,276}}
        function StaticFindObject(path)
            if path=='/Script/ReadyOrNot.BulletDamageType' then return bulletClass end
            if not signatures[path] then return {IsValid=function()return false end} end
            -- Model the actual 3.0.1 wrapper: no ForEachProperty on UFunction.
            return setmetatable({path=path, IsValid=function()return true end,
                Reflection=function()
                    return {GetProperty=function(s,n)
                        for i,actual in ipairs(signatures[path]) do
                            if actual==n then
                                local fnName=path:match(':([^:]+)$')
                                local offsets=parameterOffsets[fnName]
                                return {IsValid=function()return true end,
                                    GetOffset_Internal=function()return offsets and offsets[i] or 0 end}
                            end
                        end
                        return {IsValid=function()return false end}
                    end}
                end}, {__call=function(fn,receiver,...)
                    local name=fn.path:match(':([^:]+)$')
                    local body=receiver.nativeMethods and receiver.nativeMethods[name]
                    assert(type(body)=='function','Missing native test body for '..fn.path)
                    return body(receiver,...)
                end})
        end
        function RegisterHook(path,pre,post) hooks[path]=post; return 1,2 end
        function UnregisterHook(path,pre,post) hooks[path]=nil end
        function RegisterLoadMapPreHook(cb)
            error('Do not use the broken UE4SS 3.0.1 LoadMapPre bridge')
        end
        function RegisterInitGameStatePreHook(cb)
            assert(registrationPhase=='main', 'Map hook must retain the persistent main Lua state')
            mapRegistrations=mapRegistrations+1; stateInit=cb
        end
        function RegisterLoadMapPostHook(cb)
            error('3.0.1 LoadMapPost only invokes its first subscriber, already BPModLoaderMod')
        end
        function FindAllOf(class) assert(gameThread); return pawnList end
        function LoopInGameThreadWithDelay(ms,cb) assert(ms>=50); tick=cb end
        function LoopAsync(ms,cb) asyncTick=cb end
        function ExecuteInGameThread(cb) scheduled=cb end
        function pump()
            registrationPhase='temporary_callback'
            if asyncTick then
                gameThread=false; asyncTick(); gameThread=true
                if scheduled then local s=scheduled; scheduled=nil; s() end
            else tick() end
            registrationPhase='idle'
        end
        function param(o) return {get=function()return o end} end
        function makePawn(id, suspect, authority, swat)
            local p=object(id)
            p.suspect=suspect; p.authority=authority; p.swat=swat
            p.ueClass='/Script/ReadyOrNot.ReadyOrNotCharacter'
            p.pos={X=id*10,Y=0,Z=0}; p.equipped=weapon; p.world=world
            function p:IsA(c) return c==self.ueClass end
            function p:HasAuthority() return self.authority end
            function p:IsSuspect() return self.suspect end
            function p:IsOnSWATTeam() return self.swat end
            function p:IsDeadOrUnconscious() return self.dead or false end
            function p:IsArrested() return self.arrested or false end
            function p:GetWorld() return self.world end
            function p:GetCyberneticsController() return self.controller end
            function p:GetGameTimeSinceCreation() return clock end
            function p:K2_GetActorLocation() return self.pos end
            function p:GetEquippedWeapon() return self.equipped end
            function p:DrawWeapon() call('draw',self.id) end
            local c=object(id+1000); p.controller=c
            function c:HasAuthority() return p.authority end
            function c:IsCharacterEnemy(t) return t.swat end
            c.TargetingComponent=object(id+2000)
            c.TargetingComponent.ueClass='/Script/ReadyOrNot.TargetingComponent'
            function c.TargetingComponent:IsA(path)
                return path=='/Script/ReadyOrNot.TargetingComponent'
            end
            function c.TargetingComponent:GetClass()
                return {GetFullName=function()return 'Class /Script/ReadyOrNot.TargetingComponent' end}
            end
            function c.TargetingComponent:CallFunction(fn,...)
                if fn.path=='/Script/ReadyOrNot.TargetingComponent:AddKnownEnemy' then
                    local t,force=...; call('known',t.id,force)
                elseif fn.path=='/Script/ReadyOrNot.TargetingComponent:SetLastTrackedTarget' then
                    local t=...; call('target',t.id)
                else error('Unexpected explicit UFunction call') end
            end
            function c.TargetingComponent:AddKnownEnemy(t,force) call('known',t.id,force) end
            function c.TargetingComponent:SetLastTrackedTarget(t) call('target',t.id) end
            c.TargetingComponent.nativeMethods={
                AddKnownEnemy=c.TargetingComponent.AddKnownEnemy,
                SetLastTrackedTarget=c.TargetingComponent.SetLastTrackedTarget}
            function c:AbortCover() call('abort_cover',p.id) end
            function c:AbortCoverLandmark() call('abort_landmark',p.id) end
            local b=object(id+3000); b.CurrentScriptedFireAt={}; c.combat=b
            b.ueClass='/Script/ReadyOrNot.BaseCombatActivity'
            function c:GetCombatActivity() return b end
            function c:AddActivity(a,override) self.CurrentActivity=a; call('activity',p.id,override); return true end
            function c:RequestMoveAsync(v,project,radius)
                self.req=(self.req or 0)+1; call('move',p.id,v,project,radius)
                return self.reject and -1 or self.req
            end
            function c:IsMovingForRequest(id) return id==self.req end
            function c:AbortMove(keep) assert(keep==false); call('abort_move',p.id) end
            function b:ScriptedFireAtActor(t,secs,override,accuracy,infinite)
                assert(infinite==false and accuracy==1 and override==true)
                assert(p.controller.CurrentActivity~=self, 'combat component must not delegate to itself')
                self.CurrentScriptedFireAt.FireAtActor=t
                call('fire',p.id,t.id,secs)
            end
            function b:ScriptedLookAtActor(t,secs) call('look',p.id,t.id) end
            function b:EnterStrafeState() call('strafe',p.id) end
            function b:StopScriptedFire() self.CurrentScriptedFireAt.FireAtActor=nil; call('stop_fire',p.id) end
            function b:StopScriptedLook() call('stop_look',p.id) end
            b.nativeMethods={ScriptedFireAtActor=b.ScriptedFireAtActor,
                ScriptedLookAtActor=b.ScriptedLookAtActor,EnterStrafeState=b.EnterStrafeState,
                StopScriptedFire=b.StopScriptedFire,StopScriptedLook=b.StopScriptedLook}
            pawnList[#pawnList+1]=p
            return p
        end
        victim=makePawn(10,true,true,false); attacker=makePawn(20,false,true,true)
        function hit(v,a,dt,point,damage)
            hooks['/Script/ReadyOrNot.ReadyOrNotCharacter:Multicast_TakeDamage'](
                param(v),param(damage or 0),point~=false,param(dt or bulletClass),param(a),param(weapon))
        end
        function near(v,a,noLOS)
            local suffix=noLOS and '_NoLineOfSight' or ''
            hooks['/Script/ReadyOrNot.ReadyOrNotCharacter:Multicast_InflictSuppression'..suffix](
                param(v),param({Instigator=a,Strength=0,Distance=100}),param(nil),false)
        end
        function impact(pos,shooter,authority,isBullet,owner)
            local p=object(90)
            function p:HasAuthority() return authority~=false end
            function p:IsA(c) return isBullet~=false and c=='/Script/ReadyOrNot.BulletProjectile' end
            function p:GetInstigator() return shooter end
            function p:GetOwner() return owner end
            hooks['/Script/ReadyOrNot.Projectile:Multicast_SpawnImpactEffects'](
                param(p),param({ImpactPoint=pos}),param(nil),1,false,false)
        end
        function shotWeapon(shooter,authority,owner)
            local w=object(95)
            function w:IsA(c) return c=='/Script/ReadyOrNot.BaseMagazineWeapon' end
            function w:HasAuthority() return authority~=false end
            function w:GetInstigator() return shooter end
            function w:GetOwner() return owner end
            return w
        end
        function shot(start,dir,shooter,authority)
            hooks['/Script/ReadyOrNot.BaseMagazineWeapon:Multicast_PerformHitscan'](
                param(shotWeapon(shooter,authority)),param({Location=start,Direction=dir,Seed=1}),false,1)
        end
        function magazineFire(start,dir,shooter,authority)
            hooks['/Script/ReadyOrNot.BaseMagazineWeapon:Multicast_OnFire'](
                param(shotWeapon(shooter,authority)),param(dir),param(start),1)
        end
        function hitReport(start,finish,shooter,authority)
            hooks['/Script/ReadyOrNot.BaseMagazineWeapon:Server_HitscanHit'](
                param(shotWeapon(shooter,authority)),param({ImpactPoint=finish}),0,param(start),1000,1,0,1)
        end
        function times(name) local n=0;for _,c in ipairs(calls)do if c.name==name then n=n+1 end end;return n end
        function hasLog(s)for _,l in ipairs(logs)do if l:find(s,1,true)then return true end end;return false end
    ''')
    sig = lua.globals().signatures
    for row in interfaces['functions']+shot_interfaces['functions']:
        owner = owners.get(row['owner_constructor'])
        if owner:
            path = '/Script/ReadyOrNot.'+owner+':'+row['name']
            sig[path] = lua.table_from([p['name'] for p in row['parameters']])
    if mismatch:
        sig['/Script/ReadyOrNot.ReadyOrNotCharacter:Multicast_TakeDamage'] = lua.table_from(['Damage','DamageEvent'])
    if missing_probe:
        sig['/Script/ReadyOrNot.BulletProjectile:OnRespawnProjectile'] = lua.table_from(['RespawnLocation'])
    if legacy:
        lua.execute('LoopInGameThreadWithDelay=nil')
    if offset_mismatch:
        lua.execute('parameterOffsets.Multicast_TakeDamage[4]=8')
    test_source = source if movement is None else source.replace(
        'EnableMovement = true,', 'EnableMovement = '+str(movement).lower()+',')
    lua.execute(test_source)
    lua.execute('pump()')
    return lua

checks = []
def test(name, code, **kwargs):
    l = host(**kwargs)
    l.execute(code)
    checks.append({'name':name,'pass':True})

test('current-build signatures and hooks', '''
    assert(hasLog('READY r12')); assert(not hasLog('DISABLED'))
    local n=0; for _ in pairs(hooks)do n=n+1 end; assert(n==9)
''')
test('disabled movement fixture retains aim and fire without move cleanup', '''
    hit(victim,attacker); pump()
    assert(times('known')==1 and times('target')==1)
    assert(times('look')==1 and times('fire')==1 and times('move')==0)
    assert(hasLog('override_target=true') and hasLog('movement=false') and hasLog('STEP_END obj10') and hasLog('REACTION_TICK_END'))
    assert(not hasLog('REACTION_TICK_RESUMED'))
    clock=0.1; pump(); assert(hasLog('REACTION_TICK_RESUMED'))
    clock=1; pump(); assert(times('fire')==2 and times('move')==0)
    clock=10; pump(); assert(times('stop_fire')==1 and times('abort_move')==0)
''')

test('opt-in movement retains hit including armour zero-damage behavior', '''
    hit(victim,attacker); pump()
    assert(times('fire')==1 and times('move')==1 and times('strafe')==0)
    assert(hasLog('trigger=bullet_hit'))
''', movement=True)
test('both native near-pass paths trigger without requiring nonzero suppression strength', '''
    near(victim,attacker,false); pump(); assert(times('fire')==1)
    clock=1; near(victim,attacker,true); pump()
    assert(times('fire')==2 and hasLog('trigger=bullet_near_pass'))
''')
test('client authority and non-suspect exclusions', '''
    victim.authority=false; hit(victim,attacker); near(victim,attacker); pump()
    assert(times('fire')==0 and times('move')==0)
    victim.authority=true; victim.suspect=false; hit(victim,attacker); pump(); assert(#calls==0)
''')
test('no shooter guessing, self or friendly retaliation', '''
    hit(victim,nil); pump(); assert(times('fire')==0)
    near(victim,victim); pump(); assert(times('fire')==0)
    friend=makePawn(30,true,true,false); near(victim,friend); pump(); assert(times('fire')==0)
''')
test('non-bullet or non-point damage does not trigger', '''
    hit(victim,attacker,otherClass); pump(); assert(times('fire')==0)
    hit(victim,attacker,bulletClass,false); pump(); assert(times('fire')==0)
''')
test('repeated events coalesce and refresh reaction expiry', '''
    for i=1,200 do near(victim,attacker) end
    pump(); assert(times('activity')==0 and times('fire')==1)
    clock=7; hit(victim,attacker); pump()
    clock=10; pump(); assert(times('stop_fire')==0)
    clock=16; pump(); assert(times('stop_fire')==1 and times('abort_move')==0)
''')
test('opt-in stuck side-step requests original navigation pursuit', '''
    hit(victim,attacker); pump()
    clock=1; pump(); clock=2; pump()
    local last;for _,c in ipairs(calls)do if c.name=='move' then last=c end end
    assert(last.args[2].X==attacker.pos.X and last.args[2].Y==attacker.pos.Y)
''', movement=True)
test('dead and arrested suspects stop reacting', '''
    victim.dead=true; hit(victim,attacker); pump(); assert(times('fire')==0)
    victim.dead=false; victim.arrested=true; near(victim,attacker); pump(); assert(times('fire')==0)
''')
test('expiry does not abort a newer unrelated movement request', '''
    hit(victim,attacker); pump(); victim.controller.req=999
    clock=10; pump(); assert(times('abort_move')==0 and times('stop_fire')==1)
''', movement=True)
test('map transition drops actor references and delayed reactions', '''
    hit(victim,attacker); pump(); near(victim,attacker)
    stateInit(); calls={}; victim.alive=false; attacker.alive=false
    pump(); assert(#calls==0)
''')
test('wrong UFunction ABI disables all hooks', '''
    for i=1,25 do pump() end
    assert(hasLog('DISABLED: Signature mismatch'))
    assert(next(hooks)==nil and #calls==0)
''', mismatch=True)
test('older UE4SS scheduler never accesses objects on async thread', '''
    assert(hasLog('READY r12')); hit(victim,attacker); pump()
    assert(times('fire')==1 and times('move')==0)
''', legacy=True)

test('3.0.1 UFunction lacks ForEachProperty but reflection validation succeeds', '''
    local fn=StaticFindObject('/Script/ReadyOrNot.ReadyOrNotCharacter:Multicast_TakeDamage')
    assert(fn.ForEachProperty==nil and fn.Reflection~=nil)
    assert(hasLog('READY r12')); near(victim,attacker); pump(); assert(times('fire')==1)
''')

test('changed parameter offset is rejected before installing hooks', '''
    for i=1,25 do pump() end
    assert(hasLog('DISABLED: Signature mismatch'))
    assert(not hasLog('READY r12') and next(hooks)==nil)
''', offset_mismatch=True)

test('legacy map hook stays in persistent state and survives repeated callbacks', '''
    assert(mapRegistrations==1 and type(stateInit)=='function')
    collectgarbage('collect')
    hit(victim,attacker); pump(); stateInit(); calls={}; pump(); assert(#calls==0)
    hit(victim,attacker); pump(); assert(times('fire')==1)
    stateInit(); calls={}; pump(); assert(#calls==0 and mapRegistrations==1)
''', legacy=True)

test('explicit UFunction call works when target component member lookup is not callable', '''
    victim.controller.TargetingComponent.AddKnownEnemy=object(0)
    victim.controller.TargetingComponent.SetLastTrackedTarget=object(0)
    hit(victim,attacker); pump()
    assert(times('known')==1 and times('target')==1 and times('fire')==1)
''')

test('wrong native targeting receiver is rejected', '''
    victim.controller.TargetingComponent.ueClass='OtherComponent'
    hit(victim,attacker); pump(); assert(times('known')==0 and times('fire')==0)
    assert(hasLog('receiver class mismatch'))
''')

test('nearby bullet impact triggers from true shooter with no visibility query', '''
    impact({X=victim.pos.X+100,Y=0,Z=0},attacker); pump()
    assert(times('fire')==1 and times('move')==0 and hasLog('trigger=bullet_impact_near'))
''')

test('far impacts, clients, non-bullet projectiles and unknown shooters do not react', '''
    impact({X=99999,Y=0,Z=0},attacker); pump(); assert(times('fire')==0)
    impact(victim.pos,attacker,false); impact(victim.pos,attacker,true,false)
    impact(victim.pos,nil); pump(); assert(times('fire')==0)
''')

test('projectile owner chain resolves its actual shooter', '''
    local owner=object(80)
    function owner:IsA(c) return false end
    function owner:GetInstigator() return nil end
    function owner:GetOwner() return attacker end
    impact(victim.pos,nil,true,true,owner); pump(); assert(times('fire')==1)
''')

test('impact bursts are bounded and map init drops queued impacts', '''
    for i=1,100 do impact(victim.pos,attacker) end
    for i=1,200 do pump() end
    assert(hasLog('dropped_impacts=36'))
    impact(victim.pos,attacker); stateInit(); calls={}; pump(); assert(#calls==0)
''')

test('unavailable UObject helper and combat member lookups cannot block validated native calls', '''
    local t=victim.controller.TargetingComponent
    t.GetClass=object(0); t.IsA=object(0); t.CallFunction=object(0)
    t.AddKnownEnemy=object(0); t.SetLastTrackedTarget=object(0)
    local b=victim.controller.combat
    b.ScriptedFireAtActor=object(0); b.ScriptedLookAtActor=object(0); b.EnterStrafeState=object(0)
    b.StopScriptedFire=object(0); b.StopScriptedLook=object(0)
    hit(victim,attacker); pump(); assert(times('fire')==1 and times('move')==0)
    clock=10; pump(); assert(times('stop_fire')==1)
''')

test('raw impact and near-pass diagnostics precede suspect and projectile filters', '''
    impact(victim.pos,attacker,true,false)
    near(attacker,attacker)
    for i=1,200 do pump() end
    assert(hasLog('raw_impacts=1') and hasLog('raw_near=1'))
    assert(times('fire')==0)
''')

test('diagnostic projectile events do not manufacture an impact or reaction', '''
    local p=object(90)
    hooks['/Script/ReadyOrNot.BulletProjectile:OnProjectileValidated'](param(p))
    hooks['/Script/ReadyOrNot.BulletProjectile:OnRespawnProjectile'](param(p))
    for i=1,200 do pump() end
    assert(hasLog('respawns=1') and hasLog('validations=1') and times('fire')==0)
''')

test('enum backing descriptor is not exposed as a runtime parameter', '''
    local fn=StaticFindObject('/Script/ReadyOrNot.BulletProjectile:OnRespawnProjectile')
    assert(not fn:Reflection():GetProperty('UnderlyingType'):IsValid())
    assert(hasLog('READY r12') and not hasLog('DISABLED'))
''')

test('optional diagnostic signature mismatch does not disable core hit retaliation', '''
    assert(hasLog('PROBE_SKIPPED') and hasLog('READY r12'))
    hit(victim,attacker); pump(); assert(times('fire')==1 and times('move')==0)
''', missing_probe=True)

test('native main activity is preserved while separate combat component receives requests', '''
    local main=object(800); main.ueClass='/Script/ReadyOrNot.KickDoorActivity'
    victim.controller.CurrentActivity=main
    hit(victim,attacker); pump()
    assert(victim.controller.CurrentActivity==main and times('activity')==0)
    assert(times('fire')==1 and times('move')==0)
    clock=0.7; pump(); assert(victim.controller.CurrentActivity==main and times('fire')==2)
    assert(hasLog('COMBAT_COMPONENT') and hasLog('CALL_END obj10 ScriptedFireAtActor'))
''')

test('observed self-delegating hierarchy is rejected before fire execution', '''
    victim.controller.CurrentActivity=victim.controller.combat
    hit(victim,attacker); pump()
    assert(times('activity')==0 and times('fire')==0 and times('move')==0)
    assert(times('stop_fire')==0 and hasLog('combat_is_current_activity'))
''')

test('first native call trace identifies the unreturned or failing operation', '''
    victim.controller.combat.nativeMethods.ScriptedLookAtActor=function() error('simulated native binding failure') end
    hit(victim,attacker); pump()
    assert(hasLog('CALL_BEGIN obj10 ScriptedLookAtActor'))
    assert(not hasLog('CALL_END obj10 ScriptedLookAtActor'))
    assert(hasLog('Reaction update error') and times('fire')==0)
''')

test('shipped r12 defaults react and request native movement without activity replacement', '''
    shot({X=0,Y=0,Z=0},{X=1,Y=0,Z=0},attacker); pump()
    assert(hasLog('READY r12') and hasLog('movement=true'))
    assert(times('fire')==1 and times('move')==1 and times('activity')==0)
    clock=1; pump(); assert(times('fire')==2 and times('move')==2)
    clock=10; pump(); assert(times('stop_fire')==1 and times('abort_move')==1)
''', movement=None)

test('missed hitscan shot triggers in 3D corridor without damage or suppression', '''
    victim.pos={X=3000,Y=180,Z=100}
    shot({X=0,Y=0,Z=100},{X=2,Y=0,Z=0},attacker); pump()
    assert(times('fire')==1 and times('activity')==0 and times('move')==0)
    assert(hasLog('trigger=shot_direction_near') and not hasLog('trigger=bullet_hit'))
''')

test('magazine fire path works without projectile or hitscan lifecycle events', '''
    victim.pos={X=2000,Y=0,Z=0}
    magazineFire({X=0,Y=0,Z=0},{X=1,Y=0,Z=0},attacker); pump()
    assert(times('fire')==1 and hasLog('SHOT_SAMPLE fire'))
''')

test('corridor does not trigger far lateral, behind muzzle, beyond length or other floor', '''
    local start={X=0,Y=0,Z=0}; local dir={X=1,Y=0,Z=0}
    for _,pos in ipairs({{X=1000,Y=251,Z=0},{X=-1000,Y=0,Z=0},
            {X=11000,Y=0,Z=0},{X=1000,Y=0,Z=300}}) do
        victim.pos=pos; shot(start,dir,attacker); pump()
    end
    assert(times('fire')==0)
''')

test('hit report uses finite actual segment including impact vicinity', '''
    victim.pos={X=500,Y=100,Z=0}
    hitReport({X=0,Y=0,Z=0},{X=1000,Y=0,Z=0},attacker); pump()
    assert(times('fire')==1 and hasLog('trigger=hitscan_report_near'))
    stateInit(); calls={}; victim.pos={X=2000,Y=0,Z=0}
    hitReport({X=0,Y=0,Z=0},{X=1000,Y=0,Z=0},attacker); pump()
    assert(times('fire')==0)
''')

test('shot sources reject clients, missing shooter, self, friendly and other world', '''
    local start={X=0,Y=0,Z=0}; local dir={X=1,Y=0,Z=0}
    shot(start,dir,attacker,false); shot(start,dir,nil); shot(start,dir,victim)
    local friendly=makePawn(30,true,true,false); shot(start,dir,friendly)
    pump(); assert(times('fire')==0)
    attacker.world=object(88); shot(start,dir,attacker); pump(); assert(times('fire')==0)
''')

test('new shot queue copies transient vectors and map init discards them', '''
    victim.pos={X=1000,Y=0,Z=0}
    local start={X=0,Y=0,Z=0}; local dir={X=1,Y=0,Z=0}
    shot(start,dir,attacker); start.X=99999; dir.Y=99999; pump()
    assert(times('fire')==1)
    stateInit(); calls={}; shot({X=0,Y=0,Z=0},{X=1,Y=0,Z=0},attacker)
    stateInit(); pump(); assert(times('fire')==0)
''')

test('shot bursts remain bounded and zero directions do not create reactions', '''
    victim.pos={X=1000,Y=0,Z=0}
    shot({X=0,Y=0,Z=0},{X=0,Y=0,Z=0},attacker); pump(); assert(times('fire')==0)
    for i=1,100 do shot({X=0,Y=0,Z=0},{X=1,Y=0,Z=0},attacker) end
    for i=1,200 do pump() end
    assert(hasLog('dropped_impacts=36') and times('fire')==1)
''')

assert any(p['name']=='UnderlyingType' and int(p['flags'],16)==0
           for f in interfaces['functions'] if f['name']=='OnRespawnProjectile'
           for p in f['auxiliary_properties'])

report={'runtime':'Lua 5.4 via lupa 2.6', 'classification':'offline mocked UE4SS/game interface tests',
        'main_lua_sha256': hashlib.sha256(source.encode('utf-8')).hexdigest(),
        'checks':checks, 'game_loading':'NOT_TESTED', 'actual_shooting_movement':'NOT_TESTED',
        'unmodified_client_replication':'NOT_TESTED'}
(ROOT/'evidence/offline-tests.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))


