# Pinned gateway namespace fixtures

These public Swift sources retain the upstream copyright notices and are covered by
`../../../upstream/minimuxer-LICENSE` (GNU Affero General Public License version 3).

Repository: https://github.com/SideStore/minimuxer
Commit: `12be70dc2627307a16bfd2dc7a009080d5bec909`

- `IdeviceGateway.privacy-prepared.swift` derives from
  `DeviceGateway/idevice/IdeviceGateway.swift`, Git blob
  `e9310d0236e244813ce945236bdb99af2582f649`, upstream SHA256
  `812ea4d876c09a05e17a8ef2581915678508e0622a527d37d7f85cb248e457e8`.
  It applies only the existing `Integration/pairing_safety.py::patch_gateway`
  transformation: remove two sensitive PIN log values and disable native payload
  logging. Its exact prepared SHA256 is
  `1b66301e4ae70268ca3966639feed46271858265aa16a687dc4b144cf5179fb0`.
- `LibimobiledeviceGateway.upstream.swift` is the unmodified
  `DeviceGateway/libimobiledevice/LibimobiledeviceGateway.swift`, Git blob
  `44de5253a53d05d85dd99a2e32e96fbf13531f0e`, SHA256
  `32964c92c48c8f6e5b115edee1afa109606c9221c0ab5381f9e3c3bd54f4aef1`.
  It contains C-library calls with overlapping spellings that must not be adapted.

The helper pins one whole preimage and replaces reviewed executable-token byte
spans only. Tests neither fetch dependencies nor execute a native library or device.
