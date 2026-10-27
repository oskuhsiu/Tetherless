#ifndef TETHERLESS_HOST_CRYPTO_FIXTURE_H
#define TETHERLESS_HOST_CRYPTO_FIXTURE_H

#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Public test vectors only. Never pass device credentials to this executable. */
#define GUARD_BYTES 32
#define GUARD_VALUE 0xa5

#define REQUIRE(condition, detail) do { \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, (detail)); \
        exit(1); \
    } \
} while (0)

struct guarded32 {
    unsigned char before[GUARD_BYTES], bytes[32], after[GUARD_BYTES];
};
struct guarded64 {
    unsigned char before[GUARD_BYTES], bytes[64], after[GUARD_BYTES];
};

void require_guards(const unsigned char *before, const unsigned char *after);
void decode_hex(const char *text, unsigned char *output, size_t length);
void require_hex(const unsigned char *actual, size_t length, const char *expected);
void test_ed_sha512(void);
void test_glue_sha512(void);
void test_ed25519(void);
size_t ed_context_size(void);
size_t glue_context_size(void);
size_t glue_num_qwords_offset(void);
size_t glue_num_qwords_size(void);

#endif
