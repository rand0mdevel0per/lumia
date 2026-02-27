# Lumia Framework

**Event-driven, plugin-first framework for LLM-powered IM bots**

## Overview

Lumia is a minimal-core, plugin-first framework designed for building LLM-powered instant messaging bots. The framework provides:

- **Box Container**: Safe, type-checked parameter passing with dual transport modes (serializable vs Arc reference counting)
- **Event Bus**: Three distinct messaging primitives (Event, EventChain, Pipeline) with strict semantics
- **Plugin System**: Git-based plugin management with lifecycle hooks and dependency resolution
- **Memory System**: Topic-Instance-Edge graph with RAG and spreading activation retrieval
- **MCP Integration**: Model Context Protocol client with built-in servers for tool execution
- **pkg CLI**: Pacman-style plugin management tool

## Project Status

**Version**: 0.1.0 (Development)

This project is currently in active development. The core framework is being implemented according to the specification in `specs/LUMIA_SPECS.md`.

## Architecture

```
lumia/                  # Core framework
├── core/               # Box, Event Bus, Pipeline
├── plugin/             # Plugin system
├── config/             # Configuration management
├── memory/             # Memory graph
├── mcp/                # MCP integration
├── system/             # System APIs
└── validation/         # Static analysis tools

pkg/                    # CLI tool
plugins/                # Installed plugins (git repo)
config/                 # Configuration files
data/                   # Runtime data
```

## Requirements

- Python 3.11+
- Docker/Podman (for Shipyard sandbox)
- PostgreSQL (or use bundled pgserver)

## Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -e ".[dev]"
```

## Development

```bash
# Run tests
pytest

# Run linter
ruff check .

# Format code
ruff format .
```

## License

Proprietary

## Documentation

See `specs/LUMIA_SPECS.md` for the complete engineering specification.
