-- Versioned extension of the accepted bridge. Restoration remains owned by that bridge.
local Extension={}
function Extension.extend(Bridge)
    function Bridge:camera_lock(receipt)
        if receipt.player_target_lock then return receipt.player_target_lock end
        self:check(receipt)
        assert(self.api.remote and receipt.remote_control and self.api.target_selector and receipt.combat,
            'verified remote combat and target selector required')
        local Lock=require('player_target_lock')
        receipt.player_target_lock=Lock.new({
            target=function()
                self:check(receipt)
                if receipt.target_transition then return nil end
                local ref=receipt.combat.selected_target
                return ref and self.calls:optional(ref)and ref or nil
            end,
            same=function(a,b)return a and b and a.name==b.name and a.address==b.address and a.class==b.class end,
            eligible=function(reference)
                local target=self.calls:resolve(reference)
                if not self.api.combat:verify_target(receipt.combat)then return false end
                return self.api.target_selector:eligible(self.calls:resolve(receipt.boss),
                    self.calls:resolve(receipt.player),target)
            end,
            position=function(reference)
                local target=self.calls:resolve(reference)
                local boss=self.calls:resolve(receipt.boss)
                local a,b=boss:K2_GetActorLocation(),target:K2_GetActorLocation()
                local height=self.profile.camera.pivot_height or 80
                return {X=a.X,Y=a.Y,Z=a.Z+height},{X=b.X,Y=b.Y,Z=b.Z+80}
            end,
            rotation=function()return self.api.remote.native.rotation(self:check(receipt))end,
            set_rotation=function(rotation)
                self.api.remote.native.set_rotation(self:check(receipt),rotation)
            end,
        })
        return receipt.player_target_lock
    end
    function Bridge:toggle_target_lock(receipt)
        self:check(receipt)
        assert(receipt.input_enabled and self:verify_control(receipt),'target lock requires active control')
        local lock=self:camera_lock(receipt)
        receipt.player_lock_initialized=true
        local ok,why=lock:toggle()
        if self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOCK',tostring(lock.enabled)..'|'..tostring(why or'manual'))end
        return ok,why
    end
    local update,look,restore=Bridge.update_camera,Bridge.look,Bridge.restore
    function Bridge:update_camera(receipt)
        self:check(receipt)
        if receipt.camera_rig and receipt.combat and receipt.remote_control then
            local lock=self:camera_lock(receipt)
            if not receipt.player_lock_initialized then
                receipt.player_lock_initialized=true
                local enabled=lock:toggle()
                if self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOCK',tostring(enabled)..'|initial')end
            end
            -- Keep the camera on its current orientation while F7 awaits native target readback.
            if not receipt.target_transition then
                local ok,why=lock:update()
                if not ok and self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOST',why)end
            end
        end
        return update(self,receipt)
    end
    function Bridge:look(receipt,yaw,pitch)
        self:check(receipt)
        if receipt.player_target_lock and receipt.player_target_lock.enabled then return true end
        return look(self,receipt,yaw,pitch)
    end
    function Bridge:restore(receipt,...)
        if receipt.player_target_lock then receipt.player_target_lock:clear('restoring player')end
        return restore(self,receipt,...)
    end
    return Bridge
end
return Extension
