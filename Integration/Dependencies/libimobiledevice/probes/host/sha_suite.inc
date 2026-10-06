/* Included independently after each library's real context declaration. */
struct guarded_context {
    unsigned char before[GUARD_BYTES];
    sha512_context context;
    unsigned char after[GUARD_BYTES];
};

_Static_assert(offsetof(struct guarded_context, after) ==
               offsetof(struct guarded_context, context) + sizeof(sha512_context),
               "context canary must be immediately after the real context");

static void check_context(const struct guarded_context *box) {
    require_guards(box->before, box->after);
    SHA_EXTRA_CHECK(&box->context);
}

static void check_vector(const unsigned char *message, size_t length, const char *digest) {
    static const size_t chunks[] = {1, 111, 2, 127, 128, 129, 17, 1024, 3};
    struct guarded_context box;
    struct guarded64 output;
    size_t mode, offset, iteration, count;

    memset(&output, GUARD_VALUE, sizeof(output));
    REQUIRE(SHA_ONESHOT(message, length, output.bytes) == 0, "one-shot hash failed");
    require_guards(output.before, output.after);
    require_hex(output.bytes, sizeof(output.bytes), digest);

    /* One update and irregular chunks both include explicit zero-byte updates. */
    for (mode = 0; mode < 2; ++mode) {
        memset(&box, GUARD_VALUE, sizeof(box));
        memset(&output, GUARD_VALUE, sizeof(output));
        REQUIRE(SHA_INIT(&box.context) == 0, "hash init failed");
        check_context(&box);
        REQUIRE(SHA_UPDATE(&box.context, message, 0) == 0, "zero update failed");
        check_context(&box);
        offset = iteration = 0;
        while (offset < length) {
            count = mode == 0 ? length : chunks[iteration++ % (sizeof(chunks) / sizeof(chunks[0]))];
            if (count > length - offset) count = length - offset;
            REQUIRE(SHA_UPDATE(&box.context, message + offset, count) == 0, "hash update failed");
            check_context(&box);
            offset += count;
        }
        REQUIRE(SHA_UPDATE(&box.context, message, 0) == 0, "trailing zero update failed");
        check_context(&box);
        REQUIRE(SHA_FINAL(&box.context, output.bytes) == 0, "hash final failed");
        check_context(&box);
        require_guards(output.before, output.after);
        require_hex(output.bytes, sizeof(output.bytes), digest);
    }
}

void SHA_SUITE(void) {
    static const unsigned char long_message[] =
        "abcdefghbcdefghicdefghijdefghijkefghijklfghijklmghijklmn"
        "hijklmnoijklmnopjklmnopqklmnopqrlmnopqrsmnopqrstnopqrstu";
    static unsigned char million_a[1000000];
    check_vector((const unsigned char *)"", 0,
        "cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce"
        "47d0d13c5d85f2b0ff8318d2877eec2f63b931bd47417a81a538327af927da3e");
    check_vector((const unsigned char *)"abc", 3,
        "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
        "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f");
    REQUIRE(sizeof(long_message) - 1 == 112, "long SHA vector length changed");
    check_vector(long_message, sizeof(long_message) - 1,
        "8e959b75dae313da8cf4f72814fc143f8f7779c6eb9f7fa17299aeadb6889018"
        "501d289e4900f7e4331b99dec4b5433ac7d329eeb6dd26545e96e55b874be909");
    memset(million_a, 'a', sizeof(million_a));
    check_vector(million_a, sizeof(million_a),
        "e718483d0ce769644e2e42c7bc15b4638e1f98b13b2044285632a803afa973eb"
        "de0ff244877ea60a4cb0432ce577c31beb009c5c2c49aa2e4eadb217ad8cc09b");
    printf("PASS %s: 4 known answers x one-shot/single-update/chunked; context/output guards\n", SHA_NAME);
}
