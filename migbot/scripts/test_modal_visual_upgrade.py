"""Reopen an actual e057f48-produced synthetic G0 PASS after tool installation/upgrade."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'fixtures/modal-visual/e057f48-g0-pass.json'
INSTALLER = ROOT / 'migbot/scripts/migbot-install.py'


class ModalVisualUpgradeTests(unittest.TestCase):
    def test_pinned_online_g0_pass_resummarizes_after_upgrade_without_rewriting_archive(self):
        frozen = json.loads(FIXTURE.read_text(encoding='utf-8'))
        self.assertEqual(frozen['producer_commit'], 'e057f483540fd98d36d1541bbfecb00a36b6b4e3')
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary).resolve()
            for name, row in frozen['files'].items():
                raw = row['utf8'].encode() if 'utf8' in row else base64.b64decode(row['base64'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'], name)
                path = project/name
                self.assertTrue(path.resolve().is_relative_to(project))
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(raw)
            # Preserve a real existing project config, app/Spec files and immutable old receipts.
            config = project/'.migbot/config.json';config.parent.mkdir(exist_ok=True)
            config.write_text(json.dumps({'version':'1.0.0','ios':'../source','app_name':'Synthetic legacy app',
                                          'confirmed':True,'custom_setting':'keep-exactly'}))
            config_bytes=config.read_bytes()
            before={name:(project/name).read_bytes() for name in frozen['files']}
            installed=subprocess.run([sys.executable,'-B',str(INSTALLER),'--project',str(project)],
                                     cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(installed.returncode,0,installed.stdout+installed.stderr)
            self.assertEqual(config.read_bytes(),config_bytes)
            code='''
from pathlib import Path
import sys,json
p=Path.cwd();sys.path.insert(0,str(p/'.claude/skills/i2h-execute/scripts'))
from lib.ios_ui_dispatch import aggregate_g0
from lib.ios_stage1_acceptance import archive_g1
r=aggregate_g0(p);assert r['status']=='PASS' and r['required_units']==1,r
assert r['result_scope']=='ORIGINAL_G0' and r['stage1_complete'] is False
v=archive_g1(p);assert v['status']=='PASS' and v['current_g0_units']==1,v
print(json.dumps({'g0':r['status'],'g1':v['status'],'first_dispatch':v['g0_receipts'][0]['first_dispatch_id']}))
'''
            checked=subprocess.run([sys.executable,'-B','-c',code],cwd=project,capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)
            self.assertEqual(json.loads(checked.stdout)['first_dispatch'],'home.attempt-1')
            for name,raw in before.items():self.assertEqual((project/name).read_bytes(),raw,name)
            self.assertEqual(config.read_bytes(),config_bytes)
            self.assertFalse((project/'.claude/skills/i2h-verify/scripts/uitest_scenario.py').exists())
            # Packaging the new shared observer must not drop current online agents or policy.
            self.assertTrue((project/'.claude/agents/i2h-diagnostic-expert.md').exists())
            self.assertTrue((project/'.migbot/runtime/scripts/run_claude_task.py').exists())

    def test_installed_shared_observer_is_required_and_background_modal_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary).resolve()
            result=subprocess.run([sys.executable,'-B',str(INSTALLER),'--project',str(project)],
                                  cwd=ROOT,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            code='''
import sys
from pathlib import Path
p=Path.cwd();sys.path.insert(0,str(p/'.claude/skills/i2h-verify/scripts'))
from uitest_action import native
n=lambda **a:{'attributes':{'visible':True,**a},'children':[]}
w=n(bundleName='test.app',pagePath='pages/Root',focused=True)
s=n(type='SheetPage');s['children']=[n(id='editor')];w['children']=[n(id='base'),s]
t={'children':[w]};pred={'bundle':'test.app','page_path':'pages/Root','present':[{'id':'editor'}],'absent':[]}
assert native.observe_state(t,pred)['matched'][0]['id']=='editor'
pred['present']=[{'id':'base'}]
try:native.observe_state(t,pred)
except ValueError:pass
else:raise AssertionError('background control satisfied strict formal state')
'''
            checked=subprocess.run([sys.executable,'-B','-c',code],cwd=project,capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stdout+checked.stderr)


if __name__ == '__main__': unittest.main()
