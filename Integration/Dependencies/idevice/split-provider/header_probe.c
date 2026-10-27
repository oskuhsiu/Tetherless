/* Compile with the selected target SDK and both verified include spellings.
 * This checks header configuration only; it does not execute a provider. */
#include <OpenSSL/configuration.h>
#include <openssl/opensslv.h>
#include <openssl/ssl.h>

#if OPENSSL_VERSION_NUMBER != 0x30600020L
#error Unexpected OpenSSL header version
#endif
#ifndef OPENSSL_NO_SSLKEYLOG
#error Selected headers do not disable SSL key logging
#endif
#ifndef OPENSSL_NO_DYNAMIC_ENGINE
#error Selected headers do not disable dynamic engines
#endif
#ifdef OPENSSL_NO_PSK
#error Selected headers disable the required PSK API
#endif
#ifdef OPENSSL_NO_TLS1_2
#error Selected headers disable the required TLS 1.2 protocol
#endif

int tetherless_openssl_header_probe(void) { return OPENSSL_VERSION_MAJOR; }
/* Compile-time declaration/type check only. Do not link or execute this probe. */
void (*tetherless_openssl_psk_api_probe(void))(SSL_CTX *, SSL_psk_client_cb_func) {
    return &SSL_CTX_set_psk_client_callback;
}
