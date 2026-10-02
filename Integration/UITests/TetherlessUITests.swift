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
        XCTAssertEqual(readiness.label, "Setup is not finished")
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
        XCTAssertTrue(setup.waitForExistence(timeout: 10))
        setup.tap()
        XCTAssertTrue(app.tabBars.buttons["Settings"].isSelected)
        renewal.tap()
        let install = app.buttons["Install or manage an IPA"]
        XCTAssertTrue(install.waitForExistence(timeout: 5)); install.tap()
        XCTAssertTrue(app.tabBars.buttons["My Apps"].isSelected)
        renewal.tap()
        capture(app, "05-auto-renewal")
        // A real relaunch must retain wizard dismissal without silently granting
        // consent or fabricating an observed successful background renewal.
        app.terminate(); app.launch()
        dismissPairingPrompt(app)
        XCTAssertTrue(renewal.waitForExistence(timeout: 15)); renewal.tap()
        XCTAssertFalse(title.exists)
        let enabled = app.switches["renewal.allowUnattended"]
        if !enabled.isHittable { app.swipeUp() }
        XCTAssertTrue(enabled.waitForExistence(timeout: 5))
        XCTAssertEqual(enabled.value as? String, "0")
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
