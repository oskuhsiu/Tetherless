// Jackson Coxson

use async_stream::try_stream;
use futures::Stream;
use http2::Setting;
use tracing::debug;

use crate::{CdTunnelError, IdeviceError, ReadWrite, xpc};

pub mod errors;
mod format;
mod http2;
pub mod xpc_macro;

use format::XPCFlag;
pub use format::{Dictionary, XPCMessage, XPCObject};

const ROOT_CHANNEL: u32 = 1;
const REPLY_CHANNEL: u32 = 3;
/// First stream ID available for an outbound file transfer. Client-initiated
/// streams must be odd, and 1/3 are taken by the root and reply channels.
const FIRST_OUTBOUND_FILE_STREAM: u32 = 5;

/// Fixed XPC message-wrapper header: magic + flags + body length + message id.
const XPC_WRAPPER_LEN: usize = 24;
const RSD_MAX_MESSAGES: usize = 256;

#[derive(Debug)]
pub struct RemoteXpcClient<R: ReadWrite> {
    h2_client: http2::Http2Client<R>,
    root_id: u64,
    rsd_messages_left: Option<usize>,
    // reply_id: u64 // maybe not used?
    /// Per-channel bytes accumulated toward the next whole XPC message. Persisted
    /// across `recv_from_channel` calls so a partially-received message survives a
    /// cancelled read.
    partial: std::collections::HashMap<u32, Vec<u8>>,
    /// Stream ID for the next outbound file transfer.
    next_outbound_file_stream: u32,
}

impl<R: ReadWrite> RemoteXpcClient<R> {
    pub async fn new(socket: R) -> Result<Self, IdeviceError> {
        Ok(Self {
            h2_client: http2::Http2Client::new(socket).await?,
            root_id: 1,
            rsd_messages_left: None,
            partial: std::collections::HashMap::new(),
            next_outbound_file_stream: FIRST_OUTBOUND_FILE_STREAM,
        })
    }

    /// Acquisition-only constructor. The caller owns the whole-request deadline
    /// and cancellation; dropping that future terminates this connection.
    pub(crate) async fn new_bounded_rsd(socket: R) -> Result<Self, IdeviceError> {
        Ok(Self {
            h2_client: http2::Http2Client::new_bounded_rsd(socket).await?,
            root_id: 1,
            rsd_messages_left: Some(RSD_MAX_MESSAGES),
            partial: std::collections::HashMap::new(),
            next_outbound_file_stream: FIRST_OUTBOUND_FILE_STREAM,
        })
    }

    fn rsd_partial_bytes(&self) -> Result<usize, IdeviceError> {
        self.partial.values().try_fold(0usize, |total, part| {
            total.checked_add(part.len()).ok_or_else(|| {
                IdeviceError::UnexpectedResponse("RSD XPC buffer budget exceeded".into())
            })
        })
    }

    fn append_partial(&mut self, channel: u32, chunk: Vec<u8>) -> Result<(), IdeviceError> {
        if self.rsd_messages_left.is_some() {
            if !matches!(channel, ROOT_CHANNEL | REPLY_CHANNEL) {
                return Err(IdeviceError::UnexpectedResponse("unexpected RSD XPC channel".into()));
            }
            let bytes = self.rsd_partial_bytes()?.checked_add(chunk.len()).ok_or_else(|| {
                IdeviceError::UnexpectedResponse("RSD XPC buffer budget exceeded".into())
            })?;
            // The HTTP/2 cache has transferred ownership of this chunk to us.
            // Charge the new partial bytes before extending their allocation.
            self.h2_client.set_rsd_external_bytes(bytes)?;
        }
        self.partial.entry(channel).or_default().extend(chunk);
        Ok(())
    }

    pub async fn do_handshake(&mut self) -> Result<(), IdeviceError> {
        self.h2_client
            .set_settings(
                vec![
                    Setting::MaxConcurrentStreams(if self.rsd_messages_left.is_some() { 2 } else { 100 }),
                    Setting::InitialWindowSize(1048576),
                ],
                0,
            )
            .await?;
        self.h2_client.window_update(983041, 0).await?;
        self.h2_client.open_stream(1).await?; // root channel

        debug!("Sending empty dictionary");
        self.send_root(XPCMessage::new(
            Some(XPCFlag::AlwaysSet),
            Some(XPCObject::Dictionary(Default::default())),
            None,
        ))
        .await?;

        debug!("Opening reply stream");
        self.h2_client.open_stream(REPLY_CHANNEL).await?;
        self.send_reply(XPCMessage::new(
            Some(XPCFlag::InitHandshake | XPCFlag::AlwaysSet),
            None,
            None,
        ))
        .await?;

        debug!("Sending weird flags");
        self.send_root(XPCMessage::new(Some(XPCFlag::Custom(0x201)), None, None))
            .await?;

        Ok(())
    }

    /// Announce ourselves to the device's `remoted` as a modern (non-legacy)
    /// RemoteXPC peer.
    ///
    /// Send this only on the RSD/remoted control connection
    pub async fn send_device_handshake(&mut self) -> Result<(), IdeviceError> {
        const REMOTE_XPC_VERSION_FLAGS: u64 = 0x0100_0000_0000_0006;

        let msg = xpc!({
            "MessageType": "Handshake",
            "MessagingProtocolVersion": 7u64,
            "UUID": uuid::Uuid::new_v4(),
            "Properties": {
                "RemoteXPCVersionFlags": REMOTE_XPC_VERSION_FLAGS,
                "SensitivePropertiesVisible": true,
            },
            "Services": XPCObject::Dictionary(Dictionary::new())
        });

        self.send_object(msg, false).await
    }

    pub async fn recv(&mut self) -> Result<plist::Value, IdeviceError> {
        self.recv_from_channel(REPLY_CHANNEL).await
    }

    pub async fn recv_root(&mut self) -> Result<plist::Value, IdeviceError> {
        self.recv_from_channel(ROOT_CHANNEL).await
    }

    pub async fn recv_any(&mut self) -> Result<plist::Value, IdeviceError> {
        const CHANNELS: [u32; 2] = [ROOT_CHANNEL, REPLY_CHANNEL];
        loop {
            for channel in CHANNELS {
                if let Some(msg) = self.take_buffered(channel)?
                    && let Some(inner) = msg.message
                    && !inner.as_dictionary().is_some_and(|d| d.is_empty())
                {
                    return Ok(inner.to_plist());
                }
            }
            let (channel, chunk) = self.h2_client.read_any(&CHANNELS).await?;
            self.append_partial(channel, chunk)?;
        }
    }

    /// Decodes one whole message out of `channel`'s buffered bytes, if there is
    /// one, consuming exactly the bytes it occupies so the next message in the
    /// buffer survives. Returns `None` when the buffer doesn't hold a whole
    /// message yet.
    fn take_buffered(&mut self, channel: u32) -> Result<Option<XPCMessage>, IdeviceError> {
        if let Some(messages_left) = self.rsd_messages_left.as_mut() {
            if !matches!(channel, ROOT_CHANNEL | REPLY_CHANNEL) || *messages_left == 0 {
                return Err(IdeviceError::UnexpectedResponse("RSD XPC message budget exceeded".into()));
            }
            let buf = self.partial.entry(channel).or_default();
            let Some((message, consumed)) = XPCMessage::decode_bounded_rsd(buf)? else {
                return Ok(None);
            };
            *messages_left -= 1;
            buf.drain(..consumed);
            let bytes = self.rsd_partial_bytes()?;
            self.h2_client.set_rsd_external_bytes(bytes)?;
            return Ok(Some(message));
        }
        let buf = self.partial.entry(channel).or_default();
        match XPCMessage::decode(buf) {
            Ok(msg) => {
                let consumed = (XPC_WRAPPER_LEN + xpc_body_len(buf)).min(buf.len());
                buf.drain(..consumed);
                Ok(Some(msg))
            }
            // Not enough bytes yet.
            Err(IdeviceError::CdTunnel(CdTunnelError::SizeMismatch))
            | Err(IdeviceError::NotEnoughBytes(..)) => Ok(None),
            Err(e) => Err(e),
        }
    }

    async fn recv_from_channel(&mut self, channel: u32) -> Result<plist::Value, IdeviceError> {
        loop {
            // Try to decode a whole message from what's already buffered before
            // reading more, so a message split across earlier reads completes.
            match self.take_buffered(channel)? {
                // Skip empty-dictionary keepalives and bodyless frames.
                Some(msg) => match msg.message {
                    Some(inner) => {
                        if let Some(d) = inner.as_dictionary()
                            && d.is_empty()
                        {
                            continue;
                        }
                        return Ok(inner.to_plist());
                    }
                    None => continue,
                },
                None => {
                    let chunk = self.h2_client.read(channel).await?;
                    self.append_partial(channel, chunk)?;
                }
            }
        }
    }

    pub async fn send_object(
        &mut self,
        msg: impl Into<XPCObject>,
        expect_reply: bool,
    ) -> Result<(), IdeviceError> {
        let msg: XPCObject = msg.into();

        let mut flag = XPCFlag::DataFlag | XPCFlag::AlwaysSet;
        if expect_reply {
            flag |= XPCFlag::WantingReply;
        }

        let msg = XPCMessage::new(Some(flag), Some(msg), Some(self.root_id));
        self.send_root(msg).await?;

        Ok(())
    }

    async fn send_root(&mut self, msg: XPCMessage) -> Result<(), IdeviceError> {
        self.h2_client
            .send(msg.encode(self.root_id)?, ROOT_CHANNEL)
            .await?;
        Ok(())
    }

    async fn send_reply(&mut self, msg: XPCMessage) -> Result<(), IdeviceError> {
        self.h2_client
            .send(msg.encode(self.root_id)?, REPLY_CHANNEL)
            .await?;
        Ok(())
    }

    pub fn iter_file_chunks<'a>(
        &'a mut self,
        total_size: usize,
        file_idx: u32,
    ) -> impl Stream<Item = Result<Vec<u8>, IdeviceError>> + 'a {
        let stream_id = (file_idx + 1) * 2;

        try_stream! {
            fn strip_xpc_wrapper_prefix(buf: &[u8]) -> (&[u8], bool) {
                // Returns (data_after_wrapper, stripped_anything)
                const MAGIC: u32 = 0x29b00b92;

                if buf.len() < 24 {
                    return (buf, false);
                }

                let magic = u32::from_le_bytes([buf[0], buf[1], buf[2], buf[3]]);
                if magic != MAGIC {
                    return (buf, false);
                }

                // flags at [4..8] – not needed to compute size
                let body_len = u64::from_le_bytes([
                    buf[8], buf[9], buf[10], buf[11], buf[12], buf[13], buf[14], buf[15],
                ]) as usize;

                let wrapper_len = 24 + body_len;
                if buf.len() < wrapper_len {
                    // Incomplete wrapper (shouldn’t happen with your read API), keep as-is.
                    return (buf, false);
                }

                (&buf[wrapper_len..], true)
            }
            self.open_file_stream_for_response(stream_id).await?;

            let mut got = 0usize;
            while got < total_size {
                let bytes = self.h2_client.read(stream_id).await?;
                let (after, stripped) = strip_xpc_wrapper_prefix(&bytes);
                if stripped && after.is_empty() {
                    continue; // pure control wrapper, don't count
                }

                let data = if stripped { after.to_vec() } else { bytes };

                if data.is_empty() {
                    continue;
                }

                got += data.len();
                yield data;
            }
        }
    }

    /// Pushes the payload of a file transfer we announced in an earlier request.
    pub async fn send_file_transfer(
        &mut self,
        transfer_id: u64,
        data: &[u8],
    ) -> Result<(), IdeviceError> {
        let stream_id = self.next_outbound_file_stream;
        self.next_outbound_file_stream += 2;

        self.h2_client.open_stream(stream_id).await?;

        // The preamble is a DATA frame like any other, so it has to go through
        // the flow-controlled send path: sending it unaccounted overruns the
        // connection window once an earlier transfer has drained it, and the
        // device answers with GOAWAY (FLOW_CONTROL_ERROR).
        let preamble = XPCMessage::new(
            Some(XPCFlag::FileTxStreamRequest | XPCFlag::AlwaysSet),
            None,
            Some(transfer_id),
        )
        .encode(transfer_id)?;
        self.h2_client.send(preamble, stream_id).await?;
        self.h2_client.send(data.to_vec(), stream_id).await?;
        self.h2_client
            .send_end_stream(Vec::new(), stream_id)
            .await?;
        Ok(())
    }

    pub async fn open_file_stream_for_response(
        &mut self,
        stream_id: u32,
    ) -> Result<(), IdeviceError> {
        // 1) Open the HTTP/2 stream
        self.h2_client.open_stream(stream_id).await?;

        // 2) Send an empty XPC wrapper on that same stream with FILE_TX_STREAM_RESPONSE
        let flags = XPCFlag::AlwaysSet | XPCFlag::FileTxStreamResponse;

        let msg = XPCMessage::new(Some(flags), None, Some(0));

        // IMPORTANT: send on `stream_id`, not ROOT/REPLY
        let bytes = msg.encode(0)?;
        self.h2_client.send(bytes, stream_id).await?;
        Ok(())
    }
}

/// The XPC message body length from a decoded-OK wrapper: the little-endian u64
/// at bytes 8..16. `buf` is known to hold a full wrapper (≥ 24 bytes) here.
fn xpc_body_len(buf: &[u8]) -> usize {
    u64::from_le_bytes([
        buf[8], buf[9], buf[10], buf[11], buf[12], buf[13], buf[14], buf[15],
    ]) as usize
}


#[cfg(test)]
mod bounded_rsd_tests {
    use super::*;
    use super::http2::frame::{DataFrame, HttpFrame};
    use tokio::io::AsyncWriteExt;

    #[tokio::test]
    async fn bounded_xpc_reassembles_root_across_frames() {
        let (socket, mut peer) = tokio::io::duplex(65536);
        let mut client = RemoteXpcClient::new_bounded_rsd(socket).await.unwrap();
        let encoded = XPCMessage::new(None, Some(XPCObject::String("fixture".into())), None).encode(1).unwrap();
        for payload in encoded.chunks(7) {
            peer.write_all(&DataFrame { stream_id: ROOT_CHANNEL, payload: payload.to_vec(), end_stream: false }.serialize()).await.unwrap();
        }
        assert_eq!(client.recv_root().await.unwrap().as_string(), Some("fixture"));
        assert_eq!(client.rsd_partial_bytes().unwrap(), 0);
    }

    #[tokio::test]
    async fn bounded_xpc_counts_bodyless_and_empty_keepalives() {
        let (socket, _peer) = tokio::io::duplex(65536);
        let mut client = RemoteXpcClient::new_bounded_rsd(socket).await.unwrap();
        let bodyless = XPCMessage::new(None, None, None).encode(1).unwrap();
        for _ in 0..RSD_MAX_MESSAGES {
            client.append_partial(ROOT_CHANNEL, bodyless.clone()).unwrap();
            assert!(client.take_buffered(ROOT_CHANNEL).unwrap().is_some());
        }
        assert!(client.take_buffered(ROOT_CHANNEL).is_err());
    }

    #[tokio::test]
    async fn bounded_xpc_complete_malformed_body_is_terminal() {
        let (socket, _peer) = tokio::io::duplex(65536);
        let mut client = RemoteXpcClient::new_bounded_rsd(socket).await.unwrap();
        let mut encoded = XPCMessage::new(None, Some(XPCObject::Data(vec![1])), None).encode(1).unwrap();
        encoded[36..40].copy_from_slice(&100u32.to_le_bytes());
        client.append_partial(ROOT_CHANNEL, encoded).unwrap();
        assert!(client.take_buffered(ROOT_CHANNEL).is_err());
    }
}
