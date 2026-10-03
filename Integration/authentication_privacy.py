#!/usr/bin/env python3
"""Remove raw authentication diagnostics from exact reviewed SideSign sources."""
from pathlib import Path
import hashlib
import re
import sys

AUTH = 'Dependencies/SideSign/Sources/DeveloperPortal/Authentication.swift'
LOG = 'Dependencies/SideSign/Sources/Logging.swift'
BLOBS = {AUTH: 'f60d4c67dcca0f093dc3ac949fdd0492ef7431a2',
         LOG: '5a90099f4c017db759c5446946d13f348cc90f2a'}


def once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Unreviewed authentication privacy anchor')
    return text.replace(old, new, 1)


def patch_auth(text):
    # Remove all 72 reviewed free-form call sites, including two multiline
    # literals. Refuse new syntax instead of silently leaving a payload logger.
    output, multiline, removed = [], False, 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if multiline:
            if stripped == '\"\"\")': multiline = False
            continue
        if stripped.startswith(('debugLog(', 'verboseLog(')):
            removed += 1
            if stripped.endswith('(\"\"\"'): multiline = True
            elif not stripped.endswith(')'): raise ValueError('Unexpected log syntax')
            continue
        output.append(line)
    if multiline or removed != 72:
        raise ValueError('Unexpected authentication logger inventory')
    text = ''.join(output)
    # Dead formatting variables and header-only blocks are no longer needed.
    text = re.sub(r'^\s*if let allHeaders = request\.allHTTPHeaderFields \{\s*\}\n', '', text, flags=re.M)
    text = re.sub(r'^\s*let (?:payload|rawDecrypted|jsonStr|rawStr) = (?:prettyJSONString\(from: [^\n]+|String\(data: data, encoding: \.utf8\) \?\? data\.hexEncodedString\(\))\n', '', text, flags=re.M)
    text = re.sub(r'(jsonPayload|rawPayload): (?:prettyJSONString\(from: \w+\)|payload|rawDecrypted|jsonStr|rawStr)',
                  r'\1: "[authentication payload omitted]"', text)
    # Do not forward arbitrary server text into errors, retry prompts or logs.
    # Preserve numeric error codes and existing decisions/typed errors.
    text = once(text, 'let errorDesc = status["em"] as? String', 'let errorDesc: String? = nil')
    text = once(text, '''        let errorMsg = (responseDict?["em"] as? String)
                   ?? ((responseDict?["Status"] as? [String: any Sendable])?["em"] as? String)''',
        '        let errorMsg: String? = nil')
    text = once(text, '''        let statusDict = verifyDictionary?["Status"] as? [String: any Sendable]
        let errorMsg = (verifyDictionary?["em"] as? String)
                    ?? (statusDict?["em"] as? String)
                    ?? xmluiMessage
                    ?? xmluiTitle''', '        let errorMsg: String? = nil')
    text = once(text, 'let message = xmluiMessage ?? errorMsg ?? xmluiTitle ?? "Verification failed"',
                'let message = "Apple rejected the verification response. Please try again."')
    text = once(text, '''            let alertMsg = [xmluiTitle, xmluiMessage]
                .compactMap { $0?.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .joined(separator: ": ")
            throw DeveloperPortalError.invalid2FAResponse(cause: xmluiMessage ?? alertMsg)''',
        '''            throw DeveloperPortalError.invalid2FAResponse(cause: "Apple rejected the verification request. Please try again.")''')
    start = text.index('                let rawMessage = (statusDictionary?["em"]')
    end = text.index('                let decision = try await accountRepairHandler', start)
    text = text[:start] + '''                let message = Constants.defaultAccountRepairMessage
                SideSignLogging.authentication(.accountRepairRequired)

''' + text[end:]
    # An error can later be stringified by a UI/logger: never retain a repair
    # URL containing server-provided query data in the thrown error.
    text = once(text, 'throw DeveloperPortalError.accountRepairRequired(url: repairURL, message: message)',
                'throw DeveloperPortalError.accountRepairRequired(url: Constants.URLs.developerAccount, message: message)')
    # The interactive repair handler still receives the original official URL,
    # but rejects non-Apple / non-HTTPS destinations and embedded credentials.
    text = once(text, 'let repairURL = repairURLString.flatMap { URL(string: $0) } ?? Constants.URLs.developerAccount',
        'let repairURL = authenticationRepairURL(repairURLString, fallback: Constants.URLs.developerAccount)')
    # Fixed events cannot contain runtime values. Keep the wire protocol intact.
    text = once(text, '        let sanitizedAppleID =', '        SideSignLogging.authentication(.started)\n        let sanitizedAppleID =')
    text = once(text, '        let initResponse = try await', '        SideSignLogging.authentication(.challengeRequested)\n        let initResponse = try await')
    text = once(text, '        guard let sharedSecret = srpClient.sessionKey()',
                '        SideSignLogging.authentication(.proofVerified)\n        guard let sharedSecret = srpClient.sessionKey()')
    text = once(text, '        var currentRequest: TwoFactorRequest =', '        SideSignLogging.authentication(.secondFactorRequired)\n        var currentRequest: TwoFactorRequest =')
    text = once(text, '        return AuthSession(', '        SideSignLogging.authentication(.tokenReceived)\n        return AuthSession(')
    # Raw transport userInfo may retain response URLs/data. Keep only a fresh
    # URL error code or a stable nontransport category, not an underlying error.
    text = once(text, '''        } catch {
            throw error
        }''', '''        } catch {
            SideSignLogging.authentication(.transportFailed)
            if error is CancellationError { throw CancellationError() }
            if let failure = error as? URLError { throw URLError(failure.code) }
            throw ServerError.underlyingError(code: -1, message: "Authentication transport failed")
        }''')
    text = text.replace('key: "t/\\(app)/token"', 'key: "app-token"')
    if any(s in text for s in ['debugLog(', 'verboseLog(', 'prettyJSONString(', 'rawPayload: raw', 'jsonPayload: payload']):
        raise ValueError('Authentication payload path remains')
    # Sanitize even errors returned by fetchAccount or a caller's verification
    # handler, before the public authenticate boundary returns to native code.
    text = once(text, '        SideSignLogging.authentication(.started)',
                '        do {\n        SideSignLogging.authentication(.started)')
    text = once(text, '        return AuthSession(account: account, session: session)\n    }',
                '        return AuthSession(account: account, session: session)\n        } catch { throw sanitizedAuthenticationError(error) }\n    }')
    return text + '\n' + (Path(__file__).parent/'Overrides/AuthenticationErrorPolicy.swift').read_text()


def apply(root):
    outputs = {}
    for name, expected in BLOBS.items():
        data = (root / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if actual != expected: raise ValueError('Unreviewed authentication input: ' + name)
        outputs[name] = patch_auth(data.decode()) if name == AUTH else (Path(__file__).parent/'Overrides/SideSignLogging.swift').read_text()
    for name, text in outputs.items(): (root/name).write_text(text)

if __name__ == '__main__': apply(Path(sys.argv[1]))
