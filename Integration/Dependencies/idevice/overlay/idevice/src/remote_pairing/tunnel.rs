// Jackson Coxson
//! TLS-PSK tunnel connect helpers for remote pairing.
//!
//! These functions combine TLS-PSK handshake + CDTunnel handshake into a single call.
//! The CDTunnel protocol itself lives in [`crate::tunnel`].

use tracing::debug;

use crate::{IdeviceError, ReadWrite};

// Re-export for backwards compatibility
pub use crate::tunnel::{CdTunnel, TunnelInfo};

const CDTUNNEL_MAGIC: &[u8] = b"CDTunnel";
const DEFAULT_MTU: u16 = 16000;

/// Wraps a `tokio::net::TcpStream` with TLS-PSK using a pure-Rust implementation
/// and performs the CDTunnel handshake, returning a ready-to-use tunnel.
///
/// `encryption_key` is the key from `RemotePairingClient::encryption_key()`.
///
/// This uses a built-in TLS 1.2 PSK-AES256-CBC-SHA384 implementation with no
/// external TLS library dependency.
pub async fn connect_tls_psk_tunnel_native<S: ReadWrite>(
    stream: S,
    encryption_key: &[u8],
) -> Result<CdTunnel<super::tls_psk::TlsPskStream<S>>, IdeviceError> {
    let mut tls_stream = super::tls_psk::tls_psk_handshake(stream, encryption_key).await?;
    debug!("Native TLS-PSK handshake complete");

    // CDTunnel handshake over TLS using the record-level API
    let request = serde_json::json!({
        "type": "clientHandshakeRequest",
        "mtu": DEFAULT_MTU
    });
    let body = serde_json::to_vec(&request)?;

    let mut pkt = Vec::new();
    pkt.extend_from_slice(CDTUNNEL_MAGIC);
    pkt.extend_from_slice(&(body.len() as u16).to_be_bytes());
    pkt.extend_from_slice(&body);
    tls_stream.write_app_data(&pkt).await?;

    debug!("Sent CDTunnel handshake request via TLS");

    let response_data = tls_stream.read_app_data().await?;
    if response_data.len() < CDTUNNEL_MAGIC.len() + 2 {
        return Err(IdeviceError::UnexpectedResponse(
            "CDTunnel handshake response too short".into(),
        ));
    }
    if &response_data[..CDTUNNEL_MAGIC.len()] != CDTUNNEL_MAGIC {
        return Err(IdeviceError::UnexpectedResponse(
            "CDTunnel handshake response missing magic header".into(),
        ));
    }
    let body_len = u16::from_be_bytes([
        response_data[CDTUNNEL_MAGIC.len()],
        response_data[CDTUNNEL_MAGIC.len() + 1],
    ]) as usize;
    let body_start = CDTUNNEL_MAGIC.len() + 2;
    let response_body = &response_data[body_start..body_start + body_len];

    let response: serde_json::Value = serde_json::from_slice(response_body)
        .map_err(|e| IdeviceError::InternalError(e.to_string()))?;

    debug!("CDTunnel handshake response: {response:#?}");

    let client_params =
        response
            .get("clientParameters")
            .ok_or(IdeviceError::UnexpectedResponse(
                "missing clientParameters in CDTunnel response".into(),
            ))?;

    let client_address = client_params
        .get("address")
        .and_then(|a| a.as_str())
        .ok_or(IdeviceError::UnexpectedResponse(
            "missing client address in CDTunnel response".into(),
        ))?
        .to_string();

    let mtu = client_params
        .get("mtu")
        .and_then(|m| m.as_u64())
        .unwrap_or(1500) as u16;

    let server_address = response
        .get("serverAddress")
        .and_then(|a| a.as_str())
        .ok_or(IdeviceError::UnexpectedResponse(
            "missing server address in CDTunnel response".into(),
        ))?
        .to_string();

    let server_rsd_port = response
        .get("serverRSDPort")
        .and_then(|p| p.as_u64())
        .unwrap_or(0) as u16;

    let info = TunnelInfo {
        client_address,
        netmask: client_params
            .get("netmask")
            .and_then(|n| n.as_str())
            .unwrap_or("")
            .to_string(),
        server_address,
        mtu,
        server_rsd_port,
    };

    debug!("CDTunnel established: {info:?}");

    Ok(CdTunnel {
        inner: tls_stream,
        info,
    })
}

/// Wraps a `tokio::net::TcpStream` with TLS-PSK using OpenSSL and performs
/// the CDTunnel handshake, returning a ready-to-use tunnel.
///
/// `encryption_key` is the key from `RemotePairingClient::encryption_key()`.
///
/// Requires the `openssl` feature. Consider using [`connect_tls_psk_tunnel_native`]
/// instead, which has no external dependency.
#[cfg(feature = "openssl")]
pub async fn connect_tls_psk_tunnel<S: ReadWrite>(
    stream: S,
    encryption_key: &[u8],
) -> Result<CdTunnel<tokio_openssl::SslStream<S>>, IdeviceError> {
    use openssl::ssl::{SslConnector, SslMethod, SslVerifyMode};

    let psk = encryption_key.to_vec();

    let mut builder = SslConnector::builder(SslMethod::tls_client())
        .map_err(|e| IdeviceError::InternalError(format!("SslConnector::builder: {e}")))?;

    builder.set_verify(SslVerifyMode::NONE);
    builder
        .set_cipher_list(
            "PSK-AES128-CBC-SHA:PSK-AES256-CBC-SHA:PSK-AES128-CBC-SHA256:PSK-AES256-CBC-SHA384",
        )
        .map_err(|e| IdeviceError::InternalError(format!("set_cipher_list: {e}")))?;
    builder.set_psk_client_callback(move |_ssl, _hint, identity, psk_out| {
        if !identity.is_empty() {
            identity[0] = 0;
        }
        let len = psk.len().min(psk_out.len());
        psk_out[..len].copy_from_slice(&psk[..len]);
        Ok(len)
    });

    builder
        .set_min_proto_version(Some(openssl::ssl::SslVersion::TLS1_2))
        .map_err(|e| IdeviceError::InternalError(e.to_string()))?;
    builder
        .set_max_proto_version(Some(openssl::ssl::SslVersion::TLS1_2))
        .map_err(|e| IdeviceError::InternalError(e.to_string()))?;

    let ssl_connector = builder.build();
    let mut conf = ssl_connector
        .configure()
        .map_err(|e| IdeviceError::InternalError(e.to_string()))?;
    conf.set_verify_hostname(false);
    conf.set_use_server_name_indication(false);
    let ssl = conf
        .into_ssl("localhost")
        .map_err(|e| IdeviceError::InternalError(e.to_string()))?;

    let mut tls_stream = tokio_openssl::SslStream::new(ssl, stream)
        .map_err(|e| IdeviceError::InternalError(e.to_string()))?;

    if let Err(e) = std::pin::Pin::new(&mut tls_stream).connect().await {
        let ssl_errors = openssl::error::ErrorStack::get();
        let msg = format!("TLS-PSK handshake failed: {e} (SSL errors: {ssl_errors:?})");
        tracing::error!("{msg}");
        return Err(IdeviceError::InternalError(msg));
    }

    debug!("TLS-PSK handshake complete");

    CdTunnel::handshake(tls_stream).await
}

// Opt-in only: existing constructors and default feature selection are unchanged.
#[cfg(feature = "openssl")]
mod staged_openssl {
    use super::*;
    use openssl::ssl::{Ssl, SslContextBuilder, SslMethod, SslMode,
        SslOptions, SslSessionCacheMode, SslVerifyMode, SslVersion};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    const PSK_BYTES: usize = 32;
    const MAX_CDTUNNEL_BODY: usize = 4096;
    const PSK_SUITES: &str = "PSK-AES256-CBC-SHA384:PSK-AES128-CBC-SHA";

    fn rejected() -> IdeviceError {
        IdeviceError::UnexpectedResponse("staged OpenSSL tunnel rejected".into())
    }

    fn copy_psk(psk: &[u8; PSK_BYTES], identity: &mut [u8], output: &mut [u8]) -> usize {
        // OpenSSL treats zero as a failed PSK callback. Never truncate the key
        // or omit the identity terminator as the legacy convenience route can.
        if identity.is_empty() || output.len() < PSK_BYTES { return 0; }
        identity[0] = 0; // Existing Apple RP protocol uses an empty identity.
        output[..PSK_BYTES].copy_from_slice(psk);
        PSK_BYTES
    }

    fn client_context(psk: [u8; PSK_BYTES]) -> Result<SslContextBuilder, IdeviceError> {
        // Use the safe OpenSSL context API rather than SslConnector's general
        // web defaults, which enable partial writes and load certificate paths.
        // TLS records, CBC padding/MAC and Finished remain entirely OpenSSL's.
        let mut context = SslContextBuilder::new(SslMethod::tls_client()).map_err(|_| rejected())?;
        context.set_min_proto_version(Some(SslVersion::TLS1_2)).map_err(|_| rejected())?;
        context.set_max_proto_version(Some(SslVersion::TLS1_2)).map_err(|_| rejected())?;
        context.set_cipher_list(PSK_SUITES).map_err(|_| rejected())?;
        context.set_options(SslOptions::NO_COMPRESSION | SslOptions::NO_RENEGOTIATION | SslOptions::NO_TICKET);
        context.set_session_cache_mode(SslSessionCacheMode::OFF);
        context.set_read_ahead(false);
        // No certificate-bearing suite is offered. PSK authentication, record
        // MAC/padding and Finished are still checked by the library; NONE only
        // disables certificate verification. No hostname/SNI is configured.
        context.set_verify(SslVerifyMode::NONE);
        let modes = context.set_mode(SslMode::ACCEPT_MOVING_WRITE_BUFFER | SslMode::AUTO_RETRY);
        if modes.contains(SslMode::ENABLE_PARTIAL_WRITE) { return Err(rejected()); }
        // jktcp recreates the same packet Vec after Pending. Moving buffers are
        // allowed, but OpenSSL still requires equal bytes/length. Partial writes
        // stay disabled, so a successful write accepts an entire packet once.
        context.set_psk_client_callback(move |_ssl, _hint, identity, output| {
            Ok(copy_psk(&psk, identity, output))
        });
        // No key logging, session import/export, permissive verification hook,
        // security-level lowering, certificate fallback or reconnect is used.
        Ok(context)
    }

    /// OpenSSL-only staged PSK handshake. The caller must own a finite raw-byte /
    /// poll budget and whole-operation deadline; OpenSSL by itself is not an
    /// aggregate memory/time budget. Dropping this future owns/drops the stream.
    pub async fn tls_psk_handshake_openssl_staged<S: ReadWrite>(
        stream: S, encryption_key: &[u8],
    ) -> Result<tokio_openssl::SslStream<S>, IdeviceError> {
        let psk: [u8; PSK_BYTES] = encryption_key.try_into().map_err(|_| rejected())?;
        let context = client_context(psk)?.build();
        let ssl = Ssl::new(&context).map_err(|_| rejected())?;
        let mut stream = tokio_openssl::SslStream::new(ssl, stream).map_err(|_| rejected())?;
        std::pin::Pin::new(&mut stream).connect().await.map_err(|_| rejected())?;
        // Defense in depth against unexpected library/configuration behavior.
        if stream.ssl().version2() != Some(SslVersion::TLS1_2)
            || stream.ssl().session_reused()
            || !matches!(stream.ssl().current_cipher().map(|cipher| cipher.name()),
                Some("PSK-AES256-CBC-SHA384" | "PSK-AES128-CBC-SHA"))
        { return Err(rejected()); }
        Ok(stream)
    }

    /// OpenSSL PSK TLS followed by checked CDTunnel framing. Requires the caller's
    /// raw transport budget and deadline across acquisition and service use.
    pub async fn connect_tls_psk_tunnel_openssl_bounded<S: ReadWrite>(
        stream: S, encryption_key: &[u8],
    ) -> Result<CdTunnel<tokio_openssl::SslStream<S>>, IdeviceError> {
        let stream = tls_psk_handshake_openssl_staged(stream, encryption_key).await?;
        cdtunnel_handshake(stream).await
    }

    async fn cdtunnel_handshake<S: ReadWrite>(mut stream: S) -> Result<CdTunnel<S>, IdeviceError> {
        let body = serde_json::to_vec(&serde_json::json!({
            "type": "clientHandshakeRequest", "mtu": DEFAULT_MTU
        })).map_err(|_| rejected())?;
        stream.write_all(CDTUNNEL_MAGIC).await?;
        stream.write_all(&(body.len() as u16).to_be_bytes()).await?;
        stream.write_all(&body).await?;
        stream.flush().await?;
        let mut header = [0; 10];
        stream.read_exact(&mut header).await?;
        if &header[..8] != CDTUNNEL_MAGIC { return Err(rejected()); }
        let length = u16::from_be_bytes([header[8], header[9]]) as usize;
        if length == 0 || length > MAX_CDTUNNEL_BODY { return Err(rejected()); }
        let mut response = [0; MAX_CDTUNNEL_BODY];
        stream.read_exact(&mut response[..length]).await?;
        let info = tunnel_info(&response[..length])?;
        Ok(CdTunnel { inner: stream, info })
    }

    fn tunnel_info(bytes: &[u8]) -> Result<TunnelInfo, IdeviceError> {
        use std::net::IpAddr;
        if bytes.is_empty() || bytes.len() > MAX_CDTUNNEL_BODY { return Err(rejected()); }
        let response: serde_json::Value = serde_json::from_slice(bytes).map_err(|_| rejected())?;
        let params = response.get("clientParameters").ok_or_else(rejected)?;
        let parse_ip = |value: Option<&serde_json::Value>| -> Result<IpAddr, IdeviceError> {
            value.and_then(|v| v.as_str()).filter(|s| s.len() <= 45)
                .and_then(|s| s.parse().ok()).ok_or_else(rejected)
        };
        let client = parse_ip(params.get("address"))?;
        let server = parse_ip(response.get("serverAddress"))?;
        if client.is_ipv4() != server.is_ipv4() || client.is_unspecified() || server.is_unspecified()
            || client.is_multicast() || server.is_multicast() || client == server
        { return Err(rejected()); }
        let mtu = params.get("mtu").and_then(|v| v.as_u64())
            .and_then(|v| u16::try_from(v).ok()).filter(|v| (1280..=DEFAULT_MTU).contains(v))
            .ok_or_else(rejected)?;
        let port = response.get("serverRSDPort").and_then(|v| v.as_u64())
            .and_then(|v| u16::try_from(v).ok()).filter(|v| *v != 0).ok_or_else(rejected)?;
        Ok(TunnelInfo { client_address: client.to_string(), server_address: server.to_string(),
            netmask: String::new(), mtu, server_rsd_port: port })
    }

    #[cfg(test)]
    mod tests {
        use super::*;
        #[test]
        fn psk_callback_never_truncates_or_omits_identity_terminator() {
            let key = [0x35; PSK_BYTES];
            let mut identity = [0xaa; 4];
            let mut output = [0xbb; PSK_BYTES + 1];
            assert_eq!(copy_psk(&key, &mut identity, &mut output), PSK_BYTES);
            assert_eq!(identity, [0, 0xaa, 0xaa, 0xaa]);
            assert_eq!(&output[..PSK_BYTES], &key);
            assert_eq!(output[PSK_BYTES], 0xbb);
            for length in 0..PSK_BYTES {
                let mut output = vec![0xbb; length];
                assert_eq!(copy_psk(&key, &mut identity, &mut output), 0);
                assert!(output.iter().all(|b| *b == 0xbb));
            }
            assert_eq!(copy_psk(&key, &mut [], &mut output), 0);
        }
        #[tokio::test]
        async fn cdtunnel_rejects_oversized_length_before_body_read() {
            let (client, mut peer) = tokio::io::duplex(4096);
            peer.write_all(b"CDTunnel").await.unwrap();
            peer.write_all(&4097u16.to_be_bytes()).await.unwrap();
            assert!(cdtunnel_handshake(client).await.is_err());
        }
        #[test]
        fn context_has_exact_protocol_and_disabled_expansion_features() {
            let mut context = client_context([0x35; PSK_BYTES]).unwrap();
            assert!(context.options().contains(SslOptions::NO_COMPRESSION | SslOptions::NO_RENEGOTIATION | SslOptions::NO_TICKET));
            assert_eq!(context.min_proto_version(), Some(SslVersion::TLS1_2));
            assert_eq!(context.max_proto_version(), Some(SslVersion::TLS1_2));
            let modes = context.set_mode(SslMode::empty());
            assert!(modes.contains(SslMode::ACCEPT_MOVING_WRITE_BUFFER));
            assert!(!modes.contains(SslMode::ENABLE_PARTIAL_WRITE));
        }
        #[test]
        fn cdtunnel_rejects_unchecked_mtu_port_and_addresses() {
            let valid = serde_json::json!({"clientParameters":{"address":"fd00::1","mtu":16000},
                "serverAddress":"fd00::2","serverRSDPort":58783});
            assert!(tunnel_info(&serde_json::to_vec(&valid).unwrap()).is_ok());
            for port in [0u64, 65536, u64::MAX] {
                let mut value = valid.clone(); value["serverRSDPort"] = port.into();
                assert!(tunnel_info(&serde_json::to_vec(&value).unwrap()).is_err());
            }
            for mtu in [0u64, 60, 1279, 16001, 65536, u64::MAX] {
                let mut value = valid.clone(); value["clientParameters"]["mtu"] = mtu.into();
                assert!(tunnel_info(&serde_json::to_vec(&value).unwrap()).is_err());
            }
            let mut value = valid; value["serverAddress"] = "127.0.0.1".into();
            assert!(tunnel_info(&serde_json::to_vec(&value).unwrap()).is_err());
        }
    }
}

#[cfg(feature = "openssl")]
pub use staged_openssl::{connect_tls_psk_tunnel_openssl_bounded, tls_psk_handshake_openssl_staged};

#[cfg(all(test, feature = "openssl"))]
mod staged_openssl_fixtures {
    use super::*;
    use openssl::ssl::{Ssl, SslContextBuilder, SslMethod, SslOptions, SslSessionCacheMode, SslVersion};
    use std::{pin::Pin, task::{Context, Poll}, sync::{Arc, atomic::{AtomicBool, Ordering}}};
    use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt, DuplexStream, ReadBuf};

    const KEY: [u8; 32] = [0x35; 32];
    #[derive(Debug)]
    struct Choppy<S> { inner: S, pause: bool, corrupt: Arc<AtomicBool> }
    impl<S: AsyncRead + Unpin> AsyncRead for Choppy<S> {
        fn poll_read(self: Pin<&mut Self>, cx: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<std::io::Result<()>> {
            Pin::new(&mut self.get_mut().inner).poll_read(cx, output)
        }
    }
    impl<S: AsyncWrite + Unpin> AsyncWrite for Choppy<S> {
        fn poll_write(self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<std::io::Result<usize>> {
            let this = self.get_mut();
            if this.pause { this.pause = false; cx.waker().wake_by_ref(); return Poll::Pending; }
            this.pause = true;
            let count = bytes.len().min(23);
            let mut part = bytes[..count].to_vec();
            // Transport corruption only; no record parser or alternate crypto.
            if this.corrupt.load(Ordering::SeqCst) && !part.is_empty() { part[count - 1] ^= 1; }
            Pin::new(&mut this.inner).poll_write(cx, &part)
        }
        fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
            Pin::new(&mut self.get_mut().inner).poll_flush(cx)
        }
        fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
            Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
        }
    }
    async fn server<S: ReadWrite>(stream: S, key: [u8; 32])
        -> Result<tokio_openssl::SslStream<S>, ()>
    {
        let mut context = SslContextBuilder::new(SslMethod::tls_server()).map_err(|_| ())?;
        context.set_min_proto_version(Some(SslVersion::TLS1_2)).map_err(|_| ())?;
        context.set_max_proto_version(Some(SslVersion::TLS1_2)).map_err(|_| ())?;
        context.set_cipher_list("PSK-AES256-CBC-SHA384").map_err(|_| ())?;
        context.set_options(SslOptions::NO_COMPRESSION | SslOptions::NO_RENEGOTIATION | SslOptions::NO_TICKET);
        context.set_session_cache_mode(SslSessionCacheMode::OFF);
        context.set_psk_server_callback(move |_ssl, identity, output| {
            if identity != Some(b"".as_slice()) || output.len() < key.len() { return Ok(0); }
            output[..key.len()].copy_from_slice(&key); Ok(key.len())
        });
        let ssl = Ssl::new(&context.build()).map_err(|_| ())?;
        let mut stream = tokio_openssl::SslStream::new(ssl, stream).map_err(|_| ())?;
        Pin::new(&mut stream).accept().await.map_err(|_| ())?;
        Ok(stream)
    }
    fn pair() -> (Choppy<DuplexStream>, Choppy<DuplexStream>, Arc<AtomicBool>) {
        let (client, peer) = tokio::io::duplex(256);
        let tamper = Arc::new(AtomicBool::new(false));
        (Choppy { inner: client, pause: false, corrupt: Arc::new(AtomicBool::new(false)) },
         Choppy { inner: peer, pause: false, corrupt: tamper.clone() }, tamper)
    }
    #[tokio::test]
    async fn standard_psk_handshake_and_moving_packet_retries_are_exact_once() {
        let (client, peer, _) = pair();
        let (client, peer) = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            tokio::join!(tls_psk_handshake_openssl_staged(client, &KEY), server(peer, KEY))
        }).await.expect("controlled TLS handshake deadline");
        let mut client = client.unwrap(); let mut peer = peer.unwrap();
        let packet = vec![0x65; 16000];
        let send = async {
            let mut kept = Vec::<u8>::new();
            let count = std::future::poll_fn(|cx| {
                // Allocate before dropping the last Vec, so each retry really
                // moves the pointer, as borrowed jktcp temporary futures do.
                let new = packet.clone();
                let old = std::mem::replace(&mut kept, new);
                let result = Pin::new(&mut client).poll_write(cx, &kept);
                drop(old); result
            }).await.unwrap();
            assert_eq!(count, packet.len(), "partial packet acceptance is disabled");
            client.write_all(b"next-packet").await.unwrap();
            client.flush().await.unwrap();
        };
        let receive = async {
            let mut actual = vec![0; packet.len() + 11];
            peer.read_exact(&mut actual).await.unwrap();
            assert_eq!(&actual[..packet.len()], &packet);
            assert_eq!(&actual[packet.len()..], b"next-packet");
        };
        tokio::time::timeout(std::time::Duration::from_secs(5), async { tokio::join!(send, receive) })
            .await.expect("controlled TLS transfer deadline");
    }
    #[tokio::test]
    async fn wrong_psk_never_produces_an_authenticated_stream() {
        let (client, peer, _) = pair();
        let (client, peer) = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            tokio::join!(tls_psk_handshake_openssl_staged(client, &KEY), server(peer, [0x36; 32]))
        }).await.expect("controlled TLS rejection deadline");
        assert!(client.is_err()); assert!(peer.is_err());
    }
    #[tokio::test]
    async fn corrupted_encrypted_application_data_is_rejected() {
        let (client, peer, tamper) = pair();
        let (client, peer) = tokio::time::timeout(std::time::Duration::from_secs(5), async {
            tokio::join!(tls_psk_handshake_openssl_staged(client, &KEY), server(peer, KEY))
        }).await.expect("controlled TLS handshake deadline");
        let mut client = client.unwrap(); let mut peer = peer.unwrap();
        tamper.store(true, Ordering::SeqCst);
        let send = async {
            let _ = peer.write_all(&[0x44; 64]).await;
            let _ = peer.flush().await;
        };
        let receive = async {
            assert!(client.read_exact(&mut [0; 64]).await.is_err());
        };
        tokio::time::timeout(std::time::Duration::from_secs(5), async { tokio::join!(send, receive) })
            .await.expect("controlled TLS transfer deadline");
    }
    #[tokio::test]
    async fn invalid_psk_lengths_are_rejected_before_handshake() {
        for length in [0, 1, 31, 33, 64] {
            let (client, _peer) = tokio::io::duplex(64);
            assert!(tls_psk_handshake_openssl_staged(client, &vec![7; length]).await.is_err());
        }
    }
}

#[cfg(feature = "openssl")]
mod staged_packet_io;
#[cfg(feature = "openssl")]
pub use staged_packet_io::{PacketDrain, PacketWriteIo};
