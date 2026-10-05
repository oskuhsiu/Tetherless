// Copyright (c) 2026 Tetherless contributors. MIT; retained idevice license.
//! Synthetic, real-TCP, public-C-ABI transcripts. No device compatibility claim.
//! The blocking FFI runs on an explicitly joined scoped thread, never Tokio.
use super::*;
use idevice::remote_pairing::host_test_phone::{self as phone, Evidence, Mode, Progress};
use std::{io, net::{TcpListener, TcpStream}, pin::Pin,
    sync::atomic::{AtomicU64, AtomicUsize}, task::{Context, Poll}, time::Instant};
use tokio::io::{AsyncRead, AsyncReadExt, AsyncWrite, ReadBuf};

const HOST_NAME: &[u8] = b"synthetic host";
const HOST_MODEL: &[u8] = b"Mac17,7";

struct Token(*mut TetherlessPairingHostHandle);
// Sharing a borrowed token is safe only for this fixture: prepare completes
// first; scope joins native and all cancel callers before Token::drop/free.
// No other code obtains ownership or can start work after that scope ends.
unsafe impl Sync for Token {}
impl Token { fn pointer(&self) -> *mut TetherlessPairingHostHandle { self.0 } }
impl Drop for Token {
    fn drop(&mut self) { unsafe { tetherless_pairing_host_free(self.0); } }
}

struct PinSpy {
    handle: usize,
    cancel_on_pin: bool,
    alive: AtomicBool,
    native_returned: AtomicBool,
    invalid: AtomicBool,
    calls: AtomicUsize,
    packed: AtomicU64,
    ready: AtomicBool,
    callback_cancelled: AtomicBool,
}
extern "C" fn copy_pin(bytes: *const u8, len: usize, context: *mut c_void) {
    // No assert, unwrap, lock, wait, allocation, free or unwind in this callback.
    let spy = unsafe { &*(context as *const PinSpy) };
    let mut valid = spy.alive.load(Ordering::SeqCst)
        && !spy.native_returned.load(Ordering::SeqCst) && !bytes.is_null() && len == 6;
    let mut packed = 0u64;
    if valid {
        for (index, byte) in unsafe { std::slice::from_raw_parts(bytes, len) }.iter().enumerate() {
            valid &= byte.is_ascii_digit(); packed |= (*byte as u64) << (index * 8);
        }
    }
    if !valid { spy.invalid.store(true, Ordering::SeqCst); }
    spy.calls.fetch_add(1, Ordering::SeqCst);
    if valid {
        spy.packed.store(packed, Ordering::Relaxed);
        spy.ready.store(true, Ordering::Release);
    }
    if spy.cancel_on_pin {
        let cancelled = unsafe { tetherless_pairing_host_cancel(spy.handle as *const _) };
        spy.callback_cancelled.store(cancelled, Ordering::SeqCst);
    }
}

#[derive(Debug, Default)]
struct IoCounts { polls: AtomicUsize, dropped: AtomicUsize, read_bytes: AtomicUsize }
#[derive(Debug)]
struct TrackedIo {
    stream: tokio::net::TcpStream,
    counts: Arc<IoCounts>,
    choppy: bool,
    write_pending: bool,
}
impl Drop for TrackedIo {
    fn drop(&mut self) { self.counts.dropped.fetch_add(1, Ordering::SeqCst); }
}
impl TrackedIo {
    fn poll_budget(&self) -> io::Result<()> {
        if self.counts.polls.fetch_add(1, Ordering::SeqCst) >= 100_000 {
            Err(io::Error::other("synthetic phone poll budget"))
        } else { Ok(()) }
    }
}
impl AsyncRead for TrackedIo {
    fn poll_read(self: Pin<&mut Self>, cx: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Err(error) = this.poll_budget() { return Poll::Ready(Err(error)); }
        if !this.choppy {
            let before = output.filled().len();
            let result = Pin::new(&mut this.stream).poll_read(cx, output);
            this.counts.read_bytes.fetch_add(output.filled().len() - before, Ordering::SeqCst);
            return result;
        }
        let mut bytes = [0; 37];
        let len = bytes.len().min(output.remaining());
        let mut part = ReadBuf::new(&mut bytes[..len]);
        let result = Pin::new(&mut this.stream).poll_read(cx, &mut part);
        this.counts.read_bytes.fetch_add(part.filled().len(), Ordering::SeqCst);
        match result {
            Poll::Ready(Ok(())) => { output.put_slice(part.filled()); Poll::Ready(Ok(())) }
            result => result,
        }
    }
}
impl AsyncWrite for TrackedIo {
    fn poll_write(self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<io::Result<usize>> {
        let this = self.get_mut();
        if let Err(error) = this.poll_budget() { return Poll::Ready(Err(error)); }
        if this.choppy && this.write_pending {
            this.write_pending = false; cx.waker().wake_by_ref(); return Poll::Pending;
        }
        this.write_pending = this.choppy;
        let len = if this.choppy { bytes.len().min(23) } else { bytes.len() };
        Pin::new(&mut this.stream).poll_write(cx, &bytes[..len])
    }
    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Err(error) = this.poll_budget() { return Poll::Ready(Err(error)); }
        Pin::new(&mut this.stream).poll_flush(cx)
    }
    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let this = self.get_mut();
        if let Err(error) = this.poll_budget() { return Poll::Ready(Err(error)); }
        Pin::new(&mut this.stream).poll_shutdown(cx)
    }
}

// Caller owns this isolated listener and both endpoints. No Bonjour service is
// published, and no interface, existing socket or system setting is changed.
fn loopback_pair() -> (TcpStream, TcpStream) {
    let listener = TcpListener::bind("127.0.0.1:0").expect("isolated fixture listener");
    listener.set_nonblocking(true).expect("fixture listener nonblocking");
    let phone = TcpStream::connect_timeout(&listener.local_addr().unwrap(), Duration::from_secs(2))
        .expect("bounded fixture connect");
    phone.set_nonblocking(true).expect("fixture phone nonblocking");
    for _ in 0..2000 {
        match listener.accept() {
            Ok((host, _)) => {
                host.set_nonblocking(true).expect("set caller's original nonblocking before native entry");
                return (host, phone);
            }
            Err(error) if error.kind() == io::ErrorKind::WouldBlock =>
                std::thread::sleep(Duration::from_millis(1)),
            Err(_) => panic!("fixture accept failed"),
        }
    }
    panic!("fixture accept exceeded finite bound");
}

#[derive(Clone, Copy)]
enum Finish { Success, WrongPin, TamperM5, ControllerIdentity(Mode), CancelPin, CancelLate, DeadlineLate, CallerWaitExpired }
impl Finish {
    fn paused(self) -> bool { matches!(self, Self::CancelLate | Self::DeadlineLate | Self::CallerWaitExpired) }
    fn mode(self) -> Mode {
        match self { Self::WrongPin => Mode::WrongPin, Self::TamperM5 => Mode::TamperM5,
            Self::ControllerIdentity(mode) => mode,
            _ if self.paused() => Mode::PauseBeforeM5, _ => Mode::Complete }
    }
}
struct NativeReport {
    result: TetherlessPairingHostResult,
    output: [u8; TETHERLESS_HOST_RECORD_CAPACITY],
    length: usize,
    elapsed: Duration,
}
struct PeerReport { evidence: Option<Evidence>, eof: bool, trailing: usize, guard_expired: bool }

async fn drain_to_eof(io: &mut TrackedIo) -> (bool, usize) {
    let mut total = 0usize;
    let mut bytes = [0; 1024];
    // A fixed byte and iteration cap also covers adversarial extra frames.
    for _ in 0..4096 {
        match io.read(&mut bytes).await {
            Ok(0) => return (true, total),
            Ok(count) => { total += count; if total > 65_536 { return (false, total); } }
            Err(_) => return (false, total),
        }
    }
    (false, total)
}

fn transcript(finish: Finish, choppy: bool, first_reject_capacity: bool) {
    let mut raw = std::ptr::null_mut();
    let mut advertisement = TetherlessPairingHostAdvertisement::empty();
    assert_eq!(unsafe { tetherless_pairing_host_prepare(HOST_NAME.as_ptr(), HOST_NAME.len(),
        HOST_MODEL.as_ptr(), HOST_MODEL.len(), &mut raw, &mut advertisement) }, TetherlessPairingHostOk);
    let token = Token(raw);
    // Snapshot prepared identity before native entry. Never log key/record bytes.
    let (identity, public, private) = {
        let prepared = unsafe { &*token.pointer() }.prepared.lock().unwrap();
        let record = &prepared.as_ref().unwrap().record;
        (record.identifier().to_string(), record.public_key_bytes(), record.private_key_bytes())
    };
    let spy = PinSpy { handle: token.pointer() as usize, cancel_on_pin: matches!(finish, Finish::CancelPin),
        alive: AtomicBool::new(true), native_returned: AtomicBool::new(false), invalid: AtomicBool::new(false),
        calls: AtomicUsize::new(0), packed: AtomicU64::new(0), ready: AtomicBool::new(false),
        callback_cancelled: AtomicBool::new(false) };
    let context = &spy as *const PinSpy as *mut c_void;
    let (server, peer) = loopback_pair();
    let fd = server.as_raw_fd();
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    let descriptor_flags = unsafe { libc::fcntl(fd, libc::F_GETFD) };
    let nodelay = server.nodelay().unwrap();
    if first_reject_capacity {
        let mut output = [0x55; TETHERLESS_HOST_RECORD_CAPACITY]; let mut len = 99;
        assert_eq!(unsafe { tetherless_pairing_host_accept_fd(token.pointer(), fd, 10_000,
            Some(copy_pin), context, output.as_mut_ptr(), output.len() - 1, &mut len) },
            TetherlessPairingHostInvalidArgument);
        assert_eq!(len, 0); assert!(output.iter().all(|b| *b == 0x55));
        assert_eq!(spy.calls.load(Ordering::SeqCst), 0);
    }
    let mut original = Some(server); // Kept alive on every path until native is joined/returned.
    let progress = Arc::new(Progress::default());
    let counts = Arc::new(IoCounts::default());
    let timeout_ms = if matches!(finish, Finish::DeadlineLate) { 5000 } else { 10_000 };
    let runtime = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let ((native, peer_report, cancellation), joined) = std::thread::scope(|scope| {
        let (send, mut receive) = tokio::sync::oneshot::channel();
        let token_ref = &token; let spy_ref = &spy;
        let native = scope.spawn(move || {
            let mut output = [0x55; TETHERLESS_HOST_RECORD_CAPACITY]; let mut length = 99;
            let start = Instant::now();
            let result = unsafe { tetherless_pairing_host_accept_fd(token_ref.pointer(), fd, timeout_ms,
                Some(copy_pin), spy_ref as *const PinSpy as *mut c_void,
                output.as_mut_ptr(), output.len(), &mut length) };
            // This signal comes only after synchronous native return. It is not
            // sent by a caller-side timer. The scope still joins the worker below.
            spy_ref.native_returned.store(true, Ordering::SeqCst);
            let _ = send.send(NativeReport { result, output, length, elapsed: start.elapsed() });
        });
        let reports = tracing::subscriber::with_default(tracing::subscriber::NoSubscriber::default(), ||
            runtime.block_on(async {
                let stopped = Notify::new();
                let mut io = TrackedIo { stream: tokio::net::TcpStream::from_std(peer).unwrap(),
                    counts: Arc::clone(&counts), choppy, write_pending: choppy };
                let host = async {
                    // This is only a fixture guard. Failure requests cancellation;
                    // it never grants permission to close the caller FD or free.
                    let report = tokio::time::timeout(Duration::from_secs(18), &mut receive).await;
                    match report {
                        Ok(Ok(report)) => {
                            let intact = unsafe { libc::fcntl(fd, libc::F_GETFL) } == flags
                                && unsafe { libc::fcntl(fd, libc::F_GETFD) } == descriptor_flags
                                && original.as_ref().unwrap().nodelay().ok() == Some(nodelay)
                                && original.as_ref().unwrap().peer_addr().is_ok();
                            // Closing only after native return makes peer EOF a
                            // meaningful proof that the native duplicate is gone.
                            drop(original.take()); stopped.notify_one();
                            Some((report, intact))
                        }
                        _ => {
                            unsafe { tetherless_pairing_host_cancel(token.pointer()); }
                            // Original stays alive. The unconditional native join
                            // occurs outside block_on, before cleanup/assertions.
                            None
                        }
                    }
                };
                let phone = async {
                    let job = phone::run(&mut io, finish.mode(), Arc::clone(&progress), || async {
                        for _ in 0..14_000 {
                            if spy.ready.load(Ordering::Acquire) {
                                let packed = spy.packed.load(Ordering::Relaxed);
                                let bytes: Vec<u8> = (0..6).map(|i| (packed >> (i * 8)) as u8).collect();
                                return String::from_utf8(bytes).unwrap_or_default();
                            }
                            tokio::time::sleep(Duration::from_millis(1)).await;
                        }
                        String::new()
                    });
                    let result = tokio::time::timeout(Duration::from_secs(14), async {
                        if finish.paused() {
                            tokio::select! { result = job => Some(result), _ = stopped.notified() => None }
                        } else { Some(job.await) }
                    }).await;
                    let guard_expired = result.is_err();
                    let evidence = match result { Ok(Some(Ok(evidence))) => Some(evidence), _ => None };
                    // Native return closes only its duplicate; EOF requires the
                    // caller's original to close afterward, in host above.
                    let (eof, trailing) = tokio::time::timeout(Duration::from_secs(3), drain_to_eof(&mut io))
                        .await.unwrap_or((false, 0));
                    PeerReport { evidence, eof, trailing, guard_expired }
                };
                let cancel = async {
                    if !matches!(finish, Finish::CancelLate | Finish::CallerWaitExpired) { return (true, false); }
                    let mut reached = false;
                    for _ in 0..12_000 {
                        if progress.before_m5.load(Ordering::SeqCst) { reached = true; break; }
                        if spy.native_returned.load(Ordering::SeqCst) { break; }
                        tokio::time::sleep(Duration::from_millis(1)).await;
                    }
                    if !reached { return (false, false); }
                    let mut caller_expired = false;
                    if matches!(finish, Finish::CallerWaitExpired) {
                        // Deliberately shorter than the live native deadline.
                        // Expiry does not drop an FFI JoinHandle or its ownership.
                        let wait = async {
                            for _ in 0..1000 {
                                if spy.native_returned.load(Ordering::SeqCst) { return; }
                                tokio::time::sleep(Duration::from_millis(1)).await;
                            }
                        };
                        caller_expired = tokio::time::timeout(Duration::from_millis(25), wait).await.is_err()
                            && !spy.native_returned.load(Ordering::SeqCst);
                    }
                    (unsafe { tetherless_pairing_host_cancel(token.pointer()) }, caller_expired)
                };
                let reports = tokio::join!(host, phone, cancel);
                drop(io);
                reports
            }));
        // Explicit join also runs after a caller wait expires. Scope's own join
        // handles panic unwinding before token/context/original can be dropped.
        let joined = native.join().is_ok();
        (reports, joined)
    });
    // In the guard-failure path this is the first permitted original-FD close.
    drop(original.take());
    spy.alive.store(false, Ordering::SeqCst);
    assert!(joined, "native worker must join");
    let (native, intact) = native.expect("native returned inside finite fixture guard");
    assert!(intact, "original FD remains open with unchanged flags/options through native return");
    assert!(peer_report.eof, "peer must observe EOF after native return and original close");
    assert!(!peer_report.guard_expired, "peer operation must finish within its own bound");
    assert_eq!(counts.dropped.load(Ordering::SeqCst), 1);
    assert_eq!(spy.calls.load(Ordering::SeqCst), 1);
    assert!(!spy.invalid.load(Ordering::SeqCst));
    assert!(native.elapsed < Duration::from_secs(18));
    match finish {
        Finish::Success => {
            assert_eq!(native.result, TetherlessPairingHostOk);
            assert!((1..=TETHERLESS_HOST_RECORD_CAPACITY).contains(&native.length));
            assert!(native.output[native.length..].iter().all(|b| *b == 0));
            let record = tracing::subscriber::with_default(tracing::subscriber::NoSubscriber::default(), ||
                RpPairingFile::from_bytes(&native.output[..native.length])).expect("bounded record parses");
            let evidence = peer_report.evidence.expect("M6 authenticated and signature verified");
            assert!(record.identifier() == identity && evidence.identifier == identity);
            assert!(&advertisement.identifier[..advertisement.identifier_len] == identity.as_bytes());
            assert!(record.public_key_bytes() == public && record.private_key_bytes() == private);
            assert!(evidence.public_key.as_slice() == public.as_slice());
            assert!(record.alt_irk() == Some(phone::PHONE_ALT_IRK.as_slice()));
            assert!(evidence.host_alt_irk.as_slice() == advertisement.host_alt_irk.as_slice());
            assert!(evidence.host_name.as_bytes() == HOST_NAME && evidence.host_model.as_bytes() == HOST_MODEL);
            let txt: plist::Dictionary = plist::from_bytes(&advertisement.txt_plist[..advertisement.txt_plist_len])
                .expect("bounded advertisement parses");
            assert!(txt.get("identifier").and_then(|value| value.as_string()) == Some(identity.as_str()));
            let auth_tag = txt.get("authTag").and_then(|value| value.as_string()).expect("advertised authentication tag");
            assert!(idevice::remote_pairing::PeerDevice::validate_auth_tag(&advertisement.host_alt_irk,
                &identity, auth_tag));
            assert!(progress.m6_verified.load(Ordering::SeqCst));
            assert!(progress.srp_verified.load(Ordering::SeqCst));
            assert!(progress.m5_adapted.load(Ordering::SeqCst));
            assert_eq!(progress.sent_frames.load(Ordering::SeqCst), 4);
            assert_eq!(progress.received_frames.load(Ordering::SeqCst), 4);
            assert_eq!(peer_report.trailing, 0);
            assert!(!unsafe { tetherless_pairing_host_cancel(token.pointer()) });
        }
        _ => {
            let expected = match finish {
                Finish::WrongPin | Finish::TamperM5 | Finish::ControllerIdentity(_) => TetherlessPairingHostProtocol,
                Finish::DeadlineLate => TetherlessPairingHostTimedOut,
                _ => TetherlessPairingHostCancelled,
            };
            assert_eq!(native.result, expected);
            assert_eq!(native.length, 0); assert!(native.output.iter().all(|b| *b == 0));
            assert!(peer_report.evidence.is_none());
            assert!(!progress.m6_verified.load(Ordering::SeqCst));
            if finish.paused() {
                assert!(progress.srp_verified.load(Ordering::SeqCst));
                assert!(progress.before_m5.load(Ordering::SeqCst));
                assert_eq!(progress.sent_frames.load(Ordering::SeqCst), 3);
                assert_eq!(progress.received_frames.load(Ordering::SeqCst), 3);
            }
            if matches!(finish, Finish::CancelPin) { assert!(spy.callback_cancelled.load(Ordering::SeqCst)); }
            if matches!(finish, Finish::WrongPin) {
                assert!(!progress.srp_verified.load(Ordering::SeqCst));
                assert_eq!(progress.received_frames.load(Ordering::SeqCst), 3);
            }
            if matches!(finish, Finish::ControllerIdentity(_)) {
                assert!(finish.mode().invalid_controller_identity());
                assert!(progress.srp_verified.load(Ordering::SeqCst));
                assert!(progress.m5_original_signature_verified.load(Ordering::SeqCst));
                assert!(progress.m5_identity_mutated.load(Ordering::SeqCst));
                assert!(progress.m5_aead_verified.load(Ordering::SeqCst));
                assert!(progress.m5_adapted.load(Ordering::SeqCst));
                assert_eq!(progress.sent_frames.load(Ordering::SeqCst), 4);
                assert_eq!(progress.received_frames.load(Ordering::SeqCst), 3);
                assert_eq!(peer_report.trailing, 0);
                // Counts every delivered byte, even from invalid/partial frames
                // consumed before phone validation fails or during EOF draining.
                // Three validated responses end at M4; no later byte is allowed.
                assert_eq!(counts.read_bytes.load(Ordering::SeqCst),
                    progress.received_bytes.load(Ordering::SeqCst), "identity rejection must precede any M6 byte");
                assert!(!unsafe { tetherless_pairing_host_cancel(token.pointer()) });
            }
            if matches!(finish, Finish::TamperM5) {
                assert!(progress.srp_verified.load(Ordering::SeqCst));
                assert!(progress.m5_adapted.load(Ordering::SeqCst));
                assert_eq!(progress.sent_frames.load(Ordering::SeqCst), 4);
            }
        }
    }
    assert!(cancellation.0);
    if matches!(finish, Finish::CallerWaitExpired) { assert!(cancellation.1); }
    assert!(progress.sent_bytes.load(Ordering::SeqCst) <= 131_072);
    assert!(progress.received_bytes.load(Ordering::SeqCst) <= 131_072);
    // Reentry cannot perform I/O or invoke a callback even with an invalid FD.
    let mut output = [0x55; TETHERLESS_HOST_RECORD_CAPACITY]; let mut len = 99;
    assert_eq!(unsafe { tetherless_pairing_host_accept_fd(token.pointer(), -1, 1000,
        Some(copy_pin), context, output.as_mut_ptr(), output.len(), &mut len) }, TetherlessPairingHostAlreadyUsed);
    assert_eq!(len, 0); assert!(output.iter().all(|b| *b == 0));
    let snapshot = (spy.calls.load(Ordering::SeqCst), counts.polls.load(Ordering::SeqCst));
    std::thread::sleep(Duration::from_millis(20));
    assert_eq!(snapshot, (spy.calls.load(Ordering::SeqCst), counts.polls.load(Ordering::SeqCst)));
    assert!(!spy.invalid.load(Ordering::SeqCst));
    drop(token); // All native/peer/cancel work has joined; context remains alive.
}

#[test]
fn actual_host_success_preserves_identity_and_joins_all_owners() {
    for choppy in [false, true] { transcript(Finish::Success, choppy, false); }
}
#[test]
fn actual_host_rejects_wrong_pin_and_tampered_authenticated_m5() {
    for finish in [Finish::WrongPin, Finish::TamperM5] { transcript(finish, true, false); }
}
#[test]
fn actual_host_pin_callback_cancel_copies_pin_and_joins() { transcript(Finish::CancelPin, true, false); }
#[test]
fn actual_host_late_cancel_after_verified_srp_joins() { transcript(Finish::CancelLate, true, false); }
#[test]
fn actual_host_deadline_after_verified_srp_joins() { transcript(Finish::DeadlineLate, true, false); }
#[test]
fn caller_wait_expiry_requires_cancel_and_actual_native_join() { transcript(Finish::CallerWaitExpired, true, false); }
#[test]
fn output_capacity_rejection_does_not_consume_successful_token() { transcript(Finish::Success, true, true); }

#[test]
fn actual_host_rejects_valid_aead_invalid_controller_signature() {
    transcript(Finish::ControllerIdentity(Mode::InvalidControllerSignature), true, false);
}
#[test]
fn actual_host_rejects_valid_aead_wrong_controller_public_key() {
    transcript(Finish::ControllerIdentity(Mode::WrongControllerPublicKey), true, false);
}
#[test]
fn actual_host_rejects_valid_aead_malformed_or_mismatched_controller_identity() {
    for mode in [Mode::ShortControllerSignature, Mode::LongControllerSignature,
                 Mode::WrongControllerSignatureType, Mode::ShortControllerPublicKey,
                 Mode::MismatchedControllerAccount, Mode::WrongControllerAccountType] {
        transcript(Finish::ControllerIdentity(mode), true, false);
    }
}
