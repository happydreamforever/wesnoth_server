#!/usr/bin/env python3
"""Verify the private migration package, restore Git metadata and exact game data.
Never initializes a database, downloads software or overwrites a working tree.
Run using the new VPS system Python 3.10+ before installing project Python 3.12.10.
"""
from pathlib import Path,PurePosixPath
import argparse,hashlib,json,os,stat,subprocess,sys,uuid,importlib.util
spec=importlib.util.spec_from_file_location("gamedata_restore",Path(__file__).with_name("restore-game-data.py"))
data_restore=importlib.util.module_from_spec(spec);spec.loader.exec_module(data_restore)
ROOT=Path(__file__).resolve().parents[1]
def sha(path):
 h=hashlib.sha256()
 with path.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def run(*args,cwd=None,capture=False):
 result=subprocess.run(args,cwd=cwd,check=True,stdout=subprocess.PIPE if capture else None)
 return result.stdout if capture else None
def safe(relative):
 p=PurePosixPath(relative)
 if p.is_absolute() or '..' in p.parts or not p.parts:raise ValueError('Unsafe manifest path')
 target=ROOT.joinpath(*p.parts)
 for n in (ROOT,*[ROOT.joinpath(*p.parts[:i]) for i in range(1,len(p.parts)+1)]):
  if n.is_symlink():raise ValueError('Linked migration path is unsupported: '+relative)
 if not target.is_file():raise ValueError('Required file missing: '+relative)
 return target

def verify_manifest():
 manifest=json.loads((ROOT/'migration/MANIFEST.json').read_text())
 records=manifest['files']; seen=set()
 for i,r in enumerate(records,1):
  if r['path'] in seen:raise ValueError('Duplicate manifest entry')
  seen.add(r['path']);p=safe(r['path'])
  if p.stat().st_size!=r['bytes'] or sha(p)!=r['sha256']:raise ValueError('File differs: '+r['path'])
  if i%1000==0:print('Verified package files:',i,flush=True)
 print('PACKAGE FILES VERIFIED:',len(records),flush=True)
 return records

def restore_git(repo_name,info,verify_only):
 repo=ROOT/repo_name; bundle=ROOT/'migration/git'/f'{repo_name}.bundle'
 if not os.path.lexists(repo/'.git'):
  if verify_only:
   raise ValueError(repo_name+': Git metadata missing; run restoration first')
  temp=ROOT/'migration'/('git-restore-'+repo_name+'-'+uuid.uuid4().hex)
  temp.mkdir(mode=0o700)
  run('git','init','--quiet','--initial-branch=__migration_unborn__',str(temp))
  run('git','-C',str(temp),'bundle','verify',str(bundle))
  run('git','-C',str(temp),'fetch','--quiet',str(bundle),'+refs/*:refs/*')
  run('git','-C',str(temp),'symbolic-ref','HEAD','refs/heads/'+info['branch'])
  run('git','-C',str(temp),'config','core.autocrlf','false')
  run('git','-C',str(temp),'config','core.filemode','true')
  run('git','-C',str(temp),'remote','add','origin',info['origin'])
  run('git','-C',str(temp),'config','branch.'+info['branch']+'.remote','origin')
  run('git','-C',str(temp),'config','branch.'+info['branch']+'.merge','refs/heads/'+info['branch'])
  run('git','-C',str(temp),'read-tree','HEAD')
  staged=ROOT/'migration/git'/f'{repo_name}.staged.patch'
  if staged.stat().st_size:run('git','-C',str(temp),'apply','--cached',str(staged))
  # Destination must remain absent; no checkout/reset can replace the supplied source.
  if os.path.lexists(repo/'.git'):raise ValueError('Git destination appeared; retained staging')
  data_restore.publish_without_replacement(temp/'.git',repo/'.git');temp.rmdir()
 if (repo/'.git').is_symlink() or not(repo/'.git').is_dir():raise ValueError('Unsupported Git metadata path')
 expected_refs=(ROOT/'migration/git'/f'{repo_name}.refs.txt').read_text().splitlines()
 actual_refs=run('git','-C',str(repo),'show-ref',capture=True).decode().splitlines()
 if sorted(actual_refs)!=sorted(expected_refs):raise ValueError(repo_name+': refs differ from archived history')
 actual=run('git','-C',str(repo),'rev-parse','HEAD',capture=True).decode().strip()
 if actual!=info['head']:raise ValueError(repo_name+': HEAD differs')
 for label,args in [('unstaged',['diff']),('staged',['diff','--cached'])]:
  diff=run('git','-C',str(repo),*args,'--binary','--full-index','--no-ext-diff','--no-textconv',capture=True)
  if hashlib.sha256(diff).hexdigest()!=info['patch_sha256'][label]:raise ValueError(repo_name+': '+label+' edits differ')
 run('git','-C',str(repo),'fsck','--full','--no-reflogs','--no-dangling','--no-progress')
 print(repo_name+': history, HEAD and exact uncommitted edits verified',flush=True)

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--verify-only',action='store_true',help='No Git/data restoration; verify existing package/data')
 args=parser.parse_args()
 records=verify_manifest()
 if not args.verify_only:
  for r in records:os.chmod(safe(r['path']),r['mode'])
 repos=json.loads((ROOT/'migration/git/repositories.json').read_text())
 for name,info in repos.items():restore_git(name,info,args.verify_only)
 command=[sys.executable,'-I','-B',str(ROOT/'migration/restore-game-data.py'),'--workspace',str(ROOT)]
 if args.verify_only:command.append('--verify-only')
 run(*command)
 print('MIGRATION SOURCE RESTORE VERIFIED',flush=True)
 print('Next: migration/environment/README-ENVIRONMENT.md. Environment/builds are not installed by this helper.')
if __name__=='__main__':
 try:main()
 except (OSError,ValueError,KeyError,subprocess.CalledProcessError) as e:
  print('MIGRATION STOPPED:',str(e),file=sys.stderr);sys.exit(1)
