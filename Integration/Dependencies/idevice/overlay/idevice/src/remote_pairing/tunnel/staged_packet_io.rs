// Copyright (c) 2026 Tetherless contributors. MIT; retained idevice license.
//! Single-task packet-write ownership for borrowed jktcp over a vetted TLS stream.
//! No TLS records or cryptography are implemented here.
use std::{
    io,
    pin::Pin,
    sync::{Arc, Mutex, MutexGuard},
    task::{Context, Poll},
};
use tokio::io::{AsyncRead, AsyncWrite, ReadBuf};

const MAX_PACKET: usize = 16000;
struct State<S> {
    inner: S,
    // Fixed capacity and stable address even if the outer owner moves.
    bytes: Box<[u8; MAX_PACKET]>,
    offset: usize,
    length: usize,
    failure: Option<io::ErrorKind>,
}

/// Box this side into one inline Adapter. Do not poll either side concurrently.
/// Both owners must be dropped before publishing cancellation/completion.
pub struct PacketWriteIo<S>(Arc<Mutex<State<S>>>);
/// Locally retain this owner; flush it after dropping streams/adapter and before
/// publishing success. It is deliberately not Clone and never crosses the FFI.
pub struct PacketDrain<S>(Arc<Mutex<State<S>>>);

impl<S> std::fmt::Debug for PacketWriteIo<S> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str("PacketWriteIo") }
}
impl<S> std::fmt::Debug for PacketDrain<S> {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str("PacketDrain") }
}
fn fixed_error(kind: io::ErrorKind) -> io::Error { io::Error::new(kind, "staged packet transport failed") }
fn lock<S>(owner: &Arc<Mutex<State<S>>>) -> io::Result<MutexGuard<'_, State<S>>> {
    owner.lock().map_err(|_| fixed_error(io::ErrorKind::Other))
}
impl<S> PacketWriteIo<S> {
    pub fn new(inner: S) -> (Self, PacketDrain<S>) {
        let state = Arc::new(Mutex::new(State {
            inner, bytes: Box::new([0; MAX_PACKET]), offset: 0, length: 0, failure: None,
        }));
        (Self(Arc::clone(&state)), PacketDrain(state))
    }
}
impl<S: AsyncWrite + Unpin> State<S> {
    fn fail(&mut self, kind: io::ErrorKind) -> Poll<io::Result<()>> {
        self.failure = Some(kind); Poll::Ready(Err(fixed_error(kind)))
    }
    fn poll_drain(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        if let Some(kind) = self.failure { return Poll::Ready(Err(fixed_error(kind))); }
        while self.offset < self.length {
            let remaining = self.length - self.offset;
            // On Pending, these exact owned bytes/address/length remain intact.
            // Offset advances only when the inner stream accepts actual bytes.
            match Pin::new(&mut self.inner).poll_write(cx, &self.bytes[self.offset..self.length]) {
                Poll::Pending => return Poll::Pending,
                Poll::Ready(Ok(0)) => return self.fail(io::ErrorKind::WriteZero),
                Poll::Ready(Ok(count)) if count <= remaining => self.offset += count,
                Poll::Ready(Ok(_)) => return self.fail(io::ErrorKind::InvalidData),
                Poll::Ready(Err(error)) => return self.fail(error.kind()),
            }
        }
        self.offset = 0; self.length = 0;
        Poll::Ready(Ok(()))
    }
    fn poll_flush(&mut self, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        match self.poll_drain(cx) {
            Poll::Ready(Ok(())) => match Pin::new(&mut self.inner).poll_flush(cx) {
                Poll::Ready(Err(error)) => self.fail(error.kind()),
                result => result,
            },
            result => result,
        }
    }
}
impl<S: AsyncWrite + Unpin> PacketDrain<S> {
    /// The mutex is held only during a synchronous poll, never across an await.
    pub async fn flush(&mut self) -> io::Result<()> {
        std::future::poll_fn(|cx| match lock(&self.0) {
            Ok(mut state) => state.poll_flush(cx),
            Err(error) => Poll::Ready(Err(error)),
        }).await
    }
}
impl<S: AsyncRead + AsyncWrite + Unpin> AsyncRead for PacketWriteIo<S> {
    fn poll_read(self: Pin<&mut Self>, cx: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
        let mut state = match lock(&self.0) { Ok(state) => state, Err(error) => return Poll::Ready(Err(error)) };
        match state.poll_drain(cx) {
            Poll::Ready(Ok(())) => match Pin::new(&mut state.inner).poll_read(cx, output) {
                Poll::Ready(Err(error)) => state.fail(error.kind()),
                result => result,
            },
            result => result,
        }
    }
}
impl<S: AsyncWrite + Unpin> AsyncWrite for PacketWriteIo<S> {
    fn poll_write(self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<io::Result<usize>> {
        let mut state = match lock(&self.0) { Ok(state) => state, Err(error) => return Poll::Ready(Err(error)) };
        if let Some(kind) = state.failure { return Poll::Ready(Err(fixed_error(kind))); }
        if bytes.is_empty() { return Poll::Ready(Ok(0)); }
        if bytes.len() > MAX_PACKET {
            state.failure = Some(io::ErrorKind::InvalidInput);
            return Poll::Ready(Err(fixed_error(io::ErrorKind::InvalidInput)));
        }
        match state.poll_drain(cx) {
            Poll::Pending => return Poll::Pending, // No new caller bytes accepted.
            Poll::Ready(Err(error)) => return Poll::Ready(Err(error)),
            Poll::Ready(Ok(())) => {}
        }
        state.bytes[..bytes.len()].copy_from_slice(bytes);
        state.offset = 0; state.length = bytes.len();
        // No inner I/O after acceptance: returning Pending here would let jktcp
        // submit the same logical packet again when its temporary future drops.
        Poll::Ready(Ok(bytes.len()))
    }
    fn poll_flush(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        match lock(&self.0) { Ok(mut state) => state.poll_flush(cx), Err(error) => Poll::Ready(Err(error)) }
    }
    fn poll_shutdown(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<io::Result<()>> {
        let mut state = match lock(&self.0) { Ok(state) => state, Err(error) => return Poll::Ready(Err(error)) };
        match state.poll_drain(cx) {
            Poll::Ready(Ok(())) => match Pin::new(&mut state.inner).poll_shutdown(cx) {
                Poll::Ready(Err(error)) => state.fail(error.kind()),
                result => result,
            },
            result => result,
        }
    }
}

#[cfg(all(test, feature = "tunnel_tcp_stack"))]
mod borrowed_adapter_tests {
    use super::*;
    use crate::tcp::{adapter::Adapter, stream::AdapterStream,
        packets::{Ipv6Packet, ProtocolNumber, TcpFlags, TcpPacket}};
    use std::{collections::VecDeque, net::{IpAddr, Ipv6Addr}, time::Duration};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    const HOST: Ipv6Addr = Ipv6Addr::new(0xfd00, 0, 0, 0, 0, 0, 0, 1);
    const PEER: Ipv6Addr = Ipv6Addr::new(0xfd00, 0, 0, 0, 0, 0, 0, 2);
    const PORT: u16 = 62000;
    const PEER_SEQ: u32 = 5001;
    #[derive(Default)]
    struct Probe {
        incoming: VecDeque<u8>,
        written: Vec<Vec<u8>>,
        pending_next: bool,
        forever: bool,
        pending: Option<(usize, Vec<u8>)>,
        pending_count: usize,
        drops: usize,
    }
    struct RetryProbe(Arc<Mutex<Probe>>);
    impl Drop for RetryProbe { fn drop(&mut self) { self.0.lock().unwrap().drops += 1; } }
    // This fixture deliberately enforces OpenSSL's documented retry identity
    // rule. It is not a TLS implementation or proof of linked OpenSSL behavior.
    impl AsyncWrite for RetryProbe {
        fn poll_write(self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<io::Result<usize>> {
            let mut probe = self.0.lock().unwrap();
            if let Some((pointer, previous)) = &probe.pending {
                assert_eq!(*pointer, bytes.as_ptr() as usize, "owned packet address changed after Pending");
                assert_eq!(previous.as_slice(), bytes, "pending write bytes/length changed");
                if probe.forever { return Poll::Pending; }
                probe.pending = None;
            } else if probe.pending_next {
                probe.pending_next = false;
                probe.pending = Some((bytes.as_ptr() as usize, bytes.to_vec()));
                probe.pending_count += 1;
                cx.waker().wake_by_ref();
                return Poll::Pending;
            }
            // Adapter only writes complete <=16000-byte IPv6 packets here.
            assert!(bytes.len() >= 60 && bytes.len() <= MAX_PACKET);
            let tcp = TcpPacket::parse(&bytes[40..]).unwrap();
            if tcp.flags.syn && !tcp.flags.ack {
                let syn_ack = peer_packet(tcp.source_port, PEER_SEQ - 1,
                    tcp.sequence_number.wrapping_add(1), TcpFlags { syn: true, ack: true, ..Default::default() }, &[]);
                probe.incoming.extend(syn_ack);
            }
            probe.written.push(bytes.to_vec());
            Poll::Ready(Ok(bytes.len()))
        }
        fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> { Poll::Ready(Ok(())) }
        fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> { Poll::Ready(Ok(())) }
    }
    impl AsyncRead for RetryProbe {
        fn poll_read(self: Pin<&mut Self>, _: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
            let mut probe = self.0.lock().unwrap();
            assert!(probe.pending.is_none(), "read bypassed an outstanding write");
            if probe.incoming.is_empty() { return Poll::Pending; }
            while output.remaining() > 0 {
                let Some(byte) = probe.incoming.pop_front() else { break; };
                output.put_slice(&[byte]);
            }
            Poll::Ready(Ok(()))
        }
    }
    fn peer_packet(host_port: u16, sequence: u32, ack: u32, flags: TcpFlags, payload: &[u8]) -> Vec<u8> {
        let tcp = TcpPacket::create(IpAddr::V6(PEER), IpAddr::V6(HOST), PORT, host_port,
            sequence, ack, flags, 65534, &[], payload);
        Ipv6Packet::create(PEER, HOST, ProtocolNumber::Tcp, 64, &tcp)
    }
    fn adapter() -> (Adapter, PacketDrain<RetryProbe>, Arc<Mutex<Probe>>) {
        let probe = Arc::new(Mutex::new(Probe::default()));
        let (io, drain) = PacketWriteIo::new(RetryProbe(Arc::clone(&probe)));
        let mut adapter = Adapter::new(Box::new(io), IpAddr::V6(HOST), IpAddr::V6(PEER));
        adapter.set_mss(1540).set_send_window(64 * 1024);
        (adapter, drain, probe)
    }
    fn packets(probe: &Arc<Mutex<Probe>>) -> Vec<TcpPacket> {
        probe.lock().unwrap().written.iter().map(|raw| TcpPacket::parse(&raw[40..]).unwrap()).collect()
    }

    #[tokio::test]
    async fn receive_ack_pending_cached_read_then_different_packet_keeps_owned_write() {
        tokio::time::timeout(Duration::from_secs(5), async {
            let (mut adapter, mut drain, probe) = adapter();
            let mut stream = AdapterStream::connect(&mut adapter, PORT).await.unwrap();
            // Complete the SYN-ACK's accepted local ACK so subsequent logs are distinct.
            drain.flush().await.unwrap();
            let host_seq = packets(&probe).last().unwrap().sequence_number;
            let first = peer_packet(stream.host_port, PEER_SEQ, host_seq,
                TcpFlags { ack: true, psh: true, ..Default::default() }, b"A");
            let second = peer_packet(stream.host_port, PEER_SEQ + 1, host_seq,
                TcpFlags { ack: true, psh: true, ..Default::default() }, b"B");
            // Both IP packets enter jktcp's existing fixed read buffer at once.
            probe.lock().unwrap().incoming.extend(first.into_iter().chain(second));
            let mut byte = [0];
            stream.read_exact(&mut byte).await.unwrap(); assert_eq!(byte, *b"A");
            // ACK A is copied but not yet drained. Processing buffered packet B
            // tries to drain A, sees Pending, then jktcp returns B from its cache.
            probe.lock().unwrap().pending_next = true;
            stream.read_exact(&mut byte).await.unwrap(); assert_eq!(byte, *b"B");
            assert!(probe.lock().unwrap().pending.is_some());
            stream.write_all(b"different-C").await.unwrap();
            stream.flush().await.unwrap();
            // The later packet must not replace the retained pending ACK A.
            assert!(probe.lock().unwrap().pending.is_none());
            stream.close().await.unwrap();
            drop(stream); drop(adapter);
            assert!(!packets(&probe).last().unwrap().flags.fin, "FIN should still be retained locally");
            drain.flush().await.unwrap();
            let output = packets(&probe);
            assert_eq!(output.iter().filter(|p| p.acknowledgment_number == PEER_SEQ + 1 && p.payload.is_empty()).count(), 1);
            assert_eq!(output.iter().filter(|p| p.payload == b"different-C").count(), 1);
            assert_eq!(output.iter().filter(|p| p.flags.fin).count(), 1);
            assert!(output.last().unwrap().flags.fin);
            assert_eq!(probe.lock().unwrap().pending_count, 1);
            drop(drain);
            assert_eq!(probe.lock().unwrap().drops, 1);
        }).await.expect("borrowed ACK fixture deadline");
    }

    #[tokio::test]
    async fn pending_retransmission_then_different_packet_and_final_fin_are_exact_once() {
        tokio::time::timeout(Duration::from_secs(5), async {
            let (mut adapter, mut drain, probe) = adapter();
            let mut stream = AdapterStream::connect(&mut adapter, PORT).await.unwrap();
            stream.write_all(b"original-M").await.unwrap(); stream.flush().await.unwrap();
            drain.flush().await.unwrap();
            // The peer intentionally does not ACK M. Use the real adapter RTO.
            tokio::time::sleep(Duration::from_millis(210)).await;
            stream.flush().await.unwrap(); // Retransmit M is accepted into the shim.
            probe.lock().unwrap().pending_next = true;
            stream.write_all(b"following-N").await.unwrap();
            stream.flush().await.unwrap(); // Pending while draining retransmit M.
            stream.close().await.unwrap();
            drop(stream); drop(adapter);
            drain.flush().await.unwrap();
            let output = packets(&probe);
            let repeated: Vec<_> = output.iter().filter(|p| p.payload == b"original-M").collect();
            assert_eq!(repeated.len(), 2, "one original and one intended TCP retransmission");
            assert_eq!(repeated[0].sequence_number, repeated[1].sequence_number);
            assert_eq!(output.iter().filter(|p| p.payload == b"following-N").count(), 1);
            assert_eq!(output.iter().filter(|p| p.flags.fin).count(), 1);
            assert_eq!(probe.lock().unwrap().pending_count, 1);
            drop(drain); assert_eq!(probe.lock().unwrap().drops, 1);
        }).await.expect("borrowed retransmission fixture deadline");
    }

    #[tokio::test]
    async fn timeout_drops_both_local_owners_with_a_pending_final_drain() {
        let (mut adapter, mut drain, probe) = adapter();
        let during = Arc::clone(&probe);
        let result = tokio::time::timeout(Duration::from_millis(20), async move {
            let mut stream = AdapterStream::connect(&mut adapter, PORT).await.unwrap();
            stream.close().await.unwrap();
            drop(stream); drop(adapter);
            // The connection is established and FIN is accepted locally. Stall
            // its final drain; the remaining owner must die before timeout returns.
            { let mut state = during.lock().unwrap(); state.pending_next = true; state.forever = true; }
            drain.flush().await.unwrap();
            drop(drain);
        });
        assert!(result.await.is_err());
        assert_eq!(probe.lock().unwrap().drops, 1);
    }
}

#[cfg(test)]
mod owner_tests {
    use super::*;
    use std::collections::VecDeque;
    use tokio::io::{AsyncReadExt, AsyncWriteExt};
    enum Step { Count(usize), Pending }
    #[derive(Default)]
    struct Log { calls: usize, bytes: Vec<u8>, pending: Option<(usize, Vec<u8>)>, reads: usize, shutdowns: usize }
    struct Script { steps: VecDeque<Step>, log: Arc<Mutex<Log>> }
    impl AsyncWrite for Script {
        fn poll_write(mut self: Pin<&mut Self>, cx: &mut Context<'_>, bytes: &[u8]) -> Poll<io::Result<usize>> {
            {
                let mut log = self.log.lock().unwrap(); log.calls += 1;
                if let Some((pointer, value)) = log.pending.take() {
                    assert_eq!(pointer, bytes.as_ptr() as usize); assert_eq!(value, bytes);
                }
            }
            match self.steps.pop_front().unwrap_or(Step::Count(bytes.len())) {
                Step::Pending => {
                    self.log.lock().unwrap().pending = Some((bytes.as_ptr() as usize, bytes.to_vec()));
                    cx.waker().wake_by_ref(); Poll::Pending
                }
                Step::Count(count) => {
                    if count <= bytes.len() { self.log.lock().unwrap().bytes.extend_from_slice(&bytes[..count]); }
                    Poll::Ready(Ok(count))
                }
            }
        }
        fn poll_flush(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> { Poll::Ready(Ok(())) }
        fn poll_shutdown(self: Pin<&mut Self>, _: &mut Context<'_>) -> Poll<io::Result<()>> {
            self.log.lock().unwrap().shutdowns += 1; Poll::Ready(Ok(()))
        }
    }
    impl AsyncRead for Script {
        fn poll_read(self: Pin<&mut Self>, _: &mut Context<'_>, output: &mut ReadBuf<'_>) -> Poll<io::Result<()>> {
            let mut log = self.log.lock().unwrap(); assert!(log.pending.is_none()); log.reads += 1;
            if output.remaining() > 0 { output.put_slice(&[0x75]); } Poll::Ready(Ok(()))
        }
    }
    fn scripted(steps: Vec<Step>) -> (PacketWriteIo<Script>, PacketDrain<Script>, Arc<Mutex<Log>>) {
        let log = Arc::new(Mutex::new(Log::default()));
        let (writer, drain) = PacketWriteIo::new(Script { steps: steps.into(), log: Arc::clone(&log) });
        (writer, drain, log)
    }
    #[tokio::test]
    async fn accepted_bytes_are_ready_without_inner_io_and_pending_remainder_is_stable() {
        let (mut writer, mut drain, log) = scripted(vec![Step::Count(2), Step::Pending, Step::Count(2)]);
        writer.write_all(b"abcd").await.unwrap();
        assert_eq!(log.lock().unwrap().calls, 0, "acceptance must not perform inner I/O");
        writer.write_all(b"XYZ").await.unwrap();
        drain.flush().await.unwrap();
        assert_eq!(log.lock().unwrap().bytes, b"abcdXYZ");
    }
    #[tokio::test]
    async fn read_and_shutdown_drain_retained_bytes_first() {
        let (mut writer, _drain, log) = scripted(vec![Step::Pending]);
        writer.write_all(b"before-read").await.unwrap();
        assert_eq!(writer.read_u8().await.unwrap(), 0x75);
        assert_eq!(log.lock().unwrap().bytes, b"before-read");
        writer.write_all(b"before-shutdown").await.unwrap();
        writer.shutdown().await.unwrap();
        assert_eq!(log.lock().unwrap().bytes, b"before-readbefore-shutdown");
        assert_eq!(log.lock().unwrap().shutdowns, 1);
    }
    #[tokio::test]
    async fn zero_and_impossible_inner_counts_fail_sticky() {
        for (count, expected) in [(0, io::ErrorKind::WriteZero), (5, io::ErrorKind::InvalidData)] {
            let (mut writer, mut drain, log) = scripted(vec![Step::Count(count)]);
            writer.write_all(b"four").await.unwrap();
            assert_eq!(drain.flush().await.unwrap_err().kind(), expected);
            assert_eq!(writer.write_all(b"later").await.unwrap_err().kind(), expected);
            assert_eq!(log.lock().unwrap().calls, 1);
        }
    }
    #[tokio::test]
    async fn oversized_packet_is_rejected_before_acceptance() {
        let (mut writer, _drain, log) = scripted(vec![]);
        assert_eq!(writer.write_all(&[0; MAX_PACKET + 1]).await.unwrap_err().kind(), io::ErrorKind::InvalidInput);
        assert_eq!(log.lock().unwrap().calls, 0);
    }
}
