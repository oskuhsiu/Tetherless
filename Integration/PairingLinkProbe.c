// SPDX-License-Identifier: AGPL-3.0-only
// Compile/link evidence only. This executable is NEVER run by the probe.
#include "idevice.h"

// Exact typed references reject declaration drift. Volatile storage and linker
// roots prevent dead-stripping from making missing functions look available.
static struct PairableHostCancel *(*volatile make_cancel)(void) = pairable_host_cancel_new;
static void (*volatile signal_cancel)(const struct PairableHostCancel *) = pairable_host_cancel_signal;
static void (*volatile free_cancel)(struct PairableHostCancel *) = pairable_host_cancel_free;
static struct IdeviceFfiError *(*volatile accept_host)(
    const char *, const char *, uint16_t,
    void (*)(const char *, void *), void *, const struct PairableHostCancel *,
    uint8_t *, struct RpPairingPeerDeviceC **, struct RpPairingFileHandle **
) = pairable_host_accept;

int main(void) {
    // Even accidental execution only reads addresses; it calls no native API.
    return make_cancel == 0 || signal_cancel == 0 || free_cancel == 0 || accept_host == 0;
}
