import json
from pathlib import Path
from tempfile import TemporaryDirectory

from editorial.http import serve as serve_editorial
from local_service import call, running
from projection.http import serve as serve_projection
from projection.timing import LocalClock


def expect(expected_status, base, method, path, data=None):
    status, result = call(base, method, path, data)
    if status != expected_status:
        raise RuntimeError(f'{method} {path} returned {status}: {result}')
    return result


def main():
    with TemporaryDirectory(prefix='subtitle-demo-') as directory:
        root = Path(directory)
        second = 0
        with running(serve_projection(root / 'screen.sqlite', clock=LocalClock(lambda: second))) as screen:
            with running(serve_editorial(root / 'desk.sqlite', screen, sample=True)) as desk:
                revision = expect(200, desk, 'POST', '/approve', {'script_id': 'weekend'})['revision']
                manifest = expect(200, desk, 'POST', '/rehearse', {
                    'show_id': 'S', 'revision': revision, 'start': 0,
                    'lanes': {'zh': {'offset': 0, 'screen': 'left', 'duration': 2},
                              'en': {'offset': 2, 'screen': 'right', 'duration': 2}},
                })
                expect(200, desk, 'POST', '/preload', {'show_id': 'S'})
                second = 9
                correction = {'show_id': 'S', 'cue_id': 'C', 'correction_id': 'Q',
                              'zh': '请就座', 'en': 'Please take your seat'}
                receipt = expect(200, desk, 'POST', '/correct', correction)
                for second in (10, 12, 20, 22):
                    expect(200, screen, 'POST', '/advance', {'show_id': 'S'})
                readback = expect(200, screen, 'GET', '/readback?show_id=S&cue_id=C')
                closing = expect(200, screen, 'GET', '/readback?show_id=S')
                actual = [[row[key] for key in ('language', 'aired_at', 'version', 'text')]
                          for row in readback['records']]
                expected = [['zh', 10, 'V2', '请就座'], ['en', 12, 'V2', 'Please take your seat']]
                scheduled = [(row['cue_id'], row['language'], row['at']) for row in manifest['outputs']]
                if scheduled != [('C', 'zh', 10), ('C', 'en', 12), ('D', 'zh', 20), ('D', 'en', 22)]:
                    raise RuntimeError(f'Unexpected rehearsal: {scheduled}')
                if receipt['status'] != 'accepted' or actual != expected or not closing['complete']:
                    raise RuntimeError(f'Unexpected playout: {receipt}, {closing}')
                print(json.dumps({'rehearsal': manifest, 'correction': receipt, 'readback': closing}, ensure_ascii=False))
                scenario = {
                    'case_id': 'v6', 'input': {'correction': correction, 'second': 9, 'scheduled': scheduled},
                    'expected': 'accepted', 'actual': receipt['status'],
                    'downstream_expected': expected, 'downstream_actual': actual,
                    'code_paths': ['editorial/reconcile.py', 'projection/cues.py', 'projection/output.py', 'airlog/queries.py'],
                    'oracle': '样例 C 在第 10 秒，英文偏移 2 秒。第 9 秒获准后原时点不变，两路手工核对替换正文。',
                }
                print('POINTWISE_SCENARIO ' + json.dumps(scenario, ensure_ascii=False))


if __name__ == '__main__':
    main()
