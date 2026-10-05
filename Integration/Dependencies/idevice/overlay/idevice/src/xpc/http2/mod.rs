// Jackson Coxson

use frame::HttpFrame;
use std::collections::{HashMap, VecDeque};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tracing::{debug, warn};

use crate::{IdeviceError, ReadWrite};

pub mod frame;
pub use frame::Setting;

const HTTP2_MAGIC: &[u8] = "PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n".as_bytes();

/// HTTP/2 default initial flow-control window for both the connection and each
/// stream (RFC 7540 §6.9.2). The peer can raise the per-stream default via a
/// SETTINGS `InitialWindowSize`.
const DEFAULT_WINDOW: i64 = 65535;

const RSD_MAX_WIRE_BYTES: usize = 4 * 1024 * 1024;
const RSD_MAX_FRAMES: usize = 4096;
pub(super) const RSD_MAX_BUFFERED_BYTES: usize = 1024 * 1024;

#[derive(Debug)]
struct BoundedRsdState {
    wire_left: usize,
    frames_left: usize,
    cached_bytes: usize,
    // XPC partial buffers share this same retained-input budget.
    external_bytes: usize,
    data_flow_bytes: u32,
}

fn bounded_h2_error() -> IdeviceError {
    IdeviceError::UnexpectedResponse("invalid or over-budget RSD HTTP/2 connection".into())
}

#[derive(Debug)]
pub struct Http2Client<R: ReadWrite> {
    inner: R,
    bounded_rsd: Option<BoundedRsdState>,
    cache: HashMap<u32, VecDeque<Vec<u8>>>,
    /// How many payload octets we may still send on the connection as a whole
    /// before the peer must replenish it with a connection-level WINDOW_UPDATE.
    conn_send_window: i64,
    /// Per-stream remaining send window. Lazily seeded to `peer_initial_window`.
    stream_send_windows: HashMap<u32, i64>,
    /// The peer's current SETTINGS `InitialWindowSize` — the window each *new*
    /// stream starts with.
    peer_initial_window: i64,
    /// Raw inbound bytes not yet parsed into a whole frame. Persisting this
    /// across reads keeps [`Self::pump`] cancellation-safe: a partially-received
    /// frame survives a dropped read.
    recv_buf: Vec<u8>,
    /// Streams we finished pushing an outbound file transfer on. The device
    /// resets them once it has the payload, so a RST_STREAM for one of these is
    /// normal completion rather than an error.
    finished_file_transfer_streams: std::collections::HashSet<u32>,
}

impl<R: ReadWrite> Http2Client<R> {
    /// Writes the magic and inits the caches
    pub async fn new(mut inner: R) -> Result<Self, IdeviceError> {
        inner.write_all(HTTP2_MAGIC).await?;
        inner.flush().await?;
        Ok(Self {
            inner,
            bounded_rsd: None,
            cache: HashMap::new(),
            conn_send_window: DEFAULT_WINDOW,
            stream_send_windows: HashMap::new(),
            peer_initial_window: DEFAULT_WINDOW,
            recv_buf: Vec::new(),
            finished_file_transfer_streams: std::collections::HashSet::new(),
        })
    }

    pub(super) async fn new_bounded_rsd(inner: R) -> Result<Self, IdeviceError> {
        let mut client = Self::new(inner).await?;
        client.bounded_rsd = Some(BoundedRsdState {
            wire_left: RSD_MAX_WIRE_BYTES,
            frames_left: RSD_MAX_FRAMES,
            cached_bytes: 0,
            external_bytes: 0,
            data_flow_bytes: 0,
        });
        Ok(client)
    }

    fn check_rsd_stream(&self, stream_id: u32) -> Result<(), IdeviceError> {
        if self.bounded_rsd.is_some() && !matches!(stream_id, 1 | 3) {
            return Err(bounded_h2_error());
        }
        Ok(())
    }

    pub(super) fn set_rsd_external_bytes(&mut self, bytes: usize) -> Result<(), IdeviceError> {
        if let Some(state) = self.bounded_rsd.as_mut() {
            let total = bytes.checked_add(state.cached_bytes)
                .and_then(|n| n.checked_add(self.recv_buf.len()))
                .ok_or_else(bounded_h2_error)?;
            if total > RSD_MAX_BUFFERED_BYTES { return Err(bounded_h2_error()); }
            state.external_bytes = bytes;
        }
        Ok(())
    }

    fn take_cached(&mut self, stream_id: u32) -> Option<Vec<u8>> {
        let result = self.cache.get_mut(&stream_id).and_then(|c| c.pop_front());
        if let (Some(state), Some(bytes)) = (self.bounded_rsd.as_mut(), result.as_ref()) {
            // Every bounded insertion is charged exactly once in pump().
            state.cached_bytes -= bytes.len();
        }
        result
    }

    /// Read the next whole frame, buffering raw bytes in `recv_buf` until one is
    /// complete. Cancellation-safe: the single `read` is cancel-safe (no bytes
    /// lost if the future is dropped on `Pending`), and any bytes already
    /// buffered persist in `self` for the next call.
    async fn next_frame(&mut self) -> Result<frame::Frame, IdeviceError> {
        loop {
            let parsed = if let Some(state) = self.bounded_rsd.as_ref() {
                if state.frames_left == 0 { return Err(bounded_h2_error()); }
                frame::Frame::parse_bounded_rsd(&self.recv_buf)?
            } else {
                frame::Frame::parse(&self.recv_buf)?
            };
            if let Some((frame, consumed)) = parsed {
                if let Some(state) = self.bounded_rsd.as_mut() {
                    state.frames_left -= 1;
                    state.data_flow_bytes = if matches!(&frame, frame::Frame::Data(_)) {
                        u32::try_from(consumed - 9).map_err(|_| bounded_h2_error())?
                    } else { 0 };
                }
                self.recv_buf.drain(..consumed);
                return Ok(frame);
            }
            let mut tmp = [0u8; 16384];
            let read_len = if let Some(state) = self.bounded_rsd.as_ref() {
                // Read only the missing header or body. Reject an oversize header
                // before accepting its body, and never read ahead into new frames.
                let target = frame::Frame::bounded_rsd_frame_len(&self.recv_buf)?.unwrap_or(9);
                let retained = state.external_bytes.checked_add(state.cached_bytes)
                    .and_then(|n| n.checked_add(self.recv_buf.len()))
                    .ok_or_else(bounded_h2_error)?;
                let available = RSD_MAX_BUFFERED_BYTES.checked_sub(retained)
                    .ok_or_else(bounded_h2_error)?;
                let len = (target - self.recv_buf.len()).min(tmp.len())
                    .min(state.wire_left).min(available);
                if len == 0 { return Err(bounded_h2_error()); }
                len
            } else { tmp.len() };
            let n = self.inner.read(&mut tmp[..read_len]).await?;
            if n == 0 {
                return Err(IdeviceError::UnexpectedResponse(
                    "HTTP/2 connection closed by peer".into(),
                ));
            }
            if let Some(state) = self.bounded_rsd.as_mut() {
                state.wire_left -= n;
            }
            self.recv_buf.extend_from_slice(&tmp[..n]);
        }
    }

    pub async fn set_settings(
        &mut self,
        settings: Vec<frame::Setting>,
        stream_id: u32,
    ) -> Result<(), IdeviceError> {
        let frame = frame::SettingsFrame {
            settings,
            stream_id,
            flags: 0,
        }
        .serialize();
        self.inner.write_all(&frame).await?;
        self.inner.flush().await?;
        Ok(())
    }

    pub async fn window_update(
        &mut self,
        increment_size: u32,
        stream_id: u32,
    ) -> Result<(), IdeviceError> {
        let frame = frame::WindowUpdateFrame {
            increment_size,
            stream_id,
        }
        .serialize();
        self.inner.write_all(&frame).await?;
        self.inner.flush().await?;
        Ok(())
    }

    pub async fn open_stream(&mut self, stream_id: u32) -> Result<(), IdeviceError> {
        self.check_rsd_stream(stream_id)?;
        // Sometimes Apple is silly and sends data to a stream that isn't open
        self.cache.entry(stream_id).or_default();
        let frame = frame::HeadersFrame { stream_id }.serialize();
        self.inner.write_all(&frame).await?;
        self.inner.flush().await?;
        Ok(())
    }

    pub async fn send(&mut self, payload: Vec<u8>, stream_id: u32) -> Result<(), IdeviceError> {
        self.send_inner(payload, stream_id, false).await
    }

    /// Sends `payload` and closes our half of the stream with END_STREAM.
    ///
    /// Used to finish an outbound file transfer: the device resets the stream
    /// once it has the payload, and [`Self::pump`] treats that reset as normal
    /// completion rather than an error.
    pub async fn send_end_stream(
        &mut self,
        payload: Vec<u8>,
        stream_id: u32,
    ) -> Result<(), IdeviceError> {
        self.check_rsd_stream(stream_id)?;
        self.finished_file_transfer_streams.insert(stream_id);
        self.send_inner(payload, stream_id, true).await
    }

    async fn send_inner(
        &mut self,
        payload: Vec<u8>,
        stream_id: u32,
        end_stream: bool,
    ) -> Result<(), IdeviceError> {
        self.check_rsd_stream(stream_id)?;
        if self.bounded_rsd.is_some() && payload.len() > RSD_MAX_BUFFERED_BYTES {
            return Err(bounded_h2_error());
        }
        const MAX_FRAME_SIZE: usize = 16384;
        let mut chunks = payload.chunks(MAX_FRAME_SIZE).peekable();
        // Always send at least one frame, even for an empty payload. An empty
        // DATA frame costs no flow-control window, so send it directly.
        if chunks.peek().is_none() {
            let frame = frame::DataFrame {
                stream_id,
                payload: Vec::new(),
                end_stream,
            }
            .serialize();
            self.inner.write_all(&frame).await?;
            self.inner.flush().await?;
            return Ok(());
        }
        while let Some(chunk) = chunks.next() {
            let need = chunk.len() as i64;
            // Respect the peer's flow-control window: a DATA frame must not exceed
            // either the connection-level or the stream-level send window, or the
            // peer aborts the connection with a GOAWAY (FLOW_CONTROL_ERROR). When
            // either window is exhausted, pump inbound frames until the peer grants
            // more room with a WINDOW_UPDATE. (Matters for large payloads like
            // pasteboard images; small ones fit in the initial 64 KiB window.)
            while self.conn_send_window < need || self.stream_send_window(stream_id) < need {
                self.pump().await?;
            }
            let frame = frame::DataFrame {
                stream_id,
                payload: chunk.to_vec(),
                // Only the last chunk carries END_STREAM.
                end_stream: end_stream && chunks.peek().is_none(),
            }
            .serialize();
            self.inner.write_all(&frame).await?;
            self.conn_send_window -= need;
            *self
                .stream_send_windows
                .get_mut(&stream_id)
                .expect("seeded by stream_send_window above") -= need;
        }
        self.inner.flush().await?;
        Ok(())
    }

    /// The remaining send window for `stream_id`, seeding it to the peer's current
    /// initial window size the first time we touch the stream.
    fn stream_send_window(&mut self, stream_id: u32) -> i64 {
        *self
            .stream_send_windows
            .entry(stream_id)
            .or_insert(self.peer_initial_window)
    }

    /// Reads the next buffered payload from whichever of `stream_ids` produces
    /// one first, returning it with the stream it came from.
    pub async fn read_any(&mut self, stream_ids: &[u32]) -> Result<(u32, Vec<u8>), IdeviceError> {
        for id in stream_ids {
            self.check_rsd_stream(*id)?;
            self.cache.entry(*id).or_default();
        }
        loop {
            for id in stream_ids {
                if let Some(d) = self.take_cached(*id) {
                    return Ok((*id, d));
                }
            }
            self.pump().await?;
        }
    }

    pub async fn read(&mut self, stream_id: u32) -> Result<Vec<u8>, IdeviceError> {
        self.check_rsd_stream(stream_id)?;
        self.cache.entry(stream_id).or_default();
        loop {
            // Return any frame already buffered for this stream.
            if let Some(d) = self.take_cached(stream_id) {
                return Ok(d);
            }
            self.pump().await?;
        }
    }

    /// Read and handle a single inbound frame: ack SETTINGS (applying any
    /// `InitialWindowSize` change), apply WINDOW_UPDATEs to our send windows,
    /// replenish the peer's receive window for inbound DATA and buffer that DATA
    /// by stream. GOAWAY / RST_STREAM surface as errors via [`frame::Frame::next`].
    async fn pump(&mut self) -> Result<(), IdeviceError> {
        let frame = self.next_frame().await?;
        match frame {
            frame::Frame::Settings(settings_frame) if settings_frame.flags != 1 => {
                // Adjust every existing stream's send window by the delta in the
                // new InitialWindowSize (RFC 7540 §6.9.2), then ack.
                for setting in &settings_frame.settings {
                    if let frame::Setting::InitialWindowSize(new) = setting {
                        let delta = *new as i64 - self.peer_initial_window;
                        self.peer_initial_window = *new as i64;
                        for w in self.stream_send_windows.values_mut() {
                            if self.bounded_rsd.is_some() {
                                let next = w.checked_add(delta).ok_or_else(bounded_h2_error)?;
                                if next > 0x7fff_ffff { return Err(bounded_h2_error()); }
                                *w = next;
                            } else {
                                *w += delta;
                            }
                        }
                    }
                }
                let ack = frame::SettingsFrame {
                    settings: Vec::new(),
                    stream_id: settings_frame.stream_id,
                    flags: 1,
                }
                .serialize();
                self.inner.write_all(&ack).await?;
                self.inner.flush().await?;
            }
            frame::Frame::Ping { payload, ack: false } => {
                // Only the bounded parser produces this variant.
                let mut ack = vec![0, 0, 8, 6, 1, 0, 0, 0, 0];
                ack.extend_from_slice(&payload);
                self.inner.write_all(&ack).await?;
                self.inner.flush().await?;
            }
            frame::Frame::WindowUpdate(w) => {
                if self.bounded_rsd.is_some() {
                    let current = if w.stream_id == 0 {
                        self.conn_send_window
                    } else {
                        self.check_rsd_stream(w.stream_id)?;
                        self.stream_send_window(w.stream_id)
                    };
                    let next = current.checked_add(i64::from(w.increment_size))
                        .ok_or_else(bounded_h2_error)?;
                    if next > 0x7fff_ffff { return Err(bounded_h2_error()); }
                }
                if w.stream_id == 0 {
                    self.conn_send_window += w.increment_size as i64;
                } else {
                    let initial = self.peer_initial_window;
                    *self
                        .stream_send_windows
                        .entry(w.stream_id)
                        .or_insert(initial) += w.increment_size as i64;
                }
            }
            frame::Frame::RstStream(rst) => {
                if self.finished_file_transfer_streams.remove(&rst.stream_id) {
                    debug!(
                        "Device reset finished file transfer stream {}",
                        rst.stream_id
                    );
                } else {
                    return Err(crate::xpc::errors::XpcError::HttpStreamReset.into());
                }
            }
            frame::Frame::Data(data_frame) => {
                debug!(
                    "Got data frame for {} with {} bytes",
                    data_frame.stream_id,
                    data_frame.payload.len()
                );

                let stream_id = data_frame.stream_id;
                self.check_rsd_stream(stream_id)?;
                let len = if let Some(state) = self.bounded_rsd.as_mut() {
                    let cached = state.cached_bytes.checked_add(data_frame.payload.len())
                        .ok_or_else(bounded_h2_error)?;
                    let retained = cached.checked_add(state.external_bytes)
                        .and_then(|n| n.checked_add(self.recv_buf.len()))
                        .ok_or_else(bounded_h2_error)?;
                    if retained > RSD_MAX_BUFFERED_BYTES { return Err(bounded_h2_error()); }
                    state.cached_bytes = cached;
                    state.data_flow_bytes // Includes DATA padding for HTTP/2 flow control.
                } else { data_frame.payload.len() as u32 };
                // Cache the payload BEFORE any await so a cancelled pump (the poll
                // tick interrupting `recv_push`) can never drop it.
                self.cache
                    .entry(stream_id)
                    .or_insert_with(|| {
                        // Apple sometimes sends data before the stream is "open".
                        warn!("Received message for stream ID {stream_id} not in cache");
                        VecDeque::new()
                    })
                    .push_back(data_frame.payload);
                if len > 0 {
                    // Replenish the peer's view of our receive window so it keeps
                    // sending (e.g. the rest of a large pasteboard image). Queue
                    // both WINDOW_UPDATE frames, then flush once: write_all on the
                    // tunnel stream queues a whole frame without suspending, so a
                    // cancellation can only land on the flush — by which point both
                    // frames are already queued (never a torn or dropped update).
                    let conn = frame::WindowUpdateFrame {
                        increment_size: len,
                        stream_id: 0,
                    }
                    .serialize();
                    let stream = frame::WindowUpdateFrame {
                        increment_size: len,
                        stream_id,
                    }
                    .serialize();
                    self.inner.write_all(&conn).await?;
                    self.inner.write_all(&stream).await?;
                    self.inner.flush().await?;
                }
            }
            _ => {
                // SETTINGS ack / HEADERS — nothing to do.
            }
        }
        Ok(())
    }
}


#[cfg(test)]
mod bounded_rsd_tests {
    use super::*;

    // Controlled transport fixtures only; they do not establish device acceptance.
    #[tokio::test]
    async fn bounded_connection_accepts_expected_root_data() {
        let (client, mut peer) = tokio::io::duplex(65536);
        let mut h2 = Http2Client::new_bounded_rsd(Box::pin(client)).await.unwrap();
        peer.write_all(&frame::DataFrame { stream_id: 1, payload: vec![7], end_stream: false }.serialize()).await.unwrap();
        assert_eq!(h2.read(1).await.unwrap(), [7]);
        assert_eq!(h2.bounded_rsd.as_ref().unwrap().cached_bytes, 0);
    }

    #[tokio::test]
    async fn bounded_connection_rejects_unexpected_channels() {
        let (client, mut peer) = tokio::io::duplex(65536);
        let mut h2 = Http2Client::new_bounded_rsd(Box::pin(client)).await.unwrap();
        peer.write_all(&frame::DataFrame { stream_id: 5, payload: vec![7], end_stream: false }.serialize()).await.unwrap();
        assert!(h2.read(1).await.is_err());
        assert!(h2.cache.keys().all(|id| matches!(id, 1 | 3)));
    }

    #[tokio::test]
    async fn bounded_connection_enforces_request_wire_and_event_totals() {
        let (client, mut peer) = tokio::io::duplex(65536);
        let mut h2 = Http2Client::new_bounded_rsd(Box::pin(client)).await.unwrap();
        h2.bounded_rsd.as_mut().unwrap().wire_left = 9;
        peer.write_all(&frame::DataFrame { stream_id: 1, payload: vec![7], end_stream: false }.serialize()).await.unwrap();
        assert!(h2.read(1).await.is_err());
        assert_eq!(h2.recv_buf.len(), 9);
        let (client, mut peer) = tokio::io::duplex(65536);
        let mut h2 = Http2Client::new_bounded_rsd(Box::pin(client)).await.unwrap();
        h2.bounded_rsd.as_mut().unwrap().frames_left = 1;
        peer.write_all(&frame::SettingsFrame { stream_id: 0, settings: vec![], flags: 1 }.serialize()).await.unwrap();
        assert!(h2.read(1).await.is_err());
    }

    #[tokio::test]
    async fn bounded_connection_shares_partial_and_cached_byte_budget() {
        let (client, mut peer) = tokio::io::duplex(65536);
        let mut h2 = Http2Client::new_bounded_rsd(Box::pin(client)).await.unwrap();
        h2.set_rsd_external_bytes(RSD_MAX_BUFFERED_BYTES - 9).unwrap();
        peer.write_all(&frame::DataFrame { stream_id: 3, payload: vec![7], end_stream: false }.serialize()).await.unwrap();
        assert!(h2.read(1).await.is_err());
        assert_eq!(h2.recv_buf.len(), 9);
        assert_eq!(h2.bounded_rsd.as_ref().unwrap().cached_bytes, 0);
    }

    #[tokio::test]
    async fn bounded_connection_stops_default_control_frame_flood() {
        let (client, mut peer) = tokio::io::duplex(65536);
        let mut h2 = Http2Client::new_bounded_rsd(client).await.unwrap();
        let frame = frame::HeadersFrame { stream_id: 3 }.serialize();
        for _ in 0..=RSD_MAX_FRAMES { peer.write_all(&frame).await.unwrap(); }
        assert!(h2.read(1).await.is_err());
        assert_eq!(h2.bounded_rsd.as_ref().unwrap().frames_left, 0);
        assert!(h2.cache.len() <= 2);
    }

    #[tokio::test]
    async fn bounded_connection_stops_default_total_wire_flood() {
        let (client, mut peer) = tokio::io::duplex(5 * 1024 * 1024);
        let mut h2 = Http2Client::new_bounded_rsd(client).await.unwrap();
        // Valid ignored settings consume wire bytes without growing DATA caches.
        let mut frame = vec![0, 0x3f, 0xfc, 4, 0, 0, 0, 0, 0]; // 16380-byte body
        for _ in 0..2730 { frame.extend_from_slice(&[0, 1, 0, 0, 0, 0]); }
        for _ in 0..=RSD_MAX_WIRE_BYTES / frame.len() { peer.write_all(&frame).await.unwrap(); }
        assert!(h2.read(1).await.is_err());
        let state = h2.bounded_rsd.as_ref().unwrap();
        assert_eq!(state.wire_left, 0);
        assert!(state.frames_left > 0);
        assert_eq!(state.cached_bytes, 0);
    }


    #[tokio::test]
    async fn bounded_connection_eof_is_terminal_for_empty_and_partial_frames() {
        for prefix in [vec![], vec![0, 0, 32, 0, 0], vec![0, 0, 32, 0, 0, 0, 0, 0, 1, 7, 8, 9]] {
            let (client, mut peer) = tokio::io::duplex(65536);
            let mut h2 = Http2Client::new_bounded_rsd(client).await.unwrap();
            peer.write_all(&prefix).await.unwrap();
            peer.shutdown().await.unwrap();
            assert!(h2.read(1).await.is_err());
            assert_eq!(h2.recv_buf, prefix);
        }
    }

    #[tokio::test]
    async fn bounded_connection_stops_reply_cache_flood() {
        let (client, mut peer) = tokio::io::duplex(2 * 1024 * 1024);
        let mut h2 = Http2Client::new_bounded_rsd(client).await.unwrap();
        let frame = frame::DataFrame { stream_id: 3, payload: vec![0; 16384], end_stream: false }.serialize();
        for _ in 0..65 { peer.write_all(&frame).await.unwrap(); }
        assert!(h2.read(1).await.is_err());
        let state = h2.bounded_rsd.as_ref().unwrap();
        assert_eq!(state.cached_bytes + state.external_bytes + h2.recv_buf.len(), RSD_MAX_BUFFERED_BYTES);
        assert!(h2.cache.len() <= 2);
        assert!(state.wire_left > 0);
    }

}
