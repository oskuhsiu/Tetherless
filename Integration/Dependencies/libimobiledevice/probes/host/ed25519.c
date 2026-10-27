#include "ed25519.h"
#include "fixture.h"

void test_ed25519(void) {
    /* RFC 8032 section 7.1 TEST 1: published seed, public key, empty message. */
    static const char seed_hex[] =
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60";
    static const char public_hex[] =
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a";
    static const char signature_hex[] =
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b";
    static const unsigned char empty[] = "";
    static const unsigned char changed_message[] = "x";
    static const unsigned char scalar_message[] = "tetherless public add_scalar fixture";
    struct guarded32 seed, public_key, public_only, scalar;
    struct guarded64 private_key, private_only, signature, again;
    unsigned char original_public[32], original_private[64];
    size_t i;

    memset(&seed, GUARD_VALUE, sizeof(seed));
    memset(&public_key, GUARD_VALUE, sizeof(public_key));
    memset(&private_key, GUARD_VALUE, sizeof(private_key));
    memset(&signature, GUARD_VALUE, sizeof(signature));
    memset(&again, GUARD_VALUE, sizeof(again));
    decode_hex(seed_hex, seed.bytes, sizeof(seed.bytes));
    ed25519_create_keypair(public_key.bytes, private_key.bytes, seed.bytes);
    require_guards(seed.before, seed.after);
    require_guards(public_key.before, public_key.after);
    require_guards(private_key.before, private_key.after);
    require_hex(seed.bytes, sizeof(seed.bytes), seed_hex);
    require_hex(public_key.bytes, sizeof(public_key.bytes), public_hex);
    memcpy(original_public, public_key.bytes, sizeof(original_public));
    memcpy(original_private, private_key.bytes, sizeof(original_private));

    ed25519_sign(signature.bytes, empty, 0, public_key.bytes, private_key.bytes);
    require_guards(signature.before, signature.after);
    require_hex(signature.bytes, sizeof(signature.bytes), signature_hex);
    REQUIRE(ed25519_verify(signature.bytes, empty, 0, public_key.bytes) == 1,
            "RFC8032 signature did not verify");
    ed25519_sign(again.bytes, empty, 0, public_key.bytes, private_key.bytes);
    REQUIRE(memcmp(signature.bytes, again.bytes, sizeof(signature.bytes)) == 0,
            "Ed25519 signing is not deterministic");
    require_guards(again.before, again.after);
    REQUIRE(ed25519_verify(signature.bytes, changed_message, sizeof(changed_message) - 1,
                           public_key.bytes) == 0, "tampered message accepted");
    signature.bytes[0] ^= 1;
    REQUIRE(ed25519_verify(signature.bytes, empty, 0, public_key.bytes) == 0,
            "tampered signature accepted");
    signature.bytes[0] ^= 1;
    public_key.bytes[0] ^= 1;
    REQUIRE(ed25519_verify(signature.bytes, empty, 0, public_key.bytes) == 0,
            "tampered public key accepted");
    public_key.bytes[0] ^= 1;
    REQUIRE(memcmp(original_private, private_key.bytes, sizeof(original_private)) == 0,
            "sign/verify mutated private key");
    puts("PASS Ed25519 RFC8032 TEST 1: keypair/sign/verify, deterministic signature, 3 tamper rejections");

    memset(&scalar, GUARD_VALUE, sizeof(scalar));
    for (i = 0; i < sizeof(scalar.bytes); ++i) scalar.bytes[i] = (unsigned char)(3 * i + 1);
    scalar.bytes[31] &= 127;
    public_only = public_key;
    private_only = private_key;
    ed25519_add_scalar(public_key.bytes, private_key.bytes, scalar.bytes);
    ed25519_add_scalar(public_only.bytes, NULL, scalar.bytes);
    ed25519_add_scalar(NULL, private_only.bytes, scalar.bytes);
    REQUIRE(memcmp(public_key.bytes, original_public, sizeof(original_public)) != 0,
            "add_scalar did not change public key");
    REQUIRE(memcmp(public_key.bytes, public_only.bytes, sizeof(public_key.bytes)) == 0,
            "public-only add_scalar disagrees with keypair add_scalar");
    REQUIRE(memcmp(private_key.bytes, private_only.bytes, sizeof(private_key.bytes)) == 0,
            "private-only add_scalar disagrees with keypair add_scalar");
    ed25519_sign(signature.bytes, scalar_message, sizeof(scalar_message) - 1,
                 public_key.bytes, private_key.bytes);
    ed25519_sign(again.bytes, scalar_message, sizeof(scalar_message) - 1,
                 public_only.bytes, private_only.bytes);
    REQUIRE(memcmp(signature.bytes, again.bytes, sizeof(signature.bytes)) == 0,
            "separately adjusted keys disagree when signing");
    REQUIRE(ed25519_verify(signature.bytes, scalar_message, sizeof(scalar_message) - 1,
                           public_key.bytes) == 1, "adjusted-key signature did not verify");
    REQUIRE(ed25519_verify(signature.bytes, scalar_message, sizeof(scalar_message) - 1,
                           original_public) == 0, "original key accepted adjusted-key signature");
    signature.bytes[63] ^= 1;
    REQUIRE(ed25519_verify(signature.bytes, scalar_message, sizeof(scalar_message) - 1,
                           public_key.bytes) == 0, "tampered adjusted-key signature accepted");
    require_guards(seed.before, seed.after);
    require_guards(scalar.before, scalar.after);
    require_guards(public_key.before, public_key.after);
    require_guards(public_only.before, public_only.after);
    require_guards(private_key.before, private_key.after);
    require_guards(private_only.before, private_only.after);
    require_guards(signature.before, signature.after);
    require_guards(again.before, again.after);
    puts("PASS Ed25519 add_scalar: deterministic scalar, combined/separate key agreement, sign/verify, tamper rejection, guards");
}
