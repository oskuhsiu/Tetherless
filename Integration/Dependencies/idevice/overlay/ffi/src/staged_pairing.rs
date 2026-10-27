// Copyright (c) 2026 Tetherless contributors. MIT; see the retained idevice license.
// Additive validation-stage API for the pinned idevice source. This is NOT a
// complete staged-record acquisition API: tunnel/TLS/RSD/check-in remain separate.

use std::{
    io::Cursor,
    sync::{Arc, atomic::{AtomicBool, AtomicU8, Ordering}},
    time::Duration,
};

use plist::stream::{BinaryReader, Event, XmlReader};
use tokio::{io::{AsyncRead, AsyncReadExt, AsyncWrite, AsyncWriteExt}, sync::Notify};

use crate::house_arrest::HouseArrestClientHandle;

const OPEN: u8 = 0;
const CANCELLED: u8 = 1;
const FINISHED: u8 = 2;
pub(crate) const CHALLENGE_LEN: usize = 32;
const MAX_PATH: usize = 160;
const MAX_BUNDLE: usize = 255;
const MAX_PLIST: usize = 4096;
pub(crate) const MAX_DURATION_MS: u32 = 10_000;
const MAX_AFC_REQUESTS: usize = 36; // open, <=33 reads, close
const MAX_WIRE_BYTES: usize = 16384;
const AFC_MAGIC: u64 = 0x4141504c36414643;
const PATH_PREFIX: &[u8] = b"Library/TetherlessPairingValidation/";
const PATH_SUFFIX: &[u8] = b".challenge";

/// A fixed result code; no peer-provided text, challenge or record is returned.
#[repr(u32)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum TetherlessPairingValidationResult {
    TetherlessPairingValidationOk = 0,
    TetherlessPairingValidationInvalidArgument = 1,
    TetherlessPairingValidationCancelled = 2,
    TetherlessPairingValidationTimedOut = 3,
    TetherlessPairingValidationProtocol = 4,
    TetherlessPairingValidationIo = 5,
    TetherlessPairingValidationMismatch = 6,
    TetherlessPairingValidationAlreadyUsed = 7,
    TetherlessPairingValidationBudget = 8,
}
use TetherlessPairingValidationResult::*;
pub(crate) type Result<T> = std::result::Result<T, TetherlessPairingValidationResult>;

pub(crate) struct Control {
    state: AtomicU8,
    started: AtomicBool,
    wake: Notify,
}

impl Control {
    fn new() -> Self {
        Self { state: AtomicU8::new(OPEN), started: AtomicBool::new(false), wake: Notify::new() }
    }

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

    // Called only AFTER the operation future (and its stream) have been dropped.
    // Cancellation and completion have a single atomic linearization point.
    pub(crate) fn finish(&self, result: TetherlessPairingValidationResult) -> TetherlessPairingValidationResult {
        match self.state.compare_exchange(OPEN, FINISHED, Ordering::SeqCst, Ordering::SeqCst) {
            Ok(_) => result,
            Err(CANCELLED) => TetherlessPairingValidationCancelled,
            Err(_) => TetherlessPairingValidationAlreadyUsed,
        }
    }
}

/// Single-use cancellation context. Keep alive until validate and all concurrent
/// cancel calls return. No background validation task is spawned by this API.
pub struct TetherlessPairingValidationHandle(Arc<Control>);

pub(crate) unsafe fn begin(handle: *const TetherlessPairingValidationHandle) -> Result<Arc<Control>> {
    if handle.is_null() { return Err(TetherlessPairingValidationInvalidArgument); }
    let control = Arc::clone(&unsafe { &*handle }.0);
    if control.started.swap(true, Ordering::SeqCst) { return Err(TetherlessPairingValidationAlreadyUsed); }
    Ok(control)
}

#[unsafe(no_mangle)]
pub extern "C" fn tetherless_pairing_validation_new() -> *mut TetherlessPairingValidationHandle {
    Box::into_raw(Box::new(TetherlessPairingValidationHandle(Arc::new(Control::new()))))
}

/// Request cancellation. True means cancellation won (or was already requested),
/// false means completion already won. This is NOT the join; validate's return is.
/// # Safety
/// The handle must be live, allocated by new, and not concurrently freed.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_validation_cancel(
    handle: *const TetherlessPairingValidationHandle,
) -> bool {
    !handle.is_null() && unsafe { &*handle }.0.cancel()
}

/// # Safety
/// No validate/cancel call may be active, or start later, on this handle. Join
/// validate before freeing, even after cancellation or an application timeout.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_validation_free(
    handle: *mut TetherlessPairingValidationHandle,
) {
    if !handle.is_null() { drop(unsafe { Box::from_raw(handle) }); }
}

/// Consume an exclusively owned authenticated House Arrest connection, vend the
/// running app's container, and compare a fresh 32-byte local challenge. Nothing
/// is promoted or persisted. Only bundle ID and independent random path are sent.
///
/// This stage has an overall 1..=10000ms deadline (including remote file close),
/// <=16384 wire bytes per direction, <=36 AFC requests, a 4096-byte plist frame,
/// and fixed AFC buffers. It does NOT bound prior tunnel/TLS/RSD acquisition or
/// the internal buffers/tasks of a caller-supplied transport. Product use stays
/// gated until those stages have independently bounded, joined ownership too.
///
/// The local challenge must be freshly random, independently named with 64 hex
/// characters at Library/TetherlessPairingValidation/<name>.challenge, protected
/// and excluded from backups. It proves access to this app container, not device
/// hardware identity; copying or relaying a challenge can satisfy it.
///
/// # Safety
/// Run on a non-Tokio FFI worker thread. If client and *client are non-null,
/// ownership is transferred and *client is set to null on EVERY return path,
/// including invalid arguments. The input client must be an unused House Arrest
/// handle allocated by this library, with exclusive ownership of its connection.
/// All non-null input byte pointers must be valid for their supplied lengths and
/// remain immutable until return. The cancellation handle must remain alive until
/// this function AND concurrent cancel calls return. This function's return joins
/// the validation-stage future and drops its consumed stream. It does NOT join a
/// caller's transport worker. The caller must separately join every transport
/// worker before releasing its gateway/adapter and mutation lease. In particular,
/// pinned jktcp AdapterHandle::close is enqueue-only and is not such a join.
#[unsafe(no_mangle)]
pub unsafe extern "C" fn tetherless_pairing_validate_house_arrest(
    client: *mut *mut HouseArrestClientHandle,
    cancellation: *const TetherlessPairingValidationHandle,
    bundle_id: *const u8,
    bundle_len: usize,
    relative_path: *const u8,
    path_len: usize,
    expected: *const u8,
    expected_len: usize,
    timeout_ms: u32,
) -> TetherlessPairingValidationResult {
    if client.is_null() || unsafe { *client }.is_null() {
        return TetherlessPairingValidationInvalidArgument;
    }
    let owned = unsafe { Box::from_raw(*client) };
    unsafe { *client = std::ptr::null_mut(); }
    if cancellation.is_null() || bundle_id.is_null() || relative_path.is_null() || expected.is_null()
        || !(1..=MAX_BUNDLE).contains(&bundle_len) || path_len > MAX_PATH
        || expected_len != CHALLENGE_LEN || !(1..=MAX_DURATION_MS).contains(&timeout_ms)
    { return TetherlessPairingValidationInvalidArgument; }
    let control = match unsafe { begin(cancellation) } { Ok(c) => c, Err(e) => return e };
    let bundle = unsafe { std::slice::from_raw_parts(bundle_id, bundle_len) };
    let path = unsafe { std::slice::from_raw_parts(relative_path, path_len) };
    let expected = unsafe { std::slice::from_raw_parts(expected, expected_len) };
    if !valid_bundle(bundle) || !valid_path(path) {
        drop(owned);
        return control.finish(TetherlessPairingValidationInvalidArgument);
    }
    let Some(stream) = owned.0.idevice.get_socket() else {
        return control.finish(TetherlessPairingValidationInvalidArgument);
    };
    tracing::subscriber::with_default(tracing::subscriber::NoSubscriber::default(), || {
        crate::run_sync_local(run_owned(stream, control, bundle, path, expected, timeout_ms))
    })
}

pub(crate) fn valid_bundle(bundle: &[u8]) -> bool {
    !bundle.is_empty() && bundle.len() <= MAX_BUNDLE
        && bundle.split(|b| *b == b'.').all(|s| !s.is_empty())
        && bundle.iter().all(|b| b.is_ascii_alphanumeric() || *b == b'.' || *b == b'-')
}

pub(crate) fn valid_path(path: &[u8]) -> bool {
    path.len() == PATH_PREFIX.len() + 64 + PATH_SUFFIX.len()
        && path.starts_with(PATH_PREFIX) && path.ends_with(PATH_SUFFIX)
        && path[PATH_PREFIX.len()..PATH_PREFIX.len() + 64].iter()
            .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(b))
}

async fn run_owned<S: AsyncRead + AsyncWrite + Unpin>(
    mut stream: S, control: Arc<Control>, bundle: &[u8], path: &[u8], expected: &[u8], timeout_ms: u32,
) -> TetherlessPairingValidationResult {
    run_controlled(async move { validate_stream(&mut stream, bundle, path, expected).await }, control, timeout_ms).await
}

pub(crate) async fn run_controlled<F: std::future::Future<Output = Result<()>>>(
    operation: F, control: Arc<Control>, timeout_ms: u32,
) -> TetherlessPairingValidationResult {
    let outcome = {
        // Own all resources inside this future, so every select branch drops it before
        // finish. There is no abort-only JoinHandle, detached task or async Drop.
        let job = operation;
        tokio::pin!(job);
        tokio::select! {
            biased;
            _ = control.cancelled() => TetherlessPairingValidationCancelled,
            _ = tokio::time::sleep(Duration::from_millis(timeout_ms.into())) => TetherlessPairingValidationTimedOut,
            result = &mut job => result.err().unwrap_or(TetherlessPairingValidationOk),
        }
    };
    control.finish(outcome)
}

#[derive(Default)]
struct Budget { sent: usize, received: usize, requests: usize }

impl Budget {
    fn charge(counter: &mut usize, amount: usize) -> Result<()> {
        *counter = counter.checked_add(amount).ok_or(TetherlessPairingValidationBudget)?;
        if *counter > MAX_WIRE_BYTES { return Err(TetherlessPairingValidationBudget); }
        Ok(())
    }
    async fn write<S: AsyncWrite + Unpin + ?Sized>(&mut self, s: &mut S, bytes: &[u8]) -> Result<()> {
        Self::charge(&mut self.sent, bytes.len())?;
        s.write_all(bytes).await.map_err(|_| TetherlessPairingValidationIo)
    }
    async fn read<S: AsyncRead + Unpin + ?Sized>(&mut self, s: &mut S, bytes: &mut [u8]) -> Result<()> {
        Self::charge(&mut self.received, bytes.len())?;
        s.read_exact(bytes).await.map(|_| ()).map_err(|_| TetherlessPairingValidationIo)
    }
}

// Use the locked plist 1.8.0 streaming decoder, not Value/from_bytes (which can
// expand repeated binary references into a tree). Input is at most 4096 bytes;
// BinaryReader checks each length against that input before reserving and rejects
// cycles. Reject a nested event immediately, before descending. XML scalar sizes
// are bounded by input and its predefined-entity-only decoder. No peer text exits.
fn vend_succeeded(bytes: &[u8]) -> bool {
    plist_field_equals(bytes, "Status", "Complete")
}

fn plist_field_equals(bytes: &[u8], field: &str, value: &str) -> bool {
    if bytes.is_empty() || bytes.len() > MAX_PLIST { return false; }
    if bytes.starts_with(b"bplist00") {
        bounded_plist_events(BinaryReader::new(Cursor::new(bytes)), field, value)
    } else {
        if !xml_entities_are_known(bytes) { return false; }
        bounded_plist_events(XmlReader::new(bytes), field, value)
    }
}

// plist 1.8.0 silently discards unknown named entities inside string/key values.
// Reject them before its existing XML decoder; this is an entity-reference
// preflight, not a replacement XML parser. Apply conservatively even in comments
// and declarations: these protocol responses require no custom named entities.
pub(crate) fn xml_entities_are_known(bytes: &[u8]) -> bool {
    let mut offset = 0;
    while let Some(next) = bytes[offset..].iter().position(|b| *b == b'&') {
        offset += next + 1;
        let tail = &bytes[offset..];
        let Some(end) = tail.iter().take(13).position(|b| *b == b';') else { return false; };
        let reference = &tail[..end];
        if !matches!(reference, b"amp" | b"lt" | b"gt" | b"quot" | b"apos") {
            let (digits, radix) = if let Some(n) = reference.strip_prefix(b"#x") { (n, 16) }
                else if let Some(n) = reference.strip_prefix(b"#") { (n, 10) }
                else { return false; };
            if digits.is_empty() || !digits.iter().all(|b| if radix == 16 { b.is_ascii_hexdigit() } else { b.is_ascii_digit() }) {
                return false;
            }
            let value = std::str::from_utf8(digits).ok().and_then(|n| u32::from_str_radix(n, radix).ok());
            if !matches!(value, Some(0x9 | 0xa | 0xd | 0x20..=0xd7ff | 0xe000..=0xfffd | 0x10000..=0x10ffff)) {
                return false;
            }
        }
        offset += end + 1;
    }
    true
}

fn bounded_plist_events(
    mut events: impl Iterator<Item = std::result::Result<Event<'static>, plist::Error>>,
    field: &str, expected_value: &str,
) -> bool {
    match events.next() {
        Some(Ok(Event::StartDictionary(None | Some(0..=8)))) => (),
        _ => return false,
    }
    let mut complete = false;
    for _ in 0..=8 {
        let key = match events.next() {
            Some(Ok(Event::EndCollection)) => return complete && events.next().is_none(),
            Some(Ok(Event::String(key))) if key.len() <= 256 => key,
            _ => return false,
        };
        if key == "Error" { return false; }
        let event = match events.next() {
            Some(Ok(value)) => value,
            _ => return false,
        };
        let string = match &event {
            Event::String(value) if value.len() <= 1024 => Some(value.as_ref()),
            Event::Boolean(_) | Event::Integer(_) | Event::Real(_) | Event::Date(_) | Event::Uid(_) => None,
            Event::Data(value) if value.len() <= 1024 => None,
            _ => return false, // reject nested collections before descending
        };
        if key == field {
            if complete || string != Some(expected_value) { return false; }
            complete = true;
        }
    }
    false
}

async fn validate_stream<S: AsyncRead + AsyncWrite + Unpin + ?Sized>(
    stream: &mut S, bundle: &[u8], path: &[u8], expected: &[u8],
) -> Result<()> {
    validate_with_budget(stream, &mut Budget::default(), bundle, path, expected).await
}

// For the composite's borrowed, already-authenticated service stream. Nothing is
// boxed or spawned, so the composite owns the adapter and all its polling.
pub(crate) async fn validate_borrowed<S: AsyncRead + AsyncWrite + Unpin + ?Sized>(
    stream: &mut S, bundle: &[u8], path: &[u8], expected: &[u8],
) -> Result<()> {
    let mut budget = Budget::default();
    let checkin = b"<?xml version=\"1.0\" encoding=\"UTF-8\"?><plist version=\"1.0\"><dict><key>Label</key><string></string><key>ProtocolVersion</key><string>2</string><key>Request</key><string>RSDCheckin</string></dict></plist>";
    budget.write(stream, &(checkin.len() as u32).to_be_bytes()).await?;
    budget.write(stream, checkin).await?;
    stream.flush().await.map_err(|_| TetherlessPairingValidationIo)?;
    for expected_request in ["RSDCheckin", "StartService"] {
        let mut bytes = [0u8; MAX_PLIST];
        let length = read_plist_frame(stream, &mut budget, &mut bytes).await?;
        if !plist_field_equals(&bytes[..length], "Request", expected_request) {
            return Err(TetherlessPairingValidationProtocol);
        }
    }
    validate_with_budget(stream, &mut budget, bundle, path, expected).await
}

async fn read_plist_frame<S: AsyncRead + Unpin + ?Sized>(
    stream: &mut S, budget: &mut Budget, response: &mut [u8; MAX_PLIST],
) -> Result<usize> {
    let mut length = [0u8; 4];
    budget.read(stream, &mut length).await?;
    let length = u32::from_be_bytes(length) as usize;
    if length == 0 || length > MAX_PLIST { return Err(TetherlessPairingValidationBudget); }
    budget.read(stream, &mut response[..length]).await?;
    Ok(length)
}

async fn validate_with_budget<S: AsyncRead + AsyncWrite + Unpin + ?Sized>(
    stream: &mut S, budget: &mut Budget, bundle: &[u8], path: &[u8], expected: &[u8],
) -> Result<()> {
    if !valid_bundle(bundle) || !valid_path(path) || expected.len() != CHALLENGE_LEN {
        return Err(TetherlessPairingValidationInvalidArgument);
    }
    let prefix = b"<?xml version=\"1.0\" encoding=\"UTF-8\"?><plist version=\"1.0\"><dict><key>Command</key><string>VendContainer</string><key>Identifier</key><string>";
    let suffix = b"</string></dict></plist>";
    let mut request = [0u8; 1024];
    let size = prefix.len() + bundle.len() + suffix.len();
    request[..prefix.len()].copy_from_slice(prefix);
    request[prefix.len()..prefix.len() + bundle.len()].copy_from_slice(bundle);
    request[prefix.len() + bundle.len()..size].copy_from_slice(suffix);
    budget.write(stream, &(size as u32).to_be_bytes()).await?;
    budget.write(stream, &request[..size]).await?;
    stream.flush().await.map_err(|_| TetherlessPairingValidationIo)?;
    let mut response = [0u8; MAX_PLIST];
    let length = read_plist_frame(stream, budget, &mut response).await?;
    if !vend_succeeded(&response[..length]) { return Err(TetherlessPairingValidationProtocol); }

    let mut open = [0u8; 8 + MAX_PATH + 1];
    open[..8].copy_from_slice(&1u64.to_le_bytes()); // AFC read-only; never create/write
    open[8..8 + path.len()].copy_from_slice(path);
    let reply = afc_exchange(stream, budget, 0x0d, &open[..8 + path.len() + 1], 8).await?;
    if reply.op != 0x0e || reply.header_len != 8 || reply.len != 8 {
        return Err(TetherlessPairingValidationProtocol);
    }
    let fd: [u8; 8] = reply.body[..8].try_into().map_err(|_| TetherlessPairingValidationProtocol)?;
    let mut received = [0u8; CHALLENGE_LEN + 1];
    let mut used = 0;
    loop {
        let mut read = [0u8; 16];
        read[..8].copy_from_slice(&fd);
        read[8..].copy_from_slice(&((received.len() - used) as u64).to_le_bytes());
        let reply = afc_exchange(stream, budget, 0x0f, &read, received.len() - used).await?;
        if reply.op == 1 && reply.header_len == 8 && reply.len == 8 {
            let status = u64::from_le_bytes(reply.body[..8].try_into().map_err(|_| TetherlessPairingValidationProtocol)?);
            if status == 14 { break; } // AFC EndOfData
            return Err(TetherlessPairingValidationProtocol);
        }
        if reply.op != 2 || reply.header_len != 0 { return Err(TetherlessPairingValidationProtocol); }
        if reply.len == 0 { break; }
        received[used..used + reply.len].copy_from_slice(&reply.body[..reply.len]);
        used += reply.len;
        if used == received.len() { break; }
    }
    // Close is part of the same deadline and cancellation scope. If it stalls or
    // fails, success is impossible; dropping the session reclaims its remote FD.
    let reply = afc_exchange(stream, budget, 0x14, &fd, 8).await?;
    if reply.op != 1 || reply.header_len != 8 || reply.len != 8 || reply.body[..8] != [0u8; 8] {
        return Err(TetherlessPairingValidationProtocol);
    }
    let mut difference = 0u8;
    for i in 0..CHALLENGE_LEN { difference |= received[i] ^ expected[i]; }
    if used == CHALLENGE_LEN && difference == 0 { Ok(()) }
    else { Err(TetherlessPairingValidationMismatch) }
}

struct AfcReply { op: u64, header_len: usize, len: usize, body: [u8; CHALLENGE_LEN + 1] }

// Peer lengths are validated as u64 BEFORE conversion, subtraction or reading a
// body. Fixed arrays prevent peer-controlled allocation, including malformed u64s.
fn decode_afc_header(header: &[u8; 40], number: u64, limit: usize) -> Result<(u64, usize, usize)> {
    let field = |offset: usize| u64::from_le_bytes(header[offset..offset + 8].try_into().unwrap());
    let entire = field(8);
    let head = field(16);
    let op = field(32);
    if field(0) != AFC_MAGIC || field(24) != number || head < 40 || entire < head {
        return Err(TetherlessPairingValidationProtocol);
    }
    let maximum = if op == 1 { 8 } else { limit };
    if entire > 40 + maximum as u64 || head > entire || entire > 40 + (CHALLENGE_LEN + 1) as u64 {
        return Err(TetherlessPairingValidationBudget);
    }
    Ok((op, (head - 40) as usize, (entire - 40) as usize))
}

async fn afc_exchange<S: AsyncRead + AsyncWrite + Unpin + ?Sized>(
    stream: &mut S, budget: &mut Budget, op: u64, arguments: &[u8], limit: usize,
) -> Result<AfcReply> {
    if budget.requests >= MAX_AFC_REQUESTS || arguments.len() > 8 + MAX_PATH + 1 || limit > CHALLENGE_LEN + 1 {
        return Err(TetherlessPairingValidationBudget);
    }
    let number = budget.requests as u64;
    budget.requests += 1;
    let mut header = [0u8; 40];
    for (i, value) in [AFC_MAGIC, (40 + arguments.len()) as u64, (40 + arguments.len()) as u64, number, op].iter().enumerate() {
        header[i * 8..i * 8 + 8].copy_from_slice(&value.to_le_bytes());
    }
    budget.write(stream, &header).await?;
    budget.write(stream, arguments).await?;
    stream.flush().await.map_err(|_| TetherlessPairingValidationIo)?;
    budget.read(stream, &mut header).await?;
    let (op, header_len, len) = decode_afc_header(&header, number, limit)?;
    let mut result = AfcReply { op, header_len, len, body: [0u8; CHALLENGE_LEN + 1] };
    budget.read(stream, &mut result.body[..len]).await?;
    Ok(result)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        pin::Pin,
        sync::{Mutex, atomic::AtomicUsize},
        task::{Context, Poll},
    };
    use tokio::io::ReadBuf;

    const EXPECTED: [u8; 32] = [0xd7; 32];
    const BUNDLE: &[u8] = b"com.example.fixture";

    fn path() -> Vec<u8> {
        [PATH_PREFIX, &[b'a'; 64], PATH_SUFFIX].concat()
    }

    fn plist_response(binary: bool) -> Vec<u8> {
        // Normal locked-library serializers, not a hand-invented XML grammar.
        let value = plist::Value::Dictionary([
            (String::from("Status"), plist::Value::String("Complete".into())),
        ].into_iter().collect());
        let mut bytes = Vec::new();
        if binary { value.to_writer_binary(&mut bytes).unwrap(); }
        else { value.to_writer_xml(&mut bytes).unwrap(); }
        bytes
    }

    fn vend(binary: bool) -> Vec<u8> {
        let bytes = plist_response(binary);
        [&(bytes.len() as u32).to_be_bytes()[..], &bytes].concat()
    }

    fn checkin(binary: bool) -> Vec<u8> {
        let mut result = Vec::new();
        for request in ["RSDCheckin", "StartService"] {
            let value = plist::Value::Dictionary([
                (String::from("Request"), plist::Value::String(request.into())),
                (String::from("EnableServiceSSL"), plist::Value::Boolean(false)),
                (String::from("ProtocolVersion"), plist::Value::Integer(2.into())),
            ].into_iter().collect());
            let mut bytes = Vec::new();
            if binary { value.to_writer_binary(&mut bytes).unwrap(); }
            else { value.to_writer_xml(&mut bytes).unwrap(); }
            result.extend_from_slice(&(bytes.len() as u32).to_be_bytes());
            result.extend_from_slice(&bytes);
        }
        result
    }

    fn frame(number: u64, op: u64, head_len: usize, body: &[u8]) -> Vec<u8> {
        let mut out = Vec::new();
        for value in [AFC_MAGIC, (40 + body.len()) as u64, (40 + head_len) as u64, number, op] {
            out.extend_from_slice(&value.to_le_bytes());
        }
        out.extend_from_slice(body);
        out
    }

    fn fixture(data: &[u8], binary: bool, pieces: usize) -> Vec<u8> {
        let mut bytes = vend(binary);
        bytes.extend(frame(0, 0x0e, 8, &17u64.to_le_bytes()));
        let mut number = 1;
        for chunk in data.chunks(pieces) {
            bytes.extend(frame(number, 2, 0, chunk));
            number += 1;
        }
        if data.len() < 33 {
            bytes.extend(frame(number, 1, 8, &14u64.to_le_bytes()));
            number += 1;
        }
        bytes.extend(frame(number, 1, 8, &0u64.to_le_bytes()));
        bytes
    }

    #[derive(Debug)]
    struct FixtureStream {
        input: Vec<u8>,
        cursor: usize,
        max_chunk: usize,
        stall_at_end: bool,
        written: Arc<Mutex<Vec<u8>>>,
        drops: Arc<AtomicUsize>,
        body_polls: Arc<AtomicUsize>,
        stall_writes: bool,
        trace_reads: bool,
    }

    impl FixtureStream {
        fn new(input: Vec<u8>) -> Self {
            Self {
                input, cursor: 0, max_chunk: usize::MAX, stall_at_end: false,
                written: Arc::new(Mutex::new(Vec::new())),
                drops: Arc::new(AtomicUsize::new(0)),
                body_polls: Arc::new(AtomicUsize::new(0)),
                stall_writes: false, trace_reads: false,
            }
        }
    }

    impl Drop for FixtureStream {
        fn drop(&mut self) { self.drops.fetch_add(1, Ordering::SeqCst); }
    }

    impl AsyncRead for FixtureStream {
        fn poll_read(mut self: Pin<&mut Self>, _cx: &mut Context<'_>, buf: &mut ReadBuf<'_>) -> Poll<std::io::Result<()>> {
            if self.cursor == self.input.len() {
                self.body_polls.fetch_add(1, Ordering::SeqCst);
                if self.stall_at_end { return Poll::Pending; }
            }
            let len = (self.input.len() - self.cursor).min(buf.remaining()).min(self.max_chunk);
            if self.trace_reads { tracing::info!("fixture sensitive bytes: {:?}", &self.input[self.cursor..self.cursor + len]); }
            buf.put_slice(&self.input[self.cursor..self.cursor + len]);
            self.cursor += len;
            Poll::Ready(Ok(()))
        }
    }

    impl AsyncWrite for FixtureStream {
        fn poll_write(self: Pin<&mut Self>, _cx: &mut Context<'_>, bytes: &[u8]) -> Poll<std::io::Result<usize>> {
            if self.stall_writes { return Poll::Pending; }
            self.written.lock().unwrap().extend_from_slice(bytes);
            Poll::Ready(Ok(bytes.len()))
        }
        fn poll_flush(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<std::io::Result<()>> { Poll::Ready(Ok(())) }
        fn poll_shutdown(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<std::io::Result<()>> { Poll::Ready(Ok(())) }
    }

    async fn run_fixture(stream: FixtureStream) -> TetherlessPairingValidationResult {
        run_owned(stream, Arc::new(Control::new()), BUNDLE, &path(), &EXPECTED, 100).await
    }

    #[tokio::test]
    async fn xml_and_binary_positive_fragmented_fixtures_close_and_drop() {
        for binary in [false, true] {
            for pieces in [1, 7, 32] {
                let mut stream = FixtureStream::new(fixture(&EXPECTED, binary, pieces));
                stream.max_chunk = 1; // partial transport reads at every byte
                let drops = Arc::clone(&stream.drops);
                let written = Arc::clone(&stream.written);
                assert_eq!(run_fixture(stream).await, TetherlessPairingValidationOk);
                assert_eq!(drops.load(Ordering::SeqCst), 1);
                let wire = written.lock().unwrap();
                assert!(!wire.windows(EXPECTED.len()).any(|w| w == EXPECTED));
                let plist_len = u32::from_be_bytes(wire[..4].try_into().unwrap()) as usize;
                let value = plist::Value::from_reader(Cursor::new(&wire[4..4 + plist_len])).unwrap();
                assert_eq!(value.as_dictionary().unwrap().get("Command").unwrap().as_string(), Some("VendContainer"));
                let mut cursor = 4 + plist_len;
                let mut ops = Vec::new();
                while cursor < wire.len() {
                    let len = u64::from_le_bytes(wire[cursor + 8..cursor + 16].try_into().unwrap()) as usize;
                    let op = u64::from_le_bytes(wire[cursor + 32..cursor + 40].try_into().unwrap());
                    ops.push(op);
                    if op == 0x0d {
                        assert_eq!(&wire[cursor + 40..cursor + 48], &1u64.to_le_bytes());
                        assert_eq!(&wire[cursor + 48..cursor + len - 1], &path());
                        assert_eq!(wire[cursor + len - 1], 0);
                    }
                    cursor += len;
                }
                assert_eq!(ops[0], 0x0d);
                assert_eq!(ops.last(), Some(&0x14));
                assert!(ops[1..ops.len() - 1].iter().all(|op| *op == 0x0f));
                assert!(ops.len() <= MAX_AFC_REQUESTS);
                assert!(wire.len() <= MAX_WIRE_BYTES);
            }
        }
    }

    #[tokio::test]
    async fn borrowed_route_includes_both_checkins_in_the_same_scope() {
        for binary in [false, true] {
            let bytes = [checkin(binary), fixture(&EXPECTED, binary, 8)].concat();
            let mut stream = FixtureStream::new(bytes);
            assert_eq!(validate_borrowed(&mut stream, BUNDLE, &path(), &EXPECTED).await, Ok(()));
            let wire = stream.written.lock().unwrap();
            let len = u32::from_be_bytes(wire[..4].try_into().unwrap()) as usize;
            assert!(plist_field_equals(&wire[4..4 + len], "Request", "RSDCheckin"));
        }
    }

    #[tokio::test]
    async fn borrowed_checkin_stall_cancels_and_bad_request_rejects() {
        let mut stream = FixtureStream::new(vec![0, 0, 0, 100]);
        stream.stall_at_end = true;
        let drops = Arc::clone(&stream.drops);
        let control = Arc::new(Control::new());
        let operation = async move { validate_borrowed(&mut stream, BUNDLE, &path(), &EXPECTED).await };
        let (result, _) = tokio::join!(
            run_controlled(operation, Arc::clone(&control), 100),
            async { tokio::task::yield_now().await; assert!(control.cancel()); },
        );
        assert_eq!(result, TetherlessPairingValidationCancelled);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
        let mut stream = FixtureStream::new(vend(true)); // Status response cannot stand in for Request
        assert_eq!(validate_borrowed(&mut stream, BUNDLE, &path(), &EXPECTED).await, Err(TetherlessPairingValidationProtocol));
    }

    #[tokio::test]
    async fn blocked_write_is_also_cancellable() {
        let mut stream = FixtureStream::new(vec![]);
        stream.stall_writes = true;
        let drops = Arc::clone(&stream.drops);
        let control = Arc::new(Control::new());
        let path = path();
        let (result, _) = tokio::join!(
            run_owned(stream, Arc::clone(&control), BUNDLE, &path, &EXPECTED, 100),
            async { tokio::task::yield_now().await; assert!(control.cancel()); },
        );
        assert_eq!(result, TetherlessPairingValidationCancelled);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn mismatch_short_and_extra_byte_never_succeed() {
        for data in [vec![0xd6; 32], vec![0xd7; 31], vec![0xd7; 33], vec![]] {
            let stream = FixtureStream::new(fixture(&data, true, 33));
            let drops = Arc::clone(&stream.drops);
            assert_eq!(run_fixture(stream).await, TetherlessPairingValidationMismatch);
            assert_eq!(drops.load(Ordering::SeqCst), 1);
        }
    }

    #[tokio::test]
    async fn cancellation_drops_every_suspended_stage_before_return() {
        let full = fixture(&EXPECTED, true, 32);
        let vend_len = vend(true).len();
        // response prefix/body, open header/body, read header/body, EOF, close
        for cut in [0, 2, 4, vend_len, vend_len + 40, vend_len + 48,
            vend_len + 48 + 40, full.len() - 48, full.len() - 8]
        {
            let mut stream = FixtureStream::new(full[..cut].to_vec());
            stream.stall_at_end = true;
            let drops = Arc::clone(&stream.drops);
            let written = Arc::clone(&stream.written);
            let control = Arc::new(Control::new());
            let path = path();
            let (result, _) = tokio::join!(
                run_owned(stream, Arc::clone(&control), BUNDLE, &path, &EXPECTED, 100),
                async { tokio::task::yield_now().await; assert!(control.cancel()); },
            );
            assert_eq!(result, TetherlessPairingValidationCancelled);
            assert_eq!(drops.load(Ordering::SeqCst), 1);
            let count = written.lock().unwrap().len();
            tokio::task::yield_now().await;
            assert_eq!(written.lock().unwrap().len(), count); // no continuing I/O
        }
    }

    #[tokio::test]
    async fn deadline_includes_remote_close_and_drops_before_return() {
        let mut bytes = fixture(&EXPECTED, false, 32);
        bytes.truncate(bytes.len() - 48); // remote close never responds
        let mut stream = FixtureStream::new(bytes);
        stream.stall_at_end = true;
        let drops = Arc::clone(&stream.drops);
        let result = run_owned(stream, Arc::new(Control::new()), BUNDLE, &path(), &EXPECTED, 1).await;
        assert_eq!(result, TetherlessPairingValidationTimedOut);
        assert_eq!(drops.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn pre_cancel_does_no_io_and_late_cancel_cannot_rewrite_success() {
        let stream = FixtureStream::new(fixture(&EXPECTED, false, 32));
        let written = Arc::clone(&stream.written);
        let control = Arc::new(Control::new());
        assert!(control.cancel());
        assert_eq!(run_owned(stream, control, BUNDLE, &path(), &EXPECTED, 100).await, TetherlessPairingValidationCancelled);
        assert!(written.lock().unwrap().is_empty());
        let control = Arc::new(Control::new());
        assert_eq!(run_owned(FixtureStream::new(fixture(&EXPECTED, true, 32)), Arc::clone(&control), BUNDLE, &path(), &EXPECTED, 100).await, TetherlessPairingValidationOk);
        assert!(!control.cancel());
    }

    #[test]
    fn cancel_success_race_has_exactly_one_winner() {
        for _ in 0..128 {
            let control = Arc::new(Control::new());
            let barrier = Arc::new(std::sync::Barrier::new(2));
            let c = Arc::clone(&control);
            let b = Arc::clone(&barrier);
            let cancel = std::thread::spawn(move || { b.wait(); c.cancel() });
            barrier.wait();
            let finished = control.finish(TetherlessPairingValidationOk);
            let cancelled = cancel.join().unwrap();
            assert_eq!(cancelled, finished == TetherlessPairingValidationCancelled);
        }
    }

    #[tokio::test]
    async fn cancellation_during_operation_drop_wins_before_result_publication() {
        struct CancelOnDrop {
            control: Arc<Control>,
            dropped: Arc<AtomicBool>,
            accepted: Arc<AtomicBool>,
        }
        impl std::future::Future for CancelOnDrop {
            type Output = Result<()>;
            fn poll(self: Pin<&mut Self>, _cx: &mut Context<'_>) -> Poll<Self::Output> { Poll::Ready(Ok(())) }
        }
        impl Drop for CancelOnDrop {
            fn drop(&mut self) {
                self.accepted.store(self.control.cancel(), Ordering::SeqCst);
                self.dropped.store(true, Ordering::SeqCst);
            }
        }
        let control = Arc::new(Control::new());
        let dropped = Arc::new(AtomicBool::new(false));
        let accepted = Arc::new(AtomicBool::new(false));
        let operation = CancelOnDrop { control: Arc::clone(&control), dropped: Arc::clone(&dropped), accepted: Arc::clone(&accepted) };
        assert_eq!(run_controlled(operation, control, 100).await, TetherlessPairingValidationCancelled);
        assert!(dropped.load(Ordering::SeqCst));
        assert!(accepted.load(Ordering::SeqCst));
    }

    #[tokio::test]
    async fn malicious_plist_lengths_reject_before_body_read() {
        for length in [0u32, (MAX_PLIST + 1) as u32, u32::MAX] {
            let mut stream = FixtureStream::new(length.to_be_bytes().to_vec());
            stream.stall_at_end = true;
            let polls = Arc::clone(&stream.body_polls);
            assert_eq!(run_fixture(stream).await, TetherlessPairingValidationBudget);
            assert_eq!(polls.load(Ordering::SeqCst), 0);
        }
    }

    #[tokio::test]
    async fn malicious_afc_lengths_reject_before_body_read() {
        for (entire, head, number) in [(u64::MAX, 40, 0), (39, 40, 0), (48, u64::MAX, 0), (48, 39, 0), (49, 48, 0), (48, 48, 1)] {
            let mut bytes = vend(false);
            for word in [AFC_MAGIC, entire, head, number, 0x0e] { bytes.extend(word.to_le_bytes()); }
            let mut stream = FixtureStream::new(bytes);
            stream.stall_at_end = true;
            let polls = Arc::clone(&stream.body_polls);
            let result = run_fixture(stream).await;
            assert!(matches!(result, TetherlessPairingValidationProtocol | TetherlessPairingValidationBudget));
            assert_eq!(polls.load(Ordering::SeqCst), 0);
        }
    }

    #[test]
    fn fixed_afc_decoder_rejects_malformed_headers_without_allocating() {
        // This function operates solely on [u8;40], integer checks and a tuple:
        // no Vec, String, allocator, transport or peer-sized buffer exists here.
        for i in 0..40 {
            let valid = frame(0, 0x0e, 8, &17u64.to_le_bytes());
            let mut h: [u8; 40] = valid[..40].try_into().unwrap();
            h[i] = 0xff;
            let result = decode_afc_header(&h, 0, 8);
            if let Ok((_, head, len)) = result { assert!(head <= len && len <= 8); }
        }
    }

    #[test]
    fn parser_rejects_nested_duplicate_error_and_excessive_events() {
        for xml in [
            "<plist><dict><key>Status</key><dict><key>Status</key><string>Complete</string></dict></dict></plist>",
            "<plist><dict><key>Status</key><string>Complete</string><key>Status</key><string>Complete</string></dict></plist>",
            "<plist><dict><key>Status</key><string>Complete</string><key>Error</key><string>private peer error</string></dict></plist>",
            "<plist><dict><key>Status</key><string>Failed</string></dict></plist>",
            "<plist><dict><key>Status</key><string>Complete</string></dict><dict/></plist>",
            "not a plist",
        ] { assert!(!vend_succeeded(xml.as_bytes())); }
        let mut value = plist::Dictionary::new();
        value.insert("Status".into(), plist::Value::String("Complete".into()));
        for i in 0..8 { value.insert(format!("Other{i}"), plist::Value::String("value".into())); }
        let mut bytes = Vec::new();
        plist::Value::Dictionary(value).to_writer_binary(&mut bytes).unwrap();
        assert!(!vend_succeeded(&bytes));
        let mut malicious = plist_response(true);
        let length = malicious.len();
        malicious[length - 24..length - 16].copy_from_slice(&u64::MAX.to_be_bytes());
        assert!(!vend_succeeded(&malicious));
    }

    #[test]
    fn unknown_entities_cannot_be_silently_removed_from_protocol_values() {
        let prefix = "<plist><dict><key>Status</key><string>";
        let suffix = "</string></dict></plist>";
        for value in ["Com&unknown;plete", "Complete&missing;", "Com&;plete", "Com&#0;plete", "Com&#xD800;plete", "Com&#1114112;plete", "Complete&"] {
            assert!(!vend_succeeded(format!("{prefix}{value}{suffix}").as_bytes()));
        }
        assert!(vend_succeeded(format!("{prefix}Com&#112;lete{suffix}").as_bytes()));
        assert!(vend_succeeded(format!("{prefix}Com&#x70;lete{suffix}").as_bytes()));
        assert!(xml_entities_are_known(b"&amp;&lt;&gt;&quot;&apos;&#9;&#10;&#13;"));
        assert!(!xml_entities_are_known(b"<!-- &custom; -->"));
    }

    #[test]
    fn path_bundle_and_budget_reject_bad_inputs() {
        assert!(valid_path(&path()));
        for bad in [b"../secret".as_slice(), b"Library/file", b"/Library/file", b"Library/TetherlessPairingValidation/../secret"] {
            assert!(!valid_path(bad));
        }
        for bad in [b"".as_slice(), b"com.<bad", b"com..app", b"com.app\0", b"a/b"] { assert!(!valid_bundle(bad)); }
        let mut counter = MAX_WIRE_BYTES;
        assert_eq!(Budget::charge(&mut counter, 1), Err(TetherlessPairingValidationBudget));
        let mut counter = usize::MAX;
        assert_eq!(Budget::charge(&mut counter, 1), Err(TetherlessPairingValidationBudget));
    }

    #[test]
    fn ffi_consumes_handle_and_drops_on_invalid_or_reused_context() {
        for reused in [false, true] {
            let stream = FixtureStream::new(vec![]);
            let drops = Arc::clone(&stream.drops);
            let idevice = idevice::Idevice::new(Box::new(stream), "");
            let mut client = Box::into_raw(Box::new(HouseArrestClientHandle(idevice::house_arrest::HouseArrestClient::new(idevice))));
            let cancellation = tetherless_pairing_validation_new();
            if reused { unsafe { &*cancellation }.0.started.store(true, Ordering::SeqCst); }
            let path = path();
            let result = unsafe { tetherless_pairing_validate_house_arrest(
                &mut client, cancellation, BUNDLE.as_ptr(), BUNDLE.len(), path.as_ptr(), path.len(),
                EXPECTED.as_ptr(), if reused { EXPECTED.len() } else { 0 }, 100,
            ) };
            assert_eq!(result, if reused { TetherlessPairingValidationAlreadyUsed } else { TetherlessPairingValidationInvalidArgument });
            assert!(client.is_null());
            assert_eq!(drops.load(Ordering::SeqCst), 1);
            unsafe { tetherless_pairing_validation_free(cancellation); }
        }
    }

    #[derive(Clone)]
    struct LogCapture(Arc<Mutex<Vec<u8>>>);
    impl std::io::Write for LogCapture {
        fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes); Ok(bytes.len())
        }
        fn flush(&mut self) -> std::io::Result<()> { Ok(()) }
    }

    #[test]
    fn ffi_suppresses_nested_transport_tracing_without_global_logger_changes() {
        let captured = LogCapture(Arc::new(Mutex::new(Vec::new())));
        let writer = captured.clone();
        let subscriber = tracing_subscriber::fmt().with_max_level(tracing::Level::TRACE)
            .with_writer(move || writer.clone()).without_time().finish();
        tracing::subscriber::with_default(subscriber, || {
            let mut stream = FixtureStream::new(fixture(&EXPECTED, true, 32));
            stream.trace_reads = true;
            let mut client = Box::into_raw(Box::new(HouseArrestClientHandle(
                idevice::house_arrest::HouseArrestClient::new(idevice::Idevice::new(Box::new(stream), "")),
            )));
            let cancellation = tetherless_pairing_validation_new();
            let path = path();
            let result = unsafe { tetherless_pairing_validate_house_arrest(
                &mut client, cancellation, BUNDLE.as_ptr(), BUNDLE.len(), path.as_ptr(), path.len(),
                EXPECTED.as_ptr(), EXPECTED.len(), 100,
            ) };
            assert_eq!(result, TetherlessPairingValidationOk);
            assert!(client.is_null());
            unsafe { tetherless_pairing_validation_free(cancellation); }
        });
        assert!(captured.0.lock().unwrap().is_empty());
    }
}
