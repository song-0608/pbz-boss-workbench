"""Read the frozen offline skill and combo catalogs for the desktop workbench."""
from collections import defaultdict
import json
from pathlib import Path
import re

from build_boss_disk_repertoire import read_verified
from research_storage import PROJECT_STORAGE


CAPTURE = Path('创作协作/原生技能声明/20261121-084008-boss-combat-supplement')
EVIDENCE = Path('evidence/adaptation')
ROLES = {
    '042_AHua': '阿花', '056_YouLong': '游龙', '057_WanJun': '巨贼克万钧',
    '058_MadDoctor': '谢秋冬', '071_XianZhe': '弦儿', '073_YanQianSui': '烟千岁',
}
FOLDER_NAME = re.compile(r'[A-Za-z0-9_]+\.json')
SPECIAL_FILES = {'timelines.json', 'scripts.json', 'quarantined.json', 'root-reference-gaps.json'}


def load_json(path):
    return json.loads(path.read_bytes())


def short(path):
    return path.rsplit('.', 1)[-1]


class Catalog:
    def __init__(self, root, storage=PROJECT_STORAGE):
        self.directory = Path(storage) / CAPTURE
        evidence = Path(root) / EVIDENCE
        skills = load_json(evidence / 'native-boss-skill-repertoire-milestone-20261121.json')
        combos = load_json(evidence / 'native-boss-disk-combo-expansion-20261122.json')
        self.repertoire = self.directory / 'repertoire'
        self.combo_directory = self.directory / 'combo-index-v2'
        repertoire = read_verified(self.repertoire / 'summary.json', skills['catalog_summary_sha256'])
        combo = read_verified(self.combo_directory / 'summary.json', combos['expanded_summary_sha256'])
        if (repertoire['kind'] != 'offline_boss_disk_repertoire' or combo['kind'] != 'offline_boss_combo_tree_index'
                or any(repertoire[key] != combo[key] for key in ('scan_sha256', 'queue_sha256'))
                or any(record[key] is not False for record in (repertoire, combo)
                       for key in ('activation_allowed', 'game_started', 'installed'))):
            raise ValueError('技能目录和连招目录须来自同一次离线抓取')
        self.files = repertoire['files']
        self.combo_files = combo['files']
        self.folders = tuple(sorted(name[:-5] for name in self.files
                                    if FOLDER_NAME.fullmatch(name) and name not in SPECIAL_FILES))
        if len(self.folders) != repertoire['folders'] + 1 or 'native_support' not in self.folders:
            raise ValueError('技能目录缺少原生资源分组')
        parents = read_verified(self.combo_directory / 'parents.json', self.combo_files['parents.json'])
        self.parents = {row['class_path']: row for row in parents}
        if len(self.parents) != combo['parents'] or set(row['folder'] for row in parents) - set(self.folders):
            raise ValueError('连招目录的角色分组不完整')
        self.used_by = defaultdict(list)
        for row in parents:
            if row['activation_allowed'] is not False:
                raise ValueError('工作台只加载离线连招证据')
            for child in row['referenced_abilities']:
                self.used_by[child['class_path']].append(row['class_path'])
        self.roles = {}
        self.trees = None

    def role(self, folder):
        if folder not in self.folders:
            raise ValueError('未知原生资源分组')
        if folder not in self.roles:
            filename = folder + '.json'
            role = read_verified(self.repertoire / filename, self.files[filename])
            if role['folder'] != folder or any(row['activation_allowed'] is not False or row['playable'] is not False
                                                for row in role['skills']):
                raise ValueError('角色技能目录与分组不符')
            self.roles[folder] = role
        return self.roles[folder]

    def tree(self, path):
        if self.trees is None:
            self.trees = read_verified(self.combo_directory / 'trees.json', self.combo_files['trees.json'])
        return self.trees[path]

    def details(self, skill):
        path = skill['class_path']
        actions = skill['declared_actions']
        lines = [path, '', '原生技能路线  ' + skill['native_route'],
                 '时间线  ' + skill['timeline_resolution'],
                 '已声明动作  ' + (str(actions) if actions is not None else '未写入资源')]
        if skill['timeline_owner']:
            lines.append('时间线来源  ' + short(skill['timeline_owner']))
        if path in self.used_by:
            lines.extend(('', '引用这项技能的连招', *(short(parent) for parent in self.used_by[path])))
        parent = self.parents.get(path)
        if parent is not None:
            lines.extend(('', f"预设入口 {len(parent['choices'])} 个，行为树 {len(parent['trees'])} 棵"))
            for choice in parent['choices']:
                weight = '' if choice['weight'] is None else f"  权重 {choice['weight']:g}"
                lines.append('  ' + short(choice['path']) + weight)
            for tree_path in parent['trees']:
                tree = self.tree(tree_path)
                lines.extend(('', short(tree_path)))
                for node in tree['nodes']:
                    address = '.'.join(str(index + 1) for index in node['branch']) or '根节点'
                    ref = node['type']
                    if 'ability' in node:
                        ref = short(node['ability'])
                    elif 'subtree' in node:
                        ref = '子树 ' + node['subtree'][3]
                    props = node['properties']
                    if props.get('AbilityActivationMethod') == 'EAIAbilityActivationMethod::ByTactic':
                        ref += '（按战术标签选招）'
                        tag_query = props.get('TacticActionTagRequirements', {}).get('TagQuery', {})
                        tags = ', '.join(tag['TagName'] for tag in tag_query.get('TagDictionary', []))
                        if tags:
                            ref += ' ' + tags
                    decorators = ', '.join(item['type'] for item in node['decorators'])
                    lines.append(f"  {address}  {node['name']}  {ref}" + (f'  [{decorators}]' if decorators else ''))
            if parent['issues']:
                lines.extend(('', '资源缺口  ' + ' / '.join(parent['issues'])))
        return '\n'.join(lines)
