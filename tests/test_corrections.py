import unittest
from concurrent.futures import ThreadPoolExecutor

from tests.support import House, ReplyGate, V1, V2, aired, lanes


class CorrectionTests(unittest.TestCase):
    def test_replace_both_preloaded_languages(self):
        house = House(self)
        house.ready()
        self.assertEqual([], house.advance(9)['records'])
        receipt = house.correction()
        self.assertEqual({'correction_id': 'Q', 'show_id': 'S', 'cue_id': 'C',
                          'status': 'accepted', 'version': 'V2'}, receipt)
        self.assertEqual(receipt, house.verdict())
        self.assertEqual([('zh', 10, 'V2', V2[0])], aired(house.advance(10)['records']))
        self.assertEqual([('en', 12, 'V2', V2[1])], aired(house.advance(12)['records']))
        self.assertEqual([('zh', 10, 'V2', V2[0]), ('en', 12, 'V2', V2[1])], aired(house.read()['records']))

    def test_reject_after_first_display(self):
        house = House(self)
        house.ready()
        house.advance(10)
        house.second = 11
        receipt = house.correction(expected=409)
        self.assertEqual(('already_shown', 'V1'), (receipt['status'], receipt['version']))
        self.assertEqual(receipt, house.verdict(expected=409))
        house.advance(12)
        self.assertEqual([('zh', 10, 'V1', V1[0]), ('en', 12, 'V1', V1[1])], aired(house.read()['records']))

    def test_delayed_first_display_report(self):
        house = House(self)
        house.ready()
        actual = house.advance(10)['records']
        self.assertEqual([('zh', 10, 'V1', V1[0])], aired(actual))
        self.assertEqual(actual, house.read(cue_id='C')['records'])
        gate = ReplyGate()
        house.hold['GET', '/readback'] = gate
        with ThreadPoolExecutor(max_workers=1) as executor:
            report = executor.submit(house.edit, 200, 'GET', '/readback?show_id=S&cue_id=C')
            try:
                self.assertTrue(gate.held.wait(3))
                self.assertFalse(report.done())
                house.second = 11
                receipt = house.correction(expected=409)
                self.assertEqual('already_shown', receipt['status'])
                self.assertFalse(report.done())
            finally:
                gate.release.set()
            self.assertEqual(actual, report.result(timeout=3)['records'])
        self.assertEqual([('en', 12, 'V1', V1[1])], aired(house.advance(12)['records']))
        self.assertEqual(receipt, house.verdict(expected=409))

    def test_english_first(self):
        house = House(self)
        house.ready(setup=lanes(2, 0))
        self.assertEqual([('en', 10, 'V1', V1[1])], aired(house.advance(10)['records']))
        house.second = 11
        self.assertEqual('already_shown', house.correction(expected=409)['status'])
        self.assertEqual([('zh', 12, 'V1', V1[0])], aired(house.advance(12)['records']))
        self.assertEqual([('en', 10, 'V1', V1[1]), ('zh', 12, 'V1', V1[0])], aired(house.read()['records']))

    def test_same_second_commit_order(self):
        for correction_first in (True, False):
            with self.subTest(correction_first=correction_first):
                house = House(self)
                house.ready()
                house.second = 10
                if correction_first:
                    self.assertEqual('accepted', house.correction()['status'])
                    house.advance(10)
                    version, texts = 'V2', V2
                else:
                    house.advance(10)
                    self.assertEqual('already_shown', house.correction(expected=409)['status'])
                    version, texts = 'V1', V1
                house.advance(12)
                self.assertEqual([('zh', 10, version, texts[0]), ('en', 12, version, texts[1])],
                                 aired(house.read()['records']))

    def test_lost_answer_recovers_by_original_id(self):
        house = House(self)
        house.ready()
        house.second = 9
        house.lose.add(('POST', '/decision'))
        self.assertEqual('pending', house.correction(expected=202)['status'])
        house.restart_desk()
        result = house.verdict()
        self.assertEqual(('accepted', 'V2'), (result['status'], result['version']))
        self.assertEqual(result, house.correction())
        self.assertEqual('correction_parameter_mismatch', house.correction(texts=V1, expected=409)['error'])
        house.advance(10)
        house.advance(12)
        self.assertEqual([('zh', 10, 'V2', V2[0]), ('en', 12, 'V2', V2[1])], aired(house.read(cue_id='C')['records']))

    def test_late_recovery_after_first_display_and_restart(self):
        house = House(self)
        house.ready()
        house.second = 9
        house.lose.add(('POST', '/decision'))
        pending = house.correction(expected=202)
        self.assertEqual('pending', pending['status'])
        self.assertEqual([('zh', 10, 'V2', V2[0])], aired(house.advance(10)['records']))
        house.restart_desk()
        house.restart_screen()
        result = house.verdict()
        self.assertEqual({'correction_id': 'Q', 'show_id': 'S', 'cue_id': 'C',
                          'status': 'accepted', 'version': 'V2'}, result)
        self.assertEqual(result, house.correction())
        self.assertEqual('correction_parameter_mismatch', house.correction(texts=V1, expected=409)['error'])
        house.advance(12)
        house.restart_screen()
        self.assertEqual([], house.advance(12)['records'])
        self.assertEqual([('zh', 10, 'V2', V2[0]), ('en', 12, 'V2', V2[1])], aired(house.read(cue_id='C')['records']))
        self.assertEqual(result, house.verdict())
