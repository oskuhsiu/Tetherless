mod state;
mod websocket;

use std::sync::Arc;
use std::time::Duration;
use web_time::SystemTime;

use base64::prelude::*;
use plist_macro::plist;
use reqwest::{
    ClientBuilder,
    header::{CONTENT_TYPE, HeaderMap, HeaderValue},
};
use reqwest_middleware::ClientBuilder as MwClientBuilder;
use rootcause::option_ext::OptionExt;
use rootcause::prelude::*;
use serde::Deserialize;
use tracing::{debug, info, warn};

use crate::anisette::remote_v3::websocket::AppWebSocket;
use crate::anisette::{AnisetteClientInfo, AnisetteData, AnisetteProvider};
use crate::anisette::{
    AnisetteDataResponse,
    remote_v3::{state::AnisetteState, websocket::WsMessage},
};
use crate::auth::grandslam::GrandSlam;
use crate::util::plist::PlistDataExtract;
use crate::util::storage::{SideloadingStorage, new_storage};

pub const DEFAULT_ANISETTE_V3_URL: &str = "https://ani.jkcoxson.com";
pub const ANISETTE_STATE_KEY: &str = "anisette_state";

pub struct RemoteV3AnisetteProvider {
    pub state: Option<AnisetteState>,
    url: String,
    storage: Box<dyn SideloadingStorage>,
    serial_number: String,
    client: reqwest_middleware::ClientWithMiddleware,
    websocket_proxy: Option<String>,
}

impl RemoteV3AnisetteProvider {
    /// Create a new RemoteV3AnisetteProvider with the given URL and config path
    ///
    /// # Arguments
    /// - `url`: The URL of the remote anisette service
    /// - `storage`: The storage backend for anisette data
    /// - `serial_number`: The serial number of the device
    pub fn new(
        url: &str,
        storage: Box<dyn SideloadingStorage>,
        serial_number: String,
    ) -> Result<Self, Report> {
        Ok(Self {
            state: None,
            url: url.to_string(),
            storage,
            serial_number,
            client: Self::build_reqwest_client(None)?,
            websocket_proxy: None,
        })
    }

    pub fn set_websocket_proxy(mut self, websocket_proxy: Option<String>) -> Result<Self, Report> {
        self.websocket_proxy = websocket_proxy;
        self.client = Self::build_reqwest_client(self.websocket_proxy.clone())?;
        Ok(self)
    }

    fn build_reqwest_client(
        websocket_proxy: Option<String>,
    ) -> Result<reqwest_middleware::ClientWithMiddleware, Report> {
        if let Some(websocket_proxy) = websocket_proxy {
            use crate::auth::middleware::WasmProxyMiddleware;

            let client = Self::transport_builder().build()?;

            Ok(MwClientBuilder::new(client)
                .with(WasmProxyMiddleware::new(websocket_proxy))
                .build())
        } else {
            let client = Self::transport_builder().build()?;

            Ok(MwClientBuilder::new(client).build())
        }
    }

    // Fixed-origin transport: never forward provisioning material via redirects.
    fn transport_builder() -> ClientBuilder {
        let builder = ClientBuilder::new();
        #[cfg(not(target_arch = "wasm32"))]
        let builder = builder
            .redirect(reqwest::redirect::Policy::none())
            .connect_timeout(Duration::from_secs(10))
            .timeout(Duration::from_secs(30));
        builder
    }

    pub fn default() -> Result<Self, Report> {
        Self::new(
            DEFAULT_ANISETTE_V3_URL,
            Box::new(new_storage()),
            "0".to_string(),
        )
    }

    pub fn set_url(mut self, url: &str) -> RemoteV3AnisetteProvider {
        self.url = url.to_string();
        self
    }

    pub fn set_storage(mut self, storage: Box<dyn SideloadingStorage>) -> RemoteV3AnisetteProvider {
        self.storage = storage;
        self
    }

    pub fn set_serial_number(mut self, serial_number: String) -> RemoteV3AnisetteProvider {
        self.serial_number = serial_number;
        self
    }
}

#[cfg_attr(feature = "wasm", async_trait::async_trait(?Send))]
#[cfg_attr(not(feature = "wasm"), async_trait::async_trait)]
impl AnisetteProvider for RemoteV3AnisetteProvider {
    async fn get_anisette_data(&self) -> Result<AnisetteDataResponse, Report> {
        self.fetch_headers(None).await
    }

    async fn resync(&self, sim: &str) -> Result<AnisetteDataResponse, Report> {
        self.fetch_headers(Some(sim)).await
    }

    // Can be hardcoded, but apple is changing things so much nowadays it makes more sense to just get it from the server
    async fn get_client_info(&self) -> Result<AnisetteClientInfo, Report> {
        let response = self
            .client
            .get(format!("{}/v3/client_info", self.url))
            .send()
            .await
            .context("Failed to request /v3/client_info from anisette server")?
            .error_for_status()
            .context("anisette server returned an error for /v3/client_info")?;
        let info: AnisetteClientInfo = bounded_json(response, 16 * 1024).await?;
        validate_client_info(&info)?;

        // let info = AnisetteClientInfo {
        //     client_info:
        //         "<Pixel 7> <Android;14;UQ1A.240205.002> <com.apple.AuthKit/1 (com.apple.akd/1.0)>"
        //             .to_string(),
        //     user_agent: "akd/1.0 CFNetwork/808.1.4".to_string(),
        // };
        Ok(info)
    }

    async fn provision(&mut self, gs: &Arc<GrandSlam>, force_reset: bool) -> Result<(), Report> {
        self.get_client_info().await?;
        self.get_state(gs, force_reset).await?;
        Ok(())
    }
}

impl RemoteV3AnisetteProvider {
    async fn fetch_headers(&self, sim: Option<&str>) -> Result<AnisetteDataResponse, Report> {
        let Some(state) = self.state.as_ref() else {
            return Ok(AnisetteDataResponse::NeedsProvisioning);
        };

        let Some(adi_pb) = state.adi_pb.as_ref() else {
            return Ok(AnisetteDataResponse::NeedsProvisioning);
        };

        let client_info = self.get_client_info().await?;

        let mut body = serde_json::json!({
            "identifier": BASE64_STANDARD.encode(state.keychain_identifier),
            "adi_pb": BASE64_STANDARD.encode(adi_pb),
        });
        if let Some(sim) = sim {
            body["sim"] = serde_json::Value::String(sim.to_string());
            body["device_id"] = serde_json::Value::String(state.get_device_id());
            body["md_lu"] = serde_json::Value::String(hex::encode(state.get_md_lu()));
        }

        let response = self
            .client
            .post(format!("{}/v3/get_headers", self.url))
            .header(CONTENT_TYPE, "application/json")
            .body(body.to_string())
            .send()
            .await?
            .error_for_status()?;
        let headers: AnisetteHeaders = bounded_json(response, 64 * 1024).await?;

        match headers {
            AnisetteHeaders::Headers {
                machine_id,
                one_time_password,
                routing_info,
            } => Ok(AnisetteDataResponse::Data(AnisetteData {
                machine_id,
                one_time_password,
                routing_info,
                _device_description: client_info.client_info.clone(),
                device_unique_identifier: state.get_device_id(),
                _local_user_id: hex::encode(state.get_md_lu()),
                generated_at: SystemTime::now(),
            })),
            AnisetteHeaders::GetHeadersError { message } => {
                if message.contains("-45061") {
                    warn!("Server says anisette not provisioned");
                    return Ok(AnisetteDataResponse::IncorrectlyProvisioned);
                }
                Err(report!("Failed to get anisette headers").attach(message))
            }
        }
    }

    async fn get_state(
        &mut self,
        gs: &Arc<GrandSlam>,
        force_reset: bool,
    ) -> Result<&mut AnisetteState, Report> {
        if force_reset {
            warn!("Resetting anisette state");
            self.state = Some(AnisetteState::new());
        } else if self.state.is_none() {
            if let Ok(Some(state)) = &self.storage.retrieve_data(ANISETTE_STATE_KEY) {
                if let Ok(state) = plist::from_bytes(state) {
                    info!("Loaded existing anisette state");
                    self.state = Some(state);
                } else {
                    warn!("Failed to parse existing anisette state, starting fresh");
                    self.state = Some(AnisetteState::new());
                }
            } else {
                info!("No existing anisette state found");
                self.state = Some(AnisetteState::new());
            }
        }

        let state = self.state.as_mut().ok_or_report()?;
        if !state.is_provisioned() {
            info!("Provisioning required...");
            Self::provision(state, gs, &self.url, self.websocket_proxy.as_deref())
                .await
                .context("Failed to provision")?;
        }
        let buf = Vec::new();
        let mut writer = std::io::BufWriter::new(buf);
        plist::to_writer_xml(&mut writer, &state)?;
        self.storage
            .store_data(ANISETTE_STATE_KEY, &writer.into_inner()?)?;

        Ok(state)
    }

    async fn provisioning_headers(state: &AnisetteState) -> Result<HeaderMap, Report> {
        let mut headers = HeaderMap::new();
        headers.insert(
            "X-Apple-I-MD-LU",
            HeaderValue::from_str(&hex::encode(state.get_md_lu()))?,
        );
        // headers.insert(
        //     "X-Apple-I-Client-Time",
        //     HeaderValue::from_str(
        //         &Utc::now()
        //             .round_subsecs(0)
        //             .format("%+")
        //             .to_string()
        //             .replace("+00:00", "Z"),
        //     )?,
        // );
        // headers.insert("X-Apple-I-TimeZone", HeaderValue::from_static("UTC"));
        // headers.insert("X-Apple-Locale", HeaderValue::from_static("en_US"));
        headers.insert(
            "X-Mme-Device-Id",
            HeaderValue::from_str(&state.get_device_id())?,
        );

        Ok(headers)
    }
    async fn provision(
        state: &mut AnisetteState,
        gs: &Arc<GrandSlam>,
        url: &str,
        proxy_url: Option<&str>,
    ) -> Result<(), Report> {
        #[cfg(not(feature = "wasm"))]
        { tokio::time::timeout(Duration::from_secs(120),
            Self::provision_inner(state, gs, url, proxy_url)).await
            .context("Anisette provisioning deadline exceeded")? }
        #[cfg(feature = "wasm")]
        { Self::provision_inner(state, gs, url, proxy_url).await }
    }

    async fn provision_inner(
        state: &mut AnisetteState,
        gs: &Arc<GrandSlam>,
        url: &str,
        proxy_url: Option<&str>,
    ) -> Result<(), Report> {
        let start_provisioning = gs.get_url("midStartProvisioning")?;
        let end_provisioning = gs.get_url("midFinishProvisioning")?;

        let websocket_url = format!("{}/v3/provisioning_session", url)
            .replace("https://", "wss://")
            .replace("http://", "ws://");

        debug!("Starting provisioning at {}", websocket_url);
        // let (mut ws_stream, _) = timeout(
        //     Duration::from_secs(30),
        //     tokio_tungstenite::connect_async(&websocket_url),
        // )
        // .await
        // .map_err(|_| {
        //     report!("Timed out connecting to provisioning socket. Try a different anisette server.")
        // })
        // .context("Failed to connect to provisioning socket")?
        // .context("Failed to connect to provisioning socket")?;

        let mut ws = AppWebSocket::connect(&websocket_url, proxy_url.as_deref())
            .await
            .context("Failed to connect to provisioning socket")?;

        debug!("Connected to provisioning socket");

        loop {
            let Some(msg) = ws.next().await else { bail!("Provisioning socket ended unexpectedly") };
            let msg = msg?;

            let text = match msg {
                WsMessage::Close => bail!("Provisioning socket closed unexpectedly"),
                WsMessage::Text(t) => t,
            };

            debug!("Received provisioning message: {}", text);
            let provision_msg: ProvisioningMessage = serde_json::from_str(&text)?;

            match provision_msg {
                ProvisioningMessage::GiveIdentifier => {
                    ws.send_text(
                        serde_json::json!({
                            "identifier": BASE64_STANDARD.encode(state.keychain_identifier),
                        })
                        .to_string()
                        .into(),
                    )
                    .await
                    .context("Failed to send identifier")?;
                }
                ProvisioningMessage::GiveStartProvisioningData => {
                    let body = plist!(dict {
                        "Header": {},
                        "Request": {}
                    });

                    let response = gs
                        .plist_request(
                            &start_provisioning,
                            &body,
                            Some(Self::provisioning_headers(state).await?),
                            None,
                        )
                        .await
                        .context("Failed to send start provisioning request")?;

                    let spim = response
                        .get_str("spim")
                        .context("Start provisioning response missing spim")?;

                    ws.send_text(
                        serde_json::json!({
                            "spim": spim,
                        })
                        .to_string()
                        .into(),
                    )
                    .await
                    .context("Failed to send start provisioning data")?;
                }
                ProvisioningMessage::GiveEndProvisioningData { cpim } => {
                    let body = plist!(dict {
                        "Header": {},
                        "Request": {
                            "cpim": cpim,
                        }
                    });

                    let response = gs
                        .plist_request(
                            &end_provisioning,
                            &body,
                            Some(Self::provisioning_headers(state).await?),
                            None,
                        )
                        .await
                        .context("Failed to send end provisioning request")?;

                    ws.send_text(
                        serde_json::json!({
                            "ptm": response
                                .get_str("ptm")
                                .context("End provisioning response missing ptm")?,
                            "tk": response
                                .get_str("tk")
                                .context("End provisioning response missing tk")?,
                        })
                        .to_string()
                        .into(),
                    )
                    .await
                    .context("Failed to send start provisioning data")?;
                }
                ProvisioningMessage::ProvisioningSuccess { adi_pb } => {
                    state.adi_pb = Some(BASE64_STANDARD.decode(adi_pb)?);
                    ws.close().await?;
                    info!("Provisioning successful");
                    break;
                }
                ProvisioningMessage::Timeout => bail!("Anisette provisioning timed out"),
                ProvisioningMessage::InvalidIdentifier => {
                    bail!("Anisette provisioning failed: invalid identifier")
                }
                ProvisioningMessage::StartProvisioningError { message } => {
                    return Err(
                        report!("Anisette provisioning failed: start provisioning error")
                            .attach(message),
                    );
                }
                ProvisioningMessage::EndProvisioningError { message } => {
                    return Err(
                        report!("Anisette provisioning failed: end provisioning error")
                            .attach(message),
                    );
                }
            }
        }

        Ok(())
    }
}

#[derive(Deserialize)]
#[serde(tag = "result")]
enum ProvisioningMessage {
    GiveIdentifier,
    GiveStartProvisioningData,
    GiveEndProvisioningData { cpim: String },
    ProvisioningSuccess { adi_pb: String },
    Timeout,
    InvalidIdentifier,
    StartProvisioningError { message: String },
    EndProvisioningError { message: String },
}

#[derive(Deserialize)]
#[serde(tag = "result")]
enum AnisetteHeaders {
    GetHeadersError {
        message: String,
    },
    Headers {
        #[serde(rename = "X-Apple-I-MD-M")]
        machine_id: String,
        #[serde(rename = "X-Apple-I-MD")]
        one_time_password: String,
        #[serde(rename = "X-Apple-I-MD-RINFO")]
        routing_info: String,
    },
}

// Bound decoded response bytes even when Content-Length is absent or compressed.
async fn bounded_json<T: serde::de::DeserializeOwned>(
    mut response: reqwest::Response,
    limit: usize,
) -> Result<T, Report> {
    if !response.status().is_success() {
        bail!("Unexpected anisette HTTP status");
    }
    if response.content_length().is_some_and(|length| length > limit as u64) {
        bail!("Anisette response exceeds size limit");
    }
    let mut bytes = Vec::new();
    while let Some(chunk) = response.chunk().await? {
        if chunk.len() > limit.saturating_sub(bytes.len()) {
            bail!("Anisette response exceeds size limit");
        }
        bytes.extend_from_slice(&chunk);
    }
    Ok(serde_json::from_slice(&bytes).context("Invalid anisette JSON response")?)
}

fn validate_client_info(info: &AnisetteClientInfo) -> Result<(), Report> {
    for value in [&info.client_info, &info.user_agent] {
        if value.trim().is_empty() || value.len() > 1024 || value.chars().any(char::is_control) {
            bail!("Invalid anisette client metadata");
        }
        HeaderValue::from_str(value).context("Invalid anisette client metadata header")?;
    }
    Ok(())
}

#[cfg(all(test, not(feature = "wasm")))]
mod transport_tests {
    use super::*;
    use std::io::{Read, Write};
    use std::net::TcpListener;

    fn runtime() -> tokio::runtime::Runtime {
        let _ = rustls::crypto::ring::default_provider().install_default();
        tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap()
    }

    fn serve_once(status: &str, headers: &str, body: Vec<u8>) -> (String, std::thread::JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").unwrap();
        let url = format!("http://{}", listener.local_addr().unwrap());
        let head = format!("HTTP/1.1 {status}\r\nConnection: close\r\n{headers}\r\n");
        let task = std::thread::spawn(move || {
            let (mut stream, _) = listener.accept().unwrap();
            stream.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
            let mut request = [0u8; 4096];
            let _ = stream.read(&mut request);
            let _ = stream.write_all(head.as_bytes());
            let _ = stream.write_all(&body);
        });
        (url, task)
    }

    #[test]
    fn metadata_accepts_synthetic_values_and_rejects_invalid_values() {
        let good = AnisetteClientInfo {
            client_info: "<Synthetic> <Test;1.0>".into(), user_agent: "Synthetic/1.0".into(),
        };
        assert!(validate_client_info(&good).is_ok());
        for bad in ["".to_string(), "   ".into(), "x\r\ny".into(), "x\ty".into(), "x\0y".into(), "x".repeat(1025)] {
            assert!(validate_client_info(&AnisetteClientInfo { client_info: bad.clone(), user_agent: good.user_agent.clone() }).is_err());
            assert!(validate_client_info(&AnisetteClientInfo { client_info: good.client_info.clone(), user_agent: bad }).is_err());
        }
    }

    #[test]
    fn http_metadata_success_and_bounded_rejection() {
        runtime().block_on(async {
            let client = RemoteV3AnisetteProvider::transport_builder().no_proxy().build().unwrap();
            for (body, limit, succeeds) in [
                (br#"{"client_info":"<Synthetic>","user_agent":"Synthetic/1"}"#.to_vec(), 16384, true),
                (b"{bad json".to_vec(), 16384, false),
                (vec![b'x'; 16385], 16384, false),
            ] {
                // No Content-Length: enforce streaming bound, not only header preflight.
                let (url, server) = serve_once("200 OK", "", body);
                let response = client.get(url).send().await.unwrap();
                let result = bounded_json::<AnisetteClientInfo>(response, limit).await;
                assert_eq!(result.is_ok(), succeeds);
                server.join().unwrap();
            }
            let (url, server) = serve_once("200 OK", "Content-Length: 999999\r\n", vec![]);
            assert!(bounded_json::<AnisetteClientInfo>(client.get(url).send().await.unwrap(), 16384).await.is_err());
            server.join().unwrap();
        });
    }

    #[test]
    fn resync_payload_is_only_declared_synthetic_material() {
        runtime().block_on(async {
            for (reply, incorrectly_provisioned) in [
                (r#"{"result":"Headers","X-Apple-I-MD-M":"synthetic-machine","X-Apple-I-MD":"synthetic-otp","X-Apple-I-MD-RINFO":"0"}"#, false),
                (r#"{"result":"GetHeadersError","message":"synthetic -45061"}"#, true),
            ] {
                let listener = TcpListener::bind("127.0.0.1:0").unwrap();
                let url = format!("http://{}", listener.local_addr().unwrap());
                let server = std::thread::spawn(move || {
                    for request_number in 0..2 {
                        let (mut stream, _) = listener.accept().unwrap();
                        stream.set_read_timeout(Some(Duration::from_secs(5))).unwrap();
                        let mut request = Vec::new();
                        let header_end = loop {
                            let mut byte = [0u8; 1];
                            stream.read_exact(&mut byte).unwrap();
                            request.push(byte[0]);
                            assert!(request.len() <= 8192);
                            if request.ends_with(b"\r\n\r\n") { break request.len(); }
                        };
                        let headers = String::from_utf8(request.clone()).unwrap();
                        if request_number == 0 {
                            assert!(headers.starts_with("GET /v3/client_info "));
                        } else {
                            assert!(headers.starts_with("POST /v3/get_headers "));
                            let length: usize = headers.lines().find_map(|line| {
                                let (name, value) = line.split_once(':')?;
                                name.eq_ignore_ascii_case("content-length").then(|| value.trim().parse().unwrap())
                            }).unwrap();
                            assert!(length <= 4096);
                            request.resize(header_end + length, 0);
                            stream.read_exact(&mut request[header_end..]).unwrap();
                            let body: serde_json::Value = serde_json::from_slice(&request[header_end..]).unwrap();
                            let keys: std::collections::BTreeSet<_> = body.as_object().unwrap().keys().map(String::as_str).collect();
                            assert_eq!(keys, ["identifier", "adi_pb", "sim", "device_id", "md_lu"].into_iter().collect());
                            assert_eq!(body["identifier"], BASE64_STANDARD.encode([7u8; 16]));
                            assert_eq!(body["adi_pb"], BASE64_STANDARD.encode(b"synthetic-adi"));
                            assert_eq!(body["sim"], "synthetic-sim");
                            assert_eq!(body["device_id"], "07070707-0707-0707-0707-070707070707");
                            let state = AnisetteState { keychain_identifier: [7u8; 16], adi_pb: None };
                            assert_eq!(body["md_lu"], hex::encode(state.get_md_lu()));
                        }
                        let body = if request_number == 0 {
                            r#"{"client_info":"<Synthetic>","user_agent":"Synthetic/1"}"#
                        } else { reply };
                        write!(stream, "HTTP/1.1 200 OK\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", body.len(), body).unwrap();
                    }
                });
                let mut provider = RemoteV3AnisetteProvider::new(&url, Box::new(new_storage()), "0".into()).unwrap();
                provider.client = MwClientBuilder::new(RemoteV3AnisetteProvider::transport_builder().no_proxy().build().unwrap()).build();
                provider.state = Some(AnisetteState { keychain_identifier: [7u8; 16], adi_pb: Some(b"synthetic-adi".to_vec()) });
                let result = provider.resync("synthetic-sim").await.unwrap();
                assert_eq!(matches!(result, AnisetteDataResponse::IncorrectlyProvisioned), incorrectly_provisioned);
                if !incorrectly_provisioned { assert!(matches!(result, AnisetteDataResponse::Data(_))); }
                server.join().unwrap();
            }
        });
    }

    #[test]
    fn post_redirect_never_reaches_other_recipient() {
        runtime().block_on(async {
            let destination = TcpListener::bind("127.0.0.1:0").unwrap();
            destination.set_nonblocking(true).unwrap();
            let location = format!("Location: http://{}/collect\r\nContent-Length: 0\r\n", destination.local_addr().unwrap());
            let (url, server) = serve_once("307 Temporary Redirect", &location, vec![]);
            let response = RemoteV3AnisetteProvider::transport_builder().no_proxy().build().unwrap()
                .post(url).body("synthetic-provisioning-material").send().await.unwrap();
            assert_eq!(response.status(), reqwest::StatusCode::TEMPORARY_REDIRECT);
            assert!(bounded_json::<serde_json::Value>(response, 65536).await.is_err());
            server.join().unwrap();
            assert_eq!(destination.accept().unwrap_err().kind(), std::io::ErrorKind::WouldBlock);
        });
    }
}
