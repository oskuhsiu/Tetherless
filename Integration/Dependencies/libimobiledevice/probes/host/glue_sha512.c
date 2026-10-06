#include <libimobiledevice-glue/sha.h>
#include "fixture.h"

size_t glue_context_size(void) { return sizeof(sha512_context); }
size_t glue_num_qwords_offset(void) { return offsetof(sha512_context, num_qwords); }
size_t glue_num_qwords_size(void) { return sizeof(((sha512_context *)0)->num_qwords); }

#define SHA_INIT sha512_init
#define SHA_UPDATE sha512_update
#define SHA_FINAL sha512_final
#define SHA_ONESHOT sha512
#define SHA_SUITE test_glue_sha512
#define SHA_NAME "glue public SHA512"
#define SHA_EXTRA_CHECK(context) REQUIRE((context)->num_qwords == 8, "glue num_qwords changed")
#include "sha_suite.inc"
