"""Read individual Hypium outcomes from a complete native runner log."""
from collections import Counter
import re


SUMMARY = re.compile(
    r'^OHOS_REPORT_RESULT: stream=Tests run: (\d+), Failure: (\d+), Error: (\d+), Pass: (\d+), Ignore: (\d+)\s*$',
    re.MULTILINE,
)
OUTCOMES = {0: 'PASS', -1: 'ERROR', -2: 'FAIL', -3: 'SKIP', -4: 'SKIP'}


def parse_hypium(log: str) -> dict:
    summaries = SUMMARY.findall(log)
    if len(summaries) != 1:
        raise ValueError('expected exactly one Hypium result summary')
    total, failed, errors, passed, ignored = map(int, summaries[0])
    if not total or re.findall(r'^TestFinished-ResultCode: (\S+)\s*$', log, re.MULTILINE) != ['0']:
        raise ValueError('Hypium execution did not finish with test results')
    fields, active, cases = {}, set(), {}
    for line in log.splitlines():
        if line.startswith('OHOS_REPORT_STATUS: '):
            key, _, value = line.removeprefix('OHOS_REPORT_STATUS: ').partition('=')
            if key in ('class', 'test'):
                fields[key] = value
        elif line.startswith('OHOS_REPORT_STATUS_CODE: '):
            code = int(line.removeprefix('OHOS_REPORT_STATUS_CODE: '))
            identity = (fields.pop('class', ''), fields.pop('test', ''))
            if not all(identity) or identity in cases:
                raise ValueError(f'invalid or duplicate Hypium case: {identity}')
            if code == 1 and identity not in active:
                active.add(identity)
            elif code in OUTCOMES and identity in active:
                active.remove(identity)
                cases[identity] = OUTCOMES[code]
            else:
                raise ValueError(f'unmatched Hypium status {code}: {identity}')
    counts = Counter(cases.values())
    if active or len(cases) != total or [counts[key] for key in ('FAIL', 'ERROR', 'PASS', 'SKIP')] != [
        failed, errors, passed, ignored
    ]:
        raise ValueError('Hypium cases disagree with the result summary')
    return {'counts': dict(counts), 'cases': [
        {'suite': suite, 'test': test, 'status': status} for (suite, test), status in cases.items()
    ]}
