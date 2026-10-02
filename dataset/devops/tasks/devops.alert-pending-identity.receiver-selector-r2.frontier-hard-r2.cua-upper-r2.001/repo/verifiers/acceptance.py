"""Protected behavioral acceptance; additional annotations are not identity."""
def annotation_errors(actual, required, immutable_labels):
    if not isinstance(actual, dict):
        return ['annotations must be a mapping']
    errors = []
    for key, value in actual.items():
        if not isinstance(key, str) or not isinstance(value, str):
            errors.append('annotation keys and values must be strings')
    for key, value in required.items():
        if key not in actual:
            errors.append('missing required annotation: ' + key)
        elif actual[key] != value:
            errors.append('incorrect required annotation: ' + key)
    for key in actual.keys() - required.keys():
        if key in immutable_labels and actual[key] != immutable_labels[key]:
            errors.append('annotation contradicts immutable label: ' + key)
    return errors


def row_matches(actual, expected):
    if not isinstance(actual, dict):
        return False
    actual_core = {key: value for key, value in actual.items() if key != 'annotations'}
    expected_core = {key: value for key, value in expected.items() if key != 'annotations'}
    if actual_core != expected_core:
        return False
    if not expected['condition']:
        return actual.get('annotations') == expected['annotations']
    return not annotation_errors(actual.get('annotations'), expected['annotations'], expected['labels'])


def history_matches(actual, expected):
    if not isinstance(actual, dict) or actual.keys() != expected.keys():
        return False
    for key, rows in expected.items():
        if not isinstance(actual[key], list) or len(actual[key]) != len(rows):
            return False
        if not all(row_matches(a, e) for a, e in zip(actual[key], rows)):
            return False
    return True


def rendered_annotations_match(pairs, actual, expected):
    if not row_matches(actual, expected):
        return False
    if not isinstance(pairs, list) or any(not isinstance(pair, list) or len(pair) != 2 for pair in pairs):
        return False
    if any(not isinstance(k, str) or not isinstance(v, str) for k, v in pairs):
        return False
    rendered = dict(pairs)
    return len(rendered) == len(pairs) and rendered == actual['annotations']
