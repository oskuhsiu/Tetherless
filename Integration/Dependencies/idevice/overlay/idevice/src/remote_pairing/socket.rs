// Jackson Coxson

use base64::{Engine as _, engine::general_purpose::STANDARD as B64};
use plist_macro::{plist, pretty_print_plist};
use serde::Serialize;
use serde_json::json;
use std::{fmt::Debug, pin::Pin};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tracing::{debug, warn};

use crate::{
    IdeviceError, ReadWrite, RemoteXpcClient, remote_pairing::RPPAIRING_MAGIC, xpc::XPCObject,
};

pub trait RpPairingSocketProvider: Debug {
    fn send_plain(
        &mut self,
        value: impl Serialize,
        seq: usize,
    ) -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>>;

    fn send_encrypted(
        &mut self,
        ciphertext: Vec<u8>,
        seq: usize,
    ) -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>>;

    fn recv_plain<'a>(
        &'a mut self,
    ) -> Pin<Box<dyn Future<Output = Result<plist::Value, IdeviceError>> + Send + 'a>>;

    /// rppairing uses b64, while RemoteXPC uses raw bytes just fine
    fn serialize_bytes(b: &[u8]) -> plist::Value;
    fn deserialize_bytes(v: plist::Value) -> Option<Vec<u8>>;
}

#[derive(Debug)]
pub struct RpPairingSocket<R: ReadWrite> {
    pub inner: R,
    /// The value placed in the `originatedBy` field of every envelope we send.
    ///
    /// The host (the side that connects to a device and initiates pairing) sends
    /// `"host"`. The responder side - a "pairable host" that a device connects to
    /// and pairs *into* (see [`crate::remote_pairing::PairableHost`]) - sends
    /// `"device"`, because in rppairing terms it plays the accessory/responder role.
    originated_by: &'static str,
}

impl<R: ReadWrite> RpPairingSocket<R> {
    /// Creates a socket for the initiating host (sends `originatedBy: "host"`).
    pub fn new(socket: R) -> Self {
        Self {
            inner: socket,
            originated_by: "host",
        }
    }

    /// Creates a socket for the responder side (sends `originatedBy: "device"`).
    ///
    /// Use this when accepting a device-initiated pairing with
    /// [`crate::remote_pairing::PairableHost`].
    pub fn new_device(socket: R) -> Self {
        Self {
            inner: socket,
            originated_by: "device",
        }
    }

    async fn send_rppairing(&mut self, value: impl Serialize) -> Result<(), IdeviceError> {
        let value = serde_json::to_string(&value)?;
        debug!("send_rppairing payload: {value}");
        let x = value.as_bytes();

        let mut frame = Vec::with_capacity(RPPAIRING_MAGIC.len() + 2 + x.len());
        frame.extend_from_slice(RPPAIRING_MAGIC);
        frame.extend_from_slice(&(x.len() as u16).to_be_bytes());
        frame.extend_from_slice(x);
        self.inner.write_all(&frame).await?;
        self.inner.flush().await?;
        Ok(())
    }
}

impl<R: ReadWrite> RpPairingSocketProvider for RpPairingSocket<R> {
    fn send_plain(
        &mut self,
        value: impl Serialize,
        seq: usize,
    ) -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let v = json!({
            "message": {"plain": {"_0": value}},
            "originatedBy": self.originated_by,
            "sequenceNumber": seq
        });

        Box::pin(async move {
            self.send_rppairing(v).await?;
            Ok(())
        })
    }

    fn send_encrypted(
        &mut self,
        ciphertext: Vec<u8>,
        seq: usize,
    ) -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let v = json!({
            "message": {"streamEncrypted": {"_0": B64.encode(&ciphertext)}},
            "originatedBy": self.originated_by,
            "sequenceNumber": seq
        });

        Box::pin(async move {
            self.send_rppairing(v).await?;
            Ok(())
        })
    }

    fn recv_plain<'a>(
        &'a mut self,
    ) -> Pin<Box<dyn Future<Output = Result<plist::Value, IdeviceError>> + Send + 'a>> {
        Box::pin(async move {
            let mut magic = vec![0u8; RPPAIRING_MAGIC.len()];
            self.inner.read_exact(&mut magic).await?;

            let mut packet_len_bytes = [0u8; 2];
            self.inner.read_exact(&mut packet_len_bytes).await?;
            let packet_len = u16::from_be_bytes(packet_len_bytes);

            let mut value = vec![0u8; packet_len as usize];
            self.inner.read_exact(&mut value).await?;

            let raw_str = String::from_utf8_lossy(&value);
            debug!("recv_rppairing ({packet_len} bytes) payload: {raw_str}");

            let value: serde_json::Value = serde_json::from_slice(&value)?;

            // Try plain first, then return the whole message dict for encrypted
            if let Some(v) = value
                .get("message")
                .and_then(|x| x.get("plain"))
                .and_then(|x| x.get("_0"))
            {
                Ok(plist::to_value(v).unwrap())
            } else {
                // Return the full message for encrypted handling
                Ok(plist::to_value(&value).unwrap())
            }
        })
    }

    fn serialize_bytes(b: &[u8]) -> plist::Value {
        plist!(B64.encode(b))
    }

    fn deserialize_bytes(v: plist::Value) -> Option<Vec<u8>> {
        if let plist::Value::String(v) = v {
            B64.decode(v).ok()
        } else {
            None
        }
    }
}

impl<R: ReadWrite> RpPairingSocketProvider for RemoteXpcClient<R> {
    fn send_plain(
        &mut self,
        value: impl Serialize,
        seq: usize,
    ) -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let value: plist::Value = plist::to_value(&value).expect("plist assert failed");
        let value: XPCObject = value.into();

        let v = crate::xpc!({
            "mangledTypeName": "RemotePairing.ControlChannelMessageEnvelope",
            "value": {
                "message": {"plain": {"_0": value}},
                "originatedBy": "host",
                "sequenceNumber": seq as u64
            }
        });
        debug!("Sending XPC: {v:#?}");

        Box::pin(async move {
            self.send_object(v, true).await?;
            Ok(())
        })
    }

    fn send_encrypted(
        &mut self,
        ciphertext: Vec<u8>,
        seq: usize,
    ) -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let v = crate::xpc!({
            "mangledTypeName": "RemotePairing.ControlChannelMessageEnvelope",
            "value": {
                "message": {"streamEncrypted": {"_0": ciphertext}},
                "originatedBy": "host",
                "sequenceNumber": seq as u64
            }
        });

        Box::pin(async move {
            self.send_object(v, true).await?;
            Ok(())
        })
    }

    fn recv_plain<'a>(
        &'a mut self,
    ) -> Pin<Box<dyn Future<Output = Result<plist::Value, IdeviceError>> + Send + 'a>> {
        Box::pin(async move {
            let msg = self.recv_root().await?;
            debug!("Received RemoteXPC {}", pretty_print_plist(&msg));
            let msg = msg.into_dictionary().and_then(|mut x| x.remove("value"));

            let msg = match msg {
                Some(v) => v,
                None => {
                    return Err(IdeviceError::UnexpectedResponse(
                        "missing value field in RemoteXPC message".into(),
                    ));
                }
            };

            // Try plain first
            if let Some(plain) = msg
                .as_dictionary()
                .and_then(|x| x.get("message"))
                .and_then(|x| x.as_dictionary())
                .and_then(|x| x.get("plain"))
                .and_then(|x| x.as_dictionary())
                .and_then(|x| x.get("_0"))
                .cloned()
            {
                return Ok(plain);
            }

            // Return the whole value dict for encrypted handling
            Ok(msg)
        })
    }

    fn serialize_bytes(b: &[u8]) -> plist::Value {
        plist::Value::Data(b.to_owned())
    }

    fn deserialize_bytes(v: plist::Value) -> Option<Vec<u8>> {
        if let plist::Value::Data(v) = v {
            Some(v)
        } else {
            warn!("Non-data passed to rppairingsocket::deserialize_bytes for RemoteXPC provider");
            None
        }
    }
}

/// Opt-in raw RP socket for staged validation. No peer payloads are logged.
/// This is the existing RP framing/serde codec with finite record/wire limits.
#[derive(Debug)]
pub struct BoundedRpPairingSocket<R: ReadWrite> {
    inner: R,
    sent: usize,
    received: usize,
    frames: usize,
}

impl<R: ReadWrite> BoundedRpPairingSocket<R> {
    const MAX_FRAME: usize = 32 * 1024;
    const MAX_WIRE: usize = 256 * 1024;
    const MAX_FRAMES: usize = 64;

    pub fn new(inner: R) -> Self {
        Self { inner, sent: 0, received: 0, frames: 0 }
    }

    fn reject() -> IdeviceError {
        IdeviceError::UnexpectedResponse("staged RP frame rejected".into())
    }

    fn charge(&mut self, len: usize, send: bool) -> Result<(), IdeviceError> {
        if len == 0 || len > Self::MAX_FRAME || self.frames >= Self::MAX_FRAMES {
            return Err(Self::reject());
        }
        let counter = if send { &mut self.sent } else { &mut self.received };
        *counter = counter.checked_add(len + RPPAIRING_MAGIC.len() + 2)
            .filter(|n| *n <= Self::MAX_WIRE).ok_or_else(Self::reject)?;
        self.frames += 1;
        Ok(())
    }

    async fn send(&mut self, value: serde_json::Value) -> Result<(), IdeviceError> {
        let bytes = serde_json::to_vec(&value).map_err(|_| Self::reject())?;
        self.charge(bytes.len(), true)?;
        self.inner.write_all(RPPAIRING_MAGIC).await?;
        self.inner.write_all(&(bytes.len() as u16).to_be_bytes()).await?;
        self.inner.write_all(&bytes).await?;
        self.inner.flush().await?;
        Ok(())
    }
}

impl<R: ReadWrite> RpPairingSocketProvider for BoundedRpPairingSocket<R> {
    fn send_plain(&mut self, value: impl Serialize, seq: usize)
        -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>>
    {
        let value = json!({"message":{"plain":{"_0":value}},
            "originatedBy":"host", "sequenceNumber":seq});
        Box::pin(async move { self.send(value).await })
    }

    fn send_encrypted(&mut self, ciphertext: Vec<u8>, seq: usize)
        -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>>
    {
        let value = json!({"message":{"streamEncrypted":{"_0":B64.encode(ciphertext)}},
            "originatedBy":"host", "sequenceNumber":seq});
        Box::pin(async move { self.send(value).await })
    }

    fn recv_plain<'a>(&'a mut self)
        -> Pin<Box<dyn Future<Output = Result<plist::Value, IdeviceError>> + Send + 'a>>
    {
        Box::pin(async move {
            let mut magic = [0u8; 9];
            self.inner.read_exact(&mut magic).await?;
            if magic.as_slice() != RPPAIRING_MAGIC { return Err(Self::reject()); }
            let mut length = [0u8; 2];
            self.inner.read_exact(&mut length).await?;
            let length = u16::from_be_bytes(length) as usize;
            self.charge(length, false)?;
            let mut bytes = vec![0; length];
            self.inner.read_exact(&mut bytes).await?;
            // serde_json's recursion limit remains enabled; the wire cap bounds
            // aggregate scalar/collection allocations before plist conversion.
            let value: serde_json::Value = serde_json::from_slice(&bytes)
                .map_err(|_| Self::reject())?;
            let value = value.get("message").and_then(|v| v.get("plain"))
                .and_then(|v| v.get("_0")).unwrap_or(&value);
            plist::to_value(value).map_err(|_| Self::reject())
        })
    }

    fn serialize_bytes(bytes: &[u8]) -> plist::Value { plist!(B64.encode(bytes)) }
    fn deserialize_bytes(value: plist::Value) -> Option<Vec<u8>> {
        value.as_string().and_then(|v| B64.decode(v).ok())
    }
}

#[cfg(test)]
mod staged_rp_socket_tests {
    use super::*;
    #[tokio::test]
    async fn malformed_magic_and_oversized_length_fail_before_body_read() {
        for header in [b"BadMagic!\x00\x01".as_slice(), b"RPPairing\x80\x01".as_slice()] {
            let (client, mut peer) = tokio::io::duplex(64);
            peer.write_all(header).await.unwrap();
            let mut socket = BoundedRpPairingSocket::new(client);
            assert!(socket.recv_plain().await.is_err());
        }
    }
    #[test]
    fn frame_count_and_total_wire_are_independently_limited() {
        let (client, _peer) = tokio::io::duplex(64);
        let mut socket = BoundedRpPairingSocket::new(client);
        socket.frames = BoundedRpPairingSocket::<tokio::io::DuplexStream>::MAX_FRAMES;
        assert!(socket.charge(1, false).is_err());
        socket.frames = 0;
        socket.received = BoundedRpPairingSocket::<tokio::io::DuplexStream>::MAX_WIRE;
        assert!(socket.charge(1, false).is_err());
    }
}
