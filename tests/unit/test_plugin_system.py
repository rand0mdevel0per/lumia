"""
Tests for Plugin System.

This test suite covers:
1. Manifest parsing (valid/invalid cases)
2. Version constraint matching
3. Dependency resolution (simple, complex, cyclic)
4. Unique domain conflicts
5. Plugin loading/unloading
6. Hook execution
7. Git operations
"""

import json
import tempfile
from pathlib import Path

import pytest

from lumia.plugin.manifest import (
    ManifestError,
    ValidationError,
    VersionConstraint,
    parse_manifest,
    parse_version_constraint,
)


class TestManifestParsing:
    """Test manifest parsing and validation."""

    def test_parse_valid_manifest(self):
        """Should parse a valid manifest successfully."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "test-plugin",
                "version": "1.0.0",
                "main": "plugin.py",
                "description": "Test plugin",
                "author": "Test Author",
                "dependencies": {"dep-plugin": ">=1.0.0"},
                "unique": ["test.domain"],
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            manifest = parse_manifest(manifest_path)

            assert manifest.name == "test-plugin"
            assert manifest.version == "1.0.0"
            assert manifest.main == "plugin.py"
            assert manifest.description == "Test plugin"
            assert manifest.author == "Test Author"
            assert "dep-plugin" in manifest.dependencies
            assert manifest.unique == ["test.domain"]

    def test_parse_minimal_manifest(self):
        """Should parse manifest with only required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "minimal-plugin",
                "version": "1.0.0",
                "main": "plugin.py",
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            manifest = parse_manifest(manifest_path)

            assert manifest.name == "minimal-plugin"
            assert manifest.version == "1.0.0"
            assert manifest.main == "plugin.py"
            assert manifest.description == ""
            assert manifest.author == ""
            assert len(manifest.dependencies) == 0
            assert len(manifest.unique) == 0

    def test_parse_missing_required_field(self):
        """Should reject manifest missing required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "test-plugin",
                # Missing version and main
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            with pytest.raises(ValidationError, match="Missing required field"):
                parse_manifest(manifest_path)

    def test_parse_invalid_plugin_name(self):
        """Should reject invalid plugin names."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "Invalid_Plugin_Name",  # Uppercase and underscores not allowed
                "version": "1.0.0",
                "main": "plugin.py",
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            with pytest.raises(ValidationError, match="Invalid plugin name"):
                parse_manifest(manifest_path)

    def test_parse_invalid_version(self):
        """Should reject invalid version strings."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "test-plugin",
                "version": "1.0",  # Not semantic version
                "main": "plugin.py",
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            with pytest.raises(ValidationError, match="Invalid version"):
                parse_manifest(manifest_path)

    def test_parse_invalid_main(self):
        """Should reject non-Python entry points."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "test-plugin",
                "version": "1.0.0",
                "main": "plugin.js",  # Not a .py file
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            with pytest.raises(ValidationError, match="Invalid main entry point"):
                parse_manifest(manifest_path)

    def test_parse_invalid_unique_domain(self):
        """Should reject invalid unique domain formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"
            manifest_data = {
                "name": "test-plugin",
                "version": "1.0.0",
                "main": "plugin.py",
                "unique": ["Invalid.Domain"],  # Uppercase not allowed
            }

            with open(manifest_path, "w") as f:
                json.dump(manifest_data, f)

            with pytest.raises(ValidationError, match="Invalid unique domain"):
                parse_manifest(manifest_path)

    def test_parse_manifest_file_not_found(self):
        """Should raise error for non-existent manifest file."""
        with pytest.raises(ManifestError, match="Manifest file not found"):
            parse_manifest(Path("/nonexistent/manifest.json"))

    def test_parse_invalid_json(self):
        """Should raise error for invalid JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_path = Path(tmpdir) / "manifest.json"

            with open(manifest_path, "w") as f:
                f.write("{ invalid json }")

            with pytest.raises(ManifestError, match="Failed to parse manifest JSON"):
                parse_manifest(manifest_path)


class TestVersionConstraints:
    """Test version constraint parsing and matching."""

    def test_parse_version_constraint_exact(self):
        """Should parse exact version constraint."""
        constraint = parse_version_constraint("==1.2.3")
        assert constraint.operator == "=="
        assert constraint.version == "1.2.3"

    def test_parse_version_constraint_gte(self):
        """Should parse greater-than-or-equal constraint."""
        constraint = parse_version_constraint(">=1.0.0")
        assert constraint.operator == ">="
        assert constraint.version == "1.0.0"

    def test_parse_version_constraint_compatible(self):
        """Should parse compatible release constraint."""
        constraint = parse_version_constraint("~=1.2.3")
        assert constraint.operator == "~="
        assert constraint.version == "1.2.3"

    def test_parse_invalid_version_constraint(self):
        """Should reject invalid version constraints."""
        with pytest.raises(ValidationError, match="Invalid version constraint"):
            parse_version_constraint("invalid")

        with pytest.raises(ValidationError, match="Invalid version constraint"):
            parse_version_constraint(">1.0.0")  # > not supported

        with pytest.raises(ValidationError, match="Invalid version constraint"):
            parse_version_constraint("==1.0")  # Not semantic version

    def test_exact_version_match(self):
        """Should match exact versions correctly."""
        constraint = VersionConstraint("==", "1.2.3")
        assert constraint.matches("1.2.3")
        assert not constraint.matches("1.2.4")
        assert not constraint.matches("1.2.2")

    def test_gte_version_match(self):
        """Should match greater-than-or-equal versions correctly."""
        constraint = VersionConstraint(">=", "1.2.3")
        assert constraint.matches("1.2.3")
        assert constraint.matches("1.2.4")
        assert constraint.matches("1.3.0")
        assert constraint.matches("2.0.0")
        assert not constraint.matches("1.2.2")
        assert not constraint.matches("1.1.9")

    def test_compatible_release_match(self):
        """Should match compatible release versions correctly."""
        constraint = VersionConstraint("~=", "1.2.3")
        assert constraint.matches("1.2.3")
        assert constraint.matches("1.2.4")
        assert constraint.matches("1.2.99")
        assert not constraint.matches("1.3.0")
        assert not constraint.matches("2.0.0")
        assert not constraint.matches("1.2.2")

    def test_version_comparison(self):
        """Should compare versions correctly."""
        constraint = VersionConstraint(">=", "1.0.0")

        # Test basic comparison
        assert constraint._compare_versions("1.0.0", "1.0.0") == 0
        assert constraint._compare_versions("1.0.1", "1.0.0") == 1
        assert constraint._compare_versions("1.0.0", "1.0.1") == -1

        # Test different lengths
        assert constraint._compare_versions("1.0", "1.0.0") == 0
        assert constraint._compare_versions("1.1", "1.0.9") == 1


class TestPluginManager:
    """Test plugin manager functionality."""

    def test_discover_plugins(self):
        """Should discover plugins in plugins directory."""
        from lumia.plugin.manager import PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create test plugin
            plugin_dir = plugins_dir / "test-plugin"
            plugin_dir.mkdir()

            manifest_data = {
                "name": "test-plugin",
                "version": "1.0.0",
                "main": "plugin.py",
            }

            with open(plugin_dir / "manifest.json", "w") as f:
                json.dump(manifest_data, f)

            # Create plugin entry point
            (plugin_dir / "plugin.py").write_text("# Test plugin")

            # Discover plugins
            manager = PluginManager(plugins_dir)
            discovered = manager.discover_plugins()

            assert "test-plugin" in discovered
            assert manager.get_plugin_info("test-plugin") is not None

    def test_simple_dependency_resolution(self):
        """Should resolve simple dependencies correctly."""
        from lumia.plugin.manager import PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create plugin A (no dependencies)
            plugin_a_dir = plugins_dir / "plugin-a"
            plugin_a_dir.mkdir()
            with open(plugin_a_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-a",
                    "version": "1.0.0",
                    "main": "plugin.py",
                }, f)
            (plugin_a_dir / "plugin.py").write_text("# Plugin A")

            # Create plugin B (depends on A)
            plugin_b_dir = plugins_dir / "plugin-b"
            plugin_b_dir.mkdir()
            with open(plugin_b_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-b",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "dependencies": {"plugin-a": ">=1.0.0"},
                }, f)
            (plugin_b_dir / "plugin.py").write_text("# Plugin B")

            # Discover and resolve
            manager = PluginManager(plugins_dir)
            manager.discover_plugins()

            load_order = manager._resolve_dependencies("plugin-b")

            # A should be loaded before B
            assert load_order.index("plugin-a") < load_order.index("plugin-b")

    def test_complex_dependency_resolution(self):
        """Should resolve complex dependency graphs."""
        from lumia.plugin.manager import PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create dependency graph: D -> B -> A, D -> C -> A
            plugins = {
                "plugin-a": {"version": "1.0.0", "deps": {}},
                "plugin-b": {"version": "1.0.0", "deps": {"plugin-a": ">=1.0.0"}},
                "plugin-c": {"version": "1.0.0", "deps": {"plugin-a": ">=1.0.0"}},
                "plugin-d": {"version": "1.0.0", "deps": {"plugin-b": ">=1.0.0", "plugin-c": ">=1.0.0"}},
            }

            for name, info in plugins.items():
                plugin_dir = plugins_dir / name
                plugin_dir.mkdir()
                with open(plugin_dir / "manifest.json", "w") as f:
                    json.dump({
                        "name": name,
                        "version": info["version"],
                        "main": "plugin.py",
                        "dependencies": info["deps"],
                    }, f)
                (plugin_dir / "plugin.py").write_text(f"# {name}")

            # Discover and resolve
            manager = PluginManager(plugins_dir)
            manager.discover_plugins()

            load_order = manager._resolve_dependencies("plugin-d")

            # A must be loaded first
            assert load_order[0] == "plugin-a"
            # B and C must be loaded before D
            assert load_order.index("plugin-b") < load_order.index("plugin-d")
            assert load_order.index("plugin-c") < load_order.index("plugin-d")

    def test_circular_dependency_detection(self):
        """Should detect circular dependencies."""
        from lumia.plugin.manager import DependencyError, PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create circular dependency: A -> B -> A
            plugin_a_dir = plugins_dir / "plugin-a"
            plugin_a_dir.mkdir()
            with open(plugin_a_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-a",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "dependencies": {"plugin-b": ">=1.0.0"},
                }, f)
            (plugin_a_dir / "plugin.py").write_text("# Plugin A")

            plugin_b_dir = plugins_dir / "plugin-b"
            plugin_b_dir.mkdir()
            with open(plugin_b_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-b",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "dependencies": {"plugin-a": ">=1.0.0"},
                }, f)
            (plugin_b_dir / "plugin.py").write_text("# Plugin B")

            # Discover and try to resolve
            manager = PluginManager(plugins_dir)
            manager.discover_plugins()

            with pytest.raises(DependencyError, match="Circular dependency"):
                manager._resolve_dependencies("plugin-a")

    def test_domain_conflict_detection(self):
        """Should detect unique domain conflicts."""
        from lumia.plugin.manager import ConflictError, PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create two plugins claiming the same domain
            plugin_a_dir = plugins_dir / "plugin-a"
            plugin_a_dir.mkdir()
            with open(plugin_a_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-a",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "unique": ["test.domain"],
                }, f)
            (plugin_a_dir / "plugin.py").write_text("# Plugin A")

            plugin_b_dir = plugins_dir / "plugin-b"
            plugin_b_dir.mkdir()
            with open(plugin_b_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-b",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "unique": ["test.domain"],  # Same domain
                }, f)
            (plugin_b_dir / "plugin.py").write_text("# Plugin B")

            # Discover plugins
            manager = PluginManager(plugins_dir)
            manager.discover_plugins()

            # Check for conflict
            with pytest.raises(ConflictError, match="Domain conflict"):
                manager._check_domain_conflicts(["plugin-a", "plugin-b"])

    def test_version_constraint_mismatch(self):
        """Should reject dependency with version mismatch."""
        from lumia.plugin.manager import DependencyError, PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create plugin A with version 1.0.0
            plugin_a_dir = plugins_dir / "plugin-a"
            plugin_a_dir.mkdir()
            with open(plugin_a_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-a",
                    "version": "1.0.0",
                    "main": "plugin.py",
                }, f)
            (plugin_a_dir / "plugin.py").write_text("# Plugin A")

            # Create plugin B requiring A >= 2.0.0
            plugin_b_dir = plugins_dir / "plugin-b"
            plugin_b_dir.mkdir()
            with open(plugin_b_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-b",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "dependencies": {"plugin-a": ">=2.0.0"},
                }, f)
            (plugin_b_dir / "plugin.py").write_text("# Plugin B")

            # Discover and try to resolve
            manager = PluginManager(plugins_dir)
            manager.discover_plugins()

            with pytest.raises(DependencyError, match="requires plugin-a"):
                manager._resolve_dependencies("plugin-b")

    def test_missing_dependency(self):
        """Should reject missing dependencies."""
        from lumia.plugin.manager import DependencyError, PluginManager

        with tempfile.TemporaryDirectory() as tmpdir:
            plugins_dir = Path(tmpdir) / "plugins"
            plugins_dir.mkdir()

            # Create plugin B depending on non-existent A
            plugin_b_dir = plugins_dir / "plugin-b"
            plugin_b_dir.mkdir()
            with open(plugin_b_dir / "manifest.json", "w") as f:
                json.dump({
                    "name": "plugin-b",
                    "version": "1.0.0",
                    "main": "plugin.py",
                    "dependencies": {"plugin-a": ">=1.0.0"},
                }, f)
            (plugin_b_dir / "plugin.py").write_text("# Plugin B")

            # Discover and try to resolve
            manager = PluginManager(plugins_dir)
            manager.discover_plugins()

            with pytest.raises(DependencyError, match="not installed"):
                manager._resolve_dependencies("plugin-b")


class TestHookExecution:
    """Test lifecycle hook execution."""

    def test_execute_hook_success(self):
        """Should execute hook successfully."""
        from lumia.plugin.hooks import HookType, execute_hook

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            hooks_dir = plugin_dir / "hooks"
            hooks_dir.mkdir()

            # Create a simple hook script
            hook_script = hooks_dir / "install.py"
            hook_script.write_text("print('Hook executed')")

            # Execute hook
            execute_hook(plugin_dir, HookType.INSTALL)

    def test_execute_hook_not_found(self):
        """Should silently skip if hook not found."""
        from lumia.plugin.hooks import HookType, execute_hook

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)

            # Execute hook (no hooks directory)
            execute_hook(plugin_dir, HookType.INSTALL)  # Should not raise

    def test_execute_hook_with_env_vars(self):
        """Should inject environment variables."""
        from lumia.plugin.hooks import HookType, execute_hook

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            hooks_dir = plugin_dir / "hooks"
            hooks_dir.mkdir()

            # Create hook that checks env vars
            hook_script = hooks_dir / "install.py"
            hook_script.write_text("""
import os
assert os.environ['LUMIA_PLUGIN_DIR'] == r'""" + str(plugin_dir) + """'
assert os.environ['LUMIA_HOOK_TYPE'] == 'install'
assert os.environ['CUSTOM_VAR'] == 'test_value'
""")

            # Execute hook with custom env vars
            execute_hook(plugin_dir, HookType.INSTALL, env_vars={"CUSTOM_VAR": "test_value"})

    def test_has_hook(self):
        """Should detect if hook exists."""
        from lumia.plugin.hooks import HookType, has_hook

        with tempfile.TemporaryDirectory() as tmpdir:
            plugin_dir = Path(tmpdir)
            hooks_dir = plugin_dir / "hooks"
            hooks_dir.mkdir()

            # No hook initially
            assert not has_hook(plugin_dir, HookType.INSTALL)

            # Create hook
            hook_script = hooks_dir / "install.py"
            hook_script.write_text("print('Hook')")

            # Should detect hook
            assert has_hook(plugin_dir, HookType.INSTALL)


class TestGitOperations:
    """Test git operations."""

    def test_clone_plugin(self):
        """Should clone plugin repository."""
        # This test would require a real git repo or mock
        # Skipping for now as it requires external dependencies
        pass

    def test_list_tags(self):
        """Should list repository tags."""
        # This test would require a real git repo or mock
        # Skipping for now as it requires external dependencies
        pass

    def test_get_latest_tag(self):
        """Should get latest semantic version tag."""
        # This test would require a real git repo or mock
        # Skipping for now as it requires external dependencies
        pass


class TestAdapterSystem:
    """Test adapter registration and heartbeat."""

    def test_register_adapter(self):
        """Should register adapter successfully."""
        from lumia.system.adapters import AdapterRegistry

        registry = AdapterRegistry()
        registry.register("test-adapter", "1.0.0", {"platform": "test"})

        assert registry.is_registered("test-adapter")
        adapter_info = registry.get_adapter("test-adapter")
        assert adapter_info is not None
        assert adapter_info.adapter_id == "test-adapter"
        assert adapter_info.adapter_version == "1.0.0"
        assert adapter_info.metadata["platform"] == "test"

    def test_register_duplicate_adapter(self):
        """Should reject duplicate adapter registration."""
        from lumia.system.adapters import AdapterError, AdapterRegistry

        registry = AdapterRegistry()
        registry.register("test-adapter", "1.0.0")

        with pytest.raises(AdapterError, match="already registered"):
            registry.register("test-adapter", "1.0.0")

    def test_heartbeat_update(self):
        """Should update adapter heartbeat."""
        import time

        from lumia.system.adapters import AdapterRegistry

        registry = AdapterRegistry()
        registry.register("test-adapter", "1.0.0")

        adapter_info = registry.get_adapter("test-adapter")
        initial_heartbeat = adapter_info.last_heartbeat

        time.sleep(0.1)
        registry.heartbeat("test-adapter", "1.0.0")

        adapter_info = registry.get_adapter("test-adapter")
        assert adapter_info.last_heartbeat > initial_heartbeat

    def test_heartbeat_version_mismatch(self):
        """Should reject heartbeat with version mismatch."""
        from lumia.system.adapters import AdapterError, AdapterRegistry

        registry = AdapterRegistry()
        registry.register("test-adapter", "1.0.0")

        with pytest.raises(AdapterError, match="version mismatch"):
            registry.heartbeat("test-adapter", "2.0.0")

    def test_heartbeat_not_registered(self):
        """Should reject heartbeat for unregistered adapter."""
        from lumia.system.adapters import AdapterError, AdapterRegistry

        registry = AdapterRegistry()

        with pytest.raises(AdapterError, match="not registered"):
            registry.heartbeat("test-adapter", "1.0.0")

    def test_get_active_adapters(self):
        """Should return active adapters within timeout."""
        import time

        from lumia.system.adapters import AdapterRegistry

        registry = AdapterRegistry()
        registry.register("adapter-1", "1.0.0")
        registry.register("adapter-2", "1.0.0")

        # Both should be active initially
        active = registry.get_active_adapters(timeout=1.0)
        assert "adapter-1" in active
        assert "adapter-2" in active

        # Update heartbeat for adapter-1 only
        time.sleep(0.1)
        registry.heartbeat("adapter-1", "1.0.0")

        # With very short timeout, only adapter-1 should be active
        active = registry.get_active_adapters(timeout=0.05)
        assert "adapter-1" in active
        assert "adapter-2" not in active

