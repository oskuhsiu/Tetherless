// SPDX-License-Identifier: AGPL-3.0-only
mod apple;
mod certificates;
mod devices;
mod enrollment;
mod login_diagnostics;
mod model;
use login_diagnostics::{LoginDiagnostic, LoginFailureKind, LoginStage};

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
const ANISETTE_ORIGIN: &str = "https://mac-ani.jkcoxson.com";

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
    certificate_state: Mutex<certificates::CertificateState>,
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
        certificate_state: Mutex::new(certificates::CertificateState::default()),
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
        .route("/health", get(move || async move { Json(json!({"protocol":1,"appleAuthAvailable":true,"profileServiceAvailable":profile_service_available,"service":"tetherless-web-bootstrap", "accountBackend":"isideload", "accountBackendPin":"8ca39b6203263e539408986e546c42e7c1cc3699", "accountBackendPatch":"bounded-no-redirect-anisette-transport", "liveAppleAcceptance":false,"certificateLifecycle":1})) }))
        .route("/v1/device-enrollments", post(enrollment::create))
        .route("/v1/device-enrollments/{id}", get(enrollment::status).delete(enrollment::cancel))
        .route("/v1/device-enrollments/{id}/profile/{ticket}", get(enrollment::profile))
        .route("/v1/device-enrollments/{id}/callback", post(enrollment::callback))
        .route("/v1/sessions", post(start))
        .route("/v1/sessions/{id}", get(status).delete(cancel))
        .route("/v1/sessions/{id}/2fa", post(two_factor))
        .route("/v1/sessions/{id}/teams", get(teams))
        .route("/v1/sessions/{id}/teams/{team_id}/devices", get(registered_devices))
        .route("/v1/sessions/{id}/certificate", post(prepare_certificate))
        .route("/v1/sessions/{id}/teams/{team_id}/certificates", get(list_certificates))
        .route("/v1/sessions/{id}/teams/{team_id}/certificates/revoke", post(revoke_certificate))
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
            *session.view.lock().await = SessionView::login_failed(LoginDiagnostic::new(
                LoginStage::Task,
                LoginFailureKind::TaskFailed,
            ));
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
                diagnostic: None,
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
        )
        .map_err(|error| login_diagnostics::classify(LoginStage::AccountSetup, error))?;
        let mut account = AppleAccount::builder(&apple_id)
            .anisette_provider(provider)
            .err_429_retries(None)
            .build()
            .await
            .map_err(|error| login_diagnostics::classify(LoginStage::AccountSetup, error))?;
        account
            .login(password.as_str(), callback)
            .await
            .map_err(|error| login_diagnostics::classify(LoginStage::AppleLogin, error))?;
        DeveloperSession::from_account(&mut account)
            .await
            .map_err(|error| login_diagnostics::classify(LoginStage::DeveloperToken, error))
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
        Err(diagnostic) => {
            *session.view.lock().await = SessionView::login_failed(diagnostic);
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
            if code.len() == 6
                && code.bytes().all(|c| c.is_ascii_digit())
                && view
                    .challenge
                    .as_ref()
                    .is_some_and(|challenge| !challenge.unknown) =>
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
) -> Result<Json<serde_json::Value>, TeamsError> {
    let session = lookup(&app, &id, &headers).await?;
    let operation = async {
        let mut developer = session.developer.lock().await;
        let dev = developer
            .as_mut()
            .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
        let teams = dev.list_teams().await.map_err(TeamsError::upstream)?;
        Ok(Json(
            json!({"teams":teams.into_iter().map(|t| json!({"id":t.team_id,"name":t.name,"type":t.r#type,"status":t.status})).collect::<Vec<_>>()}),
        ))
    };
    teams_read(&session, UPSTREAM_TIMEOUT, operation).await
}

/// Preserve the original two-minute bound, cancellation and session lifetime.
/// The timeout is injectable only by local tests; clients cannot alter it.
async fn teams_read<T>(
    session: &Session,
    timeout: Duration,
    operation: impl std::future::Future<Output = Result<T, TeamsError>>,
) -> Result<T, TeamsError> {
    if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
        return Err(ApiError(StatusCode::GONE, ErrorCode::Expired).into());
    }
    if session.view.lock().await.state != "authenticated" {
        return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState).into());
    }
    let remaining = TTL.saturating_sub(session.created.elapsed());
    let result = tokio::select! {
        biased;
        _ = session.cancel.cancelled() => Err(ApiError(StatusCode::GONE, ErrorCode::Expired).into()),
        result = tokio::time::timeout(timeout.min(remaining), operation) =>
            result.unwrap_or_else(|_| Err(TeamsError::timeout())),
    };
    if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
        return Err(ApiError(StatusCode::GONE, ErrorCode::Expired).into());
    }
    result
}
/// Bounded read-only work does not extend a session or survive cancellation.
async fn authenticated_read<T>(
    session: &Session,
    operation: impl std::future::Future<Output = ApiResult<T>>,
) -> ApiResult<T> {
    if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
        return Err(ApiError(StatusCode::GONE, ErrorCode::Expired));
    }
    if session.view.lock().await.state != "authenticated" {
        return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
    }
    let remaining = TTL.saturating_sub(session.created.elapsed());
    let result = tokio::select! {
        biased;
        _ = session.cancel.cancelled() => Err(ApiError(StatusCode::GONE, ErrorCode::Expired)),
        result = tokio::time::timeout(UPSTREAM_TIMEOUT.min(remaining), operation) =>
            result.unwrap_or(Err(ApiError(StatusCode::GATEWAY_TIMEOUT, ErrorCode::AppleRequestFailed))),
    };
    if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
        return Err(ApiError(StatusCode::GONE, ErrorCode::Expired));
    }
    result
}

async fn registered_devices(
    State(app): State<Arc<App>>,
    Path((id, team_id)): Path<(String, String)>,
    headers: HeaderMap,
) -> ApiResult<Json<devices::RegisteredDevices>> {
    let session = lookup(&app, &id, &headers).await?;
    if !valid_team_id(&team_id) {
        return Err(invalid());
    }
    authenticated_read(&session, async {
        // Share the same lock as Team reads and provisioning; never race the
        // upstream developer session's mutable anisette/token state.
        let mut developer = session.developer.lock().await;
        if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
            return Err(ApiError(StatusCode::GONE, ErrorCode::Expired));
        }
        let dev = developer
            .as_mut()
            .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
        devices::list(dev, &team_id).await.map(Json)
    })
    .await
}

// Mutations use the same admission/deadline boundary as reads, but a timeout
// cannot be described as a known failure: Apple may already have accepted it.
async fn authenticated_mutation<T>(
    session: &Session,
    operation: impl std::future::Future<Output = ApiResult<T>>,
) -> ApiResult<T> {
    authenticated_read(session, operation)
        .await
        .map_err(|error| match error {
            ApiError(StatusCode::GATEWAY_TIMEOUT, ErrorCode::AppleRequestFailed) => ApiError(
                StatusCode::GATEWAY_TIMEOUT,
                ErrorCode::ProvisioningUncertain,
            ),
            // lookup already rejects expired sessions before admission. Once an
            // admitted operation might have dispatched, expiry/cancel cannot
            // establish that Apple did not commit it.
            ApiError(StatusCode::GONE, ErrorCode::Expired) => {
                ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain)
            }
            other => other,
        })
}

async fn prepare_certificate(
    State(app): State<Arc<App>>,
    Path(id): Path<String>,
    headers: HeaderMap,
    Json(input): Json<ProvisionRequest>,
) -> ApiResult<Json<certificates::CertificateOutput>> {
    let session = lookup(&app, &id, &headers).await?;
    let public_key = input.validate()?;
    authenticated_mutation(&session, async {
        // Shared across sessions and all mutations (including profile mutations).
        // The guards contain only public identifiers, never account credentials.
        let mut state = app.certificate_state.lock().await;
        let mut developer = session.developer.lock().await;
        let dev = developer
            .as_mut()
            .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
        certificates::prepare(dev, &mut state, &input, &public_key)
            .await
            .map(Json)
    })
    .await
}

async fn list_certificates(
    State(app): State<Arc<App>>,
    Path((id, team_id)): Path<(String, String)>,
    headers: HeaderMap,
) -> ApiResult<Json<certificates::CertificateCatalog>> {
    let session = lookup(&app, &id, &headers).await?;
    if !valid_team_id(&team_id) {
        return Err(invalid());
    }
    authenticated_read(&session, async {
        let mut state = app.certificate_state.lock().await;
        let mut developer = session.developer.lock().await;
        let dev = developer
            .as_mut()
            .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
        certificates::list(dev, &mut state, &id, &team_id)
            .await
            .map(Json)
    })
    .await
}

async fn revoke_certificate(
    State(app): State<Arc<App>>,
    Path((id, team_id)): Path<(String, String)>,
    headers: HeaderMap,
    Json(input): Json<certificates::RevokeRequest>,
) -> ApiResult<Json<serde_json::Value>> {
    let session = lookup(&app, &id, &headers).await?;
    if !valid_team_id(&team_id) {
        return Err(invalid());
    }
    input.validate()?;
    authenticated_mutation(&session, async {
        let mut state = app.certificate_state.lock().await;
        let mut developer = session.developer.lock().await;
        let dev = developer
            .as_mut()
            .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
        certificates::revoke(dev, &mut state, &id, &team_id, &input).await?;
        Ok(Json(
            json!({"revoked":true, "certificateId":input.certificate_id, "teamId":team_id}),
        ))
    })
    .await
}

async fn begin_profiles(
    session: &Session,
    fingerprint: [u8; 32],
) -> ApiResult<Option<ProvisionOutput>> {
    if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
        return Err(ApiError(StatusCode::GONE, ErrorCode::Expired));
    }
    let mut attempt = session.provision.lock().await;
    if let Some(existing) = attempt.as_ref() {
        if existing.fingerprint != fingerprint {
            return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
        }
        match &existing.result {
            Some(Ok(output)) => return Ok(Some(output.clone())),
            None => return Err(ApiError(StatusCode::CONFLICT, ErrorCode::Busy)),
            // This stage cannot issue certificates. Explicit retries read
            // existing resources before resuming profile preparation.
            Some(Err(_)) => {}
        }
    }
    if session.view.lock().await.state != "authenticated" {
        return Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState));
    }
    *attempt = Some(ProvisionAttempt {
        fingerprint,
        result: None,
    });
    Ok(None)
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
    if let Some(output) = begin_profiles(&session, fingerprint).await? {
        return Ok(Json(output));
    }
    // Own the operation independently of an HTTP disconnect. Repeated identical
    // requests return the stored result; they never issue a second certificate.
    let worker = session.clone();
    let (tx, rx) = tokio::sync::oneshot::channel();
    let operation_task = tokio::spawn(async move {
        let operation = async {
            let _team_mutations = app.certificate_state.lock().await;
            let mut developer = worker.developer.lock().await;
            if worker.cancel.is_cancelled() || worker.created.elapsed() >= TTL {
                return Err(ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain));
            }
            let dev = developer
                .as_mut()
                .ok_or(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))?;
            apple::provision(dev, &input, &public_key).await
        };
        tokio::select! {
            biased;
            _ = worker.cancel.cancelled() => Err(ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain)),
            result = tokio::time::timeout(UPSTREAM_TIMEOUT.min(TTL.saturating_sub(worker.created.elapsed())), operation) => result.unwrap_or(Err(ApiError(StatusCode::GATEWAY_TIMEOUT, ErrorCode::ProvisioningUncertain))),
        }
    });
    tokio::spawn(async move {
        let mut result = operation_task.await.unwrap_or(Err(ApiError(
            StatusCode::BAD_GATEWAY,
            ErrorCode::ProvisioningUncertain,
        )));
        if session.cancel.is_cancelled() || session.created.elapsed() >= TTL {
            result = Err(ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain));
        }
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
    fn synthetic_session(state: &'static str, age: Duration) -> Arc<Session> {
        let (tx, _) = mpsc::channel(1);
        Arc::new(Session {
            token: Zeroizing::new("synthetic-bearer".into()),
            created: Instant::now() - age,
            cancel: CancellationToken::new(),
            view: Mutex::new(SessionView::state(state)),
            developer: Mutex::new(None),
            two_factor: tx,
            provision: Mutex::new(None),
        })
    }
    #[tokio::test]
    async fn mutation_cancel_or_expiry_after_admission_never_reports_known_failure_or_success() {
        let session = synthetic_session("authenticated", Duration::ZERO);
        let cancel = session.cancel.clone();
        let result = authenticated_mutation(&session, async move {
            cancel.cancel();
            Ok::<_, ApiError>(())
        })
        .await;
        assert!(matches!(
            result,
            Err(ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain))
        ));
        let session = synthetic_session("authenticated", TTL - Duration::from_millis(50));
        let entered = std::sync::atomic::AtomicBool::new(false);
        let result = authenticated_mutation(&session, async {
            entered.store(true, std::sync::atomic::Ordering::SeqCst);
            std::future::pending::<ApiResult<()>>().await
        })
        .await;
        assert!(entered.load(std::sync::atomic::Ordering::SeqCst));
        assert!(matches!(
            result,
            Err(ApiError(StatusCode::GONE, ErrorCode::ProvisioningUncertain))
        ));
    }
    #[tokio::test]
    async fn failed_profile_stage_resumes_same_request_then_caches_success() {
        let session = synthetic_session("authenticated", Duration::ZERO);
        assert!(begin_profiles(&session, [1; 32]).await.unwrap().is_none());
        assert!(matches!(
            begin_profiles(&session, [1; 32]).await,
            Err(ApiError(_, ErrorCode::Busy))
        ));
        session.provision.lock().await.as_mut().unwrap().result = Some(Err(ApiError(
            StatusCode::BAD_GATEWAY,
            ErrorCode::ProfileMismatch,
        )));
        // This exact production admission path reopens ONLY the profile stage;
        // certificate issuance is no longer reachable from that stage.
        assert!(begin_profiles(&session, [1; 32]).await.unwrap().is_none());
        session.provision.lock().await.as_mut().unwrap().result = Some(Ok(ProvisionOutput {
            team_id: "SYNTHETIC".into(),
            certificate_der_base64: "public synthetic certificate".into(),
            certificate_serial: Some("ABC123".into()),
            certificate_reused: true,
            app_group_identifier: None,
            profiles: vec![],
            verification: "cmsSignatureAndMetadataOnly",
        }));
        let output = begin_profiles(&session, [1; 32]).await.unwrap().unwrap();
        assert_eq!(output.certificate_serial.as_deref(), Some("ABC123"));
        assert!(output.certificate_reused);
        assert!(matches!(
            begin_profiles(&session, [2; 32]).await,
            Err(ApiError(_, ErrorCode::WrongState))
        ));
    }
    #[tokio::test]
    async fn certificate_routes_preserve_bearer_origin_state_and_no_store() {
        use tower::ServiceExt;
        let prepare_body=json!({"consent":"register-device-app-ids-and-issue-certificate","teamId":"SYNTHETIC","certificateIntent":"createOrReuse","device":{"udid":"0000000000000000000000000000000000000000","name":"Synthetic"},"csrPem":include_str!("../tests/fixtures/request.pem"),"machineName":"Synthetic","apps":[{"bundleId":"org.example.synthetic","name":"Synthetic"}]}).to_string();
        let revoke_body=json!({"certificateId":"SYNTHETICID","certificateSerial":"ABC123","confirmationToken":"00000000-0000-4000-8000-000000000000","consent":"revoke-selected-development-certificate"}).to_string();
        for (method, path, body) in [
            ("POST", "/v1/sessions/id/certificate", prepare_body.as_str()),
            ("GET", "/v1/sessions/id/teams/SYNTHETIC/certificates", ""),
            (
                "POST",
                "/v1/sessions/id/teams/SYNTHETIC/certificates/revoke",
                revoke_body.as_str(),
            ),
        ] {
            for (token, origin, state, age, expected) in [
                (
                    false,
                    "http://127.0.0.1:8787",
                    "authenticated",
                    Duration::ZERO,
                    StatusCode::UNAUTHORIZED,
                ),
                (
                    true,
                    "https://evil.example",
                    "authenticated",
                    Duration::ZERO,
                    StatusCode::FORBIDDEN,
                ),
                (
                    true,
                    "http://127.0.0.1:8787",
                    "starting",
                    Duration::ZERO,
                    StatusCode::CONFLICT,
                ),
                (
                    true,
                    "http://127.0.0.1:8787",
                    "authenticated",
                    TTL,
                    StatusCode::GONE,
                ),
                (
                    true,
                    "http://127.0.0.1:8787",
                    "authenticated",
                    Duration::ZERO,
                    StatusCode::CONFLICT,
                ),
            ] {
                let app = test_app();
                app.sessions
                    .write()
                    .await
                    .insert("id".into(), synthetic_session(state, age));
                let mut request = axum::http::Request::builder()
                    .method(method)
                    .uri(path)
                    .header("host", "127.0.0.1:8787")
                    .header("origin", origin)
                    .header("content-type", "application/json");
                if token {
                    request = request.header("authorization", "Bearer synthetic-bearer");
                }
                let response = routes(app)
                    .oneshot(
                        request
                            .body(axum::body::Body::from(body.to_string()))
                            .unwrap(),
                    )
                    .await
                    .unwrap();
                assert_eq!(response.status(), expected, "{path}");
                assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
            }
        }
    }
    #[tokio::test]
    async fn teams_diagnostics_response_is_private_safe_and_timeout_is_distinct() {
        use rootcause::prelude::*;
        let error = TeamsError::upstream(
            report!(isideload::SideloadError::DeveloperError(
                1100,
                "SYNTHETIC_ACCOUNT_TOKEN_BODY".into()
            ))
            .context("SYNTHETIC_CONTEXT")
            .into(),
        );
        let response = error.into_response();
        assert_eq!(response.status(), StatusCode::BAD_GATEWAY);
        let body = axum::body::to_bytes(response.into_body(), 4096)
            .await
            .unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&body).unwrap(),
            json!({
                "error":"appleRequestFailed", "diagnostic": {
                    "stage":"developerTeams", "kind":"developerRejected", "upstream":"apple", "appleCode":1100
                }
            })
        );
        let session = synthetic_session("authenticated", Duration::ZERO);
        let error = teams_read(
            &session,
            Duration::ZERO,
            std::future::pending::<Result<(), TeamsError>>(),
        )
        .await
        .unwrap_err();
        let response = error.into_response();
        assert_eq!(response.status(), StatusCode::GATEWAY_TIMEOUT);
        let body = axum::body::to_bytes(response.into_body(), 4096)
            .await
            .unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&body).unwrap(),
            json!({
                "error":"appleRequestFailed", "diagnostic": {
                    "stage":"developerTeams", "kind":"upstreamTimeout", "upstream":"unknown"
                }
            })
        );
        assert_eq!(session.view.lock().await.state, "authenticated");
    }

    #[tokio::test]
    async fn teams_read_preserves_expiry_wrong_state_and_cancellation_without_diagnostics() {
        for (state, age, cancel, status, code) in [
            ("authenticated", TTL, false, StatusCode::GONE, "expired"),
            (
                "authenticated",
                Duration::ZERO,
                true,
                StatusCode::GONE,
                "expired",
            ),
            (
                "starting",
                Duration::ZERO,
                false,
                StatusCode::CONFLICT,
                "wrongState",
            ),
        ] {
            let session = synthetic_session(state, age);
            if cancel {
                session.cancel.cancel();
            }
            let error = teams_read(&session, UPSTREAM_TIMEOUT, async {
                panic!("inadmissible teams read must not execute");
                #[allow(unreachable_code)]
                Ok::<_, TeamsError>(())
            })
            .await
            .unwrap_err();
            let response = error.into_response();
            assert_eq!(response.status(), status);
            let body = axum::body::to_bytes(response.into_body(), 4096)
                .await
                .unwrap();
            assert_eq!(
                serde_json::from_slice::<serde_json::Value>(&body).unwrap(),
                json!({"error":code})
            );
        }
        let session = synthetic_session("authenticated", Duration::ZERO);
        let cancel = session.cancel.clone();
        let error = teams_read(&session, UPSTREAM_TIMEOUT, async move {
            cancel.cancel();
            Ok::<_, TeamsError>("late response must not escape")
        })
        .await
        .unwrap_err();
        assert!(matches!(
            error.error,
            ApiError(StatusCode::GONE, ErrorCode::Expired)
        ));
        assert!(error.diagnostic.is_none());
    }

    #[tokio::test]
    async fn teams_waiting_read_is_cancelled_and_dropped_not_retried() {
        let session = synthetic_session("authenticated", Duration::ZERO);
        let (entered_tx, entered_rx) = tokio::sync::oneshot::channel();
        let worker = session.clone();
        let task = tokio::spawn(async move {
            teams_read(&worker, UPSTREAM_TIMEOUT, async {
                entered_tx.send(()).unwrap();
                std::future::pending::<Result<(), TeamsError>>().await
            })
            .await
        });
        entered_rx.await.unwrap();
        session.cancel.cancel();
        let error = task.await.unwrap().unwrap_err();
        assert!(matches!(
            error.error,
            ApiError(StatusCode::GONE, ErrorCode::Expired)
        ));
        assert!(error.diagnostic.is_none());
    }

    #[tokio::test]
    async fn teams_route_preserves_authentication_status_codes_and_no_store() {
        use tower::ServiceExt;
        let app = test_app();
        app.sessions
            .write()
            .await
            .insert("id".into(), synthetic_session("starting", Duration::ZERO));
        for (id, token, expected, code) in [
            (
                "absent",
                "synthetic-bearer",
                StatusCode::NOT_FOUND,
                "notFound",
            ),
            ("id", "wrong", StatusCode::UNAUTHORIZED, "unauthorized"),
            ("id", "synthetic-bearer", StatusCode::CONFLICT, "wrongState"),
        ] {
            let request = axum::http::Request::builder()
                .uri(format!("/v1/sessions/{id}/teams"))
                .header("host", "127.0.0.1:8787")
                .header(header::AUTHORIZATION, format!("Bearer {token}"))
                .body(axum::body::Body::empty())
                .unwrap();
            let response = routes(app.clone()).oneshot(request).await.unwrap();
            assert_eq!(response.status(), expected);
            assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
            let body = axum::body::to_bytes(response.into_body(), 4096)
                .await
                .unwrap();
            assert_eq!(
                serde_json::from_slice::<serde_json::Value>(&body).unwrap(),
                json!({"error":code})
            );
        }
    }

    #[tokio::test]
    async fn unknown_two_factor_rejects_code_without_consuming_challenge() {
        let app = test_app();
        let mut session = synthetic_session("awaitingTwoFactor", Duration::ZERO);
        let (tx, mut rx) = mpsc::channel(1);
        Arc::get_mut(&mut session).unwrap().two_factor = tx;
        session.view.lock().await.challenge = Some(Challenge {
            sms: false,
            unknown: true,
            retry: true,
            numbers: vec![],
            selected_number_id: None,
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
        assert!(matches!(
            two_factor(
                State(app.clone()),
                Path("id".into()),
                headers.clone(),
                Json(TwoFactorRequest::SubmitCode {
                    code: "123456".into()
                })
            )
            .await,
            Err(ApiError(StatusCode::BAD_REQUEST, ErrorCode::InvalidRequest))
        ));
        assert!(matches!(
            rx.try_recv(),
            Err(mpsc::error::TryRecvError::Empty)
        ));
        assert_eq!(session.view.lock().await.state, "awaitingTwoFactor");
        assert_eq!(
            two_factor(
                State(app.clone()),
                Path("id".into()),
                headers.clone(),
                Json(TwoFactorRequest::SendToDevices)
            )
            .await
            .unwrap(),
            StatusCode::ACCEPTED
        );
        assert!(matches!(
            rx.try_recv().unwrap(),
            TwoFactorCallbackResponse::SendToDevices
        ));
        assert_eq!(session.view.lock().await.state, "starting");
        // Simulate the subsequent callback after a method was selected.
        *session.view.lock().await = SessionView {
            state: "awaitingTwoFactor",
            error: None,
            diagnostic: None,
            challenge: Some(Challenge {
                sms: false,
                unknown: false,
                retry: false,
                numbers: vec![],
                selected_number_id: None,
            }),
        };
        assert_eq!(
            two_factor(
                State(app),
                Path("id".into()),
                headers,
                Json(TwoFactorRequest::SubmitCode {
                    code: "123456".into()
                })
            )
            .await
            .unwrap(),
            StatusCode::ACCEPTED
        );
        assert!(matches!(
            rx.try_recv().unwrap(),
            TwoFactorCallbackResponse::SubmitCode(_)
        ));
    }
    #[tokio::test]
    async fn registered_device_route_requires_bearer_state_and_origin_without_network() {
        use tower::ServiceExt;
        let app = test_app();
        let session = synthetic_session("starting", Duration::ZERO);
        app.sessions
            .write()
            .await
            .insert("id".into(), session.clone());
        for (token, origin, team, expected) in [
            (None, None, "SYNTHETIC", StatusCode::UNAUTHORIZED),
            (
                Some("Bearer wrong"),
                None,
                "SYNTHETIC",
                StatusCode::UNAUTHORIZED,
            ),
            (
                Some("Bearer synthetic-bearer"),
                Some("https://wrong.example"),
                "SYNTHETIC",
                StatusCode::FORBIDDEN,
            ),
            (
                Some("Bearer synthetic-bearer"),
                None,
                "SYNTHETIC",
                StatusCode::CONFLICT,
            ),
            (
                Some("Bearer synthetic-bearer"),
                None,
                "INVALID-TEAM",
                StatusCode::BAD_REQUEST,
            ),
        ] {
            let mut request = axum::http::Request::builder()
                .uri(format!("/v1/sessions/id/teams/{team}/devices"))
                .header("host", "127.0.0.1:8787");
            if let Some(token) = token {
                request = request.header(header::AUTHORIZATION, token);
            }
            if let Some(origin) = origin {
                request = request.header(header::ORIGIN, origin);
            }
            let response = routes(app.clone())
                .oneshot(request.body(axum::body::Body::empty()).unwrap())
                .await
                .unwrap();
            assert_eq!(response.status(), expected);
            assert_eq!(response.headers()[header::CACHE_CONTROL], "no-store");
        }
        *session.view.lock().await = SessionView::state("authenticated");
        session.cancel.cancel();
        let mut headers = HeaderMap::new();
        headers.insert(
            header::AUTHORIZATION,
            HeaderValue::from_static("Bearer synthetic-bearer"),
        );
        assert!(matches!(
            registered_devices(State(app), Path(("id".into(), "SYNTHETIC".into())), headers).await,
            Err(ApiError(StatusCode::GONE, ErrorCode::Expired))
        ));
    }
    #[tokio::test]
    async fn authenticated_read_does_not_start_or_return_after_cancel_or_expiry() {
        let session = synthetic_session("authenticated", Duration::ZERO);
        session.cancel.cancel();
        assert!(matches!(
            authenticated_read(&session, async {
                panic!("read must not run");
                #[allow(unreachable_code)]
                Ok::<_, ApiError>(())
            })
            .await,
            Err(ApiError(StatusCode::GONE, ErrorCode::Expired))
        ));
        let expired = synthetic_session("authenticated", TTL);
        assert!(matches!(
            authenticated_read(&expired, async {
                panic!("expired read must not run");
                #[allow(unreachable_code)]
                Ok::<_, ApiError>(())
            })
            .await,
            Err(ApiError(StatusCode::GONE, ErrorCode::Expired))
        ));
        let session = synthetic_session("authenticated", Duration::ZERO);
        let cancelled = session.clone();
        assert!(matches!(
            authenticated_read(&session, async move {
                cancelled.cancel.cancel();
                Ok("must not escape cancellation")
            })
            .await,
            Err(ApiError(StatusCode::GONE, ErrorCode::Expired))
        ));
    }
    #[tokio::test]
    async fn authenticated_read_can_be_cancelled_while_waiting_on_serialized_work() {
        let session = synthetic_session("authenticated", Duration::ZERO);
        let guard = session.developer.lock().await;
        let worker = session.clone();
        let (started, waiting) = tokio::sync::oneshot::channel();
        let task = tokio::spawn(async move {
            authenticated_read(&worker, async {
                let _ = started.send(());
                let _guard = worker.developer.lock().await;
                panic!("cancelled directory read must not acquire the upstream session");
                #[allow(unreachable_code)]
                Ok::<_, ApiError>(())
            })
            .await
        });
        waiting.await.unwrap();
        session.cancel.cancel();
        assert!(matches!(
            task.await.unwrap(),
            Err(ApiError(StatusCode::GONE, ErrorCode::Expired))
        ));
        drop(guard);
        assert!(session.developer.try_lock().is_ok());
    }
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
            certificate_state: Mutex::new(certificates::CertificateState::default()),
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
            certificate_state: Mutex::new(certificates::CertificateState::default()),
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
    async fn failed_profiles_can_resume_but_changed_or_running_requests_are_rejected() {
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
                Err(ApiError(StatusCode::CONFLICT, ErrorCode::WrongState))
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
