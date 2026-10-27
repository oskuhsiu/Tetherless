// Copyright (c) 2026 Tetherless contributors. MIT; see the retained idevice license.
//! Bounded device-initiated host handshake over an exclusively caller-owned TCP FD.
//! This API does not create a listener, advertise, persist, validate the current
//! phone, or promote a pairing record. Those remain separately owned operations.

use std::{
    ffi::c_void,
    future::Future,
    os::fd::{AsRawFd, FromRawFd},
    sync::{Arc, Mutex, atomic::{AtomicBool, AtomicU8, Ordering}},
    time::Duration,
};

use idevice::remote_pairing::{PairableHost, PairableHostInfo, RpPairingFile};
use tokio::sync::Notify;

pub const TETHERLESS_HOST_RECORD_CAPACITY: usize = 4096;
pub const TETHERLESS_HOST_TXT_CAPACITY: usize = 2048;
const MAX_DURATION_MS: u32 = 120_000;
const OPEN: u8 = 0;
const CANCELLED: u8 = 1;
const FINISHED: u8 = 2;

#[repr(u32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TetherlessPairingHostResult {
    TetherlessPairingHostOk = 0,
    TetherlessPairingHostInvalidArgument = 1,
    TetherlessPairingHostCancelled = 2,
    TetherlessPairingHostTimedOut = 3,
    TetherlessPairingHostProtocol = 4,
    TetherlessPairingHostIo = 5,
    TetherlessPairingHostAlreadyUsed = 7,
    TetherlessPairingHostBudget = 8,
}
use TetherlessPairingHostResult::*;
type Result<T> = std::result::Result<T, TetherlessPairingHostResult>;

#[repr(C)]
pub struct TetherlessPairingHostAdvertisement {
    pub identifier: [u8; 64],
    pub identifier_len: usize,
    pub txt_plist: [u8; TETHERLESS_HOST_TXT_CAPACITY],
    pub txt_plist_len: usize,
    pub host_alt_irk: [u8; 16],
}
impl TetherlessPairingHostAdvertisement {
    fn empty() -> Self {
        Self { identifier: [0; 64], identifier_len: 0,
               txt_plist: [0; TETHERLESS_HOST_TXT_CAPACITY], txt_plist_len: 0, host_alt_irk: [0; 16] }
    }
}

struct Control { state: AtomicU8, started: AtomicBool, wake: Notify }
impl Control {
    fn new() -> Self { Self { state: AtomicU8::new(OPEN), started: AtomicBool::new(false), wake: Notify::new() } }
    fn cancel(&self) -> bool {
        match self.state.compare_exchange(OPEN, CANCELLED, Ordering::SeqCst, Ordering::SeqCst) {
            Ok(_) => { self.wake.notify_waiters(); true }
            Err(CANCELLED) => true,
            Err(_) => false,
        }
    }
    async fn cancelled(&self) {
        loop {
            let notified = self.wake.notified();
            tokio::pin!(notified);
            notified.as_mut().enable();
            if self.state.load(Ordering::SeqCst) == CANCELLED { return; }
            notified.await;
        }
    }
    fn finish<T>(&self, result: Result<T>) -> Result<T> {
        match self.state.compare_exchange(OPEN, FINISHED, Ordering::SeqCst, Ordering::SeqCst) {
            Ok(_) => result,
            Err(CANCELLED) => Err(TetherlessPairingHostCancelled),
            Err(_) => Err(TetherlessPairingHostAlreadyUsed),
        }
    }
}

struct Prepared { record: RpPairingFile, info: PairableHostInfo }
/// One-shot identity and cancellation ownership. A handle is never reused.
pub struct TetherlessPairingHostHandle { control: Arc<Control>, prepared: Mutex<Option<Prepared>> }

fn prepared(name: &str, model: &str) -> Result<(Prepared, TetherlessPairingHostAdvertisement)> {
    let info = PairableHostInfo::generate(name, model);
    let record = info.generate_staged_record();
    let mut txt = plist::Dictionary::new();
    for (key, value) in info.mdns_txt_records(record.identifier()) { txt.insert(key, plist::Value::String(value)); }
    let mut bytes = Vec::new();
    plist::to_writer_xml(&mut bytes, &plist::Value::Dictionary(txt)).map_err(|_| TetherlessPairingHostProtocol)?;
    if bytes.len() > TETHERLESS_HOST_TXT_CAPACITY || record.identifier().len() > 64 {
        return Err(TetherlessPairingHostBudget);
    }
    let mut advertisement = TetherlessPairingHostAdvertisement::empty();
    advertisement.identifier_len = record.identifier().len();
    advertisement.identifier[..advertisement.identifier_len].copy_from_slice(record.identifier().as_bytes());
    advertisement.txt_plist_len = bytes.len();
    advertisement.txt_plist[..bytes.len()].copy_from_slice(&bytes);
    advertisement.host_alt_irk = info.alt_irk;
    Ok((Prepared { record, info }, advertisement))
}

fn valid_text(bytes: &[u8], maximum: usize) -> Option<&str> {
    if bytes.is_empty() || bytes.len() > maximum { return None; }
    let value = std::str::from_utf8(bytes).ok()?;
    (!value.chars().any(char::is_control)).then_some(value)
}

/// Prepare bounded identity/TXT bytes for the caller's platform Bonjour service.
/// No network, listener, mDNS daemon, file or worker is created here.
///
/// # Safety
/// All pointers must be valid for the stated lengths / output types, nonaliasing,
/// and immutable except the two outputs. Outputs are cleared on every return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_host_prepare(
    name: *const u8, name_len: usize, model: *const u8, model_len: usize,
    out_handle: *mut *mut TetherlessPairingHostHandle,
    out_advertisement: *mut TetherlessPairingHostAdvertisement,
) -> TetherlessPairingHostResult {
    if !out_handle.is_null() { unsafe { *out_handle = std::ptr::null_mut(); } }
    if !out_advertisement.is_null() { unsafe { out_advertisement.write(TetherlessPairingHostAdvertisement::empty()); } }
    if name.is_null() || model.is_null() || out_handle.is_null() || out_advertisement.is_null()
        || !(1..=128).contains(&name_len) || !(1..=64).contains(&model_len)
    { return TetherlessPairingHostInvalidArgument; }
    let Some(name) = valid_text(unsafe { std::slice::from_raw_parts(name, name_len) }, 128) else {
        return TetherlessPairingHostInvalidArgument;
    };
    let Some(model) = valid_text(unsafe { std::slice::from_raw_parts(model, model_len) }, 64) else {
        return TetherlessPairingHostInvalidArgument;
    };
    if !model.starts_with("Mac") || !model.bytes().all(|b| b.is_ascii_alphanumeric() || b == b',') {
        return TetherlessPairingHostInvalidArgument;
    }
    match prepared(name, model) {
        Ok((value, advertisement)) => {
            let handle = Box::new(TetherlessPairingHostHandle {
                control: Arc::new(Control::new()), prepared: Mutex::new(Some(value)),
            });
            unsafe { out_advertisement.write(advertisement); *out_handle = Box::into_raw(handle); }
            TetherlessPairingHostOk
        }
        Err(error) => error,
    }
}

/// True means cancellation won / was already requested. This is not a join.
/// # Safety
/// Keep the handle alive until this call and the handshake call return.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_host_cancel(handle: *const TetherlessPairingHostHandle) -> bool {
    !handle.is_null() && unsafe { &*handle }.control.cancel()
}

/// # Safety
/// No handshake or cancel call may be active or start later. Wait for the blocking
/// handshake to return before freeing; a timeout on the caller is not completion.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_host_free(handle: *mut TetherlessPairingHostHandle) {
    if !handle.is_null() { drop(unsafe { Box::from_raw(handle) }); }
}

pub type TetherlessPairingHostPinCallback = Option<extern "C" fn(*const u8, usize, *mut c_void)>;
struct PinContext { callback: TetherlessPairingHostPinCallback, context: *mut c_void }
// Deliberately not Send/Sync: the callback runs only on this blocking FFI worker.

fn duplicate_connected_tcp(fd: i32) -> Result<std::net::TcpStream> {
    // Do not change O_NONBLOCK on the caller's shared open-file description.
    let mut socket_type: libc::c_int = 0;
    let mut socket_type_len = std::mem::size_of::<libc::c_int>() as libc::socklen_t;
    if unsafe { libc::getsockopt(fd, libc::SOL_SOCKET, libc::SO_TYPE,
        &mut socket_type as *mut _ as *mut c_void, &mut socket_type_len) } != 0
        || socket_type != libc::SOCK_STREAM
    { return Err(TetherlessPairingHostInvalidArgument); }
    let flags = unsafe { libc::fcntl(fd, libc::F_GETFL) };
    if flags < 0 || flags & libc::O_NONBLOCK == 0 { return Err(TetherlessPairingHostInvalidArgument); }
    let copied = unsafe { libc::fcntl(fd, libc::F_DUPFD_CLOEXEC, 0) };
    if copied < 0 { return Err(TetherlessPairingHostIo); }
    let stream = unsafe { std::net::TcpStream::from_raw_fd(copied) };
    if stream.peer_addr().is_err() || stream.local_addr().is_err() {
        return Err(TetherlessPairingHostInvalidArgument);
    }
    Ok(stream)
}

async fn run_controlled<T, F: Future<Output = Result<T>>>(
    job: F, control: Arc<Control>, deadline: tokio::time::Instant,
) -> Result<T> {
    let result = {
        let operation = job;
        tokio::pin!(operation);
        tokio::select! {
            biased;
            _ = control.cancelled() => Err(TetherlessPairingHostCancelled),
            _ = tokio::time::sleep_until(deadline) => Err(TetherlessPairingHostTimedOut),
            result = &mut operation => result,
        }
    }; // operation and all of its owned transport/record state drop before finish
    let result = if tokio::time::Instant::now() >= deadline { Err(TetherlessPairingHostTimedOut) } else { result };
    control.finish(result)
}

async fn handshake(
    stream: std::net::TcpStream, prepared: Prepared, control: Arc<Control>,
    deadline: tokio::time::Instant, pin: PinContext,
) -> Result<Vec<u8>> {
    let stream = tokio::net::TcpStream::from_std(stream).map_err(|_| TetherlessPairingHostIo)?;
    handshake_stream(stream, prepared, control, deadline, pin).await
}

async fn handshake_stream<S: idevice::ReadWrite>(
    stream: S, mut prepared: Prepared, control: Arc<Control>,
    deadline: tokio::time::Instant, pin: PinContext,
) -> Result<Vec<u8>> {
    let read_control = Arc::clone(&control);
    let mut host = PairableHost::new_bounded_stream_checked(stream, prepared.info,
        move || read_control.state.load(Ordering::SeqCst) == OPEN && tokio::time::Instant::now() < deadline);
    host.accept(&mut prepared.record, |value| async move {
        if control.state.load(Ordering::SeqCst) != OPEN || tokio::time::Instant::now() >= deadline { return; }
        if value.len() == 6 && value.bytes().all(|b| b.is_ascii_digit()) {
            if let Some(callback) = pin.callback { callback(value.as_ptr(), value.len(), pin.context); }
        }
    }).await.map_err(|_| TetherlessPairingHostProtocol)?;
    let bytes = prepared.record.to_bytes();
    if bytes.is_empty() || bytes.len() > TETHERLESS_HOST_RECORD_CAPACITY { return Err(TetherlessPairingHostBudget); }
    Ok(bytes)
}

/// Perform exactly one bounded SRP host handshake. Caller owns platform Bonjour,
/// listening/accepted socket cleanup, session generation and the mutation lease.
/// The accepted FD is duplicated; this call owns/drops only its duplicate.
///
/// Frames <=16384 bytes, <=4 messages each direction, OPACK depth<=16/nodes<=512/
/// expanded scalar bytes<=65536; 1..=384-byte G3072 public value in (0,N) and exact 64-byte M3 proof. No pinless mode.
/// Deadline is 1..=120000ms; fixed-cost crypto and a callback cannot be preempted
/// mid-poll. The callback MUST copy the six ASCII bytes and return promptly.
/// It may race cancellation; caller generation checks must discard stale UI work.
/// No callback occurs after this function returns. Return joins all owned work;
/// no native listener, advertiser or per-request background task is created.
///
/// # Safety
/// Run on a non-Tokio FFI worker. fd must be connected, nonblocking TCP and remain
/// owned/open by the caller until return. Duplication shares the socket and open-file
/// status flags: neither side may change flags/options, shut down, or perform
/// competing I/O during this call. We never set O_NONBLOCK; the caller sets it
/// before entry. F_DUPFD_CLOEXEC changes only the new descriptor's close-on-exec
/// flag. Close the caller's original descriptor after this function returns.
///
/// The caller must reserve ownership before enqueueing native entry, reject new
/// entries during teardown, and keep the handle, output buffers and callback
/// context valid until this call AND every in-flight cancel call return. The
/// callback may request cancellation, but must not free/reenter accept_fd or
/// wait synchronously on its own worker. A queued call counts as in-flight. Output buffer must
/// be writable for exactly 4096 bytes; out_len must be writable. Pointers must not
/// alias. On any failure output length stays zero; serialized record bytes are
/// copied only after native completion/cancellation arbitration. Staged bytes
/// still require separate current-container validation and atomic promotion.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_host_accept_fd(
    handle: *const TetherlessPairingHostHandle, fd: i32, timeout_ms: u32,
    pin_callback: TetherlessPairingHostPinCallback, pin_context: *mut c_void,
    out_record: *mut u8, record_capacity: usize, out_len: *mut usize,
) -> TetherlessPairingHostResult {
    if !out_len.is_null() { unsafe { *out_len = 0; } }
    if handle.is_null() || out_record.is_null() || out_len.is_null() || pin_callback.is_none()
        || record_capacity != TETHERLESS_HOST_RECORD_CAPACITY || !(1..=MAX_DURATION_MS).contains(&timeout_ms)
    { return TetherlessPairingHostInvalidArgument; }
    unsafe { std::ptr::write_bytes(out_record, 0, TETHERLESS_HOST_RECORD_CAPACITY); }
    let handle = unsafe { &*handle };
    let control = Arc::clone(&handle.control);
    if control.started.swap(true, Ordering::SeqCst) { return TetherlessPairingHostAlreadyUsed; }
    let prepared = handle.prepared.lock().unwrap_or_else(|p| p.into_inner()).take();
    let Some(prepared) = prepared else { return TetherlessPairingHostAlreadyUsed; };
    if control.state.load(Ordering::SeqCst) == CANCELLED {
        drop(prepared);
        return TetherlessPairingHostCancelled;
    }
    let stream = match duplicate_connected_tcp(fd) {
        Ok(stream) => stream,
        Err(error) => { drop(prepared); return control.finish::<()>(Err(error)).unwrap_err(); }
    };
    let callback = PinContext { callback: pin_callback, context: pin_context };
    let result = tracing::subscriber::with_default(tracing::subscriber::NoSubscriber::default(), || {
        crate::run_sync_local(async move {
            let deadline = tokio::time::Instant::now() + Duration::from_millis(timeout_ms.into());
            let job = handshake(stream, prepared, Arc::clone(&control), deadline, callback);
            run_controlled(job, control, deadline).await
        })
    });
    match result {
        Ok(bytes) => {
            unsafe { std::ptr::copy_nonoverlapping(bytes.as_ptr(), out_record, bytes.len()); *out_len = bytes.len(); }
            TetherlessPairingHostOk
        }
        Err(error) => error,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::AtomicUsize;

    struct DropCount(Arc<AtomicUsize>);
    impl Drop for DropCount { fn drop(&mut self) { self.0.fetch_add(1, Ordering::SeqCst); } }

    #[tokio::test]
    async fn cancellation_before_start_drops_owned_job_before_return() {
        let control = Arc::new(Control::new()); control.cancel();
        let dropped = Arc::new(AtomicUsize::new(0));
        let marker = DropCount(Arc::clone(&dropped));
        let job = async move { let _marker = marker; std::future::pending::<Result<()>>().await };
        assert_eq!(run_controlled(job, control, tokio::time::Instant::now() + Duration::from_secs(1)).await,
                   Err(TetherlessPairingHostCancelled));
        assert_eq!(dropped.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn deadline_drops_owned_job_and_does_not_succeed() {
        let control = Arc::new(Control::new());
        let dropped = Arc::new(AtomicUsize::new(0));
        let marker = DropCount(Arc::clone(&dropped));
        let job = async move { let _marker = marker; std::future::pending::<Result<()>>().await };
        assert_eq!(run_controlled(job, control, tokio::time::Instant::now() + Duration::from_millis(1)).await,
                   Err(TetherlessPairingHostTimedOut));
        assert_eq!(dropped.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn cancellation_beats_ready_success_and_late_cancel_cannot_reopen_finish() {
        let control = Arc::new(Control::new()); control.cancel();
        assert_eq!(run_controlled(async { Ok(vec![1u8]) }, Arc::clone(&control),
                   tokio::time::Instant::now() + Duration::from_secs(1)).await, Err(TetherlessPairingHostCancelled));
        let control = Arc::new(Control::new());
        assert_eq!(run_controlled(async { Ok(()) }, Arc::clone(&control),
                   tokio::time::Instant::now() + Duration::from_secs(1)).await, Ok(()));
        assert!(!control.cancel());
    }

    #[test]
    fn prepare_bounds_are_pure_and_outputs_contain_no_pairing_private_key() {
        let (_, metadata) = prepared("synthetic host", "Mac17,7").unwrap();
        assert_eq!(metadata.identifier_len, 36);
        let dict: plist::Dictionary = plist::from_bytes(&metadata.txt_plist[..metadata.txt_plist_len]).unwrap();
        assert!(!dict.contains_key("private_key"));
        assert_eq!(dict.len(), 7);
        assert!(valid_text(b"bad\0name", 128).is_none());
        assert!(valid_text(&[b'x'; 129], 128).is_none());
    }

    extern "C" fn count_pin(_: *const u8, _: usize, context: *mut c_void) {
        let calls = unsafe { &*(context as *const AtomicUsize) };
        calls.fetch_add(1, Ordering::SeqCst);
    }

    #[test]
    fn public_token_is_single_use_and_cancelled_outputs_stay_empty() {
        let name = b"synthetic host"; let model = b"Mac17,7";
        let mut handle = std::ptr::null_mut();
        let mut advertisement = TetherlessPairingHostAdvertisement::empty();
        unsafe {
            assert_eq!(tetherless_pairing_host_prepare(name.as_ptr(), name.len(), model.as_ptr(), model.len(),
                       &mut handle, &mut advertisement), TetherlessPairingHostOk);
            assert!(tetherless_pairing_host_cancel(handle));
            let mut output = [0x55; TETHERLESS_HOST_RECORD_CAPACITY]; let mut length = 99;
            let calls = AtomicUsize::new(0);
            let context = &calls as *const AtomicUsize as *mut c_void;
            assert_eq!(tetherless_pairing_host_accept_fd(handle, -1, 1000, Some(count_pin),
                context, output.as_mut_ptr(), output.len(), &mut length), TetherlessPairingHostCancelled);
            assert_eq!(length, 0); assert!(output.iter().all(|b| *b == 0));
            assert_eq!(tetherless_pairing_host_accept_fd(handle, -1, 1000, Some(count_pin),
                context, output.as_mut_ptr(), output.len(), &mut length), TetherlessPairingHostAlreadyUsed);
            assert_eq!(calls.load(Ordering::SeqCst), 0);
            tetherless_pairing_host_free(handle);
        }
    }

    struct PinSpy { calls: AtomicUsize, alive: AtomicBool, invalid: AtomicBool, control: Arc<Control> }
    extern "C" fn cancel_from_pin(bytes: *const u8, length: usize, context: *mut c_void) {
        let spy = unsafe { &*(context as *const PinSpy) };
        // An extern-C callback must not unwind, even when this test detects a bug.
        let valid = spy.alive.load(Ordering::SeqCst) && !bytes.is_null() && length == 6
            && unsafe { std::slice::from_raw_parts(bytes, length) }.iter().all(u8::is_ascii_digit);
        if !valid { spy.invalid.store(true, Ordering::SeqCst); }
        spy.calls.fetch_add(1, Ordering::SeqCst);
        spy.control.cancel();
    }

    #[tokio::test]
    async fn actual_responder_pin_callback_may_cancel_and_stream_is_joined() {
        use tokio::io::AsyncWriteExt;
        let control = Arc::new(Control::new());
        let spy = Box::new(PinSpy { calls: AtomicUsize::new(0), alive: AtomicBool::new(true), invalid: AtomicBool::new(false), control: Arc::clone(&control) });
        let (mut peer, stream) = tokio::io::duplex(16_384);
        for bytes in [
            &br#"{"message":{"plain":{"_0":{"request":{"_0":{"handshake":{"_0":{}}}}}}}}"#[..],
            &br#"{"message":{"plain":{"_0":{"event":{"_0":{"pairingData":{"_0":{"data":"BgEB"}}}}}}}}"#[..],
        ] {
            peer.write_all(b"RPPairing").await.unwrap();
            peer.write_all(&(bytes.len() as u16).to_be_bytes()).await.unwrap();
            peer.write_all(bytes).await.unwrap();
        }
        let (prepared, _) = prepared("synthetic host", "Mac17,7").unwrap();
        let deadline = tokio::time::Instant::now() + Duration::from_secs(10);
        let context = &*spy as *const PinSpy as *mut c_void;
        let job = handshake_stream(stream, prepared, Arc::clone(&control), deadline,
                                  PinContext { callback: Some(cancel_from_pin), context });
        assert_eq!(run_controlled(job, control, deadline).await, Err(TetherlessPairingHostCancelled));
        assert_eq!(spy.calls.load(Ordering::SeqCst), 1);
        assert!(!spy.invalid.load(Ordering::SeqCst));
        spy.alive.store(false, Ordering::SeqCst);
        assert!(peer.write_all(b"late peer data").await.is_err());
        assert_eq!(spy.calls.load(Ordering::SeqCst), 1);
    }

    #[test]
    fn cancellation_and_completion_have_one_winner() {
        for _ in 0..64 {
            let control = Arc::new(Control::new());
            let (result, cancelled) = std::thread::scope(|scope| {
                let other = Arc::clone(&control);
                let cancel = scope.spawn(move || other.cancel());
                let result = control.finish(Ok(()));
                (result, cancel.join().unwrap())
            });
            if cancelled { assert_eq!(result, Err(TetherlessPairingHostCancelled)); }
            else { assert_eq!(result, Ok(())); }
        }
    }

    #[test]
    fn fd_duplicate_never_closes_the_caller_descriptor() {
        let listener = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let client = std::net::TcpStream::connect(listener.local_addr().unwrap()).unwrap();
        let (server, _) = listener.accept().unwrap();
        assert!(duplicate_connected_tcp(server.as_raw_fd()).is_err());
        server.set_nonblocking(true).unwrap();
        let flags = unsafe { libc::fcntl(server.as_raw_fd(), libc::F_GETFL) };
        let duplicate = duplicate_connected_tcp(server.as_raw_fd()).unwrap();
        assert_eq!(unsafe { libc::fcntl(duplicate.as_raw_fd(), libc::F_GETFL) }, flags);
        assert_ne!(unsafe { libc::fcntl(duplicate.as_raw_fd(), libc::F_GETFD) } & libc::FD_CLOEXEC, 0);
        drop(duplicate);
        assert_eq!(unsafe { libc::fcntl(server.as_raw_fd(), libc::F_GETFL) }, flags);
        assert!(server.peer_addr().is_ok());
        assert!(client.peer_addr().is_ok());
        assert!(duplicate_connected_tcp(listener.as_raw_fd()).is_err());
        let udp = std::net::UdpSocket::bind("127.0.0.1:0").unwrap();
        udp.connect("127.0.0.1:9").unwrap(); udp.set_nonblocking(true).unwrap();
        assert!(duplicate_connected_tcp(udp.as_raw_fd()).is_err());
    }
}
