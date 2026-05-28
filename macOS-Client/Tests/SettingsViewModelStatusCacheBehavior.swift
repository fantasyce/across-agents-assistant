import Combine

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

@main
struct SettingsViewModelStatusCacheBehavior {
    @MainActor
    static func main() {
        let vm = SettingsViewModel(bootstrapOnInit: false, loadPersisted: false)
        vm.localAgents = [.localAgent, .hermes, .claude]
        vm.cloudLLMs = [.deepSeek, .miniMax]
        vm.apiKeyStatusCache = [:]

        var publishCount = 0
        let cancellable = vm.objectWillChange.sink { _ in
            publishCount += 1
        }

        vm.applyBackendKeyStatuses(["deepseek": "configured", "minimax": "configured"])

        assert(vm.availableCloudLLMs.map(\.id) == ["deepseek", "minimax"], "backend key statuses should expose configured cloud LLMs")
        assert(vm.visibleAgentIds == ["deepseek", "minimax"], "visible agents should include configured cloud LLMs immediately")
        assert(vm.availabilityBootstrapState == .loading, "backend key statuses alone should not finish startup availability")
        assert(!vm.shouldShowRightSidebar, "right sidebar should stay hidden until full availability bootstrap completes")
        assert(publishCount > 0, "applying backend key statuses should publish UI updates")

        vm.completeBackendReadyAvailabilityBootstrap()
        assert(vm.availabilityBootstrapState == .ready, "startup availability should become ready after backend keys are refreshed without waiting for local agent detection")
        assert(vm.shouldShowRightSidebar, "right sidebar should appear once startup availability is complete and cloud LLMs are configured")

        cancellable.cancel()
        print("SettingsViewModelStatusCacheBehavior passed")
    }
}
