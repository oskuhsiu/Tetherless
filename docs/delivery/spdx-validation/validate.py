#!/usr/bin/env python3
"""Recheck preserved SPDX 2.3 structural evidence locally; never fetch a schema."""
from copy import deepcopy
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform

from jsonschema import Draft7Validator, FormatChecker
from referencing import Registry

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
INPUT_SHA256 = 'e249a287e44af82fed07e6525b6bc18d801989ee67101ce1745dbb21e1b17ebc'
SCHEMA_SHA256 = '239208b7ac287b3cf5d9a9af23f9d69863971102a5e1587a27a398b43490b89b'
SCHEMA_BLOB = 'ee61e6686e885f8139c132647fd0b4f483b8fb81'


def pointer(path):
    return '/' + '/'.join(str(p).replace('~', '~0').replace('/', '~1') for p in path) if path else ''


def report_error(error):
    return {'instancePointer': pointer(error.absolute_path),
            'schemaPointer': pointer(error.absolute_schema_path),
            'keyword': error.validator, 'message': error.message}


def main():
    source = ROOT / 'docs/supply-chain/candidate-sbom.spdx.json'
    original = source.read_bytes()
    schema_bytes = (HERE / 'spdx-2.3.schema.json').read_bytes()
    if hashlib.sha256(original).hexdigest() != INPUT_SHA256:
        raise ValueError('Historical candidate bytes differ from this evidence')
    if hashlib.sha256(schema_bytes).hexdigest() != SCHEMA_SHA256:
        raise ValueError('Pinned schema bytes differ from this evidence')
    if hashlib.sha1(b'blob ' + str(len(schema_bytes)).encode() + b'\0' + schema_bytes).hexdigest() != SCHEMA_BLOB:
        raise ValueError('Pinned schema does not match its upstream Git blob')
    document, schema = json.loads(original), json.loads(schema_bytes)
    refs, formats = [], []
    def inspect(value):
        if isinstance(value, dict):
            if '$ref' in value:
                refs.append(value['$ref'])
            if 'format' in value:
                formats.append(value['format'])
            for item in value.values():
                inspect(item)
        elif isinstance(value, list):
            for item in value:
                inspect(item)
    inspect(schema)
    if any(not isinstance(ref, str) or not ref.startswith('#') for ref in refs):
        raise ValueError('Remote schema references are not permitted')
    retrievals = []
    def reject_remote(uri):
        retrievals.append(uri)
        raise RuntimeError('Remote schema retrieval disabled')
    Draft7Validator.check_schema(schema)
    validator = Draft7Validator(schema, registry=Registry(retrieve=reject_remote), format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(document), key=lambda e: (pointer(e.absolute_path), e.message))
    negative = deepcopy(document)
    del negative['SPDXID']
    negative_errors = list(validator.iter_errors(negative))
    if not any(e.validator == 'required' and "'SPDXID' is a required property" == e.message for e in negative_errors):
        raise AssertionError('Negative control did not detect the missing required field')
    if source.read_bytes() != original:
        raise AssertionError('Historical candidate changed during validation')
    print(json.dumps({
        'outcome': 'pass' if not errors else 'fail', 'errorCount': len(errors),
        'errors': [report_error(e) for e in errors], 'schemaSelfValidation': 'passed',
        'inputSHA256': INPUT_SHA256, 'schemaSHA256': SCHEMA_SHA256,
        'validator': {'implementation': 'python-jsonschema', 'version': importlib.metadata.version('jsonschema'),
                      'class': 'jsonschema.Draft7Validator', 'python': platform.python_version(),
                      'referencingVersion': importlib.metadata.version('referencing')},
        'formatCheckerEnabled': True, 'schemaReferenceCount': len(refs), 'schemaFormatKeywordCount': len(formats),
        'remoteRetrievalAttempts': retrievals,
        'negativeControl': {'description': 'Removed top-level SPDXID in an in-memory copy only',
                            'outcome': 'expected-rejection', 'errors': [report_error(e) for e in negative_errors]},
        'historicalInputUnchanged': True,
        'scope': 'Pinned historical JSON Schema structural validation only; no complete semantic compliance or final linked-binary claim.'
    }, sort_keys=True, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
