"""Minimal static analyzer for .NET Framework -> .NET Core migration targeting detection.
Read-only: never writes to, builds, or executes anything in the scanned repository -- it only
parses .csproj/.config XML and file presence, and greps .cs file text. No MSBuild, no dotnet
CLI, no network."""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from findings import Finding

LEGACY_MSBUILD_NS = "http://schemas.microsoft.com/developer/msbuild/2003"

# Framework-only assemblies with no direct .NET Core equivalent (or one requiring a real
# rewrite, not a mechanical port). Prefix-matched against <Reference Include="..."/>.
INCOMPATIBLE_ASSEMBLY_PREFIXES = (
    "System.Web",
    "System.Windows.Forms",
    "System.Drawing",
    "System.ServiceModel",
    "System.EnterpriseServices",
    "System.Web.Services",
    "System.Workflow",
)

_finding_counter = 0


def _next_id() -> str:
    global _finding_counter
    _finding_counter += 1
    return f"FIND-{_finding_counter:03d}"


def _local_tag(elem: ET.Element) -> str:
    tag = elem.tag
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _rel(path: Path, repo_root: Path) -> str:
    return path.relative_to(repo_root).as_posix()


def _find_usage_sites(project_dir: Path, repo_root: Path, namespace_prefix: str) -> list[str]:
    """Every .cs file under the project directory whose text mentions the namespace, whether
    via a `using` directive or a fully-qualified reference -- a real fix needs these paths in
    scope, not just the .csproj where the assembly reference happens to be declared. A plain
    substring/word-boundary match, not a real C# parse: false positives (e.g. a comment) are
    the safe direction here, since they widen scope rather than narrow it."""
    pattern = re.compile(r"\b" + re.escape(namespace_prefix) + r"\b")
    sites = []
    for cs_path in sorted(project_dir.rglob("*.cs")):
        if "bin" in cs_path.parts or "obj" in cs_path.parts:
            continue
        try:
            content = cs_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if pattern.search(content):
            sites.append(_rel(cs_path, repo_root))
    return sites


def _is_legacy_project(root: ET.Element) -> bool:
    return root.tag.startswith(f"{{{LEGACY_MSBUILD_NS}}}") or root.get("Sdk") is None


def analyze_project(csproj_path: Path, repo_root: Path) -> list[Finding]:
    findings: list[Finding] = []
    tree = ET.parse(csproj_path)
    root = tree.getroot()
    rel_csproj = _rel(csproj_path, repo_root)
    legacy = _is_legacy_project(root)

    if legacy:
        findings.append(Finding(
            id=_next_id(),
            category="project-format",
            severity="high",
            affected_paths=[rel_csproj],
            description="Non-SDK-style project file (legacy MSBuild XML format). Must be "
                        "converted to SDK-style before the project can be built with the "
                        "modern dotnet CLI on any platform.",
            remediation_tag="retarget-sdk-style-project",
            evidence={"root_tag": root.tag},
        ))

    for elem in root.iter():
        local = _local_tag(elem)
        if local in ("TargetFrameworkVersion", "TargetFramework", "TargetFrameworks") and elem.text:
            findings.append(Finding(
                id=_next_id(),
                category="target-framework",
                severity="medium" if legacy else "low",
                affected_paths=[rel_csproj],
                description=f"Project targets '{elem.text.strip()}'.",
                remediation_tag="retarget-sdk-style-project" if legacy else None,
                evidence={"element": local, "value": elem.text.strip()},
            ))

    packages_config = csproj_path.parent / "packages.config"
    if packages_config.exists():
        findings.append(Finding(
            id=_next_id(),
            category="package-management",
            severity="medium",
            affected_paths=[rel_csproj, _rel(packages_config, repo_root)],
            description="packages.config-based package management detected; needs conversion "
                        "to PackageReference before the project can restore with the modern "
                        "dotnet CLI.",
            remediation_tag="migrate-packages-config-to-package-reference",
            evidence={},
        ))

    incompatible_refs: dict[str, list[str]] = {}
    for elem in root.iter():
        if _local_tag(elem) != "Reference":
            continue
        include = elem.get("Include", "")
        assembly_name = include.split(",", 1)[0].strip()
        for prefix in INCOMPATIBLE_ASSEMBLY_PREFIXES:
            if assembly_name == prefix or assembly_name.startswith(prefix + "."):
                incompatible_refs.setdefault(prefix, []).append(assembly_name)
                break

    for prefix, assemblies in sorted(incompatible_refs.items()):
        usage_sites = _find_usage_sites(csproj_path.parent, repo_root, prefix)
        findings.append(Finding(
            id=_next_id(),
            category="incompatible-api",
            severity="high",
            affected_paths=[rel_csproj, *usage_sites],
            description=f"References {prefix}-family assemblies with no direct .NET Core "
                        f"equivalent: {sorted(set(assemblies))}. Requires a real rewrite, not "
                        f"a mechanical port. {len(usage_sites)} source file(s) actually "
                        f"reference this namespace and are in scope for the fix, not just the "
                        f"project file's reference declaration.",
            remediation_tag="replace-incompatible-api",
            evidence={"assemblies": sorted(set(assemblies)), "usage_site_count": len(usage_sites)},
        ))

    return findings


def analyze_config_files(repo_root: Path) -> list[Finding]:
    findings = []
    for config_path in sorted(repo_root.rglob("*.config")):
        if config_path.name not in ("App.config", "Web.config", "web.config"):
            continue
        if "bin" in config_path.parts or "obj" in config_path.parts:
            continue
        findings.append(Finding(
            id=_next_id(),
            category="config-format",
            severity="low",
            affected_paths=[_rel(config_path, repo_root)],
            description=f"Legacy XML configuration file ({config_path.name}); .NET Core "
                        f"favors appsettings.json plus the Options pattern.",
            remediation_tag="modernize-config-file",
            evidence={},
        ))
    return findings


def analyze_repo(repo_root: Path) -> list[Finding]:
    global _finding_counter
    _finding_counter = 0

    findings: list[Finding] = []
    for csproj_path in sorted(repo_root.rglob("*.csproj")):
        if "bin" in csproj_path.parts or "obj" in csproj_path.parts:
            continue
        findings.extend(analyze_project(csproj_path, repo_root))

    findings.extend(analyze_config_files(repo_root))
    return findings
