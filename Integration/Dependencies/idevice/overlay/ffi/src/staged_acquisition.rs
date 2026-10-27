// Copyright (c) 2026 Tetherless contributors. MIT; see retained idevice license.
//! Validation-only acquisition from a staged .rppairing record and one selected
//! numeric endpoint. Nothing is persisted, promoted, paired or returned as a handle.
//! OpenSSL-only source candidate; target library/native validation remains pending.
#![cfg(feature = "openssl")]
use std::{
    io::Cursor,
    net::SocketAddr,
    pin::Pin,
    sync::{Arc, atomic::{AtomicBool, AtomicUsize, Ordering}},
    task::{Context, Poll},
};
use idevice::{
    remote_pairing::{BoundedRpPairingSocket, RemotePairingClient, RpPairingFile,
        tunnel::{connect_tls_psk_tunnel_openssl_bounded, PacketWriteIo}},
    rsd::RsdHandshake,
    tcp::{adapter::Adapter, stream::AdapterStream},
};
use plist::stream::{BinaryReader, Event, XmlReader};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};
use crate::staged_pairing::{self, Result, TetherlessPairingValidationHandle,
    TetherlessPairingValidationResult, TetherlessPairingValidationResult::*};

const MAX_RECORD: usize = 64 * 1024;
const MAX_ENDPOINT: usize = 128;
const MAX_BUNDLE: usize = 255;
const MAX_PATH: usize = 160;
const MAX_IO_POLLS: usize = 262_144;
const MAX_TRANSPORT_BYTES: usize = 8 * 1024 * 1024; // combined sockets, per direction
const HOUSE_ARREST: &str = "com.apple.mobile.house_arrest.shim.remote";

/// Validate an in-memory, staged .rppairing (Ed25519 remote pairing) record.
/// Legacy lockdown pair files are not accepted. The selected endpoint is bounded
/// UTF-8 numeric SocketAddr text, e.g. 192.0.2.1:49152 or [fe80::1%3]:49152;
/// hostnames are rejected and no discovery/fallback/re-pairing takes place.
///
/// A single operation owns record parsing, RP verification, TLS/CDTunnel, RSD,
/// check-in, VendContainer, challenge read/remote file close, service close and
/// final destruction. The caller's 1..=10000ms deadline and cancellation cover
/// the whole operation. No background adapter task is spawned. Return is the
/// join: all sockets, the borrowed adapter streams, and adapter are gone first.
///
/// The cumulative raw transport budget is 8MiB per direction across both TCP
/// sockets, including TLS overhead. This also bounds jktcp's receive cache while
/// waiting for ACKs. Other protocol layers have smaller independent limits.
/// No staged record, connection handle, peer metadata or challenge is returned;
/// only fixed result codes leave this function. The original record is unchanged.
/// A successful challenge proves app-container access, not hardware identity.
///
/// # Safety
/// Invoke on a non-Tokio FFI worker thread. All input pointers must reference the
/// supplied number of immutable bytes through return. The cancellation handle
/// must be live until this function and every concurrent cancel call have joined.
/// It is single-use. Before calling, write a fresh independently named 32-byte
/// random local challenge under the documented validation directory, protect it
/// and exclude it from backup. Never send the expected challenge to the peer.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_validate_staged(
    record: *const u8, record_len: usize,
    endpoint: *const u8, endpoint_len: usize,
    cancellation: *const TetherlessPairingValidationHandle,
    bundle_id: *const u8, bundle_len: usize,
    relative_path: *const u8, path_len: usize,
    expected: *const u8, expected_len: usize,
    timeout_ms: u32,
) -> TetherlessPairingValidationResult {
    if record.is_null() || endpoint.is_null() || bundle_id.is_null()
        || relative_path.is_null() || expected.is_null()
        || !(1..=MAX_RECORD).contains(&record_len)
        || !(1..=MAX_ENDPOINT).contains(&endpoint_len)
        || !(1..=MAX_BUNDLE).contains(&bundle_len) || path_len > MAX_PATH
        || expected_len != staged_pairing::CHALLENGE_LEN
        || !(1..=staged_pairing::MAX_DURATION_MS).contains(&timeout_ms)
    { return TetherlessPairingValidationInvalidArgument; }
    let control = match unsafe { staged_pairing::begin(cancellation) } {
        Ok(control) => control, Err(result) => return result,
    };
    let record = unsafe { std::slice::from_raw_parts(record, record_len) };
    let endpoint = unsafe { std::slice::from_raw_parts(endpoint, endpoint_len) };
    let bundle = unsafe { std::slice::from_raw_parts(bundle_id, bundle_len) };
    let path = unsafe { std::slice::from_raw_parts(relative_path, path_len) };
    let expected = unsafe { std::slice::from_raw_parts(expected, expected_len) };
    // Pinned upstream RP/plist routines log payloads under tracing. Use a
    // thread-local subscriber for this inline block_on only. No global setting
    // is changed; no background job can outlive or escape this scoped redaction.
    tracing::subscriber::with_default(tracing::subscriber::NoSubscriber::default(), || {
        crate::run_sync_local(staged_pairing::run_controlled(
            acquire_and_validate(record, endpoint, bundle, path, expected), control, timeout_ms,
        ))
    })
}

fn parse_endpoint(bytes: &[u8]) -> Result<SocketAddr> {
    if bytes.is_empty() || bytes.len() > MAX_ENDPOINT { return Err(TetherlessPairingValidationInvalidArgument); }
    let address: SocketAddr = std::str::from_utf8(bytes).ok().and_then(|s| s.parse().ok())
        .ok_or(TetherlessPairingValidationInvalidArgument)?;
    if address.port() == 0 || address.ip().is_unspecified() || address.ip().is_multicast() {
        return Err(TetherlessPairingValidationInvalidArgument);
    }
    Ok(address)
}

// Reject nested/recursive binary references before the tree-based upstream
// decoder can expand them. A .rppairing record is one flat dictionary of scalars.
// All streams stop at 32 events, individual scalar size is bounded by input64KiB.
fn flat_record_events<'a>(events: impl Iterator<Item = std::result::Result<Event<'a>, plist::Error>>) -> bool {
    let mut events = events;
    if !matches!(events.next(), Some(Ok(Event::StartDictionary(_)))) { return false; }
    let mut expect_key = true;
    let mut seen = Vec::<String>::new();
    for event in events.by_ref().take(32) {
        match event {
            Ok(Event::EndCollection) if expect_key => return events.next().is_none(),
            Ok(Event::String(key)) if expect_key => {
                if !matches!(key.as_ref(), "public_key" | "private_key" | "identifier" | "alt_irk" | "generated_by")
                    || seen.iter().any(|old| old == key.as_ref())
                { return false; }
                seen.push(key.into_owned()); expect_key = false;
            }
            Ok(Event::String(_)) | Ok(Event::Data(_)) if !expect_key => expect_key = true,
            _ => return false,
        }
    }
    false
}

fn parse_record(bytes: &[u8]) -> Result<RpPairingFile> {
    if bytes.is_empty() || bytes.len() > MAX_RECORD { return Err(TetherlessPairingValidationInvalidArgument); }
    let valid = if bytes.starts_with(b"bplist00") {
        flat_record_events(BinaryReader::new(Cursor::new(bytes)))
    } else {
        if !staged_pairing::xml_entities_are_known(bytes) {
            return Err(TetherlessPairingValidationInvalidArgument);
        }
        flat_record_events(XmlReader::new(Cursor::new(bytes)))
    };
    if !valid { return Err(TetherlessPairingValidationInvalidArgument); }
    let record = RpPairingFile::from_bytes(bytes).map_err(|_| TetherlessPairingValidationInvalidArgument)?;
    if !record.is_paired() || record.identifier().is_empty() || record.identifier().len() > 128
        || record.identifier().chars().any(char::is_control)
        || record.alt_irk().is_some_and(|bytes| bytes.len() != 16)
        || record.e_private_key.verifying_key() != record.e_public_key
    { return Err(TetherlessPairingValidationInvalidArgument); }
    Ok(record)
}

async fn acquire_and_validate(
    record: &[u8], endpoint: &[u8], bundle: &[u8], path: &[u8], expected: &[u8],
) -> Result<()> {
    acquire_with_connector(record, endpoint, bundle, path, expected,
        |address| tokio::net::TcpStream::connect(address)).await
}

// Adapter contains a 64-KiB receive array. Keep that storage out of every
// enclosing async state machine, including before the first socket is polled.
// Its upstream constructor can still use a bounded stack temporary; isolating
// this synchronous call prevents that temporary from enlarging our poll frame.
#[inline(never)]
fn owned_adapter<S: idevice::ReadWrite + 'static>(
    raw: S, client_ip: std::net::IpAddr, server_ip: std::net::IpAddr,
) -> Box<Adapter> {
    Box::new(Adapter::new(Box::new(raw), client_ip, server_ip))
}

// The production connector is exactly TcpStream::connect above. Injection is
// private and allows cancellation fixtures without accounts, devices or sockets.
async fn acquire_with_connector<C, F, S>(
    record: &[u8], endpoint: &[u8], bundle: &[u8], path: &[u8], expected: &[u8], mut connect: C,
) -> Result<()>
where
    C: FnMut(SocketAddr) -> F,
    F: std::future::Future<Output = std::io::Result<S>>,
    S: idevice::ReadWrite + 'static,
{
    // This bounded parse runs inside the cancellation/deadline future. No file
    // path lookup, persistent write, promotion, or default pairing handle exists.
    if !staged_pairing::valid_bundle(bundle) || !staged_pairing::valid_path(path) {
        return Err(TetherlessPairingValidationInvalidArgument);
    }
    let address = parse_endpoint(endpoint)?;
    let mut record = parse_record(record)?;
    let wire = Arc::new(WireBudget::default());
    let result = async {
        let stream = connect(address).await.map_err(|_| TetherlessPairingValidationIo)?;
        let stream = LimitedIo::new(stream, wire.clone());
        let mut rpc = RemotePairingClient::new(BoundedRpPairingSocket::new(stream), "Tetherless");
        // Pin only the larger sequential phase futures, not the already-built
        // composite. Each box is polled in this task and dropped at its await;
        // cancellation synchronously drops the active box and all local owners.
        Box::pin(rpc.connect_staged(&mut record))
            .await.map_err(|_| TetherlessPairingValidationProtocol)?;
        let port = rpc.create_tcp_listener_bounded().await.map_err(|_| TetherlessPairingValidationProtocol)?;
        let mut tunnel_address = address;
        tunnel_address.set_port(port);
        let stream = connect(tunnel_address).await.map_err(|_| TetherlessPairingValidationIo)?;
        let tunnel = Box::pin(connect_tls_psk_tunnel_openssl_bounded(LimitedIo::new(stream, wire.clone()), rpc.encryption_key()))
            .await.map_err(|_| TetherlessPairingValidationProtocol)?;
        let client_ip = tunnel.info.client_address.parse().map_err(|_| TetherlessPairingValidationProtocol)?;
        let server_ip = tunnel.info.server_address.parse().map_err(|_| TetherlessPairingValidationProtocol)?;
        let rsd_port = tunnel.info.server_rsd_port;
        let mtu = tunnel.info.mtu as usize;
        // The adapter owns the raw tunnel. AdapterStream only borrows it; no
        // to_async_handle/AdapterHandle, spawn, unbounded channel, or async Drop.
        // CDTunnel caps MTU at16000. The owned packet shim copies one packet
        // once and preserves its exact TLS write identity across Pending, even
        // when jktcp abandons a temporary ACK/retransmit future after caching data.
        if !(1280..=16000).contains(&mtu) { return Err(TetherlessPairingValidationProtocol); }
        let (raw, mut final_drain) = PacketWriteIo::new(tunnel.into_inner());
        let mut adapter = owned_adapter(raw, client_ip, server_ip);
        adapter.set_mss(mtu - 60).set_send_window(64 * 1024);
        let handshake = {
            let mut stream = AdapterStream::connect(&mut adapter, rsd_port).await
                .map_err(|_| TetherlessPairingValidationIo)?;
            let handshake = Box::pin(RsdHandshake::new_bounded(&mut stream)).await;
            let close = stream.close().await;
            // Drop before a second mutable borrow of the same adapter.
            drop(stream);
            let handshake = handshake.map_err(|_| TetherlessPairingValidationProtocol)?;
            close.map_err(|_| TetherlessPairingValidationIo)?;
            handshake
        };
        let port = handshake.services.get(HOUSE_ARREST)
            .filter(|service| service.port != 0 && !service.uses_remote_xpc)
            .map(|service| service.port).ok_or(TetherlessPairingValidationProtocol)?;
        // RSD metadata can now be freed before the challenge read.
        drop(handshake);
        let mut stream = AdapterStream::connect(&mut adapter, port).await.map_err(|_| TetherlessPairingValidationIo)?;
        let validation = Box::pin(staged_pairing::validate_borrowed(&mut stream, bundle, path, expected)).await;
        let close = stream.close().await;
        drop(stream);
        validation?;
        close.map_err(|_| TetherlessPairingValidationIo)?;
        // Adapter::close does not flush its raw transport. The local drain
        // owner keeps the TLS stream alive after adapter destruction, ensuring
        // the final accepted FIN is drained before success, under this deadline.
        // This still does not prove the peer acknowledged that TCP FIN.
        drop(adapter);
        final_drain.flush().await.map_err(|_| TetherlessPairingValidationIo)?;
        drop(final_drain);
        drop(rpc);
        Ok(())
    }.await;
    if wire.exhausted.load(Ordering::Relaxed) { Err(TetherlessPairingValidationBudget) } else { result }
}

#[derive(Default)]
struct WireBudget { read: AtomicUsize, written: AtomicUsize, polls: AtomicUsize, exhausted: AtomicBool }
impl WireBudget {
    fn reject(&self) -> std::io::Error {
        self.exhausted.store(true, Ordering::Relaxed);
        std::io::Error::other("staged transport budget exceeded")
    }
}

// Counts actual transport bytes, including TLS/IP/TCP overhead, across both
// connections. Independent protocol frame limits prevent single huge allocations.
struct LimitedIo<S> { inner: S, budget: Arc<WireBudget>, polls: usize }
impl<S> LimitedIo<S> {
    fn new(inner: S, budget: Arc<WireBudget>) -> Self { Self { inner, budget, polls: 0 } }
    fn before_poll(&mut self, cx: &mut Context<'_>) -> std::io::Result<bool> {
        if self.budget.polls.fetch_add(1, Ordering::Relaxed) >= MAX_IO_POLLS
            || self.budget.exhausted.load(Ordering::Relaxed)
        { return Err(self.budget.reject()); }
        self.polls += 1;
        if self.polls == 64 { self.polls = 0; cx.waker().wake_by_ref(); Ok(true) } else { Ok(false) }
    }
}
impl<S> std::fmt::Debug for LimitedIo<S> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str("LimitedIo") }
}
impl<S: AsyncRead + Unpin> AsyncRead for LimitedIo<S> {
    fn poll_read(self: Pin<&mut Self>, cx: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        if output.remaining() == 0 { return Poll::Ready(Ok(())); }
        match this.before_poll(cx) {
            Ok(true) => return Poll::Pending,
            Err(e) => return Poll::Ready(Err(e)),
            Ok(false) => {}
        }
        let remaining = MAX_TRANSPORT_BYTES.saturating_sub(this.budget.read.load(Ordering::Relaxed));
        if remaining == 0 || this.budget.exhausted.load(Ordering::Relaxed) {
            return Poll::Ready(Err(this.budget.reject()));
        }
        let mut bytes = [0; 16384];
        let length = bytes.len().min(output.remaining()).min(remaining);
        let mut buffer = ReadBuf::new(&mut bytes[..length]);
        match Pin::new(&mut this.inner).poll_read(cx, &mut buffer) {
            Poll::Pending => Poll::Pending,
            Poll::Ready(Err(e)) => Poll::Ready(Err(e)),
            Poll::Ready(Ok(())) => {
                this.budget.read.fetch_add(buffer.filled().len(), Ordering::Relaxed);
                output.put_slice(buffer.filled());
                Poll::Ready(Ok(()))
            }
        }
    }
}
impl<S: AsyncWrite + Unpin> AsyncWrite for LimitedIo<S> {
    fn poll_write(self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<std::io::Result<usize>> {
        let this = self.get_mut();
        if bytes.is_empty() { return Poll::Ready(Ok(0)); }
        match this.before_poll(cx) {
            Ok(true) => return Poll::Pending,
            Err(e) => return Poll::Ready(Err(e)),
            Ok(false) => {}
        }
        let remaining = MAX_TRANSPORT_BYTES.saturating_sub(this.budget.written.load(Ordering::Relaxed));
        if remaining == 0 || this.budget.exhausted.load(Ordering::Relaxed) {
            return Poll::Ready(Err(this.budget.reject()));
        }
        match Pin::new(&mut this.inner).poll_write(cx, &bytes[..bytes.len().min(remaining)]) {
            Poll::Ready(Ok(length)) => { this.budget.written.fetch_add(length, Ordering::Relaxed); Poll::Ready(Ok(length)) }
            other => other,
        }
    }
    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        match this.before_poll(cx) {
            Ok(true) => Poll::Pending,
            Err(e) => Poll::Ready(Err(e)),
            Ok(false) => Pin::new(&mut this.inner).poll_flush(cx),
        }
    }
    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        match this.before_poll(cx) {
            Ok(true) => Poll::Pending,
            Err(e) => Poll::Ready(Err(e)),
            Ok(false) => Pin::new(&mut this.inner).poll_shutdown(cx),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    #[test]
    fn endpoint_is_numeric_selected_address_only() {
        for value in ["example.org:123", "127.0.0.1:0", "0.0.0.0:123", "[ff02::1]:123", "127.0.0.1"] {
            assert!(parse_endpoint(value.as_bytes()).is_err());
        }
        for value in ["192.0.2.1:49152", "[fd00::1]:49152", "[fe80::1%3]:49152"] {
            assert!(parse_endpoint(value.as_bytes()).is_ok());
        }
    }
    #[test]
    fn record_rejects_nested_and_duplicate_scalars() {
        for value in [
            b"<plist><dict><key>identifier</key><dict/></dict></plist>".as_slice(),
            b"<plist><dict><key>identifier</key><string>a</string><key>identifier</key><string>b</string></dict></plist>",
        ] { assert!(parse_record(value).is_err()); }
        assert!(parse_record(&vec![0; MAX_RECORD + 1]).is_err());
    }
    #[test]
    fn record_rejects_unknown_xml_entities_before_plist_decoder() {
        let mut record = RpPairingFile::generate("synthetic-only-fixture");
        record.identifier = "a&ghost;b".into();
        let xml = String::from_utf8(record.to_bytes()).unwrap();
        let malicious = xml.replace("&amp;ghost;", "&ghost;");
        assert_ne!(xml, malicious);
        assert!(parse_record(malicious.as_bytes()).is_err());
        assert!(parse_record(xml.as_bytes()).is_ok());
    }
    #[tokio::test]
    async fn transport_budget_stops_before_crossing_shared_limit() {
        let wire = Arc::new(WireBudget::default());
        wire.read.store(MAX_TRANSPORT_BYTES - 1, Ordering::Relaxed);
        let (client, mut peer) = tokio::io::duplex(64);
        peer.write_all(&[1, 2]).await.unwrap();
        let mut stream = LimitedIo::new(client, wire.clone());
        let mut bytes = [0; 2];
        assert_eq!(stream.read(&mut bytes).await.unwrap(), 1);
        assert!(stream.read(&mut bytes).await.is_err());
        assert!(wire.exhausted.load(Ordering::Relaxed));
        assert_eq!(wire.read.load(Ordering::Relaxed), MAX_TRANSPORT_BYTES);
    }
}

#[cfg(test)]
mod ownership_fixtures {
    use super::*;
    use tokio::sync::Notify;
    #[derive(Debug)]
    struct PendingIo { drops: Arc<AtomicUsize>, reading: Arc<Notify> }
    impl Drop for PendingIo { fn drop(&mut self) { self.drops.fetch_add(1, Ordering::SeqCst); } }
    impl AsyncRead for PendingIo {
        fn poll_read(self: Pin<&mut Self>, _: &mut Context<'_>, _: &mut ReadBuf<'_>) -> Poll<std::io::Result<()>> {
            self.reading.notify_one(); Poll::Pending
        }
    }
    impl AsyncWrite for PendingIo {
        fn poll_write(self: Pin<&mut Self>, _: &mut Context<'_>, bytes: &[u8]) -> Poll<std::io::Result<usize>> {
            Poll::Ready(Ok(bytes.len()))
        }
        fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<std::io::Result<()>> { Poll::Ready(Ok(())) }
        fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<std::io::Result<()>> { Poll::Ready(Ok(())) }
    }

    #[test]
    fn composite_future_storage_stays_bounded_without_constructing_it() {
        // Infer the concrete future from an uncalled factory: even a regression
        // must report its size without first putting that future on the stack.
        fn future_bytes<A, F: std::future::Future>(_: impl FnOnce(A) -> F) -> usize {
            std::mem::size_of::<F>()
        }
        fn connector(_: SocketAddr) -> std::future::Ready<std::io::Result<PendingIo>> {
            panic!("the layout-only connector must never run")
        }
        let production = future_bytes(|()| acquire_and_validate(&[], &[], &[], &[], &[]));
        let injected = future_bytes(|()| acquire_with_connector(&[], &[], &[], &[], &[], connector));
        let controlled = future_bytes(|control| staged_pairing::run_controlled(
            acquire_with_connector(&[], &[], &[], &[], &[], connector), control, 1000,
        ));
        let joined = future_bytes(|control| async move {
            let job = acquire_with_connector(&[], &[], &[], &[], &[], connector);
            tokio::join!(staged_pairing::run_controlled(job, control, 1000), std::future::pending::<()>())
        });
        // This guards by-value state storage, not a platform's whole call stack.
        // The real cancel/timeout fixture below must still run on default stacks.
        for (name, bytes) in [("production", production), ("injected", injected),
            ("controlled", controlled), ("joined", joined)]
        {
            eprintln!("staged acquisition future layout: {name}={bytes} bytes");
            assert!(bytes <= 16 * 1024, "{name} future embeds {bytes} bytes of state");
        }
    }

    #[test]
    fn heap_owned_adapter_drops_transport_synchronously() {
        let drops = Arc::new(AtomicUsize::new(0));
        let reading = Arc::new(Notify::new());
        let adapter = owned_adapter(PendingIo { drops: drops.clone(), reading },
            "192.0.2.1".parse().unwrap(), "192.0.2.2".parse().unwrap());
        assert_eq!(drops.load(Ordering::SeqCst), 0);
        drop(adapter);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }

    async fn two_sockets_stalled_in_real_tls(cancel: bool) {
        let handle = staged_pairing::tetherless_pairing_validation_new();
        let control = unsafe { staged_pairing::begin(handle) }.unwrap();
        let drops = Arc::new(AtomicUsize::new(0));
        let reading = Arc::new(Notify::new());
        let budget = Arc::new(WireBudget::default());
        let rp = LimitedIo::new(PendingIo { drops: drops.clone(), reading: reading.clone() }, budget.clone());
        let tls = LimitedIo::new(PendingIo { drops: drops.clone(), reading: reading.clone() }, budget);
        let job = async move {
            let result = idevice::remote_pairing::tunnel::tls_psk_handshake_openssl_staged(tls, &[5; 32]).await;
            drop(rp);
            result.map(|_| ()).map_err(|_| TetherlessPairingValidationProtocol)
        };
        let result = if cancel {
            let cancel = async {
                reading.notified().await;
                assert_eq!(drops.load(Ordering::SeqCst), 0);
                assert!(unsafe { staged_pairing::tetherless_pairing_validation_cancel(handle) });
            };
            let (result, ()) = tokio::join!(staged_pairing::run_controlled(job, control, 1000), cancel);
            result
        } else {
            staged_pairing::run_controlled(job, control, 1).await
        };
        assert_eq!(drops.load(Ordering::SeqCst), 2, "both sockets must be destroyed before return");
        assert_eq!(result, if cancel { TetherlessPairingValidationCancelled } else { TetherlessPairingValidationTimedOut });
        unsafe { staged_pairing::tetherless_pairing_validation_free(handle); }
    }
    #[tokio::test]
    async fn cancellation_joins_both_owned_sockets_during_tls() { two_sockets_stalled_in_real_tls(true).await; }
    #[tokio::test]
    async fn timeout_joins_both_owned_sockets_during_tls() { two_sockets_stalled_in_real_tls(false).await; }
    #[tokio::test]
    async fn composite_acquisition_joins_rp_socket_on_cancel_and_timeout() {
        for cancel_requested in [false, true] {
            let record = RpPairingFile::generate("synthetic-only-fixture").to_bytes();
            let path = [b"Library/TetherlessPairingValidation/".as_slice(),
                &[b'a'; 64], b".challenge"].concat();
            let handle = staged_pairing::tetherless_pairing_validation_new();
            let control = unsafe { staged_pairing::begin(handle) }.unwrap();
            let drops = Arc::new(AtomicUsize::new(0));
            let dials = Arc::new(AtomicUsize::new(0));
            let reading = Arc::new(Notify::new());
            let job = acquire_with_connector(&record, b"192.0.2.1:49152", b"com.example.fixture",
                &path, &[8; 32], |_| {
                    dials.fetch_add(1, Ordering::SeqCst);
                    std::future::ready(Ok(PendingIo { drops: drops.clone(), reading: reading.clone() }))
                });
            let outcome = if cancel_requested {
                let cancel = async {
                    reading.notified().await;
                    assert!(unsafe { staged_pairing::tetherless_pairing_validation_cancel(handle) });
                };
                let (outcome, ()) = tokio::join!(staged_pairing::run_controlled(job, control, 1000), cancel);
                outcome
            } else {
                staged_pairing::run_controlled(job, control, 1).await
            };
            assert_eq!(outcome, if cancel_requested { TetherlessPairingValidationCancelled }
                else { TetherlessPairingValidationTimedOut });
            assert_eq!(drops.load(Ordering::SeqCst), 1);
            assert_eq!(dials.load(Ordering::SeqCst), 1, "no fallback connection may be attempted");
            unsafe { staged_pairing::tetherless_pairing_validation_free(handle); }
        }
    }
    #[tokio::test]
    async fn raw_poll_budget_rejects_pending_transport_finitely() {
        use tokio::io::AsyncReadExt;
        let budget = Arc::new(WireBudget::default());
        budget.polls.store(MAX_IO_POLLS, Ordering::Relaxed);
        let mut io = LimitedIo::new(PendingIo { drops: Arc::new(AtomicUsize::new(0)),
            reading: Arc::new(Notify::new()) }, budget.clone());
        assert!(io.read(&mut [0]).await.is_err());
        assert!(budget.exhausted.load(Ordering::Relaxed));
    }
}

#[cfg(test)]
mod contributory_composite_tests {
    use super::*;
    use std::sync::Mutex;
    #[derive(Default, Debug)]
    struct Trace { sent: Vec<u8>, read: usize, drops: usize }
    #[derive(Debug)]
    struct ScriptedRp { replies: Vec<u8>, offset: usize, trace: Arc<Mutex<Trace>> }
    impl Drop for ScriptedRp { fn drop(&mut self) { self.trace.lock().unwrap().drops += 1; } }
    impl AsyncRead for ScriptedRp {
        fn poll_read(mut self: Pin<&mut Self>, _: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<std::io::Result<()>> {
            let count = output.remaining().min(self.replies.len() - self.offset);
            output.put_slice(&self.replies[self.offset..self.offset + count]);
            self.offset += count; self.trace.lock().unwrap().read += count;
            Poll::Ready(Ok(()))
        }
    }
    impl AsyncWrite for ScriptedRp {
        fn poll_write(self: Pin<&mut Self>, _: &mut Context<'_>, bytes: &[u8]) -> Poll<std::io::Result<usize>> {
            self.trace.lock().unwrap().sent.extend_from_slice(bytes); Poll::Ready(Ok(bytes.len()))
        }
        fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<std::io::Result<()>> { Poll::Ready(Ok(())) }
        fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<std::io::Result<()>> { Poll::Ready(Ok(())) }
    }
    fn frame(json: &[u8]) -> Vec<u8> {
        [b"RPPairing".as_slice(), &(json.len() as u16).to_be_bytes(), json].concat()
    }
    fn frames(mut bytes: &[u8]) -> Vec<&[u8]> {
        let mut result = Vec::new();
        while !bytes.is_empty() {
            assert!(bytes.len() >= 11); assert_eq!(&bytes[..9], b"RPPairing");
            let length = u16::from_be_bytes([bytes[9], bytes[10]]) as usize;
            assert!(bytes.len() >= 11 + length);
            result.push(&bytes[11..11 + length]); bytes = &bytes[11 + length..];
        }
        result
    }
    #[tokio::test]
    async fn low_order_raw_rp_stops_before_host_auth_listener_and_second_connection() {
        // TLV bytes: State=2, PublicKey length32, then u=0 or u=1. These are
        // synthetic public low-order inputs; no account/device fixture is used.
        for public_tlv in [
            "BgECAyAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
            "BgECAyABAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA==",
        ] {
            let greeting = frame(br#"{"response":{"_1":{"handshake":{"_0":{}}}}}"#);
            let key = frame(format!("{{\"event\":{{\"_0\":{{\"pairingData\":{{\"_0\":{{\"data\":\"{public_tlv}\"}}}}}}}}}}").as_bytes());
            // A final verify reply is present so the unsafe old path would
            // transmit host authentication and attempt its encrypted listener.
            let final_verify = frame(br#"{"event":{"_0":{"pairingData":{"_0":{"data":"BgEE"}}}}}"#);
            let replies = [greeting.as_slice(), key.as_slice(), final_verify.as_slice()].concat();
            let total = replies.len();
            let record = RpPairingFile::generate("synthetic-contributory-fixture").to_bytes();
            let path = [b"Library/TetherlessPairingValidation/".as_slice(), &[b'a'; 64], b".challenge"].concat();
            let trace = Arc::new(Mutex::new(Trace::default()));
            let dials = AtomicUsize::new(0);
            let result = acquire_with_connector(&record, b"192.0.2.1:49152", b"com.example.fixture",
                &path, &[9; 32], |_| {
                    dials.fetch_add(1, Ordering::SeqCst);
                    std::future::ready(Ok(ScriptedRp { replies: replies.clone(), offset: 0, trace: Arc::clone(&trace) }))
                }).await;
            assert_eq!(result, Err(TetherlessPairingValidationProtocol));
            assert_eq!(dials.load(Ordering::SeqCst), 1, "TLS/second connection must not be attempted");
            let trace = trace.lock().unwrap();
            assert_eq!(trace.drops, 1);
            assert!(trace.read < total, "final host-authentication reply must remain unread");
            let sent = frames(&trace.sent);
            assert_eq!(sent.len(), 2);
            for body in sent {
                let text = std::str::from_utf8(body).unwrap();
                assert!(!text.contains("\"startNewSession\":false"));
                assert!(!text.contains("streamEncrypted"));
                assert!(!text.contains("createListener"));
            }
        }
    }
}
