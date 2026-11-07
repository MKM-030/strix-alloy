"""Qualify native cost-rule activation from saved text and request counters."""
import re

STARTUP = re.compile(r'\bflash_serve: listening on [^\r\n]*; MTP depth-\d+[^\r\n]*')
PATTERN = re.compile(
    r'\breq (?P<id>\d+) spec: (?P<rounds>\d+) rounds (?P<legacy_accepted>\d+) accepted; '
    r'chain (?P<head_rounds>\d+) rounds (?P<head_drafted>\d+) drafted (?P<head_accepted>\d+) accepted; '
    r'lookup (?P<lookup_rounds>\d+) rounds (?P<lookup_drafted>\d+) drafted (?P<lookup_accepted>\d+) accepted; '
    r'grammar (?P<grammar_rounds>\d+) rounds (?P<grammar_drafted>\d+) drafted (?P<grammar_accepted>\d+) accepted; '
    r'\d+ serial;(?: list (?P<list_tokens>\d+) tokens (?P<list_off>\d+) off;)?')


def qualify_trace(text, samples, expected_rule):
    if type(expected_rule) is not str or expected_rule not in ('gate', 'cost'):
        raise ValueError('Requires exact gate or cost rule')
    banners = STARTUP.findall(text)
    marker = 'cost rule' if expected_rule == 'cost' else 'confidence gate'
    if (len(banners) != 1 or ', ' + marker + ')' not in banners[0]
            or sum(', ' + item + ')' in banners[0] for item in ('cost rule', 'confidence gate')) != 1):
        raise ValueError('Requires exactly one matching native MTP startup banner')
    ids = [sample['native_request_id'] for sample in samples]
    if len(ids) != 4 or len(set(ids)) != 4 or any(type(value) is not int or value < 0 for value in ids):
        raise ValueError('Requires four unique native request IDs')
    traces = {}
    for match in PATTERN.finditer(text):
        row = {key: int(value) for key, value in match.groupdict().items() if value is not None}
        traces.setdefault(row['id'], []).append(row)
    result = []
    for sample in samples:
        matches = traces.get(sample['native_request_id'], [])
        if len(matches) != 1:
            raise ValueError('Selected native request trace missing or duplicated')
        row = matches[0]
        counters = sample['speculation']
        # The legacy aggregate 'accepted' log field has no matching API field.
        # Reconcile only fields exposed with the same semantics by the API.
        expected = dict(rounds=counters['rounds'])
        expected.update({scope + '_' + key: counters[scope][key]
            for scope in ('head', 'lookup', 'grammar') for key in ('rounds', 'drafted', 'accepted')})
        if any(type(value) is not int or value < 0 or row[key] != value for key, value in expected.items()):
            raise ValueError('Native request and saved speculation counters differ')
        if row['head_rounds'] <= 0 or row['head_drafted'] <= 0:
            raise ValueError('Positive MTP head activity is required')
        if any(row[scope + '_' + key] for scope in ('lookup', 'grammar')
               for key in ('rounds', 'drafted', 'accepted')):
            raise ValueError('Natural cost qualification requires zero lookup and grammar activity')
        result.append(row)
    return dict(expected_rule=expected_rule, startup_banner=dict(marker=marker, count=1),
        samples=result, native_rule_activation_observed=True, per_decision_policy_observed=False,
        qualification_scope='Native startup rule with matching per-request MTP head counters')
