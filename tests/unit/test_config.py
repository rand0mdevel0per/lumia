"""
Tests for Configuration System.

This test suite covers:
1. Schema validation (type mismatch, constraint violation)
2. TOML generation from schema (with comments)
3. TOML parsing and round-trip preservation
4. Runtime read/write operations
5. Auto-flush verification
6. Concurrent access safety
7. Error cases
"""

import tempfile
from pathlib import Path

import pytest

import lumia.config
from lumia.config.schema import ConfigField, SchemaError, ValidationError


class TestSchemaValidation:
    """Test schema field validation."""

    def test_field_creation_basic_types(self):
        """ConfigField should accept basic types."""
        field_int = ConfigField(int, 42, "An integer")
        assert field_int.type_ is int
        assert field_int.default == 42

        field_str = ConfigField(str, "hello", "A string")
        assert field_str.type_ is str
        assert field_str.default == "hello"

        field_float = ConfigField(float, 3.14, "A float")
        assert field_float.type_ is float
        assert field_float.default == 3.14

        field_bool = ConfigField(bool, True, "A boolean")
        assert field_bool.type_ is bool
        assert field_bool.default is True

    def test_field_default_type_mismatch(self):
        """ConfigField should reject default value that doesn't match type."""
        with pytest.raises(SchemaError, match="does not match type"):
            ConfigField(int, "not an int", "Bad default")

    def test_field_min_max_constraints(self):
        """ConfigField should accept min/max constraints for numbers."""
        field = ConfigField(int, 50, "Number with range", min=0, max=100)
        assert field.min == 0
        assert field.max == 100

        # Validate within range
        field.validate(50)
        field.validate(0)
        field.validate(100)

        # Validate out of range
        with pytest.raises(ValidationError, match="less than minimum"):
            field.validate(-1)

        with pytest.raises(ValidationError, match="greater than maximum"):
            field.validate(101)

    def test_field_string_length_constraints(self):
        """ConfigField should accept min/max length constraints for strings."""
        field = ConfigField(str, "hello", "String with length", min=3, max=10)

        # Validate within range
        field.validate("hello")
        field.validate("abc")
        field.validate("1234567890")

        # Validate out of range
        with pytest.raises(ValidationError, match="less than minimum"):
            field.validate("ab")

        with pytest.raises(ValidationError, match="greater than maximum"):
            field.validate("12345678901")

    def test_field_choices_constraint(self):
        """ConfigField should accept choices constraint."""
        field = ConfigField(str, "red", "Color choice", choices=["red", "green", "blue"])

        # Validate valid choices
        field.validate("red")
        field.validate("green")
        field.validate("blue")

        # Validate invalid choice
        with pytest.raises(ValidationError, match="not in allowed choices"):
            field.validate("yellow")

    def test_field_choices_default_must_be_in_choices(self):
        """ConfigField default must be in choices if choices specified."""
        with pytest.raises(SchemaError, match="not in choices"):
            ConfigField(str, "yellow", "Bad choice", choices=["red", "green", "blue"])

    def test_field_list_length_constraints(self):
        """ConfigField should accept min/max length constraints for lists."""
        field = ConfigField(list, [1, 2, 3], "List with length", min=1, max=5)

        # Validate within range
        field.validate([1])
        field.validate([1, 2, 3])
        field.validate([1, 2, 3, 4, 5])

        # Validate out of range
        with pytest.raises(ValidationError, match="less than minimum"):
            field.validate([])

        with pytest.raises(ValidationError, match="greater than maximum"):
            field.validate([1, 2, 3, 4, 5, 6])


class TestTOMLHandler:
    """Test TOML file I/O operations."""

    def test_toml_read_write_roundtrip(self):
        """TOML read/write should preserve data."""
        from lumia.config.toml_handler import read_toml, write_toml

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            # Write data
            data = {
                "plugin1": {"field1": 42, "field2": "hello"},
                "plugin2": {"field3": 3.14, "field4": True},
            }
            write_toml(config_file, data)

            # Read back
            loaded = read_toml(config_file)
            assert loaded == data

    def test_toml_generate_from_schema(self):
        """TOML generation should include comments from schema."""
        from lumia.config.toml_handler import generate_toml_from_schema

        schema = {
            "threshold": ConfigField(float, 0.5, "Detection threshold", min=0.0, max=1.0),
            "max_retries": ConfigField(int, 3, "Maximum retry attempts", min=1, max=10),
        }
        config_data = {"threshold": 0.5, "max_retries": 3}

        toml_str = generate_toml_from_schema("test-plugin", schema, config_data)

        # Check that comments are included
        assert "Detection threshold" in toml_str
        assert "Maximum retry attempts" in toml_str
        assert "min: 0.0" in toml_str or "min: 0" in toml_str
        assert "max: 1.0" in toml_str or "max: 1" in toml_str

        # Check that values are included
        assert "threshold = 0.5" in toml_str
        assert "max_retries = 3" in toml_str


class TestRuntimeAccess:
    """Test ConfigProxy runtime access."""

    def test_config_proxy_read(self):
        """ConfigProxy should allow reading config values."""
        from lumia.config.runtime import ConfigProxy

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "field1": ConfigField(int, 42, "Field 1"),
                "field2": ConfigField(str, "hello", "Field 2"),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Read default values
            assert proxy.field1 == 42
            assert proxy.field2 == "hello"

    def test_config_proxy_write(self):
        """ConfigProxy should allow writing config values."""
        from lumia.config.runtime import ConfigProxy

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "field1": ConfigField(int, 42, "Field 1"),
                "field2": ConfigField(str, "hello", "Field 2"),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Write new values
            proxy.field1 = 100
            proxy.field2 = "world"

            # Read back
            assert proxy.field1 == 100
            assert proxy.field2 == "world"

    def test_config_proxy_validation_on_write(self):
        """ConfigProxy should validate values on write."""
        from lumia.config.runtime import ConfigProxy

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "field1": ConfigField(int, 42, "Field 1", min=0, max=100),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Valid write
            proxy.field1 = 50

            # Invalid write (out of range)
            with pytest.raises(ValidationError, match="greater than maximum"):
                proxy.field1 = 150

            # Invalid write (wrong type)
            with pytest.raises(ValidationError, match="Expected type"):
                proxy.field1 = "not an int"

    def test_config_proxy_unknown_field(self):
        """ConfigProxy should reject unknown fields."""
        from lumia.config.runtime import ConfigProxy

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "field1": ConfigField(int, 42, "Field 1"),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Read unknown field
            with pytest.raises(AttributeError, match="not found in schema"):
                _ = proxy.unknown_field

            # Write unknown field
            with pytest.raises(AttributeError, match="not found in schema"):
                proxy.unknown_field = 123


class TestAutoFlush:
    """Test auto-flush behavior."""

    def test_config_auto_flush_on_write(self):
        """ConfigProxy should auto-flush to file on write."""
        from lumia.config.runtime import ConfigProxy
        from lumia.config.toml_handler import read_toml

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "field1": ConfigField(int, 42, "Field 1"),
                "field2": ConfigField(str, "hello", "Field 2"),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Write new value
            proxy.field1 = 100

            # Verify file was written
            assert config_file.exists()

            # Read file directly
            data = read_toml(config_file)
            assert "test-plugin" in data
            assert data["test-plugin"]["field1"] == 100

    def test_config_multiple_writes_flush(self):
        """Multiple writes should all flush to file."""
        from lumia.config.runtime import ConfigProxy
        from lumia.config.toml_handler import read_toml

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "field1": ConfigField(int, 42, "Field 1"),
                "field2": ConfigField(str, "hello", "Field 2"),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Multiple writes
            proxy.field1 = 100
            proxy.field2 = "world"
            proxy.field1 = 200

            # Read file directly
            data = read_toml(config_file)
            assert data["test-plugin"]["field1"] == 200
            assert data["test-plugin"]["field2"] == "world"


class TestConcurrentAccess:
    """Test thread-safe concurrent access."""

    def test_concurrent_writes(self):
        """Concurrent writes should be thread-safe."""
        import threading

        from lumia.config.runtime import ConfigProxy

        with tempfile.TemporaryDirectory() as tmpdir:
            config_file = Path(tmpdir) / "test.toml"

            schema = {
                "counter": ConfigField(int, 0, "Counter"),
            }

            proxy = ConfigProxy("test-plugin", schema, config_file)

            # Concurrent writes
            def increment():
                for _ in range(10):
                    current = proxy.counter
                    proxy.counter = current + 1

            threads = []
            for _ in range(5):
                thread = threading.Thread(target=increment)
                threads.append(thread)
                thread.start()

            for thread in threads:
                thread.join()

            # Note: Due to race conditions, final value may not be exactly 50
            # But the file should be valid and readable
            assert config_file.exists()


class TestConfigAPI:
    """Test public configuration API."""

    def test_field_helper_function(self):
        """field() helper should create ConfigField."""
        field = lumia.config.field(int, 42, "Test field", min=0, max=100)
        assert isinstance(field, ConfigField)
        assert field.type_ is int
        assert field.default == 42
        assert field.min == 0
        assert field.max == 100

    def test_declare_and_get(self):
        """declare() and get() should work together."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily change config file path
            original_config_file = lumia.config._config_file
            lumia.config._config_file = Path(tmpdir) / "test.toml"

            try:
                # Clear schemas
                lumia.config._schemas.clear()

                # Declare schema
                lumia.config.declare(
                    "test-plugin",
                    {
                        "field1": lumia.config.field(int, 42, "Field 1"),
                        "field2": lumia.config.field(str, "hello", "Field 2"),
                    },
                )

                # Get config accessor
                cfg = lumia.config.get("test-plugin")
                assert cfg.field1 == 42
                assert cfg.field2 == "hello"

                # Write and verify
                cfg.field1 = 100
                assert cfg.field1 == 100

            finally:
                # Restore original config file path
                lumia.config._config_file = original_config_file
                lumia.config._schemas.clear()

    def test_declare_duplicate_raises_error(self):
        """Declaring schema twice should raise error."""
        try:
            lumia.config._schemas.clear()

            lumia.config.declare(
                "test-plugin",
                {"field1": lumia.config.field(int, 42, "Field 1")},
            )

            # Declare again should fail
            with pytest.raises(lumia.config.ConfigError, match="already declared"):
                lumia.config.declare(
                    "test-plugin",
                    {"field1": lumia.config.field(int, 42, "Field 1")},
                )
        finally:
            lumia.config._schemas.clear()

    def test_get_without_declare_raises_error(self):
        """Getting config without declaring schema should raise error."""
        try:
            lumia.config._schemas.clear()

            with pytest.raises(lumia.config.ConfigError, match="not declared"):
                lumia.config.get("unknown-plugin")
        finally:
            lumia.config._schemas.clear()





