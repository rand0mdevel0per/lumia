# Lumia Framework — Engineering Specification
**Document ID:** LUMIA-SPEC-001  
**Version:** 0.1.0-draft  
**Status:** Draft  
**License:** Proprietary

---

## Table of Contents

1. [Overview](#1-overview)
2. [Architecture](#2-architecture)
3. [Core: Box Container](#3-core-box-container)
4. [Core: Event Bus](#4-core-event-bus)
5. [Core: Pipeline](#5-core-pipeline)
6. [Core: Event Provider](#6-core-event-provider)
7. [Plugin System](#7-plugin-system)
8. [Configuration System](#8-configuration-system)
9. [Tool Execution & Sandbox](#9-tool-execution--sandbox)
10. [MCP Tool Design](#10-mcp-tool-design)
11. [Memory System](#11-memory-system)
12. [Heartflow Plugin — Message Processing Chain](#12-heartflow-plugin--message-processing-chain)
13. [Registry & pkg CLI](#13-registry--pkg-cli)
14. [Quality & Validation](#14-quality--validation)
15. [Technology Stack](#15-technology-stack)

---

## 1. Overview

**Lumia** is an event-driven, plugin-first framework for LLM-powered IM bots. The core is minimal by design: it provides an event bus, pipeline dispatcher, plugin lifecycle manager, and the `Box` smart container. All domain logic — including the main reply handler — lives in plugins.

### Design Principles
- **Minimal core.** The framework has no opinion about personalities, memory, or reply logic.
- **Plugin-first.** Every capability is a plugin, including adapters and the heartflow responder.
- **Modern bus model.** Three distinct messaging primitives (Event, EventChain, Pipeline) with strict semantics.
- **Safe transfer.** `Box` is the sole parameter container; raw `Any` passing is prohibited.
- **Arch philosophy.** Simple, modular, correct. Ship small, extend via plugins.

---

## 2. Architecture

```
IM Platform (QQ / Discord / Telegram / ...)
        │
        ▼
┌─────────────────────────────────────────────────────┐
│                  Event Provider                      │  (plugin)
│  Receives raw platform events, emits Lumia events   │
└───────────────────────┬─────────────────────────────┘
                        │  lumia.pipe.start() / lumia.event.start()
                        ▼
┌─────────────────────────────────────────────────────┐
│                   Event Bus                          │  (core)
│                                                     │
│   ┌─────────────┐  ┌──────────────┐  ┌──────────┐  │
│   │  Pipeline   │  │  EventChain  │  │  Event   │  │
│   │ (breakable) │  │  (transform) │  │ (notify) │  │
│   └──────┬──────┘  └──────────────┘  └──────────┘  │
└──────────┼──────────────────────────────────────────┘
           │
    ┌──────┴────────────────────────────────────┐
    │            Pipeline: 'msg'                │
    │                                           │
    │  priv=200  [L0] Logic Filter              │
    │  priv=100  [L1] Small Model Perception    │
    │  priv=50   [L2] Planner (per-group)       │
    │  priv=10   [L3] Heartflow LLM             │
    └───────────────────────────────────────────┘
                        │
          ┌─────────────┼──────────────┐
          ▼             ▼              ▼
     [Polish LLM]  [Memory Update]  [Relation Update]
          │
          ▼
    lumia.event.start('msg.send, dest=...')
          │
          ▼
    Event Provider → Platform send
```

---

## 3. Core: Box Container

### 3.1 Purpose

`Box` is the **only** permitted parameter type for pipeline and event handlers. It:
- Prevents type-chaos from untyped `Any` passing across plugin boundaries
- Provides two transport modes depending on serializability
- Carries type metadata for static validation at publish time

### 3.2 Transport Modes

```
Box.any(x)
  ├─ x is dill-serializable
  │     → dill.dumps(x) stored internally
  │     → Passing = copy (value semantics)
  │     → No reference counting needed
  │
  └─ x is NOT dill-serializable (socket, file handle, DB connection, etc.)
        → Stored as live heap reference
        → Arc<T> semantics: reference count tracked
        → refcount reaches 0 → destructor called (resource released)
        → Passing = refcount+1 (shared ownership)
```

The two paths are **completely independent**. There is no reference counting for serializable values.

### 3.3 API

```python
# Construction
box = Box.any(x)              # auto-detect serializable vs arc path

# Consumption
value = box.into()            # unpack; runtime type assertion; panics on mismatch
box2  = box.clone()           # dill path: new deserialized copy
                              # arc path: refcount+1, same heap object

# Type introspection (used by validator)
box.inner_type() -> type      # returns the stored type for static checks
```

### 3.4 Arc Path Implementation

- Use `weakref` + `__del__` for refcount tracking (CPython immediate drop on zero)
- **Prohibition:** resource objects MUST NOT hold a back-reference to their `Box` (prevents refcount cycle → leak)
- On `__del__`: call resource's `.close()` / `.release()` / context-specific destructor

### 3.5 RAII Contract

Resources that cannot be dill-serialized MUST be wrapped in Box before entering any pipeline or event handler. Bare resource passing across handler boundaries is a spec violation and will be caught by `pkg dev validate`.

---

## 4. Core: Event Bus

### 4.1 Three Messaging Primitives

#### 4.1.1 Event (Notification)
- All subscribers receive the event in strict priority order
- **Cannot be interrupted.** All subscribers always execute.
- Subscribers MUST NOT mutate the Box content.
- Use for: logging, monitoring, memory writes, side-effect fanout.

```python
@lumia.event.consumer('cron.1h')
def cache_refresh(content: lumia.Box):
    PlCache.refresh(str(content.into()))

@lumia.event.consumer_re('msg.send, dest=3.11.group-*')
def send_qq(src: str, content: lumia.Box):
    gid = src.split('-')[1]
    qq = NapcatClient.ws.acq()
    qq.send(json.from_str(str(content.into())), gid)

# Emit
lumia.event.start(id=f'msg.send, dest=3.qq.group-{gid}', content=lumia.Box.any(msg))
```

#### 4.1.2 EventChain (Ordered Transform)
- Strict priority order, **cannot be interrupted**
- Subscribers MAY mutate the Box content before it reaches the next subscriber
- Use for: message preprocessing, metadata attachment, content normalization

(Registration API mirrors Event consumers; semantic difference is mutation permission.)

#### 4.1.3 Interceptor
- Executes **before** any Event consumer or EventChain handler for the matched id
- Higher `priv` executes first
- Calling `lumia.utils.intercept()` blocks the event entirely — no consumers execute
- Not calling `intercept()` allows the event to proceed normally

```python
@lumia.event.interceptor('bus.adapters.qq.find_active', priv=100)
def heartbeat(content: lumia.Box):
    lumia.system.adapters.heartbeat(str(content.into()), 'napcat-adapter-qq-1.0.29')
    # no intercept() call → event continues

@lumia.event.interceptor_re('bus.adapters.qq.find_old.*', priv=9999)
def stop_old(src: str, content: lumia.Box):
    if str(content.into()) < '1.0.29':
        lumia.utils.intercept()
```

### 4.2 ID Namespace Conventions

| Pattern | Meaning |
|---|---|
| `cron.1m` / `cron.1h` / `cron.1d` | Timer tick events |
| `msg.qq` | Raw incoming QQ message |
| `msg` | Normalized incoming message (all platforms) |
| `msg.send, dest=<pid>.<type>-<id>` | Outgoing message send request |
| `bus.adapters.<platform>.<action>` | Adapter internal bus |
| `bus.adapters.<platform>.<action>.*` | Adapter wildcard (use `_re` variant) |
| `memory.update` | Memory graph write event |
| `relation.update` | Relation graph write event |

`<pid>` = platform numeric id (3 = QQ); `<type>` = `group` / `private`; `<id>` = chat id.

### 4.3 Regex / Glob Variants

- `consumer_re` / `interceptor_re` / `pipe.on_re` accept glob-style patterns (`*` wildcard)
- Handlers using `_re` variants **MUST** declare `src: str` as first parameter
- `src` receives the full matched id string at call time
- Framework validates `src` presence at registration time; missing `src` → `RegistrationError`

```python
@lumia.event.consumer_re('msg.send, dest=3.11.group-*')
def send_qq(src: str, content: lumia.Box):
    gid = src.split('-')[1]   # extract group id from matched id
    ...
```

### 4.4 Lazy Parsing

Event ids are stored as raw strings at registration. The framework builds a routing index lazily on first dispatch. Glob patterns are compiled to `re.Pattern` at index-build time, not at registration time.

---

## 5. Core: Pipeline

### 5.1 Semantics

Pipeline is the **only** breakable message flow. A handler either:
- Calls `lumia.utils.next()` → execution passes to the next lower-priority handler
- Returns without calling `next()` → chain breaks; no further handlers execute

Side effects (e.g., pushing to context buffer) may occur before or after `next()` or on break.

### 5.2 Priority (`priv`)

Higher `priv` value = executes earlier. Ties resolved by registration order (first registered = higher effective priority).

### 5.3 API

```python
# Register handler
@lumia.pipe.on('msg', priv=50)
def handle_msg(content: lumia.Box):
    # process...
    lumia.utils.next()   # continue; omit to break chain

# Regex variant
@lumia.pipe.on_re('bus.adapters.qq.exp.*', priv=120)
def explore(src: str, content: lumia.Box):
    if not ready:
        lumia.utils.next()
        return
    NapcatClient.initialize()
    lumia.system.adapters.reg(f'qq-exp-{src.split(".")[4]}', 'napcat-adapter-qq-1.0.29')
    lumia.utils.next()

# Start a pipeline
lumia.pipe.start(id='msg', content=lumia.Box.any(raw_msg))
```

### 5.4 `lumia.utils`

Explicit utility functions; no implicit injection, no context magic.

```python
lumia.utils.next()        # Pipeline: pass to next handler
lumia.utils.intercept()   # Interceptor: block event from all consumers
```

---

## 6. Core: Event Provider

### 6.1 Role

Event Providers are plugins that act as **event sources**. They connect to external platforms, receive raw messages, and inject normalized events into the Lumia bus. They also consume outbound `msg.send` events to deliver replies.

### 6.2 Adapter Contract

An adapter plugin MUST:
1. Register itself via `lumia.system.adapters.reg(adapter_id, adapter_version)`
2. Emit heartbeats in response to `bus.adapters.<platform>.find_active`
3. Start the normalized `msg` pipeline on incoming messages
4. Consume `msg.send, dest=<pid>.<type>-<id>` events for outbound delivery
5. Attach `sender_embedding` to the message Box before starting the pipeline

```python
def on_receive(raw: dict):
    # Attach sender embedding before pipeline start
    raw['sender_embedding'] = embed_sync(raw['sender_id'])
    lumia.pipe.start(id='msg', content=lumia.Box.any(raw))
    lumia.event.start(id='msg.qq', content=lumia.Box.any(raw))

@lumia.event.consumer_re('msg.send, dest=3.qq.group-*')
def deliver(src: str, content: lumia.Box):
    gid = src.split('-')[1]
    NapcatClient.ws.acq().send(content.into(), gid)
```

---

## 7. Plugin System

### 7.1 Core Principles

- Every plugin is a **git repository** cloned into `plugins/<name>/`
- `plugins/` itself is a git repository (installation state is version-controlled)
- **git tag = version.** No separate version field in manifest. `pkg -S name@v1.2.3` checks out tag `v1.2.3`.
- Closed-source plugins may ship `.pyc` entry points; manifest declares `"main": "plugin.pyc"`
- Configuration is managed exclusively through the Lumia config API; plugins never read/write toml directly

### 7.2 manifest.json

```json
{
  "name": "heartflow",
  "display_name": "HeartFlow Main Responder",
  "description": "Multi-layer cognitive filter + heartflow LLM reply plugin",
  "author": "yourname",
  "license": "MIT",

  "main": "plugin.py",
  "min_core_version": "0.2.0",

  "dependencies": {
    "memory-graph": ">=0.2.0",
    "persona-loader": ">=0.1.0"
  },
  "provides": ["response"],
  "unique": ["response"],

  "source": {
    "type": "git",
    "url": "https://github.com/yourname/heartflow"
  },

  "config_schema": "config-schema.toml",
  "closed_source": false
}
```

#### `unique` Field Semantics

At load time, the framework scans all active plugins' `unique` arrays. If any unique domain appears in more than one plugin, the conflicting plugin is **rejected with a load error**. This is a framework-level guarantee — plugins do not declare conflicts against each other.

Example: only one plugin with `"unique": ["response"]` may be active at any time.

### 7.3 Directory Layout

```
<bot-root>/
├── plugins/                      ← git repo (tracks installed state)
│   ├── .git/
│   ├── heartflow/                ← cloned from github, checked out at tag v0.3.1
│   │   ├── .git/
│   │   ├── manifest.json
│   │   ├── plugin.py             ← entry point (or plugin.pyc for closed-source)
│   │   ├── config-schema.toml
│   │   └── hooks/
│   │       ├── pre_install.py
│   │       ├── post_install.py
│   │       ├── pre_upgrade.py
│   │       ├── post_upgrade.py
│   │       ├── pre_uninstall.py
│   │       └── post_uninstall.py
│   └── persona-loader/
│       ├── manifest.json
│       └── plugin.py
├── config/
│   ├── lumia.toml                ← core framework config
│   ├── heartflow.toml            ← auto-generated from config-schema.toml on install
│   └── persona-loader.toml
└── data/
    ├── pgdata/                   ← pgserver data directory
    └── shipyard/                 ← sandbox mount point
```

### 7.4 Lifecycle Hooks

Hooks are Python scripts executed at lifecycle transitions. The framework injects environment variables:

| Variable | Available In | Value |
|---|---|---|
| `PLUGIN_NAME` | all | plugin manifest name |
| `PLUGIN_VERSION` | all | current git tag |
| `PREV_VERSION` | upgrade | previous git tag |
| `BOT_ROOT` | all | absolute path to bot root |
| `PLUGIN_DIR` | all | absolute path to plugin directory |

Hook execution order:

```
Install:   pre_install.py  → git clone --branch <tag> --depth 1  → post_install.py  → load
Upgrade:   pre_upgrade.py  → git fetch && git checkout <new_tag>  → post_upgrade.py  → reload
Uninstall: pre_uninstall.py → unload → post_uninstall.py → rm -rf plugins/<name>  (config preserved)
```

Hook exit code != 0 aborts the operation with an error.

### 7.5 Plugin Entry Point

```python
# plugin.py
import lumia

# Config declaration — framework persists to config/<plugin>.toml
# Values accessible at runtime via lumia.config.get('<plugin>').<field>
lumia.config.declare('heartflow', {
    'trigger_threshold': lumia.config.field(float, default=0.65, desc="Engagement trigger threshold"),
    'attention_window':  lumia.config.field(int,   default=120,  desc="Attention window in seconds"),
    'planner_model':     lumia.config.field(str,   default='deepseek-chat'),
    'main_model':        lumia.config.field(str,   default='deepseek-reasoner'),
    'polish_model':      lumia.config.field(str,   default='gpt-4o-mini'),
})

def on_load():
    """Called after plugin is fully initialized."""
    ...

def on_unload():
    """Called before plugin is removed. Release resources."""
    ...

@lumia.pipe.on('msg', priv=50)
def handle(content: lumia.Box):
    ...
    lumia.utils.next()
```

---

## 8. Configuration System

### 8.1 Format

All configuration files are **TOML**, stored under `config/`. The framework owns file I/O; plugins access config exclusively through the Lumia config API.

### 8.2 Schema Declaration (`config-schema.toml`)

```toml
[trigger_threshold]
type = "float"
default = 0.65
description = "Score threshold above which the bot engages"
min = 0.0
max = 1.0

[attention_window]
type = "int"
default = 120
description = "Seconds the bot remains attentive after speaking"

[planner_model]
type = "str"
default = "deepseek-chat"
description = "Model identifier for the Planner layer"
```

On install, the framework generates `config/<plugin>.toml` with default values and inline comments from `description` fields.

### 8.3 Runtime Access

```python
cfg = lumia.config.get('heartflow')
threshold = cfg.trigger_threshold   # typed access, not dict lookup
cfg.trigger_threshold = 0.7         # write triggers immediate toml flush
```

---

## 9. Tool Execution & Sandbox

### 9.1 Sandbox: Shipyard

Lumia uses [AstrBotDevs/shipyard](https://github.com/AstrBotDevs/shipyard) as the isolated tool execution environment.

**Shipyard architecture:**
- **Bay:** Central orchestrator service. Manages Ship lifecycle, routes execution requests.
- **Ship:** Isolated container (Docker/Podman/Kubernetes). Runs a FastAPI service exposing Python, Shell, and FS APIs.
- **Session reuse:** Multiple sessions share a Ship instance; Ship auto-extends TTL on activity.
- **Persistence:** Host-mounted at `data/shipyard/ship_mnt_data/`; survives container restarts.

**Shipyard capabilities available to Lumia tools:**

| Tool | Shipyard API | Notes |
|---|---|---|
| Python executor | `python/execute` (IPython, persistent state) | Full stdlib + installed packages |
| Virtual bash | `shell/execute` | Standard shell commands |
| File system | `fs/create_file`, `fs/read_file`, `fs/write_file`, `fs/delete_file`, `fs/list_dir` | Sandboxed to session dir |
| TypeScript / Node.js | `shell/execute` + node pre-installed | Via shell |

### 9.2 Sandbox Constraint

**MCP servers CANNOT run inside Shipyard.** Shipyard provides isolated code execution; MCP protocol requires persistent server processes with their own lifecycle. MCP servers run outside the sandbox in the host process or a separate container.

### 9.3 Tool Execution Flow

```
Planner decides tool call needed
        │
        ├─ Tool is sandbox-safe (code exec, shell, fs)?
        │       → Shipyard session → execute → return result Box
        │
        └─ Tool requires external I/O / browser / API?
                → MCP client → MCP server (host-side) → return result Box
```

All tool results are wrapped in `Box` before being returned to the Planner context.

---

## 10. MCP Tool Design

### 10.1 MCP Constraint Summary

- MCP servers run **outside Shipyard**, on the host or in a dedicated sidecar container
- MCP is only accessible from the **Planner layer (L2) and above** — L0/L1 have no MCP access
- Each MCP tool call is gated by Planner's routing decision

### 10.2 Built-in MCP Tools (Host-side, Lumia-native)

#### 10.2.1 `lumia.mcp.python` — Sandboxed Python Executor

Bridges MCP calls to Shipyard's Python API.

```
Tool name:    python_exec
Input:        { "code": str, "session_id": str }
Output:       { "stdout": str, "stderr": str, "result": any }
Backend:      Shipyard ship/python/execute
Persistence:  IPython kernel state preserved within session
```

#### 10.2.2 `lumia.mcp.shell` — Sandboxed Shell

Bridges MCP calls to Shipyard's shell API.

```
Tool name:    shell_exec
Input:        { "command": str, "session_id": str }
Output:       { "stdout": str, "stderr": str, "exit_code": int }
Backend:      Shipyard ship/shell/execute
```

#### 10.2.3 `lumia.mcp.fs` — Sandboxed File System

```
Tool names:   fs_read, fs_write, fs_list, fs_delete
Input:        { "path": str, ... }
Backend:      Shipyard ship/fs/*
Scope:        Session working directory only; path traversal blocked
```

#### 10.2.4 `lumia.mcp.typescript` — TypeScript Executor

```
Tool name:    ts_exec
Input:        { "code": str, "session_id": str }
Output:       { "stdout": str, "stderr": str }
Backend:      shell_exec with `npx tsx -e "<code>"`
Runtime:      Node.js + tsx pre-installed in Shipyard ship image
```

#### 10.2.5 `lumia.mcp.browser` — Puppeteer Browser Automation

Runs **outside Shipyard** (requires persistent Chromium process). Dedicated sidecar container.

```
Tool name:    browser_navigate
Input:        { "url": str }
Output:       { "title": str, "text": str, "html": str }

Tool name:    browser_click
Input:        { "selector": str }
Output:       { "success": bool }

Tool name:    browser_type
Input:        { "selector": str, "text": str }
Output:       { "success": bool }

Tool name:    browser_screenshot
Input:        { "full_page": bool }
Output:       { "image_base64": str }

Tool name:    browser_eval
Input:        { "js": str }
Output:       { "result": any }
```

**MCP ↔ Puppeteer interaction design:**

The Planner does NOT issue raw browser commands. Instead, it declares a **high-level goal**:

```json
{
  "goal": "Find the current price of item X on site Y",
  "start_url": "https://example.com",
  "extraction_schema": { "price": "string", "currency": "string" }
}
```

A dedicated `browser_agent` loop within the MCP server:
1. Receives goal + schema
2. Executes a micro-agentic loop (navigate → screenshot → decide next action → repeat)
3. Returns structured result matching `extraction_schema`
4. Planner receives clean data, not raw DOM

This isolates the browser complexity from the Planner's reasoning loop.

**Session management:**
- Browser sessions persist for the duration of a Planner task (not per-message)
- Session TTL: 5 minutes idle → auto-close
- Max concurrent sessions: configurable, default 3

#### 10.2.6 `lumia.mcp.web_search` — Web Search

```
Tool name:    web_search
Input:        { "query": str, "max_results": int (default 5) }
Output:       { "results": [{ "title", "url", "snippet" }] }
Backend:      Configurable (SearXNG self-hosted recommended; or API key based)
```

#### 10.2.7 `lumia.mcp.memory_query` — Direct Memory Graph Query

Allows Planner to explicitly query the memory graph beyond what the automatic RAG injection provides.

```
Tool name:    memory_query
Input:        { "query": str, "sender_id": str | null, "top_k": int }
Output:       { "topics": [...], "instances": [...] }
Backend:      pgvector HNSW + spreading activation (see §11)
```

### 10.3 MCP Server Lifecycle

```
lumia.system.mcp.register(server_name, command, args, env)
  → spawns MCP server subprocess (host-side)
  → maintains stdio/SSE transport
  → auto-restarts on crash (max 3 retries, then disable)

lumia.system.mcp.call(server_name, tool_name, input_dict)
  → returns result dict
  → timeout: 30s default, configurable per tool
```

---

## 11. Memory System

### 11.1 Storage Backend

**pgserver** — portable PostgreSQL with pgvector.

```python
import pgserver
db = pgserver.get_server("./data/pgdata")
db.psql('CREATE EXTENSION IF NOT EXISTS vector')
uri = db.get_uri()
```

No manual PostgreSQL installation required. `pip install pgserver` bundles platform-specific binaries. Multiple processes sharing the same data directory are handled safely.

### 11.2 Schema: Topic-Instance-Edge Graph

Three-layer graph structure:

**`memory_topics`** — Concept nodes
```sql
id              TEXT PRIMARY KEY
topic_name      TEXT NOT NULL
topic_embedding vector(1536) NOT NULL     -- HNSW indexed
strength        FLOAT DEFAULT 1.0         -- [0, 1]
decay_rate      FLOAT DEFAULT 0.1
half_life_days  FLOAT DEFAULT 7.0
access_count    INTEGER DEFAULT 0
last_accessed   TIMESTAMP DEFAULT NOW()
created_at      TIMESTAMP DEFAULT NOW()
metadata        JSONB DEFAULT '{}'
```

**`memory_instances`** — Specific memory records under a topic
```sql
id                TEXT PRIMARY KEY
topic_id          TEXT REFERENCES memory_topics(id) ON DELETE CASCADE
content           TEXT NOT NULL
content_embedding vector(1536) NOT NULL   -- HNSW indexed
relevance_score   FLOAT DEFAULT 1.0
importance        FLOAT DEFAULT 0.5
created_at        TIMESTAMP DEFAULT NOW()
last_accessed     TIMESTAMP DEFAULT NOW()
metadata          JSONB DEFAULT '{}'
```

**`topic_edges`** — Associations between topics
```sql
id               TEXT PRIMARY KEY
from_topic       TEXT REFERENCES memory_topics(id) ON DELETE CASCADE
to_topic         TEXT REFERENCES memory_topics(id) ON DELETE CASCADE
weight           FLOAT DEFAULT 1.0         -- [0, 1], HNSW-style
edge_type        TEXT DEFAULT 'semantic'
activation_count INTEGER DEFAULT 0
last_activated   TIMESTAMP DEFAULT NOW()
decay_rate       FLOAT DEFAULT 0.05
UNIQUE (from_topic, to_topic)
```

### 11.3 Retrieval: RAG + Spreading Activation

```
Input: query_text, sender_id (optional), top_k=10

Step 1 — Encode
  query_embedding = embed(query_text)

Step 2 — Vector search (HNSW cosine)
  seed_topics = SELECT top-20 from memory_topics
                ORDER BY cosine_similarity(topic_embedding, query_embedding) DESC
  Filter by sender_id in metadata if provided (avoids cross-person confusion)

Step 3 — Spreading Activation
  frontier = seed_topics
  visited  = {}
  FOR depth in [1, 2]:
    FOR topic in frontier:
      neighbors = topic_edges WHERE from_topic=topic.id AND weight >= 0.3
      score[neighbor] = score[topic] * edge.weight * (0.5 ** depth)
      frontier = neighbors not in visited

Step 4 — Rank & fetch
  all_candidates = seed_topics ∪ spread_topics, ranked by combined score
  top_topics      = all_candidates[:top_k]
  instances       = SELECT from memory_instances WHERE topic_id IN top_topics
                    ORDER BY relevance_score DESC LIMIT top_k

Step 5 — strengthen_memory() for each accessed topic
  strength    = MIN(strength + 0.1, 1.0)
  access_count += 1
  last_accessed = NOW()
  half_life_days *= 1.1
```

### 11.4 Forgetting Mechanism

**Decay formula:** `S(t) = S₀ × (0.5)^(t / half_life_days)`

**Eviction criteria** (run via `cron.1d` event):
- `strength < 0.05` AND
- `last_accessed < NOW() - 30 days` AND
- `access_count < 5`

Edge weights decay independently with `decay_rate=0.05`, half-life 7 days.

### 11.5 Sender Embedding

Each `memory_instance` stores the `sender_id` in `metadata`. Retrieval queries that include `sender_id` filter at the topic level to prioritize memories associated with that person, reducing cross-person conflation.

---

## 12. Heartflow Plugin — Message Processing Chain

### 12.1 Pipeline Overview

Pipeline id: `msg`

```
priv=200  L0 Logic Filter
priv=100  L1 Small Model Perception
priv=50   L2 Planner
priv=10   L3 Heartflow LLM
```

### 12.2 L0 — Logic Filter (`priv=200`)

**Cost:** Zero tokens. Pure rule evaluation.

**Rules (evaluated in order, first fail = break chain silently):**
1. Bot on cooldown (< min_reply_interval since last send) → break
2. Sender in blacklist → break
3. Message type not handled (e.g., raw file, unsupported media) → break
4. Message rate from sender exceeds rate limit → break
5. `@bot` mention present → set `force_engage=True` on Box metadata, `next()`
6. All rules pass → `next()`

On break: no context buffer push, no logging (silent drop).

### 12.3 L1 — Small Model Perception (`priv=100`)

**Cost:** Minimal tokens (single classify call, skipped entirely on low cosine).

**State read:** `PlannerState.attention_vector` for the current group.

**Processing:**

```
Step 1 — Cosine pre-filter
  sim = cosine(msg_embedding, planner.attention_vector)
  IF sim < cosine_threshold AND NOT force_engage:
    push_to_context_buffer(msg, compressed=True)
    break                              ← silent accumulate, no LLM call

Step 2 — Small model score
  score = small_model.classify(msg, context_summary, persona_hint)
  # Returns relevance_score: float in [0, 1]

Step 3 — Dynamic threshold check
  threshold = base_threshold
  IF now() < planner.attention_window_end:
    threshold *= 0.7                   ← lower threshold during attention window
  IF score > threshold OR force_engage:
    next()                             ← pass to Planner
  ELSE:
    push_to_context_buffer(msg, compressed=True)
    break
```

### 12.4 L2 — Planner (`priv=50`)

**Cost:** Medium tokens. Per-group stateful instance.

#### Planner State

```python
@dataclass
class PlannerState:
    group_id: str
    attention_vector: list[float]       # current topic focus embedding
    attention_window_end: datetime      # when reduced-threshold window expires
    dynamic_threshold: float            # current L1 trigger threshold
    context_buffer: list[ContextEntry]  # gradient-compressed message history
```

#### Context Buffer Gradient

```
Most recent k messages        → stored verbatim
Messages k to 3k              → paragraph-level compression
                                (speaker, emotion, key event retained)
Messages older than 3k        → topic-level summary only
                                (topic + major turning points)
```

Compression is performed by a dedicated small model on a `cron.15m` event.

#### Routing Decision

```
Receive message + context package
  │
  ├─ Needs external data?
  │    → lumia.system.mcp.call('web_search', ...)  or  mcp.call('browser', ...)
  │    → attach results to context
  │
  ├─ Needs deep reasoning?
  │    → lumia.system.mcp.call('thinker', ...)     ← dedicated reasoning model
  │    → attach chain-of-thought summary to context
  │
  └─ Ready to engage
       → pack ContextPackage → next()
```

#### ContextPackage (passed to L3 via Box)

```json
{
  "group_id": "...",
  "recent_messages": [...],
  "context_summary": "...",
  "memory_rag": [...],
  "hint_injections": [...],
  "tool_results": [...],
  "sender_profile": { "id": "...", "relation_summary": "..." },
  "force_engage": false
}
```

#### Attention Update

After `next()`, Planner listens to the `memory.update` event and updates `attention_vector` using the `attention_shift` returned by L3.

### 12.5 L3 — Heartflow LLM (`priv=10`)

**Cost:** High tokens. The main consciousness step.

**Input:** ContextPackage (from Box), persona system prompt, memory RAG results.

**Output (structured JSON):**

```json
{
  "reply_bias": {
    "intent": "curious follow-up",
    "emotion": "light, slightly excited",
    "key_points": ["want to know about X", "can mention Y"],
    "persona_hint": "can be playful"
  },
  "memory_updates": [
    { "action": "upsert", "topic": "...", "content": "...", "importance": 0.7 }
  ],
  "relation_updates": [
    { "from": "user_a", "to": "self", "type": "friend", "weight_delta": 0.05 }
  ],
  "attention_shift": [0.1, -0.3, ...]
}
```

After output:
- `reply_bias` → passed to Polish LLM via `lumia.pipe.start('reply.polish', ...)`
- `memory_updates` → `lumia.event.start('memory.update', ...)`
- `relation_updates` → `lumia.event.start('relation.update', ...)`
- `attention_shift` → attached to Box metadata, consumed by Planner after chain

### 12.6 Polish LLM (sub-pipeline: `reply.polish`)

**Input:** `reply_bias` + original message + full persona system prompt + knowledge base HNSW results.

**Output:** Final natural language reply string.

**Rationale for separation:** Thinking (L3) and expression (Polish) are decoupled. Changing speaking style only requires replacing the Polish LLM prompt or model. The `reply_bias` itself can be stored as memory — it is higher information density than storing the verbatim reply text.

Polish LLM sends reply via:
```python
lumia.event.start(
    id=f'msg.send, dest=3.qq.group-{group_id}',
    content=lumia.Box.any(reply_text)
)
```

### 12.7 Context Hint Mechanism

#### Purpose
Surface contextually relevant "noteworthy points" from history into the current prompt without accumulating stale hints across turns.

#### Hint Storage
Lightweight KV store (not the memory graph). Key: `hint:<hash>`. Value: hint text + TTL + embedding.

#### Injection Flow

```
Build prompt for L3:
  Step 1 — embedding similarity search over hint KV
            query = current message embedding
            candidates = top-5 by cosine similarity

  Step 2 — hash match
            exact hash lookup for known commitments / scheduled events
            (handles semantic variants that embedding might miss)

  Step 3 — merge, deduplicate, take top-N

  Step 4 — inject as [HINT] block in L3 system prompt

  Step 5 — clear previous turn's injected hints from KV
            (prevents unbounded accumulation)
```

#### Hint Production
L2 Planner and L3 may produce new hints as a side-effect:
```json
{ "hint": "User mentioned meeting on Friday", "ttl_hours": 48, "hash": "sha256:..." }
```

#### Dual-path Rationale
- **Embedding only:** misses precise commitments ("meet Friday" may match unrelated Friday events)
- **Hash only:** misses rephrased variants ("next Friday" vs "this Friday evening")
- **Both:** complementary coverage

---

## 13. Registry & pkg CLI

### 13.1 Registry

Cloudflare Worker. Stores metadata only. Package bodies remain on GitHub/Gitea.

**Endpoints:**

```
GET /search?q=<keyword>[&page=<n>]
→ [{ name, display_name, description, author, git_url, latest_tag, stars }]

GET /pkg/<name>
→ { manifest, readme_md, versions: [{ tag, date, changelog }] }

POST /pkg (authenticated)
→ Submit new plugin or version (PR-based, human review)
```

Worker goes down → install still works via `git clone <url> --branch <tag>`.

### 13.2 pkg CLI Reference

```
INSTALL / REMOVE
  pkg -S <name>              Install latest tagged version
  pkg -S <name>@<tag>        Install specific version
  pkg -S <n1> <n2> ...       Install multiple plugins
  pkg -R <name>              Uninstall plugin (config preserved)
  pkg -R <name> --purge      Uninstall + delete config

UPGRADE
  pkg -U                     Upgrade all installed plugins
  pkg -U <name>              Upgrade specific plugin
  pkg -U --dry-run           Show what would be upgraded

QUERY
  pkg -Q                     List all installed plugins (name, version, status)
  pkg -Ql <name>             List files in plugin directory
  pkg -Ss <keyword>          Search registry
  pkg -Si <name>             Show plugin info (manifest + versions)

MAINTENANCE
  pkg -Sc                    Clear download cache

DEVELOPMENT
  pkg dev init <name>        Scaffold new plugin (manifest + plugin.py + hooks + schema)
  pkg dev validate           Run ruff + Box type check + Arc path check
  pkg dev pack               Compile to .pyc for closed-source distribution
  pkg dev publish            Submit to registry (opens PR)
  pkg dev run                Hot-reload test in sandboxed subprocess
  pkg dev run --watch        File watcher + auto-reload
```

### 13.3 Version Resolution

```
pkg -S heartflow
  → GET /pkg/heartflow → latest_tag
  → git clone <git_url> --branch <latest_tag> --depth 1 plugins/heartflow/

pkg -S heartflow@v0.3.1
  → git clone <git_url> --branch v0.3.1 --depth 1 plugins/heartflow/

pkg -U heartflow
  → GET /pkg/heartflow → latest_tag
  → IF latest_tag != current_tag:
      run pre_upgrade hook
      git -C plugins/heartflow fetch --tags
      git -C plugins/heartflow checkout <latest_tag>
      run post_upgrade hook
      reload plugin
```

---

## 14. Quality & Validation

### 14.1 `pkg dev validate` — Three-Layer Check

**Layer 1: ruff**
```
ruff check .
ruff format --check .
```
Standard Python linting + formatting. Config in `pyproject.toml` or `ruff.toml` at plugin root.

**Layer 2: Box type alignment (Lumia static analyzer)**

AST scan of plugin source:
- For each `Box.any(x)`: record inferred type of `x`
- For each `.into()` call site: record expected type from usage context
- Cross-reference: `Box.any(T)` must be compatible with downstream `.into()` expected type
- Report mismatch as error with file + line

**Layer 3: Arc path check**

- Detect types that are known non-serializable (inherit from `socket.socket`, `io.RawIOBase`, open file handles, etc.)
- Verify they are only passed via `Box.any()` (Arc path), never via dill-serialized Box
- Verify no Arc-path Box is held by the resource itself (cycle check via AST reference graph)

### 14.2 Plugin Signing (Optional)

Public plugins may submit an Ed25519 signature in the registry. `pkg -S` verifies signature if present. Unsigned plugins install with a warning. Closed-source plugins are encouraged to sign `.pyc` artifacts.

---

## 15. Technology Stack

| Component | Technology | Notes |
|---|---|---|
| IM protocol | NapCat / Lagrange + OneBot v11 | QQ adapter |
| Framework core | Python 3.11+ | Lumia |
| Serialization | dill | All Box dill-path transfers |
| Vector database | pgserver (PostgreSQL 16 + pgvector) | `pip install pgserver` |
| Vector index | HNSW (pgvector) | m=16, ef_construction=64 |
| Sandbox | AstrBotDevs/shipyard | Docker/Podman/K8s |
| Browser automation | Puppeteer (Node.js) | Outside sandbox, sidecar |
| Small model | Qwen2.5-3B (quantized) or equiv | L1 perception, compression |
| Planner / L3 LLM | Deepseek / Claude / GPT-4o | Configurable per plugin |
| Thinker | Deepseek-R1 or equiv reasoning model | On-demand |
| Code quality | ruff + Lumia analyzer | `pkg dev validate` |
| Plugin registry | Cloudflare Worker + GitHub | Metadata edge, bodies on git |
| Plugin versioning | git tags | tag = semver version |
| Config format | TOML | `config/<plugin>.toml` |
| TypeScript runtime | Node.js + tsx (in Shipyard image) | For ts_exec MCP tool |

---

*End of LUMIA-SPEC-001*
