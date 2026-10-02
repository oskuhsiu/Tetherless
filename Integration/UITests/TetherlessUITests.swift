// SPDX-License-Identifier: AGPL-3.0-only
import XCTest

/// Runs against the complete, unmodified production app in a fresh Simulator.
/// No account, pairing record, successful backend fixture or private swizzle.
final class TetherlessUITests: XCTestCase {
    @MainActor func testFirstSetupAndLocalNavigation() throws {
        continueAfterFailure = false
        let app = XCUIApplication()
        app.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        app.launch()
        addUIInterruptionMonitor(withDescription: "Notification permission") { alert in
            let deny = alert.buttons["Don’t Allow"]
            if deny.exists { deny.tap(); return true }
            return false
        }
        let springboard = XCUIApplication(bundleIdentifier: "com.apple.springboard")
        let deny = springboard.alerts.buttons["Don’t Allow"]
        if deny.waitForExistence(timeout: 8) { deny.tap() }
        let title = app.staticTexts["onboarding.title"]
        XCTAssertTrue(title.waitForExistence(timeout: 20), "Expected the actual first-launch onboarding")
        XCTAssertEqual(title.label, "Welcome to Tetherless")
        capture(app, "01-welcome")
        app.buttons["onboarding.next"].tap()
        XCTAssertTrue(app.buttons["onboarding.importPairing"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["onboarding.next"].isEnabled, "A fresh simulator has no pairing")
        app.buttons["onboarding.importPairing"].tap()
        let cancelImport = app.buttons["Cancel"].firstMatch
        XCTAssertTrue(cancelImport.waitForExistence(timeout: 10)); cancelImport.tap()
        XCTAssertTrue(app.buttons["onboarding.importPairing"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["onboarding.next"].isEnabled)
        // Kill/relaunch mid-wizard: persist navigation, not fake prerequisites.
        app.terminate(); app.launch()
        XCTAssertTrue(title.waitForExistence(timeout: 15))
        XCTAssertEqual(title.label, "Device pairing")
        XCTAssertFalse(app.buttons["onboarding.next"].isEnabled)
        capture(app, "01b-resumed-pairing")
        app.buttons["onboarding.later"].tap()
        XCTAssertTrue(app.buttons["onboarding.openVPN"].waitForExistence(timeout: 5))
        app.buttons["onboarding.next"].tap()
        XCTAssertTrue(app.buttons["onboarding.signIn"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["onboarding.next"].isEnabled, "No account was supplied")
        capture(app, "02-account-needed")
        app.buttons["onboarding.later"].tap()
        let consent = app.switches["onboarding.allowUnattended"]
        XCTAssertTrue(consent.waitForExistence(timeout: 5))
        XCTAssertEqual(consent.value as? String, "0", "Consent must not be silently enabled")
        XCTAssertTrue(app.buttons["onboarding.openShortcuts"].exists)
        capture(app, "03-automation-consent")
        app.buttons["onboarding.next"].tap()
        let readiness = app.staticTexts["onboarding.readiness"]
        XCTAssertTrue(readiness.waitForExistence(timeout: 5))
        XCTAssertEqual(readiness.label, "Setup is not finished", app.staticTexts["onboarding.readinessDetail"].label)
        XCTAssertFalse(app.staticTexts["You're All Set!"].exists)
        capture(app, "04-review-incomplete")
        app.buttons["onboarding.back"].tap()
        XCTAssertTrue(consent.waitForExistence(timeout: 5))
        XCTAssertEqual(consent.value as? String, "0")
        app.buttons["onboarding.next"].tap()
        app.buttons["onboarding.finish"].tap()
        dismissPairingPrompt(app)
        let renewal = app.tabBars.buttons["Auto Renewal"]
        XCTAssertTrue(renewal.waitForExistence(timeout: 15), "Dismissed wizard must lead to the real app")
        renewal.tap()
        let setup = app.buttons["renewal.openSetup"]
        XCTAssertTrue(revealRenewalControl(setup, in: app))
        setup.tap()
        XCTAssertTrue(app.tabBars.buttons["Settings"].isSelected)
        renewal.tap()
        let install = app.buttons["Install or manage an IPA"]
        XCTAssertTrue(revealRenewalControl(install, in: app)); install.tap()
        XCTAssertTrue(app.tabBars.buttons["My Apps"].isSelected)
        renewal.tap()
        let resume = app.buttons["renewal.resumeSetup"]
        XCTAssertTrue(revealRenewalControl(resume, in: app))
        resume.tap()
        XCTAssertTrue(title.waitForExistence(timeout: 10))
        XCTAssertEqual(title.label, "Review setup")
        XCTAssertEqual(app.staticTexts["onboarding.readiness"].label, "Setup is not finished", app.staticTexts["onboarding.readinessDetail"].label)
        app.buttons["onboarding.back"].tap()
        XCTAssertTrue(consent.waitForExistence(timeout: 5))
        XCTAssertEqual(consent.value as? String, "0")
        app.buttons["onboarding.next"].tap()
        app.buttons["onboarding.finish"].tap()
        XCTAssertTrue(renewal.waitForExistence(timeout: 10))
        capture(app, "05-auto-renewal")
        // A real relaunch must retain wizard dismissal without silently granting
        // consent or fabricating an observed successful background renewal.
        app.terminate(); app.launch()
        dismissPairingPrompt(app)
        XCTAssertTrue(renewal.waitForExistence(timeout: 15)); renewal.tap()
        XCTAssertFalse(title.exists)
        let enabled = app.switches["renewal.allowUnattended"]
        XCTAssertTrue(revealRenewalControl(enabled, in: app))
        XCTAssertEqual(enabled.value as? String, "0")
    }
    /// SwiftUI Form virtualizes offscreen rows. Waiting for an absent row
    /// cannot reveal it on the SE-sized test device: scroll the actual Form,
    /// then require the exact control to exist and be hittable before tapping.
    /// Return-scroll positions vary when switching tabs, so search both ways
    /// with a hard bound. Never tap a coordinate or silently skip an assertion.
    @MainActor private func revealRenewalControl(_ element: XCUIElement,
                                                 in app: XCUIApplication) -> Bool {
        guard app.tabBars.buttons["Auto Renewal"].isSelected,
              app.navigationBars["Auto Renewal"].waitForExistence(timeout: 5) else {
            capture(app, "failure-wrong-renewal-screen")
            return false
        }
        let form = app.collectionViews.firstMatch
        guard form.waitForExistence(timeout: 5) else {
            capture(app, "failure-missing-renewal-form")
            return false
        }
        if element.exists && element.isHittable { return true }
        for scrollDown in [false, true] {
            for _ in 0..<6 {
                if scrollDown { form.swipeDown() } else { form.swipeUp() }
                if element.exists && element.isHittable { return true }
            }
        }
        capture(app, "failure-unreachable-renewal-control")
        return false
    }
    @MainActor private func dismissPairingPrompt(_ app: XCUIApplication) {
        let prompt = app.alerts["Pairing File"]
        if prompt.waitForExistence(timeout: 5) { prompt.buttons["Cancel"].tap() }
    }
    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways; add(attachment)
    }
}
