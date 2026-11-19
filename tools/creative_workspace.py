"""Shared UE authoring proposals and three-way integration, without game access."""
import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
from pathlib import Path,PurePosixPath
import re
import shutil
import subprocess
import uuid

from research_storage import PROJECT_STORAGE

CONFIGS=('Config/PBZCreative/3c.json','Config/PBZCreative/effects.json','Config/PBZCreative/scene.json')
LIMITS={'mouse_scale':(.05,1),'look_step_degrees':(10,45),'manual_unlock_degrees':(.25,10),
        'skill_buffer_seconds':(0,.25),'walk_speed_cm_s':(150,900),'turn_rate_degrees_s':(90,900)}
ROLES={'*','ahua_guitoudao','057_wanjun','073_yanqiansui','056_youlong','058_maddoctor','071_xianzhe'}
MAX_FILES=512
MAX_BYTES=512*1024*1024
MISSING=object()


def canonical(value):return (json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2,allow_nan=False)+'\n').encode('utf-8')
def digest(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_bytes(),parse_constant=lambda value:(_ for _ in ()).throw(ValueError('nonfinite JSON: '+value)))


def file_digest(path):
    h=hashlib.sha256()
    with plain(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def plain(path):
    path=Path(path).absolute()
    for p in (path,*path.parents):
        assert not p.is_symlink() and not getattr(p,'is_junction',lambda:False)(),'linked collaboration path rejected'
        if p.exists():assert not getattr(p.lstat(),'st_file_attributes',0)&0x400,'reparse collaboration path rejected'
    return path


def paths(storage=PROJECT_STORAGE,lane='ue'):
    assert lane in ('ue','backend'),'unknown authoring lane'
    base=plain(Path(storage)/'创作协作')
    folder='UE工程/PBZCreative' if lane=='ue' else '后台草稿/PBZCreative'
    return dict(base=base,workspace=base/folder,proposals=base/'提案',integrations=base/'集成',
                active=base/'active.json',lock=base/'merge.lock')


def relative(name):
    assert isinstance(name,str),'creative path must be text'
    p=PurePosixPath(name)
    assert isinstance(name,str) and str(p)==name and not p.is_absolute() and '\\' not in name and ':' not in name
    assert not any(part in ('','.','..') for part in p.parts),'invalid creative asset path'
    assert name in CONFIGS or (name.startswith('Content/PBZCreative/') and p.suffix.lower() in ('.uasset','.umap','.uexp','.ubulk')), \
        'only owned creative assets and shared config may be submitted'
    return name


def validate_config(name,value):
    assert isinstance(value,dict) and type(value.get('schema')) is int and value['schema']==1,'creative config schema required'
    canonical(value)  # Reject nonfinite values, including nested visual preset values.
    if name==CONFIGS[0]:
        assert set(value)=={'schema','profiles'} and isinstance(value['profiles'],dict)
        assert set(value['profiles'])<=ROLES,'unknown control role'
        for role,settings in value['profiles'].items():
            assert isinstance(settings,dict) and set(settings)<=set(LIMITS),'unknown 3C field'
            for key,n in settings.items():
                low,high=LIMITS[key]
                assert type(n) in (float,int) and math.isfinite(n) and low<=n<=high,'3C value outside range: '+key
    else:
        assert set(value)=={'schema','presets'} and isinstance(value['presets'],dict),'visual presets must be a data object'
    return value


def atomic(path,raw):
    path=plain(path);path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.'+uuid.uuid4().hex+'.tmp')
    try:
        with tmp.open('xb') as f:f.write(raw)
        os.replace(tmp,path)
    finally:
        if tmp.exists():tmp.unlink()


@contextmanager
def merge_lock(storage=PROJECT_STORAGE):
    p=paths(storage);p['base'].mkdir(parents=True,exist_ok=True)
    try:fd=os.open(p['lock'],os.O_WRONLY|os.O_CREAT|os.O_EXCL)
    except FileExistsError:raise RuntimeError('另一个窗口正在集成；若上次异常退出，请先检查 merge.lock，勿重复覆盖。')
    try:
        os.write(fd,canonical(dict(pid=os.getpid())));os.close(fd)
        yield
    finally:p['lock'].unlink()


def initialize(storage=PROJECT_STORAGE,lane='ue'):
    p=paths(storage,lane);workspace=plain(p['workspace'])
    project=dict(FileVersion=3,EngineAssociation='5.8',Category='ModAuthoring',
        Description='Independent authoring workspace; PBZ runtime compatibility requires separate validation.',
        Plugins=[dict(Name='Niagara',Enabled=True),dict(Name='EnhancedInput',Enabled=True)])
    initial={'PBZCreative.uproject':canonical(project),
        CONFIGS[0]:canonical(dict(schema=1,profiles={})),
        CONFIGS[1]:canonical(dict(schema=1,presets={})),CONFIGS[2]:canonical(dict(schema=1,presets={})),
        '.pbz-base.json':canonical(dict(schema=1,proposal=None)),
        'Config/DefaultEngine.ini':b'[/Script/EngineSettings.GameMapsSettings]\nGameDefaultMap=/Engine/Maps/Entry\nEditorStartupMap=/Engine/Maps/Entry\n',
        'COLLABORATION.md':('''# PBZ shared authoring workspace

Edit assets under Content/PBZCreative and shared data under Config/PBZCreative.
Submit saved files through the same Boss workbench. Unsaved editor changes are
not included. Integration checks conflicts and feeds the next developer build;
it does not hot-install assets or modify a running game. New visual assets still
need cooking, mount/load compatibility and runtime checks.
''').encode('utf-8')}
    for name,raw in initial.items():
        path=plain(workspace/name);path.parent.mkdir(parents=True,exist_ok=True)
        if not path.exists():
            try:
                with path.open('xb') as f:f.write(raw)
            except FileExistsError:pass
    (workspace/'Content/PBZCreative').mkdir(parents=True,exist_ok=True)
    return workspace/'PBZCreative.uproject'


def scan(workspace):
    workspace=plain(workspace);found={};total=0
    for folder in ('Content/PBZCreative','Config/PBZCreative'):
        start=plain(workspace/folder)
        if folder=='Content/PBZCreative' and not start.exists():continue
        assert start.is_dir(),'initialize the creative workspace first'
        for directory,dirs,names in os.walk(start,followlinks=False):
            for name in dirs:plain(Path(directory)/name)
            for name in names:
                source=plain(Path(directory)/name);rel=source.relative_to(workspace).as_posix();relative(rel)
                assert rel.casefold() not in {x.casefold() for x in found},'case-colliding creative paths'
                size=source.stat().st_size;total+=size;found[rel]=source
                assert len(found)<=MAX_FILES and total<=MAX_BYTES,'proposal exceeds 512 files / 512 MiB'
    assert set(CONFIGS)<=set(found),'shared configuration files are required'
    return found


def checked_snapshot(kind,key,storage=PROJECT_STORAGE):
    assert kind in ('proposal','integration') and re.fullmatch('[a-f0-9]{24}',key),'invalid snapshot identity'
    p=paths(storage);directory=plain(p['proposals' if kind=='proposal' else 'integrations']/key)
    manifest=read(plain(directory/'manifest.json'))
    assert type(manifest['schema']) is int and manifest['schema']==1 and manifest['kind']==kind and digest(canonical(manifest))[:24]==key
    assert isinstance(manifest['files'],dict) and len(manifest['files'])<=MAX_FILES
    stored={}
    for folder,dirs,names in os.walk(plain(directory/'files'),followlinks=False):
        for name in dirs:plain(Path(folder)/name)
        for name in names:
            path=plain(Path(folder)/name);rel=path.relative_to(directory/'files').as_posix();relative(rel)
            assert rel.casefold() not in stored,'case-colliding creative paths'
            stored[rel.casefold()]=rel
    assert set(stored.values())==set(manifest['files']),'snapshot file set changed'
    total=0
    for name,row in manifest['files'].items():
        relative(name);path=plain(directory/'files'/name)
        assert isinstance(row,dict) and set(row)=={'bytes','sha256'}
        assert type(row['bytes']) is int and row['bytes']>=0 and re.fullmatch('[a-f0-9]{64}',row['sha256'])
        assert path.is_file() and path.stat().st_size==row['bytes']
        total+=row['bytes'];assert total<=MAX_BYTES
        assert file_digest(path)==row['sha256'],'snapshot content changed: '+name
        if name in CONFIGS:validate_config(name,read(path))
    assert set(CONFIGS)<=set(manifest['files'])
    return directory,manifest


def active(storage=PROJECT_STORAGE):
    p=paths(storage)
    if not p['active'].exists():return None,None,None
    pointer=read(plain(p['active']));assert set(pointer)=={'schema','integration'} and pointer['schema']==1
    directory,manifest=checked_snapshot('integration',pointer['integration'],storage)
    return pointer['integration'],directory,manifest


def freeze(kind,files,metadata,storage=PROJECT_STORAGE,before_publish=None):
    assert kind in ('proposal','integration')
    p=paths(storage);parent=plain(p['proposals' if kind=='proposal' else 'integrations']);parent.mkdir(parents=True,exist_ok=True)
    staging=parent/('.pending-'+uuid.uuid4().hex);staging.mkdir()
    try:
        rows={};total=0
        for name,source in sorted(files.items()):
            relative(name);target=plain(staging/'files'/name);target.parent.mkdir(parents=True,exist_ok=True)
            size=len(source) if isinstance(source,bytes) else plain(source).stat().st_size
            total+=size;assert len(rows)<MAX_FILES and total<=MAX_BYTES,'proposal size bound exceeded'
            if isinstance(source,bytes):target.write_bytes(source)
            else:
                source=plain(source);before=source.stat()
                with source.open('rb') as src,target.open('xb') as dest:shutil.copyfileobj(src,dest,1024*1024)
                after=source.stat()
                assert (before.st_ino,before.st_size,before.st_mtime_ns)==(after.st_ino,after.st_size,after.st_mtime_ns), \
                    'editor changed a file during submission; save and submit again'
            assert target.stat().st_size==size,'source size changed during submission'
            rows[name]=dict(bytes=size,sha256=file_digest(target))
            if name in CONFIGS:validate_config(name,read(target))
        assert set(CONFIGS)<=set(rows),'shared configurations are required'
        assert len({name.casefold() for name in rows})==len(rows),'case-colliding creative paths'
        if before_publish:before_publish(rows)
        manifest=dict(schema=1,kind=kind,files=rows,**metadata)
        key=digest(canonical(manifest))[:24];target=parent/key
        (staging/'manifest.json').write_bytes(canonical(manifest))
        if not target.exists():os.rename(staging,target)
        else:
            _,existing=checked_snapshot(kind,key,storage);assert existing==manifest
        checked_snapshot(kind,key,storage)
        return key
    finally:
        if staging.exists():
            assert plain(staging).parent==parent and staging.name.startswith('.pending-')
            shutil.rmtree(staging)


def submit(storage=PROJECT_STORAGE,lane='ue'):
    p=paths(storage,lane);workspace=plain(p['workspace']);base=read(plain(workspace/'.pbz-base.json'))
    assert set(base)=={'schema','proposal'} and base['schema']==1
    if base['proposal']:checked_snapshot('proposal',base['proposal'],storage)
    files=scan(workspace)
    def unchanged(rows):
        assert read(workspace/'.pbz-base.json')==base,'integration advanced while submitting; retry'
        saved=scan(workspace)
        assert set(rows)==set(saved),'editor changed the saved file set during submission'
        for name,source in saved.items():
            assert source.stat().st_size==rows[name]['bytes'] and file_digest(source)==rows[name]['sha256'], \
                'editor changed saved content during submission; save and submit again: '+name
    return freeze('proposal',files,dict(base=base['proposal'],origin='creative_authoring',lane=lane),storage,before_publish=unchanged)


def three_way(base,incoming,current,path='',resolutions=None):
    if incoming==base:return current,[]
    if current==base or current==incoming:return incoming,[]
    if all(isinstance(v,dict) or v is MISSING for v in (base,incoming,current)):
        b={} if base is MISSING else base;i={} if incoming is MISSING else incoming;c={} if current is MISSING else current
        # Whole-object deletion must conflict with concurrent edits inside it.
        if incoming is MISSING or current is MISSING:
            return resolve_conflict(incoming,current,path,resolutions)
        merged={};conflicts=[]
        for key in sorted(set(b)|set(i)|set(c)):
            token=key.replace('~','~0').replace('/','~1')
            value,issues=three_way(b.get(key,MISSING),i.get(key,MISSING),c.get(key,MISSING),path+'/'+token,resolutions)
            conflicts+=issues
            if value is not MISSING:merged[key]=value
        return merged,conflicts
    return resolve_conflict(incoming,current,path,resolutions)


def resolve_conflict(incoming,current,path,resolutions):
    choice=(resolutions or {}).get(path)
    if choice is None:return current,[path]
    assert choice in ('incoming','current'),'invalid conflict choice'
    return (incoming if choice=='incoming' else current),[]


def merge_plan(key,storage=PROJECT_STORAGE,resolutions=None):
    proposal_dir,proposal=checked_snapshot('proposal',key,storage)
    if proposal['base']:base_dir,base=checked_snapshot('proposal',proposal['base'],storage)
    else:base_dir,base=None,dict(files={})
    current_key,current_dir,current=active(storage)
    current=current or dict(files={})
    result={};conflicts=[]
    for name in sorted(set(base['files'])|set(proposal['files'])|set(current['files'])):
        b=base['files'].get(name,MISSING);i=proposal['files'].get(name,MISSING);c=current['files'].get(name,MISSING)
        if name in CONFIGS:
            values=[read(directory/'files'/name) if row is not MISSING else MISSING
                    for row,directory in ((b,base_dir),(i,proposal_dir),(c,current_dir))]
            value,issues=three_way(*values,path=name,resolutions=resolutions);conflicts+=issues
            if value is not MISSING:result[name]=canonical(validate_config(name,value))
        else:
            # Cooked/source asset bytes are atomic; never merge their metadata fields.
            if i==b:value=c
            elif c==b or c==i:value=i
            else:
                value,issues=resolve_conflict(i,c,name,resolutions);conflicts+=issues
            if value is not MISSING:
                source=proposal_dir if value==i else current_dir
                result[name]=source/'files'/name
    return dict(proposal=key,current=current_key,conflicts=conflicts,files=result)


def integrate(key,storage=PROJECT_STORAGE,*,resolutions=None,expected_current=MISSING):
    with merge_lock(storage):
        _,proposal=checked_snapshot('proposal',key,storage)
        author=paths(storage,proposal['lane'])['workspace']
        current_key,_,current=active(storage)
        if expected_current is not MISSING:
            assert current_key==expected_current,'集成版本已被另一方更新，请重新预览冲突'
        if current and current['proposal']==key:
            atomic(author/'.pbz-base.json',canonical(dict(schema=1,proposal=key)))
            return current_key
        plan=merge_plan(key,storage)
        choices=resolutions or {}
        assert set(choices)<=set(plan['conflicts']),'冲突列表已改变，请重新预览'
        if choices:plan=merge_plan(key,storage,resolutions=choices)
        assert not plan['conflicts'],'合并冲突，保留双方修改：'+'；'.join(plan['conflicts'])
        key_out=freeze('integration',plan['files'],dict(proposal=key,previous=plan['current'],
            conflict_resolutions=choices,runtime_accepted=False,visual_assets_state='editor_source_not_cooked'),storage)
        atomic(paths(storage)['active'],canonical(dict(schema=1,integration=key_out)))
        # Advance only the author's proposal baseline, never overwrite UE assets.
        atomic(author/'.pbz-base.json',canonical(dict(schema=1,proposal=key)))
        return key_out


def tuning(storage=PROJECT_STORAGE):
    key,directory,manifest=active(storage)
    if not key:return {},None
    return validate_config(CONFIGS[0],read(directory/'files'/CONFIGS[0]))['profiles'], \
        dict(integration=key,manifest_sha256=digest(canonical(manifest)),visual_assets_state='editor_source_not_cooked')


def save_profile(role,settings,expected_sha,storage=PROJECT_STORAGE):
    assert role in ROLES
    path=plain(paths(storage)['workspace']/CONFIGS[0])
    with merge_lock(storage):
        raw=path.read_bytes();assert digest(raw)==expected_sha,'3C文件已被其他编辑修改，请刷新后再保存'
        value=validate_config(CONFIGS[0],json.loads(raw))
        if settings==value['profiles'].get(role,{}):
            validate_config(CONFIGS[0],dict(schema=1,profiles={role:settings}))
            return expected_sha
        value['profiles'][role]=settings;validate_config(CONFIGS[0],value)
        assert digest(path.read_bytes())==expected_sha,'3C文件在保存前发生变化，请刷新'
        atomic(path,canonical(value))
    return digest(canonical(value))


def render_tuning(source,storage=PROJECT_STORAGE,selected=None):
    profiles,identity=tuning(storage=storage) if selected is None else selected
    if not profiles:return source,identity
    from build_boss_profile_candidate import lua
    marker='    for key,value in pairs(override or{})do\n'
    assert source.count(marker)==1,'3C tuning source changed; review integration hook'
    insertion=('    local authored='+lua(profiles)+'\n'
        '    local requested={}\n'
        "    for key,value in pairs(authored['*']or{})do requested[key]=value end\n"
        '    for key,value in pairs(authored[id]or{})do requested[key]=value end\n'
        '    for key,value in pairs(override or{})do requested[key]=value end\n'
        '    for key,value in pairs(requested)do\n')
    return source.replace(marker,insertion),identity


def open_editor(storage=PROJECT_STORAGE):
    project=plain(paths(storage)['workspace']/'PBZCreative.uproject');assert project.is_file(),'initialize workspace first'
    engine=Path(r'D:\UE_5.8/Engine/Binaries/Win64/UnrealEditor.exe');assert engine.is_file(),'UE 5.8 editor not found'
    return subprocess.Popen([str(engine),str(project)],cwd=project.parent,
        creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0)).pid


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);sub=parser.add_subparsers(dest='action',required=True)
    for action in ('initialize','submit'):sub.add_parser(action).add_argument('--lane',choices=('ue','backend'),default='ue')
    sub.add_parser('status')
    for action in ('preview','integrate'):sub.add_parser(action).add_argument('proposal')
    args=parser.parse_args()
    if args.action=='initialize':result=dict(project=str(initialize(lane=args.lane)))
    elif args.action=='submit':result=dict(proposal=submit(lane=args.lane))
    elif args.action=='status':result=dict(workspace=str(paths()['workspace']),active=active()[0])
    elif args.action=='preview':
        plan=merge_plan(args.proposal);result={k:v for k,v in plan.items() if k!='files'}
    else:result=dict(integration=integrate(args.proposal))
    print(json.dumps(result,ensure_ascii=False,indent=2))
