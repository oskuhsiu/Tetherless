use futures::{SinkExt, StreamExt};
use rootcause::prelude::*;

pub enum WsMessage {
    Text(String),
    Close,
}

pub struct AppWebSocket {
    #[cfg(not(feature = "wasm"))]
    inner: tokio_tungstenite::WebSocketStream<
        tokio_tungstenite::MaybeTlsStream<tokio::net::TcpStream>,
    >,
    #[cfg(feature = "wasm")]
    inner: ws_stream_wasm::WsStream,
    #[cfg(feature = "wasm")]
    meta: ws_stream_wasm::WsMeta,
}

impl AppWebSocket {
    pub async fn connect(url: &str, proxy_url: Option<&str>) -> Result<Self, Report> {
        let target_url = if proxy_url.is_some() {
            let proxied = format!(
                "{}{}",
                proxy_url.unwrap(),
                urlencoding::encode(url)
            )
            .replace("https://", "wss://");
            proxied
        } else {
            url.to_string()
        };

        #[cfg(not(feature = "wasm"))]
        {
            use tokio::time::{Duration, timeout};

            let (stream, _) = timeout(
                Duration::from_secs(30),
                tokio_tungstenite::connect_async_with_config(
                    &target_url,
                    Some(tokio_tungstenite::tungstenite::protocol::WebSocketConfig::default()
                        .max_message_size(Some(64 * 1024))
                        .max_frame_size(Some(64 * 1024))),
                    false,
                ),
            )
            .await?
            .context(
                "Timed out connecting to provisioning socket. Try a different anisette server.",
            )?;
            Ok(Self { inner: stream })
        }
        #[cfg(feature = "wasm")]
        {
            let (meta, stream) = ws_stream_wasm::WsMeta::connect(&target_url, None)
                .await
                .map_err(|e| report!("WS connect failed: {e:?}"))?;
            Ok(Self {
                meta,
                inner: stream,
            })
        }
    }

    pub async fn send_text(&mut self, text: String) -> Result<(), Report> {
        #[cfg(not(feature = "wasm"))]
        {
            if text.len() > 64 * 1024 { bail!("Provisioning message exceeds size limit"); }
            tokio::time::timeout(std::time::Duration::from_secs(30), self.inner
                .send(tokio_tungstenite::tungstenite::Message::Text(text.into())))
                .await.context("Provisioning send deadline exceeded")??;
        }
        #[cfg(feature = "wasm")]
        self.inner
            .send(ws_stream_wasm::WsMessage::Text(text))
            .await
            .map_err(|e| report!("WS send failed: {e:?}"))?;
        Ok(())
    }

    pub async fn next(&mut self) -> Option<Result<WsMessage, Report>> {
        #[cfg(not(feature = "wasm"))]
        {
            let msg = match tokio::time::timeout(
                std::time::Duration::from_secs(30), self.inner.next()).await {
                Ok(message) => message?,
                Err(_) => return Some(Err(report!("Provisioning receive deadline exceeded"))),
            };
            Some(msg.map_err(Into::into).map(|m| match m {
                tokio_tungstenite::tungstenite::Message::Text(t) => WsMessage::Text(t.to_string()),
                tokio_tungstenite::tungstenite::Message::Close(_) => WsMessage::Close,
                _ => WsMessage::Close,
            }))
        }
        #[cfg(feature = "wasm")]
        {
            let msg = self.inner.next().await?;
            Some(Ok(match msg {
                ws_stream_wasm::WsMessage::Text(t) => WsMessage::Text(t),
                ws_stream_wasm::WsMessage::Binary(_) => WsMessage::Close,
            }))
        }
    }

    pub async fn close(&mut self) -> Result<(), Report> {
        #[cfg(not(feature = "wasm"))]
        tokio::time::timeout(std::time::Duration::from_secs(5), self.inner.close(None))
            .await.context("Provisioning close deadline exceeded")??;
        #[cfg(feature = "wasm")]
        self.meta
            .close()
            .await
            .map_err(|e| report!("WS close failed: {e:?}"))?;
        Ok(())
    }
}

#[cfg(all(test, not(feature = "wasm")))]
mod transport_tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    #[test]
    fn websocket_redirect_is_not_followed() {
        let destination = TcpListener::bind("127.0.0.1:0").unwrap();
        destination.set_nonblocking(true).unwrap();
        let origin = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("ws://{}", origin.local_addr().unwrap());
        let location = format!("HTTP/1.1 302 Found\r\nLocation: ws://{}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n", destination.local_addr().unwrap());
        let server = std::thread::spawn(move || {
            let (mut stream, _) = origin.accept().unwrap();
            stream.set_read_timeout(Some(std::time::Duration::from_secs(5))).unwrap();
            let _ = stream.read(&mut [0u8; 4096]);
            stream.write_all(location.as_bytes()).unwrap();
        });
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            assert!(AppWebSocket::connect(&url, None).await.is_err());
        });
        server.join().unwrap();
        assert_eq!(destination.accept().unwrap_err().kind(), std::io::ErrorKind::WouldBlock);
    }

    #[test]
    fn wss_does_not_fall_back_to_plaintext() {
        let _ = rustls::crypto::ring::default_provider().install_default();
        let origin = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("wss://{}", origin.local_addr().unwrap());
        let server = std::thread::spawn(move || {
            let (mut stream, _) = origin.accept().unwrap();
            stream.set_read_timeout(Some(std::time::Duration::from_secs(5))).unwrap();
            let mut bytes = [0u8; 4096];
            let count = stream.read(&mut bytes).unwrap();
            assert!(count > 0);
            assert_ne!(&bytes[..count.min(3)], b"GET");
            let _ = stream.write_all(b"HTTP/1.1 200 OK\r\nContent-Length: 0\r\n\r\n");
        });
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            assert!(AppWebSocket::connect(&url, None).await.is_err());
        });
        server.join().unwrap();
    }

    #[test]
    fn websocket_rejects_oversized_message() {
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap().block_on(async {
            let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
            let url = format!("ws://{}", listener.local_addr().unwrap());
            let server = tokio::spawn(async move {
                let (stream, _) = listener.accept().await.unwrap();
                let mut socket = tokio_tungstenite::accept_async(stream).await.unwrap();
                let _ = socket.send(tokio_tungstenite::tungstenite::Message::Text("x".repeat(65537).into())).await;
            });
            let mut socket = AppWebSocket::connect(&url, None).await.unwrap();
            assert!(socket.next().await.unwrap().is_err());
            server.await.unwrap();
        });
    }
}
