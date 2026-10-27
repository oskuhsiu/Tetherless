// SPDX-License-Identifier: AGPL-3.0-only
import Foundation
import Testing
@testable import TetherlessCore
#if canImport(CoreData)
import CoreData
#endif

@Suite("Untrusted catalogs must not crash or silently choose a version")
struct CatalogImportSafetyTests {
    private func key(_ version: String = "1", build: String? = nil,
                     app: String = "test.app", source: String? = "test.source") -> CatalogVersionIdentity {
        .init(source: source, app: app, version: version, build: build)
    }
    @Test func rejectsTwoAndThreeIdenticalKeys() {
        for count in [2, 3] {
            #expect(throws: CatalogImportError.duplicateVersion) {
                try CatalogImportSafety.requireUniqueVersions(Array(repeating: key(), count: count))
            }
        }
    }
    @Test func nilAndEmptyBuildAreTheSameStoredKey() {
        #expect(throws: CatalogImportError.duplicateVersion) {
            try CatalogImportSafety.requireUniqueVersions([key(build: nil), key(build: "")])
        }
    }
    @Test func missingBuildIsNotTheLiteralNilString() throws {
        try CatalogImportSafety.requireUniqueVersions([key(), key(build: "nil")])
    }
    @Test func independentAppsSourcesAndBuildsRemainValid() throws {
        try CatalogImportSafety.requireUniqueVersions([
            key(), key("2"), key(build: "20"), key(app: "another.app"), key(source: "another.source")
        ])
    }
    @Test func compositeKeyDoesNotUseDelimiterConcatenation() throws {
        try CatalogImportSafety.requireUniqueVersions([key("1|2", build: "3"), key("1", build: "2|3")])
    }
    @Test func emptyIdentityFailsWithoutLeakingInput() {
        #expect(throws: CatalogImportError.invalidVersionRecord) {
            try CatalogImportSafety.requireUniqueVersions([key("")])
        }
        #expect(throws: CatalogImportError.invalidVersionRecord) {
            try CatalogImportSafety.requireUniqueVersions([key(app: "")])
        }
    }
    @Test func versionBudgetIsBounded() {
        #expect(throws: CatalogImportError.tooManyVersions) {
            try CatalogImportSafety.requireUniqueVersions((0...50_000).lazy.map { key(String($0)) })
        }
    }
    @Test func safeNSErrorSurvivesBridging() {
        let error = CatalogImportError.unresolvedConstraint as NSError
        #expect(error.domain == "org.tetherless.CatalogImport")
        #expect(error.code == 3)
        #expect(error.localizedRecoverySuggestion?.contains("Installed apps are not removed") == true)
        #expect(Set(error.userInfo.keys) == [NSLocalizedDescriptionKey, NSLocalizedRecoverySuggestionErrorKey])
    }

    #if canImport(CoreData)
    /// Use real Core Data and SQLite, not a mock save. Production preflight runs
    /// on the same inserted-object graph, including versions outside app.versions.
    @Test func rejectedChildGraphLeavesExistingSQLiteCatalogIntact() throws {
        let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }
        let entity = NSEntityDescription(); entity.name = "AppVersion"
        entity.managedObjectClassName = NSStringFromClass(NSManagedObject.self)
        entity.properties = ["sourceID", "appBundleID", "version", "buildVersion"].map { name in
            let property = NSAttributeDescription(); property.name = name
            property.attributeType = .stringAttributeType; property.isOptional = false
            return property
        }
        entity.uniquenessConstraints = [["sourceID", "appBundleID", "version", "buildVersion"]]
        let model = NSManagedObjectModel(); model.entities = [entity]
        let coordinator = NSPersistentStoreCoordinator(managedObjectModel: model)
        let store = try coordinator.addPersistentStore(ofType: NSSQLiteStoreType, configurationName: nil,
                                                       at: directory.appendingPathComponent("test.sqlite"))
        defer { try? coordinator.remove(store) }
        let parent = NSManagedObjectContext(concurrencyType: .privateQueueConcurrencyType)
        parent.persistentStoreCoordinator = coordinator
        try parent.performAndWait {
            insert("original", in: parent)
            try CatalogImportSafety.validateNewVersions(in: parent); try parent.save()
        }
        let child = NSManagedObjectContext(concurrencyType: .privateQueueConcurrencyType); child.parent = parent
        try child.performAndWait {
            insert("next", in: child); insert("next", in: child); insert("next", in: child)
            do {
                try CatalogImportSafety.validateNewVersions(in: child)
                Issue.record("Duplicate graph was accepted")
            } catch {
                #expect(error as? CatalogImportError == .duplicateVersion)
                child.rollback()
            }
            #expect(!child.hasChanges)
        }
        try parent.performAndWait {
            #expect(!parent.hasChanges)
            let rows = try parent.fetch(NSFetchRequest<NSManagedObject>(entityName: "AppVersion"))
            #expect(rows.count == 1)
            #expect(rows.first?.value(forKey: "version") as? String == "original")
        }
        // A valid next import is not poisoned by the previous child failure.
        try child.performAndWait {
            insert("valid-next", in: child)
            try CatalogImportSafety.validateNewVersions(in: child); try child.save()
        }
        try parent.performAndWait { try parent.save() }
        let reader = NSManagedObjectContext(concurrencyType: .privateQueueConcurrencyType)
        reader.persistentStoreCoordinator = coordinator
        try reader.performAndWait {
            let rows = try reader.fetch(NSFetchRequest<NSManagedObject>(entityName: "AppVersion"))
            #expect(Set(rows.compactMap { $0.value(forKey: "version") as? String }) == ["original", "valid-next"])
        }
    }
    private func insert(_ version: String, in context: NSManagedObjectContext) {
        let object = NSEntityDescription.insertNewObject(forEntityName: "AppVersion", into: context)
        object.setValue("test.source", forKey: "sourceID"); object.setValue("test.app", forKey: "appBundleID")
        object.setValue(version, forKey: "version"); object.setValue("", forKey: "buildVersion")
    }
    #endif
}
