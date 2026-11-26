import unittest

from tests.support import House, V1, cue


class DraftTests(unittest.TestCase):
    def test_missing_translation_leaves_saved_draft_and_revision(self):
        house = House(self)
        self.assertEqual('V1', house.prepare())
        self.assertEqual('invalid_string', house.draft([cue(texts=(V1[0], '  '))], expected=400)['error'])
        self.assertEqual([cue()], house.edit(200, 'GET', '/draft?script_id=weekend')['cues'])
        self.assertEqual([cue()], house.edit(200, 'GET', '/revision?revision=V1')['cues'])

    def test_fresh_approval_has_independent_identity(self):
        house = House(self)
        first = house.prepare()
        adjusted = cue(second=15)
        house.draft([adjusted])
        second = house.approve()
        self.assertEqual(('V1', 'V2'), (first, second))
        self.assertEqual([cue()], house.edit(200, 'GET', '/revision?revision=V1')['cues'])
        self.assertEqual([adjusted], house.edit(200, 'GET', '/revision?revision=V2')['cues'])
