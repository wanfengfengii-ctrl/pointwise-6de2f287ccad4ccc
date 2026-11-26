import unittest

from tests.support import House, V1, V2, aired, cue


class ProjectionTests(unittest.TestCase):
    def test_two_outputs_and_missing_lane(self):
        house = House(self)
        house.ready()
        first = house.advance(10)['records']
        self.assertEqual([('zh', 10, 'V1', V1[0])], aired(first))
        partial = house.read(cue_id='C')
        self.assertEqual(first, partial['records'])
        self.assertEqual(['en'], partial['cues'][0]['missing'])
        self.assertFalse(partial['complete'])
        self.assertEqual([], house.advance(11)['records'])
        self.assertEqual([('en', 12, 'V1', V1[1])], aired(house.advance(12)['records']))
        complete = house.read()
        self.assertEqual([('zh', 10, 'V1', V1[0]), ('en', 12, 'V1', V1[1])], aired(complete['records']))
        self.assertEqual([], complete['cues'][0]['missing'])
        self.assertTrue(complete['complete'])
        self.assertEqual([], house.advance(13)['records'])

    def test_before_due(self):
        house = House(self)
        house.ready()
        self.assertEqual([], house.advance(9)['records'])
        partial = house.read()
        self.assertEqual([], partial['records'])
        self.assertEqual(['zh', 'en'], partial['cues'][0]['missing'])
        self.assertFalse(partial['complete'])

    def test_readback_show_scope(self):
        house = House(self)
        house.rehearse(house.prepare(), show='S')
        house.rehearse(house.prepare([cue(texts=V2)]), show='T')
        for show in ('S', 'T'):
            house.preload(show)
        house.advance(10, 'T')
        house.advance(10, 'S')
        house.advance(12, 'S')
        s = house.read('S', 'C')
        t = house.read('T', 'C')
        self.assertEqual([('zh', 10, 'V1', V1[0]), ('en', 12, 'V1', V1[1])], aired(s['records']))
        self.assertEqual([('zh', 10, 'V2', V2[0])], aired(t['records']))
        self.assertEqual(['S', 'S'], [item['show_id'] for item in s['records']])
        self.assertEqual(['T'], [item['show_id'] for item in t['records']])
        self.assertEqual([], s['cues'][0]['missing'])
        self.assertEqual(['en'], t['cues'][0]['missing'])
        self.assertEqual('unknown_show', house.read('missing', expected=404)['error'])
        self.assertEqual('unknown_cue', house.read('S', 'missing', expected=404)['error'])

    def test_offline_playout(self):
        house = House(self)
        house.ready()
        house.desk_run.close()
        self.assertEqual([('zh', 10, 'V1', V1[0])], aired(house.advance(10)['records']))
        self.assertEqual([('en', 12, 'V1', V1[1])], aired(house.advance(12)['records']))
        self.assertTrue(house.read()['complete'])

    def test_preload_unconfirmed_and_duplicate_delivery(self):
        house = House(self)
        formal = house.rehearse(house.prepare())
        route = ('POST', '/inbox')
        house.block.add(route)
        pending = house.preload(expected=202)
        self.assertEqual('pending', pending['status'])
        self.assertEqual('unknown_show', house.advance(9, expected=404)['error'])
        self.assertEqual(formal, house.delayed[route]['manifest'])
        house.block.remove(route)
        receipt = house.deliver(route)
        self.assertEqual(receipt, house.deliver(route))
        self.assertEqual(receipt, house.preload())
        self.assertEqual(pending['manifest_id'], receipt['manifest_id'])
        self.assertEqual([('zh', 10, 'V1', V1[0])], aired(house.advance(10)['records']))
        self.assertEqual(receipt, house.deliver(route))
        self.assertEqual([('en', 12, 'V1', V1[1])], aired(house.advance(12)['records']))
        self.assertEqual(2, len(house.read()['records']))
        self.assertEqual([], house.advance(12)['records'])

    def test_reinitialize_preserves_edits_and_playout(self):
        house = House(self, sample=True)
        revision = house.approve()
        formal = house.rehearse(revision)
        receipt = house.preload()
        house.draft([cue(second=14, texts=V2)])
        first = house.advance(10)['records'][0]
        house.restart_desk(sample=True)
        house.restart_screen()
        self.assertEqual([cue(second=14, texts=V2)], house.edit(200, 'GET', '/draft?script_id=weekend')['cues'])
        self.assertEqual(formal, house.edit(200, 'GET', '/rehearse?show_id=S'))
        self.assertEqual(receipt, house.preload())
        self.assertEqual([first], house.read(cue_id='C')['records'])
        self.assertEqual([], house.advance(10)['records'])
        self.assertEqual([('en', 12, 'V1', V1[1])], aired(house.advance(12)['records']))
        self.assertEqual([('zh', 10, 'V1', V1[0]), ('en', 12, 'V1', V1[1])],
                         aired(house.read(cue_id='C')['records']))
