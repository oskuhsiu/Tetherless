# Local signing export crypto

`TetherlessForge.min.js` is the unmodified distribution from **node-forge 1.4.0**, already pinned in `WebBootstrap/package-lock.json`. Upstream: https://github.com/digitalbazaar/forge. SHA-256: `d9b9074e6861200d676e25dcfe97889db5e8f4150bb766d29c491ad709a51b58`. The adjacent upstream LICENSE is retained. No runtime download or remote service is used.

`TetherlessSigningCrypto.js` is our local adapter. Both resources are hash-checked by `NativeEncryptedP12` before execution. JavaScriptCore gets Security.framework random bytes; `Math.random` throws. Secrets are passed as function arguments, never interpolated into source, logged or sent to a web view. A new context is discarded after each operation.

The pinned CodeSignKit `d0c67710fda9a2646b9e829cb2cf443892728371` `Sources/PKCS12Builder.swift` lines 15–19 accepts `password`, but lines 57–67 emit an unencrypted `keyBag` and lines 83–89 return a PFX without MAC. Therefore the native legacy `encryptedP12Data` is NOT an encrypted-export implementation. It is not used for external backups. Internal existing Keychain envelopes continue to rely on platform Keychain protection; no misleading claim of file encryption is made.

Native export requires successful resource checks, encrypted shrouded-key-bag+MAC construction, same-password platform `SecPKCS12Import` with exact cert/key binding, and empty/wrong-password rejection. Failure never falls back to the upstream builder. Native compilation, packaged resource presence and actual iOS import compatibility are independent gates; Node/OpenSSL interoperability is not iOS acceptance.
