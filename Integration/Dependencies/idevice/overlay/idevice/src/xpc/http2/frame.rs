// Jackson Coxson

use crate::IdeviceError;
use crate::xpc::errors::XpcError;

/// Fixed HTTP/2 frame header size: 3-byte length, 1-byte type, 1-byte flags,
/// 4-byte stream id.
const FRAME_HEADER_LEN: usize = 9;

pub trait HttpFrame {
    fn serialize(&self) -> Vec<u8>;
}

#[derive(Debug)]
#[allow(dead_code)] // we don't care about frames from the device
pub enum Frame {
    Settings(SettingsFrame),
    /// Used only by the bounded RSD parser.
    Ping { payload: [u8; 8], ack: bool },
    WindowUpdate(WindowUpdateFrame),
    Headers(HeadersFrame),
    Data(DataFrame),
    RstStream(RstStreamFrame),
}

impl Frame {
    /// Parse a single frame from the front of `buf`.
    ///
    /// Returns `Ok(None)` when `buf` does not yet hold a complete frame (the
    /// caller should read more bytes and retry). On success returns the frame
    /// and how many bytes it consumed, so the caller can drain exactly that much
    /// — this keeps frame reassembly cancellation-safe: a partially-received
    /// frame stays buffered until it is whole. RST_STREAM and GOAWAY surface as
    /// errors (they consume no bytes; the connection is finished either way).
    pub fn parse(buf: &[u8]) -> Result<Option<(Self, usize)>, IdeviceError> {
        if buf.len() < FRAME_HEADER_LEN {
            return Ok(None);
        }
        let frame_len = u32::from_be_bytes([0x00, buf[0], buf[1], buf[2]]) as usize;
        let frame_type = buf[3];
        let flags = buf[4];
        let stream_id = u32::from_be_bytes([buf[5], buf[6], buf[7], buf[8]]);

        let total = FRAME_HEADER_LEN + frame_len;
        if buf.len() < total {
            return Ok(None);
        }
        let body = &buf[FRAME_HEADER_LEN..total];

        let frame = match frame_type {
            0x00 => Self::Data(DataFrame {
                stream_id,
                payload: body.to_vec(),
                end_stream: flags & 0x01 != 0,
            }),
            0x01 => Self::Headers(HeadersFrame { stream_id }),
            0x03 => Self::RstStream(RstStreamFrame { stream_id }),
            0x04 => {
                // settings: a sequence of (u16 identifier, u32 value) entries
                let mut settings = Vec::new();
                let mut i = 0;
                while i + 6 <= body.len() {
                    let setting_type = u16::from_be_bytes([body[i], body[i + 1]]);
                    let value =
                        u32::from_be_bytes([body[i + 2], body[i + 3], body[i + 4], body[i + 5]]);
                    settings.push(match setting_type {
                        0x03 => Setting::MaxConcurrentStreams(value),
                        0x04 => Setting::InitialWindowSize(value),
                        _ => return Err(XpcError::UnknownHttpSetting(setting_type).into()),
                    });
                    i += 6;
                }
                Self::Settings(SettingsFrame {
                    settings,
                    stream_id,
                    flags,
                })
            }
            0x07 => {
                let msg = if body.len() < 8 {
                    "<MISSING>".to_string()
                } else {
                    String::from_utf8_lossy(&body[8..]).to_string()
                };
                return Err(XpcError::HttpGoAway(msg).into());
            }
            0x08 => {
                if body.len() != 4 {
                    return Err(IdeviceError::UnexpectedResponse(
                        "HTTP/2 window update frame body was not 4 bytes".into(),
                    ));
                }
                let window = u32::from_be_bytes([body[0], body[1], body[2], body[3]]);
                Self::WindowUpdate(WindowUpdateFrame {
                    increment_size: window,
                    stream_id,
                })
            }
            _ => return Err(XpcError::UnknownFrame(frame_type).into()),
        };

        Ok(Some((frame, total)))
    }
}

#[derive(Debug, Clone)]
pub struct SettingsFrame {
    pub settings: Vec<Setting>,
    pub stream_id: u32,
    pub flags: u8,
}

#[derive(Debug, Clone)]
pub enum Setting {
    MaxConcurrentStreams(u32),
    InitialWindowSize(u32),
}

impl Setting {
    fn serialize(&self) -> Vec<u8> {
        match self {
            Setting::MaxConcurrentStreams(m) => {
                let mut res = vec![0x00, 0x03];
                res.extend(m.to_be_bytes());
                res
            }
            Setting::InitialWindowSize(s) => {
                let mut res = vec![0x00, 0x04];
                res.extend(s.to_be_bytes());
                res
            }
        }
    }
}

impl HttpFrame for SettingsFrame {
    fn serialize(&self) -> Vec<u8> {
        let settings = self
            .settings
            .iter()
            .map(|x| x.serialize())
            .collect::<Vec<Vec<u8>>>()
            .concat();
        let settings_len = (settings.len() as u32).to_be_bytes();
        let mut res = vec![
            settings_len[1],
            settings_len[2],
            settings_len[3],
            0x04,
            self.flags,
        ];
        res.extend(self.stream_id.to_be_bytes());
        res.extend(settings);
        res
    }
}

#[derive(Debug, Clone)]
pub struct WindowUpdateFrame {
    pub increment_size: u32,
    pub stream_id: u32,
}

impl HttpFrame for WindowUpdateFrame {
    fn serialize(&self) -> Vec<u8> {
        let mut res = vec![0x00, 0x00, 0x04, 0x08, 0x00]; // size, frame ID, flags
        res.extend(self.stream_id.to_be_bytes());
        res.extend(self.increment_size.to_be_bytes());
        res
    }
}

#[derive(Debug, Clone)]
/// We don't actually care about this frame according to spec. This is just to open new channels.
pub struct HeadersFrame {
    pub stream_id: u32,
}

impl HttpFrame for HeadersFrame {
    fn serialize(&self) -> Vec<u8> {
        let mut res = vec![0x00, 0x00, 0x00, 0x01, 0x04];
        res.extend(self.stream_id.to_be_bytes());
        res
    }
}

#[derive(Debug, Clone)]
pub struct RstStreamFrame {
    pub stream_id: u32,
}

#[derive(Debug, Clone)]
pub struct DataFrame {
    pub stream_id: u32,
    pub payload: Vec<u8>,
    /// Sets END_STREAM, marking this as the last frame we send on the stream.
    pub end_stream: bool,
}

impl HttpFrame for DataFrame {
    fn serialize(&self) -> Vec<u8> {
        let mut res = (self.payload.len() as u32).to_be_bytes().to_vec();
        res.remove(0); // only 3 significant bytes
        res.push(0x00); // frame type
        res.push(if self.end_stream { 0x01 } else { 0x00 }); // flags
        res.extend(self.stream_id.to_be_bytes());
        res.extend(self.payload.clone());
        res
    }
}


pub(super) const RSD_MAX_FRAME_BYTES: usize = 16384;

fn bounded_frame_error() -> IdeviceError {
    IdeviceError::UnexpectedResponse("invalid or over-budget RSD HTTP/2 frame".into())
}

impl Frame {
    /// Validate the header before waiting for its advertised body. Only the
    /// control connection and the two RSD streams can be represented or cached.
    pub(super) fn bounded_rsd_frame_len(buf: &[u8]) -> Result<Option<usize>, IdeviceError> {
        if buf.len() < FRAME_HEADER_LEN { return Ok(None); }
        let len = usize::try_from(u32::from_be_bytes([0, buf[0], buf[1], buf[2]]))
            .map_err(|_| bounded_frame_error())?;
        if len > RSD_MAX_FRAME_BYTES { return Err(bounded_frame_error()); }
        // RFC 7540: the reserved stream-id bit is ignored on receipt.
        let stream = u32::from_be_bytes([buf[5], buf[6], buf[7], buf[8]]) & 0x7fff_ffff;
        let flags = buf[4];
        match buf[3] {
            0x00 if matches!(stream, 1 | 3) && flags & !0x09 == 0 => {}
            0x01 if matches!(stream, 1 | 3) && flags & !0x2d == 0 && flags & 4 != 0 => {}
            0x03 if matches!(stream, 1 | 3) && flags == 0 && len == 4 => {}
            0x04 if stream == 0 && flags & !1 == 0 && len % 6 == 0
                && (flags & 1 == 0 || len == 0) => {}
            0x06 if stream == 0 && flags & !1 == 0 && len == 8 => {}
            0x07 if stream == 0 && flags == 0 && len >= 8 => {}
            0x08 if matches!(stream, 0 | 1 | 3) && flags == 0 && len == 4 => {}
            _ => return Err(bounded_frame_error()),
        }
        len.checked_add(FRAME_HEADER_LEN).map(Some).ok_or_else(bounded_frame_error)
    }

    pub(super) fn parse_bounded_rsd(buf: &[u8]) -> Result<Option<(Self, usize)>, IdeviceError> {
        let Some(total) = Self::bounded_rsd_frame_len(buf)? else { return Ok(None); };
        if buf.len() < total { return Ok(None); }
        let body = &buf[FRAME_HEADER_LEN..total];
        let flags = buf[4];
        let stream_id = u32::from_be_bytes([buf[5], buf[6], buf[7], buf[8]]) & 0x7fff_ffff;
        let frame = match buf[3] {
            0x00 => {
                let payload = if flags & 8 != 0 {
                    let (&padding, data) = body.split_first().ok_or_else(bounded_frame_error)?;
                    let data_len = data.len().checked_sub(usize::from(padding))
                        .ok_or_else(bounded_frame_error)?;
                    &data[..data_len]
                } else { body };
                Self::Data(DataFrame { stream_id, payload: payload.to_vec(), end_stream: flags & 1 != 0 })
            }
            0x01 => {
                // RemoteXPC uses empty HEADERS with END_HEADERS. Validate optional
                // padding/priority lengths without allocating an HPACK decoder.
                let mut content = body;
                if flags & 8 != 0 {
                    let (&padding, data) = content.split_first().ok_or_else(bounded_frame_error)?;
                    let len = data.len().checked_sub(usize::from(padding)).ok_or_else(bounded_frame_error)?;
                    content = &data[..len];
                }
                if flags & 0x20 != 0 && content.len() < 5 { return Err(bounded_frame_error()); }
                Self::Headers(HeadersFrame { stream_id })
            }
            0x03 => Self::RstStream(RstStreamFrame { stream_id }),
            0x04 => {
                let mut settings = Vec::new();
                for entry in body.chunks_exact(6) {
                    let id = u16::from_be_bytes([entry[0], entry[1]]);
                    let value = u32::from_be_bytes([entry[2], entry[3], entry[4], entry[5]]);
                    match id {
                        3 => settings.push(Setting::MaxConcurrentStreams(value)),
                        4 if value <= 0x7fff_ffff => settings.push(Setting::InitialWindowSize(value)),
                        4 => return Err(bounded_frame_error()),
                        2 if value > 1 => return Err(bounded_frame_error()),
                        5 if !(16384..=16777215).contains(&value) => return Err(bounded_frame_error()),
                        _ => {} // RFC 7540 requires unknown settings be ignored.
                    }
                }
                Self::Settings(SettingsFrame { settings, stream_id, flags })
            }
            0x06 => {
                let mut payload = [0; 8];
                payload.copy_from_slice(body);
                Self::Ping { payload, ack: flags & 1 != 0 }
            }
            // Do not put peer-provided GOAWAY diagnostics in errors or logs.
            0x07 => return Err(IdeviceError::UnexpectedResponse("RSD HTTP/2 peer closed the connection".into())),
            0x08 => {
                let increment_size = u32::from_be_bytes([body[0], body[1], body[2], body[3]]) & 0x7fff_ffff;
                if increment_size == 0 { return Err(bounded_frame_error()); }
                Self::WindowUpdate(WindowUpdateFrame { increment_size, stream_id })
            }
            _ => return Err(bounded_frame_error()),
        };
        Ok(Some((frame, total)))
    }
}

#[cfg(test)]
mod bounded_rsd_tests {
    use super::*;

    #[test]
    fn bounded_frames_round_trip_and_reassemble() {
        let encoded = DataFrame { stream_id: 1, payload: vec![1, 2, 3], end_stream: false }.serialize();
        for len in 0..encoded.len() { assert!(Frame::parse_bounded_rsd(&encoded[..len]).unwrap().is_none()); }
        let (Frame::Data(decoded), used) = Frame::parse_bounded_rsd(&encoded).unwrap().unwrap() else { panic!("wrong frame"); };
        assert_eq!(decoded.payload, [1, 2, 3]);
        assert_eq!(used, encoded.len());
    }

    #[test]
    fn bounded_header_rejects_oversized_and_unexpected_stream_before_body() {
        let mut header = vec![0xff, 0xff, 0xff, 0, 0, 0, 0, 0, 1];
        assert!(Frame::parse_bounded_rsd(&header).is_err());
        header[..3].copy_from_slice(&[0, 0, 2]);
        header[8] = 5;
        assert!(Frame::parse_bounded_rsd(&header).is_err());
        header[3] = 8;
        header[..3].copy_from_slice(&[0, 0, 4]);
        assert!(Frame::parse_bounded_rsd(&header).is_err());
    }

    #[test]
    fn bounded_frames_validate_lengths_padding_and_windows() {
        assert!(Frame::parse_bounded_rsd(&[0,0,1,4,0,0,0,0,0]).is_err());
        assert!(Frame::parse_bounded_rsd(&[0,0,1,0,8,0,0,0,1,2]).is_err());
        let zero = WindowUpdateFrame { increment_size: 0, stream_id: 0 }.serialize();
        assert!(Frame::parse_bounded_rsd(&zero).is_err());
        let mut padded = vec![0,0,4,0,8,0,0,0,1,1,7,8,0];
        let (Frame::Data(data), _) = Frame::parse_bounded_rsd(&padded).unwrap().unwrap() else { panic!("wrong frame"); };
        assert_eq!(data.payload, [7,8]);
        padded[5] |= 0x80; // Reserved bit does not create another channel.
        assert!(Frame::parse_bounded_rsd(&padded).is_ok());
    }
}
