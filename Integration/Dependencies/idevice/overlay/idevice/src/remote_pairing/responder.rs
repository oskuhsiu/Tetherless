//! Device-initiated remote pairing (the "pairable host" / responder side).
//!
//! Starting with iOS 27, a device can initiate pairing to a
//! computer instead of the computer initiating pairing to the device. The
//! computer advertises an `_remotepairing-pairable-host._tcp` mDNS service; the
//! device connects to the advertised port and drives an rppairing conversation.
//!
//! In that conversation the roles are flipped relative to [`super::RemotePairingClient`]:
//! the device plays the rppairing "host" (it sends `originatedBy: "host"`,
//! initiates the handshake and the SRP pair-setup), while the computer
//! play the rppairing "device"/accessory (`originatedBy: "device"`). We generate
//! and display the setup PIN; the user types it into the iOS device.

use base64::{Engine as _, engine::general_purpose::STANDARD as B64};
use chacha20poly1305::{
    ChaCha20Poly1305, Key, KeyInit, Nonce,
    aead::{Aead, Payload},
};
use ed25519_dalek::{Signature, VerifyingKey};
use hkdf::Hkdf;
use idevice_srp::{client::SrpClient, groups::G_3072, server::SrpServer};
use plist::Value;
use plist_macro::{PlistExt, plist};
use rand::{Rng as _, RngExt as _};
use rsa::signature::SignerMut as _;
use sha2::Sha512;
use tracing::{debug, warn};

use crate::IdeviceError;

use super::{
    PeerDevice, RpPairingFile, errors::RemotePairingError, opack, peer_device, tlv,
    tlv::PairingDataComponentType as Tt,
};

/// The DNS-SD service type a pairable host advertises over mDNS. A device browses
/// for this and, when the user taps "Pair with ...", connects to the advertised
/// host/port and drives the rppairing conversation handled by [`PairableHost`].
pub const PAIRABLE_HOST_SERVICE_TYPE: &str = "_remotepairing-pairable-host._tcp.local.";

/// Static information this host advertises and presents to a connecting device.
///
/// `name` and `model` are what the device displays to the user (e.g. a Mac shows
/// `model = "Mac17,7"`, `name = "Jackson's MacBook Pro"`). iOS treats the host as
/// a computer, so keep `model` a Mac identifier. The remaining fields can be left
/// at their defaults as pairing succeeds with empty `udid`/`identifier` and without
/// any `deviceKVSData`.
#[derive(Debug, Clone)]
pub struct PairableHostInfo {
    /// Human-readable name shown on the device, e.g. `"Jackson's MacBook Pro"`.
    pub name: String,
    /// Hardware model identifier shown on the device, e.g. `"Mac17,7"`.
    pub model: String,
    /// UDID reported in `peerDeviceInfo`. May be left empty.
    pub udid: String,
    /// Identifier reported in `peerDeviceInfo`. May be left empty.
    pub identifier: String,
    /// Wire protocol version reported during the handshake. Recent iOS uses 26.
    pub wire_protocol_version: u8,
    /// Our 16-byte mDNS identity key. It is sent to the device during pairing
    /// (M6) and must match the `altIRK` used to compute the `authTag` advertised
    /// in the `_remotepairing-pairable-host._tcp` record, so an already-paired
    /// device can recognize this host. Persist it across runs alongside the
    /// pairing file.
    ///
    /// See [`Self::mdns_txt_records`] and [`crate::remote_pairing::compute_auth_tag`].
    pub alt_irk: [u8; 16],
    /// Advertise pinless pairing support. When enabled, pair-setup uses Apple's
    /// conventional all-zero setup code instead of a user-entered random PIN.
    pub allows_pinless_pairing: bool,
}

impl PairableHostInfo {
    /// Creates host info for the given name/model with a freshly generated random
    /// `alt_irk`. Persist [`Self::alt_irk`] so reconnecting devices keep working.
    pub fn generate(name: impl Into<String>, model: impl Into<String>) -> Self {
        let mut alt_irk = [0u8; 16];
        rand::rng().fill_bytes(&mut alt_irk);
        Self {
            name: name.into(),
            model: model.into(),
            alt_irk,
            ..Default::default()
        }
    }

    /// Creates a fresh staged identity, so a repair attempt does not deliberately
    /// reuse the old peer-side host identifier before local validation succeeds.
    /// The legacy name-derived generator remains unchanged.
    pub fn generate_staged_record(&self) -> RpPairingFile {
        let mut record = RpPairingFile::generate(&self.name);
        record.identifier = uuid::Uuid::new_v4().to_string();
        record
    }

    /// Builds the TXT records to publish for the [`PAIRABLE_HOST_SERVICE_TYPE`]
    /// mDNS service, as `(key, value)` pairs suitable for any mDNS library.
    ///
    /// `service_identifier` is the host's stable identifier and must be the same
    /// value used as the mDNS service instance name and sent to the device during
    /// pairing, pass [`RpPairingFile::identifier`]. The `authTag` is derived from
    /// [`Self::alt_irk`] and this identifier so an already-paired device can
    /// recognize the host.
    pub fn mdns_txt_records(&self, service_identifier: &str) -> Vec<(String, String)> {
        let auth_tag = B64.encode(peer_device::compute_auth_tag(
            &self.alt_irk,
            service_identifier,
        ));
        vec![
            ("name".into(), self.name.clone()),
            ("identifier".into(), service_identifier.to_string()),
            ("authTag".into(), auth_tag),
            ("model".into(), self.model.clone()),
            ("flags".into(), "1".into()),
            ("ver".into(), self.wire_protocol_version.to_string()),
            ("minVer".into(), "17".into()),
        ]
    }
}

impl Default for PairableHostInfo {
    fn default() -> Self {
        Self {
            name: "idevice-rs".to_string(),
            model: "Mac17,7".to_string(),
            udid: String::new(),
            identifier: String::new(),
            wire_protocol_version: 26,
            alt_irk: [0u8; 16],
            allows_pinless_pairing: false,
        }
    }
}

/// SRP username used by Apple's pair-setup. Both sides hash with this.
const SRP_USERNAME: &[u8] = b"Pair-Setup";

/// The responder side of rppairing: accepts a device-initiated pairing.
///
/// Construct one around a socket configured for the responder role
/// ([`super::RpPairingSocket::new_device`]) and call [`Self::accept`].
pub struct PairableHost<R: super::RpPairingSocketProvider> {
    inner: R,
    host_info: PairableHostInfo,
    /// Our own send-side sequence counter (the device maintains its own).
    sequence_number: usize,
    /// The SRP session key established during pairing.
    encryption_key: Vec<u8>,
    paired_peer_device: Option<PeerDevice>,
    bounded_host: bool,
}

impl<R: super::RpPairingSocketProvider> PairableHost<R> {
    pub fn new(inner: R, host_info: PairableHostInfo) -> Self {
        Self {
            inner,
            host_info,
            sequence_number: 0,
            encryption_key: Vec::new(),
            paired_peer_device: None,
            bounded_host: false,
        }
    }

    /// Caller-owned host path with explicit peer-info and SRP work limits.
    /// Authenticates the M5 controller identity before replying or accepting peer metadata.
    /// The caller also owns bounded framing, cancellation and the operation deadline.
    pub fn new_bounded(inner: R, host_info: PairableHostInfo) -> Self {
        let mut host = Self::new(inner, host_info);
        host.bounded_host = true;
        host
    }

    /// The SRP session key established during the most recent successful pairing.
    pub fn encryption_key(&self) -> &[u8] {
        &self.encryption_key
    }

    /// Accept a device-initiated pairing.
    ///
    /// Performs the handshake and the full SRP pair-setup. `pin_callback` is
    /// invoked with the 6-digit setup code that should be displayed to the user
    /// to enter on the device.
    ///
    /// On success the device's identity (including its `altIRK`) is stored in
    /// `pairing_file.alt_irk` and the parsed [`PeerDevice`] is returned. The
    /// caller is responsible for persisting `pairing_file`.
    pub async fn accept<Fut>(
        &mut self,
        pairing_file: &mut RpPairingFile,
        pin_callback: impl FnOnce(String) -> Fut,
    ) -> Result<PeerDevice, IdeviceError>
    where
        Fut: std::future::Future<Output = ()>,
    {
        if self.bounded_host && self.host_info.allows_pinless_pairing {
            return Err(IdeviceError::UnexpectedResponse("bounded host requires a PIN".into()));
        }
        self.handshake().await?;
        let peer_device = self.pair_setup(pairing_file, pin_callback).await?;
        Ok(peer_device)
    }

    /// Receive the device's handshake request and reply with our device info.
    async fn handshake(&mut self) -> Result<(), IdeviceError> {
        debug!("Waiting for device handshake request");
        let request = self.inner.recv_plain().await?;
        debug!("Handshake request: {request:#?}");

        let handshake = request
            .get_by("request")
            .and_then(|x| x.get_by("_0"))
            .and_then(|x| x.get_by("handshake"))
            .and_then(|x| x.get_by("_0"))
            .ok_or(IdeviceError::UnexpectedResponse(
                "missing request._0.handshake._0 in device handshake".into(),
            ))?;

        if handshake
            .get_by("hostOptions")
            .and_then(|x| x.get_by("attemptPairVerify"))
            .and_then(|x| x.as_boolean())
            .unwrap_or(false)
        {
            return Err(IdeviceError::UnexpectedResponse(
                "device requested pair-verify; only device-initiated pair-setup is supported"
                    .into(),
            ));
        }

        let mut peer_info = plist::Dictionary::new();
        peer_info.insert("udid".into(), Value::String(self.host_info.udid.clone()));
        peer_info.insert(
            "deviceKVSIncludesSensitiveInfo".into(),
            Value::Boolean(false),
        );
        peer_info.insert(
            "identifier".into(),
            Value::String(self.host_info.identifier.clone()),
        );
        peer_info.insert("name".into(), Value::String(self.host_info.name.clone()));
        peer_info.insert("model".into(), Value::String(self.host_info.model.clone()));

        let response = plist!({
            "response": {
                "forRequestIdentifier": 0,
                "_1": {
                    "handshake": {
                        "_0": {
                            "wireProtocolVersion": Value::Integer(
                                (self.host_info.wire_protocol_version as i64).into(),
                            ),
                            "minimumSupportedWireProtocolVersion": 8,
                            "deviceOptions": {
                                "allowsPairSetup": true,
                                "allowsPinlessPairing": self.host_info.allows_pinless_pairing,
                                "allowsIncomingTunnelConnections": false,
                                "allowsUpgradeOfLockdownPairings": false,
                                "allowsSharingSensitiveInfo": false
                            },
                            "peerDeviceInfo": Value::Dictionary(peer_info)
                        }
                    }
                }
            }
        });

        debug!("Sending handshake response: {response:#?}");
        self.send_plain(response).await
    }

    /// Run the SRP pair-setup as the server/accessory (M1 - M6).
    async fn pair_setup<Fut>(
        &mut self,
        pairing_file: &mut RpPairingFile,
        pin_callback: impl FnOnce(String) -> Fut,
    ) -> Result<PeerDevice, IdeviceError>
    where
        Fut: std::future::Future<Output = ()>,
    {
        debug!("Waiting for pair-setup M1");
        let m1 = self.recv_pairing_tlv().await?;
        expect_state(&m1, 1)?;

        // m2
        let srp_client = SrpClient::<Sha512>::new(&G_3072);
        let srp_server = SrpServer::<Sha512>::new(&G_3072);

        let mut salt = [0u8; 16];
        rand::rng().fill_bytes(&mut salt);

        let pin = if self.host_info.allows_pinless_pairing {
            "000000".to_string()
        } else {
            format!("{:06}", rand::rng().random_range(0..1_000_000))
        };
        let verifier = srp_client.compute_verifier(SRP_USERNAME, pin.as_bytes(), &salt);

        let mut bounded_attempts = 0;
        let (b_priv, b_pub) = loop {
            if self.bounded_host {
                if bounded_attempts >= 16 {
                    return Err(IdeviceError::UnexpectedResponse("host SRP work budget".into()));
                }
                bounded_attempts += 1;
            }
            let mut b = [0u8; 32];
            rand::rng().fill_bytes(&mut b);
            let b_pub = srp_server.compute_public_ephemeral(&b, &verifier);
            if b_pub.len() == 384 {
                break (b, b_pub);
            }
        };

        // Display the PIN for the user to enter on the device.
        pin_callback(pin).await;

        let mut m2 = vec![
            tlv::TLV8Entry {
                tlv_type: Tt::State,
                data: vec![0x02],
            },
            tlv::TLV8Entry {
                tlv_type: Tt::Salt,
                data: salt.to_vec(),
            },
        ];
        m2.extend(chunk_tlv(Tt::PublicKey, &b_pub));
        debug!("Sending pair-setup M2 (salt + B)");
        self.send_pairing_tlv(&m2).await?;

        // m3
        debug!("Waiting for pair-setup M3");
        let m3 = self.recv_pairing_tlv().await?;
        ensure_no_error(&m3)?;
        expect_state(&m3, 3)?;

        let a_pub = tlv::collect_component_data(&m3, Tt::PublicKey);
        let client_proof = tlv::collect_component_data(&m3, Tt::Proof);
        if self.bounded_host { bounded_srp_inputs(&a_pub, &client_proof)?; }
        if a_pub.is_empty() || client_proof.is_empty() {
            return Err(IdeviceError::UnexpectedResponse(
                "pair-setup M3 missing public key or proof".into(),
            ));
        }

        let verifier = srp_server
            .process_reply(&b_priv, &verifier, &a_pub, SRP_USERNAME, &salt)
            .map_err(|e| {
                warn!("SRP process_reply failed: {e:?}");
                RemotePairingError::SrpAuthFailed
            })?;

        if verifier.verify_client(&client_proof).is_err() {
            warn!("SRP client proof verification failed (wrong PIN?)");
            // Tell the device authentication failed.
            self.send_pairing_tlv(&[
                tlv::TLV8Entry {
                    tlv_type: Tt::State,
                    data: vec![0x04],
                },
                tlv::TLV8Entry {
                    tlv_type: Tt::ErrorResponse,
                    data: vec![0x02], // kTLVError_Authentication
                },
            ])
            .await?;
            return Err(RemotePairingError::SrpAuthFailed.into());
        }

        if self.bounded_host && (verifier.key().len() != 64 || verifier.proof().len() != 64) {
            return Err(IdeviceError::UnexpectedResponse("bounded host SRP output size".into()));
        }
        let session_key = verifier.key().to_vec();

        // m4
        debug!("Sending pair-setup M4 (server proof)");
        self.send_pairing_tlv(&[
            tlv::TLV8Entry {
                tlv_type: Tt::State,
                data: vec![0x04],
            },
            tlv::TLV8Entry {
                tlv_type: Tt::Proof,
                data: verifier.proof().to_vec(),
            },
        ])
        .await?;

        // Derive the shared ChaCha20-Poly1305 key used for the M5/M6 exchange.
        let setup_cipher = {
            let hk = Hkdf::<Sha512>::new(Some(b"Pair-Setup-Encrypt-Salt"), &session_key);
            let mut key = [0u8; 32];
            hk.expand(b"Pair-Setup-Encrypt-Info", &mut key)
                .expect("HKDF expand failed");
            ChaCha20Poly1305::new(Key::from_slice(&key))
        };

        // m5
        debug!("Waiting for pair-setup M5 (device identity)");
        let m5 = self.recv_pairing_tlv().await?;
        ensure_no_error(&m5)?;
        expect_state(&m5, 5)?;

        let ciphertext = tlv::collect_component_data(&m5, Tt::EncryptedData);
        let plaintext = setup_cipher
            .decrypt(
                Nonce::from_slice(b"\x00\x00\x00\x00PS-Msg05"),
                Payload {
                    msg: &ciphertext,
                    aad: b"",
                },
            )
            .map_err(|e| {
                warn!("Failed to decrypt pair-setup M5: {e:?}");
                RemotePairingError::ChachaEncryption(e)
            })?;

        let device_tlv = tlv::deserialize_tlv8(&plaintext)?;
        debug!("Decrypted device identity TLV: {device_tlv:#?}");
        let peer_device = if self.bounded_host {
            bounded_authenticated_peer_device(&device_tlv, &session_key)?
        } else { peer_device::parse_peer_device_from_tlv(&device_tlv)? };

        // m6
        debug!("Sending pair-setup M6 (our identity)");
        let m6_plain = self.build_accessory_identity_tlv(pairing_file, &session_key);
        let m6_cipher = setup_cipher
            .encrypt(
                Nonce::from_slice(b"\x00\x00\x00\x00PS-Msg06"),
                Payload {
                    msg: &m6_plain,
                    aad: b"",
                },
            )
            .map_err(RemotePairingError::ChachaEncryption)?;

        let mut m6 = chunk_tlv(Tt::EncryptedData, &m6_cipher);
        m6.push(tlv::TLV8Entry {
            tlv_type: Tt::State,
            data: vec![0x06],
        });
        self.send_pairing_tlv(&m6).await?;

        // Store the device's altIRK so we can validate its future
        // `_remotepairing._tcp` advertisements.
        pairing_file.alt_irk = Some(peer_device.alt_irk.clone());
        self.encryption_key = session_key;
        self.paired_peer_device = Some(peer_device.clone());

        Ok(peer_device)
    }

    /// Builds the (plaintext) accessory identity TLV sent in M6: our identifier,
    /// long-term Ed25519 public key, a signature over them, and an OPACK info blob.
    fn build_accessory_identity_tlv(
        &self,
        pairing_file: &mut RpPairingFile,
        session_key: &[u8],
    ) -> Vec<u8> {
        // Accessory signature: Ed25519 over (AccessoryX || identifier || LTPK),
        // where AccessoryX is derived from the SRP session key.
        let mut accessory_x = [0u8; 32];
        Hkdf::<Sha512>::new(Some(b"Pair-Setup-Accessory-Sign-Salt"), session_key)
            .expand(b"Pair-Setup-Accessory-Sign-Info", &mut accessory_x)
            .expect("HKDF expand failed");

        let ltpk = pairing_file.e_public_key.to_bytes();
        let mut signbuf = Vec::with_capacity(32 + pairing_file.identifier.len() + 32);
        signbuf.extend_from_slice(&accessory_x);
        signbuf.extend_from_slice(pairing_file.identifier.as_bytes());
        signbuf.extend_from_slice(&ltpk);
        let signature = pairing_file.e_private_key.sign(&signbuf);

        let info = opack::plist_to_opack(&plist!({
            "altIRK": self.host_info.alt_irk.to_vec(),
            "btAddr": "11:22:33:44:55:66",
            "mac": vec![0x11u8, 0x22, 0x33, 0x44, 0x55, 0x66],
            "remotepairing_serial_number": "AAAAAAAAAAAA",
            "accountID": pairing_file.identifier.as_str(),
            "remotepairing_udid": self.host_info.udid.as_str(),
            "model": self.host_info.model.as_str(),
            "name": self.host_info.name.as_str()
        }));

        tlv::serialize_tlv8(&[
            tlv::TLV8Entry {
                tlv_type: Tt::Identifier,
                data: pairing_file.identifier.as_bytes().to_vec(),
            },
            tlv::TLV8Entry {
                tlv_type: Tt::PublicKey,
                data: ltpk.to_vec(),
            },
            tlv::TLV8Entry {
                tlv_type: Tt::Signature,
                data: signature.to_vec(),
            },
            tlv::TLV8Entry {
                tlv_type: Tt::Info,
                data: info,
            },
        ])
    }

    /// Send a plain (`message.plain`) envelope, bumping our sequence counter.
    async fn send_plain(&mut self, value: plist::Value) -> Result<(), IdeviceError> {
        self.inner.send_plain(value, self.sequence_number).await?;
        self.sequence_number += 1;
        Ok(())
    }

    /// Send a `pairingData` event carrying the given TLV entries.
    async fn send_pairing_tlv(&mut self, entries: &[tlv::TLV8Entry]) -> Result<(), IdeviceError> {
        let data = R::serialize_bytes(&tlv::serialize_tlv8(entries));
        self.send_plain(plist!({
            "event": {
                "_0": {
                    "pairingData": {
                        "_0": {
                            "data": data,
                            "startNewSession": false,
                            "kind": "setupManualPairing"
                        }
                    }
                }
            }
        }))
        .await
    }

    /// Receive a `pairingData` event and decode its TLV payload.
    async fn recv_pairing_tlv(&mut self) -> Result<Vec<tlv::TLV8Entry>, IdeviceError> {
        let response = self.inner.recv_plain().await?;

        let data = response
            .get_by("event")
            .and_then(|x| x.get_by("_0"))
            .and_then(|x| x.get_by("pairingData"))
            .and_then(|x| x.get_by("_0"))
            .and_then(|x| x.get_by("data"))
            .ok_or(IdeviceError::UnexpectedResponse(
                "missing event._0.pairingData._0.data in device message".into(),
            ))?;

        let bytes = R::deserialize_bytes(data.to_owned()).ok_or(
            IdeviceError::UnexpectedResponse("failed to deserialize pairing data bytes".into()),
        )?;

        Ok(tlv::deserialize_tlv8(&bytes)?)
    }
}

/// Split `data` into TLV entries of at most 255 bytes each (the TLV length limit).
fn chunk_tlv(tlv_type: Tt, data: &[u8]) -> Vec<tlv::TLV8Entry> {
    data.chunks(255)
        .map(|chunk| tlv::TLV8Entry {
            tlv_type,
            data: chunk.to_vec(),
        })
        .collect()
}

/// Returns an error if the TLV stream contains an `ErrorResponse` component.
fn ensure_no_error(entries: &[tlv::TLV8Entry]) -> Result<(), IdeviceError> {
    if let Some(err) = entries.iter().find(|e| e.tlv_type == Tt::ErrorResponse) {
        return Err(IdeviceError::UnexpectedResponse(format!(
            "device returned pairing error: {:?}",
            err.data
        )));
    }
    Ok(())
}

/// Validates that the TLV stream carries the expected `State` value.
fn expect_state(entries: &[tlv::TLV8Entry], expected: u8) -> Result<(), IdeviceError> {
    let state = entries
        .iter()
        .find(|e| e.tlv_type == Tt::State)
        .and_then(|e| e.data.first().copied());
    match state {
        Some(s) if s == expected => Ok(()),
        other => Err(IdeviceError::UnexpectedResponse(format!(
            "unexpected pair-setup state: expected {expected}, got {other:?}"
        ))),
    }
}

impl<R: super::RpPairingSocketProvider> std::fmt::Debug for PairableHost<R> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("PairableHost")
            .field("inner", &self.inner)
            .field("sequence_number", &self.sequence_number)
            .field("host_info", &self.host_info)
            .finish()
    }
}


fn bounded_srp_inputs(public_key: &[u8], proof: &[u8]) -> Result<(), IdeviceError> {
    // The pinned client can emit short big-endian group values. Bound the
    // representation to G3072 width without requiring otherwise unnecessary pad bytes.
    if public_key.is_empty() || public_key.len() > 384 || proof.len() != 64 {
        return Err(IdeviceError::UnexpectedResponse("bounded host SRP input size".into()));
    }
    // Public group element must satisfy 0 < A < N. These bytes are public input;
    // comparison introduces no secret-dependent branch or new cryptographic primitive.
    let modulus = G_3072.n.to_bytes_be();
    let leading_zeroes = public_key.iter().take_while(|b| **b == 0).count();
    let value = &public_key[leading_zeroes..];
    if modulus.len() != 384 || value.is_empty()
        || (value.len() == modulus.len() && value >= modulus.as_slice()) {
        return Err(IdeviceError::UnexpectedResponse("bounded host SRP public value".into()));
    }
    Ok(())
}

fn controller_identity_error() -> IdeviceError {
    IdeviceError::UnexpectedResponse("bounded host controller identity rejected".into())
}

/// Authenticates exactly the pinned client's ControllerX || Identifier || LTPK.
/// These bounded fields all fit in one TLV8 entry; reject missing, duplicate or
/// fragmented values rather than authenticate an ambiguous concatenation.
fn bounded_controller_identity<'a>(
    entries: &'a [tlv::TLV8Entry], session_key: &[u8],
) -> Result<&'a str, IdeviceError> {
    fn component(entries: &[tlv::TLV8Entry], kind: Tt) -> Result<&[u8], IdeviceError> {
        let mut found = entries.iter().filter(|entry| entry.tlv_type == kind);
        let value = found.next().ok_or_else(controller_identity_error)?;
        if found.next().is_some() { return Err(controller_identity_error()); }
        Ok(&value.data)
    }
    if session_key.len() != 64 { return Err(controller_identity_error()); }
    let identifier = component(entries, Tt::Identifier)?;
    if identifier.is_empty() || identifier.len() > 128 { return Err(controller_identity_error()); }
    let identifier = std::str::from_utf8(identifier).map_err(|_| controller_identity_error())?;
    if identifier.chars().any(char::is_control) { return Err(controller_identity_error()); }
    let public: &[u8; 32] = component(entries, Tt::PublicKey)?
        .try_into().map_err(|_| controller_identity_error())?;
    let signature = Signature::from_slice(component(entries, Tt::Signature)?)
        .map_err(|_| controller_identity_error())?;
    let key = VerifyingKey::from_bytes(public).map_err(|_| controller_identity_error())?;
    let mut controller_x = [0u8; 32];
    Hkdf::<Sha512>::new(Some(b"Pair-Setup-Controller-Sign-Salt"), session_key)
        .expand(b"Pair-Setup-Controller-Sign-Info", &mut controller_x)
        .map_err(|_| controller_identity_error())?;
    let mut signed = Vec::with_capacity(32 + identifier.len() + 32);
    signed.extend_from_slice(&controller_x);
    signed.extend_from_slice(identifier.as_bytes());
    signed.extend_from_slice(public);
    key.verify_strict(&signed, &signature).map_err(|_| controller_identity_error())?;
    Ok(identifier)
}

fn bounded_authenticated_peer_device(
    entries: &[tlv::TLV8Entry], session_key: &[u8],
) -> Result<PeerDevice, IdeviceError> {
    ensure_no_error(entries)?;
    let identifier = bounded_controller_identity(entries, session_key)?;
    let peer = bounded_peer_device(entries)?;
    // The accepted peer identity must be the identifier whose key possession
    // was proved. Info remains AEAD-bound; it is not part of the signature.
    if peer.account_id != identifier { return Err(controller_identity_error()); }
    Ok(peer)
}

fn bounded_peer_device(entries: &[tlv::TLV8Entry]) -> Result<PeerDevice, IdeviceError> {
    ensure_no_error(entries)?;
    let info = tlv::collect_component_data(entries, Tt::Info);
    let parsed = opack::opack_to_plist_bounded(&info)
        .map_err(|_| IdeviceError::UnexpectedResponse("bounded host OPACK rejected".into()))?;
    let dict = parsed.as_dictionary()
        .ok_or_else(|| IdeviceError::UnexpectedResponse("bounded host peer-info type".into()))?;
    let peer = PeerDevice::try_from_info_dictionary(dict)?;
    for (value, maximum) in [(&peer.account_id, 128), (&peer.model, 128),
                              (&peer.name, 256), (&peer.remotepairing_udid, 128)] {
        if value.is_empty() || value.len() > maximum || value.chars().any(char::is_control) {
            return Err(IdeviceError::UnexpectedResponse("bounded host peer-info size".into()));
        }
    }
    Ok(peer)
}

#[cfg(test)]
mod bounded_host_tests {
    use super::*;

    #[test]
    fn srp_inputs_are_exact_before_expensive_work() {
        assert!(bounded_srp_inputs(&[1u8; 384], &[1u8; 64]).is_ok());
        for size in [1, 383] { assert!(bounded_srp_inputs(&vec![1; size], &[1; 64]).is_ok()); }
        for size in [0, 385, 16384] {
            assert!(bounded_srp_inputs(&vec![1; size], &[1; 64]).is_err());
        }
        for size in [0, 1, 63, 65, 16384] {
            assert!(bounded_srp_inputs(&[1; 384], &vec![1; size]).is_err());
        }
    }

    #[test]
    fn rejects_noncontributory_public_values_and_tests_locked_primitive_guard() {
        let modulus = G_3072.n.to_bytes_be();
        assert!(bounded_srp_inputs(&[0; 384], &[1; 64]).is_err());
        assert!(bounded_srp_inputs(&modulus, &[1; 64]).is_err());
        assert!(bounded_srp_inputs(&[255; 384], &[1; 64]).is_err());
        let client = SrpClient::<Sha512>::new(&G_3072);
        let server = SrpServer::<Sha512>::new(&G_3072);
        let salt = [1u8; 16];
        let verifier = client.compute_verifier(SRP_USERNAME, b"synthetic password", &salt);
        let twice_modulus = (&G_3072.n << 1usize).to_bytes_be();
        for public in [vec![0u8; 384], modulus, twice_modulus] {
            assert!(server.process_reply(&[2u8; 32], &verifier, &public, SRP_USERNAME, &salt).is_err());
        }
    }

    fn info(name: &str) -> Vec<tlv::TLV8Entry> {
        let value = crate::plist!({ "accountID": "synthetic-account", "altIRK": vec![1u8; 16],
            "model": "synthetic-model", "name": name, "remotepairing_udid": "synthetic-id" });
        vec![tlv::TLV8Entry { tlv_type: Tt::Info, data: opack::plist_to_opack(&value) }]
    }

    #[test]
    fn bounded_peer_metadata_rejects_control_and_oversize_fields() {
        assert!(bounded_peer_device(&info("synthetic")).is_ok());
        for name in ["".to_string(), "x".repeat(257), "bad\nname".to_string()] {
            assert!(bounded_peer_device(&info(&name)).is_err());
        }
    }

    #[test]
    fn staged_records_with_same_display_name_have_independent_identifiers() {
        let info = PairableHostInfo::generate("synthetic host", "Mac17,7");
        let first = info.generate_staged_record();
        let second = info.generate_staged_record();
        assert_ne!(first.identifier(), second.identifier());
        assert_ne!(first.identifier(), RpPairingFile::generate(&info.name).identifier());
        assert_eq!(uuid::Uuid::parse_str(first.identifier()).unwrap().get_version_num(), 4);
        assert_eq!(first.public_key_bytes().len(), 32);
        assert_eq!(first.private_key_bytes().len(), 32);
    }

    #[test]
    fn host_generated_record_has_fixed_small_serialization() {
        let mut record = RpPairingFile::generate("synthetic host");
        record.alt_irk = Some(vec![1u8; 16]);
        let bytes = record.to_bytes();
        assert!(bytes.len() <= 4096);
        assert_eq!(RpPairingFile::from_bytes(&bytes).unwrap().alt_irk().unwrap().len(), 16);
    }
}

/// Private-to-host protocol adapter; no listener, advertiser or task is created.
pub struct BoundedHostSocket<R: crate::ReadWrite> {
    inner: R,
    received: usize,
    sent: usize,
    receive_messages: usize,
    send_messages: usize,
    continuing: std::sync::Arc<dyn Fn() -> bool + Send + Sync>,
}
impl<R: crate::ReadWrite> std::fmt::Debug for BoundedHostSocket<R> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str("BoundedHostSocket") }
}

impl<R: crate::ReadWrite> PairableHost<BoundedHostSocket<R>> {
    pub fn new_bounded_stream(stream: R, host_info: PairableHostInfo) -> Self {
        Self::new_bounded_stream_checked(stream, host_info, || true)
    }
    pub fn new_bounded_stream_checked(
        stream: R, host_info: PairableHostInfo, continuing: impl Fn() -> bool + Send + Sync + 'static,
    ) -> Self {
        Self::new_bounded(BoundedHostSocket { inner: stream, received: 0, sent: 0,
            receive_messages: 0, send_messages: 0, continuing: std::sync::Arc::new(continuing) }, host_info)
    }
}

impl<R: crate::ReadWrite> BoundedHostSocket<R> {
    async fn send_encoded(&mut self, bytes: Vec<u8>) -> Result<(), IdeviceError> {
        use tokio::io::AsyncWriteExt;
        if !(self.continuing)() || bytes.is_empty() || bytes.len() > 16_384 || self.send_messages >= 4 {
            return Err(host_frame_error());
        }
        self.sent = self.sent.checked_add(bytes.len() + 11).ok_or_else(host_frame_error)?;
        if self.sent > 131_072 { return Err(host_frame_error()); }
        self.send_messages += 1;
        self.inner.write_all(b"RPPairing").await?;
        self.inner.write_all(&(bytes.len() as u16).to_be_bytes()).await?;
        self.inner.write_all(&bytes).await?;
        self.inner.flush().await?;
        Ok(())
    }
}

fn host_frame_error() -> IdeviceError {
    IdeviceError::UnexpectedResponse("bounded host frame rejected".into())
}

fn host_json_bounded(value: &serde_json::Value, depth: usize, nodes: &mut usize) -> bool {
    if depth > 16 || *nodes >= 512 { return false; }
    *nodes += 1;
    match value {
        serde_json::Value::Array(items) => items.iter().all(|v| host_json_bounded(v, depth + 1, nodes)),
        serde_json::Value::Object(items) => items.iter().all(|(k, v)|
            k.len() <= 128 && host_json_bounded(v, depth + 1, nodes)),
        serde_json::Value::String(s) => s.len() <= 16_384,
        _ => true,
    }
}

impl<R: crate::ReadWrite> super::RpPairingSocketProvider for BoundedHostSocket<R> {
    fn send_plain(&mut self, value: impl serde::Serialize, seq: usize)
        -> std::pin::Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let encoded = serde_json::to_value(value).and_then(|value| serde_json::to_vec(&serde_json::json!({
            "message": {"plain": {"_0": value}}, "originatedBy": "device", "sequenceNumber": seq
        })));
        Box::pin(async move { self.send_encoded(encoded.map_err(|_| host_frame_error())?).await })
    }

    fn send_encrypted(&mut self, ciphertext: Vec<u8>, seq: usize)
        -> std::pin::Pin<Box<dyn Future<Output = Result<(), IdeviceError>> + Send + '_>> {
        let encoded = if ciphertext.len() > 8192 { Err(host_frame_error()) } else {
            serde_json::to_vec(&serde_json::json!({
                "message": {"streamEncrypted": {"_0": B64.encode(&ciphertext)}},
                "originatedBy": "device", "sequenceNumber": seq
            })).map_err(|_| host_frame_error())
        };
        Box::pin(async move { self.send_encoded(encoded?).await })
    }

    fn recv_plain<'a>(&'a mut self)
        -> std::pin::Pin<Box<dyn Future<Output = Result<plist::Value, IdeviceError>> + Send + 'a>> {
        Box::pin(async move {
            use tokio::io::AsyncReadExt;
            if !(self.continuing)() || self.receive_messages >= 4 { return Err(host_frame_error()); }
            self.receive_messages += 1;
            let mut header = [0u8; 11];
            self.inner.read_exact(&mut header).await?;
            if &header[..9] != b"RPPairing" { return Err(host_frame_error()); }
            let length = u16::from_be_bytes([header[9], header[10]]) as usize;
            if length == 0 || length > 16_384 { return Err(host_frame_error()); }
            self.received = self.received.checked_add(length + 11).ok_or_else(host_frame_error)?;
            if self.received > 131_072 { return Err(host_frame_error()); }
            let mut bytes = vec![0u8; length];
            self.inner.read_exact(&mut bytes).await?;
            if !(self.continuing)() { return Err(host_frame_error()); }
            let value: serde_json::Value = serde_json::from_slice(&bytes).map_err(|_| host_frame_error())?;
            if !host_json_bounded(&value, 0, &mut 0) { return Err(host_frame_error()); }
            if let Some(plain) = value.get("message").and_then(|v| v.get("plain")).and_then(|v| v.get("_0")) {
                plist::to_value(plain).map_err(|_| host_frame_error())
            } else { plist::to_value(&value).map_err(|_| host_frame_error()) }
        })
    }

    fn serialize_bytes(bytes: &[u8]) -> plist::Value { plist::Value::String(B64.encode(bytes)) }
    fn deserialize_bytes(value: plist::Value) -> Option<Vec<u8>> {
        let plist::Value::String(value) = value else { return None; };
        if value.len() > 16_384 { return None; }
        B64.decode(value).ok()
    }
}

#[cfg(test)]
mod bounded_host_frame_tests {
    use super::*;
    use super::super::RpPairingSocketProvider;
    use tokio::io::AsyncWriteExt;

    fn socket<R: crate::ReadWrite>(inner: R) -> BoundedHostSocket<R> {
        BoundedHostSocket { inner, received: 0, sent: 0, receive_messages: 0, send_messages: 0,
                            continuing: std::sync::Arc::new(|| true) }
    }

    #[tokio::test]
    async fn rejects_bad_magic_and_oversized_frame_before_body_read() {
        for header in [*b"WRONGMAGI\0\x01", *b"RPPairing\x40\x01"] {
            let (mut writer, reader) = tokio::io::duplex(32);
            writer.write_all(&header).await.unwrap();
            assert!(socket(reader).recv_plain().await.is_err());
        }
    }

    #[tokio::test]
    async fn reads_fragmented_valid_frame_and_enforces_message_count() {
        let (mut writer, reader) = tokio::io::duplex(256);
        let bytes = br#"{"message":{"plain":{"_0":{"ok":true}}}}"#;
        writer.write_all(b"RPPairing").await.unwrap();
        writer.write_all(&(bytes.len() as u16).to_be_bytes()).await.unwrap();
        for byte in bytes { writer.write_all(&[*byte]).await.unwrap(); }
        let mut reader = socket(reader);
        assert!(reader.recv_plain().await.unwrap().as_dictionary().unwrap()["ok"].as_boolean().unwrap());
        reader.receive_messages = 4;
        assert!(reader.recv_plain().await.is_err());
    }

    #[test]
    fn rejects_deep_or_many_node_json_before_plist_conversion() {
        let mut value = serde_json::json!(true);
        for _ in 0..18 { value = serde_json::json!([value]); }
        assert!(!host_json_bounded(&value, 0, &mut 0));
        let many = serde_json::Value::Array(vec![serde_json::Value::Bool(true); 600]);
        assert!(!host_json_bounded(&many, 0, &mut 0));
    }
}

#[cfg(test)]
mod bounded_controller_signature_tests {
    use super::*;
    use ed25519_dalek::SigningKey;

    const SESSION: [u8; 64] = [0x31; 64];
    const IDENTIFIER: &[u8] = b"synthetic-controller";

    fn identity(identifier: &[u8], session: &[u8]) -> Vec<tlv::TLV8Entry> {
        let signing = SigningKey::from_bytes(&[0x27; 32]);
        let public = signing.verifying_key().to_bytes();
        let mut prefix = [0; 32];
        Hkdf::<Sha512>::new(Some(b"Pair-Setup-Controller-Sign-Salt"), session)
            .expand(b"Pair-Setup-Controller-Sign-Info", &mut prefix).unwrap();
        let mut signed = prefix.to_vec();
        signed.extend_from_slice(identifier); signed.extend_from_slice(&public);
        let signature = ed25519_dalek::Signer::sign(&signing, &signed);
        vec![
            tlv::TLV8Entry { tlv_type: Tt::Identifier, data: identifier.to_vec() },
            tlv::TLV8Entry { tlv_type: Tt::PublicKey, data: public.to_vec() },
            tlv::TLV8Entry { tlv_type: Tt::Signature, data: signature.to_bytes().to_vec() },
        ]
    }
    fn with_info(account: Value) -> Vec<tlv::TLV8Entry> {
        let mut entries = identity(IDENTIFIER, &SESSION);
        let value = crate::plist!({ "accountID": account, "altIRK": vec![1u8; 16],
            "model": "synthetic-model", "name": "synthetic phone", "remotepairing_udid": "synthetic-id" });
        entries.push(tlv::TLV8Entry { tlv_type: Tt::Info, data: opack::plist_to_opack(&value) });
        entries
    }

    #[test]
    fn accepts_exact_controller_signature_and_identifier_boundary() {
        let entries = identity(IDENTIFIER, &SESSION);
        // Independently generated Python Ed25519/HKDF-SHA512 synthetic vector.
        // This assertion is authored; native execution remains required.
        let expected_signature = [
            0xcd, 0x12, 0x9d, 0x24, 0x2b, 0x15, 0x31, 0x81, 0x0e, 0x45, 0x11, 0x0c, 0x89, 0xb4, 0xfd, 0xc9,
            0x8d, 0xc3, 0x8f, 0x1d, 0x2f, 0x6e, 0x2e, 0x20, 0xc0, 0x99, 0x5b, 0x1b, 0x0a, 0x3b, 0x18, 0x49,
            0x3e, 0x06, 0x4c, 0xe5, 0x2d, 0xc8, 0x13, 0x4d, 0x93, 0x37, 0xbb, 0x5b, 0xb6, 0x92, 0x4d, 0xba,
            0x1a, 0x71, 0x84, 0xf1, 0x09, 0x0a, 0x9f, 0xe4, 0xb5, 0x71, 0xaa, 0xcf, 0xca, 0x7c, 0x65, 0x08
        ];
        assert!(entries[2].data.as_slice() == expected_signature);
        assert!(bounded_controller_identity(&entries, &SESSION).is_ok());
        let boundary = identity(&[b'a'; 128], &SESSION);
        assert!(bounded_controller_identity(&boundary, &SESSION).is_ok());
        assert!(bounded_authenticated_peer_device(&with_info(Value::String(
            "synthetic-controller".into())), &SESSION).is_ok());
    }

    #[test]
    fn requires_exact_key_signature_session_lengths_and_bounded_identifier() {
        for size in [0, 1, 31, 63, 65, 128] {
            assert!(bounded_controller_identity(&identity(IDENTIFIER, &SESSION), &vec![0; size]).is_err());
        }
        for (index, sizes) in [(1, &[0usize, 1, 31, 33, 255][..]), (2, &[0usize, 1, 63, 65, 255][..])] {
            for &size in sizes {
                let mut entries = identity(IDENTIFIER, &SESSION);
                entries[index].data.resize(size, 0);
                assert!(bounded_controller_identity(&entries, &SESSION).is_err());
            }
        }
        for identifier in [vec![], vec![b'a'; 129]] {
            assert!(bounded_controller_identity(&identity(&identifier, &SESSION), &SESSION).is_err());
        }
    }

    #[test]
    fn rejects_missing_wrong_type_duplicate_and_fragmented_identity_fields() {
        for index in 0..3 {
            let mut missing = identity(IDENTIFIER, &SESSION); missing.remove(index);
            assert!(bounded_controller_identity(&missing, &SESSION).is_err());
            let mut wrong_type = identity(IDENTIFIER, &SESSION); wrong_type[index].tlv_type = Tt::Proof;
            assert!(bounded_controller_identity(&wrong_type, &SESSION).is_err());
            let mut duplicate = identity(IDENTIFIER, &SESSION); duplicate.push(duplicate[index].clone());
            assert!(bounded_controller_identity(&duplicate, &SESSION).is_err());
            let mut split = identity(IDENTIFIER, &SESSION);
            let data = split[index].data.split_off(1);
            split.push(tlv::TLV8Entry { tlv_type: split[index].tlv_type, data });
            assert!(bounded_controller_identity(&split, &SESSION).is_err());
        }
    }

    #[test]
    fn rejects_non_utf8_or_control_identifiers_even_with_valid_signatures() {
        for identifier in [&[0xff][..], b"bad\nidentifier", b"bad\0identifier", b"bad\x7fidentifier"] {
            assert!(bounded_controller_identity(&identity(identifier, &SESSION), &SESSION).is_err());
        }
    }

    #[test]
    fn binds_signature_to_session_identifier_public_key_and_strict_verification() {
        let entries = identity(IDENTIFIER, &SESSION);
        assert!(bounded_controller_identity(&entries, &[0x32; 64]).is_err());
        for index in [0, 2] {
            let mut changed = entries.clone(); changed[index].data[0] ^= 1;
            assert!(bounded_controller_identity(&changed, &SESSION).is_err());
        }
        let mut wrong_key = entries.clone();
        wrong_key[1].data = SigningKey::from_bytes(&[0x28; 32]).verifying_key().to_bytes().to_vec();
        assert!(bounded_controller_identity(&wrong_key, &SESSION).is_err());
        // The canonical identity point is a weak public key. A matching weak R
        // and zero scalar must not be accepted even when all lengths are exact.
        let mut weak = entries;
        weak[1].data = vec![0; 32]; weak[1].data[0] = 1;
        weak[2].data = vec![0; 64]; weak[2].data[0] = 1;
        assert!(bounded_controller_identity(&weak, &SESSION).is_err());
    }

    #[test]
    fn accepted_peer_account_must_match_signed_identifier_and_have_string_type() {
        for account in [Value::String("different-controller".into()), Value::Data(IDENTIFIER.to_vec()),
                        Value::Integer(7.into())] {
            let entries = with_info(account);
            assert!(bounded_controller_identity(&entries, &SESSION).is_ok());
            assert!(bounded_authenticated_peer_device(&entries, &SESSION).is_err());
        }
        let mut entries = identity(IDENTIFIER, &SESSION);
        entries.push(tlv::TLV8Entry { tlv_type: Tt::Info,
            data: opack::plist_to_opack(&Value::String("not a dictionary".into())) });
        assert!(bounded_authenticated_peer_device(&entries, &SESSION).is_err());
    }
}
