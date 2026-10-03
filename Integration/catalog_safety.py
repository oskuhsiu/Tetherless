#!/usr/bin/env python3
"""Reject ambiguous catalog graphs before save; never trap on remote records."""
from pathlib import Path
import hashlib
import sys

MERGE = 'AltStore/Core/Model/MergePolicies/MergePolicy.swift'
FETCH = 'SideStore/Core/Operations/StandaloneOperations/FetchSourceOperation.swift'
MANAGER = 'AltStore/Managing Apps/AppManager.swift'
BLOBS = {MERGE: '568c3a86963c31bde649ee44cdfdc7c4a0cbea75',
         FETCH: '06d019d1b3ae98eaa1593d7fec954633c1e13fd6',
         MANAGER: '9397828fddd9c47cfa8d17e6cec1d4f0a7385bbb'}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unreviewed catalog transformation anchor')
    return text.replace(old, new, 1)


def patch_merge(text):
    return once(text, '''                // Unknown context-level conflict.
                let entityName = conflict.conflictingObjects.first?.entity.name ?? "Unknown"
                assertionFailure("Context Conflict Detected for table '\\(entityName)': is there ambiguous data?\\nConflict:\\(conflict)")''',
        '''                // A remote source is data, not a programmer assertion. Refuse
                // the transaction without a Debug trap or Release-mode data loss.
                throw CatalogImportError.unresolvedConstraint''')


def patch_fetch(text):
    text = once(text, '''            let identifier = try self.performDecodeAndSave(data: data, response: response, childContext: childContext)
            try childContext.save()
            return identifier''', '''            do {
                let identifier = try self.performDecodeAndSave(data: data, response: response, childContext: childContext)
                try childContext.save()
                return identifier
            } catch {
                // Nothing from a rejected source reaches the parent context.
                childContext.rollback()
                throw error
            }''')
    text = once(text, '''        try self.verify(source, response: response)
''', '''        // Includes every release channel, not only app.versions. Validate
        // before any save or legacy deduplication can discard an arbitrary row.
        try CatalogImportSafety.validateNewVersions(in: childContext)
        try self.verify(source, response: response)
''')
    text = once(text, '''        var duplicateApps = [StoreApp]()
''', '')
    text = once(text, '''                duplicateApps.append(app)
                continue''', '''                throw CatalogImportError.duplicateApp''')
    text = once(text, '''            var versions = Set<String>()
            var duplicateVersions = [AppVersion]()
            for version in app.versions {
                if versions.contains(version.versionID) {
                    duplicateVersions.append(version)
                    continue
                }
                versions.insert(version.versionID)
            }
            
            for version in duplicateVersions {
                debugLog("[FetchSourceOperation]: Warning: Skipping duplicate version '\\(version.version)' for app '\\(app.name)' (\\(app.bundleIdentifier)).")
                version.managedObjectContext?.delete(version)
            }
            
''', '')
    return once(text, '''        for app in duplicateApps {
            debugLog("[FetchSourceOperation]: Warning: Skipping duplicate app '\\(app.name)' (\\(app.bundleIdentifier)) in source '\\(source.name)'.")
            app.managedObjectContext?.delete(app)
        }
        
''', '')


def patch_manager(text):
    return once(text, '''                    debugLog("Failed to save managedObjectContext in fetchSources: \\(error.localizedDescription)")''', '''                    // Do not report success or hand an unsaved conflicting
                    // context to a caller which might attempt to save it again.
                    managedObjectContext.rollback()
                    completionHandler(.failure(.init(error)))
                    NotificationCenter.default.post(name: AppManager.didFetchSourceNotification, object: self)
                    return''')


def apply(root):
    outputs = {}
    for name, transform in [(MERGE, patch_merge), (FETCH, patch_fetch), (MANAGER, patch_manager)]:
        data = (root / name).read_bytes()
        digest = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if digest != BLOBS[name]:
            raise ValueError('Unreviewed catalog input: ' + name)
        outputs[name] = transform(data.decode())
    for name, text in outputs.items():
        (root / name).write_text(text)


if __name__ == '__main__':
    apply(Path(sys.argv[1]))
