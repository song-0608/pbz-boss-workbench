"""Seed a visible UE authoring hub using installed Epic template assets."""
import argparse
from contextlib import contextmanager
import json
import os
from pathlib import Path,PurePosixPath
import shutil
import subprocess

import creative_workspace as cw

ENGINE=Path(r'D:\UE_5.8')
MAP='/Game/PBZCreative/Maps/L_PBZCreativeHub'
SOURCE=Path(__file__).with_name('creative_starter_assets.py')
VIEW_SOURCE=Path(__file__).with_name('creative_starter_view.py')
REQUIRED=('Maps/L_PBZCreativeHub.umap','Characters/BP_CreativeCharacter.uasset',
          'Characters/BP_CreativeGameMode.uasset','Effects/NS_CreativeFountain.uasset')


def editor_processes(project):
    command="[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false); Get-CimInstance Win32_Process -Filter \"Name='UnrealEditor.exe'\" | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"
    result=subprocess.run(['powershell.exe','-NoProfile','-Command',command],capture_output=True,
        encoding='utf-8',errors='replace',timeout=15,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    assert result.returncode==0,'could not check existing editor ownership'
    if not result.stdout.strip():return []
    rows=json.loads(result.stdout);rows=rows if isinstance(rows,list) else [rows]
    needle=str(Path(project).resolve()).replace('\\','/').casefold()
    return [row for row in rows if needle in str(row.get('CommandLine','')).replace('\\','/').casefold()]


def state_path(project):return Path(project).parent/'Saved/PBZCreative/starter-complete.json'


def ready(project):
    project=cw.plain(project);report=state_path(project)
    if not report.is_file():return False
    value=cw.read(report)
    return value.get('completed') is True and value.get('map')==MAP and all(
        (project.parent/'Content/PBZCreative'/name).is_file() for name in REQUIRED)


def install_view_helper(project):
    project=cw.plain(project)
    cw.atomic(project.parent/'Saved/PBZCreative/view_starter.py',VIEW_SOURCE.read_bytes())
    init=cw.plain(project.parent/'Content/Python/init_unreal.py')
    marker='# PBZ creative view bootstrap v1\n'
    source=marker+'''import importlib.util
import sys
from pathlib import Path
import unreal
if '-run=' not in unreal.SystemLibrary.get_command_line().lower():
    source=Path(unreal.Paths.project_dir()).resolve()/'Saved/PBZCreative/view_starter.py'
    if source.is_file():
        spec=importlib.util.spec_from_file_location('pbz_creative_view',str(source))
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        module.start()
'''
    if not init.exists() or init.read_text(encoding='utf-8').startswith(marker):cw.atomic(init,source.encode('utf-8'))


@contextmanager
def lease(project):
    path=cw.plain(Path(project).parent/'Saved/PBZCreative/starter.lock');path.parent.mkdir(parents=True,exist_ok=True)
    try:fd=os.open(path,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
    except FileExistsError:raise RuntimeError('另一个工作台正在生成练习场，请等待完成。')
    try:
        with os.fdopen(fd,'wb') as output:output.write(cw.canonical(dict(pid=os.getpid())))
        yield
    finally:path.unlink()


def ini_values(path,section,values,allowed=None):
    """Change only named keys, retaining unrelated settings and custom maps."""
    path=cw.plain(path);lines=path.read_text(encoding='utf-8-sig').splitlines() if path.exists() else []
    header='['+section+']'
    starts=[i for i,line in enumerate(lines) if line.strip()==header]
    assert len(starts)<=1,'duplicate UE config section'
    if starts:start=starts[0]
    else:
        if lines and lines[-1]:lines.append('')
        start=len(lines);lines.append(header)
    end=next((i for i in range(start+1,len(lines)) if lines[i].strip().startswith('[')),len(lines))
    body=lines[start+1:end];result=[];seen=set()
    for line in body:
        key,separator,value=line.partition('=');key=key.strip()
        if separator and key in values:
            assert key not in seen,'duplicate UE config key: '+key
            seen.add(key)
            if allowed is None or value.strip() in allowed|{values[key]}:line=key+'='+values[key]
        result.append(line)
    result.extend(key+'='+value for key,value in values.items() if key not in seen)
    raw=('\n'.join(lines[:start+1]+result+lines[end:])+'\n').encode('utf-8')
    if not path.exists() or path.read_bytes()!=raw:cw.atomic(path,raw)


def template_sources(engine=ENGINE):
    engine=cw.plain(engine);template=engine/'Templates/TP_ThirdPersonBP/Content'
    sources={}
    for source in (template/'ThirdPerson/Blueprints').rglob('*'):
        if source.is_file():sources[source.relative_to(template).as_posix()]=cw.plain(source)
    for name in ('Characters','Input','LevelPrototyping'):
        root=engine/'Templates/TemplateResources/High'/name/'Content'
        assert root.is_dir(),'installed third-person template pack missing: '+name
        for source in root.rglob('*'):
            if source.is_file():
                key=name+'/'+source.relative_to(root).as_posix()
                assert key not in sources,'template source collision'
                sources[key]=cw.plain(source)
    assert 'ThirdPerson/Blueprints/BP_ThirdPersonCharacter.uasset' in sources
    return sources


def prepare(project,engine=ENGINE):
    project=cw.plain(project);assert project.is_file() and project.name=='PBZCreative.uproject'
    assert not editor_processes(project),'请先保存并关闭这个创作工程，再生成练习场；不会强制结束编辑器。'
    value=cw.read(project);plugins=value.setdefault('Plugins',[])
    for name in ('Niagara','EnhancedInput','PythonScriptPlugin','EditorScriptingUtilities','GameplayStateTree'):
        row=next((p for p in plugins if p['Name']==name),None)
        if row is None:plugins.append(dict(Name=name,Enabled=True))
        else:assert row.get('Enabled') is True,'required editor plugin was explicitly disabled: '+name
    cw.atomic(project,cw.canonical(value))
    copied=0;preserved=[];sources=template_sources(engine)
    baseline=project.parent/'Saved/PBZCreative/template-baseline.json'
    previous=cw.read(baseline).get('files',{}) if baseline.exists() else {}
    for name,source in sources.items():
        target=cw.plain(project.parent/'Content'/name)
        if target.exists():
            if cw.file_digest(target)!=cw.file_digest(source):preserved.append(name)
            continue
        target.parent.mkdir(parents=True,exist_ok=True)
        with source.open('rb') as src,target.open('xb') as dest:shutil.copyfileobj(src,dest)
        copied+=1
    # Repair only byte-identical files owned by the previous template receipt.
    hashes={cw.file_digest(source) for source in sources.values()};removed=[]
    for name,old_hash in previous.items():
        relative=PurePosixPath(name)
        assert str(relative)==name and not relative.is_absolute() and not any(p in ('.','..') for p in relative.parts)
        assert '\\' not in name and ':' not in name
        target=cw.plain(project.parent/'Content'/name)
        assert target.is_relative_to((project.parent/'Content').absolute())
        if name not in sources and old_hash in hashes and target.is_file() and cw.file_digest(target)==old_hash:
            target.unlink();removed.append(name)
    ini_values(project.parent/'Config/DefaultInput.ini','/Script/Engine.InputSettings',dict(
        DefaultPlayerInputClass='/Script/EnhancedInput.EnhancedPlayerInput',
        DefaultInputComponentClass='/Script/EnhancedInput.EnhancedInputComponent'))
    output=project.parent/'Saved/PBZCreative'
    output.mkdir(parents=True,exist_ok=True)
    cw.atomic(output/'template-baseline.json',cw.canonical(dict(schema=1,source='installed UE 5.8 ThirdPersonBP and High template packs',
        files={name:cw.file_digest(source) for name,source in sorted(sources.items())},preserved_modified=preserved,
        repaired_old_template_paths=removed)))
    cw.atomic(output/'build_starter.py',SOURCE.read_bytes())
    return dict(copied=copied,preserved_modified=preserved,baseline_files=len(sources))


def ensure(project,engine=ENGINE):
    project=cw.plain(project)
    install_view_helper(project)
    if ready(project):return cw.read(state_path(project))
    with lease(project):
        if ready(project):return cw.read(state_path(project))
        seeded=prepare(project,engine);folder=project.parent/'Saved/PBZCreative'
        executable=cw.plain(Path(engine)/'Engine/Binaries/Win64/UnrealEditor-Cmd.exe')
        assert executable.is_file(),'UE commandlet executable not found'
        command=[str(executable),str(project),'-run=pythonscript','-script='+str(folder/'build_starter.py'),
            '-unattended','-NullRHI','-nosplash','-nosound','-nop4','-UTF8Output']
        with (folder/'starter-build.log').open('wb') as log:
            result=subprocess.run(command,cwd=project.parent,stdout=log,stderr=subprocess.STDOUT,timeout=420,
                creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        assert result.returncode==0 and ready(project),'UE练习场生成未完成，请检查 Saved/PBZCreative/starter-build.log；保留创作文件。'
        ini_values(project.parent/'Config/DefaultEngine.ini','/Script/EngineSettings.GameMapsSettings',dict(
            GameDefaultMap=MAP,EditorStartupMap=MAP),allowed={'/Engine/Maps/Entry','/Engine/Maps/Entry.Entry',''})
        report=cw.read(state_path(project));report['template_seed']=seeded
        cw.atomic(state_path(project),cw.canonical(report))
        return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane',choices=('ue','backend'),default='ue')
    parser.add_argument('--prepare-only',action='store_true')
    args=parser.parse_args();project=cw.initialize(lane=args.lane)
    result=prepare(project) if args.prepare_only else ensure(project)
    print(json.dumps(result,ensure_ascii=False,indent=2))
