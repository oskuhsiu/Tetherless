`demo1.dylib` is a synthetic upstream test binary, not an application or Apple credential.
Source: SylvaSigner f7127d6857a6aaa919b7430ef73baa262fe28070,
`vendor/zsign/test/dylib/bin/demo1.dylib` (zsign MIT license in ../../licenses/).
Tests create a temporary IPA around this fixture and generate self-signed test-only
certificates, CMS profiles and P12 bytes in memory. Those certificates are NOT
Apple-issued and the output cannot establish real iOS installation acceptance.
