import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import patcher


class TranslationTests(unittest.TestCase):
    def test_preserves_executable_structure_and_id(self):
        source = 'f({defaultMessage:"Open {name}",id:"open-id"},x);let model="opus";'
        output, stats, ids = patcher.rewrite(source, {}, {'Open {name}': '打开 {name}'})
        self.assertIn('id:"open-id"', output)
        self.assertTrue(output.endswith(';let model="opus";'))
        self.assertEqual(stats['replacements'], 1)
        self.assertEqual(ids, {'open-id'})

    def test_rejects_missing_variable(self):
        source = 'defaultMessage:"Open {name}",id:"id"'
        output, stats, _ = patcher.rewrite(source, {}, {'Open {name}': '打开'})
        self.assertEqual(output, source)
        self.assertEqual(stats['skipped_invalid'], 1)

    def test_plural_branches_and_nested_arguments(self):
        source = '{n, plural, one {File {name}} other {# files from {name}}}'
        target = '{n, plural, one {文件 {name}} other {来自 {name} 的 # 个文件}}'
        self.assertTrue(patcher.compatible(source, target))
        self.assertFalse(patcher.compatible(source, '{n, plural, other {# 个文件}}'))

    def test_missing_other_or_unclosed_brace_rejected(self):
        for value in ('{n, plural, one {x}}', 'Hi {name', 'Hi }'):
            with self.assertRaises(ValueError):
                patcher.message_signature(value)

    def test_rich_tags_and_variable_types(self):
        self.assertTrue(patcher.compatible('<link>Read {name}</link>', '<link>阅读 {name}</link>'))
        self.assertFalse(patcher.compatible('<link>Read</link>', '阅读'))
        self.assertFalse(patcher.compatible('{n, number}', '{n}'))

    def test_icu_apostrophe_escaping(self):
        self.assertTrue(patcher.compatible("Show '{literal}' and {value}", "显示 '{literal}' 和 {value}"))
        self.assertTrue(patcher.compatible("Don't remove {name}", '不要移除 {name}'))

    def test_json_escaping_prevents_code_injection(self):
        target = '中文";throw new Error("test");//'
        output, _, _ = patcher.rewrite('defaultMessage:"Hello",id:"id"', {}, {'Hello': target})
        match = patcher.MESSAGES.fullmatch(output)
        self.assertIsNotNone(match)
        self.assertEqual(json.loads(match['text']), target)

    def test_repeat_application_does_not_change_chinese(self):
        source = 'defaultMessage:"Archive",id:"id"'
        translated, _, _ = patcher.rewrite(source, {}, {'Archive': '归档'})
        again, stats, _ = patcher.rewrite(translated, {}, {'Archive': '归档'})
        self.assertEqual(again, translated)
        self.assertEqual(stats['replacements'], 0)

    def test_unknown_text_unchanged(self):
        source = 'defaultMessage:"Unknown",id:"id";const endpoint="https://example.invalid";'
        self.assertEqual(patcher.rewrite(source, {}, {})[0], source)

    def test_all_shipped_translations_preserve_icu(self):
        for source, target in patcher.read_json(patcher.ROOT / 'resources/supplemental-zh-CN.json').items():
            with self.subTest(source=source):
                self.assertTrue(patcher.compatible(source, target))

    def test_reported_home_and_settings_labels(self):
        translations = patcher.read_json(patcher.ROOT / 'resources/supplemental-zh-CN.json')
        cases = [
            ('Customize Cowork for me', '6vxCyHtxqT', '为我定制 Cowork'),
            ('General', 'f0sgug52cn', '通用'),
            ('Cowork', '+MH0VdRCHz', '协作（Cowork）'),
        ]
        for english, key, expected in cases:
            with self.subTest(label=english):
                source = 'defaultMessage:' + json.dumps(english) + ',id:' + json.dumps(key)
                output, stats, ids = patcher.rewrite(source, {}, translations)
                self.assertEqual(json.loads(patcher.MESSAGES.fullmatch(output)['text']), expected)
                self.assertEqual(stats['replacements'], 1)
                self.assertEqual(ids, {key})


class TransactionTests(unittest.TestCase):
    def test_failed_install_restores_original(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            app, stage, backup = root / 'app', root / 'stage', root / 'backup'
            app.mkdir()
            stage.mkdir()
            (app / 'original').write_text('original')
            rename = Path.rename

            def fail_stage(path, target):
                if path == stage:
                    raise OSError('Simulated replacement failure')
                return rename(path, target)

            with patch.object(Path, 'rename', fail_stage):
                with self.assertRaises(OSError):
                    patcher.swap(app, stage, backup)
            self.assertEqual((app / 'original').read_text(), 'original')
            self.assertFalse(backup.exists())

    def test_existing_backup_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('app', 'stage', 'backup'):
                (root / name).mkdir()
            with self.assertRaises(RuntimeError):
                patcher.swap(root / 'app', root / 'stage', root / 'backup')
            self.assertTrue((root / 'app').exists())


if __name__ == '__main__':
    unittest.main()
