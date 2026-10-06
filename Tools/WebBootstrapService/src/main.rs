// SPDX-License-Identifier: AGPL-3.0-only
mod apple;
mod enrollment;
mod model;

use axum::{
    Json, Router,
    extract::{DefaultBodyLimit, Path, Request, State},
    http::{HeaderMap, HeaderValue, Method, StatusCode, header},
    middleware::{self, Next},
    response::{IntoResponse, Response},
    routing::{get, post},
};
use isideload::{
    anisette::remote_v3::RemoteV3AnisetteProvider,
    auth::apple_account::{AppleAccount, TwoFactorCallbackResponse},
    dev::{developer_session::DeveloperSession, teams::TeamsApi},
    util::storage::InMemoryStorage,
};
use model::*;
use serde_json::json;
use std::{
    collections::HashMap,
    net::SocketAddr,
    sync::Arc,
    time::{Duration, Instant},
};
use subtle::ConstantTimeEq;
use tokio::sync::{Mutex, RwLock, mpsc};
use tokio_util::sync::CancellationToken;
use tower_http::{cors::CorsLayer, services::ServeDir, set_header::SetResponseHeaderLayer};
use uuid::Uuid;
use zeroize::Zeroizing;

const TTL: Duration = Duration::from_secs(600);
const MAX_SESSIONS: usize = 8;
const UPSTREAM_TIMEOUT: Duration = Duration::from_secs(120);
// Explicit endpoint pin. It cannot be selected from a request, URL or account.
const ANISETTE_ORIGIN: &str = "https://ani.stikstore.app";

struct Session {
    token: Zeroizing<String>,
    created: Instant,
    cancel: CancellationToken,
    view: Mutex<SessionView>,
    developer: Mutex<Option<DeveloperSession>>,
    two_factor: mpsc::Sender<TwoFactorCallbackResponse>,
    // A started mutation is never retried automatically after uncertain failure.
    provision: Mutex<Option<ProvisionAttempt>>,
}
struct ProvisionAttempt {
    fingerprint: [u8; 32],
    result: Option<ApiResult<ProvisionOutput>>,
}
struct App {
    sessions: RwLock<HashMap<String, Arc<Session>>>,
    last_start: Mutex<Option<Instant>>,
    enrollments: RwLock<HashMap<String, Arc<enrollment::Enrollment>>>,
    last_enrollment_start: Mutex<Option<Instant>>,
    allowed_origin: String,
    allowed_host: String,
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    // Do not install tracing subscribers or request-body/access logging.
    std::panic::set_hook(Box::new(|_| {
        eprintln!("Bootstrap task failed; private diagnostic payload omitted")
    }));
    rustls::crypto::ring::default_provider()
        .install_default()
        .map_err(|_| "TLS provider setup failed")?;
    isideload::init().map_err(|_| "Apple client initialization failed")?;
    let bind: SocketAddr = std::env::var("TETHERLESS_BIND")
        .unwrap_or_else(|_| "127.0.0.1:8787".into())
        .parse()?;
    if !bind.ip().is_loopback() {
        return Err("Only loopback binding is supported; use a local HTTPS reverse proxy".into());
    }
    let origin =
        std::env::var("FRONTEND_ORIGIN").unwrap_or_else(|_| "http://127.0.0.1:8787".into());
    validate_origin(&origin)?;
    let host = std::env::var("TETHERLESS_PUBLIC_HOST").unwrap_or_else(|_| bind.to_string());
    if host.contains('/') || host.contains('@') || host.chars().any(char::is_control) {
        return Err("Invalid public host".into());
    }
    let app = Arc::new(App {
        sessions: RwLock::new(HashMap::new()),
        last_start: Mutex::new(None),
        enrollments: RwLock::new(HashMap::new()),
        last_enrollment_start: Mutex::new(None),
        allowed_origin: origin,
        allowed_host: host,
    });
    let cleanup = app.clone();
    tokio::spawn(async move {
        let mut ticks = tokio::time::interval(Duration::from_secs(5));
        loop {
            ticks.tick().await;
            cleanup
                .enrollments
                .write()
                .await
                .retain(|_, record| record.created.elapsed() < enrollment::ENROLLMENT_TTL);
            cleanup.sessions.write().await.retain(|_, session| {
                if session.created.elapsed() >= TTL {
                    session.cancel.cancel();
                    false
                } else {
                    true
                }
            });
        }
    });
    let listener = tokio::net::TcpListener::bind(bind).await?;
    eprintln!(
        "Tetherless bootstrap service listening on loopback; live account use requires explicit browser actions"
    );
    axum::serve(listener, routes(app.clone()))
        .with_graceful_shutdown(async move {
            let _ = tokio::signal::ctrl_c().await;
            for session in app
                .sessions
                .write()
                .await
                .drain()
                .map(|(_, session)| session)
            {
                session.cancel.cancel();
            }
        })
        .await?;
    Ok(())
}

fn validate_origin(origin: &str) -> Result<(), &'static str> {
    let uri: axum::http::Uri = origin.parse().map_err(|_| "Invalid FRONTEND_ORIGIN")?;
    if uri.path() != "/" || uri.query().is_some() || uri.authority().is_none() {
        return Err("FRONTEND_ORIGIN must contain only scheme and authority");
    }
    let host = uri.host().unwrap_or("");
    if uri.authority().is_some_and(|a| a.as_str().contains('@')) {
        return Err("Origin may not contain credentials");
    }
    match uri.scheme_str() {
        Some("https") => Ok(()),
        Some("http") if matches!(host, "127.0.0.1" | "localhost" | "[::1]") => Ok(()),
        _ => Err("Passwords require HTTPS; HTTP is permitted only for loopback development"),
    }
}

fn routes(app: Arc<App>) -> Router {
    let origin = HeaderValue::from_str(&app.allowed_origin).expect("origin validated at startup");
    let profile_service_available = app.allowed_origin.starts_with("https://");
    Router::new()
        .route("/health", get(move || async move { Json(json!({"protocol":1,"appleAuthAvailable":true,"profileServiceAvailable":profile_service_available,"service":"tetherless-web-bootstrap", "accountBackend":"isideload", "accountBackendPin":"dd442588370060b8776b1276a1acd717b6668b26", "liveAppleAcceptance":false})) }))
        .route("/v1/device-enrollments", post(enrollment::create))
        .route("/v1/device-enrollments/{id}", get(enrollment::status).delete(enrollment::cancel))
        .route("/v1/device-enrollments/{id}/profile/{ticket}", get(enrollment::profile))
        .route("/v1/device-enrollments/{id}/callback", post(enrollment::callback))
        .route("/v1/sessions", post(start))
        .route("/v1/sessions/{id}", get(status).delete(cancel))
        .route("/v1/sessions/{id}/2fa", post(two_factor))
        .route("/v1/sessions/{id}/teams", get(teams))
        .route("/v1/sessions/{id}/provision", post(provision))
        .fallback_service(ServeDir::new(std::env::var("TETHERLESS_FRONTEND_DIR").unwrap_or_else(|_| "../../WebBootstrap/dist".into())))
        .layer(DefaultBodyLimit::max(32 * 1024))
        .layer(CorsLayer::new().allow_origin(origin).allow_methods([Method::GET, Method::POST, Method::DELETE])
            .allow_headers([header::CONTENT_TYPE, header::AUTHORIZATION]))
        .layer(middleware::from_fn_with_state(app.clone(), guard))
        .layer(SetResponseHeaderLayer::overriding(header::CACHE_CONTROL, HeaderValue::from_static("no-store")))
        .layer(SetResponseHeaderLayer::overriding(header::X_CONTENT_TYPE_OPTIONS, HeaderValue::from_static("nosniff")))
        .with_state(app)
}

async fn guard(State(app): State<Arc<App>>, req: Request, next: Next) -> Response {
    let host = req
        .headers()
        .get(header::HOST)
        .and_then(|h| h.to_str().ok());
    let origin = req
        .headers()
        .get(header::ORIGIN)
        .and_then(|h| h.to_str().ok());
    let callback_post = req.method() == Method::POST
        && origin.is_none()
        && req
            .uri()
            .path()
            .strip_prefix("/v1/device-enrollments/")
            .is_some_and(|tail| {
                let parts: Vec<_> = tail.split('/').collect();
                parts.len() == 2 && Uuid::parse_str(parts[0]).is_ok() && parts[1] == "callback"
            });
    if host != Some(app.allowed_host.as_str())
        || origin.is_some_and(|s| s != app.allowed_origin)
        || (req.method() != Method::GET
            && !callback_post
            && origin != Some(app.allowed_origin.as_str()))
    {
        return ApiError(StatusCode::FORBIDDEN, ErrorCode::OriginRejected).into_response();
    }
    next.run(req).await
}

async fn lookup(app: &App, id: &str, headers: &HeaderMap) -> ApiResult<Arc<Session>> {
    let session = app
        .sessions
        .read()
        .await
        .get(id)
        .cloned()
        .ok_or(ApiError(StatusCode::NOT_FOUND, ErrorCode::NotFound))?;
    let supplied = headers
        .get(header::AUTHORIZATION)
        .and_then(|h| h.to_str().ok())
        .and_then(|s| s.strip_prefix("Bearer "))
        .unwrap_or("");
    if !bool::from(session.token.as_bytes().ct_eq(supplied.as_bytes())) {
        return Err(ApiError(StatusCode::UNAUTHORIZED, ErrorCode::Unauthorized));
    }
    if session.created.elapsed() >= TTL || session.cancel.is_cancelled() {
        session.cancel.cancel();
        return Err(ApiError(StatusCode::GONE, ErrorCode::Expired));
    }
    Ok(session)
}

async fn start(
    State(app): State<Arc<App>>,
    Json(input): Json<StartRequest>,
) -> ApiResult<(StatusCode, Json<serde_json::Value>)> {
    let password = Zeroizing::new(input.password);
    if input.apple_id.trim().is_empty()
        || input.apple_id.len() > 254
        || input.apple_id.chars().any(char::is_control)
        || password.is_empty()
        || password.len() > 1024
    {
        return Err(invalid());
    }
    let mut last = app.last_start.lock().await;
    if last.is_some_and(|t| t.elapsed() < Duration::from_secs(5)) {
        return Err(ApiError(StatusCode::TOO_MANY_REQUESTS, ErrorCode::Busy));
    }
    let mut sessions = app.sessions.write().await;
    if sessions.len() >= MAX_SESSIONS {
        return Err(ApiError(StatusCode::TOO_MANY_REQUESTS, ErrorCode::Busy));
    }
    *last = Some(Instant::now());
    let id = Uuid::new_v4().to_string();
    // Two independent UUIDs: 244 random bits, separate from the public session ID.
    let token = format!("{}{}", Uuid::new_v4().simple(), Uuid::new_v4().simple());
    let (tx, rx) = mpsc::channel(1);
    let session = Arc::new(Session {
        token: Zeroizing::new(token.clone()),
        created: Instant::now(),
        cancel: CancellationToken::new(),
        view: Mutex::new(SessionView::state("starting")),
        developer: Mutex::new(None),
        two_factor: tx,
        provision: Mutex::new(None),
    });
    sessions.insert(id.clone(), session.clone());
    let login_session = session.clone();
    let task = tokio::spawn(login(login_session, input.apple_id, password, rx));
    tokio::spawn(async move {
        if task.await.is_err() && !session.cancel.is_cancelled() {
            *session.view.lock().await = SessionView::failed(ErrorCode::AppleAuthenticationFailed);
        }
    });
    Ok((
        StatusCode::ACCEPTED,
        Json(
            json!({"sessionId":id,"sessionToken":token,"state":"starting","expiresInSeconds":TTL.as_secs()}),
        ),
    ))
}

async fn login(
    session: Arc<Session>,
    apple_id: String,
    password: Zeroizing<String>,
    rx: mpsc::Receiver<TwoFactorCallbackResponse>,
) {
    let receiver = Arc::new(Mutex::new(rx));
    let callback_session = session.clone();
    let callback = move |params: isideload::auth::apple_account::TwoFactorCallbackParams| {
        let session = callback_session.clone();
        let receiver = receiver.clone();
        async move {
            *session.view.lock().await = SessionView {
                state: "awaitingTwoFactor",
                error: None,
                challenge: Some(Challenge {
                    sms: params.sms,
                    unknown: params.unknown,
                    retry: params.last_error.is_some(),
                    selected_number_id: params.selected_number_id,
                    numbers: params
                        .numbers
                        .into_iter()
                        .map(|p| PhoneChoice {
                            id: p.id,
                            last_two_digits: p.last_two_digits,
                        })
                        .collect(),
                }),
            };
            let answer = tokio::select! {
                _ = session.cancel.cancelled() => TwoFactorCallbackResponse::Abort,
                answer = async { receiver.lock().await.recv().await } => answer.unwrap_or(TwoFactorCallbackResponse::Abort),
            };
            *session.view.lock().await = SessionView::state("starting");
            Ok(answer)
        }
    };
    let operation = async {
        let provider = RemoteV3AnisetteProvider::new(
            ANISETTE_ORIGIN,
            Box::new(InMemoryStorage::new()),
            "0".into(),
        )?;
        let mut account = AppleAccount::builder(&apple_id)
            .anisette_provider(provider)
            .err_429_retries(None)
            .login(password.as_str(), callback)
            .await?;
        DeveloperSession::from_account(&mut account).await
    };
    let result = tokio::select! {
        _ = session.cancel.cancelled() => return,
        _ = tokio::time::sleep(TTL) => { session.cancel.cancel(); return; },
        result = operation => result,
    };
    // The borrowed password is no longer needed and is zeroed on drop.
    drop(password);
    match result {
        Ok(dev) => {
            *session.developer.lock().await = Some(dev);
            *session.view.lock().await = SessionView::state("authenticated");
        }
        Err(_) => {
            *session.view.lock().await = SessionView::failed(ErrorCode::AppleAuthenticationFailed);
        }
    }
}

async fn status(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
) -> ApiResult<Json<SessionView>> {
    let session = lookup(&app, &id, &headers).await?;
    let view = session.view.lock().await.clone();
    Ok(Json(view))
}
async fn cancel(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
) -> ApiResult<StatusCode> {
    let session = lookup(&app, &id, &headers).await?;
    session.cancel.cancel();
    app.sessions.write().await.remove(&id);
    Ok(StatusCode::NO_CONTENT)
}
async fn two_factor(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
    Json(input): Json<TwoFactorRequest>,
) -> ApiResult<StatusCode> {
    let session = lookup(&app, &id, &headers).await?;
    let mut view = session.view.lock().await;
    if view.state != "awaitingTwoFactor" {
        return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
    }
    let answer = match input {
        TwoFactorRequest::SubmitCode { code }
            if code.len() == 6 && code.bytes().all(|c| c.is_ascii_digit()) =>
        {
            TwoFactorCallbackResponse::SubmitCode(code)
        }
        TwoFactorRequest::SendSms { number_id }
            if view
                .challenge
                .as_ref()
                .is_some_and(|c| c.numbers.iter().any(|p| p.id == number_id)) =>
        {
            TwoFactorCallbackResponse::SendSms(number_id)
        }
        TwoFactorRequest::SendToDevices => TwoFactorCallbackResponse::SendToDevices,
        TwoFactorRequest::ResendCode => TwoFactorCallbackResponse::ResendCode,
        _ => return Err(invalid()),
    };
    session
        .two_factor
        .try_send(answer)
        .map_err(|_| ApiError(StatusCode::CONFLICT, ErrorCode::Busy))?;
    *view = SessionView::state("starting");
    Ok(StatusCode::ACCEPTED)
}
async fn teams(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
) -> ApiResult<Json<serde_json::Value>> {
    let session = lookup(&app, &id, &headers).await?;
    let operation = async {
        let mut developer = session.developer.lock().await;
        let dev = developer
            .as_mut()
            .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
        let teams = dev
            .list_teams()
            .await
            .map_err(|_| ApiError(StatusCode::BAD_GATEWAY, ErrorCode::AppleRequestFailed))?;
        Ok(Json(
            json!({"teams":teams.into_iter().map(|t| json!({"id":t.team_id,"name":t.name,"type":t.r#type,"status":t.status})).collect::<Vec<_>>()}),
        ))
    };
    tokio::select! {
        _ = session.cancel.cancelled() => Err(ApiError(StatusCode::GONE, ErrorCode::Expired)),
        result = tokio::time::timeout(UPSTREAM_TIMEOUT, operation) => result.map_err(|_| ApiError(StatusCode::GATEWAY_TIMEOUT, ErrorCode::AppleRequestFailed))?,
    }
}
async fn provision(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
    Json(input): Json<ProvisionRequest>,
) -> ApiResult<Json<ProvisionOutput>> {
    let session = lookup(&app, &id, &headers).await?;
    let public_key = input.validate()?;
    let fingerprint = input.fingerprint()?;
    {
        let mut attempt = session.provision.lock().await;
        if let Some(existing) = attempt.as_ref() {
            if existing.fingerprint != fingerprint {
                return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
            }
            return existing
                .result
                .clone()
                .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::Busy))?
                .map(Json);
        }
        if session.view.lock().await.state != "authenticated" {
            return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
        }
        *attempt = Some(ProvisionAttempt {
            fingerprint,
            result: None,
        });
    }
    // Own the operation independently of an HTTP disconnect. Repeated identical
    // requests return the stored result; they never issue a second certificate.
    let worker = session.clone();
    let (tx, rx) = tokio::sync::oneshot::channel();
    let operation_task = tokio::spawn(async move {
        let operation = async {
            let mut developer = worker.developer.lock().await;
            let dev = developer
                .as_mut()
                .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
            apple::provision(dev, &input, &public_key).await
        };
        tokio::select! {
            _ = worker.cancel.cancelled() => Err(ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain)),
            result = tokio::time::timeout(UPSTREAM_TIMEOUT, operation) => result.unwrap_or(Err(ApiError(StatusCode::GATEWAY_TIMEOUT, ErrorCode::ProvisioningUncertain))),
        }
    });
    tokio::spawn(async move {
        let result = operation_task.await.unwrap_or(Err(ApiError(
            StatusCode::BAD_GATEWAY,
            ErrorCode::ProvisioningUncertain,
        )));
        if let Some(attempt) = session.provision.lock().await.as_mut() {
            attempt.result = Some(result.clone());
        }
        let _ = tx.send(result);
    });
    rx.await
        .map_err(|_| ApiError(StatusCode::BAD_GATEWAY, ErrorCode::ProvisioningUncertain))?
        .map(Json)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn passwords_are_not_accepted_for_plaintext_remote_origins() {
        for s in [
            "http://example.com",
            "https://example.com/path",
            "https://example.com?x=1",
            "https://user@example.com",
            "file:///tmp/index.html",
        ] {
            assert!(validate_origin(s).is_err());
        }
        for s in [
            "https://bootstrap.example.com",
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ] {
            assert!(validate_origin(s).is_ok());
        }
    }
    #[tokio::test]
    async fn unknown_session_does_not_contact_apple() {
        let app = App {
            sessions: RwLock::new(HashMap::new()),
            last_start: Mutex::new(None),
            enrollments: RwLock::new(HashMap::new()),
            last_enrollment_start: Mutex::new(None),
            allowed_origin: "https://example.com".into(),
            allowed_host: "example.com".into(),
        };
        assert!(matches!(
            lookup(&app, "unknown", &HeaderMap::new()).await,
            Err(ApiError(StatusCode::NOT_FOUND, _))
        ));
    }
    fn test_app() -> Arc<App> {
        Arc::new(App {
            sessions: RwLock::new(HashMap::new()),
            last_start: Mutex::new(None),
            enrollments: RwLock::new(HashMap::new()),
            last_enrollment_start: Mutex::new(None),
            allowed_origin: "http://127.0.0.1:8787".into(),
            allowed_host: "127.0.0.1:8787".into(),
        })
    }
    #[tokio::test]
    async fn hostile_origin_rejected_before_login_or_network() {
        use tower::ServiceExt;
        let app = test_app();
        let request = axum::http::Request::builder()
            .method("POST")
            .uri("/v1/sessions")
            .header("host", "127.0.0.1:8787")
            .header("origin", "https://evil.example")
            .header("content-type", "application/json")
            .body(axum::body::Body::from(
                r#"{"appleId":"fake","password":"synthetic"}"#,
            ))
            .unwrap();
        let result = routes(app.clone()).oneshot(request).await.unwrap();
        assert_eq!(result.status(), StatusCode::FORBIDDEN);
        assert!(app.sessions.read().await.is_empty());
    }
    #[tokio::test]
    async fn missing_origin_rejected_before_login_or_network() {
        use tower::ServiceExt;
        let app = test_app();
        let request = axum::http::Request::builder()
            .method("POST")
            .uri("/v1/sessions")
            .header("host", "127.0.0.1:8787")
            .header("content-type", "application/json")
            .body(axum::body::Body::from(
                r#"{"appleId":"fake","password":"synthetic"}"#,
            ))
            .unwrap();
        assert_eq!(
            routes(app.clone()).oneshot(request).await.unwrap().status(),
            StatusCode::FORBIDDEN
        );
        assert!(app.sessions.read().await.is_empty());
    }
    #[tokio::test]
    async fn session_needs_separate_bearer_and_expires() {
        let app = test_app();
        let (tx, _rx) = mpsc::channel(1);
        let session = Arc::new(Session {
            token: Zeroizing::new("synthetic-bearer".into()),
            created: Instant::now(),
            cancel: CancellationToken::new(),
            view: Mutex::new(SessionView::state("starting")),
            developer: Mutex::new(None),
            two_factor: tx,
            provision: Mutex::new(None),
        });
        app.sessions
            .write()
            .await
            .insert("public-id".into(), session.clone());
        assert!(matches!(
            lookup(&app, "public-id", &HeaderMap::new()).await,
            Err(ApiError(StatusCode::UNAUTHORIZED, _))
        ));
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer synthetic-bearer"),
        );
        assert!(lookup(&app, "public-id", &headers).await.is_ok());
        session.cancel.cancel();
        assert!(matches!(
            lookup(&app, "public-id", &headers).await,
            Err(ApiError(StatusCode::GONE, _))
        ));
    }
    #[tokio::test]
    async fn uncertain_or_running_provision_is_never_reissued() {
        // Synthetic local state only: no Apple session/transport is installed.
        let request = || {
            serde_json::from_value::<ProvisionRequest>(json!({
                "consent":"register-device-app-ids-and-issue-certificate","teamId":"SYNTHETIC",
                "device":{"udid":"0000000000000000000000000000000000000000","name":"Synthetic"},
                "csrPem":include_str!("../tests/fixtures/request.pem"),"machineName":"Synthetic",
                "apps":[{"bundleId":"org.example.synthetic","name":"Synthetic"}]
            }))
            .unwrap()
        };
        let fingerprint = request().fingerprint().unwrap();
        let app = test_app();
        let (tx, _rx) = mpsc::channel(1);
        let session = Arc::new(Session {
            token: Zeroizing::new("synthetic-bearer".into()),
            created: Instant::now(),
            cancel: CancellationToken::new(),
            view: Mutex::new(SessionView::state("authenticated")),
            developer: Mutex::new(None),
            two_factor: tx,
            provision: Mutex::new(Some(ProvisionAttempt {
                fingerprint,
                result: Some(Err(ApiError(
                    StatusCode::GATEWAY_TIMEOUT,
                    ErrorCode::ProvisioningUncertain,
                ))),
            })),
        });
        app.sessions
            .write()
            .await
            .insert("id".into(), session.clone());
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer synthetic-bearer"),
        );
        for _ in 0..2 {
            assert!(matches!(
                provision(
                    State(app.clone()),
                    Path("id".into()),
                    headers.clone(),
                    Json(request())
                )
                .await,
                Err(ApiError(
                    StatusCode::GATEWAY_TIMEOUT,
                    ErrorCode::ProvisioningUncertain
                ))
            ));
        }
        let mut changed = request();
        changed.machine_name = "Changed".into();
        assert!(matches!(
            provision(
                State(app.clone()),
                Path("id".into()),
                headers.clone(),
                Json(changed)
            )
            .await,
            Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))
        ));
        session.provision.lock().await.as_mut().unwrap().result = None;
        assert!(matches!(
            provision(State(app), Path("id".into()), headers, Json(request())).await,
            Err(ApiError(StatusCode::CONFLICT, ErrorCode::Busy))
        ));
    }
}
