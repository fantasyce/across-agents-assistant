import Foundation
import Testing
@testable import AcrossAgentsAssistantClient

struct RuntimeBoundaryBehaviorTests {
    @Test
    func productModeIgnoresProtectedAcrossHomeOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-home", isDirectory: true)
            .path
        let protected = "\(home)/Documents/projects/across"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_HOME": protected
        ]

        let root = RuntimeBoundary.safeAcrossRoot(environment: env)

        #expect(root.path == "\(home)/.across")
        #expect(!root.path.contains("Documents"))
    }

    @Test
    func productModePreservesSimilarlyNamedAcrossHomeOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-adjacent-home", isDirectory: true)
            .path
        let adjacent = "\(home)/DocumentsArchive/across"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_HOME": adjacent
        ]

        let root = RuntimeBoundary.safeAcrossRoot(environment: env)

        #expect(root.path == adjacent)
    }

    @Test
    func productModeExpandsTildeAcrossHomeWithEnvironmentHome() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-tilde-home", isDirectory: true)
            .path
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_HOME": "~/safe-across"
        ]

        let root = RuntimeBoundary.safeAcrossRoot(environment: env)

        #expect(root.path == "\(home)/safe-across")
    }

    @Test
    func productModePreservesNonUserDocumentsDirectoryOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-non-user-home", isDirectory: true)
            .path
        let nonUserDocuments = "/tmp/Documents/across"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_HOME": nonUserDocuments
        ]

        let root = RuntimeBoundary.safeAcrossRoot(environment: env)

        #expect(root.path == nonUserDocuments)
    }

    @Test
    func developerModePreservesProtectedAcrossHomeOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-dev-home", isDirectory: true)
            .path
        let protected = "\(home)/Documents/projects/across"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_DEVELOPER_MODE": "1",
            "ACROSS_HOME": protected
        ]

        let root = RuntimeBoundary.safeAcrossRoot(environment: env)

        #expect(root.path == protected)
    }

    @Test
    func productModeRejectsProtectedBackendDirectoryOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-backend-home", isDirectory: true)
            .path
        let backend = "\(home)/Documents/projects/across-agents-assistant/backend"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_BACKEND_DIR": backend
        ]

        let override = RuntimeBoundary.safeBackendProjectDirectoryOverride(environment: env, bundledBackendAvailable: true)

        #expect(override == nil)
    }

    @Test
    func developerModeAllowsProtectedBackendDirectoryOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-backend-dev-home", isDirectory: true)
            .path
        let backend = "\(home)/Documents/projects/across-agents-assistant/backend"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_DEVELOPER_MODE": "1",
            "ACROSS_AGENTS_BACKEND_DIR": backend
        ]

        let override = RuntimeBoundary.safeBackendProjectDirectoryOverride(environment: env, bundledBackendAvailable: true)

        #expect(override?.path == backend)
    }

    @Test
    func developerModeExpandsTildeBackendDirectoryWithEnvironmentHome() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-backend-tilde-home", isDirectory: true)
            .path
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_DEVELOPER_MODE": "1",
            "ACROSS_AGENTS_BACKEND_DIR": "~/Documents/projects/across-agents-assistant/backend"
        ]

        let override = RuntimeBoundary.safeBackendProjectDirectoryOverride(environment: env, bundledBackendAvailable: true)

        #expect(override?.path == "\(home)/Documents/projects/across-agents-assistant/backend")
    }

    @Test
    func productModeIgnoresProtectedAppHomeOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-app-home", isDirectory: true)
            .path
        let protected = "\(home)/Documents/projects/across-agents-assistant-data"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_HOME": protected
        ]

        let root = RuntimeBoundary.safeAppHome(environment: env, bundledBackendAvailable: true)

        #expect(root.path == "\(home)/.across/data/across-agents-assistant")
        #expect(RuntimeBoundary.hasAllowedAppHomeOverride(environment: env, bundledBackendAvailable: true) == false)
        #expect(!root.path.contains("Documents"))
    }

    @Test
    func developerModePreservesProtectedAppHomeOverride() {
        let home = URL(fileURLWithPath: NSTemporaryDirectory())
            .appendingPathComponent("aaa-runtime-boundary-app-dev-home", isDirectory: true)
            .path
        let protected = "\(home)/Documents/projects/across-agents-assistant-data"
        let env = [
            "HOME": home,
            "ACROSS_AGENTS_PRODUCT_MODE": "1",
            "ACROSS_AGENTS_DEVELOPER_MODE": "1",
            "ACROSS_AGENTS_HOME": protected
        ]

        let root = RuntimeBoundary.safeAppHome(environment: env, bundledBackendAvailable: true)

        #expect(root.path == protected)
        #expect(RuntimeBoundary.hasAllowedAppHomeOverride(environment: env, bundledBackendAvailable: true))
    }
}
