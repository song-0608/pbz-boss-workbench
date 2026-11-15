"""用途：同一离线研究进程仅加载两项能力类供只读检查，不生成角色、不激活能力。"""
import hashlib
import json
from pathlib import Path
import time
import sys
import official_validation as v
import research_game_menu as menu


def main():
    state = json.loads(v.state_path().read_text(encoding='utf-8'))
    if (state.get('restored') or state.get('network_active') or not state.get('readonly_ai_experiment')
            or state.get('boss_lifecycle_experiment') or time.time() > state['deadline_unix'] - 120):
        raise RuntimeError('Idle read-only offline carrier required; active control cannot be overwritten')
    v.verify_build(state['ue4ss_loader_manifest'])
    row = next(r for r in state['ue4ss_loader_manifest']
               if r['physical_path'].replace('\\', '/').endswith('/PBZObserveAI/Scripts/main.lua'))
    target = Path(row['physical_path'])
    all_subtrees='--all-subtrees' in sys.argv[1:]
    source = '''-- 用途：仅加载已确认的能力类，交给外部只读反射工具；不生成或激活。
ExecuteInGameThread(function()
    local ok,why=pcall(function()
        local seen={};local nodes=0
        local function inspect_node(node)
            if not(node and node:IsValid())or seen[node:GetAddress()]then return end
            seen[node:GetAddress()]=true;nodes=nodes+1;assert(nodes<=128,'tree node bound exceeded')
            local path=node:GetFullName();print('PBZ_ATTACK_CONTRACT:TREE_NODE='..path..'\\n')
            local cls=node:GetClass();local depth=0
            while cls and cls:IsValid()and depth<12 do
                cls:ForEachProperty(function(prop)
                    local declaration=prop:GetFullName()
                    if declaration:match('^ObjectProperty ')or declaration:match('^ClassProperty ')then
                        local name=prop:GetFName():ToString();local value=node[name]
                        if value and value:IsValid()then print('PBZ_ATTACK_CONTRACT:NODE_REF='..path..'|'..name..'|'..value:GetFullName()..'\\n')end
                    end
                end)
                cls=cls:GetSuperStruct();depth=depth+1
            end
            if node:IsA('/Script/AIModule.BTCompositeNode')then
                node.Children:ForEach(function(_,item)
                    local child=item:get();inspect_node(child.ChildTask);inspect_node(child.ChildComposite)
                end)
            end
        end
        local paths={
            '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Attack_01.GA_AHua_Attack_01_C',
            '/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/GA_AHua_Skill_06.GA_AHua_Skill_06_C',
            ALL_SUBTREE_PATHS
        }
        for _,path in ipairs(paths)do
            local class=LoadAsset(path);assert(class and class:IsValid(),'ability class not loaded')
            print('PBZ_ATTACK_CONTRACT:CLASS='..class:GetFullName()..'\\n')
            if class:GetCDO():IsA('/Script/SGameAI.RunSubtreeAbility')then
                -- 用途：只读类默认对象的连招子树映射；不运行ChooseTree，不修改权重。
                local defaults=class:GetCDO();assert(defaults and defaults:IsValid(),'default object unavailable')
                local count=0
                defaults.ComboTreeWithWeight:ForEach(function(key,value)
                    count=count+1;assert(count<=32,'combo map exceeds diagnostic bound')
                    local tree=key:get();assert(tree and tree:IsValid(),'combo tree key invalid')
                    print('PBZ_ATTACK_CONTRACT:COMBO_TREE='..tree:GetFullName()..'|weight='..tostring(value:get())..'\\n')
                    inspect_node(tree.RootNode)
                end)
                print('PBZ_ATTACK_CONTRACT:COMBO_COUNT='..count..'\\n')
            end
        end
        print('PBZ_ATTACK_CONTRACT:READY=classes only; no ability activation\\n')
    end)
    if not ok then print('PBZ_ATTACK_CONTRACT:REJECTED='..tostring(why)..'\\n')end
end)
'''
    base='/PBZCombatAsset/ActorData/Mobs/042_AHua/Ability/GuiTouDao/Abilities/New/'
    names=('GA_AHua_PunishCounter_01','GA_AHua_Homing_Flower','GA_AHua_Homing_Flower_Hard')
    additional='\n'.join("            '"+base+name+'.'+name+"_C',"for name in names)if all_subtrees else''
    source=source.replace('ALL_SUBTREE_PATHS',additional)
    data = source.encode('utf-8')
    work = Path(state['work'])
    (work / 'attack-readonly-before.lua').write_bytes(target.read_bytes())
    row['sha256'] = hashlib.sha256(data).hexdigest()
    v.save(v.state_path(), state)
    target.write_bytes(data)
    (work / 'attack-readonly-probe.lua').write_bytes(data)
    v.verify_build(state['ue4ss_loader_manifest'])
    print(menu.click(0, 0, 2560, 1600, 'observe_reload'))


if __name__ == '__main__':
    main()
