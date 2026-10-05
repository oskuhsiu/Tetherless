// SPDX-License-Identifier: AGPL-3.0-only
import XCTest

final class RuntimePickerTests: XCTestCase {
    @MainActor func testCrossContainerSelection() throws {
        continueAfterFailure = false
        let producer = XCUIApplication(bundleIdentifier: "org.tetherless.testdocuments")
        producer.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        producer.launch()
        defer { producer.terminate() }
        capture(producer, "producer-launched")
        XCTAssertTrue(producer.staticTexts["fixture.documentReady"].waitForExistence(timeout: 10))
        XCTAssertFalse(producer.staticTexts["fixture.documentFailed"].exists)
        capture(producer, "producer-document-ready")
        producer.terminate()

        let recipient = XCUIApplication()
        recipient.launchArguments = ["-AppleLanguages", "(en)", "-AppleLocale", "en_US"]
        recipient.launch()
        defer { capture(recipient, "recipient-final"); recipient.terminate() }
        let open = recipient.buttons["runtime.open"]
        XCTAssertTrue(open.waitForExistence(timeout: 10))
        // These are two actual system presentations and actual system Cancel
        // actions, not a warm-up, an app-owned substitute or a callback fixture.
        for attempt in 1...2 {
            XCTAssertTrue(open.isEnabled); XCTAssertTrue(open.isHittable)
            open.tap()
            let cancel = recipient.buttons["Cancel"].firstMatch
            XCTAssertTrue(cancel.waitForExistence(timeout: 10)); XCTAssertTrue(cancel.isHittable)
            capture(recipient, "cancel-\(attempt)-before")
            cancel.tap()
            let returned = XCTNSPredicateExpectation(predicate: NSPredicate(format:
                "exists == true AND isEnabled == true AND isHittable == true"), object: open)
            XCTAssertEqual(XCTWaiter.wait(for: [returned], timeout: 5), .completed)
            XCTAssertEqual(recipient.staticTexts["runtime.outcome"].label, "cancelled")
            XCTAssertEqual(recipient.staticTexts["runtime.callbackCounts"].label,
                           Array(repeating: "1", count: attempt).joined(separator: ","))
            XCTAssertEqual(recipient.staticTexts["runtime.dismissed"].label, "true")
            XCTAssertEqual(recipient.staticTexts["runtime.violation"].label, "false")
            XCTAssertFalse(recipient.otherElements["Browse View (Picker)"].exists)
        }
        open.tap()
        let browse = recipient.buttons["Browse"].firstMatch
        XCTAssertTrue(browse.waitForExistence(timeout: 10)); XCTAssertTrue(browse.isHittable)
        browse.tap()
        tapDocumentItem("On My iPhone", in: recipient, documentCell: false)
        tapDocumentItem("Tetherless Test Documents", in: recipient, documentCell: true)
        tapDocumentItem("Tetherless-Invalid-Pairing.plist", in: recipient, documentCell: true)
        let outcome = recipient.staticTexts["runtime.outcome"]
        let dismissed = recipient.staticTexts["runtime.dismissed"]
        let terminal = XCTNSPredicateExpectation(predicate: NSPredicate(format:
            "exists == true AND label == %@", "true"), object: dismissed)
        // Keep the original ten-second deadline. No retries or subsequent grace wait.
        let observed = XCTWaiter.wait(for: [terminal], timeout: 10)
        let pickerVisible = recipient.otherElements["Browse View (Picker)"].exists
        capture(recipient, "after-single-file-activation")
        let attachment = XCTAttachment(string: "waitCompleted=\(observed == .completed); outcome=\(outcome.exists ? outcome.label : "not-visible"); pickerVisible=\(pickerVisible); productAccepted=false")
        attachment.name = "runtime-selection-result"; attachment.lifetime = .keepAlways; add(attachment)
        XCTAssertEqual(observed, .completed)
        XCTAssertEqual(outcome.label, "selectedFileURL")
        XCTAssertEqual(recipient.staticTexts["runtime.callbackCounts"].label, "1,1,1")
        XCTAssertEqual(recipient.staticTexts["runtime.dismissed"].label, "true")
        XCTAssertEqual(recipient.staticTexts["runtime.violation"].label, "false")
        XCTAssertFalse(pickerVisible)
        XCTAssertTrue(open.isEnabled); XCTAssertTrue(open.isHittable)
    }

    @MainActor private func tapDocumentItem(_ name: String, in app: XCUIApplication,
                                            documentCell: Bool) {
        // Same reviewed semantic-cell selector as the full product test. Never
        // try another descendant, coordinate, gesture or repeated activation.
        let stem = (name as NSString).deletingPathExtension
        let match = NSPredicate(format: "label == %@ OR label == %@ OR label BEGINSWITH %@ OR label BEGINSWITH %@",
                                name, stem, name + ",", stem + ",")
        let items = documentCell ? app.cells : app.descendants(matching: .any)
        let item = items.matching(match).firstMatch
        XCTAssertTrue(item.waitForExistence(timeout: 10))
        XCTAssertTrue(item.isEnabled); XCTAssertTrue(item.isHittable)
        capture(app, "before-semantic-activation")
        item.tap()
    }

    @MainActor private func capture(_ app: XCUIApplication, _ name: String) {
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = name; screenshot.lifetime = .keepAlways; add(screenshot)
        let hierarchy = XCTAttachment(string: app.debugDescription)
        hierarchy.name = name + "-hierarchy"; hierarchy.lifetime = .keepAlways; add(hierarchy)
    }
}
