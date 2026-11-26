import json
import unittest

from local_service import Problem
from program.schedule import build_schedule
from scripts.revisions import ApprovedRevision
from tests.support import House, V1, V2, aired, cue, lanes


class ProgramTests(unittest.TestCase):
    def setUp(self):
        self.house = House(self)

    def test_rehearsal_times(self):
        house = self.house
        manifest = house.rehearse(house.prepare(), start=100)
        actual = [[item['language'], item['at']] for item in manifest['outputs']]
        self.assertEqual([['zh', 110], ['en', 112]], actual)
        self.assertEqual('received', house.preload()['status'])
        self.assertEqual([], house.advance(109)['records'])
        house.advance(110)
        house.advance(112)
        downstream = [[row['language'], row['aired_at']] for row in house.read()['records']]
        self.assertEqual([['zh', 110], ['en', 112]], downstream)
        print('POINTWISE_SCENARIO ' + json.dumps({
            'case_id': 'v1', 'input': {'start': 100, 'cue_second': 10, 'offsets': {'zh': 0, 'en': 2}},
            'expected': [['zh', 110], ['en', 112]], 'actual': actual,
            'downstream_expected': [['zh', 110], ['en', 112]], 'downstream_actual': downstream,
            'code_paths': ['program/schedule.py', 'program/rehearsal.py', 'editorial/preload.py',
                           'projection/output.py', 'airlog/queries.py'],
            'oracle': '100 + 10 + 0 = 110，100 + 10 + 2 = 112。用相同两秒推进并独立核对实播。',
        }, ensure_ascii=False))

    def test_approved_snapshot(self):
        house = self.house
        revision = house.prepare()
        self.assertEqual('V1', revision)
        house.draft([cue(second=14, texts=V2)])
        original = house.edit(200, 'GET', '/revision?revision=V1')
        self.assertEqual([cue()], original['cues'])
        for show, start in (('S', 100), ('T', 200)):
            with self.subTest(show=show):
                manifest = house.rehearse(revision, show=show, start=start)
                self.assertEqual([(start + 10, V1[0]), (start + 12, V1[1])],
                                 [(row['at'], row['text']) for row in manifest['outputs']])
                house.preload(show)
                house.advance(start + 10, show)
                house.advance(start + 12, show)
                self.assertEqual([('zh', start + 10, 'V1', V1[0]), ('en', start + 12, 'V1', V1[1])],
                                 aired(house.read(show)['records']))

    def test_invalid_draft_and_unapproved_revision(self):
        house = self.house
        invalid = cue()
        del invalid['en']
        self.assertEqual('invalid_fields', house.draft([invalid], expected=400)['error'])
        self.assertEqual('unknown_draft', house.edit(404, 'POST', '/approve', {'script_id': 'weekend'})['error'])
        house.draft([cue()])
        self.assertEqual('unapproved_revision', house.rehearse('V1', expected=404)['error'])
        self.assertEqual('no_formal_manifest', house.preload(expected=404)['error'])

    def test_bad_inputs_leave_no_new_manifest(self):
        house = self.house
        revision = house.prepare()
        self.assertEqual('duplicate_cue', house.draft([cue(), cue(second=14)], expected=400)['error'])
        self.assertEqual([cue()], house.edit(200, 'GET', '/draft?script_id=weekend')['cues'])
        house.draft([])
        self.assertEqual('empty_draft', house.edit(400, 'POST', '/approve', {'script_id': 'weekend'})['error'])
        with self.assertRaises(Problem) as caught:
            build_schedule(ApprovedRevision('V2', 'weekend', ()), 0, lanes())
        self.assertEqual('empty_manifest', caught.exception.payload['error'])
        self.assertEqual('unapproved_revision', house.rehearse('V2', expected=404)['error'])
        self.assertEqual('negative_output_time', house.rehearse(revision, setup=lanes(zh=-11), expected=400)['error'])
        self.assertEqual('invalid_integer', house.rehearse(revision, start=True, expected=400)['error'])
        self.assertEqual('no_formal_manifest', house.edit(404, 'GET', '/rehearse?show_id=S')['error'])
        self.assertEqual('no_formal_manifest', house.preload(expected=404)['error'])

    def test_screen_overlap_and_adjacent_windows(self):
        house = self.house
        setup = lanes(0, 20, same_screen=True)
        overlap = house.prepare([cue('A', 10), cue('B', 11)])
        result = house.rehearse(overlap, setup=setup, expected=409)
        self.assertEqual('screen_conflict', result['error'])
        self.assertEqual({'screen': 'left', 'outputs': [
            {'cue_id': 'A', 'language': 'zh', 'window': [10, 12]},
            {'cue_id': 'B', 'language': 'zh', 'window': [11, 13]},
        ]}, result['conflicts'][0])
        house.preload(expected=404)
        adjacent = house.prepare([cue('A', 10), cue('B', 12)])
        formal = house.rehearse(adjacent, setup=setup)
        self.assertEqual([10, 12, 30, 32], [row['at'] for row in formal['outputs']])
        house.rehearse(overlap, setup=setup, expected=409)
        self.assertEqual(formal, house.edit(200, 'GET', '/rehearse?show_id=S'))
        self.assertEqual('received', house.preload()['status'])

    def test_separate_screens_can_overlap(self):
        house = self.house
        formal = house.rehearse(house.prepare(), setup=lanes(0, 0))
        self.assertEqual([('zh', 'left', 10), ('en', 'right', 10)],
                         [(row['language'], row['screen'], row['at']) for row in formal['outputs']])
        house.preload()
        self.assertEqual([('zh', 10, 'V1', V1[0]), ('en', 10, 'V1', V1[1])],
                         aired(house.advance(10)['records']))
