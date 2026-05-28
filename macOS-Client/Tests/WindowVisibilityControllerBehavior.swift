final class FakeWindowApp: WindowApplicationControlling {
    var isHidden = false
    var windows: [FakeWindow] = []
    var hideCallCount = 0
    var unhideCallCount = 0
    var activateCallCount = 0
    var requestNewWindowCallCount = 0

    func hide() {
        hideCallCount += 1
    }

    func unhide() {
        unhideCallCount += 1
    }

    func activate() {
        activateCallCount += 1
    }

    func requestNewWindow() {
        requestNewWindowCallCount += 1
    }
}

final class FakeWindow: WindowRepresenting {
    var isVisible: Bool
    var isMiniaturized: Bool
    var didOrderFront = false
    var didDeminiaturize = false

    init(isVisible: Bool, isMiniaturized: Bool) {
        self.isVisible = isVisible
        self.isMiniaturized = isMiniaturized
    }

    func makeKeyAndOrderFront() {
        didOrderFront = true
        isVisible = true
    }

    func deminiaturize() {
        didDeminiaturize = true
        isMiniaturized = false
    }
}

func assert(_ condition: @autoclosure () -> Bool, _ message: String) {
    if !condition() {
        fatalError(message)
    }
}

func testToggleHidesWhenAnyMainWindowIsVisible() {
    let app = FakeWindowApp()
    app.windows = [FakeWindow(isVisible: true, isMiniaturized: false)]

    WindowVisibilityController.toggle(app)

    assert(app.hideCallCount == 1, "visible app should hide")
    assert(app.activateCallCount == 0, "visible app should not activate")
    assert(!app.windows[0].didOrderFront, "visible window should not be reordered")
}

func testToggleShowsExistingWindowWhenAppIsHidden() {
    let app = FakeWindowApp()
    app.isHidden = true
    app.windows = [FakeWindow(isVisible: false, isMiniaturized: false)]

    WindowVisibilityController.toggle(app)

    assert(app.unhideCallCount == 1, "hidden app should unhide")
    assert(app.activateCallCount == 1, "hidden app should activate")
    assert(app.windows[0].didOrderFront, "hidden app should order reusable window front")
    assert(app.requestNewWindowCallCount == 0, "hidden app should not request new window when one exists")
}

func testToggleRequestsNewWindowWhenNoReusableWindowExists() {
    let app = FakeWindowApp()

    WindowVisibilityController.toggle(app)

    assert(app.requestNewWindowCallCount == 1, "missing window should request new window")
    assert(app.activateCallCount == 1, "missing window should activate app")
}

@main
struct WindowVisibilityControllerBehavior {
    static func main() {
        testToggleHidesWhenAnyMainWindowIsVisible()
        testToggleShowsExistingWindowWhenAppIsHidden()
        testToggleRequestsNewWindowWhenNoReusableWindowExists()
        print("WindowVisibilityControllerBehavior passed")
    }
}
