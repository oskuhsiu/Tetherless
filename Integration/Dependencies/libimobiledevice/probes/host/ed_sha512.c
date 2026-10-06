/* The Ed and glue headers deliberately never share a translation unit. */
#include "sha512.h"
#include "fixture.h"

size_t ed_context_size(void) { return sizeof(sha512_context); }

_Static_assert(sizeof(sha512_context) == offsetof(sha512_context, buf) + 128,
               "Ed context must end with buf, with no glue num_qwords member");

#define SHA_INIT tetherless_c_ed25519_sha512_init
#define SHA_UPDATE tetherless_c_ed25519_sha512_update
#define SHA_FINAL tetherless_c_ed25519_sha512_final
#define SHA_ONESHOT tetherless_c_ed25519_sha512
#define SHA_SUITE test_ed_sha512
#define SHA_NAME "Ed25519 namespaced SHA512"
#define SHA_EXTRA_CHECK(context) ((void)(context))
#include "sha_suite.inc"
