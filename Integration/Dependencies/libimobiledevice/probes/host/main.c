#include "fixture.h"

void require_guards(const unsigned char *before, const unsigned char *after) {
    size_t i;
    for (i = 0; i < GUARD_BYTES; ++i) {
        REQUIRE(before[i] == GUARD_VALUE, "leading guard overwritten");
        REQUIRE(after[i] == GUARD_VALUE, "trailing guard overwritten");
    }
}

static unsigned char hex_digit(char c) {
    if (c >= '0' && c <= '9') return (unsigned char)(c - '0');
    if (c >= 'a' && c <= 'f') return (unsigned char)(c - 'a' + 10);
    REQUIRE(0, "invalid hexadecimal test vector");
    return 0;
}

void decode_hex(const char *text, unsigned char *output, size_t length) {
    size_t i;
    REQUIRE(strlen(text) == length * 2, "incorrect test vector length");
    for (i = 0; i < length; ++i)
        output[i] = (unsigned char)((hex_digit(text[2 * i]) << 4) |
                                   hex_digit(text[2 * i + 1]));
}

void require_hex(const unsigned char *actual, size_t length, const char *expected) {
    unsigned char decoded[64];
    REQUIRE(length <= sizeof(decoded), "test comparison buffer too small");
    decode_hex(expected, decoded, length);
    REQUIRE(memcmp(actual, decoded, length) == 0, "known-answer mismatch");
}

int main(void) {
    size_t ed_size = ed_context_size(), glue_size = glue_context_size();
    REQUIRE(ed_size < glue_size, "the two real SHA contexts must differ in size");
    REQUIRE(glue_num_qwords_offset() == ed_size,
            "glue num_qwords must follow the complete smaller Ed context");
    REQUIRE(glue_num_qwords_offset() + glue_num_qwords_size() <= glue_size,
            "glue num_qwords must be inside its own context");
    printf("CONTEXT_SIZES ed=%zu glue=%zu glue_num_qwords_offset=%zu glue_num_qwords_size=%zu\n",
           ed_size, glue_size, glue_num_qwords_offset(), glue_num_qwords_size());
    test_ed_sha512();
    test_glue_sha512();
    test_ed25519();
    puts("PASS all host crypto fixtures");
    return 0;
}
