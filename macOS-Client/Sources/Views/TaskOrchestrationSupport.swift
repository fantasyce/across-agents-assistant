import SwiftUI

struct TaskStatusNotice {
    let icon: String
    let message: String
    let color: Color
}

struct TaskTheme {
    let colorScheme: ColorScheme

    var background: Color { AcrossTheme.canvasFill(for: colorScheme) }
    var headerBackground: Color { AcrossTheme.panelFill(for: colorScheme) }
    var panelBackground: Color { AcrossTheme.panelFill(for: colorScheme) }
    var cardBackground: Color { AcrossTheme.panelFill(for: colorScheme) }
    var fieldBackground: Color { AcrossTheme.recessedFill(for: colorScheme) }
    var hoverBackground: Color { AcrossTheme.hoverFill(for: colorScheme) }
    var subtleBackground: Color { AcrossTheme.panelFill(for: colorScheme) }
    var controlBackground: Color { AcrossTheme.recessedFill(for: colorScheme) }
    var divider: Color { AcrossTheme.separator(for: colorScheme) }
    var primaryText: Color { .primary }
    var strongText: Color { .primary }
    var bodyText: Color { .primary }
    var mutedText: Color { .secondary }
}

