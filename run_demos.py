"""Checklist demo entry: ordinary business demo followed by co-display scenarios.

Runs both real-HTTP demonstrations in order and exits non-zero if either the
ordinary demo raises or the simultaneous scenarios fail.
"""
import sys
import unittest

import demo
import simultaneous_demo


def main():
    print('=== ordinary show demo (demo.py) ===', file=sys.stderr, flush=True)
    demo.main()
    print('=== bilingual co-display scenarios (simultaneous_demo.py) ===',
          file=sys.stderr, flush=True)
    suite = unittest.defaultTestLoader.loadTestsFromModule(simultaneous_demo)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
