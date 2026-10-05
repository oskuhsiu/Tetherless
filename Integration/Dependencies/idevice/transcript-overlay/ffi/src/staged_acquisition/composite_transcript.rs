// Copyright (c) 2026 Tetherless contributors. MIT; retained idevice license.
//! Drives the production composite. Only TcpStream::connect is substituted.
//! This is synthetic integration/ownership evidence, not Apple compatibility.
use super::*;
use idevice::remote_pairing::staged_test_peer::{self as peer, Evidence, Progress, Stage};
use std::{collections::VecDeque, sync::Mutex, time::Duration};
use tokio::{io::DuplexStream, sync::Notify};

#[derive(Debug, Default)]
struct Owners {
    client: AtomicUsize,
    peer: AtomicUsize,
    client_polls: AtomicUsize,
    peer_polls: AtomicUsize,
    dials: Mutex<Vec<SocketAddr>>,
    changed: Notify,
}
impl Owners {
    async fn wait_dials(&self, count: usize) {
        loop {
            let change = self.changed.notified(); tokio::pin!(change); change.as_mut().enable();
            if self.dials.lock().unwrap().len() >= count { return; }
            change.await;
        }
    }
}
#[derive(Debug)]
struct TrackedIo {
    inner: DuplexStream,
    owners: Arc<Owners>,
    client: bool,
    choppy: bool,
    write_pending: bool,
    final_drain_stall: bool,
    progress: Arc<Progress>,
}
impl Drop for TrackedIo {
    fn drop(&mut self) {
        let count = if self.client { &self.owners.client } else { &self.owners.peer };
        count.fetch_add(1, Ordering::SeqCst);
    }
}
impl TrackedIo {
    fn count_poll(&self) -> std::io::Result<()> {
        let polls = if self.client { &self.owners.client_polls } else { &self.owners.peer_polls };
        if polls.fetch_add(1, Ordering::SeqCst) >= 100_000 {
            Err(std::io::Error::other("synthetic fixture poll budget"))
        } else { Ok(()) }
    }
}
impl AsyncRead for TrackedIo {
    fn poll_read(self: Pin<&mut Self>, cx: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        if let Err(error) = this.count_poll() { return Poll::Ready(Err(error)); }
        if !this.choppy { return Pin::new(&mut this.inner).poll_read(cx, output); }
        let mut bytes = [0; 37];
        let count = bytes.len().min(output.remaining());
        let mut part = ReadBuf::new(&mut bytes[..count]);
        match Pin::new(&mut this.inner).poll_read(cx, &mut part) {
            Poll::Ready(Ok(())) => { output.put_slice(part.filled()); Poll::Ready(Ok(())) }
            result => result,
        }
    }
}
impl AsyncWrite for TrackedIo {
    fn poll_write(self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<std::io::Result<usize>> {
        let this = self.get_mut();
        if let Err(error) = this.count_poll() { return Poll::Ready(Err(error)); }
        if this.choppy && this.write_pending {
            this.write_pending = false; cx.waker().wake_by_ref(); return Poll::Pending;
        }
        this.write_pending = this.choppy;
        let count = if this.choppy { bytes.len().min(23) } else { bytes.len() };
        Pin::new(&mut this.inner).poll_write(cx, &bytes[..count])
    }
    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        let this = self.get_mut();
        if let Err(error) = this.count_poll() { return Poll::Ready(Err(error)); }
        // The close response has already been sent and the next underlying TLS
        // flush belongs to the composite's final drain. No protocol is replaced.
        if this.final_drain_stall && this.progress.close_reply_sent.load(Ordering::SeqCst) {
            this.progress.mark(Stage::FinalDrain); return Poll::Pending;
        }
        Pin::new(&mut this.inner).poll_flush(cx)
    }
    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<std::io::Result<()>> {
        Pin::new(&mut self.get_mut().inner).poll_shutdown(cx)
    }
}

// Declared before joined futures so panic unwinding also drops those futures
// before freeing the token. This guard never outlives any cancellation caller.
struct Token(*mut TetherlessPairingValidationHandle);
impl Drop for Token {
    fn drop(&mut self) { unsafe { staged_pairing::tetherless_pairing_validation_free(self.0); } }
}

#[derive(Clone, Copy)]
enum Finish { Success, Cancel(Stage), Timeout(Stage) }
struct Report { result: TetherlessPairingValidationResult, evidence: Option<Evidence> }

async fn transcript(finish: Finish, choppy: bool) -> Report {
    let stop_at = match finish { Finish::Success => None,
        Finish::Cancel(Stage::FinalDrain) => None,
        Finish::Cancel(stage) | Finish::Timeout(stage) => Some(stage) };
    let progress = Progress::new(stop_at);
    let owners = Arc::new(Owners::default());
    // Fixed-capacity in-memory transports; no OS listener or network address is used.
    let (rp_client, rp_peer) = tokio::io::duplex(16 * 1024);
    let (tls_client, tls_peer) = tokio::io::duplex(16 * 1024);
    let mut connections = VecDeque::from([rp_client, tls_client]);
    let wrap = |inner, client, final_drain_stall| TrackedIo { inner,
        owners: Arc::clone(&owners), client, choppy, write_pending: choppy,
        final_drain_stall, progress: Arc::clone(&progress) };
    let peer_rp = wrap(rp_peer, false, false);
    let peer_tls = wrap(tls_peer, false, false);
    let record = peer::record().to_bytes();
    let record_before = record.clone();
    let path = peer::challenge_path();
    let token = Token(staged_pairing::tetherless_pairing_validation_new());
    let handle = token.0;
    let control = unsafe { staged_pairing::begin(handle) }.unwrap();
    let stopped = Notify::new();
    let job = acquire_with_connector(&record, b"192.0.2.1:49152", peer::BUNDLE, &path,
        &peer::CHALLENGE, |address| {
            let index = owners.dials.lock().unwrap().len();
            assert!(index < 2, "no discovery, retry, fallback or extra connector invocation");
            assert_eq!(address.ip().to_string(), "192.0.2.1");
            assert_eq!(address.port(), if index == 0 { peer::ENDPOINT_PORT } else { peer::TUNNEL_PORT });
            owners.dials.lock().unwrap().push(address); owners.changed.notify_waiters();
            let inner = connections.pop_front().expect("exactly two socket owners");
            std::future::ready(Ok(wrap(inner, true,
                index == 1 && matches!(finish, Finish::Cancel(Stage::FinalDrain)))))
        });
    let client = async {
        let deadline_ms = if matches!(finish, Finish::Timeout(_)) { 1500 } else { 8000 };
        let result = staged_pairing::run_controlled(job, control, deadline_ms).await;
        assert_eq!(owners.client.load(Ordering::SeqCst), owners.dials.lock().unwrap().len(),
            "all connected composite sockets must drop before publishing any result");
        // Let the successful peer consume the final drained FIN. Errors terminate
        // the peer immediately: select drops the same owned future, never detach.
        if result != TetherlessPairingValidationOk { stopped.notify_one(); }
        result
    };
    let server = async {
        tokio::select! {
            result = peer::run(peer_rp, peer_tls, Arc::clone(&progress)) => Some(result),
            _ = stopped.notified() => None,
        }
    };
    let cancel = async {
        if let Finish::Cancel(stage) = finish {
            progress.wait_for(stage).await;
            if stage == Stage::FinalDrain {
                // Prove this is teardown after the actual final FIN crossed TLS,
                // rather than an earlier OpenSSL flush during application I/O.
                progress.wait_for(Stage::ServiceFin).await;
            }
            let count = if matches!(stage, Stage::Greeting | Stage::PairVerify | Stage::Listener) { 1 } else { 2 };
            owners.wait_dials(count).await;
            assert_eq!(owners.client.load(Ordering::SeqCst), 0);
            assert!(unsafe { staged_pairing::tetherless_pairing_validation_cancel(handle) });
        }
    };
    let joined = tokio::time::timeout(Duration::from_secs(10), async {
        tokio::join!(client, server, cancel)
    }).await;
    // Even a failing fixture guard cancels/drops every owned future before the
    // handle is freed. No detached task is created anywhere in this transcript.
    drop(connections); // Close preallocated but never connected fixture endpoints.
    drop(token); // The joined/timeout future and every cancel caller are gone.
    let connected = owners.dials.lock().unwrap().len();
    assert_eq!(owners.client.load(Ordering::SeqCst), connected);
    assert_eq!(owners.peer.load(Ordering::SeqCst), 2);
    let (result, server, ()) = joined.expect("finite complete synthetic transcript");
    assert_eq!(record, record_before, "staged input remains byte-for-byte unchanged");
    match finish {
        Finish::Success => {
            assert_eq!(result, TetherlessPairingValidationOk,
                "synthetic stages: {:?}; peer result: {:?}", progress.stages(), server);
            assert_eq!(connected, 2);
        }
        Finish::Cancel(stage) => {
            assert!(progress.reached(stage)); assert_eq!(result, TetherlessPairingValidationCancelled);
        }
        Finish::Timeout(stage) => {
            assert!(progress.reached(stage), "timeout must exercise the requested boundary");
            assert_eq!(result, TetherlessPairingValidationTimedOut);
        }
    }
    // Freeze observations, yield once, and prove no work continues after join.
    let polls = (owners.client_polls.load(Ordering::SeqCst), owners.peer_polls.load(Ordering::SeqCst));
    tokio::task::yield_now().await;
    assert_eq!(polls, (owners.client_polls.load(Ordering::SeqCst), owners.peer_polls.load(Ordering::SeqCst)));
    Report { result, evidence: server.map(|result| result.expect("faithful peer completed")) }
}

#[tokio::test]
async fn actual_composite_success_authenticates_discovers_reads_closes_and_joins() {
    for choppy in [false, true] {
        let report = transcript(Finish::Success, choppy).await;
        assert_eq!(report.result, TetherlessPairingValidationOk);
        let evidence = report.evidence.expect("peer must observe final TCP FIN before fixture return");
        assert!(evidence.host_signature_verified && evidence.encrypted_listener_verified);
        assert!(evidence.tls12_psk_negotiated && evidence.rsd_handshake_verified);
        assert!(evidence.checkin_verified && evidence.vend_verified);
        assert_eq!(evidence.afc_operations, [0x0d, 0x0f, 0x0f, 0x14]);
        assert_eq!(evidence.tcp_fins, 2, "RSD close and service close traverse TLS");
        assert!(evidence.client_application_bytes > 0 && evidence.client_application_bytes < 64 * 1024);
    }
}

#[tokio::test]
async fn actual_composite_cancellation_joins_at_every_protocol_boundary() {
    for stage in [Stage::Greeting, Stage::PairVerify, Stage::Listener, Stage::Tls,
        Stage::CdTunnel, Stage::Rsd, Stage::Checkin, Stage::VendContainer,
        Stage::AfcOpen, Stage::AfcRead, Stage::AfcClose, Stage::FinalDrain] {
        transcript(Finish::Cancel(stage), true).await;
    }
}

#[tokio::test]
async fn actual_composite_deadline_covers_afc_after_all_prior_stages() {
    transcript(Finish::Timeout(Stage::AfcRead), true).await;
}
