"""Build/publish only explicit allowlists. Never recursively export the local project."""
import argparse
import json
from pathlib import Path
import shutil
from app.public_digest.pipeline import rebuild_index
from app.public_digest.rights import publishable

ROOT=Path(__file__).resolve().parents[2]
CODE=[
 'app/__init__.py','app/briefing/__init__.py','app/briefing/model.py','app/briefing/collect.py',
 'app/public_digest/rights.py','app/public_digest/adapters.py','app/public_digest/__init__.py','app/public_digest/pipeline.py','app/public_digest/package.py',
 'config/public_sources.json','static_pages/index.html','static_pages/style.css','static_pages/app.js',
 'tests/public/__init__.py','tests/public/test_public.py','tests/public/view.test.cjs']


def public_paths(root):
 return [p for p in sorted((root/'data/reports').glob('*.json')) if publishable(json.loads(p.read_text()))]


def no_links(path):
 if Path(path).is_symlink():raise ValueError('symlink not permitted')


def build_site(root,destination):
 root=Path(root);destination=Path(destination)
 if destination.resolve()==root.resolve():raise ValueError('site destination must be separate')
 if destination.exists() and any(destination.iterdir()):raise ValueError('site destination must be empty to prevent stale content')
 destination.mkdir(parents=True,exist_ok=True)
 rebuild_index(root)
 public_json=[root/'data/index.json',root/'data/status.json',*public_paths(root)]
 if sum(p.stat().st_size for p in public_json if p.exists())>64*1024*1024:
  raise ValueError('Public artifact budget exceeded; stop rather than incur extra storage')
 for name in ('index.html','style.css','app.js'):
  no_links(root/'static_pages'/name)
  shutil.copyfile(root/'static_pages'/name,destination/name)
 for path in [root/'data/index.json',root/'data/status.json',*public_paths(root)]:
  if path.exists():
   no_links(path)
   target=destination/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True)
   shutil.copyfile(path,target)
 (destination/'.nojekyll').touch()
 return destination


def export_public(destination,root=ROOT):
 root=Path(root);destination=Path(destination)
 if destination.exists():raise FileExistsError('Export target must not exist')
 destination.mkdir(parents=True)
 for name in CODE:
  source=root/name;no_links(source)
  target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
 # Validate every archive before it is part of the reviewable public export.
 rebuild_index(root)
 for path in [root/'data/index.json',root/'data/status.json',*public_paths(root)]:
  if path.exists():
   no_links(path)
   target=destination/path.relative_to(root);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,target)
 for source,target in [('deploy/pages/daily.yml.example','.github/workflows/daily.yml'),
                       ('deploy/pages/PUBLIC_README.md','README.md'),('deploy/pages/gitignore.example','.gitignore')]:
  target=destination/target;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(root/source,target)
 # Only this selected directory is eligible for later user-approved upload.
 return destination

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('command',choices=['build','export']);p.add_argument('destination');p.add_argument('--root',default=str(ROOT))
 a=p.parse_args()
 print(build_site(a.root,a.destination) if a.command=='build' else export_public(a.destination,a.root))
