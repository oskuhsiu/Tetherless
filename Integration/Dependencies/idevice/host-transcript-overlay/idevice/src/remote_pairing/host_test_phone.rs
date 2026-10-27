// Copyright (c) 2026 Tetherless contributors. MIT; retained idevice license.
//! Opt-in synthetic phone for the bounded host. Never use in artifacts.
//! Existing client SRP and M5/M6 methods are called unchanged. Wire adaptation
//! adds a synthetic UDID; explicit negative modes then corrupt controller identity
//! inside a newly authenticated M5, separately from the existing AEAD-tag fault.
use super::{opack, tlv, PeerDevice, RemotePairingClient, RpPairingFile,
    RpPairingSocketProvider, RPPAIRING_MAGIC, WIRE_PROTOCOL_VERSION};
use crate::IdeviceError;
use base64::{Engine as _, engine::general_purpose::STANDARD as B64};
use chacha20poly1305::{ChaCha20Poly1305, Key, KeyInit, Nonce, aead::{Aead, Payload}};
use ed25519_dalek::{Signature, VerifyingKey};
use hkdf::Hkdf;
use plist_macro::{plist, PlistExt};
use serde::Serialize;
use sha2::Sha512;
use std::{future::Future, pin::Pin, sync::{Arc, atomic::{AtomicBool, AtomicUsize, Ordering}}};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tlv::{PairingDataComponentType as Tt, TLV8Entry};

const PHONE_NAME: &str = "synthetic phone";
const PHONE_UDID: &str = "synthetic-phone-udid";
pub const PHONE_ALT_IRK: [u8; 16] = *b"\xe9\xe8-\xc0jIykVoT\x00\x19\xb1\xc7{";
const FRAME_CAP: usize = 16_384;
const WIRE_CAP: usize = 131_072;

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode {
    Complete, WrongPin, PauseBeforeM5, TamperM5,
    InvalidControllerSignature, WrongControllerPublicKey, ShortControllerSignature,
    LongControllerSignature, WrongControllerSignatureType, ShortControllerPublicKey,
    MismatchedControllerAccount, WrongControllerAccountType,
}
impl Mode {
    pub fn invalid_controller_identity(self) -> bool {
        matches!(self, Self::InvalidControllerSignature | Self::WrongControllerPublicKey
            | Self::ShortControllerSignature | Self::LongControllerSignature
            | Self::WrongControllerSignatureType | Self::ShortControllerPublicKey
            | Self::MismatchedControllerAccount | Self::WrongControllerAccountType)
    }
}

#[derive(Default)]
pub struct Progress {
    pub greeting_verified: AtomicBool,
    pub srp_verified: AtomicBool,
    pub before_m5: AtomicBool,
    pub m5_adapted: AtomicBool,
    pub m5_original_signature_verified: AtomicBool,
    pub m5_identity_mutated: AtomicBool,
    pub m5_aead_verified: AtomicBool,
    pub m6_verified: AtomicBool,
    pub sent_frames: AtomicUsize,
    pub received_frames: AtomicUsize,
    pub sent_bytes: AtomicUsize,
    pub received_bytes: AtomicUsize,
}

// No Debug implementation: evidence contains an ephemeral public identity and
// should not accidentally cause a protocol/key/record dump in assertion output.
pub struct Evidence {
    pub identifier: String,
    pub public_key: [u8; 32],
    pub host_alt_irk: Vec<u8>,
    pub host_name: String,
    pub host_model: String,
}

fn rejected() -> IdeviceError {
    IdeviceError::UnexpectedResponse("synthetic phone transcript rejected".into())
}

fn chunk(kind: Tt, bytes: &[u8]) -> Vec<TLV8Entry> {
    bytes.chunks(255).map(|part| TLV8Entry { tlv_type: kind, data: part.to_vec() }).collect()
}

fn component(entries: &[TLV8Entry], kind: Tt) -> Vec<u8> {
    tlv::collect_component_data(entries, kind)
}

fn state(entries: &[TLV8Entry], expected: u8) -> Result<(), IdeviceError> {
    if component(entries, Tt::State) != [expected]
        || tlv::contains_component(entries, Tt::ErrorResponse) { return Err(rejected()); }
    Ok(())
}

fn json_bounded(value: &serde_json::Value, depth: usize, nodes: &mut usize) -> bool {
    if depth > 16 || *nodes >= 512 { return false; }
    *nodes += 1;
    match value {
        serde_json::Value::Array(values) => values.iter().all(|v| json_bounded(v, depth + 1, nodes)),
        serde_json::Value::Object(values) => values.iter().all(|(k, v)|
            k.len() <= 128 && json_bounded(v, depth + 1, nodes)),
        serde_json::Value::String(value) => value.len() <= FRAME_CAP,
        _ => true,
    }
}

struct PhoneSocket<S: crate::ReadWrite> {
    io: S,
    progress: Arc<Progress>,
    setup_cipher: Option<ChaCha20Poly1305>,
    controller_x: Option<[u8; 32]>,
    mode: Mode,
}
impl<S: crate::ReadWrite> std::fmt::Debug for PhoneSocket<S> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str("SyntheticPhoneSocket")
    }
}

impl<S: crate::ReadWrite> PhoneSocket<S> {
    fn adapt_m5(&self, value: &mut serde_json::Value) -> Result<(), IdeviceError> {
        let cipher = self.setup_cipher.as_ref().ok_or_else(rejected)?;
        let data = value.pointer_mut("/event/_0/pairingData/_0/data").ok_or_else(rejected)?;
        let encoded = data.as_str().filter(|s| s.len() <= FRAME_CAP).ok_or_else(rejected)?;
        let outer = tlv::deserialize_tlv8(&B64.decode(encoded).map_err(|_| rejected())?)?;
        state(&outer, 5)?;
        let ciphertext = component(&outer, Tt::EncryptedData);
        let plaintext = cipher.decrypt(Nonce::from_slice(b"\0\0\0\0PS-Msg05"),
            Payload { msg: &ciphertext, aad: b"" }).map_err(|_| rejected())?;
        let entries = tlv::deserialize_tlv8(&plaintext)?;
        // The pinned client's chosen short synthetic name keeps its original
        // unchunked Info below 255 bytes. Reject rather than repair malformed TLV.
        if tlv::serialize_tlv8(&entries) != plaintext { return Err(rejected()); }
        let public: [u8; 32] = component(&entries, Tt::PublicKey).try_into().map_err(|_| rejected())?;
        let signature = Signature::from_slice(&component(&entries, Tt::Signature)).map_err(|_| rejected())?;
        let mut signed = self.controller_x.as_ref().ok_or_else(rejected)?.to_vec();
        signed.extend_from_slice(&component(&entries, Tt::Identifier)); signed.extend_from_slice(&public);
        VerifyingKey::from_bytes(&public).map_err(|_| rejected())?
            .verify_strict(&signed, &signature).map_err(|_| rejected())?;
        self.progress.m5_original_signature_verified.store(true, Ordering::SeqCst);
        let info = component(&entries, Tt::Info);
        let mut dictionary = opack::opack_to_plist_bounded(&info)
            .map_err(|_| rejected())?.into_dictionary().ok_or_else(rejected)?;
        if dictionary.contains_key("remotepairing_udid") { return Err(rejected()); }
        dictionary.insert("remotepairing_udid".into(), plist::Value::String(PHONE_UDID.into()));
        match self.mode {
            Mode::MismatchedControllerAccount => {
                dictionary.insert("accountID".into(), plist::Value::String("different-controller".into()));
            }
            Mode::WrongControllerAccountType => {
                dictionary.insert("accountID".into(), plist::Value::Data(component(&entries, Tt::Identifier)));
            }
            _ => {}
        }
        let info = opack::plist_to_opack(&plist::Value::Dictionary(dictionary));
        let mut adapted = Vec::new();
        // Preserve the real client identity here; explicit negative modes mutate it below.
        // Info itself is not in the Ed25519 signature; the entire M5 is AEAD-bound.
        for entry in entries.into_iter().filter(|entry| entry.tlv_type != Tt::Info) {
            adapted.extend(chunk(entry.tlv_type, &entry.data));
        }
        adapted.extend(chunk(Tt::Info, &info));
        let fault_type = match self.mode {
            Mode::InvalidControllerSignature | Mode::ShortControllerSignature
            | Mode::LongControllerSignature | Mode::WrongControllerSignatureType => Some(Tt::Signature),
            Mode::WrongControllerPublicKey | Mode::ShortControllerPublicKey => Some(Tt::PublicKey),
            _ => None,
        };
        if let Some(kind) = fault_type {
            let entry = adapted.iter_mut().find(|entry| entry.tlv_type == kind).ok_or_else(rejected)?;
            match self.mode {
                Mode::InvalidControllerSignature => { *entry.data.last_mut().ok_or_else(rejected)? ^= 1; }
                Mode::WrongControllerPublicKey => {
                    entry.data = ed25519_dalek::SigningKey::from_bytes(&[0x28; 32])
                        .verifying_key().to_bytes().to_vec();
                }
                Mode::ShortControllerSignature | Mode::ShortControllerPublicKey => { entry.data.pop().ok_or_else(rejected)?; }
                Mode::LongControllerSignature => { entry.data.push(0); }
                Mode::WrongControllerSignatureType => { entry.tlv_type = Tt::Proof; }
                _ => return Err(rejected()),
            }
        }
        self.progress.m5_identity_mutated.store(self.mode.invalid_controller_identity(), Ordering::SeqCst);
        let adapted = tlv::serialize_tlv8(&adapted);
        let mut ciphertext = cipher.encrypt(Nonce::from_slice(b"\0\0\0\0PS-Msg05"),
            Payload { msg: &adapted, aad: b"" }).map_err(|_| rejected())?;
        // Check the exact outgoing ciphertext before any deliberate tag fault.
        // Identity-negative modes retain this valid authentication tag.
        let checked = cipher.decrypt(Nonce::from_slice(b"\0\0\0\0PS-Msg05"),
            Payload { msg: &ciphertext, aad: b"" }).map_err(|_| rejected())?;
        if checked != adapted { return Err(rejected()); }
        self.progress.m5_aead_verified.store(true, Ordering::SeqCst);
        if self.mode == Mode::TamperM5 {
            let byte = ciphertext.last_mut().ok_or_else(rejected)?;
            *byte ^= 1; // Change authentication tag only, after legitimate encryption.
        }
        let mut outer = chunk(Tt::EncryptedData, &ciphertext);
        outer.push(TLV8Entry { tlv_type: Tt::State, data: vec![5] });
        *data = serde_json::Value::String(B64.encode(tlv::serialize_tlv8(&outer)));
        self.progress.m5_adapted.store(true, Ordering::SeqCst);
        Ok(())
    }

    async fn send(&mut self, mut value: serde_json::Value, seq: usize) -> Result<(), IdeviceError> {
        let count = self.progress.sent_frames.load(Ordering::SeqCst);
        if count >= 4 || seq != count { return Err(rejected()); }
        if count == 3 {
            self.progress.before_m5.store(true, Ordering::SeqCst);
            if self.mode == Mode::PauseBeforeM5 {
                // The harness owns this future, enforces a finite peer timeout,
                // and drops it only after native return before joining its thread.
                std::future::pending::<()>().await;
            }
            self.adapt_m5(&mut value)?;
        }
        let envelope = serde_json::json!({ "message": { "plain": { "_0": value } },
            "originatedBy": "host", "sequenceNumber": seq });
        if !json_bounded(&envelope, 0, &mut 0) { return Err(rejected()); }
        let bytes = serde_json::to_vec(&envelope)?;
        let total = self.progress.sent_bytes.load(Ordering::SeqCst) + bytes.len() + 11;
        if bytes.is_empty() || bytes.len() > FRAME_CAP || total > WIRE_CAP { return Err(rejected()); }
        self.io.write_all(RPPAIRING_MAGIC).await?;
        self.io.write_all(&(bytes.len() as u16).to_be_bytes()).await?;
        self.io.write_all(&bytes).await?;
        self.io.flush().await?;
        self.progress.sent_frames.store(count + 1, Ordering::SeqCst);
        self.progress.sent_bytes.store(total, Ordering::SeqCst);
        Ok(())
    }

    async fn receive(&mut self) -> Result<plist::Value, IdeviceError> {
        let count = self.progress.received_frames.load(Ordering::SeqCst);
        if count >= 4 { return Err(rejected()); }
        let mut header = [0; 11];
        self.io.read_exact(&mut header).await?;
        if &header[..9] != RPPAIRING_MAGIC { return Err(rejected()); }
        let len = u16::from_be_bytes([header[9], header[10]]) as usize;
        let total = self.progress.received_bytes.load(Ordering::SeqCst) + len + 11;
        if len == 0 || len > FRAME_CAP || total > WIRE_CAP { return Err(rejected()); }
        let mut bytes = vec![0; len];
        self.io.read_exact(&mut bytes).await?;
        let value: serde_json::Value = serde_json::from_slice(&bytes)?;
        if !json_bounded(&value, 0, &mut 0)
            || value.get("originatedBy").and_then(|v| v.as_str()) != Some("device")
            || value.get("sequenceNumber").and_then(|v| v.as_u64()) != Some(count as u64) {
            return Err(rejected());
        }
        let value = value.pointer("/message/plain/_0").ok_or_else(rejected)?;
        // Validate every expected response state, including before invoking the
        // pinned client's M6 decrypt routine (which otherwise panics on bad AEAD).
        if count != 0 {
            let data = value.pointer("/event/_0/pairingData/_0/data")
                .and_then(|v| v.as_str()).ok_or_else(rejected)?;
            let outer = tlv::deserialize_tlv8(&B64.decode(data).map_err(|_| rejected())?)?;
            let expected = (count * 2) as u8;
            // Wrong PIN legitimately returns M4 with ErrorResponse; the original
            // client's SRP method must reject it, not a replacement fixture result.
            if component(&outer, Tt::State) != [expected] { return Err(rejected()); }
            if count == 3 {
                state(&outer, 6)?;
                let cipher = self.setup_cipher.as_ref().ok_or_else(rejected)?;
                cipher.decrypt(Nonce::from_slice(b"\0\0\0\0PS-Msg06"),
                    Payload { msg: &component(&outer, Tt::EncryptedData), aad: b"" })
                    .map_err(|_| rejected())?;
            }
        }
        self.progress.received_frames.store(count + 1, Ordering::SeqCst);
        self.progress.received_bytes.store(total, Ordering::SeqCst);
        plist::to_value(value).map_err(|_| rejected())
    }
}

impl<S: crate::ReadWrite> RpPairingSocketProvider for PhoneSocket<S> {
    fn send_plain(&mut self, value: impl Serialize, seq: usize)
        -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let value = serde_json::to_value(value);
        Box::pin(async move { self.send(value?, seq).await })
    }
    fn send_encrypted(&mut self, _: Vec<u8>, _: usize)
        -> Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        Box::pin(async { Err(rejected()) })
    }
    fn recv_plain<'a>(&'a mut self)
        -> Pin<Box<dyn Future<Output = Result<plist::Value, IdeviceError>> + Send + 'a>> {
        Box::pin(async move { self.receive().await })
    }
    fn serialize_bytes(bytes: &[u8]) -> plist::Value { plist::Value::String(B64.encode(bytes)) }
    fn deserialize_bytes(value: plist::Value) -> Option<Vec<u8>> {
        let value = value.into_string()?;
        if value.len() > FRAME_CAP { return None; }
        B64.decode(value).ok()
    }
}

/// Runs the real pinned SRP client inside a bounded phone transport. The caller
/// must own and bound this future; no worker or transport is spawned here.
pub async fn run<S, F, Fut>(io: S, mode: Mode, progress: Arc<Progress>, pin: F)
    -> Result<Evidence, IdeviceError>
where S: crate::ReadWrite, F: Fn() -> Fut, Fut: Future<Output = String> {
    let socket = PhoneSocket { io, progress: Arc::clone(&progress), setup_cipher: None, controller_x: None, mode };
    let mut client = RemotePairingClient::new(socket, PHONE_NAME);
    // Public connect() always requests pair-verify. This phone route instead
    // requests pair-setup; the production responder rejection remains unchanged.
    client.inner.send_plain(plist!({ "request": { "_0": { "handshake": { "_0": {
        "hostOptions": { "attemptPairVerify": false },
        "wireProtocolVersion": plist::Value::Integer(WIRE_PROTOCOL_VERSION.into())
    } } } } }), 0).await?;
    client.sequence_number += 1;
    let greeting = client.inner.recv_plain().await?;
    let greeting = greeting.get_by("response").and_then(|v| v.get_by("_1"))
        .and_then(|v| v.get_by("handshake")).and_then(|v| v.get_by("_0")).ok_or_else(rejected)?;
    let options = greeting.get_by("deviceOptions").ok_or_else(rejected)?;
    if options.get_by("allowsPairSetup").and_then(|v| v.as_boolean()) != Some(true)
        || options.get_by("allowsPinlessPairing").and_then(|v| v.as_boolean()) != Some(false) {
        return Err(rejected());
    }
    progress.greeting_verified.store(true, Ordering::SeqCst);
    let (salt, public, mut pin) = client.request_pair_consent(pin).await?;
    if pin.len() != 6 || !pin.bytes().all(|b| b.is_ascii_digit()) { return Err(rejected()); }
    if mode == Mode::WrongPin {
        let mut bytes = pin.into_bytes(); bytes[0] = if bytes[0] == b'9' { b'0' } else { bytes[0] + 1 };
        pin = String::from_utf8(bytes).map_err(|_| rejected())?;
    }
    let key = client.init_srp_context(&salt, &public, &pin).await?;
    if key.len() != 64 { return Err(rejected()); }
    progress.srp_verified.store(true, Ordering::SeqCst);
    let mut setup_key = [0; 32];
    Hkdf::<Sha512>::new(Some(b"Pair-Setup-Encrypt-Salt"), &key)
        .expand(b"Pair-Setup-Encrypt-Info", &mut setup_key).map_err(|_| rejected())?;
    client.inner.setup_cipher = Some(ChaCha20Poly1305::new(Key::from_slice(&setup_key)));
    let mut controller_x = [0; 32];
    Hkdf::<Sha512>::new(Some(b"Pair-Setup-Controller-Sign-Salt"), &key)
        .expand(b"Pair-Setup-Controller-Sign-Info", &mut controller_x).map_err(|_| rejected())?;
    client.inner.controller_x = Some(controller_x);
    let mut phone_record = RpPairingFile::generate(PHONE_NAME);
    let response = client.save_pair_record_on_peer(&mut phone_record, &key).await?;
    let identifier = component(&response, Tt::Identifier);
    let public: [u8; 32] = component(&response, Tt::PublicKey).try_into().map_err(|_| rejected())?;
    let signature = Signature::from_slice(&component(&response, Tt::Signature)).map_err(|_| rejected())?;
    let mut accessory_x = [0; 32];
    Hkdf::<Sha512>::new(Some(b"Pair-Setup-Accessory-Sign-Salt"), &key)
        .expand(b"Pair-Setup-Accessory-Sign-Info", &mut accessory_x).map_err(|_| rejected())?;
    let mut signed = accessory_x.to_vec(); signed.extend_from_slice(&identifier); signed.extend_from_slice(&public);
    VerifyingKey::from_bytes(&public).map_err(|_| rejected())?
        .verify_strict(&signed, &signature).map_err(|_| rejected())?;
    let info = component(&response, Tt::Info);
    let dictionary = opack::opack_to_plist_bounded(&info).map_err(|_| rejected())?
        .into_dictionary().ok_or_else(rejected)?;
    let host = PeerDevice::try_from_info_dictionary(&dictionary)?;
    let identifier = String::from_utf8(identifier).map_err(|_| rejected())?;
    if identifier != host.account_id { return Err(rejected()); }
    progress.m6_verified.store(true, Ordering::SeqCst);
    Ok(Evidence { identifier, public_key: public, host_alt_irk: host.alt_irk,
        host_name: host.name, host_model: host.model })
}
