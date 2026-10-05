//! Remote Service Discovery
//! Communicates via XPC and returns advertised services

use std::collections::HashMap;

use serde::Deserialize;
use tracing::{debug, warn};

use crate::{IdeviceError, ReadWrite, RemoteXpcClient, provider::RsdProvider};

/// Describes an available XPC service
#[derive(Debug, Clone, Deserialize)]
pub struct RsdService {
    /// Required entitlement to access this service
    pub entitlement: String,
    /// Port number where the service is available
    pub port: u16,
    /// Whether the service uses remote XPC
    pub uses_remote_xpc: bool,
    /// Optional list of supported features
    pub features: Option<Vec<String>>,
    /// Optional service version number
    pub service_version: Option<i64>,
}

#[derive(Debug, Clone)]
pub struct RsdHandshake {
    pub services: HashMap<String, RsdService>,
    pub protocol_version: usize,
    pub properties: HashMap<String, plist::Value>,
    pub uuid: String,
}

impl RsdHandshake {
    pub async fn new(socket: impl ReadWrite) -> Result<Self, IdeviceError> {
        let mut xpc_client = RemoteXpcClient::new(socket).await?;
        xpc_client.do_handshake().await?;
        xpc_client.send_device_handshake().await?;
        let data = xpc_client.recv_root().await?;
        Self::from_handshake_data(data, false)
    }

    /// Bounded, acquisition-only RSD over the existing RemoteXPC transport.
    /// The caller must apply its whole-request cancellation and deadline to this
    /// future. Failure or cancellation is terminal: discard the connection.
    /// Existing `new` callers retain their original behavior.
    pub async fn new_bounded(socket: impl ReadWrite) -> Result<Self, IdeviceError> {
        let mut xpc_client = RemoteXpcClient::new_bounded_rsd(socket).await?;
        xpc_client.do_handshake().await?;
        xpc_client.send_device_handshake().await?;
        let data = xpc_client.recv_root().await?;
        Self::from_handshake_data(data, true)
    }

    fn from_handshake_data(data: plist::Value, bounded: bool) -> Result<Self, IdeviceError> {
        let services_dict = match data
            .as_dictionary()
            .and_then(|x| x.get("Services"))
            .and_then(|x| x.as_dictionary())
        {
            Some(d) => d,
            None => {
                return Err(IdeviceError::UnexpectedResponse(
                    "missing Services dictionary in RSD handshake".into(),
                ));
            }
        };

        if bounded && services_dict.len() > 1024 {
            return Err(IdeviceError::UnexpectedResponse("RSD service budget exceeded".into()));
        }

        // Parse available services
        let mut services: HashMap<String, RsdService> = HashMap::new();
        for (name, service) in services_dict.into_iter() {
            match service.as_dictionary() {
                Some(service) => {
                    let entitlement = match service.get("Entitlement").and_then(|x| x.as_string()) {
                        Some(e) => e.to_string(),
                        None => {
                            warn!("Service did not contain entitlement string");
                            continue;
                        }
                    };
                    let port = match service
                        .get("Port")
                        .and_then(|x| x.as_string())
                        .and_then(|x| x.parse::<u16>().ok())
                    {
                        Some(e) => e,
                        None => {
                            warn!("Service did not contain port string");
                            continue;
                        }
                    };
                    let uses_remote_xpc = match service
                        .get("Properties")
                        .and_then(|x| x.as_dictionary())
                        .and_then(|x| x.get("UsesRemoteXPC"))
                        .and_then(|x| x.as_boolean())
                    {
                        Some(e) => e.to_owned(),
                        None => false, // default is false
                    };

                    let features = service
                        .get("Properties")
                        .and_then(|x| x.as_dictionary())
                        .and_then(|x| x.get("Features"))
                        .and_then(|x| x.as_array())
                        .map(|f| {
                            f.iter()
                                .filter_map(|x| x.as_string())
                                .map(|x| x.to_string())
                                .collect::<Vec<String>>()
                        });

                    let service_version = service
                        .get("Properties")
                        .and_then(|x| x.as_dictionary())
                        .and_then(|x| x.get("ServiceVersion"))
                        .and_then(|x| x.as_signed_integer())
                        .map(|e| e.to_owned());

                    services.insert(
                        name.to_string(),
                        RsdService {
                            entitlement,
                            port,
                            uses_remote_xpc,
                            features,
                            service_version,
                        },
                    );
                }
                None => {
                    warn!("Service is not a dictionary!");
                    continue;
                }
            }
        }

        let protocol_version = match data.as_dictionary().and_then(|x| {
            x.get("MessagingProtocolVersion")
                .and_then(|x| x.as_signed_integer())
        }) {
            Some(p) if bounded => usize::try_from(p).map_err(|_| {
                IdeviceError::UnexpectedResponse("invalid RSD protocol version".into())
            })?,
            Some(p) => p as usize,
            None => {
                return Err(IdeviceError::UnexpectedResponse(
                    "missing MessagingProtocolVersion in RSD handshake".into(),
                ));
            }
        };

        let uuid = match data
            .as_dictionary()
            .and_then(|x| x.get("UUID").and_then(|x| x.as_string()))
        {
            Some(u) => u.to_string(),
            None => {
                return Err(IdeviceError::UnexpectedResponse(
                    "missing UUID in RSD handshake".into(),
                ));
            }
        };

        let properties = match data
            .as_dictionary()
            .and_then(|x| x.get("Properties").and_then(|x| x.as_dictionary()))
        {
            Some(d) => d
                .into_iter()
                .map(|(name, prop)| (name.to_owned(), prop.to_owned()))
                .collect::<HashMap<String, plist::Value>>(),
            None => {
                return Err(IdeviceError::UnexpectedResponse(
                    "missing Properties dictionary in RSD handshake".into(),
                ));
            }
        };

        Ok(Self {
            services,
            protocol_version,
            properties,
            uuid,
        })
    }

    pub async fn connect<T>(&mut self, provider: &mut impl RsdProvider) -> Result<T, IdeviceError>
    where
        T: crate::RsdService,
    {
        let service_name = T::rsd_service_name();
        let service = match self.services.get(&service_name.to_string()) {
            Some(s) => s,
            None => {
                return Err(IdeviceError::ServiceNotFound);
            }
        };

        debug!(
            "Connecting to RSD service {service_name} on port {}",
            service.port
        );
        let stream = provider.connect_to_service_port(service.port).await?;
        T::from_stream(stream).await
    }
}


#[cfg(test)]
mod bounded_rsd_tests {
    use super::*;
    use crate::xpc::{Dictionary, XPCMessage, XPCObject};
    use tokio::io::{AsyncReadExt, AsyncWriteExt};

    fn fixture() -> XPCObject {
        let mut service = Dictionary::new();
        service.insert("Port".into(), XPCObject::String("62078".into()));
        service.insert("Entitlement".into(), XPCObject::String("fixture".into()));
        let mut services = Dictionary::new();
        services.insert("fixture.service".into(), XPCObject::Dictionary(service));
        let mut root = Dictionary::new();
        root.insert("Services".into(), XPCObject::Dictionary(services));
        root.insert("MessagingProtocolVersion".into(), XPCObject::UInt64(7));
        root.insert("UUID".into(), XPCObject::String("fixture".into()));
        root.insert("Properties".into(), XPCObject::Dictionary(Dictionary::new()));
        XPCObject::Dictionary(root)
    }

    #[tokio::test]
    async fn bounded_handshake_accepts_controlled_service_fixture() {
        let (socket, mut peer) = tokio::io::duplex(65536);
        let encoded = XPCMessage::new(None, Some(fixture()), None).encode(1).unwrap();
        // Synthetic HTTP/2 DATA on the existing root stream.
        let len = u32::try_from(encoded.len()).unwrap().to_be_bytes();
        let mut frame = vec![len[1], len[2], len[3], 0, 0, 0, 0, 0, 1];
        frame.extend(encoded);
        peer.write_all(&frame).await.unwrap();
        let handshake = RsdHandshake::new_bounded(socket).await.unwrap();
        assert_eq!(handshake.services["fixture.service"].port, 62078);
        assert_eq!(handshake.protocol_version, 7);
        let mut magic = [0; 24];
        peer.read_exact(&mut magic).await.unwrap();
        assert_eq!(&magic, b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n");
    }

    #[test]
    fn bounded_handshake_rejects_negative_protocol_version() {
        let mut data = fixture().to_plist();
        data.as_dictionary_mut().unwrap().insert("MessagingProtocolVersion".into(), plist::Value::Integer((-1i64).into()));
        assert!(RsdHandshake::from_handshake_data(data, true).is_err());
    }

    #[tokio::test]
    async fn bounded_handshake_future_can_be_dropped_without_spawned_work() {
        let (socket, mut peer) = tokio::io::duplex(65536);
        let mut future = Box::pin(RsdHandshake::new_bounded(socket));
        // Drive to the stalled read without sleeping or starting a detached task.
        std::future::poll_fn(|cx| {
            assert!(std::future::Future::poll(future.as_mut(), cx).is_pending());
            std::task::Poll::Ready(())
        }).await;
        drop(future);
        let mut outbound = Vec::new();
        peer.read_to_end(&mut outbound).await.unwrap();
        assert!(outbound.starts_with(b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n"));
        assert!(outbound.len() < 4096);
    }

    #[test]
    fn bounded_handshake_enforces_service_count() {
        let mut data = fixture().to_plist();
        let mut services = plist::Dictionary::new();
        for index in 0..1025 { services.insert(format!("fixture.{index}"), plist::Value::Boolean(true)); }
        data.as_dictionary_mut().unwrap().insert("Services".into(), plist::Value::Dictionary(services));
        assert!(RsdHandshake::from_handshake_data(data, true).is_err());
    }

}
