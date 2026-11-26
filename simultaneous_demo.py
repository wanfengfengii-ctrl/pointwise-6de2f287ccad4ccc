import json
import unittest

from tests.support import House, V2, lanes


class CoDisplayScenarios(unittest.TestCase):
    def setUp(self):
        self.house = House(self)
        self.revision = self.house.prepare()

    def rehearse(self, *, zh=None, en=None, en_offset=2, expected=200):
        return self.house.edit(expected, 'POST', '/rehearse', {
            'show_id': 'S', 'revision': self.revision, 'start': 0,
            'lanes': lanes(en=en_offset),
            'co_display': {
                'windows': {'zh': [[0, 1]] if zh is None else zh,
                            'en': [[0, 1]] if en is None else en},
                'min_seconds': 1,
            },
        })

    def preload(self):
        receipt = self.house.preload()
        self.assertEqual('received', receipt['status'])
        return receipt

    @staticmethod
    def starts(response):
        return sorted((row['language'], row['aired_at']) for row in response['records'])

    def tick(self, second, status, emitted=()):
        response = self.house.advance(second)
        self.assertEqual(status, response['co_display_status'])
        self.assertEqual(sorted(emitted), self.starts(response))
        return response

    def read(self, status, zh, en, overlap):
        response = self.house.read(cue_id='C')
        actual = response['co_display']
        self.assertEqual(status, actual['status'])
        self.assertEqual({'zh': zh, 'en': en}, actual['starts'])
        self.assertEqual(overlap, actual['overlap_seconds'])
        self.assertEqual(status == 'satisfied', response['complete'])
        missing = [language for language, second in (('zh', zh), ('en', en)) if second is None]
        self.assertEqual(missing, response['cues'][0]['missing'])
        return response

    def report(self, result):
        print(json.dumps({'scenario': self._testMethodName, 'readback': result}, ensure_ascii=False))

    def test_required_staggered_start(self):
        manifest = self.rehearse()
        self.rehearse(zh=[[0, 0]], expected=409)
        self.assertEqual(manifest, self.house.edit(200, 'GET', '/rehearse?show_id=S'))
        receipt = self.preload()
        self.rehearse(en=[[0, 0]], expected=409)
        self.assertEqual(receipt, self.preload())
        self.tick(10, 'waiting')
        correction = self.house.correction(correction_id='before')
        self.assertEqual('accepted', correction['status'])
        self.tick(11, 'waiting', [('zh', 11)])
        late = self.house.correction(correction_id='after', expected=409)
        self.assertEqual('already_shown', late['status'])
        self.tick(12, 'satisfied', [('en', 12)])
        result = self.read('satisfied', 11, 12, 1)
        self.assertEqual(list(V2), [row['text'] for row in result['records']])
        self.assertEqual({correction['version']}, {row['version'] for row in result['records']})
        self.report(result)

    def test_late_second_lane(self):
        self.rehearse()
        self.preload()
        self.house.desk_run.close()
        self.tick(11, 'waiting', [('zh', 11)])
        self.house.restart_screen()
        self.house.second = 13
        before = self.read('waiting', 11, None, 0)
        self.tick(13, 'missed')
        result = self.read('missed', 11, None, 0)
        self.assertEqual(before['records'], result['records'])
        self.house.restart_screen()
        self.tick(13, 'missed')
        self.tick(14, 'missed')
        self.assertEqual(result, self.read('missed', 11, None, 0))
        self.report(result)

    def test_english_starts_first(self):
        self.rehearse(zh=[[0, 0], [3, 3]], en_offset=1)
        self.preload()
        self.house.desk_run.close()
        self.tick(12, 'waiting', [('en', 12)])
        self.tick(13, 'satisfied', [('zh', 13)])
        self.report(self.read('satisfied', 13, 12, 1))

    def test_optional_early_start(self):
        self.rehearse(zh=[[0, 0], [4, 4]], en=[[0, 0], [3, 3]], en_offset=1)
        self.preload()
        first = self.house.advance(10)
        self.assertEqual('waiting', first['co_display_status'])
        emitted = self.starts(first)
        self.assertIn(emitted, ([], [('zh', 10)]))
        correction = self.house.correction(expected=409 if emitted else 200)
        if emitted:
            self.assertEqual('already_shown', correction['status'])
            self.tick(14, 'missed')
            self.report(self.read('missed', 10, None, 0))
        else:
            self.assertEqual('accepted', correction['status'])
            self.tick(14, 'satisfied', [('zh', 14), ('en', 14)])
            result = self.read('satisfied', 14, 14, 2)
            self.assertEqual({correction['version']}, {row['version'] for row in result['records']})
            self.report(result)


if __name__ == '__main__':
    unittest.main(verbosity=2)
