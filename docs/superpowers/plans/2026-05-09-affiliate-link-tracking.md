# Affiliate Link Tracking Implementation Plan (v3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a tracker-driven affiliate link tracker. Two main user-facing scripts in `yt-analysis/`:
1. `process_yt_tracker.py` — for rows where `topic_status="To Process"`, uses LLM to detect tools, registers short URLs in D1+KV, writes `actual_links` + `short_links` columns + LLM-generated `video_description` to YT tracker.
2. `yt_analysis.py` — interactive orchestrator. Asks user what to sync (metadata, views, affiliate clicks, rank analysis). Filters by `yt_upload_status="uploaded"`. Calls helper modules.

**Architecture:** TypeScript Worker on Cloudflare reads `slug → target_url` from KV (the only redirect-path dependency) and fire-and-forget logs clicks to D1 via `ctx.waitUntil()`. Python scripts use Gemini for LLM tasks, Cloudflare REST API for D1+KV, gspread for sheets.

**Tech Stack:** TypeScript (Worker), Cloudflare Workers/KV/D1, Wrangler 3.x, Vitest. Python with gspread, requests, pytest, pytest-mock, google-genai. (Spec: `docs/superpowers/specs/2026-05-09-affiliate-link-tracking-design.md`.)

---

## Prerequisites (USER-SIDE, before Task 1)

These are NOT plan tasks — the user must complete them first.

1. Cloudflare account (free) at https://dash.cloudflare.com
2. Add `agrolloo.com` to Cloudflare; verify DNS records imported
3. At domain registrar, switch nameservers to Cloudflare's two (24–48h propagation)
4. `npm install -g wrangler@3 && wrangler --version` — confirm 3.x
5. `wrangler login`
6. CF API token at https://dash.cloudflare.com/profile/api-tokens with `D1:Edit` + `Workers KV Storage:Edit`
7. Copy `Account ID` from CF dashboard (right sidebar)
8. Confirm `myproj/credentials.json` exists; service account has read access to YT tracker, Affiliate Programs, and Analysis sheets

---

## File structure (final)

```
myproj/
├── prompts/                            # NEW
│   ├── detect-tools.md
│   └── generate-description.md
├── workers/
│   └── redirector/
│       ├── wrangler.toml, package.json, tsconfig.json, vitest.config.ts, .gitignore
│       ├── src/index.ts                # ~80 lines
│       ├── test/slug.test.ts
│       └── migrations/0001_init.sql
├── common/
│   ├── cloudflare.py                   # NEW
│   ├── affiliate.py                    # NEW
│   ├── llm.py                          # NEW
│   ├── gemini.py                       # existing
│   ├── sheets.py                       # existing
│   └── env.py                          # existing
├── yt-analysis/
│   ├── yt_analysis.py                  # NEW: interactive orchestrator (main entry)
│   ├── process_yt_tracker.py           # NEW: tracker → URLs + description
│   ├── sync_metadata.py                # MODIFIED (renamed from sync_analysis.py)
│   ├── sync_views.py                   # MODIFIED (refactored to expose function)
│   ├── sync_clicks.py                  # NEW: fills affiliate_link_clicks column
│   ├── sync_rankings.py                # UNTOUCHED
│   └── tests/
│       ├── __init__.py, conftest.py
│       ├── test_cloudflare.py
│       ├── test_affiliate.py
│       ├── test_llm.py
│       ├── test_process_yt_tracker.py
│       ├── test_sync_metadata.py       # tests for the refactored module
│       ├── test_sync_clicks.py
│       └── test_yt_analysis.py
├── .env, .env.example                  # MODIFIED
├── .gitignore                          # MODIFIED
└── requirements.txt                    # MODIFIED
```

Manual sheet edits (not code, in Task 14):
- **YT tracker** `Master` tab — add three new headers in row 1: `video_notes`, `actual_links`, `short_links`
- **Analysis sheet** `Per video cost,views and clicks` tab — add two new headers: `video_notes`, `yt_upload_status`

---

## Task 1: Test infrastructure + new env vars

**Files:**
- Modify: `requirements.txt`, `.env`, `.env.example`
- Create: `yt-analysis/tests/__init__.py`, `yt-analysis/tests/conftest.py`

- [ ] **Step 1.1: Add Python test deps**

Append to `requirements.txt`:
```
pytest==8.3.4
pytest-mock==3.14.0
requests==2.32.3
```

- [ ] **Step 1.2: Install**

```bash
cd /Users/kbtg/codebase/myproj && source venv/bin/activate && pip install -q -r requirements.txt && pytest --version
```
Expected: `pytest 8.3.4`.

- [ ] **Step 1.3: Add CF env vars to .env**

Append to `myproj/.env`:
```
CF_API_TOKEN=<FILL_IN>
CF_ACCOUNT_ID=<FILL_IN>
CF_D1_DATABASE_ID=<FILL_IN_AFTER_TASK_3>
CF_KV_NAMESPACE_ID=<FILL_IN_AFTER_TASK_3>
LINK_DOMAIN=go.agrolloo.com
```

- [ ] **Step 1.4: Mirror placeholders in .env.example**

```
CF_API_TOKEN=your_cloudflare_api_token
CF_ACCOUNT_ID=your_cloudflare_account_id
CF_D1_DATABASE_ID=your_d1_database_id
CF_KV_NAMESPACE_ID=your_kv_namespace_id
LINK_DOMAIN=go.yourdomain.com
```

- [ ] **Step 1.5: Tests dir + conftest**

Create `yt-analysis/tests/__init__.py` (empty).

Create `yt-analysis/tests/conftest.py`:
```python
"""Add myproj root to sys.path so `from common.x import y` works in tests."""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
```

- [ ] **Step 1.6: Verify**

```bash
pytest yt-analysis/tests -v
```
Expected: "no tests ran".

- [ ] **Step 1.7: Commit**

```bash
git add requirements.txt .env.example yt-analysis/tests/__init__.py yt-analysis/tests/conftest.py
git commit -m "chore: pytest infra + CF link-tracker env placeholders"
```

---

## Task 2: `common/affiliate.py` (TDD)

**Files:**
- Create: `yt-analysis/tests/test_affiliate.py`, `common/affiliate.py`

(Identical to v2 — see prior plan revision; reproduced fully here for self-containment.)

- [ ] **Step 2.1: Tests for `normalize_tool_name`**

Create `yt-analysis/tests/test_affiliate.py`:
```python
"""Tests for common.affiliate."""

import os
import pytest

from common.affiliate import AffiliateRecord, normalize_tool_name


class TestNormalizeToolName:
    def test_lowercases(self):
        assert normalize_tool_name("Heygen") == "heygen"
    def test_replaces_spaces_with_hyphens(self):
        assert normalize_tool_name("envato elements") == "envato-elements"
    def test_collapses_multi_spaces(self):
        assert normalize_tool_name("envato   elements") == "envato-elements"
    def test_strips_outer_whitespace(self):
        assert normalize_tool_name("  invideo ai  ") == "invideo-ai"
    def test_keeps_digits(self):
        assert normalize_tool_name("10web") == "10web"
    def test_strips_special_chars(self):
        assert normalize_tool_name("invideo.ai!") == "invideo-ai"
    def test_empty_raises(self):
        with pytest.raises(ValueError):
            normalize_tool_name("")
```

- [ ] **Step 2.2: Run, expect ImportError**

`pytest yt-analysis/tests/test_affiliate.py -v`

- [ ] **Step 2.3: Implement minimal `common/affiliate.py`**

Create `common/affiliate.py`:
```python
"""Affiliate Programs sheet reader + tool name normalization."""

import os
import re
from dataclasses import dataclass

from .sheets import extract_sheet_id, get_gspread_client


@dataclass(frozen=True)
class AffiliateRecord:
    tool: str
    display_name: str
    target_url: str
    approval_status: str
    coupon_status: str
    coupon_code: str

    @property
    def is_approved(self) -> bool:
        return self.approval_status.strip().lower() == "approved"


def normalize_tool_name(name: str) -> str:
    if not name or not name.strip():
        raise ValueError("Tool name is empty")
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

- [ ] **Step 2.4: Run tests** — Expected: 7 passed.

- [ ] **Step 2.5: Tests for `load_affiliate_records`**

Append to test file:
```python
class TestLoadAffiliateRecords:
    @pytest.fixture
    def fake_sheet_rows(self):
        return [
            ["Affiliate Program", "Where", "", "Approval Status",
             "My Affiliate Link", "Coupon Status", "Coupon Code", "Notes"],
            ["heygen", "Impact.com", "", "Approved",
             "https://heygen.sjv.io/abc", "code received", "HEY30", ""],
            ["envato elements", "Impact.com", "", "Approved",
             "https://elements.envato.com/aff?id=1", "Occassional Code", "", ""],
            ["pending tool", "Impact.com", "", "Pending",
             "https://example.com/aff", "", "", ""],
        ]

    def test_loads_and_normalizes_keys(self, mocker, fake_sheet_rows):
        from common import affiliate
        ws = mocker.MagicMock()
        ws.get_all_values.return_value = fake_sheet_rows
        sh = mocker.MagicMock()
        sh.worksheet.return_value = ws
        client = mocker.MagicMock()
        client.open_by_key.return_value = sh
        mocker.patch("common.affiliate.get_gspread_client", return_value=client)
        mocker.patch("common.affiliate.extract_sheet_id", return_value="SHEET_ID")
        mocker.patch.dict(os.environ, {"AFFILIATE_PROGRAMS_SHEET_URL": "x"})

        records = affiliate.load_affiliate_records()
        assert "heygen" in records
        assert records["heygen"].is_approved is True
        assert records["heygen"].coupon_code == "HEY30"
        assert "envato-elements" in records
        assert records["pending-tool"].is_approved is False

    def test_raises_when_env_var_missing(self, mocker):
        from common import affiliate
        mocker.patch.dict(os.environ, {}, clear=True)
        with pytest.raises(RuntimeError, match="AFFILIATE_PROGRAMS_SHEET_URL"):
            affiliate.load_affiliate_records()
```

- [ ] **Step 2.6: Run, expect failure**

- [ ] **Step 2.7: Implement `load_affiliate_records`**

Append to `common/affiliate.py`:
```python
def load_affiliate_records() -> dict[str, AffiliateRecord]:
    sheet_url = os.getenv("AFFILIATE_PROGRAMS_SHEET_URL")
    if not sheet_url:
        raise RuntimeError("AFFILIATE_PROGRAMS_SHEET_URL not set in .env")

    client = get_gspread_client()
    ws = client.open_by_key(extract_sheet_id(sheet_url)).worksheet("Sheet1")
    rows = ws.get_all_values()
    if not rows or len(rows) < 2:
        return {}

    header = [h.strip() for h in rows[0]]
    idx = {h: i for i, h in enumerate(header)}

    def cell(row, col):
        i = idx.get(col)
        return row[i].strip() if i is not None and i < len(row) else ""

    records = {}
    for row in rows[1:]:
        display = cell(row, "Affiliate Program")
        if not display:
            continue
        try:
            slug = normalize_tool_name(display)
        except ValueError:
            continue
        records[slug] = AffiliateRecord(
            tool=slug, display_name=display,
            target_url=cell(row, "My Affiliate Link"),
            approval_status=cell(row, "Approval Status"),
            coupon_status=cell(row, "Coupon Status"),
            coupon_code=cell(row, "Coupon Code"),
        )
    return records
```

- [ ] **Step 2.8: Run all** — Expected: 9 passed.

- [ ] **Step 2.9: Commit**

```bash
git add common/affiliate.py yt-analysis/tests/test_affiliate.py
git commit -m "feat(common): affiliate.py — sheet reader + tool name normalization"
```

---

## Task 3: Worker scaffolding + KV namespace + D1 database

**Files:**
- Create: `workers/redirector/{package.json, tsconfig.json, .gitignore, wrangler.toml}`
- Modify: root `.gitignore`

- [ ] **Step 3.1: Init project**

```bash
mkdir -p /Users/kbtg/codebase/myproj/workers/redirector
cd /Users/kbtg/codebase/myproj/workers/redirector
```

Create `workers/redirector/package.json`:
```json
{
  "name": "redirector",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "wrangler dev",
    "deploy": "wrangler deploy",
    "test": "vitest run",
    "typecheck": "tsc --noEmit"
  },
  "devDependencies": {
    "@cloudflare/workers-types": "^4.20250101.0",
    "typescript": "^5.7.0",
    "vitest": "^2.1.0",
    "wrangler": "^3.95.0"
  }
}
```

Create `workers/redirector/tsconfig.json`:
```json
{
  "compilerOptions": {
    "target": "ES2022", "module": "ES2022", "moduleResolution": "Bundler",
    "lib": ["ES2022"], "types": ["@cloudflare/workers-types"],
    "strict": true, "noEmit": true,
    "esModuleInterop": true, "skipLibCheck": true
  },
  "include": ["src/**/*", "test/**/*"]
}
```

Create `workers/redirector/.gitignore`:
```
node_modules
.wrangler
.dev.vars
*.log
```

- [ ] **Step 3.2: Install Worker deps**

```bash
npm install --silent
```

- [ ] **Step 3.3: Add to root .gitignore**

Append to `myproj/.gitignore`:
```

# Worker (workers/redirector)
workers/redirector/node_modules/
workers/redirector/.wrangler/
workers/redirector/.dev.vars
```

- [ ] **Step 3.4: Create KV namespace**

```bash
wrangler kv namespace create CLICKS_KV
```
Save `id` to `myproj/.env` as `CF_KV_NAMESPACE_ID=...`.

- [ ] **Step 3.5: Create D1 database**

```bash
wrangler d1 create clicks-db
```
Save `database_id` to `myproj/.env` as `CF_D1_DATABASE_ID=...`.

- [ ] **Step 3.6: Write `wrangler.toml`**

Create `workers/redirector/wrangler.toml` (replace `<KV_ID>` and `<D1_ID>`):
```toml
name = "redirector"
main = "src/index.ts"
compatibility_date = "2025-04-01"

[[kv_namespaces]]
binding = "CLICKS_KV"
id = "<KV_ID>"

[[d1_databases]]
binding = "DB"
database_name = "clicks-db"
database_id = "<D1_ID>"

[observability]
enabled = true
```

- [ ] **Step 3.7: Verify**

```bash
wrangler whoami
cat wrangler.toml
```

- [ ] **Step 3.8: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/package.json workers/redirector/tsconfig.json \
        workers/redirector/.gitignore workers/redirector/wrangler.toml \
        .gitignore
git commit -m "chore(worker): scaffold + create KV namespace + D1 database"
```

---

## Task 4: D1 schema migration

- [ ] **Step 4.1: Write migration**

Create `workers/redirector/migrations/0001_init.sql`:
```sql
CREATE TABLE IF NOT EXISTS videos (
  video_code   TEXT PRIMARY KEY,
  video_title  TEXT NOT NULL,
  created_at   INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS links (
  slug         TEXT PRIMARY KEY,
  video_code   TEXT NOT NULL,
  tool         TEXT NOT NULL,
  target_url   TEXT NOT NULL,
  created_at   INTEGER NOT NULL,
  FOREIGN KEY (video_code) REFERENCES videos(video_code)
);
CREATE INDEX IF NOT EXISTS idx_links_video_code ON links(video_code);

CREATE TABLE IF NOT EXISTS clicks (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  slug         TEXT NOT NULL,
  clicked_at   INTEGER NOT NULL,
  ip_hash      TEXT,
  ua_hash      TEXT,
  referer      TEXT
);
CREATE INDEX IF NOT EXISTS idx_clicks_slug_ts ON clicks(slug, clicked_at);
```

- [ ] **Step 4.2: Apply**

```bash
cd workers/redirector
wrangler d1 execute clicks-db --remote --file=migrations/0001_init.sql
```

- [ ] **Step 4.3: Verify**

```bash
wrangler d1 execute clicks-db --remote --command="SELECT name FROM sqlite_master WHERE type='table';"
```
Expected: `videos`, `links`, `clicks`.

- [ ] **Step 4.4: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/migrations/0001_init.sql
git commit -m "feat(worker): D1 schema migration"
```

---

## Task 5: `common/cloudflare.py` (TDD)

**Files:**
- Create: `yt-analysis/tests/test_cloudflare.py`, `common/cloudflare.py`

- [ ] **Step 5.1: Failing tests**

Create `yt-analysis/tests/test_cloudflare.py`:
```python
"""Tests for common.cloudflare REST clients."""

import os
import pytest

from common.cloudflare import D1Client, KVClient


@pytest.fixture
def cf_env(mocker):
    mocker.patch.dict(os.environ, {
        "CF_API_TOKEN": "test-token",
        "CF_ACCOUNT_ID": "test-account",
        "CF_D1_DATABASE_ID": "test-d1",
        "CF_KV_NAMESPACE_ID": "test-kv",
    }, clear=False)


class TestD1Client:
    def test_query_posts_correct_url(self, mocker, cf_env):
        mock_post = mocker.patch("common.cloudflare.requests.post")
        mock_post.return_value.json.return_value = {
            "success": True,
            "result": [{"results": [{"slug": "a/b"}], "success": True}],
        }
        mock_post.return_value.raise_for_status.return_value = None

        client = D1Client()
        result = client.query("SELECT * FROM links WHERE slug = ?", ["a/b"])

        url = mock_post.call_args[0][0]
        assert "accounts/test-account/d1/database/test-d1/query" in url
        body = mock_post.call_args.kwargs["json"]
        assert body == {"sql": "SELECT * FROM links WHERE slug = ?", "params": ["a/b"]}
        assert result == [{"slug": "a/b"}]

    def test_query_raises_on_api_error(self, mocker, cf_env):
        mock_post = mocker.patch("common.cloudflare.requests.post")
        mock_post.return_value.json.return_value = {
            "success": False, "errors": [{"message": "syntax error"}]
        }
        mock_post.return_value.raise_for_status.return_value = None
        client = D1Client()
        with pytest.raises(RuntimeError, match="syntax error"):
            client.query("BAD SQL")


class TestKVClient:
    def test_put_sends_to_correct_url(self, mocker, cf_env):
        mock_put = mocker.patch("common.cloudflare.requests.put")
        mock_put.return_value.json.return_value = {"success": True}
        mock_put.return_value.raise_for_status.return_value = None

        client = KVClient()
        client.put("a/b", "https://target")

        url = mock_put.call_args[0][0]
        assert "accounts/test-account/storage/kv/namespaces/test-kv/values/a%2Fb" in url
        assert mock_put.call_args.kwargs["data"] == "https://target"
```

- [ ] **Step 5.2: Run, expect ImportError**

- [ ] **Step 5.3: Implement**

Create `common/cloudflare.py`:
```python
"""Cloudflare REST API clients for D1 and KV."""

import os
from typing import Any
from urllib.parse import quote

import requests

CF_API_BASE = "https://api.cloudflare.com/client/v4"


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} not set in .env")
    return value


class D1Client:
    def __init__(self) -> None:
        self.account_id = _required_env("CF_ACCOUNT_ID")
        self.database_id = _required_env("CF_D1_DATABASE_ID")
        self.token = _required_env("CF_API_TOKEN")

    def query(self, sql: str, params: list[Any] | None = None) -> list[dict]:
        url = f"{CF_API_BASE}/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        body = {"sql": sql, "params": params or []}
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=body, timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            errs = data.get("errors", [])
            msg = "; ".join(e.get("message", "?") for e in errs) or "unknown error"
            raise RuntimeError(f"D1 query failed: {msg}")
        return data["result"][0].get("results", [])


class KVClient:
    def __init__(self) -> None:
        self.account_id = _required_env("CF_ACCOUNT_ID")
        self.namespace_id = _required_env("CF_KV_NAMESPACE_ID")
        self.token = _required_env("CF_API_TOKEN")

    def _value_url(self, key: str) -> str:
        return (
            f"{CF_API_BASE}/accounts/{self.account_id}"
            f"/storage/kv/namespaces/{self.namespace_id}/values/{quote(key, safe='')}"
        )

    def put(self, key: str, value: str) -> None:
        resp = requests.put(
            self._value_url(key),
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "text/plain"},
            data=value, timeout=15,
        )
        resp.raise_for_status()
        if not resp.json().get("success"):
            raise RuntimeError(f"KV PUT failed for key {key!r}")

    def delete(self, key: str) -> None:
        resp = requests.delete(
            self._value_url(key),
            headers={"Authorization": f"Bearer {self.token}"},
            timeout=15,
        )
        resp.raise_for_status()
```

- [ ] **Step 5.4: Run tests** — Expected: 3 passed.

- [ ] **Step 5.5: Commit**

```bash
git add common/cloudflare.py yt-analysis/tests/test_cloudflare.py
git commit -m "feat(common): cloudflare.py with D1Client and KVClient"
```

---

## Task 6: Worker implementation

**Files:**
- Create: `workers/redirector/{vitest.config.ts, src/index.ts, test/slug.test.ts}`

- [ ] **Step 6.1: vitest config**

Create `workers/redirector/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: { include: ["test/**/*.test.ts"] },
});
```

- [ ] **Step 6.2: Failing tests**

Create `workers/redirector/test/slug.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { hashIdentifier, isValidSlug } from "../src/index";

describe("hashIdentifier", () => {
  it("returns 16-char hex string", async () => {
    expect(await hashIdentifier("hello")).toMatch(/^[0-9a-f]{16}$/);
  });
  it("returns same hash for same input", async () => {
    expect(await hashIdentifier("foo")).toBe(await hashIdentifier("foo"));
  });
  it("returns different hashes for different inputs", async () => {
    expect(await hashIdentifier("foo")).not.toBe(await hashIdentifier("bar"));
  });
  it("returns empty string for empty input", async () => {
    expect(await hashIdentifier("")).toBe("");
  });
});

describe("isValidSlug", () => {
  it("accepts code/tool form", () => { expect(isValidSlug("acha/heygen")).toBe(true); });
  it("accepts hyphenated tool", () => { expect(isValidSlug("acha/envato-elements")).toBe(true); });
  it("rejects empty", () => { expect(isValidSlug("")).toBe(false); });
  it("rejects single segment", () => { expect(isValidSlug("acha")).toBe(false); });
  it("rejects deeper nesting", () => { expect(isValidSlug("acha/heygen/extra")).toBe(false); });
  it("rejects illegal chars", () => {
    expect(isValidSlug("acha/hey gen")).toBe(false);
    expect(isValidSlug("acha/heygen?utm=x")).toBe(false);
  });
});
```

- [ ] **Step 6.3: Run, expect failure**

```bash
cd workers/redirector && npm test
```

- [ ] **Step 6.4: Implement Worker**

Create `workers/redirector/src/index.ts`:
```ts
/**
 * Redirector Worker for go.agrolloo.com/*
 * KV lookup → 302 redirect; clicks logged via ctx.waitUntil() (fire-and-forget).
 * Dedup is done at query time in sync_clicks.py, NOT here.
 */

export interface Env {
  CLICKS_KV: KVNamespace;
  DB: D1Database;
}

const NOT_FOUND_BODY = "Link not found";
const SLUG_RE = /^[a-zA-Z0-9]+\/[a-zA-Z0-9-]+$/;

export async function hashIdentifier(value: string): Promise<string> {
  if (!value) return "";
  const data = new TextEncoder().encode(value);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .slice(0, 8)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export function isValidSlug(slug: string): boolean {
  return SLUG_RE.test(slug);
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    const slug = url.pathname.replace(/^\/+/, "");

    if (!slug || !isValidSlug(slug)) {
      return new Response(NOT_FOUND_BODY, {
        status: 404, headers: { "content-type": "text/plain" },
      });
    }

    const target = await env.CLICKS_KV.get(slug);
    if (!target) {
      return new Response(NOT_FOUND_BODY, {
        status: 404, headers: { "content-type": "text/plain" },
      });
    }

    const ip = req.headers.get("cf-connecting-ip") ?? "";
    const ua = req.headers.get("user-agent") ?? "";
    const referer = req.headers.get("referer") ?? "";
    ctx.waitUntil(logClick(env, slug, ip, ua, referer));

    return Response.redirect(target, 302);
  },
};

async function logClick(
  env: Env, slug: string, ip: string, ua: string, referer: string
): Promise<void> {
  try {
    const ipHash = await hashIdentifier(ip);
    const uaHash = await hashIdentifier(ua);
    const ts = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO clicks (slug, clicked_at, ip_hash, ua_hash, referer) VALUES (?, ?, ?, ?, ?)"
    ).bind(slug, ts, ipHash, uaHash, referer).run();
  } catch (e) {
    console.error("logClick failed", e);
  }
}
```

- [ ] **Step 6.5: Run tests** — Expected: 10 passed.
- [ ] **Step 6.6: Typecheck** — `npm run typecheck` — Expected: no errors.
- [ ] **Step 6.7: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/src/index.ts workers/redirector/test/slug.test.ts \
        workers/redirector/vitest.config.ts
git commit -m "feat(worker): redirector with KV lookup + fire-and-forget D1 logging"
```

---

## Task 7: Deploy Worker + DNS route

- [ ] **Step 7.1: Confirm DNS migration is Active** (CF dashboard)
- [ ] **Step 7.2: Add `go.agrolloo.com` AAAA record** — name `go`, IPv6 `100::`, Proxied
- [ ] **Step 7.3: Add Worker route**

Append to `workers/redirector/wrangler.toml`:
```toml

[[routes]]
pattern = "go.agrolloo.com/*"
zone_name = "agrolloo.com"
```

- [ ] **Step 7.4: Deploy**

```bash
cd workers/redirector && wrangler deploy
```

- [ ] **Step 7.5: Smoke 404**

```bash
curl -sI https://go.agrolloo.com/nonexistent
```
Expected: `HTTP/2 404`.

- [ ] **Step 7.6: Insert test slug + verify redirect**

```bash
wrangler kv key put --remote --binding=CLICKS_KV "test/example" "https://example.com/"
curl -sI https://go.agrolloo.com/test/example
```
Expected: `HTTP/2 302`, `location: https://example.com/`.

- [ ] **Step 7.7: Verify click logged**

```bash
wrangler d1 execute clicks-db --remote --command="SELECT slug FROM clicks ORDER BY id DESC LIMIT 1;"
```

- [ ] **Step 7.8: Cleanup**

```bash
wrangler kv key delete --remote --binding=CLICKS_KV "test/example"
wrangler d1 execute clicks-db --remote --command="DELETE FROM clicks WHERE slug='test/example';"
```

- [ ] **Step 7.9: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/wrangler.toml
git commit -m "deploy(worker): go.agrolloo.com route + verified end-to-end"
```

---

## Task 8: `common/llm.py` + prompt templates (TDD)

**Files:**
- Create: `prompts/detect-tools.md`, `prompts/generate-description.md`
- Create: `yt-analysis/tests/test_llm.py`, `common/llm.py`

- [ ] **Step 8.1: Prompt templates**

Create `prompts/detect-tools.md`:
```markdown
You are an expert at parsing video creator notes to identify which affiliate tools/products will be promoted in a YouTube video.

Given:
- A video title
- Free-form notes the creator wrote about the video
- A list of candidate tools (slug — display name)

Return a JSON list of tool slugs the creator is going to promote. Match conservatively — only include if clearly intended for promotion.

Do NOT include:
- Tools mentioned only as competitors that the creator is NOT going to link to
- Tools mentioned as examples the creator doesn't endorse
- Tools that aren't in the candidate list

---

Video title: {video_title}

Notes:
{video_notes}

Candidate tools (slug — display name):
{candidates_block}

Return JSON: {{"tools": ["slug1", "slug2", ...]}}
```

(Note: `{{` and `}}` escape literal braces for Python `.format()`.)

Create `prompts/generate-description.md`:
```markdown
You are writing the YouTube video description for a creator's affiliate-focused tutorial/comparison video. Generate a clear, engaging description that:

- Opens with a 1-2 line hook summarizing what the video covers
- Lists each tool/product mentioned with the affiliate short URL alongside its name
- Mentions any coupon codes inline next to the relevant tool
- Closes with a brief CTA
- Sounds like a real creator wrote it — friendly, not corporate

Format with line breaks. No hashtags. No emojis unless they fit naturally.

---

Video title: {video_title}

Creator's notes:
{video_notes}

Tools to feature (link → short URL → coupon if any):
{links_block}

Output the description text only. No preamble, no markdown headers.
```

- [ ] **Step 8.2: Failing tests**

Create `yt-analysis/tests/test_llm.py`:
```python
"""Tests for common.llm."""

import pytest

from common.llm import detect_tools, generate_description


class TestDetectTools:
    def test_calls_gemini_with_candidates(self, mocker):
        mock_json = mocker.patch("common.llm.gemini.generate_json")
        mock_json.return_value = {"tools": ["heygen", "synthesia"]}

        result = detect_tools(
            video_title="Heygen vs Synthesia",
            video_notes="Comparing both",
            candidate_tools={"heygen": "heygen", "synthesia": "synthesia", "fliki": "fliki"},
        )
        assert result == ["heygen", "synthesia"]
        prompt_arg = mock_json.call_args.kwargs.get("prompt") or mock_json.call_args.args[1]
        assert "heygen — heygen" in prompt_arg
        assert "fliki — fliki" in prompt_arg

    def test_filters_out_unknown_tools(self, mocker):
        mock_json = mocker.patch("common.llm.gemini.generate_json")
        mock_json.return_value = {"tools": ["heygen", "halucinated"]}
        result = detect_tools(
            video_title="x", video_notes="y",
            candidate_tools={"heygen": "heygen"},
        )
        assert result == ["heygen"]


class TestGenerateDescription:
    def test_generates_text_with_links_block(self, mocker):
        mock_text = mocker.patch("common.llm.gemini.generate_text")
        mock_text.return_value = "polished description"

        result = generate_description(
            video_title="Heygen review", video_notes="My take",
            link_specs=[{"tool": "heygen", "short_url": "https://go.agrolloo.com/acha/heygen", "coupon_code": "HEY30"}],
        )
        assert result == "polished description"
        prompt_arg = mock_text.call_args.kwargs.get("prompt") or mock_text.call_args.args[1]
        assert "https://go.agrolloo.com/acha/heygen" in prompt_arg
        assert "HEY30" in prompt_arg
```

- [ ] **Step 8.3: Run, expect ImportError**

- [ ] **Step 8.4: Implement**

Create `common/llm.py`:
```python
"""LLM helpers for tool detection + YT description generation."""

import os

from . import gemini
from .env import MYPROJ_ROOT

DEFAULT_MODEL = "gemini-2.5-flash"
PROMPTS_DIR = os.path.join(MYPROJ_ROOT, "prompts")


def _load_prompt(filename: str) -> str:
    with open(os.path.join(PROMPTS_DIR, filename), "r", encoding="utf-8") as f:
        return f.read()


def detect_tools(
    video_title: str, video_notes: str, candidate_tools: dict[str, str], model: str = DEFAULT_MODEL
) -> list[str]:
    """candidate_tools: {slug: display_name}. Returns subset present in candidate_tools."""
    candidates_block = "\n".join(f"- {slug} — {display}" for slug, display in candidate_tools.items())
    prompt = _load_prompt("detect-tools.md").format(
        video_title=video_title, video_notes=video_notes, candidates_block=candidates_block
    )
    schema = {"type": "object", "properties": {"tools": {"type": "array", "items": {"type": "string"}}}}
    parsed = gemini.generate_json(model=model, prompt=prompt, schema=schema)
    raw = parsed.get("tools", []) if isinstance(parsed, dict) else []
    return [t for t in raw if t in candidate_tools]


def generate_description(
    video_title: str, video_notes: str, link_specs: list[dict], model: str = DEFAULT_MODEL
) -> str:
    """link_specs: list of {tool, short_url, coupon_code}."""
    lines = []
    for spec in link_specs:
        coupon = spec.get("coupon_code", "")
        coupon_part = f" (coupon: {coupon})" if coupon else ""
        lines.append(f"- {spec['tool']} → {spec['short_url']}{coupon_part}")
    links_block = "\n".join(lines)
    prompt = _load_prompt("generate-description.md").format(
        video_title=video_title, video_notes=video_notes, links_block=links_block
    )
    return gemini.generate_text(model=model, prompt=prompt)
```

- [ ] **Step 8.5: Run tests** — Expected: 3 passed.

- [ ] **Step 8.6: Commit**

```bash
git add prompts/detect-tools.md prompts/generate-description.md common/llm.py yt-analysis/tests/test_llm.py
git commit -m "feat(common): llm.py + prompts for tool detection and description"
```

---

## Task 9: `yt-analysis/process_yt_tracker.py` (TDD)

The unified core script. Reads YT tracker rows where `topic_status="To Process"`, runs the full pipeline (LLM tool detection → URL creation → description generation → tracker writeback), transitions status to `To Review`. Writes `actual_links` and `short_links` columns as **per-tool blocks**.

**Files:**
- Create: `yt-analysis/tests/test_process_yt_tracker.py`, `yt-analysis/process_yt_tracker.py`

- [ ] **Step 9.1: Failing tests for `generate_video_code` + per-tool block formatter**

Create `yt-analysis/tests/test_process_yt_tracker.py`:
```python
"""Tests for yt-analysis.process_yt_tracker."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import process_yt_tracker as p  # type: ignore  # noqa: E402


class TestGenerateVideoCode:
    def test_returns_4_char_alphanumeric(self):
        code = p.generate_video_code(existing_codes=set())
        assert len(code) == 4 and code.isalnum()

    def test_avoids_collisions(self, mocker):
        mocker.patch.object(p.secrets, "choice", side_effect=list("abcd" + "abcd" + "wxyz"))
        code = p.generate_video_code(existing_codes={"abcd"})
        assert code == "wxyz"

    def test_raises_after_too_many_collisions(self, mocker):
        mocker.patch.object(p.secrets, "choice", side_effect=list("abcd" * 1000))
        with pytest.raises(RuntimeError, match="generate"):
            p.generate_video_code(existing_codes={"abcd"}, max_attempts=5)


class TestFormatLinkBlock:
    def test_per_tool_block(self):
        items = [("heygen", "https://heygen.sjv.io/abc"), ("synthesia", "https://synthesia.io/?aff=xyz")]
        text = p.format_link_block(items)
        assert text == "heygen: https://heygen.sjv.io/abc\nsynthesia: https://synthesia.io/?aff=xyz"

    def test_empty(self):
        assert p.format_link_block([]) == ""
```

- [ ] **Step 9.2: Run, expect ImportError**

- [ ] **Step 9.3: Stub `process_yt_tracker.py`**

Create `yt-analysis/process_yt_tracker.py`:
```python
"""Unified video processor — tracker-driven affiliate link workflow.

Reads rows from YT tracker where topic_status="To Process", uses Gemini to
detect tools and generate the YouTube description, registers short URLs in
D1+KV, populates YT tracker columns (video_description, actual_links,
short_links), and transitions status to "To Review".

Re-runnable. Errors mark the row's status as still-To-Process and skip.
"""

import os
import secrets
import sys
import time
from dataclasses import dataclass

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.affiliate import load_affiliate_records  # noqa: E402
from common.cloudflare import D1Client, KVClient  # noqa: E402
from common.llm import detect_tools, generate_description  # noqa: E402
from common.sheets import col_letter, extract_sheet_id, get_gspread_client  # noqa: E402

YT_TRACKER_TAB = "Master"
STATUS_TO_PROCESS = "To Process"
STATUS_TO_REVIEW = "To Review"

BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CODE_LENGTH = 4


def generate_video_code(existing_codes: set[str], max_attempts: int = 100) -> str:
    for _ in range(max_attempts):
        code = "".join(secrets.choice(BASE62) for _ in range(CODE_LENGTH))
        if code not in existing_codes:
            return code
    raise RuntimeError(f"Could not generate a unique {CODE_LENGTH}-char code in {max_attempts} attempts")


def format_link_block(items: list[tuple[str, str]]) -> str:
    """[(tool, url), ...] -> 'tool1: url1\\ntool2: url2'"""
    return "\n".join(f"{tool}: {url}" for tool, url in items)


def main() -> int:
    raise NotImplementedError
```

- [ ] **Step 9.4: Run, verify `generate_video_code` + `format_link_block` pass**

`pytest yt-analysis/tests/test_process_yt_tracker.py::TestGenerateVideoCode -v` — Expected: 3 passed.
`pytest yt-analysis/tests/test_process_yt_tracker.py::TestFormatLinkBlock -v` — Expected: 2 passed.

- [ ] **Step 9.5: Tests for `process_one_video`**

Append to test file:
```python
class TestProcessOneVideo:
    @pytest.fixture
    def mock_deps(self, mocker):
        from common.affiliate import AffiliateRecord
        affiliates = {
            "heygen": AffiliateRecord(
                tool="heygen", display_name="heygen",
                target_url="https://heygen.sjv.io/abc",
                approval_status="Approved",
                coupon_status="code received", coupon_code="HEY30",
            ),
            "synthesia": AffiliateRecord(
                tool="synthesia", display_name="synthesia",
                target_url="https://synthesia.io/?aff=xyz",
                approval_status="Approved",
                coupon_status="", coupon_code="",
            ),
            "pending-tool": AffiliateRecord(
                tool="pending-tool", display_name="pending tool",
                target_url="https://example.com",
                approval_status="Pending",
                coupon_status="", coupon_code="",
            ),
        }
        mocker.patch("process_yt_tracker.load_affiliate_records", return_value=affiliates)
        mocker.patch("process_yt_tracker.detect_tools", return_value=["heygen", "synthesia"])
        mocker.patch("process_yt_tracker.generate_description", return_value="Polished description")
        d1 = mocker.MagicMock()
        d1.query.return_value = []
        kv = mocker.MagicMock()
        return {"d1": d1, "kv": kv}

    def test_creates_video_with_per_tool_blocks(self, mock_deps, mocker):
        mocker.patch.object(p.secrets, "choice", side_effect=list("acha" * 3))
        result = p.process_one_video(
            video_title="Heygen vs Synthesia", video_notes="Comparing both",
            d1=mock_deps["d1"], kv=mock_deps["kv"], link_domain="go.agrolloo.com",
        )
        assert result.video_code == "acha"
        assert "heygen: https://heygen.sjv.io/abc" in result.actual_links_text
        assert "synthesia: https://synthesia.io/?aff=xyz" in result.actual_links_text
        assert "heygen: https://go.agrolloo.com/acha/heygen" in result.short_links_text
        assert "synthesia: https://go.agrolloo.com/acha/synthesia" in result.short_links_text
        assert result.description == "Polished description"
        sql = [c.args[0] for c in mock_deps["d1"].query.call_args_list]
        assert any("INSERT INTO videos" in s for s in sql)
        assert sum("INSERT INTO links" in s for s in sql) == 2
        assert mock_deps["kv"].put.call_count == 2

    def test_errors_on_unapproved_tool(self, mock_deps, mocker):
        mocker.patch("process_yt_tracker.detect_tools", return_value=["pending-tool"])
        with pytest.raises(p.ProcessError, match="not Approved"):
            p.process_one_video(
                video_title="x", video_notes="y",
                d1=mock_deps["d1"], kv=mock_deps["kv"], link_domain="go.agrolloo.com",
            )

    def test_idempotent_existing_video(self, mock_deps, mocker):
        mocker.patch.object(p.secrets, "choice", side_effect=list("zzzz" * 100))
        mock_deps["d1"].query.side_effect = [
            [{"video_code": "acha"}],
            [{"slug": "acha/heygen"}],
            None,
        ]
        result = p.process_one_video(
            video_title="Heygen vs Synthesia", video_notes="Comparing both",
            d1=mock_deps["d1"], kv=mock_deps["kv"], link_domain="go.agrolloo.com",
        )
        assert result.video_code == "acha"
        sql = [c.args[0] for c in mock_deps["d1"].query.call_args_list]
        assert sum("INSERT INTO videos" in s for s in sql) == 0
        assert sum("INSERT INTO links" in s for s in sql) == 1
        assert mock_deps["kv"].put.call_count == 1
```

- [ ] **Step 9.6: Run, expect failures**

- [ ] **Step 9.7: Implement `process_one_video` and `main`**

Replace the `main()` stub in `process_yt_tracker.py` with:

```python
class ProcessError(Exception):
    pass


@dataclass
class ProcessResult:
    video_code: str
    is_new_video: bool
    tools: list[str]
    actual_links_text: str    # per-tool block
    short_links_text: str     # per-tool block
    description: str


def _existing_video_code_for_title(d1: D1Client, title: str) -> str | None:
    rows = d1.query("SELECT video_code FROM videos WHERE video_title = ? LIMIT 1", [title])
    return rows[0]["video_code"] if rows else None


def _existing_slugs_for_video(d1: D1Client, video_code: str) -> set[str]:
    rows = d1.query("SELECT slug FROM links WHERE video_code = ?", [video_code])
    return {r["slug"] for r in rows}


def _existing_codes(d1: D1Client) -> set[str]:
    rows = d1.query("SELECT video_code FROM videos", [])
    return {r["video_code"] for r in rows}


def process_one_video(
    video_title: str, video_notes: str, d1: D1Client, kv: KVClient, link_domain: str
) -> ProcessResult:
    if not video_title.strip():
        raise ProcessError("video_title is empty")

    affiliates = load_affiliate_records()
    candidates = {slug: rec.display_name for slug, rec in affiliates.items()}

    detected = detect_tools(video_title, video_notes, candidates)
    if not detected:
        raise ProcessError("LLM returned no tools — refine notes and try again")

    unapproved = [t for t in detected if not affiliates[t].is_approved]
    if unapproved:
        raise ProcessError(f"Detected tools have approval not Approved: {', '.join(unapproved)}")

    existing_code = _existing_video_code_for_title(d1, video_title)
    if existing_code is not None:
        video_code = existing_code
        is_new_video = False
        already_present = _existing_slugs_for_video(d1, video_code)
    else:
        video_code = generate_video_code(_existing_codes(d1))
        is_new_video = True
        already_present = set()

    now = int(time.time())
    if is_new_video:
        d1.query(
            "INSERT INTO videos (video_code, video_title, created_at) VALUES (?, ?, ?)",
            [video_code, video_title, now],
        )

    actual_pairs: list[tuple[str, str]] = []
    short_pairs: list[tuple[str, str]] = []
    link_specs: list[dict] = []
    for tool in detected:
        slug = f"{video_code}/{tool}"
        target = affiliates[tool].target_url
        short = f"https://{link_domain}/{slug}"
        actual_pairs.append((tool, target))
        short_pairs.append((tool, short))
        link_specs.append({"tool": tool, "short_url": short, "coupon_code": affiliates[tool].coupon_code})
        if slug in already_present:
            continue
        d1.query(
            "INSERT INTO links (slug, video_code, tool, target_url, created_at) VALUES (?, ?, ?, ?, ?)",
            [slug, video_code, tool, target, now],
        )
        kv.put(slug, target)

    description = generate_description(video_title, video_notes, link_specs)

    return ProcessResult(
        video_code=video_code,
        is_new_video=is_new_video,
        tools=detected,
        actual_links_text=format_link_block(actual_pairs),
        short_links_text=format_link_block(short_pairs),
        description=description,
    )


def main() -> int:
    link_domain = os.getenv("LINK_DOMAIN")
    tracker_url = os.getenv("YT_TRACKER_SHEET_URL")
    if not link_domain or not tracker_url:
        print("ERROR: LINK_DOMAIN and YT_TRACKER_SHEET_URL must be set", file=sys.stderr)
        return 2

    client = get_gspread_client()
    ws = client.open_by_key(extract_sheet_id(tracker_url)).worksheet(YT_TRACKER_TAB)
    rows = ws.get_all_values()
    if not rows or len(rows) < 2:
        print("YT tracker has no data rows.")
        return 0

    header = [h.strip() for h in rows[0]]
    try:
        title_col = header.index("video_title")
        notes_col = header.index("video_notes")
        desc_col = header.index("video_description")
        actual_col = header.index("actual_links")
        short_col = header.index("short_links")
        status_col = header.index("topic_status")
    except ValueError as e:
        print(f"ERROR: missing required header in YT tracker: {e}", file=sys.stderr)
        return 2

    d1 = D1Client()
    kv = KVClient()

    processed = 0
    failed = 0
    for i, row in enumerate(rows[1:], start=2):
        if (row[status_col] if len(row) > status_col else "").strip() != STATUS_TO_PROCESS:
            continue
        title = row[title_col].strip() if len(row) > title_col else ""
        notes = row[notes_col].strip() if len(row) > notes_col else ""

        print(f"\n→ Row {i}: {title!r}")
        try:
            result = process_one_video(title, notes, d1, kv, link_domain)
        except ProcessError as e:
            print(f"  SKIP: {e}", file=sys.stderr)
            failed += 1
            continue

        ws.batch_update([
            {"range": f"{col_letter(desc_col)}{i}", "values": [[result.description]]},
            {"range": f"{col_letter(actual_col)}{i}", "values": [[result.actual_links_text]]},
            {"range": f"{col_letter(short_col)}{i}", "values": [[result.short_links_text]]},
            {"range": f"{col_letter(status_col)}{i}", "values": [[STATUS_TO_REVIEW]]},
        ], value_input_option="USER_ENTERED")

        processed += 1
        print(f"  ✓ {result.video_code} — {len(result.tools)} link(s); status → To Review")

    print(f"\nProcessed: {processed} | Failed: {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9.8: Run all tests** — Expected: 8 passed.

- [ ] **Step 9.9: Commit**

```bash
git add yt-analysis/process_yt_tracker.py yt-analysis/tests/test_process_yt_tracker.py
git commit -m "feat(yt-analysis): process_yt_tracker.py — tracker-driven workflow with actual_links + short_links columns"
```

---

## Task 10: Refactor `sync_views.py` to expose function

The existing script works standalone; refactor so it can be called from `yt_analysis.py`.

**Files:**
- Modify: `yt-analysis/sync_views.py`

- [ ] **Step 10.1: Read current sync_views.py**

`cat yt-analysis/sync_views.py` — note the structure (currently a script with `main()` only).

- [ ] **Step 10.2: Refactor to expose `sync_views()` function**

Edit `yt-analysis/sync_views.py`. Find the body of the existing `main()` function and split it: extract everything except the env-var validation into a new top-level `sync_views()` function. Keep `main()` calling it.

Final structure:
```python
# ... existing imports ...

def sync_views() -> dict:
    """Fetch YouTube view counts for each yt_link in Analysis sheet,
    write to 'views' column. Returns summary dict.
    """
    yt_api_key = os.getenv("YT_API_KEY")
    if not yt_api_key:
        raise RuntimeError("YT_API_KEY missing from .env")

    client = get_gspread_client()
    ws = client.open_by_key(DEST_SHEET_ID).worksheet(DEST_TAB)
    # ... [the existing rest of main()'s body, minus sys.exit] ...

    return {
        "rows_scanned": len(rows) - 1,
        "valid_links": len(row_to_vid),
        "skipped_invalid": skipped_invalid,
        "unique_ids": len(unique_ids),
        "views_written": written,
        "na_marked": na,
    }


def main() -> int:
    try:
        result = sync_views()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"Rows scanned:                  {result['rows_scanned']}")
    print(f"Valid YouTube links:           {result['valid_links']}")
    print(f"Skipped (unrecognized format): {result['skipped_invalid']}")
    print(f"Unique video IDs queried:      {result['unique_ids']}")
    print(f"Views written:                 {result['views_written']}")
    print(f"Marked N/A (private/deleted):  {result['na_marked']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 10.3: Smoke test** — run script and confirm output matches prior behavior.

```bash
cd /Users/kbtg/codebase/myproj && source venv/bin/activate
python3 yt-analysis/sync_views.py
```
Expected: same output as before the refactor.

- [ ] **Step 10.4: Commit**

```bash
git add yt-analysis/sync_views.py
git commit -m "refactor(yt-analysis): expose sync_views() function for orchestrator import"
```

---

## Task 11: Replace `sync_analysis.py` with `sync_metadata.py`

Rename + refactor + update column list to include `video_notes` and `yt_upload_status`. Add filter: only sync rows where source's `yt_upload_status = "uploaded"`.

**Files:**
- Delete: `yt-analysis/sync_analysis.py`
- Create: `yt-analysis/sync_metadata.py`, `yt-analysis/tests/test_sync_metadata.py`

- [ ] **Step 11.1: Failing test**

Create `yt-analysis/tests/test_sync_metadata.py`:
```python
"""Tests for yt-analysis.sync_metadata."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sync_metadata as m  # type: ignore  # noqa: E402


class TestFieldMap:
    def test_includes_video_notes_and_yt_upload_status(self):
        src_keys = [src for src, dst in m.FIELD_MAP]
        assert "video_notes" in src_keys
        assert "yt_upload_status" in src_keys

    def test_canonical_order(self):
        # video_title first, yt_link last (matches Analysis sheet ordering)
        assert m.FIELD_MAP[0][0] == "video_title"
        assert m.FIELD_MAP[-1][0] == "yt_link"


class TestUploadFilter:
    def test_only_uploaded_rows_pass(self):
        assert m.is_uploaded("uploaded") is True
        assert m.is_uploaded("Uploaded") is True
        assert m.is_uploaded(" UPLOADED ") is True
        assert m.is_uploaded("To Do") is False
        assert m.is_uploaded("") is False
```

- [ ] **Step 11.2: Run, expect ImportError**

- [ ] **Step 11.3: Create `sync_metadata.py`**

Copy `yt-analysis/sync_analysis.py` to `yt-analysis/sync_metadata.py`, then make these changes:

1. Update the module docstring to reference "sync metadata from YT tracker → Analysis sheet, filtered by yt_upload_status='uploaded'".

2. Update `FIELD_MAP` to include the two new columns:
```python
FIELD_MAP = [
    ("video_title", "video_title"),
    ("video_notes", "video_notes"),
    ("video_description", "video_description"),
    ("category", "category"),
    ("subcategory", "sub_category"),
    ("yt_upload_status", "yt_upload_status"),
    ("yt_upload_date", "yt_upload_date"),
    ("yt_link", "yt_link"),
]
```

3. Add an `is_uploaded` filter helper:
```python
def is_uploaded(status: str) -> bool:
    return (status or "").strip().lower() == "uploaded"
```

4. In the `main()` function (or extract `sync_metadata()` per the same pattern as Task 10), modify the row-iteration loop to skip rows whose source `yt_upload_status` is not `"uploaded"`. Filter applies BEFORE the title-match logic.

5. Wrap the body of `main()` into a `sync_metadata()` function so `yt_analysis.py` can import it (mirror the sync_views.py pattern).

- [ ] **Step 11.4: Delete the old `sync_analysis.py`**

```bash
rm yt-analysis/sync_analysis.py
```

- [ ] **Step 11.5: Run tests** — Expected: 5 passed.

- [ ] **Step 11.6: Smoke run**

```bash
python3 yt-analysis/sync_metadata.py
```
Expected: works without errors. May report 0 rows synced if no rows have `yt_upload_status = "uploaded"` yet.

- [ ] **Step 11.7: Commit**

```bash
git add yt-analysis/sync_metadata.py yt-analysis/tests/test_sync_metadata.py
git rm yt-analysis/sync_analysis.py
git commit -m "refactor(yt-analysis): rename sync_analysis -> sync_metadata, add video_notes + yt_upload_status, filter by uploaded status"
```

---

## Task 12: `yt-analysis/sync_clicks.py` (TDD)

Fills the existing `affiliate_link_clicks` column in Analysis sheet with rich per-tool blocks. Format:
```
tool, actual_affiliate_link, generated_link, count_last_30d, count_overall
```

**Files:**
- Create: `yt-analysis/tests/test_sync_clicks.py`, `yt-analysis/sync_clicks.py`

- [ ] **Step 12.1: Failing tests**

Create `yt-analysis/tests/test_sync_clicks.py`:
```python
"""Tests for yt-analysis.sync_clicks."""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sync_clicks as c  # type: ignore  # noqa: E402


class TestFormatBlock:
    def test_one_line_per_tool(self):
        link_data = [
            {"tool": "heygen", "target_url": "https://heygen.sjv.io/abc",
             "short_url": "https://go.agrolloo.com/acha/heygen", "count_30d": 12, "count_all": 142},
            {"tool": "synthesia", "target_url": "https://synthesia.io/?aff=xyz",
             "short_url": "https://go.agrolloo.com/acha/synthesia", "count_30d": 5, "count_all": 38},
        ]
        text = c.format_clicks_cell(link_data)
        lines = text.split("\n")
        assert len(lines) == 2
        assert lines[0] == "heygen, https://heygen.sjv.io/abc, https://go.agrolloo.com/acha/heygen, 12, 142"
        assert lines[1] == "synthesia, https://synthesia.io/?aff=xyz, https://go.agrolloo.com/acha/synthesia, 5, 38"

    def test_empty_returns_empty(self):
        assert c.format_clicks_cell([]) == ""


class TestCountClicksForSlug:
    def test_runs_two_dedup_queries(self, mocker):
        d1 = mocker.MagicMock()
        d1.query.side_effect = [[{"n": 12}], [{"n": 142}]]
        c30, call = c.count_clicks_for_slug(d1, "acha/heygen", now_ts=1_000_000_000)
        assert (c30, call) == (12, 142)
        first_params = d1.query.call_args_list[0].args[1]
        assert first_params == ["acha/heygen", 1_000_000_000 - 30 * 86400]
```

- [ ] **Step 12.2: Run, expect ImportError**

- [ ] **Step 12.3: Implement**

Create `yt-analysis/sync_clicks.py`:
```python
"""Refresh the Analysis sheet's affiliate_link_clicks column.

For each row with a video_title that matches a row in D1's videos table:
- Look up that video's slugs (videos JOIN links by video_title)
- Query D1 for last_30d + all_time counts (deduped at query time)
- Build per-tool blocks: "tool, target_url, short_url, count_30d, count_all"
- Write to affiliate_link_clicks column
"""

import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.cloudflare import D1Client  # noqa: E402
from common.sheets import col_letter, extract_sheet_id, get_gspread_client  # noqa: E402

ANALYSIS_TAB = "Per video cost,views and clicks"
CLICKS_HEADER = "affiliate_link_clicks"
TITLE_HEADER = "video_title"

THIRTY_DAYS_SECONDS = 30 * 86400

SQL_LINKS_FOR_TITLE = """
SELECT l.slug AS slug, l.tool AS tool, l.target_url AS target_url
FROM links l
JOIN videos v ON v.video_code = l.video_code
WHERE v.video_title = ?
ORDER BY l.tool
"""

SQL_30D = """
SELECT COUNT(*) AS n FROM (
  SELECT 1 FROM clicks
  WHERE slug = ? AND clicked_at >= ?
  GROUP BY ip_hash, ua_hash, (clicked_at / 3600)
)
"""

SQL_ALL = """
SELECT COUNT(*) AS n FROM (
  SELECT 1 FROM clicks
  WHERE slug = ?
  GROUP BY ip_hash, ua_hash, (clicked_at / 3600)
)
"""


def count_clicks_for_slug(d1: D1Client, slug: str, now_ts: int) -> tuple[int, int]:
    threshold = now_ts - THIRTY_DAYS_SECONDS
    r30 = d1.query(SQL_30D, [slug, threshold])
    rall = d1.query(SQL_ALL, [slug])
    return (
        int(r30[0]["n"]) if r30 else 0,
        int(rall[0]["n"]) if rall else 0,
    )


def format_clicks_cell(link_data: list[dict]) -> str:
    return "\n".join(
        f"{d['tool']}, {d['target_url']}, {d['short_url']}, {d['count_30d']}, {d['count_all']}"
        for d in link_data
    )


def sync_clicks() -> dict:
    """Refresh the affiliate_link_clicks column. Returns summary dict."""
    link_domain = os.getenv("LINK_DOMAIN")
    sheet_url = os.getenv("ANALYSIS_INCOME_SHEET_URL")
    if not link_domain or not sheet_url:
        raise RuntimeError("LINK_DOMAIN and ANALYSIS_INCOME_SHEET_URL must be set")

    client = get_gspread_client()
    ws = client.open_by_key(extract_sheet_id(sheet_url)).worksheet(ANALYSIS_TAB)
    rows = ws.get_all_values()
    if not rows or len(rows) < 2:
        return {"rows_refreshed": 0, "rows_scanned": 0}

    header = [h.strip() for h in rows[0]]
    title_col = header.index(TITLE_HEADER)
    clicks_col = header.index(CLICKS_HEADER)

    d1 = D1Client()
    now_ts = int(time.time())
    updates = []
    refreshed = 0

    for i, row in enumerate(rows[1:], start=2):
        title = row[title_col].strip() if len(row) > title_col else ""
        if not title:
            continue
        link_rows = d1.query(SQL_LINKS_FOR_TITLE, [title])
        if not link_rows:
            continue

        per_link = []
        for lr in link_rows:
            slug = lr["slug"]
            short_url = f"https://{link_domain}/{slug}"
            c30, call = count_clicks_for_slug(d1, slug, now_ts)
            per_link.append({
                "tool": lr["tool"], "target_url": lr["target_url"], "short_url": short_url,
                "count_30d": c30, "count_all": call,
            })

        cell_text = format_clicks_cell(per_link)
        updates.append({
            "range": f"{col_letter(clicks_col)}{i}",
            "values": [[cell_text]],
        })
        refreshed += 1

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")

    return {"rows_refreshed": refreshed, "rows_scanned": len(rows) - 1}


def main() -> int:
    try:
        result = sync_clicks()
    except RuntimeError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2
    print(f"Rows refreshed: {result['rows_refreshed']} / {result['rows_scanned']} scanned")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 12.4: Run tests** — Expected: 3 passed.

- [ ] **Step 12.5: Commit**

```bash
git add yt-analysis/sync_clicks.py yt-analysis/tests/test_sync_clicks.py
git commit -m "feat(yt-analysis): sync_clicks.py — fill affiliate_link_clicks with rich format"
```

---

## Task 13: `yt-analysis/yt_analysis.py` — interactive orchestrator (TDD)

Asks user what to sync (multi-select). Calls helper modules. Prints per-step + final summary.

**Files:**
- Create: `yt-analysis/tests/test_yt_analysis.py`, `yt-analysis/yt_analysis.py`

- [ ] **Step 13.1: Failing tests for menu parsing**

Create `yt-analysis/tests/test_yt_analysis.py`:
```python
"""Tests for yt-analysis.yt_analysis (orchestrator)."""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import yt_analysis as y  # type: ignore  # noqa: E402


class TestParseSelection:
    def test_single_number(self):
        assert y.parse_selection("1", n_options=4) == {1}

    def test_comma_separated(self):
        assert y.parse_selection("1,3", n_options=4) == {1, 3}

    def test_with_whitespace(self):
        assert y.parse_selection(" 1 , 2 ", n_options=4) == {1, 2}

    def test_all_keyword(self):
        assert y.parse_selection("all", n_options=4) == {1, 2, 3, 4}

    def test_invalid_raises(self):
        with pytest.raises(ValueError):
            y.parse_selection("99", n_options=4)
        with pytest.raises(ValueError):
            y.parse_selection("abc", n_options=4)


class TestRunSelected:
    def test_calls_metadata_sync(self, mocker, capsys):
        m_meta = mocker.patch("yt_analysis.sync_metadata.sync_metadata", return_value={"matched": 5, "appended": 0})
        mocker.patch("yt_analysis.sync_views.sync_views")
        mocker.patch("yt_analysis.sync_clicks.sync_clicks")
        y.run_selected({1})
        m_meta.assert_called_once()
        out = capsys.readouterr().out
        assert "metadata" in out.lower()

    def test_calls_views_sync(self, mocker):
        mocker.patch("yt_analysis.sync_metadata.sync_metadata")
        m_views = mocker.patch("yt_analysis.sync_views.sync_views", return_value={"views_written": 3})
        mocker.patch("yt_analysis.sync_clicks.sync_clicks")
        y.run_selected({2})
        m_views.assert_called_once()

    def test_rank_analysis_prints_placeholder(self, mocker, capsys):
        mocker.patch("yt_analysis.sync_metadata.sync_metadata")
        mocker.patch("yt_analysis.sync_views.sync_views")
        mocker.patch("yt_analysis.sync_clicks.sync_clicks")
        y.run_selected({4})
        out = capsys.readouterr().out
        assert "sync_rankings.py" in out
```

- [ ] **Step 13.2: Run, expect ImportError**

- [ ] **Step 13.3: Implement**

Create `yt-analysis/yt_analysis.py`:
```python
"""Interactive orchestrator for the YT analysis pipeline.

Asks the user which sync operations to run, then calls the corresponding
helper modules (sync_metadata, sync_views, sync_clicks) and prints a
summary at the end.

Rank analysis is intentionally not handled here — see sync_rankings.py.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Import sibling modules in this folder
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sync_clicks  # noqa: E402
import sync_metadata  # noqa: E402
import sync_views  # noqa: E402

OPTIONS = [
    ("Metadata sync (tracker → Analysis sheet, filtered by yt_upload_status=uploaded)", "metadata"),
    ("Views (YouTube API → 'views' column in Analysis sheet)", "views"),
    ("Affiliate link clicks (D1 → 'affiliate_link_clicks' column with rich format)", "clicks"),
    ("Rank analysis", "rank"),
]


def parse_selection(text: str, n_options: int) -> set[int]:
    """Parse a user input like '1', '1,2,3', or 'all' into a set of option numbers."""
    text = text.strip().lower()
    if not text:
        raise ValueError("Empty selection")
    if text == "all":
        return set(range(1, n_options + 1))
    out: set[int] = set()
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if not part.isdigit():
            raise ValueError(f"Not a number: {part!r}")
        n = int(part)
        if n < 1 or n > n_options:
            raise ValueError(f"Out of range: {n}")
        out.add(n)
    if not out:
        raise ValueError("No valid selections")
    return out


def prompt_user() -> set[int]:
    print("\nWhat do you want to sync?\n")
    for i, (label, _) in enumerate(OPTIONS, start=1):
        print(f"  {i}. {label}")
    print('\nEnter numbers (e.g. "1,2"), or "all".')
    while True:
        try:
            raw = input("> ")
            return parse_selection(raw, len(OPTIONS))
        except ValueError as e:
            print(f"Invalid input: {e}. Try again.")


def run_selected(selection: set[int]) -> None:
    summary: dict[str, dict | str] = {}

    if 1 in selection:
        print("\n→ Syncing metadata...")
        try:
            summary["metadata"] = sync_metadata.sync_metadata()
            print("  ✓ metadata sync done")
        except Exception as e:
            summary["metadata"] = f"ERROR: {e}"
            print(f"  ✗ metadata sync failed: {e}", file=sys.stderr)

    if 2 in selection:
        print("\n→ Fetching views...")
        try:
            summary["views"] = sync_views.sync_views()
            print("  ✓ views sync done")
        except Exception as e:
            summary["views"] = f"ERROR: {e}"
            print(f"  ✗ views sync failed: {e}", file=sys.stderr)

    if 3 in selection:
        print("\n→ Refreshing affiliate link clicks...")
        try:
            summary["clicks"] = sync_clicks.sync_clicks()
            print("  ✓ clicks sync done")
        except Exception as e:
            summary["clicks"] = f"ERROR: {e}"
            print(f"  ✗ clicks sync failed: {e}", file=sys.stderr)

    if 4 in selection:
        print("\n→ Rank analysis: not part of this script.")
        print("  Run `python3 yt-analysis/sync_rankings.py` separately.")
        summary["rank"] = "deferred (run sync_rankings.py)"

    print("\n========== SUMMARY ==========")
    for key, val in summary.items():
        print(f"{key}: {val}")


def main() -> int:
    selection = prompt_user()
    run_selected(selection)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 13.4: Run tests** — Expected: 8 passed.

- [ ] **Step 13.5: Manual smoke** — `python3 yt-analysis/yt_analysis.py`, pick option 1 (metadata sync), confirm it runs (may report 0 rows if no "uploaded" videos yet).

- [ ] **Step 13.6: Commit**

```bash
git add yt-analysis/yt_analysis.py yt-analysis/tests/test_yt_analysis.py
git commit -m "feat(yt-analysis): yt_analysis.py — interactive orchestrator (metadata/views/clicks/rank)"
```

---

## Task 14: Sheet schema setup + end-to-end smoke test

Add the new column headers to both sheets, then verify the full pipeline works on a real video.

- [ ] **Step 14.1: Add YT tracker columns**

Open YT tracker (`YT_TRACKER_SHEET_URL`) → `Master` tab. In row 1, add three new headers in adjacent empty columns:
- `video_notes`
- `actual_links`
- `short_links`

- [ ] **Step 14.2: Add Analysis sheet columns**

Open Analysis sheet (`ANALYSIS_INCOME_SHEET_URL`) → `Per video cost,views and clicks` tab. In row 1, add two new headers:
- `video_notes`
- `yt_upload_status`

- [ ] **Step 14.3: Pick a real video for the test**

In YT tracker, add or pick a row:
- `video_title`: `"E2E test — heygen"`
- `video_notes`: `"Heygen demo video. Show pricing, voice cloning."`
- `topic_status`: `"To Process"`
- `yt_upload_status`: leave blank for now

- [ ] **Step 14.4: Run process_yt_tracker**

```bash
cd /Users/kbtg/codebase/myproj && source venv/bin/activate
python3 yt-analysis/process_yt_tracker.py
```
Expected: `→ Row N: 'E2E test — heygen'` then `✓ <code> — 1 link(s); status → To Review`.

- [ ] **Step 14.5: Verify YT tracker updated**

Open the tracker. The test row now has:
- `video_description`: polished description text
- `actual_links`: `heygen: https://heygen.sjv.io/abc` (or similar)
- `short_links`: `heygen: https://go.agrolloo.com/<code>/heygen`
- `topic_status`: `"To Review"`

- [ ] **Step 14.6: Mark video as uploaded**

In the same tracker row, set `yt_upload_status` to `"uploaded"` (this triggers metadata sync + views).

- [ ] **Step 14.7: Run yt_analysis (interactive)**

```bash
python3 yt-analysis/yt_analysis.py
```
At the prompt, type `1,3` (metadata + clicks; skip views since the test row has no real `yt_link`).

Expected: prints `→ Syncing metadata...` and `→ Refreshing affiliate link clicks...`, then a summary.

- [ ] **Step 14.8: Verify Analysis sheet has the row**

Open Analysis sheet. Row matching `video_title = "E2E test — heygen"` should now have:
- `video_notes`: matches tracker
- `yt_upload_status`: `"uploaded"`
- `affiliate_link_clicks`: `heygen, https://heygen.sjv.io/abc, https://go.agrolloo.com/<code>/heygen, 0, 0` (counts are 0 since no real clicks yet)

- [ ] **Step 14.9: Generate clicks and re-run clicks sync**

```bash
for i in 1 2 3; do curl -sI "<short_url_from_step_14.5>" > /dev/null; sleep 1; done
python3 yt-analysis/yt_analysis.py
# Pick option 3 (clicks)
```
Expected: `affiliate_link_clicks` now shows `heygen, ..., ..., 1, 1` (3 raw clicks dedup to 1 in the same hour).

- [ ] **Step 14.10: Cleanup E2E test data**

```bash
cd workers/redirector
# Replace <code> with actual generated code from Step 14.4/14.5
wrangler kv key delete --remote --binding=CLICKS_KV "<code>/heygen"
wrangler d1 execute clicks-db --remote --command="DELETE FROM clicks WHERE slug LIKE '<code>/%';"
wrangler d1 execute clicks-db --remote --command="DELETE FROM links WHERE video_code='<code>';"
wrangler d1 execute clicks-db --remote --command="DELETE FROM videos WHERE video_code='<code>';"
```
Delete the test row from YT tracker AND Analysis sheet.

- [ ] **Step 14.11: Final commit (if anything tweaked)**

```bash
cd /Users/kbtg/codebase/myproj
git status
```
If clean, no commit needed. If anything was edited during E2E, commit it.

---

## Acceptance criteria

When all tasks complete:

1. `python3 yt-analysis/process_yt_tracker.py` processes every YT tracker row in `"To Process"` state — registers short URLs in D1+KV, generates polished descriptions via Gemini, populates the tracker (description, `actual_links`, `short_links`, status → To Review).
2. `python3 yt-analysis/yt_analysis.py` shows an interactive menu with 4 options. Selecting metadata syncs tracker → Analysis sheet for `yt_upload_status="uploaded"` rows. Selecting views fills the `views` column. Selecting clicks fills the `affiliate_link_clicks` column with rich per-tool blocks. Selecting rank analysis prints "run sync_rankings.py" placeholder.
3. The Worker at `go.agrolloo.com/*` 302-redirects valid slugs and 404s on unknown ones.
4. Tests pass: `pytest yt-analysis/tests -v` shows ≥35 passed; `cd workers/redirector && npm test` shows 10 passed.
5. The redirect path never blocks on D1 — fire-and-forget logging via `ctx.waitUntil()`.

## Troubleshooting

- **`wrangler whoami` shows nothing** → `wrangler login`.
- **`wrangler d1 execute` returns 401** → API token missing scopes.
- **`go.agrolloo.com` returns the WP site** → DNS not propagated or Worker route misconfigured.
- **Python `ImportError: No module named common`** → run from `myproj/` root.
- **Gemini returns an unapproved tool** → row stays at `To Process` with stderr message; fix Affiliate sheet or notes, re-run.
- **`yt_analysis.py` reports 0 rows for metadata sync** → check `yt_upload_status` column is set to `"uploaded"` on at least one tracker row.
- **`sync_clicks.py` says "Refreshed 0 row(s)"** → no Analysis sheet rows match a `videos.video_title` in D1. Run `process_yt_tracker.py` first to populate.
