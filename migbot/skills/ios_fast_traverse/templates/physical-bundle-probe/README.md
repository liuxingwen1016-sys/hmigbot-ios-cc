# I2H Physical Bundle Probe Templates

**Optional DEBUG-only templates** for physical device test evidence binding through installed bundle hash attestation.

## Purpose

These templates provide a compile-time opt-in mechanism to add bundle integrity verification to iOS apps under test on physical devices. The probe computes the installed bundle hash using the exact algorithm from `ios_evidence_protocol.py source_identity()` and writes receipts to the app's Documents directory.

## Architecture

**Shared Core + iOS Probe**:
- `I2HBundleHashCore.h/m` - Foundation-only hashing core matching `ios_evidence_protocol.py`
- `I2HBundleProbe.h/m` - UIKit DEBUG probe using shared core
- `i2h_bundle_hash_cli.m` - macOS CLI harness for host-side validation
- `test_bundle_hash_core.py` - Portable regression driver (Darwin-only)

## Integration

Manual opt-in integration required:

1. **Add source files to Xcode project** as Objective-C build sources:
   - `I2HBundleHashCore.h`
   - `I2HBundleHashCore.m`
   - `I2HBundleProbe.h`
   - `I2HBundleProbe.m`

2. **No Swift code modification needed** - the probe auto-registers via `+load` method

3. **Frameworks required**:
   - `UIKit.framework`
   - `Foundation.framework`
   - `CommonCrypto` (system library)

## Activation

The probe activates when **all** conditions are met:

- Built with `DEBUG=1` configuration
- App transitions to foreground (`UIApplicationDidBecomeActive`)
- Launch arguments include: `-I2HBundleProbeChallenge <nonce_value>`

Launch argument must be provided programmatically (e.g., via XCTest, command-line tool, or test harness).

## Security Properties

### Actual Strength (what this provides)

- **Single launch attestation**: Hash computed once per app launch at first foreground activation
- **Foreground verification**: Confirms app is in `UIApplicationStateActive` at probe start and end
- **Same PID correlation**: Probe records process ID, allowing correlation with test execution
- **Fail-closed file operations**: Any file read/enumeration error aborts hash computation and writes error receipt
- **Post-loop enumeration check**: Explicit error check after enumeration loop prevents partial hash success

### Explicit Limitations (what this does NOT provide)

- **NOT per-screenshot pre/post/ACK protocol**: This is a single one-time probe at launch, not per-request verification
- **NO independent nonce comparison proven**: Template assumes external validation; nonce freshness enforcement not device-tested
- **NO fault injection validation**: Enumeration error handling verified by code review only, not proven with device fault injection
- **Shared core host-validated only**: macOS CLI harness validated against native `ios_evidence_protocol.py`; iOS probe on physical device not tested

## Hash Algorithm

Matches `ios_evidence_protocol.py source_identity()` exactly:

```
sorted_relative_posix_paths.each do |path|
  hash.update(path + NUL + file_bytes + NUL)
end
```

**Excluded parts** (skipped in enumeration):
- `.git`, `.build`, `DerivedData`, `build`, `dist`, `node_modules`

**Included files**:
- All regular files (not symlinks, not directories)
- `_CodeSignature/` directory contents
- `embedded.mobileprovision`

**Fail-closed behavior**: Any file read error or enumeration failure returns nil and writes error receipt.

## Receipt Format

### Success Receipt

Written to: `<App Documents>/i2h_bundle_probe_receipt.json`

```json
{
  "probe_type": "installed_bundle_hash",
  "instrumented_variant": "DEBUG_source_test_only",
  "challenge": "<launch_arg_nonce>",
  "probe_start_utc": "2024-11-15T12:34:56.789Z",
  "pid": 12345,
  "bundle_id": "com.example.app",
  "version": "1.0.0",
  "build": "100",
  "foreground_at_probe_start": true,
  "application_state_at_start": 0,
  "installed_bundle_sha256": "abc123...",
  "bundle_path": "/var/containers/Bundle/Application/.../App.app",
  "probe_end_utc": "2024-11-15T12:34:57.234Z",
  "probe_duration_seconds": 0.445,
  "foreground_at_probe_end": true,
  "application_state_at_end": 0
}
```

### Error Receipt

Written to: `<App Documents>/i2h_bundle_probe_receipt_error.json`

Error conditions:
- `probe_not_in_foreground_at_start`: App not in active state when probe started
- `bundle_hash_computation_failed`: File read/enumeration error during hash computation
- `lost_foreground_during_probe`: App backgrounded during hash computation

## Client Validation Required

**Critical**: Receipt alone does not prove integrity. External validator MUST:

1. **Nonce freshness**: Verify challenge nonce was generated for this specific test run, not reused
2. **Expected digest**: Compare `installed_bundle_sha256` against independently computed expected hash from build-for-testing artifacts or frozen test build
3. **Signature coverage**: Ensure expected hash includes all `.app` bundle bytes including `_CodeSignature/` and `embedded.mobileprovision`
4. **Staleness detection**: Reject receipts where expected hash was computed from stale/outdated build artifacts

## Comparison to Default Simulator Collector

The existing `ios_fast_traverse` default evidence collector is **simulator-only** (`simctl` based). These templates are designed for **physical device** scenarios where `simctl` is unavailable. They do NOT upgrade or replace the simulator collector.

## Build Configuration

### DEBUG Configuration
Full implementation included. Probe is active when launch args provide challenge.

### Release Configuration
Consider excluding implementation methods entirely using preprocessor guards to ensure zero runtime overhead:

```objective-c
#if !DEBUG
// Empty stub - probe never active in Release
+ (void)load {}
#endif
```

Templates include `#if DEBUG` guards to prevent accidental Release activation.

## Limitations Summary

- **Shared core host-validated**: macOS CLI harness validated against `ios_evidence_protocol.py` (9/9 fixtures)
- **iOS probe NOT device-tested**: Refactored templates compile successfully but not tested on physical device
- **Compile-tested only**: No runtime device testing, no fault injection validation
- **No Swift/XCTest examples**: Integration assumes Objective-C knowledge
- **Manual wiring**: No automatic installer, no runtime protocol registration, no skill command integration
- **Single-launch only**: Not suitable for continuous monitoring or per-operation verification

## Host-Side Validation

**Portable regression driver**: `test_bundle_hash_core.py`
- Darwin-only (explicit skip on non-Darwin platforms)
- Locates and imports UNMODIFIED `ios_evidence_protocol.py` from canonical repo
- Always compiles current shared core source (no cached binaries)
- Tests all 9 required fixture cases
- Uses temporary directory (or `TEST_OUTPUT_DIR` environment variable)

Run validation:
```bash
cd migbot/skills/ios_fast_traverse/templates/physical-bundle-probe/
python3 test_bundle_hash_core.py
```

The driver validates that `I2HBundleHashCore` matches native Python `source_identity()` exactly.

## Source Provenance

Derived from:
- Generalized from internal physical device probe prototype
- Refactored to shared Foundation-only core + UIKit probe wrapper
- Generalized to I2H naming conventions for portable template distribution
- Hash algorithm matches: `migbot/skills/i2h-spec/scripts/ios_evidence_protocol.py::source_identity()`
- Post-loop enumeration error check added for fail-closed guarantee
- NSURLIsRegularFileKey check added to match Python path.is_file() contract
