from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from plan_input_view import FEATURES, UI, build_view, markdown


class PlanInputViewTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        (self.project / 'spec/baseline').mkdir(parents=True)
        (self.project / UI).write_text(
            '# UI\n\n## 1. 全局约定\npriority\n'
            '## 2. SwiftUI Views 清单\npage_0001_RootView\n'
            '```markdown\n## 假标题\n```\n## 3. UIKit ViewControllers 清单\n'
            '## 4. 页面关系图\n### 导航层次\nRootView -> SheetView\n'
            '## 5. 状态管理总览\nUnrelated prose\n## 8. 共享组件\nshared widget\n',
            encoding='utf-8',
        )
        (self.project / FEATURES).write_text(
            '# 功能索引\n## 2. 业务功能\n### F001: 交易\nfull unrelated feature\n'
            '### F007: 公共组件\nShared list\n### F009: 共用入口\nShared auth\n'
            '## 9. 技术栈映射总览\nCore API contract\n',
            encoding='utf-8',
        )

    def test_ui_and_slice_keep_page_relationships_and_canonical_ranges(self):
        for role in ('ui', 'slice'):
            view = build_view(self.project, role, [])
            output = markdown(view)
            self.assertIn('page_0001_RootView', output)
            self.assertIn('RootView -> SheetView', output)
            self.assertIn('shared widget', output)
            self.assertNotIn('Unrelated prose', output)
            original = (self.project / UI).read_bytes()
            self.assertEqual(view[0]['sha256'], sha256(original).hexdigest())
            lines = original.decode().splitlines(keepends=True)
            for span in view[0]['excerpts']:
                self.assertEqual(span['text'], ''.join(lines[span['first_line'] - 1:span['last_line']]))

    def test_base_keeps_explicit_shared_feature_without_full_feature_index(self):
        output = markdown(build_view(self.project, 'base', ['F009']))
        for required in ('shared widget', 'Shared list', 'Shared auth', 'Core API contract'):
            self.assertIn(required, output)
        self.assertNotIn('full unrelated feature', output)
        self.assertNotIn('RootView -> SheetView', output)

    def test_legacy_headings_and_missing_explicit_feature_fall_back_to_full_input(self):
        for path, role, selected in ((UI, 'ui', []), (FEATURES, 'base', ['F099'])):
            raw = '# Legacy heading\nEvery obligation must survive.\n'
            (self.project / path).write_text(raw, encoding='utf-8')
            document = next(item for item in build_view(self.project, role, selected) if item['path'] == path)
            self.assertTrue(document['fallback'])
            self.assertEqual(document['excerpts'][0]['text'], raw)
