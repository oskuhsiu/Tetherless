// SPDX-License-Identifier: AGPL-3.0-only
//! Read-only registered-device directory and fail-closed existing-only admission.
use crate::model::*;
use axum::http::StatusCode;
use isideload::dev::{
    developer_session::DeveloperSession,
    device_type::DeveloperDeviceType,
    devices::{DeveloperDevice, DevicesApi},
    teams::{DeveloperTeam, TeamsApi},
};
use serde::Serialize;
use std::{collections::HashSet, future::Future};

const MAX_TEAMS: usize = 128;
const MAX_DEVICES: usize = 1000;

fn upstream_error() -> ApiError {
    ApiError(StatusCode::BAD_GATEWAY, ErrorCode::AppleRequestFailed)
}

/// This test seam deliberately exposes reads only; it cannot register or enable devices.
pub(crate) trait DeviceDirectory {
    fn teams(&mut self) -> impl Future<Output = ApiResult<Vec<DeveloperTeam>>> + Send;
    fn devices(
        &mut self,
        team: &DeveloperTeam,
    ) -> impl Future<Output = ApiResult<Vec<DeveloperDevice>>> + Send;
}

impl DeviceDirectory for DeveloperSession {
    async fn teams(&mut self) -> ApiResult<Vec<DeveloperTeam>> {
        self.list_teams().await.map_err(|_| upstream_error())
    }
    async fn devices(&mut self, team: &DeveloperTeam) -> ApiResult<Vec<DeveloperDevice>> {
        self.list_devices(team, Some(DeveloperDeviceType::Ios))
            .await
            .map_err(|_| upstream_error())
    }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "camelCase")]
pub enum DeviceStatus {
    Active,
    Disabled,
    Unknown,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisteredDevice {
    pub udid: String,
    pub name: String,
    pub status: DeviceStatus,
    pub selectable: bool,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct RegisteredDevices {
    pub team_id: String,
    pub devices: Vec<RegisteredDevice>,
}

fn catalog(devices: Vec<DeveloperDevice>) -> ApiResult<Vec<RegisteredDevice>> {
    if devices.len() > MAX_DEVICES {
        return Err(upstream_error());
    }
    let mut seen = HashSet::new();
    devices
        .into_iter()
        .map(|device| {
            if !valid_udid(&device.device_number)
                || !seen.insert(device.device_number.to_ascii_lowercase())
            {
                return Err(upstream_error());
            }
            // Legacy QH65B2 statuses, independently documented by Fastlane:
            // spaceship/lib/spaceship/portal/device.rb at
            // 1912c0760355eebb5e90f643e6e77b74cf346e3b (blob 9a673c6f6d9e8b666539fbde32dc8bb8795fd900).
            // The pinned isideload type leaves status optional and uninterpreted.
            // Do not treat missing/new status values as evidence of eligibility.
            let status = match device.status.as_deref() {
                Some("c") => DeviceStatus::Active,
                Some("r") => DeviceStatus::Disabled,
                _ => DeviceStatus::Unknown,
            };
            Ok(RegisteredDevice {
                udid: device.device_number,
                name: device
                    .name
                    .filter(|name| safe_name(name))
                    .unwrap_or_else(|| "Registered device".into()),
                status,
                selectable: status == DeviceStatus::Active,
            })
        })
        .collect()
}

pub async fn list(
    directory: &mut impl DeviceDirectory,
    team_id: &str,
) -> ApiResult<RegisteredDevices> {
    if !valid_team_id(team_id) {
        return Err(invalid());
    }
    let teams = directory.teams().await?;
    if teams.len() > MAX_TEAMS {
        return Err(upstream_error());
    }
    let mut matching = teams.into_iter().filter(|team| team.team_id == team_id);
    let team = matching.next().ok_or_else(invalid)?;
    if matching.next().is_some() {
        return Err(upstream_error());
    }
    let devices = catalog(directory.devices(&team).await?)?;
    Ok(RegisteredDevices {
        team_id: team.team_id,
        devices,
    })
}

/// Call before certificate issuance and every other provisioning mutation.
/// An existing selection is re-read from the authenticated team's iOS directory.
pub async fn require_existing(
    directory: &mut impl DeviceDirectory,
    team: &DeveloperTeam,
    udid: &str,
) -> ApiResult<()> {
    if !valid_udid(udid) {
        return Err(invalid());
    }
    let devices = catalog(directory.devices(team).await?)?;
    if !devices
        .iter()
        .any(|device| device.selectable && device.udid.eq_ignore_ascii_case(udid))
    {
        return Err(ApiError(
            StatusCode::CONFLICT,
            ErrorCode::DeviceNotAvailable,
        ));
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn device(udid: &str, status: Option<&str>) -> DeveloperDevice {
        DeveloperDevice {
            name: Some("Synthetic device".into()),
            device_id: Some("PRIVATEPORTALID".into()),
            device_number: udid.into(),
            status: status.map(str::to_owned),
        }
    }
    fn team(id: &str) -> DeveloperTeam {
        DeveloperTeam {
            name: None,
            team_id: id.into(),
            r#type: None,
            status: None,
        }
    }
    struct Directory {
        teams: Vec<DeveloperTeam>,
        devices: Vec<DeveloperDevice>,
        queried: Vec<String>,
        fail: bool,
    }
    impl DeviceDirectory for Directory {
        async fn teams(&mut self) -> ApiResult<Vec<DeveloperTeam>> {
            if self.fail {
                return Err(upstream_error());
            }
            Ok(self.teams.clone())
        }
        async fn devices(&mut self, team: &DeveloperTeam) -> ApiResult<Vec<DeveloperDevice>> {
            self.queried.push(team.team_id.clone());
            if self.fail {
                return Err(upstream_error());
            }
            Ok(self.devices.clone())
        }
    }
    fn directory() -> Directory {
        Directory {
            teams: vec![team("SYNTHETIC")],
            devices: vec![device(&"a".repeat(40), Some("c"))],
            queried: Vec::new(),
            fail: false,
        }
    }
    #[tokio::test]
    async fn listing_uses_only_the_authenticated_team_and_discloses_bounded_fields() {
        let mut directory = directory();
        assert!(list(&mut directory, "OTHER").await.is_err());
        assert!(directory.queried.is_empty());
        assert!(list(&mut directory, "../invalid").await.is_err());
        let result = list(&mut directory, "SYNTHETIC").await.unwrap();
        assert_eq!(directory.queried, ["SYNTHETIC"]);
        let json = serde_json::to_value(result).unwrap();
        assert_eq!(json["devices"][0]["status"], "active");
        assert_eq!(json["devices"][0]["selectable"], true);
        assert!(json["devices"][0].get("deviceId").is_none());
        assert!(!json.to_string().contains("PRIVATEPORTALID"));
    }
    #[test]
    fn catalog_distinguishes_disabled_and_unknown_without_guessing_new_statuses() {
        for (raw, expected) in [
            (Some("c"), DeviceStatus::Active),
            (Some("r"), DeviceStatus::Disabled),
            (None, DeviceStatus::Unknown),
            (Some("ENABLED"), DeviceStatus::Unknown),
            (Some("processing"), DeviceStatus::Unknown),
        ] {
            let output = catalog(vec![device(&"0".repeat(40), raw)]).unwrap();
            assert_eq!(output[0].status, expected);
            assert_eq!(output[0].selectable, expected == DeviceStatus::Active);
        }
    }
    #[test]
    fn catalog_rejects_oversize_invalid_and_ambiguous_device_lists() {
        assert!(catalog(vec![device(&"0".repeat(40), Some("c")); MAX_DEVICES + 1]).is_err());
        assert!(catalog(vec![device("not-a-udid", Some("c"))]).is_err());
        assert!(
            catalog(vec![
                device(&"a".repeat(40), Some("c")),
                device(&"A".repeat(40), Some("r"))
            ])
            .is_err()
        );
        assert!(catalog(vec![]).unwrap().is_empty());
        let mut invalid_name = device(&"0".repeat(40), Some("c"));
        invalid_name.name = Some("do not log\nprivate data".into());
        assert_eq!(
            catalog(vec![invalid_name]).unwrap()[0].name,
            "Registered device"
        );
    }
    #[tokio::test]
    async fn existing_admission_rechecks_active_udid_and_never_registers() {
        let mut directory = directory();
        let selected_team = team("SYNTHETIC");
        require_existing(&mut directory, &selected_team, &"A".repeat(40))
            .await
            .unwrap();
        for status in [Some("r"), None, Some("unknown")] {
            directory.devices[0].status = status.map(str::to_owned);
            assert!(matches!(
                require_existing(&mut directory, &selected_team, &"a".repeat(40)).await,
                Err(ApiError(
                    StatusCode::CONFLICT,
                    ErrorCode::DeviceNotAvailable
                ))
            ));
        }
        directory.devices.clear();
        assert!(matches!(
            require_existing(&mut directory, &selected_team, &"a".repeat(40)).await,
            Err(ApiError(
                StatusCode::CONFLICT,
                ErrorCode::DeviceNotAvailable
            ))
        ));
        assert_eq!(directory.queried.len(), 5);
        // DeviceDirectory has no registration or enable operation, including in production.
    }
    #[tokio::test]
    async fn teams_and_upstream_failures_are_bounded_and_fail_closed() {
        let mut directory = directory();
        directory.teams = vec![team("SYNTHETIC"); MAX_TEAMS + 1];
        assert!(list(&mut directory, "SYNTHETIC").await.is_err());
        assert!(directory.queried.is_empty());
        directory.teams = vec![team("SYNTHETIC"); 2];
        assert!(list(&mut directory, "SYNTHETIC").await.is_err());
        directory.fail = true;
        assert!(matches!(
            list(&mut directory, "SYNTHETIC").await,
            Err(ApiError(
                StatusCode::BAD_GATEWAY,
                ErrorCode::AppleRequestFailed
            ))
        ));
    }
}
