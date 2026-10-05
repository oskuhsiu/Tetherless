// Ownership/cancellation spy. No sockets, authentication, file writes or logging.
#include "IDevice.h"
#include <pthread.h>
#include <stdlib.h>
#include <string.h>
struct TetherlessPairingValidationHandle { bool cancelled; };
static pthread_mutex_t lock = PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t ready = PTHREAD_COND_INITIALIZER;
static bool holding;
static unsigned started, cancels, frees, active, invalid_input, freed_active;
void tetherless_spy_reset(bool hold) {
    pthread_mutex_lock(&lock);
    holding = hold; started = cancels = frees = active = invalid_input = freed_active = 0;
    pthread_mutex_unlock(&lock);
}
void tetherless_spy_release(void) {
    pthread_mutex_lock(&lock); holding = false; pthread_cond_broadcast(&ready); pthread_mutex_unlock(&lock);
}
#define COUNT(name) unsigned tetherless_spy_##name(void) { pthread_mutex_lock(&lock); unsigned n = name; pthread_mutex_unlock(&lock); return n; }
COUNT(started) COUNT(cancels) COUNT(frees) COUNT(active) COUNT(invalid_input)
unsigned tetherless_spy_freed_while_active(void) { pthread_mutex_lock(&lock); unsigned n = freed_active; pthread_mutex_unlock(&lock); return n; }
TetherlessPairingValidationHandle *tetherless_pairing_validation_new(void) { return calloc(1, sizeof(TetherlessPairingValidationHandle)); }
bool tetherless_pairing_validation_cancel(const TetherlessPairingValidationHandle *handle) {
    pthread_mutex_lock(&lock); cancels++; ((TetherlessPairingValidationHandle *)handle)->cancelled = true; pthread_mutex_unlock(&lock); return true;
}
void tetherless_pairing_validation_free(TetherlessPairingValidationHandle *handle) {
    pthread_mutex_lock(&lock); frees++; if (active) freed_active++; pthread_mutex_unlock(&lock); free(handle);
}
TetherlessPairingValidationResult tetherless_pairing_validate_staged(
    const uint8_t *record, uintptr_t record_len, const uint8_t *endpoint, uintptr_t endpoint_len,
    const TetherlessPairingValidationHandle *handle, const uint8_t *bundle, uintptr_t bundle_len,
    const uint8_t *path, uintptr_t path_len, const uint8_t *expected, uintptr_t expected_len, uint32_t timeout_ms) {
    pthread_mutex_lock(&lock); started++; active++;
    const char *prefix = "Library/TetherlessPairingValidation/";
    const size_t prefix_len = strlen(prefix);
    bool valid = record && record_len > 0 && record_len <= 4096 && endpoint && endpoint_len > 0 && endpoint_len <= 128 &&
        bundle && bundle_len > 0 && bundle_len <= 255 && path && path_len == prefix_len + 64 + 10 &&
        !memcmp(path, prefix, prefix_len) && !memcmp(path + path_len - 10, ".challenge", 10) &&
        expected && expected_len == 32 && timeout_ms > 0 && timeout_ms <= 10000;
    if (valid) {
        for (size_t i = prefix_len; i < prefix_len + 64; i++) {
            if (!((path[i] >= '0' && path[i] <= '9') || (path[i] >= 'a' && path[i] <= 'f'))) valid = false;
        }
    }
    if (!valid) invalid_input++;
    while (holding) pthread_cond_wait(&ready, &lock);
    bool cancelled = handle->cancelled;
    active--; pthread_mutex_unlock(&lock);
    return !valid ? TetherlessPairingValidationInvalidArgument : cancelled ? TetherlessPairingValidationCancelled : TetherlessPairingValidationOk;
}
