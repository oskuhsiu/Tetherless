#!/usr/bin/env python3
"""Acquire exactly the selected successful C Actions proof before Rust compilation.

The committed context is deliberately unselected until genuine C acceptance.
Only this caller creates the handoff hash; no artifact may choose its own trust.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile

from apply_patch import canonical_json
from build_xcframework import file_hash
from retained_c_provider import (REPOSITORY, MAX_JSON, MAX_ZIP, require, load_selection, validate_selection,
    verify_run, verify_job, verify_artifact_metadata, verify_git_tree, zip_files, validate_product,
    digest, verify, read_json_bytes)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, newurl):
        return None


class ActionsRead:
    def __init__(self, token):
        require(isinstance(token, str) and bool(token), 'read-only GitHub job token is required')
        self.base = 'https://api.github.com/repos/' + REPOSITORY + '/'
        self.token = token
        self.opener = urllib.request.build_opener(NoRedirect())
        self.deadline = time.monotonic() + 600

    def open(self, url, *, authenticated):
        require(time.monotonic() < self.deadline, 'C artifact acquisition exceeded 600 seconds')
        headers = {'User-Agent': 'tetherless-retained-c-provider', 'Accept': 'application/vnd.github+json'}
        if authenticated:
            route = url.removeprefix(self.base)
            require(url.startswith(self.base) and re.fullmatch(
                r'(?:actions/runs/[1-9][0-9]*(?:/(?:artifacts\?per_page=100&page=[1-9][0-9]*|attempts/[1-9][0-9]*/jobs\?per_page=100&page=[1-9][0-9]*))?'
                r'|actions/(?:jobs/[1-9][0-9]*|artifacts/[1-9][0-9]*(?:/zip)?)'
                r'|git/(?:commits/[0-9a-f]{40}|trees/[0-9a-f]{40}\?recursive=1))', route),
                'unreviewed authenticated C API destination')
            headers.update({'Authorization': 'Bearer ' + self.token, 'X-GitHub-Api-Version': '2022-11-28'})
        return self.opener.open(urllib.request.Request(url, headers=headers), timeout=30)

    def get(self, route):
        with self.open(self.base + route, authenticated=True) as response:
            require(response.status == 200, 'C Actions metadata request failed')
            raw = response.read(MAX_JSON + 1)
        return read_json_bytes(raw)

    def download(self, artifact_id, destination, expected_size):
        require(type(artifact_id) is int and artifact_id > 0 and type(expected_size) is int and 0 < expected_size <= MAX_ZIP,
                'invalid C artifact download identity or bound')
        require(not destination.exists() and not destination.is_symlink(), 'C artifact download output must be fresh')
        try:
            response = self.open(self.base + 'actions/artifacts/' + str(artifact_id) + '/zip', authenticated=True)
        except urllib.error.HTTPError as error:
            try:
                require(error.code == 302, 'C artifact download did not return its expected redirect')
                location = error.headers.get('Location', '')
            finally:
                error.close()
        else:
            response.close()
            raise ValueError('C artifact download did not return its expected redirect')
        target = urllib.parse.urlsplit(location)
        require(target.scheme == 'https' and target.hostname and not target.username and not target.password
                and target.port in (None, 443) and not target.fragment
                and any(target.hostname.endswith(suffix) for suffix in ('.blob.core.windows.net', '.actions.githubusercontent.com')),
                'C artifact redirect is outside reviewed HTTPS storage')
        # No auth forwarding and no automatic second redirect. Never retain the URL.
        with self.open(location, authenticated=False) as response, destination.open('xb') as output:
            require(response.status == 200, 'C artifact storage request failed')
            count = 0
            while True:
                require(time.monotonic() < self.deadline, 'C artifact acquisition exceeded 600 seconds')
                chunk = response.read(min(1024 * 1024, expected_size - count + 1))
                if not chunk: break
                count += len(chunk)
                require(count <= expected_size, 'C artifact download exceeds selected size')
                output.write(chunk)
        require(count == expected_size, 'C artifact download is shorter than selected size')


def write_json(path, value):
    with path.open('xb') as stream:
        stream.write(canonical_json(value))


def listing(api, route, key, retained, stem):
    rows, total, seen = [], None, set()
    for page in range(1, 21):
        value = api.get(route + '?per_page=100&page=' + str(page))
        write_json(retained / (stem + '-%02d.json' % page), value)
        count, items = value.get('total_count'), value.get(key)
        require(type(count) is int and 0 <= count <= 2000 and (total is None or total == count)
                and isinstance(items, list) and len(items) <= 100, 'C Actions listing count invalid or unstable')
        total = count
        for item in items:
            require(isinstance(item, dict) and type(item.get('id')) is int and item['id'] > 0
                    and item['id'] not in seen, 'C Actions listing repeats or omits an identity')
            seen.add(item['id'])
        rows.extend(items)
        require(len(rows) <= total, 'C Actions listing exceeds total')
        if len(rows) == total: return rows
        require(bool(items), 'C Actions listing is incomplete')
    raise ValueError('C Actions listing exceeded 20 pages')


def acquire(api, selection, destination, *, selection_path=None):
    s = validate_selection(selection)
    require(not destination.exists() and not destination.is_symlink(), 'retained C output must be fresh')
    destination.mkdir(parents=True)
    retained = destination / 'api'; retained.mkdir()
    run_route = 'actions/runs/' + str(s['run_id'])
    run = api.get(run_route); verify_run(run, s)
    write_json(retained / 'run-before.json', run)
    jobs = listing(api, run_route + '/attempts/' + str(s['run_attempt']) + '/jobs', 'jobs', retained, 'jobs')
    matches = [j for j in jobs if j.get('name') == 'c-provider']
    require(len(matches) == 1, 'C provider job absent or ambiguous')
    verify_job(matches[0], s)
    job = api.get('actions/jobs/' + str(s['job_id']))
    require(job == matches[0], 'C job changed after listing'); verify_job(job, s)
    write_json(retained / 'job.json', job)
    artifacts = listing(api, run_route + '/artifacts', 'artifacts', retained, 'artifacts')
    matches = [a for a in artifacts if a.get('id') == s['artifact_id']]
    exact_name = 'c-provider-' + s['source_commit'] + '-' + str(s['run_attempt'])
    require(len(matches) == 1 and len([a for a in artifacts if a.get('name') == exact_name]) == 1,
            'selected C artifact absent or ambiguous')
    verify_artifact_metadata(matches[0], s)
    metadata = api.get('actions/artifacts/' + str(s['artifact_id']))
    require(metadata == matches[0], 'C artifact metadata changed after listing'); verify_artifact_metadata(metadata, s)
    write_json(retained / 'artifact.json', metadata)
    commit = api.get('git/commits/' + s['source_commit'])
    require(commit.get('sha') == s['source_commit'] and isinstance(commit.get('tree', {}).get('sha'), str)
            and re.fullmatch('[0-9a-f]{40}', commit['tree']['sha']), 'C source commit identity differs')
    tree = api.get('git/trees/' + commit['tree']['sha'] + '?recursive=1')
    verify_git_tree(tree, commit['tree']['sha'])
    write_json(retained / 'source-commit.json', commit); write_json(retained / 'source-tree.json', tree)
    archive = destination / 'actions-artifact.zip'
    api.download(s['artifact_id'], archive, s['size_in_bytes'])
    require(archive.is_file() and not archive.is_symlink() and archive.stat().st_size == s['size_in_bytes']
            and file_hash(archive) == s['archive_sha256'], 'C outer Actions ZIP digest or size differs')
    outer = zip_files(archive)
    product, _targets = validate_product(outer, s, commit, tree)
    product_root = destination / 'product'; product_root.mkdir()
    for name, raw in product.items():
        path = product_root / name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(raw)
    # Recheck final run identity after all validation to reject a racing rerun.
    final_run = api.get(run_route); verify_run(final_run, s)
    write_json(retained / 'run-after.json', final_run)
    final_job = api.get('actions/jobs/' + str(s['job_id'])); verify_job(final_job, s)
    require(final_job == job, 'C successful job changed during acquisition')
    final_metadata = api.get('actions/artifacts/' + str(s['artifact_id'])); verify_artifact_metadata(final_metadata, s)
    require(final_metadata == metadata, 'C artifact changed during acquisition')
    handoff = {'schema': 1, 'selection': s,
        'api_files': {'api/' + p.name: file_hash(p) for p in sorted(retained.iterdir())},
        'product_files': {'product/' + n: digest(raw) for n, raw in product.items()}}
    handoff_path = destination / 'handoff.json'; write_json(handoff_path, handoff)
    handoff_sha256 = file_hash(handoff_path)
    for sdk, target in (('iphoneos', 'aarch64-apple-ios'), ('iphonesimulator', 'aarch64-apple-ios-sim')):
        verify(destination, {'sdk': sdk, 'rust': target}, expected_handoff_sha256=handoff_sha256, selection_path=selection_path)
    return {'handoff_sha256': handoff_sha256}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        selection = load_selection()  # Never create an API client for an unselected context.
        require(os.environ.get('GITHUB_REPOSITORY') == REPOSITORY, 'C acquisition caller repository differs')
        result = acquire(ActionsRead(os.environ['GH_TOKEN']), selection, args.output.absolute())
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write('handoff_sha256=' + result['handoff_sha256'] + '\n')
    except (ValueError, KeyError, OSError, zipfile.BadZipFile) as error:
        # URLError can include a signed storage URL. Suppress transport details.
        message = type(error).__name__ if isinstance(error, urllib.error.URLError) else str(error)
        parser.exit(1, 'C handoff acquisition failed: ' + message + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
