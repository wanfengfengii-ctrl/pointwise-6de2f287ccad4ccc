import unittest

from tests.support import House, lanes


class PreloadTests(unittest.TestCase):
    def test_recover_preload_commit_after_response_loss(self):
        house = House(self)
        house.rehearse(house.prepare())
        house.lose.add(('POST', '/inbox'))
        pending = house.preload(expected=202)
        actual = house.project(200, 'GET', '/inbox?show_id=S')
        self.assertEqual('pending', pending['status'])
        self.assertEqual(pending['manifest_id'], actual['manifest_id'])
        house.restart_desk()
        self.assertEqual(actual, house.preload())

    def test_pending_preload_pins_its_formal_manifest(self):
        house = House(self)
        revision = house.prepare()
        formal = house.rehearse(revision)
        house.block.add(('POST', '/inbox'))
        house.preload(expected=202)
        rejected = house.rehearse(revision, setup=lanes(en=4), expected=409)
        self.assertEqual('show_already_preloading', rejected['error'])
        self.assertEqual(formal, house.edit(200, 'GET', '/rehearse?show_id=S'))
        house.block.clear()
        self.assertEqual('received', house.preload()['status'])
        self.assertEqual(['zh', 'en'], [row['language'] for row in house.advance(12)['records']])
