#!/usr/bin/env python3
"""
Dependency Version Checker and Update Tracker
Checks current versions of Python libraries and external compilers
against latest available versions
"""

import json
import subprocess
import sys
from datetime import datetime

import requests


class DependencyChecker:
    """Check and track dependency versions"""

    def __init__(self):
        self.results = {
            "timestamp": datetime.now().isoformat(),
            "python_libraries": {},
            "external_compilers": {},
            "recommendations": [],
            "update_needed": False,
        }

    def check_python_library_versions(self) -> dict[str, dict[str, str]]:
        """Check Python library versions against PyPI"""

        # Libraries used in validation
        libraries = {
            "pydantic": ">=2.0",
            "sqlalchemy": ">=2.0",
            "jsonschema": ">=4.0",
            "graphql-core": ">=3.2",
            "avro-python3": ">=1.11",
            "pathway": ">=0.7",
            "pytest": None,
            "pytest-cov": None,
            "ruff": None,
            "mypy": None,
        }

        for lib_name, min_version in libraries.items():
            try:
                # Get current installed version
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        f"import {lib_name.replace('-', '_')}; print({lib_name.replace('-', '_')}.__version__)",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                current_version = (
                    result.stdout.strip() if result.returncode == 0 else "Not installed"
                )
            except Exception:
                current_version = "Error checking"

            try:
                # Get latest version from PyPI
                response = requests.get(
                    f"https://pypi.org/pypi/{lib_name}/json", timeout=10
                )
                if response.status_code == 200:
                    data = response.json()
                    latest_version = data["info"]["version"]
                else:
                    latest_version = "Unknown"
            except Exception:
                latest_version = "Error fetching"

            self.results["python_libraries"][lib_name] = {
                "current": current_version,
                "latest": latest_version,
                "min_required": min_version,
                "update_available": self._version_compare(
                    current_version, latest_version
                ),
            }

            if self._version_compare(current_version, latest_version):
                self.results["recommendations"].append(
                    f"Update {lib_name}: {current_version} → {latest_version}"
                )
                self.results["update_needed"] = True

        return self.results["python_libraries"]

    def check_external_compiler_versions(self) -> dict[str, dict[str, str]]:
        """Check external compiler versions"""

        compilers = {
            "node": {"cmd": ["node", "--version"], "current_dockerfile": "v20.19.2"},
            "typescript": {"cmd": ["tsc", "--version"], "current_dockerfile": "latest"},
            "java": {"cmd": ["java", "--version"], "current_dockerfile": "openjdk-21"},
            "kotlin": {"cmd": ["kotlinc", "-version"], "current_dockerfile": "v2.0.21"},
            "protoc": {"cmd": ["protoc", "--version"], "current_dockerfile": "3.21.12"},
        }

        for compiler, config in compilers.items():
            try:
                result = subprocess.run(
                    config["cmd"], capture_output=True, text=True, timeout=10
                )
                current_version = self._extract_version(result.stdout + result.stderr)
            except Exception:
                current_version = "Not available"

            # Get latest versions (simplified approach)
            latest_version = self._get_latest_compiler_version(compiler)

            self.results["external_compilers"][compiler] = {
                "current": current_version,
                "latest": latest_version,
                "dockerfile_version": config["current_dockerfile"],
                "update_available": current_version != latest_version
                and latest_version != "Unknown",
            }

            if current_version != latest_version and latest_version != "Unknown":
                self.results["recommendations"].append(
                    f"Consider updating {compiler}: {current_version} → {latest_version}"
                )
                self.results["update_needed"] = True

        return self.results["external_compilers"]

    def _extract_version(self, version_output: str) -> str:
        """Extract version number from command output"""
        import re

        # Common version patterns
        patterns = [
            r"v?(\d+\.\d+\.\d+)",
            r"Version (\d+\.\d+\.\d+)",
            r"(\d+\.\d+\.\d+)",
            r"v(\d+\.\d+)",
            r"(\d+\.\d+)",
        ]

        for pattern in patterns:
            match = re.search(pattern, version_output)
            if match:
                return match.group(1)

        return version_output.strip()

    def _get_latest_compiler_version(self, compiler: str) -> str:
        """Get latest version for external compilers (simplified)"""
        try:
            if compiler == "node":
                response = requests.get(
                    "https://api.github.com/repos/nodejs/node/releases/latest",
                    timeout=10,
                )
                return (
                    response.json()["tag_name"]
                    if response.status_code == 200
                    else "Unknown"
                )
            elif compiler == "typescript":
                response = requests.get(
                    "https://registry.npmjs.org/typescript/latest", timeout=10
                )
                return (
                    response.json()["version"]
                    if response.status_code == 200
                    else "Unknown"
                )
            elif compiler == "kotlin":
                response = requests.get(
                    "https://api.github.com/repos/JetBrains/kotlin/releases/latest",
                    timeout=10,
                )
                return (
                    response.json()["tag_name"]
                    if response.status_code == 200
                    else "Unknown"
                )
            else:
                return "Unknown"
        except Exception:
            return "Error fetching"

    def _version_compare(self, current: str, latest: str) -> bool:
        """Simple version comparison"""
        if current in ["Not installed", "Error checking"] or latest in [
            "Unknown",
            "Error fetching",
        ]:
            return False

        try:
            from packaging import version

            return version.parse(current) < version.parse(latest)
        except Exception:
            return current != latest

    def generate_report(self) -> str:
        """Generate a formatted dependency report"""
        report = []
        report.append("🔍 DEPENDENCY VERSION REPORT")
        report.append("=" * 50)
        report.append(f"Generated: {self.results['timestamp']}")
        report.append("")

        report.append("📦 PYTHON LIBRARIES:")
        report.append("-" * 30)
        for lib, info in self.results["python_libraries"].items():
            status = "🟡 UPDATE AVAILABLE" if info["update_available"] else "✅ CURRENT"
            report.append(
                f"{lib:<20} {info['current']:<15} → {info['latest']:<15} {status}"
            )

        report.append("")
        report.append("🔧 EXTERNAL COMPILERS:")
        report.append("-" * 30)
        for compiler, info in self.results["external_compilers"].items():
            status = "🟡 UPDATE AVAILABLE" if info["update_available"] else "✅ CURRENT"
            report.append(
                f"{compiler:<15} {info['current']:<20} → {info['latest']:<20} {status}"
            )

        if self.results["recommendations"]:
            report.append("")
            report.append("💡 RECOMMENDATIONS:")
            report.append("-" * 30)
            for rec in self.results["recommendations"]:
                report.append(f"• {rec}")

        return "\n".join(report)

    def save_results(self, filepath: str = "dependency_check.json"):
        """Save results to JSON file"""
        with open(filepath, "w") as f:
            json.dump(self.results, f, indent=2)


def main():
    """Main execution"""
    print("🔍 Checking dependency versions...")

    checker = DependencyChecker()

    print("📦 Checking Python libraries...")
    checker.check_python_library_versions()

    print("🔧 Checking external compilers...")
    checker.check_external_compiler_versions()

    print("\n" + checker.generate_report())

    # Save results
    checker.save_results()
    print("\n💾 Results saved to dependency_check.json")

    # Exit with status code based on updates needed
    sys.exit(1 if checker.results["update_needed"] else 0)


if __name__ == "__main__":
    main()
