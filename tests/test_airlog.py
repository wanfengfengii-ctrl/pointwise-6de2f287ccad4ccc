import unittest

from tests.support import House, V1, aired, cue


class AirlogTests(unittest.TestCase):
    def test_catch_up_keeps_formal_order_and_records_actual_second(self):
        house = House(self)
        house.rehearse(house.prepare([cue('B', 14), cue('A', 10)]))
        house.preload()
        result = house.advance(17)['records']
        self.assertEqual([('A', 'zh'), ('A', 'en'), ('B', 'zh'), ('B', 'en')],
                         [(row['cue_id'], row['language']) for row in result])
        self.assertEqual([('zh', 17, 'V1', V1[0]), ('en', 17, 'V1', V1[1])] * 2, aired(result))
        self.assertEqual(result, house.read()['records'])
        self.assertEqual([], house.advance(18)['records'])

    def test_closeout_lists_cues_without_any_output(self):
        house = House(self)
        house.rehearse(house.prepare([cue('C', 10), cue('D', 20)]))
        house.preload()
        house.advance(12)
        result = house.read()
        self.assertEqual(2, len(result['records']))
        self.assertEqual([('C', [], True), ('D', ['zh', 'en'], False)],
                         [(entry['cue_id'], entry['missing'], entry['complete']) for entry in result['cues']])
        self.assertFalse(result['complete'])
