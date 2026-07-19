#!/usr/bin/env python3
"""Fail when AAA's SwiftUI sources drift from the frontend handbook."""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VIEWS_ROOT = ROOT / "macOS-Client" / "Sources" / "Views"


@dataclass(frozen=True)
class Finding:
    path: Path
    line: int
    message: str


def line_number(source: str, offset: int) -> int:
    return source.count("\n", 0, offset) + 1


def find_pattern(
    findings: list[Finding],
    path: Path,
    source: str,
    pattern: str,
    message: str,
    *,
    flags: int = 0,
) -> None:
    for match in re.finditer(pattern, source, flags):
        findings.append(Finding(path, line_number(source, match.start()), message))


def audit_sources() -> list[Finding]:
    findings: list[Finding] = []
    swift_files = sorted(VIEWS_ROOT.rglob("*.swift"))

    for path in swift_files:
        source = path.read_text(encoding="utf-8")
        find_pattern(
            findings,
            path,
            source,
            r"\bDisclosureGroup\s*\(",
            "use MinimalDisclosureSection/MinimalDisclosureRow so the whole row is clickable",
        )
        find_pattern(
            findings,
            path,
            source,
            r"\b(?:Linear|Radial|Angular)Gradient\s*\(",
            "decorative gradients are outside the calm native visual language",
        )
        find_pattern(
            findings,
            path,
            source,
            r"\bMinimalWorkflowHeader\s*\(",
            "legacy page header usage must migrate to MinimalPageHeader and the shared content frame",
        )
        find_pattern(
            findings,
            path,
            source,
            r"Color\s*\(\s*hex:\s*\"#?(?:4d6bfe|007aff|0a84ff)\"\s*\)",
            "use AcrossTheme.accent instead of a page-local blue literal",
            flags=re.IGNORECASE,
        )
        find_pattern(
            findings,
            path,
            source,
            r"\.stroke(?:Border)?\s*\([^\n\)]*(?:AcrossTheme\.accent|Color\.blue|\.blue|systemBlue)",
            "blue outlines are forbidden; selected navigation uses a blue background only",
            flags=re.IGNORECASE,
        )

    page_contracts = {
        "UnifiedWorkView.swift": ("MinimalPageHeader", "minimalPageContentFrame"),
        "MinimalRunsOverviewView.swift": ("MinimalPageHeader", "minimalPageContentFrame"),
        "AutopilotWorkbenchView.swift": ("MinimalPageHeader", "minimalPageContentFrame"),
        "CapabilityProgressView.swift": ("MinimalPageHeader", "minimalPageContentFrame"),
        "EvidenceMemoryOperationsViews.swift": ("MinimalPageHeader", "minimalPageContentFrame"),
        "MinimalProjectWorkspaceView.swift": ("MinimalPageHeader", "minimalPageContentFrame"),
        "ModelSettingsView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
        "AgentCapabilitiesView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
        "PluginLifecycleView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
        "DevicesWorkersSettingsView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
        "MCPPreferencesView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
        "ToolPermissionsView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
        "StartupDiagnosticsView.swift": ("MinimalSettingsPageHeader", "minimalPageContentFrame"),
    }
    for filename, required_markers in page_contracts.items():
        path = VIEWS_ROOT / filename
        source = path.read_text(encoding="utf-8")
        for marker in required_markers:
            if marker not in source:
                findings.append(
                    Finding(path, 1, f"page contract requires {marker}")
                )

    disclosure_path = VIEWS_ROOT / "MinimalWorkflowComponents.swift"
    disclosure_source = disclosure_path.read_text(encoding="utf-8")
    disclosure_contract = (
        "struct MinimalDisclosureRow",
        ".contentShape(Rectangle())",
        ".accessibilityLabel(accessibilityLabel)",
        'Image(systemName: isExpanded ? "chevron.down" : "chevron.right")',
        "Spacer(minLength: 12)",
    )
    for marker in disclosure_contract:
        if marker not in disclosure_source:
            findings.append(
                Finding(disclosure_path, 1, f"shared disclosure contract is missing {marker}")
            )

    workflow_path = VIEWS_ROOT / "MinimalRunsOverviewView.swift"
    workflow_source = workflow_path.read_text(encoding="utf-8")
    if "onStartWork()" not in workflow_source:
        findings.append(Finding(workflow_path, 1, "workflow creation must route to the universal Work composer"))
    for forbidden in (
        "SimpleStartWorkflowView",
        "TaskNewTaskForm(",
        "runActionRow(",
        "destination = .quality",
        "destination = .release",
    ):
        if forbidden in workflow_source:
            findings.append(Finding(workflow_path, 1, "workflow must not expose preset or duplicate task composers"))

    loop_path = VIEWS_ROOT / "AutopilotWorkbenchView.swift"
    loop_source = loop_path.read_text(encoding="utf-8")
    workspace_start = loop_source.find("private func agentWorkspaceReadinessPanel")
    workspace_end = loop_source.find("private func summaryGrid", workspace_start)
    workspace_source = loop_source[workspace_start:workspace_end]
    if "AcrossTheme.panelFill" in workspace_source or "AcrossTheme.recessedFill" in workspace_source:
        findings.append(Finding(loop_path, 1, "the singleton Agent Workspace section must remain flat"))
    section_start = loop_source.find("private func sectionPanel")
    section_end = loop_source.find("private func summaryPairs", section_start)
    if "AcrossTheme.panelFill" not in loop_source[section_start:section_end]:
        findings.append(Finding(loop_path, 1, "repeated operational sections must render as peer cards"))
    section_source = loop_source[section_start:section_end]
    if "maxHeight: sectionCardHeight" not in section_source or "prefix(3)" not in section_source:
        findings.append(Finding(loop_path, 1, "operational cards require one fixed height and a bounded four-line content budget"))
    if "snapshot.agents.filter(\\.available)" not in workspace_source:
        findings.append(Finding(loop_path, 1, "Agent Workspace must hide unavailable local agents"))

    quality_path = VIEWS_ROOT / "QualityGateOperationsView.swift"
    quality_source = quality_path.read_text(encoding="utf-8")
    if "HSplitView" in quality_source:
        findings.append(Finding(quality_path, 1, "the code-quality workflow must use one calm content column, not nested left/right panes"))
    for marker in ("MinimalSectionHeader", "MinimalDisclosureSection", 'systemImage: "play.fill"'):
        if marker not in quality_source:
            findings.append(Finding(quality_path, 1, f"code-quality workflow is missing {marker}"))

    sidebar_path = VIEWS_ROOT / "OperationsWorkbenchSidebar.swift"
    sidebar_source = sidebar_path.read_text(encoding="utf-8")
    for forbidden in ("reviewCount", "navigationRow(.humanReview"):
        if forbidden in sidebar_source:
            findings.append(Finding(sidebar_path, 1, "review attention must use owning-surface dots, not a global review destination"))
    for marker in ("attentionSurfaces.contains(surface)", "Circle()"):
        if marker not in sidebar_source:
            findings.append(Finding(sidebar_path, 1, "owning surfaces with pending work require one quiet attention dot"))

    models_path = VIEWS_ROOT / "ModelSettingsView.swift"
    models_source = models_path.read_text(encoding="utf-8")
    if "unconfiguredLocalAgents" not in models_source or "showingUnconfiguredLocalAgents.toggle()" not in models_source:
        findings.append(Finding(models_path, 1, "Settings must retain configurable presets for unavailable local Agents"))

    capabilities_path = VIEWS_ROOT / "AgentCapabilitiesView.swift"
    capabilities_source = capabilities_path.read_text(encoding="utf-8")
    for marker in ("settingsViewModel.availableLocalAgents.map", "settingsViewModel.availableCloudLLMs.map"):
        if marker not in capabilities_source:
            findings.append(Finding(capabilities_path, 1, "Capabilities must list only ready local Agents and configured cloud models"))

    return sorted(findings, key=lambda item: (str(item.path), item.line, item.message))


def main() -> int:
    findings = audit_sources()
    if findings:
        print(f"Frontend design audit failed with {len(findings)} finding(s):")
        for finding in findings:
            relative = finding.path.relative_to(ROOT)
            print(f"- {relative}:{finding.line}: {finding.message}")
        return 1

    view_count = len(list(VIEWS_ROOT.rglob("*.swift")))
    print(f"Frontend design audit passed: {view_count} SwiftUI source files checked.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
