# Build artifacts and first installation

Development instructions only. No physical-device handoff is requested yet.

## Rebuild the exact source

Use `develop` or a recorded full implementation commit. Initialize the pinned recursive submodules without `--remote`, run the core and Python tests, then run `python3 Integration/prepare.py`. That script invokes `harden.py`; skipping the hardening step is not the supported Tetherless build.

Native targets keep upstream internal names:

```sh
xcodebuild build \
  -project .generated/SideStore/AltStore.xcodeproj \
  -scheme SideStore \
  -configuration Release \
  -destination 'generic/platform=iOS' \
  -derivedDataPath .generated/DerivedData \
  -onlyUsePackageVersionsFromResolvedFile \
  CODE_SIGNING_ALLOWED=NO CODE_SIGNING_REQUIRED=NO \
  AD_HOC_CODE_SIGNING_ALLOWED=YES DEVELOPMENT_TEAM=XYZ0123456 \
  ORG_IDENTIFIER=com.SideStore
```

The legacy organization/target names do not set the new base identity: the hash-locked Build.xcconfig patch explicitly sets `BASE_BUNDLE_ID = org.tetherless.Tetherless`. Verify the actual output `Info.plist`, do not infer it from the archive's filename.

`Integration/package_unsigned.py` packages `SideStore.app` as `Payload/Tetherless.app`. The internal executable name may remain SideStore. It records the source commit, configuration, output SHA-256 and explicit unvalidated/unsigned flags in `manifest.json`. CI artifacts are retained temporarily; they are not a permanent release channel.

## Bootstrap remains a separate workflow

The user must authorize signing and installation with their own Apple Account or valid registered-device credentials. A CI build does not contain a usable provisioning profile or private key. Existing desktop bootstrap tools are candidates for the first installation only; their exact compatibility with Tetherless's changed product identity still requires the consolidated acceptance pass. Do not assume a tool's SideStore-specific installation button recognizes an independently named app.

A clean device still needs an initial trusted installation path, system confirmations and pairing. On-device wireless pairing on supported systems does not itself solve initial app delivery. Daily renewal must not depend on the bootstrap computer remaining on or reconnecting later.

## Private-key change and recovery

Tetherless deliberately does not read an embedded `ALTCertificate.p12` from its own bundle to recover signing authority. After first installation, the normal authorized login/certificate flow must establish a signable identity in Tetherless's device-local Keychain. Existing certificate capacity may require an explicit choice; never automatically revoke another tool's certificate. The selected certificate/Team and manager re-sign are separate from ordinary profile renewal.

For a later manager version update or identity repair, use a trusted matching product/Team and the explicit full-install flow. Retain data and journal state, then re-enroll the repaired identity using the Auto Renewal screen. Do not uninstall first as a routine update instruction. A completely expired manager cannot execute its own recovery and may require an external reinstallation route.

## Before a device handoff

The developer supplies a reviewed source revision, correctly identified unsigned input or authorized test build, integrity manifest, bootstrap procedure, test IPA and diagnostic instructions together. The owner enters secrets only on the device or authorized local signing tool. The first unattended acceptance may renew the following day; a longer expiry-crossing observation is separate, not a seven-day coding cycle.
