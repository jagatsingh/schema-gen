#!/usr/bin/env python3
"""
Automated Dependency Updater
Updates Dockerfile.validation and dependency files with latest versions
"""

import json
import re
import subprocess
import sys
from pathlib import Path

import requests


class DependencyUpdater:
    """Automated dependency updater"""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.dockerfile_path = self.project_root / "Dockerfile.validation"
        self.dependencies_config = self.project_root / "dependencies.json"
        self.updates_made = []
        self.errors = []

    def load_dependencies_config(self) -> dict:
        """Load dependencies configuration"""
        try:
            with open(self.dependencies_config) as f:
                return json.load(f)
        except FileNotFoundError:
            self.errors.append("dependencies.json not found")
            return {}

    def get_latest_kotlin_version(self) -> str | None:
        """Get latest Kotlin version from GitHub"""
        try:
            response = requests.get(
                "https://api.github.com/repos/JetBrains/kotlin/releases/latest",
                timeout=10,
            )
            if response.status_code == 200:
                tag_name = response.json()["tag_name"]
                return tag_name.lstrip("v")
            return None
        except Exception as e:
            self.errors.append(f"Failed to fetch Kotlin version: {e}")
            return None

    def get_latest_jackson_version(self) -> str | None:
        """Get latest Jackson version from Maven Central"""
        try:
            response = requests.get(
                "https://search.maven.org/solrsearch/select?q=g:com.fasterxml.jackson.core+AND+a:jackson-core&rows=1&wt=json",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                if data["response"]["docs"]:
                    return data["response"]["docs"][0]["latestVersion"]
            return None
        except Exception as e:
            self.errors.append(f"Failed to fetch Jackson version: {e}")
            return None

    def get_latest_kotlinx_serialization_version(self) -> str | None:
        """Get latest kotlinx.serialization version"""
        try:
            response = requests.get(
                "https://search.maven.org/solrsearch/select?q=g:org.jetbrains.kotlinx+AND+a:kotlinx-serialization-core-jvm&rows=1&wt=json",
                timeout=10,
            )
            if response.status_code == 200:
                data = response.json()
                if data["response"]["docs"]:
                    return data["response"]["docs"][0]["latestVersion"]
            return None
        except Exception as e:
            self.errors.append(f"Failed to fetch kotlinx.serialization version: {e}")
            return None

    def update_dockerfile_kotlin(self, new_version: str) -> bool:
        """Update Kotlin version in Dockerfile"""
        try:
            content = self.dockerfile_path.read_text()

            # Update Kotlin compiler download URL
            old_download_pattern = r"https://github\.com/JetBrains/kotlin/releases/download/v[\d.]+/kotlin-compiler-[\d.]+\.zip"
            new_download_url = f"https://github.com/JetBrains/kotlin/releases/download/v{new_version}/kotlin-compiler-{new_version}.zip"

            updated_content = re.sub(old_download_pattern, new_download_url, content)

            if updated_content != content:
                self.dockerfile_path.write_text(updated_content)
                self.updates_made.append(f"Updated Kotlin to v{new_version}")
                return True

            return False

        except Exception as e:
            self.errors.append(f"Failed to update Kotlin version: {e}")
            return False

    def update_dockerfile_jackson(self, new_version: str) -> bool:
        """Update Jackson version in Dockerfile"""
        try:
            content = self.dockerfile_path.read_text()

            # Update Jackson JAR URLs
            patterns = [
                r"jackson-core-[\d.]+\.jar",
                r"jackson-databind-[\d.]+\.jar",
                r"jackson-annotations-[\d.]+\.jar",
            ]

            replacements = [
                f"jackson-core-{new_version}.jar",
                f"jackson-databind-{new_version}.jar",
                f"jackson-annotations-{new_version}.jar",
            ]

            updated_content = content
            for pattern, replacement in zip(patterns, replacements, strict=False):
                updated_content = re.sub(pattern, replacement, updated_content)

            if updated_content != content:
                self.dockerfile_path.write_text(updated_content)
                self.updates_made.append(f"Updated Jackson to v{new_version}")
                return True

            return False

        except Exception as e:
            self.errors.append(f"Failed to update Jackson version: {e}")
            return False

    def update_dockerfile_kotlinx_serialization(self, new_version: str) -> bool:
        """Update kotlinx.serialization version in Dockerfile"""
        try:
            content = self.dockerfile_path.read_text()

            # Update kotlinx.serialization JAR URLs
            patterns = [
                r"kotlinx-serialization-core-jvm-[\d.]+\.jar",
                r"kotlinx-serialization-json-jvm-[\d.]+\.jar",
            ]

            replacements = [
                f"kotlinx-serialization-core-jvm-{new_version}.jar",
                f"kotlinx-serialization-json-jvm-{new_version}.jar",
            ]

            updated_content = content
            for pattern, replacement in zip(patterns, replacements, strict=False):
                updated_content = re.sub(pattern, replacement, updated_content)

            if updated_content != content:
                self.dockerfile_path.write_text(updated_content)
                self.updates_made.append(
                    f"Updated kotlinx.serialization to v{new_version}"
                )
                return True

            return False

        except Exception as e:
            self.errors.append(f"Failed to update kotlinx.serialization version: {e}")
            return False

    def update_dependencies_config(self, updates: dict) -> bool:
        """Update dependencies.json with new versions"""
        try:
            config = self.load_dependencies_config()
            if not config:
                return False

            # Update external compiler versions
            for compiler, version in updates.get("external_compilers", {}).items():
                if compiler in config["external_compilers"]:
                    config["external_compilers"][compiler]["current_version"] = version

            # Update external library versions
            for library, versions in updates.get("external_libraries", {}).items():
                if library in config["external_libraries"]:
                    for key, value in versions.items():
                        if key in config["external_libraries"][library]:
                            config["external_libraries"][library][key] = value

            # Save updated config
            with open(self.dependencies_config, "w") as f:
                json.dump(config, f, indent=2)

            return True

        except Exception as e:
            self.errors.append(f"Failed to update dependencies config: {e}")
            return False

    def test_docker_build(self) -> bool:
        """Test if Docker still builds after updates"""
        try:
            print("🧪 Testing Docker build after updates...")
            result = subprocess.run(
                [
                    "docker",
                    "build",
                    "-f",
                    "Dockerfile.validation",
                    "-t",
                    "schema-gen-test",
                    ".",
                ],
                capture_output=True,
                text=True,
                timeout=600,
                cwd=self.project_root,
            )

            if result.returncode == 0:
                print("✅ Docker build successful")
                return True
            else:
                self.errors.append(f"Docker build failed: {result.stderr}")
                print(f"❌ Docker build failed: {result.stderr}")
                return False

        except Exception as e:
            self.errors.append(f"Docker build test failed: {e}")
            return False

    def run_updates(self, test_build: bool = True) -> bool:
        """Run all dependency updates"""
        print("🔄 Starting dependency updates...")

        config_updates = {"external_compilers": {}, "external_libraries": {}}

        # Update Kotlin
        kotlin_version = self.get_latest_kotlin_version()
        if kotlin_version:
            if self.update_dockerfile_kotlin(kotlin_version):
                config_updates["external_compilers"]["kotlin"] = f"v{kotlin_version}"

        # Update Jackson
        jackson_version = self.get_latest_jackson_version()
        if jackson_version:
            if self.update_dockerfile_jackson(jackson_version):
                config_updates["external_libraries"]["jackson"] = {
                    "core_version": jackson_version,
                    "databind_version": jackson_version,
                    "annotations_version": jackson_version,
                }

        # Update kotlinx.serialization
        serialization_version = self.get_latest_kotlinx_serialization_version()
        if serialization_version:
            if self.update_dockerfile_kotlinx_serialization(serialization_version):
                config_updates["external_libraries"]["kotlinx_serialization"] = {
                    "core_version": serialization_version,
                    "json_version": serialization_version,
                }

        # Update config file
        if config_updates["external_compilers"] or config_updates["external_libraries"]:
            self.update_dependencies_config(config_updates)

        # Test Docker build if requested
        if test_build and self.updates_made:
            if not self.test_docker_build():
                return False

        return len(self.errors) == 0

    def generate_summary(self) -> str:
        """Generate update summary"""
        lines = []
        lines.append("🔄 DEPENDENCY UPDATE SUMMARY")
        lines.append("=" * 40)

        if self.updates_made:
            lines.append("✅ UPDATES APPLIED:")
            for update in self.updates_made:
                lines.append(f"  • {update}")
        else:
            lines.append("ℹ️  No updates were needed")

        if self.errors:
            lines.append("")
            lines.append("❌ ERRORS ENCOUNTERED:")
            for error in self.errors:
                lines.append(f"  • {error}")

        return "\n".join(lines)


def main():
    """Main execution"""
    import argparse

    parser = argparse.ArgumentParser(description="Update dependencies automatically")
    parser.add_argument(
        "--test-build",
        action="store_true",
        default=True,
        help="Test Docker build after updates",
    )
    parser.add_argument("--no-test", action="store_true", help="Skip Docker build test")
    args = parser.parse_args()

    updater = DependencyUpdater()
    success = updater.run_updates(test_build=not args.no_test)

    print("\n" + updater.generate_summary())

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
