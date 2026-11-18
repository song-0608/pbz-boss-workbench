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
            frame_seconds=function()
                self:check(receipt)
                assert(self.api.locomotion,'verified locomotion clock required for camera following')
                return self.api.locomotion.native.frame_seconds(self.calls:resolve(receipt.boss))
            end,
        })
        return receipt.player_target_lock
    end
    function Bridge:toggle_target_lock(receipt)
        self:check(receipt)
        assert(receipt.input_enabled and self:verify_control(receipt),'target lock requires active control')
        local lock=self:camera_lock(receipt)
        receipt.manual_look_degrees=0
        receipt.player_lock_initialized=true
        local ok,why=lock:toggle()
        if self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOCK',tostring(lock.enabled)..'|'..tostring(why or'manual'))end
        return ok,why
    end
    local update,look,restore=Bridge.update_camera,Bridge.look,Bridge.restore
    function Bridge:update_camera(receipt)
        self:check(receipt)
        local followed=false
        if receipt.camera_rig and receipt.combat and receipt.remote_control then
            local lock=self:camera_lock(receipt)
            if not receipt.player_lock_initialized then
                receipt.player_lock_initialized=true
                -- Combat targeting and camera locking are independent. Keep the
                -- verified combat target; camera starts free until middle click.
                if self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOCK','false|initial-free')end
            end
            -- Keep the camera on its current orientation while F7 awaits native target readback.
            if not receipt.target_transition then
                local ok,why=lock:update()
                if not ok and self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOST',why)end
                followed=ok and lock.enabled
            end
        end
        local ok,why=update(self,receipt)
        if ok~=true then return ok,why end
        if followed then
            -- Target following may rotate after mouse sampling. Forward movement
            -- must use this frame's final orientation, not the previous heading.
            return true,self.api.remote.native.rotation(self:check(receipt)).Yaw
        end
        return true
    end
    function Bridge:look(receipt,yaw,pitch)
        self:check(receipt)
        local lock=receipt.player_target_lock
        if lock and lock.enabled then
            local threshold=require('player_3c_tuning').resolve(self.profile.id).manual_unlock_degrees
            local magnitude=math.abs(yaw)+math.abs(pitch)
            receipt.manual_look_degrees=magnitude<0.05 and 0 or((receipt.manual_look_degrees or 0)+magnitude)
            if receipt.manual_look_degrees<threshold then
                return true,self.api.remote.native.rotation(self:check(receipt)).Yaw
            end
            lock:clear('manual camera input');receipt.manual_look_degrees=0
            if self.api.experience_log then self.api.experience_log('TARGET_CAMERA_LOCK','false|manual-camera-input')end
        end
        local ok,why=look(self,receipt,yaw,pitch)
        if ok~=true then return ok,why end
        return true,self.api.remote.native.rotation(self:check(receipt)).Yaw
    end
    local start=Bridge.start_skill
    function Bridge:start_skill(receipt,id)
        -- Skills own their native gait/root motion. Only the temporary walking
        -- override is released; resource/cooldown/ability activity stays native.
        if self.api.locomotion and receipt.remote_control and receipt.remote_control.locomotion then
            self.api.locomotion:suspend(receipt.remote_control.locomotion)
        end
        local token=start(self,receipt,id)
        if token==false and self.api.experience_log then
            receipt.native_skill_rejections=receipt.native_skill_rejections or{}
            local failures=(receipt.native_skill_rejections[id]or 0)+1
            receipt.native_skill_rejections[id]=failures
            self.api.experience_log('SKILL_NATIVE_REJECTED',id..'|consecutive='..failures..'|no-cooldown-or-resource-override')
        elseif token then
            if receipt.native_skill_rejections then receipt.native_skill_rejections[id]=nil end
        end
        return token
    end
    function Bridge:restore(receipt,...)
        if receipt.player_target_lock then receipt.player_target_lock:clear('restoring player')end
        return restore(self,receipt,...)
    end
    return Bridge
end
return Extension
