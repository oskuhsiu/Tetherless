// Copyright (c) 2026 Tetherless contributors. MIT; retained idevice license.
//! Opt-in synthetic peer for the real staged acquisition composite.
//! No listener, account, device, persistence, C ABI, or alternate production route.
//! Existing locked crypto, OpenSSL TLS, XPC and jktcp packet encoders are used.
//! This deliberately bounded, ordered transcript is not a general TCP server.
use super::{tlv::{self, PairingDataComponentType as Tag, TLV8Entry},
    RemotePairingClient, RpPairingFile, RpPairingSocket, RpPairingSocketProvider};
use base64::{Engine as _, engine::general_purpose::STANDARD as B64};
use chacha20poly1305::{ChaCha20Poly1305, KeyInit, Nonce, aead::Aead};
use ed25519_dalek::{Signature, SigningKey};
use hkdf::Hkdf;
use openssl::ssl::{Ssl, SslContextBuilder, SslMethod, SslOptions, SslSessionCacheMode, SslVersion};
use plist_macro::plist;
use rsa::rand_core::OsRng;
use serde_json::{Value, json};
use sha2::Sha512;
use std::{io, net::{IpAddr, Ipv6Addr}, pin::Pin,
    sync::{Arc, Mutex, atomic::{AtomicBool, Ordering}}};
use tokio::{io::{AsyncReadExt, AsyncWriteExt}, sync::Notify};
use x25519_dalek::{EphemeralSecret, PublicKey};
use crate::{ReadWrite, tcp::packets::{Ipv6Packet, ProtocolNumber, TcpFlags, TcpPacket},
    xpc::XPCMessage};

pub const ENDPOINT_PORT: u16 = 49152;
pub const TUNNEL_PORT: u16 = 49153;
const RSD_PORT: u16 = 58783;
const AFC_PORT: u16 = 62000;
const HOST: Ipv6Addr = Ipv6Addr::new(0xfd00, 0, 0, 0, 0, 0, 0, 1);
const PEER: Ipv6Addr = Ipv6Addr::new(0xfd00, 0, 0, 0, 0, 0, 0, 2);
pub const BUNDLE: &[u8] = b"com.example.synthetic";
pub const CHALLENGE: [u8; 32] = [0xd7; 32];
const AFC_MAGIC: u64 = 0x4141504c36414643;
const MAX_PEER_EVENTS: usize = 1024;
const MAX_APPLICATION_BYTES: usize = 64 * 1024;

pub fn challenge_path() -> Vec<u8> {
    [b"Library/TetherlessPairingValidation/".as_slice(), &[b'a'; 64], b".challenge"].concat()
}
pub fn record() -> RpPairingFile {
    let key = SigningKey::from_bytes(&[0x32; 32]);
    RpPairingFile { e_public_key: key.verifying_key(), e_private_key: key,
        identifier: "synthetic-composite-only".into(), alt_irk: None, generated_by: None }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Stage { Greeting, PairVerify, Listener, Tls, CdTunnel, Rsd, Checkin,
    VendContainer, AfcOpen, AfcRead, AfcClose, ServiceFin, FinalDrain }
#[derive(Debug)]
pub struct Progress {
    stages: Mutex<Vec<Stage>>,
    changed: Notify,
    stop_at: Option<Stage>,
    pub close_reply_sent: AtomicBool,
}
impl Progress {
    pub fn new(stop_at: Option<Stage>) -> Arc<Self> {
        Arc::new(Self { stages: Mutex::new(Vec::new()), changed: Notify::new(), stop_at,
            close_reply_sent: AtomicBool::new(false) })
    }
    pub fn reached(&self, stage: Stage) -> bool { self.stages.lock().unwrap().contains(&stage) }
    pub fn stages(&self) -> Vec<Stage> { self.stages.lock().unwrap().clone() }
    pub fn mark(&self, stage: Stage) {
        let mut stages = self.stages.lock().unwrap();
        if !stages.contains(&stage) { stages.push(stage); self.changed.notify_waiters(); }
    }
    pub async fn wait_for(&self, stage: Stage) {
        loop {
            let change = self.changed.notified(); tokio::pin!(change); change.as_mut().enable();
            if self.reached(stage) { return; }
            change.await;
        }
    }
    async fn checkpoint(&self, stage: Stage) {
        self.mark(stage);
        if self.stop_at == Some(stage) { std::future::pending::<()>().await; }
    }
}

#[derive(Debug, Default)]
pub struct Evidence {
    pub host_signature_verified: bool,
    pub encrypted_listener_verified: bool,
    pub tls12_psk_negotiated: bool,
    pub rsd_handshake_verified: bool,
    pub checkin_verified: bool,
    pub vend_verified: bool,
    pub afc_operations: Vec<u64>,
    pub tcp_fins: usize,
    pub client_application_bytes: usize,
}
fn bad() -> io::Error { io::Error::other("synthetic transcript mismatch") }
fn require(ok: bool) -> io::Result<()> { if ok { Ok(()) } else { Err(bad()) } }
fn converted<T, E>(value: Result<T, E>) -> io::Result<T> { value.map_err(|_| bad()) }
fn field<'a>(value: &'a Value, path: &str) -> io::Result<&'a Value> { value.pointer(path).ok_or_else(bad) }
fn component(entries: &[TLV8Entry], tag: Tag) -> io::Result<Vec<u8>> {
    require(entries.iter().filter(|entry| entry.tlv_type == tag).count() == 1)?;
    Ok(tlv::collect_component_data(entries, tag))
}
fn pairing_data(value: &Value) -> io::Result<Vec<TLV8Entry>> {
    let item = field(value, "/message/plain/_0/event/_0/pairingData/_0")?;
    require(item.get("kind").and_then(Value::as_str) == Some("verifyManualPairing"))?;
    let bytes = converted(B64.decode(item.get("data").and_then(Value::as_str).ok_or_else(bad)?))?;
    converted(tlv::deserialize_tlv8(&bytes))
}
async fn read_rp<S: ReadWrite>(socket: &mut RpPairingSocket<S>, sequence: u64) -> io::Result<Value> {
    let mut header = [0; 11]; socket.inner.read_exact(&mut header).await?;
    require(&header[..9] == b"RPPairing")?;
    let length = u16::from_be_bytes([header[9], header[10]]) as usize;
    require(length > 0 && length <= 16 * 1024)?;
    let mut body = vec![0; length]; socket.inner.read_exact(&mut body).await?;
    let value: Value = converted(serde_json::from_slice(&body))?;
    require(value.get("originatedBy").and_then(Value::as_str) == Some("host")
        && value.get("sequenceNumber").and_then(Value::as_u64) == Some(sequence))?;
    Ok(value)
}
async fn send_pairing<S: ReadWrite>(socket: &mut RpPairingSocket<S>, entries: &[TLV8Entry], seq: usize) -> io::Result<()> {
    let value = plist!({"event":{"_0":{"pairingData":{"_0":{
        "data": B64.encode(tlv::serialize_tlv8(entries))
    }}}}});
    converted(socket.send_plain(value, seq).await)
}
async fn verify_rp<S: ReadWrite>(socket: &mut RpPairingSocket<S>, progress: &Progress,
    evidence: &mut Evidence) -> io::Result<[u8; 32]>
{
    let greeting = read_rp(socket, 0).await?;
    require(field(&greeting, "/message/plain/_0/request/_0/handshake/_0/hostOptions/attemptPairVerify")?.as_bool() == Some(true))?;
    require(field(&greeting, "/message/plain/_0/request/_0/handshake/_0/wireProtocolVersion")?.as_u64() == Some(19))?;
    progress.checkpoint(Stage::Greeting).await;
    converted(socket.send_plain(plist!({"response":{"_1":{"handshake":{"_0":{}}}}}), 0).await)?;

    let first = read_rp(socket, 1).await?;
    require(field(&first, "/message/plain/_0/event/_0/pairingData/_0/startNewSession")?.as_bool() == Some(true))?;
    let first = pairing_data(&first)?;
    require(component(&first, Tag::State)? == [1])?;
    let host_public: [u8; 32] = component(&first, Tag::PublicKey)?.try_into().map_err(|_| bad())?;
    let secret = EphemeralSecret::random_from_rng(OsRng);
    let public = PublicKey::from(&secret);
    let shared = secret.diffie_hellman(&PublicKey::from(host_public));
    require(shared.was_contributory())?;
    progress.checkpoint(Stage::PairVerify).await;
    send_pairing(socket, &[
        TLV8Entry { tlv_type: Tag::State, data: vec![2] },
        TLV8Entry { tlv_type: Tag::PublicKey, data: public.as_bytes().to_vec() },
    ], 1).await?;
    let third = read_rp(socket, 2).await?;
    require(field(&third, "/message/plain/_0/event/_0/pairingData/_0/startNewSession")?.as_bool() == Some(false))?;
    let third = pairing_data(&third)?;
    require(component(&third, Tag::State)? == [3])?;
    let mut key = [0; 32];
    converted(Hkdf::<Sha512>::new(Some(b"Pair-Verify-Encrypt-Salt"), shared.as_bytes())
        .expand(b"Pair-Verify-Encrypt-Info", &mut key))?;
    let cipher = ChaCha20Poly1305::new_from_slice(&key).map_err(|_| bad())?;
    let auth = converted(cipher.decrypt(Nonce::from_slice(b"\0\0\0\0PV-Msg03"),
        component(&third, Tag::EncryptedData)?.as_slice()))?;
    let auth = converted(tlv::deserialize_tlv8(&auth))?;
    let record = record();
    require(component(&auth, Tag::Identifier)? == record.identifier.as_bytes())?;
    let signbuf = [host_public.as_slice(), record.identifier.as_bytes(), public.as_bytes()].concat();
    let signature = converted(Signature::from_slice(&component(&auth, Tag::Signature)?))?;
    converted(record.e_public_key.verify_strict(&signbuf, &signature))?;
    evidence.host_signature_verified = true;
    send_pairing(socket, &[TLV8Entry { tlv_type: Tag::State, data: vec![4] }], 2).await?;

    let encrypted = read_rp(socket, 3).await?;
    let encrypted = converted(B64.decode(field(&encrypted, "/message/streamEncrypted/_0")?.as_str().ok_or_else(bad)?))?;
    let (client_cipher, server_cipher) = RemotePairingClient::<RpPairingSocket<S>>::derive_main_ciphers(shared.as_bytes());
    let plaintext = converted(client_cipher.decrypt(Nonce::from_slice(&[0; 12]), encrypted.as_slice()))?;
    let request: Value = converted(serde_json::from_slice(&plaintext))?;
    require(field(&request, "/request/_0/createListener/transportProtocolType")?.as_str() == Some("tcp"))?;
    let psk = converted(B64.decode(field(&request, "/request/_0/createListener/key")?.as_str().ok_or_else(bad)?))?;
    require(psk.as_slice() == shared.as_bytes())?;
    evidence.encrypted_listener_verified = true;
    progress.checkpoint(Stage::Listener).await;
    let reply = converted(serde_json::to_vec(&json!({"response":{"_1":{"createListener":{"port":TUNNEL_PORT}}}})))?;
    let reply = converted(server_cipher.encrypt(Nonce::from_slice(&[0; 12]), reply.as_slice()))?;
    converted(socket.send_encrypted(reply, 3).await)?;
    Ok(*shared.as_bytes())
}

async fn tls_server<S: ReadWrite>(stream: S, key: [u8; 32]) -> io::Result<tokio_openssl::SslStream<S>> {
    // Same standard OpenSSL server contract as the separately reviewed TLS fixture.
    let mut context = converted(SslContextBuilder::new(SslMethod::tls_server()))?;
    converted(context.set_min_proto_version(Some(SslVersion::TLS1_2)))?;
    converted(context.set_max_proto_version(Some(SslVersion::TLS1_2)))?;
    converted(context.set_cipher_list("PSK-AES256-CBC-SHA384"))?;
    context.set_options(SslOptions::NO_COMPRESSION | SslOptions::NO_RENEGOTIATION | SslOptions::NO_TICKET);
    context.set_session_cache_mode(SslSessionCacheMode::OFF);
    context.set_psk_server_callback(move |_ssl, identity, output| {
        if identity != Some(b"".as_slice()) || output.len() < key.len() { return Ok(0); }
        output[..key.len()].copy_from_slice(&key); Ok(key.len())
    });
    let ssl = converted(Ssl::new(&context.build()))?;
    let mut stream = converted(tokio_openssl::SslStream::new(ssl, stream))?;
    converted(Pin::new(&mut stream).accept().await)?;
    require(stream.ssl().version_str() == "TLSv1.2")?;
    require(stream.ssl().current_cipher().map(|cipher| cipher.name()) == Some("PSK-AES256-CBC-SHA384"))?;
    Ok(stream)
}
async fn cdtunnel<S: ReadWrite>(stream: &mut S, progress: &Progress) -> io::Result<()> {
    let mut header = [0; 10]; stream.read_exact(&mut header).await?;
    require(&header[..8] == b"CDTunnel")?;
    let length = u16::from_be_bytes([header[8], header[9]]) as usize;
    require(length > 0 && length < 4096)?;
    let mut body = vec![0; length]; stream.read_exact(&mut body).await?;
    let request: Value = converted(serde_json::from_slice(&body))?;
    require(request.get("type").and_then(Value::as_str) == Some("clientHandshakeRequest"))?;
    require(request.get("mtu").and_then(Value::as_u64) == Some(16000))?;
    progress.checkpoint(Stage::CdTunnel).await;
    let body = converted(serde_json::to_vec(&json!({"clientParameters":{"address":"fd00::1","mtu":1280},
        "serverAddress":"fd00::2","serverRSDPort":RSD_PORT})))?;
    stream.write_all(&[b"CDTunnel".as_slice(), &(body.len() as u16).to_be_bytes(), &body].concat()).await?;
    stream.flush().await
}

struct TcpPeer<S> {
    wire: S, host_port: u16, port: u16, seq: u32, ack: u32, acked: u32,
    input: Vec<u8>, events: usize, client_bytes: usize,
}
impl<S: ReadWrite> TcpPeer<S> {
    fn new(wire: S) -> Self { Self { wire, host_port: 0, port: 0, seq: 0, ack: 0, acked: 0,
        input: Vec::new(), events: 0, client_bytes: 0 } }
    async fn packet(&mut self) -> io::Result<TcpPacket> {
        self.events += 1; require(self.events <= MAX_PEER_EVENTS)?;
        let mut header = [0; 40]; self.wire.read_exact(&mut header).await?;
        let length = u16::from_be_bytes([header[4], header[5]]) as usize;
        require(header[0] >> 4 == 6 && header[6] == 6 && (20..=1240).contains(&length))?;
        let mut bytes = header.to_vec(); bytes.resize(40 + length, 0);
        self.wire.read_exact(&mut bytes[40..]).await?;
        // Its slice parser is crate-private; the public reader is used only
        // after this fixture has bounded and acquired the complete packet.
        let mut encoded = bytes.as_slice();
        let ip = Ipv6Packet::from_reader(&mut encoded, &None).await?;
        require(encoded.is_empty())?;
        require(ip.source == HOST && ip.destination == PEER)?;
        let tcp = TcpPacket::parse(&ip.payload)?;
        require(!tcp.flags.rst && !tcp.flags.urg && tcp.data_offset >= 20)?;
        Ok(tcp)
    }
    async fn send(&mut self, flags: TcpFlags, payload: &[u8]) -> io::Result<()> {
        require(payload.len() <= 1220)?;
        let tcp = TcpPacket::create(IpAddr::V6(PEER), IpAddr::V6(HOST), self.port, self.host_port,
            self.seq, self.ack, flags, 65534, &[], payload);
        let packet = Ipv6Packet::create(PEER, HOST, ProtocolNumber::Tcp, 64, &tcp);
        self.wire.write_all(&packet).await?; self.wire.flush().await?;
        self.seq = self.seq.wrapping_add(payload.len() as u32 + u32::from(flags.syn) + u32::from(flags.fin));
        Ok(())
    }
    async fn accept(&mut self, port: u16) -> io::Result<()> {
        require(self.input.is_empty())?;
        let syn = self.packet().await?;
        require(syn.destination_port == port && syn.flags.syn && !syn.flags.ack && syn.payload.is_empty())?;
        self.port = port; self.host_port = syn.source_port;
        self.seq = 70000 + u32::from(port); self.ack = syn.sequence_number.wrapping_add(1);
        self.acked = self.seq;
        self.send(TcpFlags { syn: true, ack: true, ..Default::default() }, &[]).await?;
        let ack = self.packet().await?;
        self.verify_connection(&ack)?;
        require(ack.flags.ack && !ack.flags.syn && ack.payload.is_empty()
            && ack.sequence_number == self.ack && ack.acknowledgment_number == self.seq)?;
        self.acked = self.seq; Ok(())
    }
    fn verify_connection(&self, packet: &TcpPacket) -> io::Result<()> {
        require(packet.destination_port == self.port && packet.source_port == self.host_port)
    }
    async fn receive(&mut self) -> io::Result<()> {
        let packet = self.packet().await?; self.verify_connection(&packet)?;
        require(!packet.flags.fin && !packet.flags.syn && packet.flags.ack)?;
        // Deterministic ordered synthetic peer: unexpected duplication, gaps or
        // optimistic acknowledgements fail the fixture rather than being hidden.
        require(packet.sequence_number == self.ack
            && (self.acked..=self.seq).contains(&packet.acknowledgment_number))?;
        self.acked = packet.acknowledgment_number;
        if !packet.payload.is_empty() {
            self.client_bytes += packet.payload.len();
            require(self.client_bytes <= MAX_APPLICATION_BYTES)?;
            self.ack = self.ack.wrapping_add(packet.payload.len() as u32);
            self.input.extend_from_slice(&packet.payload);
            self.send(TcpFlags { ack: true, ..Default::default() }, &[]).await?;
        }
        Ok(())
    }
    async fn read(&mut self, count: usize) -> io::Result<Vec<u8>> {
        require(count <= 16 * 1024)?;
        while self.input.len() < count { self.receive().await?; }
        Ok(self.input.drain(..count).collect())
    }
    async fn write(&mut self, bytes: &[u8]) -> io::Result<()> {
        for piece in bytes.chunks(89) { // Cross protocol headers and TCP payload boundaries.
            self.send(TcpFlags { ack: true, psh: true, ..Default::default() }, piece).await?;
            // Await each ACK so even a tiny encrypted transport buffer cannot
            // deadlock on simultaneous peer writes. No background TCP pump.
            // HTTP/2 control replies may arrive while the peer is writing DATA.
            // Preserve their ordered application bytes and ACK them normally.
            while self.acked != self.seq { self.receive().await?; }
        }
        Ok(())
    }
    async fn finish(&mut self) -> io::Result<()> {
        require(self.input.is_empty())?;
        loop {
            let packet = self.packet().await?; self.verify_connection(&packet)?;
            require(packet.flags.ack && !packet.flags.syn && packet.payload.is_empty()
                && packet.sequence_number == self.ack && packet.acknowledgment_number == self.seq)?;
            if packet.flags.fin {
                // Actual FIN observed through OpenSSL, including the final drain.
                // Production close does not wait for FIN acknowledgement.
                self.ack = self.ack.wrapping_add(1); return Ok(());
            }
        }
    }
}

// RFC7540 nine-byte frame envelope, matching pinned xpc/http2/frame.rs. XPC
// payloads themselves are encoded and decoded by the actual library.
fn h2_frame(kind: u8, flags: u8, channel: u32, body: &[u8]) -> Vec<u8> {
    let mut bytes = (body.len() as u32).to_be_bytes()[1..].to_vec();
    bytes.extend([kind, flags]); bytes.extend(channel.to_be_bytes()); bytes.extend(body); bytes
}
async fn rsd<S: ReadWrite>(peer: &mut TcpPeer<S>, progress: &Progress, evidence: &mut Evidence) -> io::Result<()> {
    peer.accept(RSD_PORT).await?;
    require(peer.read(24).await?.as_slice() == b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n")?;
    let mut settings = false; let mut root = false; let mut reply = false;
    let mut handshake = false; let mut xpc_root = Vec::new();
    for _ in 0..32 {
        let header = peer.read(9).await?;
        let length = u32::from_be_bytes([0, header[0], header[1], header[2]]) as usize;
        require(length <= 16384)?;
        let channel = u32::from_be_bytes(header[5..9].try_into().unwrap());
        let body = peer.read(length).await?;
        match (header[3], channel) {
            (4, 0) => { require(header[4] == 0 && body.len() == 12)?; settings = true; }
            (8, 0) => require(body == 983041u32.to_be_bytes())?,
            (1, 1) => root = true,
            (1, 3) => reply = true,
            (0, 1) => {
                xpc_root.extend(body); require(xpc_root.len() <= 16384)?;
                while xpc_root.len() >= 24 {
                    let body_len = u64::from_le_bytes(xpc_root[8..16].try_into().unwrap()) as usize;
                    require(body_len <= 16360)?;
                    if xpc_root.len() < body_len + 24 { break; }
                    let bytes: Vec<_> = xpc_root.drain(..body_len + 24).collect();
                    let message = converted(XPCMessage::decode(&bytes))?;
                    if let Some(object) = message.message {
                        let value = object.to_plist();
                        if value.as_dictionary().and_then(|d| d.get("MessageType")).and_then(plist::Value::as_string) == Some("Handshake") {
                            let d = value.as_dictionary().ok_or_else(bad)?;
                            require(d.get("MessagingProtocolVersion").and_then(plist::Value::as_unsigned_integer) == Some(7))?;
                            require(d.get("Services").and_then(plist::Value::as_dictionary).is_some_and(|d| d.is_empty()))?;
                            handshake = true;
                        }
                    }
                }
            }
            (0, 3) => { let message = converted(XPCMessage::decode(&body))?;
                require(message.flags == 0x00400001 && message.message.is_none())?; }
            _ => return Err(bad()),
        }
        if handshake { break; }
    }
    require(settings && root && reply && handshake && xpc_root.is_empty())?;
    evidence.rsd_handshake_verified = true;
    progress.checkpoint(Stage::Rsd).await;
    // RFC7540 server preface: its own SETTINGS, then ACK the client settings.
    peer.write(&h2_frame(4, 0, 0, &[])).await?;
    peer.write(&h2_frame(4, 1, 0, &[])).await?;
    let object = crate::xpc!({"MessagingProtocolVersion":7u64,
        "UUID":"00000000-0000-0000-0000-000000000001", "Properties":{},
        "Services":{"com.apple.mobile.house_arrest.shim.remote":{
            "Entitlement":"", "Port": AFC_PORT.to_string(), "Properties":{"UsesRemoteXPC":false}
        }}});
    let body = converted(XPCMessage { flags: 0x101, message: Some(object), message_id: Some(1) }.encode(1))?;
    // Reassembly must cross separate HTTP/2 frames, not only TCP reads.
    let split = 31.min(body.len());
    peer.write(&h2_frame(0, 0, 1, &body[..split])).await?;
    peer.write(&h2_frame(0, 0, 1, &body[split..])).await?;
    require(peer.read(9).await? == h2_frame(4, 1, 0, &[]))?;
    // The real bounded client replenishes connection and stream windows for
    // each received DATA frame; validate both rather than silently discard them.
    for length in [split, body.len() - split] {
        for channel in [0, 1] {
            require(peer.read(13).await? == h2_frame(8, 0, channel, &(length as u32).to_be_bytes()))?;
        }
    }
    peer.finish().await?; evidence.tcp_fins += 1;
    Ok(())
}
async fn read_plist<S: ReadWrite>(peer: &mut TcpPeer<S>) -> io::Result<plist::Value> {
    let length = u32::from_be_bytes(peer.read(4).await?.try_into().unwrap()) as usize;
    require(length > 0 && length <= 4096)?;
    converted(plist::Value::from_reader(std::io::Cursor::new(peer.read(length).await?)))
}
async fn write_plist<S: ReadWrite>(peer: &mut TcpPeer<S>, value: plist::Value) -> io::Result<()> {
    let mut bytes = Vec::new(); converted(value.to_writer_binary(&mut bytes))?;
    peer.write(&[&(bytes.len() as u32).to_be_bytes()[..], &bytes].concat()).await
}
fn plist_equals(value: &plist::Value, key: &str, expected: &str) -> bool {
    value.as_dictionary().and_then(|d| d.get(key)).and_then(plist::Value::as_string) == Some(expected)
}
async fn afc_request<S: ReadWrite>(peer: &mut TcpPeer<S>, number: u64, operation: u64) -> io::Result<Vec<u8>> {
    let header = peer.read(40).await?;
    let field = |offset| u64::from_le_bytes(header[offset..offset+8].try_into().unwrap());
    let length = field(8);
    require(field(0) == AFC_MAGIC && (40..=512).contains(&length) && field(16) == length
        && field(24) == number && field(32) == operation)?;
    peer.read(length as usize - 40).await
}
async fn afc_response<S: ReadWrite>(peer: &mut TcpPeer<S>, number: u64, operation: u64, head: usize, body: &[u8]) -> io::Result<()> {
    let mut bytes = Vec::new();
    for field in [AFC_MAGIC, (40 + body.len()) as u64, (40 + head) as u64, number, operation] {
        bytes.extend(field.to_le_bytes());
    }
    bytes.extend(body); peer.write(&bytes).await
}
async fn house_arrest<S: ReadWrite>(peer: &mut TcpPeer<S>, progress: &Progress, evidence: &mut Evidence) -> io::Result<()> {
    peer.accept(AFC_PORT).await?;
    let checkin = read_plist(peer).await?;
    require(plist_equals(&checkin, "Request", "RSDCheckin"))?;
    evidence.checkin_verified = true; progress.checkpoint(Stage::Checkin).await;
    for request in ["RSDCheckin", "StartService"] {
        write_plist(peer, plist!({"Request":request, "EnableServiceSSL":false, "ProtocolVersion":2})).await?;
    }
    let vend = read_plist(peer).await?;
    require(plist_equals(&vend, "Command", "VendContainer")
        && plist_equals(&vend, "Identifier", std::str::from_utf8(BUNDLE).unwrap()))?;
    evidence.vend_verified = true; progress.checkpoint(Stage::VendContainer).await;
    write_plist(peer, plist!({"Status":"Complete"})).await?;
    let open = afc_request(peer, 0, 0x0d).await?; evidence.afc_operations.push(0x0d);
    require(open == [&1u64.to_le_bytes()[..], &challenge_path(), &[0]].concat())?;
    progress.checkpoint(Stage::AfcOpen).await;
    afc_response(peer, 0, 0x0e, 8, &17u64.to_le_bytes()).await?;
    let read = afc_request(peer, 1, 0x0f).await?; evidence.afc_operations.push(0x0f);
    require(read == [17u64.to_le_bytes(), 33u64.to_le_bytes()].concat())?;
    progress.checkpoint(Stage::AfcRead).await;
    afc_response(peer, 1, 2, 0, &CHALLENGE).await?;
    let eof = afc_request(peer, 2, 0x0f).await?; evidence.afc_operations.push(0x0f);
    require(eof == [17u64.to_le_bytes(), 1u64.to_le_bytes()].concat())?;
    afc_response(peer, 2, 1, 8, &14u64.to_le_bytes()).await?;
    let close = afc_request(peer, 3, 0x14).await?; evidence.afc_operations.push(0x14);
    require(close == 17u64.to_le_bytes())?; progress.checkpoint(Stage::AfcClose).await;
    progress.close_reply_sent.store(true, Ordering::SeqCst);
    afc_response(peer, 3, 1, 8, &0u64.to_le_bytes()).await?;
    peer.finish().await?; evidence.tcp_fins += 1;
    progress.mark(Stage::ServiceFin);
    Ok(())
}

/// Every transport is borrowed or owned by this one future; dropping it joins
/// the peer synchronously. The caller must bound the entire concurrent fixture.
pub async fn run<S: ReadWrite>(rp: S, tunnel: S, progress: Arc<Progress>) -> io::Result<Evidence> {
    let mut evidence = Evidence::default();
    let mut rp = RpPairingSocket::new_device(rp);
    let key = verify_rp(&mut rp, &progress, &mut evidence).await?;
    progress.checkpoint(Stage::Tls).await;
    let mut tls = tls_server(tunnel, key).await?;
    evidence.tls12_psk_negotiated = true;
    cdtunnel(&mut tls, &progress).await?;
    let mut peer = TcpPeer::new(tls);
    rsd(&mut peer, &progress, &mut evidence).await?;
    house_arrest(&mut peer, &progress, &mut evidence).await?;
    evidence.client_application_bytes = peer.client_bytes;
    drop(peer); drop(rp);
    Ok(evidence)
}
