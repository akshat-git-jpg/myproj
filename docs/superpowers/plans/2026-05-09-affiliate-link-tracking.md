# Affiliate Link Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Cloudflare-backed branded link shortener at `go.agrolloo.com` with click logging, plus Python scripts to register video→tool links and fill click counts in the Analysis sheet.

**Architecture:** TypeScript Worker on Cloudflare reads `slug → target_url` from KV (synchronous, the only redirect-path dependency) and fire-and-forget logs clicks to D1 via `ctx.waitUntil()`. Python scripts (`add_links.py`, `sync_clicks.py`) talk to D1+KV via Cloudflare REST API and read tool URLs from the existing Affiliate Programs sheet.

**Tech Stack:** TypeScript on Cloudflare Workers, KV, D1; Python with gspread, requests, pytest, pytest-mock; Wrangler CLI 3.x. (Spec: `docs/superpowers/specs/2026-05-09-affiliate-link-tracking-design.md`.)

---

## Prerequisites (USER-SIDE, before Task 1)

These are NOT plan tasks — the user must complete them first.

1. Sign up for Cloudflare (free).
2. Add `agrolloo.com` to Cloudflare. Verify all DNS records imported (especially the A record pointing to Hostinger).
3. At domain registrar, switch nameservers to the two Cloudflare ones shown in the CF dashboard. Wait 24–48h for propagation. WordPress site keeps working.
4. `npm install -g wrangler@3 && wrangler --version` — confirm 3.x installed.
5. `wrangler login` — authenticates via browser.
6. Create CF API token at https://dash.cloudflare.com/profile/api-tokens with these permissions:
   - `Account → D1 → Edit`
   - `Account → Workers KV Storage → Edit`
   Scope to your account only. Save the token securely.
7. From CF dashboard "Account Home" (right sidebar), copy your `Account ID`.
8. Confirm `myproj/credentials.json` exists and the service account `n8n-google-sa@n8n-workflows-454504.iam.gserviceaccount.com` has read access to the Affiliate Programs sheet (already true from prior session).

**Notes:** During DNS propagation, Worker development can use `*.workers.dev` URLs. Final cutover to `go.agrolloo.com` happens in Task 7.

---

## File structure (created by this plan)

```
myproj/
├── workers/
│   └── redirector/
│       ├── wrangler.toml             # Worker + KV + D1 + route config
│       ├── package.json              # vitest, wrangler, typescript
│       ├── tsconfig.json
│       ├── vitest.config.ts
│       ├── .gitignore                # node_modules, .dev.vars, .wrangler
│       ├── src/
│       │   └── index.ts              # ~80 lines: redirect + log
│       ├── test/
│       │   └── slug.test.ts          # unit tests for pure functions
│       └── migrations/
│           └── 0001_init.sql         # videos, links, clicks tables + index
├── common/
│   ├── cloudflare.py                 # NEW: D1 + KV REST API client
│   └── affiliate.py                  # NEW: Affiliate Programs sheet reader + tool slug normalization
├── yt-analysis/
│   ├── add_links.py                  # NEW: register a video's links
│   ├── sync_clicks.py                # NEW: fill click counts in Analysis sheet
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py               # shared fixtures
│       ├── test_cloudflare.py
│       ├── test_affiliate.py
│       ├── test_add_links.py
│       └── test_sync_clicks.py
├── .env                              # MODIFIED: add CF_* + LINK_DOMAIN
├── .env.example                      # MODIFIED: same placeholders
├── .gitignore                        # MODIFIED: workers/redirector/{node_modules,.dev.vars,.wrangler}
└── requirements.txt                  # MODIFIED: pytest, pytest-mock, requests
```

Manual sheet edit (not code): the Analysis sheet's `Per video cost,views and clicks` tab gets three new column headers in row 1 — `affiliate_links`, `clicks_last_30d`, `clicks_all_time`.

---

## Task 1: Test infrastructure + new env vars

**Files:**
- Modify: `requirements.txt`
- Modify: `.env`
- Modify: `.env.example`
- Create: `yt-analysis/tests/__init__.py`
- Create: `yt-analysis/tests/conftest.py`

- [ ] **Step 1.1: Add Python test deps to requirements.txt**

Append to `requirements.txt`:
```
pytest==8.3.4
pytest-mock==3.14.0
requests==2.32.3
```

- [ ] **Step 1.2: Install the new deps**

Run:
```bash
cd /Users/kbtg/codebase/myproj && source venv/bin/activate && pip install -q -r requirements.txt && pytest --version
```
Expected: `pytest 8.3.4` printed.

- [ ] **Step 1.3: Add CF env vars to .env**

Append to `myproj/.env` (replace `<FILL_IN>` placeholders with actual values from prerequisites):
```
# Cloudflare link tracker
CF_API_TOKEN=<FILL_IN>
CF_ACCOUNT_ID=<FILL_IN>
CF_D1_DATABASE_ID=<FILL_IN_AFTER_TASK_3>
CF_KV_NAMESPACE_ID=<FILL_IN_AFTER_TASK_3>
LINK_DOMAIN=go.agrolloo.com
```

The two `_AFTER_TASK_3` values get filled in once we create the namespace and DB.

- [ ] **Step 1.4: Mirror the same keys (without secrets) into .env.example**

Append to `myproj/.env.example`:
```
# Cloudflare link tracker
CF_API_TOKEN=your_cloudflare_api_token
CF_ACCOUNT_ID=your_cloudflare_account_id
CF_D1_DATABASE_ID=your_d1_database_id
CF_KV_NAMESPACE_ID=your_kv_namespace_id
LINK_DOMAIN=go.yourdomain.com
```

- [ ] **Step 1.5: Create the tests directory + conftest**

Create `yt-analysis/tests/__init__.py` as an empty file.

Create `yt-analysis/tests/conftest.py`:
```python
"""Shared pytest fixtures and test bootstrapping.

Adds myproj root to sys.path so `from common.x import y` works in tests
the same way it does in the runtime scripts.
"""

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
```

- [ ] **Step 1.6: Confirm tests collect**

Run:
```bash
cd /Users/kbtg/codebase/myproj && source venv/bin/activate && pytest yt-analysis/tests -v
```
Expected: `no tests ran` (no test files yet) and exit code 5 (no collected). That's fine — proves pytest discovers the directory.

- [ ] **Step 1.7: Commit**

```bash
git add requirements.txt .env.example yt-analysis/tests/__init__.py yt-analysis/tests/conftest.py
git commit -m "chore: add pytest infra + CF link-tracker env placeholders"
```
(Note: `.env` is gitignored; only `.env.example` is committed.)

---

## Task 2: Common helper — `common/affiliate.py` (TDD)

Reads the Affiliate Programs sheet, normalizes tool names, looks up target URLs and coupon codes. Validates approval status.

**Files:**
- Create: `yt-analysis/tests/test_affiliate.py`
- Create: `common/affiliate.py`

- [ ] **Step 2.1: Write failing tests for tool slug normalization**

Create `yt-analysis/tests/test_affiliate.py`:
```python
"""Tests for common.affiliate."""

import pytest

from common.affiliate import normalize_tool_name, AffiliateRecord


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

- [ ] **Step 2.2: Run tests, verify failure**

Run:
```bash
cd /Users/kbtg/codebase/myproj && source venv/bin/activate && pytest yt-analysis/tests/test_affiliate.py -v
```
Expected: `ImportError: cannot import name 'normalize_tool_name' from 'common.affiliate'` (module doesn't exist).

- [ ] **Step 2.3: Implement minimal `common/affiliate.py` to pass slug tests**

Create `common/affiliate.py`:
```python
"""Affiliate Programs sheet reader + tool name normalization."""

import os
import re
from dataclasses import dataclass
from typing import Optional

from .sheets import extract_sheet_id, get_gspread_client


@dataclass(frozen=True)
class AffiliateRecord:
    tool: str           # normalized slug, e.g., "envato-elements"
    display_name: str   # original sheet name, e.g., "envato elements"
    target_url: str     # value from "My Affiliate Link"
    approval_status: str
    coupon_status: str
    coupon_code: str

    @property
    def is_approved(self) -> bool:
        return self.approval_status.strip().lower() == "approved"


def normalize_tool_name(name: str) -> str:
    """Lowercase, strip non-alphanumeric (collapse to single hyphen)."""
    if not name or not name.strip():
        raise ValueError("Tool name is empty")
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")
```

- [ ] **Step 2.4: Run tests, verify pass**

Run: `pytest yt-analysis/tests/test_affiliate.py::TestNormalizeToolName -v`
Expected: 7 passed.

- [ ] **Step 2.5: Add tests for `load_affiliate_records()` (gspread mocked)**

Append to `yt-analysis/tests/test_affiliate.py`:
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
        assert records["heygen"].target_url == "https://heygen.sjv.io/abc"
        assert records["heygen"].is_approved is True
        assert records["heygen"].coupon_code == "HEY30"

        assert "envato-elements" in records  # space normalized to hyphen
        assert records["envato-elements"].display_name == "envato elements"

        assert "pending-tool" in records
        assert records["pending-tool"].is_approved is False

    def test_raises_when_env_var_missing(self, mocker):
        from common import affiliate
        mocker.patch.dict(os.environ, {}, clear=True)
        with pytest.raises(RuntimeError, match="AFFILIATE_PROGRAMS_SHEET_URL"):
            affiliate.load_affiliate_records()
```

Add `import os` at the top of the test file (after the existing pytest import).

- [ ] **Step 2.6: Run tests, expect failure**

Run: `pytest yt-analysis/tests/test_affiliate.py::TestLoadAffiliateRecords -v`
Expected: `AttributeError` or `ImportError` for `load_affiliate_records`.

- [ ] **Step 2.7: Implement `load_affiliate_records()`**

Append to `common/affiliate.py`:
```python
def load_affiliate_records() -> dict[str, AffiliateRecord]:
    """Read the Affiliate Programs sheet and return a {tool_slug: record} mapping.

    Reads sheet URL from env var AFFILIATE_PROGRAMS_SHEET_URL.
    Raises RuntimeError if the env var isn't set.
    """
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

    def cell(row: list[str], col: str) -> str:
        i = idx.get(col)
        if i is None or i >= len(row):
            return ""
        return row[i].strip()

    records: dict[str, AffiliateRecord] = {}
    for row in rows[1:]:
        display = cell(row, "Affiliate Program")
        if not display:
            continue
        try:
            slug = normalize_tool_name(display)
        except ValueError:
            continue
        records[slug] = AffiliateRecord(
            tool=slug,
            display_name=display,
            target_url=cell(row, "My Affiliate Link"),
            approval_status=cell(row, "Approval Status"),
            coupon_status=cell(row, "Coupon Status"),
            coupon_code=cell(row, "Coupon Code"),
        )
    return records
```

- [ ] **Step 2.8: Run all affiliate tests**

Run: `pytest yt-analysis/tests/test_affiliate.py -v`
Expected: 9 passed.

- [ ] **Step 2.9: Commit**

```bash
git add common/affiliate.py yt-analysis/tests/test_affiliate.py
git commit -m "feat(common): add affiliate.py with sheet reader + tool name normalization"
```

---

## Task 3: Worker scaffolding + create KV namespace and D1 database

**Files:**
- Create: `workers/redirector/package.json`
- Create: `workers/redirector/tsconfig.json`
- Create: `workers/redirector/.gitignore`
- Create: `workers/redirector/wrangler.toml`
- Modify: `.gitignore` (root) — add Worker artifacts

- [ ] **Step 3.1: Initialize the Worker project**

Run:
```bash
mkdir -p /Users/kbtg/codebase/myproj/workers/redirector && cd /Users/kbtg/codebase/myproj/workers/redirector
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
    "target": "ES2022",
    "module": "ES2022",
    "moduleResolution": "Bundler",
    "lib": ["ES2022"],
    "types": ["@cloudflare/workers-types"],
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "skipLibCheck": true
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

- [ ] **Step 3.2: Install Worker dependencies**

Run:
```bash
cd /Users/kbtg/codebase/myproj/workers/redirector && npm install --silent
```
Expected: `node_modules/` appears, no errors.

- [ ] **Step 3.3: Add Worker artifacts to root .gitignore**

Append to `myproj/.gitignore`:
```

# Worker (workers/redirector)
workers/redirector/node_modules/
workers/redirector/.wrangler/
workers/redirector/.dev.vars
```

- [ ] **Step 3.4: Create the KV namespace**

Run from `workers/redirector/`:
```bash
wrangler kv namespace create CLICKS_KV
```
Expected output (the `id` is what we save):
```
🌀 Creating namespace with title "redirector-CLICKS_KV"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
[[kv_namespaces]]
binding = "CLICKS_KV"
id = "abc123def456..."
```

Save the `id` — paste it into `myproj/.env` as `CF_KV_NAMESPACE_ID=abc123def456...`.

- [ ] **Step 3.5: Create the D1 database**

Run from `workers/redirector/`:
```bash
wrangler d1 create clicks-db
```
Expected output:
```
✅ Successfully created DB 'clicks-db'
[[d1_databases]]
binding = "DB"
database_name = "clicks-db"
database_id = "xyz987654..."
```

Save the `database_id` — paste it into `myproj/.env` as `CF_D1_DATABASE_ID=xyz987654...`.

- [ ] **Step 3.6: Write `wrangler.toml`**

Create `workers/redirector/wrangler.toml` (replace `<KV_ID>` and `<D1_ID>` with values from steps 3.4 and 3.5):
```toml
name = "redirector"
main = "src/index.ts"
compatibility_date = "2025-04-01"

# Local dev URL: http://localhost:8787
# Production URL (after Task 7): https://go.agrolloo.com/*

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

- [ ] **Step 3.7: Verify config**

Run:
```bash
cd /Users/kbtg/codebase/myproj/workers/redirector && wrangler whoami
```
Expected: shows your authenticated CF account email.

Run: `cat wrangler.toml`
Expected: KV and D1 IDs are filled in (no `<...>` placeholders).

- [ ] **Step 3.8: Commit**

```bash
git add workers/redirector/package.json workers/redirector/tsconfig.json \
        workers/redirector/.gitignore workers/redirector/wrangler.toml \
        .gitignore
git commit -m "chore(worker): scaffold redirector Worker, create KV namespace and D1 database"
```

(Note: `.env` updates are local-only since `.env` is gitignored.)

---

## Task 4: D1 schema migration

Apply the 3-table schema from the spec.

**Files:**
- Create: `workers/redirector/migrations/0001_init.sql`

- [ ] **Step 4.1: Write the migration SQL**

Create `workers/redirector/migrations/0001_init.sql`:
```sql
-- Affiliate link tracker schema (matches design spec 2026-05-09)

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

- [ ] **Step 4.2: Apply the migration**

Run from `workers/redirector/`:
```bash
wrangler d1 execute clicks-db --remote --file=migrations/0001_init.sql
```
Expected: 3 tables + 2 indexes created. Output shows "Successfully executed".

- [ ] **Step 4.3: Verify tables exist**

Run:
```bash
wrangler d1 execute clicks-db --remote --command="SELECT name FROM sqlite_master WHERE type='table';"
```
Expected output includes `videos`, `links`, `clicks` (and `sqlite_sequence` from AUTOINCREMENT).

- [ ] **Step 4.4: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/migrations/0001_init.sql
git commit -m "feat(worker): add D1 schema migration for videos, links, clicks tables"
```

---

## Task 5: Common helper — `common/cloudflare.py` (TDD)

REST API client for D1 SQL queries and KV reads/writes. Used by `add_links.py` and `sync_clicks.py`.

**Files:**
- Create: `yt-analysis/tests/test_cloudflare.py`
- Create: `common/cloudflare.py`

- [ ] **Step 5.1: Write failing test for `D1Client.query()`**

Create `yt-analysis/tests/test_cloudflare.py`:
```python
"""Tests for common.cloudflare REST client."""

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
    def test_query_posts_to_correct_url(self, mocker, cf_env):
        mock_post = mocker.patch("common.cloudflare.requests.post")
        mock_post.return_value.json.return_value = {
            "success": True,
            "result": [{"results": [{"slug": "a/b"}], "success": True}],
        }
        mock_post.return_value.raise_for_status.return_value = None

        client = D1Client()
        result = client.query("SELECT * FROM links WHERE slug = ?", ["a/b"])

        mock_post.assert_called_once()
        url = mock_post.call_args[0][0]
        assert "accounts/test-account/d1/database/test-d1/query" in url
        body = mock_post.call_args.kwargs["json"]
        assert body == {"sql": "SELECT * FROM links WHERE slug = ?", "params": ["a/b"]}
        assert result == [{"slug": "a/b"}]

    def test_query_raises_on_api_error(self, mocker, cf_env):
        mock_post = mocker.patch("common.cloudflare.requests.post")
        mock_post.return_value.json.return_value = {
            "success": False,
            "errors": [{"message": "syntax error"}],
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

Run: `pytest yt-analysis/tests/test_cloudflare.py -v`
Expected: `ImportError: cannot import name 'D1Client'`.

- [ ] **Step 5.3: Implement `common/cloudflare.py`**

Create `common/cloudflare.py`:
```python
"""Cloudflare REST API clients for D1 and KV.

Both read auth + IDs from env vars (loaded by common.env).
"""

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
        """Execute a parameterized SQL statement. Returns the list of result rows."""
        url = f"{CF_API_BASE}/accounts/{self.account_id}/d1/database/{self.database_id}/query"
        body = {"sql": sql, "params": params or []}
        resp = requests.post(
            url,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            json=body,
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        if not data.get("success"):
            errs = data.get("errors", [])
            msg = "; ".join(e.get("message", "?") for e in errs) or "unknown error"
            raise RuntimeError(f"D1 query failed: {msg}")
        # D1 returns: {"result": [{"results": [...], "success": true, ...}]}
        results = data["result"][0].get("results", [])
        return results


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
            data=value,
            timeout=15,
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

- [ ] **Step 5.4: Run tests, verify pass**

Run: `pytest yt-analysis/tests/test_cloudflare.py -v`
Expected: 3 passed.

- [ ] **Step 5.5: Commit**

```bash
git add common/cloudflare.py yt-analysis/tests/test_cloudflare.py
git commit -m "feat(common): add cloudflare.py with D1Client and KVClient"
```

---

## Task 6: Worker implementation (`workers/redirector/src/index.ts`)

Redirect logic: KV lookup → 302 + fire-and-forget D1 INSERT. Includes pure-function unit tests.

**Files:**
- Create: `workers/redirector/test/slug.test.ts`
- Create: `workers/redirector/src/index.ts`
- Create: `workers/redirector/vitest.config.ts`

- [ ] **Step 6.1: Add vitest config**

Create `workers/redirector/vitest.config.ts`:
```ts
import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    include: ["test/**/*.test.ts"],
  },
});
```

- [ ] **Step 6.2: Write failing tests for pure helpers**

Create `workers/redirector/test/slug.test.ts`:
```ts
import { describe, it, expect } from "vitest";
import { hashIdentifier, isValidSlug } from "../src/index";

describe("hashIdentifier", () => {
  it("returns 16-char hex string", async () => {
    const result = await hashIdentifier("hello");
    expect(result).toMatch(/^[0-9a-f]{16}$/);
  });

  it("returns the same hash for the same input", async () => {
    const a = await hashIdentifier("foo");
    const b = await hashIdentifier("foo");
    expect(a).toBe(b);
  });

  it("returns different hashes for different inputs", async () => {
    const a = await hashIdentifier("foo");
    const b = await hashIdentifier("bar");
    expect(a).not.toBe(b);
  });

  it("returns empty string for empty input", async () => {
    expect(await hashIdentifier("")).toBe("");
  });
});

describe("isValidSlug", () => {
  it("accepts code/tool form", () => {
    expect(isValidSlug("acha/heygen")).toBe(true);
  });

  it("accepts hyphenated tool", () => {
    expect(isValidSlug("acha/envato-elements")).toBe(true);
  });

  it("rejects empty", () => {
    expect(isValidSlug("")).toBe(false);
  });

  it("rejects single segment (no slash)", () => {
    expect(isValidSlug("acha")).toBe(false);
  });

  it("rejects deeper nesting", () => {
    expect(isValidSlug("acha/heygen/extra")).toBe(false);
  });

  it("rejects illegal chars", () => {
    expect(isValidSlug("acha/hey gen")).toBe(false);
    expect(isValidSlug("acha/heygen?utm=x")).toBe(false);
  });
});
```

- [ ] **Step 6.3: Run tests, expect failure (no source file)**

Run from `workers/redirector/`:
```bash
npm test
```
Expected: build error — `src/index.ts` not found.

- [ ] **Step 6.4: Implement Worker source**

Create `workers/redirector/src/index.ts`:
```ts
/**
 * Redirector Worker for go.agrolloo.com/*
 *
 * - Reads slug from URL path
 * - Looks up target_url in KV
 * - Returns 302 redirect to target_url
 * - Fire-and-forget logs the click to D1 (does NOT block the redirect)
 *
 * Dedup is intentionally NOT done here. sync_clicks.py deduplicates at query
 * time with `GROUP BY ip_hash, ua_hash, (clicked_at / 3600)`. This keeps the
 * redirect path free of any synchronous D1 dependency.
 */

export interface Env {
  CLICKS_KV: KVNamespace;
  DB: D1Database;
}

const NOT_FOUND_BODY = "Link not found";

export async function hashIdentifier(value: string): Promise<string> {
  if (!value) return "";
  const data = new TextEncoder().encode(value);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(buf))
    .slice(0, 8)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

const SLUG_RE = /^[a-zA-Z0-9]+\/[a-zA-Z0-9-]+$/;

export function isValidSlug(slug: string): boolean {
  return SLUG_RE.test(slug);
}

export default {
  async fetch(req: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(req.url);
    const slug = url.pathname.replace(/^\/+/, ""); // strip leading slash

    if (!slug || !isValidSlug(slug)) {
      return new Response(NOT_FOUND_BODY, {
        status: 404,
        headers: { "content-type": "text/plain" },
      });
    }

    const target = await env.CLICKS_KV.get(slug);
    if (!target) {
      return new Response(NOT_FOUND_BODY, {
        status: 404,
        headers: { "content-type": "text/plain" },
      });
    }

    // Fire-and-forget click log (does not block the redirect).
    const ip = req.headers.get("cf-connecting-ip") ?? "";
    const ua = req.headers.get("user-agent") ?? "";
    const referer = req.headers.get("referer") ?? "";
    ctx.waitUntil(logClick(env, slug, ip, ua, referer));

    return Response.redirect(target, 302);
  },
};

async function logClick(
  env: Env,
  slug: string,
  ip: string,
  ua: string,
  referer: string,
): Promise<void> {
  try {
    const ipHash = await hashIdentifier(ip);
    const uaHash = await hashIdentifier(ua);
    const ts = Math.floor(Date.now() / 1000);
    await env.DB.prepare(
      "INSERT INTO clicks (slug, clicked_at, ip_hash, ua_hash, referer) VALUES (?, ?, ?, ?, ?)",
    )
      .bind(slug, ts, ipHash, uaHash, referer)
      .run();
  } catch (e) {
    // Log to console; never throw — we don't want to spam errors that block CF
    console.error("logClick failed", e);
  }
}
```

- [ ] **Step 6.5: Run tests, verify pass**

Run from `workers/redirector/`:
```bash
npm test
```
Expected: 10 tests passed (4 hashIdentifier + 6 isValidSlug).

- [ ] **Step 6.6: Typecheck**

Run: `npm run typecheck`
Expected: no errors.

- [ ] **Step 6.7: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/src/index.ts workers/redirector/test/slug.test.ts \
        workers/redirector/vitest.config.ts
git commit -m "feat(worker): implement redirector with KV lookup + fire-and-forget D1 logging"
```

---

## Task 7: Deploy Worker + DNS route

Get `go.agrolloo.com/*` routing to the Worker.

- [ ] **Step 7.1: Confirm DNS migration is complete**

Verify by visiting `https://dash.cloudflare.com/`. Click `agrolloo.com` — should show **"Active"** status. If still pending, wait. Do not proceed if status is anything other than Active.

- [ ] **Step 7.2: Add `go.agrolloo.com` DNS record**

In CF dashboard: `agrolloo.com` → DNS → Records → Add record:
- Type: `AAAA`
- Name: `go`
- IPv6 address: `100::` (a placeholder — Worker route will intercept)
- Proxy status: **Proxied** (orange cloud)
- TTL: Auto

Save. The record is "fake" — the actual response comes from the Worker route we'll add next.

- [ ] **Step 7.3: Add Worker route to wrangler.toml**

Append to `workers/redirector/wrangler.toml`:
```toml

[[routes]]
pattern = "go.agrolloo.com/*"
zone_name = "agrolloo.com"
```

- [ ] **Step 7.4: Deploy the Worker**

Run from `workers/redirector/`:
```bash
wrangler deploy
```
Expected output: shows the deployed URL `https://go.agrolloo.com/*` and a `*.workers.dev` URL.

- [ ] **Step 7.5: Smoke-test 404 path**

Run:
```bash
curl -sI https://go.agrolloo.com/nonexistent
```
Expected: `HTTP/2 404` with body `Link not found` (visible via `curl -i`).

- [ ] **Step 7.6: Insert a test slug into KV and D1, then verify the redirect works**

Run from `workers/redirector/`:
```bash
wrangler kv key put --remote --binding=CLICKS_KV "test/example" "https://example.com/"
```

Run:
```bash
curl -sI https://go.agrolloo.com/test/example
```
Expected: `HTTP/2 302`, `location: https://example.com/`.

- [ ] **Step 7.7: Verify the click was logged**

Run from `workers/redirector/`:
```bash
wrangler d1 execute clicks-db --remote --command="SELECT slug, clicked_at FROM clicks ORDER BY id DESC LIMIT 1;"
```
Expected: one row with `slug = "test/example"` and a recent timestamp.

- [ ] **Step 7.8: Clean up test slug**

Run:
```bash
wrangler kv key delete --remote --binding=CLICKS_KV "test/example"
wrangler d1 execute clicks-db --remote --command="DELETE FROM clicks WHERE slug='test/example';"
```

- [ ] **Step 7.9: Commit**

```bash
cd /Users/kbtg/codebase/myproj
git add workers/redirector/wrangler.toml
git commit -m "deploy(worker): add go.agrolloo.com route + verify end-to-end redirect"
```

---

## Task 8: `yt-analysis/add_links.py` (TDD)

CLI: register a video + its tool links. Reads URLs from Affiliate Programs sheet, writes to D1 + KV.

**Files:**
- Create: `yt-analysis/tests/test_add_links.py`
- Create: `yt-analysis/add_links.py`

- [ ] **Step 8.1: Write failing tests for `generate_video_code()`**

Create `yt-analysis/tests/test_add_links.py`:
```python
"""Tests for yt-analysis.add_links."""

import os
import sys

import pytest

# add_links.py lives at yt-analysis/add_links.py — make it importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import add_links  # type: ignore  # noqa: E402


class TestGenerateVideoCode:
    def test_returns_4_char_string(self):
        code = add_links.generate_video_code(existing_codes=set())
        assert len(code) == 4

    def test_only_uses_base62_chars(self):
        code = add_links.generate_video_code(existing_codes=set())
        assert all(c.isalnum() for c in code)

    def test_avoids_collisions(self, mocker):
        # Force the random generator to return "abcd" twice then "wxyz"
        mocker.patch.object(
            add_links.secrets,
            "choice",
            side_effect=list("abcd" + "abcd" + "wxyz"),
        )
        code = add_links.generate_video_code(existing_codes={"abcd"})
        assert code == "wxyz"

    def test_raises_after_too_many_collisions(self, mocker):
        mocker.patch.object(add_links.secrets, "choice", side_effect=list("abcd" * 1000))
        with pytest.raises(RuntimeError, match="generate"):
            add_links.generate_video_code(existing_codes={"abcd"}, max_attempts=5)
```

- [ ] **Step 8.2: Run tests, expect ImportError**

Run: `pytest yt-analysis/tests/test_add_links.py -v`
Expected: `ImportError: No module named 'add_links'`.

- [ ] **Step 8.3: Implement `generate_video_code` and stub the rest**

Create `yt-analysis/add_links.py`:
```python
"""Register a YouTube video's affiliate links in the Cloudflare link tracker.

Usage:
  python3 yt-analysis/add_links.py "Video title" tool1 tool2 ...

Reads target URLs from the Affiliate Programs sheet (env: AFFILIATE_PROGRAMS_SHEET_URL).
Writes (video, link) rows into D1 and pushes slug->target_url mappings to KV.
Errors out if any tool is missing from the sheet OR has approval status != Approved.
"""

import argparse
import os
import secrets
import sys
import time

# Make `from common.x import y` work when running this script directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.affiliate import load_affiliate_records, normalize_tool_name  # noqa: E402
from common.cloudflare import D1Client, KVClient  # noqa: E402

BASE62 = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CODE_LENGTH = 4


def generate_video_code(existing_codes: set[str], max_attempts: int = 100) -> str:
    """Generate a unique 4-char base62 code, avoiding existing_codes."""
    for _ in range(max_attempts):
        code = "".join(secrets.choice(BASE62) for _ in range(CODE_LENGTH))
        if code not in existing_codes:
            return code
    raise RuntimeError(
        f"Could not generate a unique {CODE_LENGTH}-char code in {max_attempts} attempts"
    )


def main() -> int:
    raise NotImplementedError("main() built in later steps")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 8.4: Run tests, verify pass**

Run: `pytest yt-analysis/tests/test_add_links.py::TestGenerateVideoCode -v`
Expected: 4 passed.

- [ ] **Step 8.5: Add tests for `register_video()` (the core orchestrator)**

Append to `yt-analysis/tests/test_add_links.py`:
```python
class TestRegisterVideo:
    @pytest.fixture
    def mock_affiliates(self, mocker):
        from common.affiliate import AffiliateRecord
        records = {
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
        return mocker.patch("add_links.load_affiliate_records", return_value=records)

    @pytest.fixture
    def mock_d1(self, mocker):
        d1 = mocker.MagicMock(spec=D1Client)
        d1.query.return_value = []  # default: no existing video
        mocker.patch("add_links.D1Client", return_value=d1)
        return d1

    @pytest.fixture
    def mock_kv(self, mocker):
        kv = mocker.MagicMock(spec=KVClient)
        mocker.patch("add_links.KVClient", return_value=kv)
        return kv

    def test_creates_new_video_and_links(self, mock_affiliates, mock_d1, mock_kv):
        result = add_links.register_video(
            "Heygen vs Synthesia review",
            ["heygen", "synthesia"],
            link_domain="go.agrolloo.com",
        )

        assert len(result.short_urls) == 2
        assert result.video_code in result.short_urls["heygen"]
        assert result.short_urls["heygen"].startswith("https://go.agrolloo.com/")
        assert result.short_urls["heygen"].endswith("/heygen")

        # D1: 1 video INSERT + 2 links INSERTs (or all in one batch)
        sql_calls = [c.args[0] for c in mock_d1.query.call_args_list]
        assert any("INSERT INTO videos" in s for s in sql_calls)
        assert sum("INSERT INTO links" in s for s in sql_calls) == 2

        # KV: 2 puts
        assert mock_kv.put.call_count == 2

    def test_errors_on_missing_tool(self, mock_affiliates, mock_d1, mock_kv):
        with pytest.raises(SystemExit, match=r"^2$"):
            add_links.register_video(
                "Some video", ["heygen", "doesnotexist"], link_domain="go.agrolloo.com"
            )

    def test_errors_on_unapproved_tool(self, mock_affiliates, mock_d1, mock_kv):
        with pytest.raises(SystemExit, match=r"^2$"):
            add_links.register_video(
                "Some video", ["pending-tool"], link_domain="go.agrolloo.com"
            )

    def test_idempotent_on_existing_video(self, mock_affiliates, mock_d1, mock_kv):
        # Simulate existing video found in D1
        mock_d1.query.side_effect = [
            [{"video_code": "acha", "video_title": "Heygen vs Synthesia review"}],  # videos lookup
            [{"slug": "acha/heygen"}],  # existing links
            None,  # INSERT links new
        ]
        result = add_links.register_video(
            "Heygen vs Synthesia review",
            ["heygen", "synthesia"],
            link_domain="go.agrolloo.com",
        )
        assert result.video_code == "acha"
        # Only synthesia is new, so only 1 INSERT INTO links + 1 KV put
        sql_calls = [c.args[0] for c in mock_d1.query.call_args_list]
        assert sum("INSERT INTO links" in s for s in sql_calls) == 1
        assert mock_kv.put.call_count == 1
```

- [ ] **Step 8.6: Run tests, expect failure**

Run: `pytest yt-analysis/tests/test_add_links.py::TestRegisterVideo -v`
Expected: 4 failed (`register_video` not implemented).

- [ ] **Step 8.7: Implement `register_video()`**

Replace the `main()` stub in `yt-analysis/add_links.py` with the full implementation:

```python
from dataclasses import dataclass


@dataclass
class RegisterResult:
    video_code: str
    is_new_video: bool
    short_urls: dict[str, str]      # tool_slug -> short URL
    coupon_codes: dict[str, str]    # tool_slug -> coupon code (empty string if none)


def _existing_video_code_for_title(d1: D1Client, title: str) -> str | None:
    rows = d1.query("SELECT video_code FROM videos WHERE video_title = ? LIMIT 1", [title])
    return rows[0]["video_code"] if rows else None


def _existing_slugs_for_video(d1: D1Client, video_code: str) -> set[str]:
    rows = d1.query("SELECT slug FROM links WHERE video_code = ?", [video_code])
    return {r["slug"] for r in rows}


def _existing_codes(d1: D1Client) -> set[str]:
    rows = d1.query("SELECT video_code FROM videos", [])
    return {r["video_code"] for r in rows}


def register_video(
    video_title: str, tools: list[str], link_domain: str
) -> RegisterResult:
    if not video_title.strip():
        print("ERROR: video title is empty", file=sys.stderr)
        sys.exit(2)
    if not tools:
        print("ERROR: at least one tool is required", file=sys.stderr)
        sys.exit(2)

    # Normalize tools (caller may pass any case/whitespace)
    requested = [normalize_tool_name(t) for t in tools]

    affiliates = load_affiliate_records()
    missing = [t for t in requested if t not in affiliates]
    if missing:
        print(
            f"ERROR: tools not found in Affiliate Programs sheet: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(2)

    unapproved = [t for t in requested if not affiliates[t].is_approved]
    if unapproved:
        print(
            "ERROR: these tools have approval_status != Approved (refusing to create dead links): "
            f"{', '.join(unapproved)}",
            file=sys.stderr,
        )
        sys.exit(2)

    d1 = D1Client()
    kv = KVClient()

    existing_code = _existing_video_code_for_title(d1, video_title)
    if existing_code is not None:
        video_code = existing_code
        is_new_video = False
        already_present_slugs = _existing_slugs_for_video(d1, video_code)
    else:
        video_code = generate_video_code(_existing_codes(d1))
        is_new_video = True
        already_present_slugs = set()

    now = int(time.time())

    if is_new_video:
        d1.query(
            "INSERT INTO videos (video_code, video_title, created_at) VALUES (?, ?, ?)",
            [video_code, video_title, now],
        )

    short_urls: dict[str, str] = {}
    coupon_codes: dict[str, str] = {}
    for tool in requested:
        slug = f"{video_code}/{tool}"
        short_urls[tool] = f"https://{link_domain}/{slug}"
        coupon_codes[tool] = affiliates[tool].coupon_code

        if slug in already_present_slugs:
            continue  # idempotent skip

        target = affiliates[tool].target_url
        d1.query(
            "INSERT INTO links (slug, video_code, tool, target_url, created_at) VALUES (?, ?, ?, ?, ?)",
            [slug, video_code, tool, target, now],
        )
        kv.put(slug, target)

    return RegisterResult(
        video_code=video_code,
        is_new_video=is_new_video,
        short_urls=short_urls,
        coupon_codes=coupon_codes,
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Register a video's affiliate links in the link tracker."
    )
    parser.add_argument("video_title", help="The YouTube video title")
    parser.add_argument("tools", nargs="+", help="Tool names (matched against Affiliate Programs sheet)")
    args = parser.parse_args()

    link_domain = os.getenv("LINK_DOMAIN")
    if not link_domain:
        print("ERROR: LINK_DOMAIN not set in .env", file=sys.stderr)
        return 2

    result = register_video(args.video_title, args.tools, link_domain)

    status = "Created" if result.is_new_video else "Updated"
    print(f"\n✓ {status} video {result.video_code} — {args.video_title!r}\n")
    print("YouTube description block:")
    for tool, url in result.short_urls.items():
        print(f"  {tool} → {url}")

    print("\nCoupon codes (FYI):")
    for tool, code in result.coupon_codes.items():
        print(f"  {tool}: {code or '(no code)'}")

    return 0
```

- [ ] **Step 8.8: Run all add_links tests**

Run: `pytest yt-analysis/tests/test_add_links.py -v`
Expected: 8 passed total (4 generate_video_code + 4 register_video).

- [ ] **Step 8.9: Manual smoke test against real D1**

Add a real test entry. From repo root:
```bash
source venv/bin/activate
python3 yt-analysis/add_links.py "Plan smoke test video" heygen
```
Expected output: prints `✓ Created video <code>`, the short URL `https://go.agrolloo.com/<code>/heygen`, and the coupon code `HEY30`.

Verify the click target works:
```bash
curl -sI "https://go.agrolloo.com/$(echo <code>)/heygen"
```
Expected: `302` to `https://heygen.sjv.io/abc` (or whatever URL is in your sheet).

- [ ] **Step 8.10: Clean up smoke test entry**

Run from repo root:
```bash
wrangler d1 execute clicks-db --remote --command="DELETE FROM links WHERE video_code IN (SELECT video_code FROM videos WHERE video_title='Plan smoke test video');"
wrangler d1 execute clicks-db --remote --command="DELETE FROM videos WHERE video_title='Plan smoke test video';"
```
Then delete the KV entry. (Note the slug from the smoke test output above and replace `<slug>` below.)
```bash
wrangler kv key delete --remote --binding=CLICKS_KV --config workers/redirector/wrangler.toml "<slug>"
```

- [ ] **Step 8.11: Commit**

```bash
git add yt-analysis/add_links.py yt-analysis/tests/test_add_links.py
git commit -m "feat(yt-analysis): add add_links.py to register video links in D1+KV"
```

---

## Task 9: `yt-analysis/sync_clicks.py` (TDD)

Reads `affiliate_links` column from Analysis sheet, queries D1 with deduplication, writes `clicks_last_30d` and `clicks_all_time` columns.

**Files:**
- Create: `yt-analysis/tests/test_sync_clicks.py`
- Create: `yt-analysis/sync_clicks.py`

- [ ] **Step 9.1: Write failing tests for the slug regex extractor**

Create `yt-analysis/tests/test_sync_clicks.py`:
```python
"""Tests for yt-analysis.sync_clicks."""

import os
import sys
import time

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sync_clicks  # type: ignore  # noqa: E402


class TestExtractSlugs:
    def test_extracts_single_slug(self):
        cell = "Tools: heygen https://go.agrolloo.com/acha/heygen"
        assert sync_clicks.extract_slugs(cell, "go.agrolloo.com") == ["acha/heygen"]

    def test_extracts_multiple_slugs(self):
        cell = "https://go.agrolloo.com/acha/heygen\nhttps://go.agrolloo.com/acha/synthesia"
        result = sync_clicks.extract_slugs(cell, "go.agrolloo.com")
        assert result == ["acha/heygen", "acha/synthesia"]

    def test_ignores_other_domains(self):
        cell = "https://other.com/foo/bar https://go.agrolloo.com/acha/heygen"
        assert sync_clicks.extract_slugs(cell, "go.agrolloo.com") == ["acha/heygen"]

    def test_dedupes_within_one_cell(self):
        cell = "https://go.agrolloo.com/acha/heygen and again https://go.agrolloo.com/acha/heygen"
        assert sync_clicks.extract_slugs(cell, "go.agrolloo.com") == ["acha/heygen"]

    def test_empty_cell_returns_empty(self):
        assert sync_clicks.extract_slugs("", "go.agrolloo.com") == []
```

- [ ] **Step 9.2: Run, expect ImportError**

Run: `pytest yt-analysis/tests/test_sync_clicks.py -v`
Expected: `ImportError: No module named 'sync_clicks'`.

- [ ] **Step 9.3: Implement `extract_slugs` and stub the rest**

Create `yt-analysis/sync_clicks.py`:
```python
"""Fill click counts in the Analysis sheet from D1.

Reads:  affiliate_links column from "Per video cost,views and clicks" tab
Writes: clicks_last_30d and clicks_all_time columns

Both windows deduplicate clicks by (ip_hash, ua_hash, hour_bucket) at query time.
"""

import os
import re
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from common.cloudflare import D1Client  # noqa: E402
from common.sheets import col_letter, extract_sheet_id, get_gspread_client  # noqa: E402

DEST_TAB = "Per video cost,views and clicks"
LINKS_HEADER = "affiliate_links"
CLICKS_30D_HEADER = "clicks_last_30d"
CLICKS_ALL_HEADER = "clicks_all_time"


def extract_slugs(cell: str, link_domain: str) -> list[str]:
    """Pull all <code>/<tool> slugs that follow the configured link domain."""
    if not cell:
        return []
    pattern = re.compile(
        rf"https?://{re.escape(link_domain)}/([a-zA-Z0-9]+/[a-zA-Z0-9-]+)"
    )
    seen: list[str] = []
    for m in pattern.finditer(cell):
        slug = m.group(1)
        if slug not in seen:
            seen.append(slug)
    return seen


def main() -> int:
    raise NotImplementedError
```

- [ ] **Step 9.4: Run tests, verify pass**

Run: `pytest yt-analysis/tests/test_sync_clicks.py::TestExtractSlugs -v`
Expected: 5 passed.

- [ ] **Step 9.5: Write tests for `count_clicks_per_slug()` (D1 mocked)**

Append to `yt-analysis/tests/test_sync_clicks.py`:
```python
class TestCountClicksPerSlug:
    def test_runs_two_queries_per_slug(self, mocker):
        d1 = mocker.MagicMock()
        # Mock returns: [{"n": <count>}] for each query
        d1.query.side_effect = [
            [{"n": 12}],  # acha/heygen 30d
            [{"n": 142}], # acha/heygen all-time
            [{"n": 5}],   # acha/synthesia 30d
            [{"n": 38}],  # acha/synthesia all-time
        ]
        result = sync_clicks.count_clicks_per_slug(
            d1, ["acha/heygen", "acha/synthesia"], now_ts=1746820000
        )
        assert result == {
            "acha/heygen": (12, 142),
            "acha/synthesia": (5, 38),
        }
        # Two queries per slug = 4 total
        assert d1.query.call_count == 4

    def test_handles_zero_count(self, mocker):
        d1 = mocker.MagicMock()
        d1.query.side_effect = [[{"n": 0}], [{"n": 0}]]
        result = sync_clicks.count_clicks_per_slug(d1, ["new/tool"], now_ts=1746820000)
        assert result == {"new/tool": (0, 0)}

    def test_query_uses_30d_threshold(self, mocker):
        d1 = mocker.MagicMock()
        d1.query.side_effect = [[{"n": 0}], [{"n": 0}]]
        sync_clicks.count_clicks_per_slug(d1, ["a/b"], now_ts=1_000_000_000)
        first_call_params = d1.query.call_args_list[0].args[1]
        # second param = (now_ts - 30 days in seconds)
        assert first_call_params == ["a/b", 1_000_000_000 - 30 * 86400]
```

- [ ] **Step 9.6: Run, expect failure**

Run: `pytest yt-analysis/tests/test_sync_clicks.py::TestCountClicksPerSlug -v`
Expected: `AttributeError: 'count_clicks_per_slug'`.

- [ ] **Step 9.7: Implement `count_clicks_per_slug` and `main`**

Replace the `main()` stub in `yt-analysis/sync_clicks.py` with:
```python
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

THIRTY_DAYS_SECONDS = 30 * 86400


def count_clicks_per_slug(
    d1: D1Client, slugs: list[str], now_ts: int
) -> dict[str, tuple[int, int]]:
    """Returns {slug: (count_last_30d, count_all_time)} with 1-hour-window dedup."""
    threshold = now_ts - THIRTY_DAYS_SECONDS
    out: dict[str, tuple[int, int]] = {}
    for slug in slugs:
        r30 = d1.query(SQL_30D, [slug, threshold])
        rall = d1.query(SQL_ALL, [slug])
        c30 = int(r30[0]["n"]) if r30 else 0
        call = int(rall[0]["n"]) if rall else 0
        out[slug] = (c30, call)
    return out


def main() -> int:
    link_domain = os.getenv("LINK_DOMAIN")
    if not link_domain:
        print("ERROR: LINK_DOMAIN not set in .env", file=sys.stderr)
        return 2

    sheet_url = os.getenv("ANALYSIS_INCOME_SHEET_URL")
    if not sheet_url:
        print("ERROR: ANALYSIS_INCOME_SHEET_URL not set in .env", file=sys.stderr)
        return 2

    client = get_gspread_client()
    ws = client.open_by_key(extract_sheet_id(sheet_url)).worksheet(DEST_TAB)

    rows = ws.get_all_values()
    if not rows:
        print("Sheet is empty.")
        return 0

    header = [h.strip() for h in rows[0]]
    try:
        links_col = header.index(LINKS_HEADER)
        c30_col = header.index(CLICKS_30D_HEADER)
        call_col = header.index(CLICKS_ALL_HEADER)
    except ValueError:
        print(
            f"ERROR: missing required headers. Need {LINKS_HEADER!r}, "
            f"{CLICKS_30D_HEADER!r}, {CLICKS_ALL_HEADER!r}.",
            file=sys.stderr,
        )
        return 2

    # Per-row: extract slugs from affiliate_links cell
    row_slugs: dict[int, list[str]] = {}  # 1-based row number -> list of slugs
    for i, row in enumerate(rows[1:], start=2):
        cell = row[links_col] if len(row) > links_col else ""
        slugs = extract_slugs(cell, link_domain)
        if slugs:
            row_slugs[i] = slugs

    if not row_slugs:
        print(f"No slugs found in {LINKS_HEADER!r} column.")
        return 0

    unique_slugs = sorted({s for slugs in row_slugs.values() for s in slugs})
    print(f"Querying {len(unique_slugs)} unique slug(s)...")

    d1 = D1Client()
    counts = count_clicks_per_slug(d1, unique_slugs, now_ts=int(time.time()))

    # Build per-row formatted strings
    updates = []
    for row_num, slugs in row_slugs.items():
        c30_lines = []
        call_lines = []
        for slug in slugs:
            tool = slug.split("/", 1)[1]
            c30, call = counts.get(slug, (0, 0))
            c30_lines.append(f"{tool}: {c30}")
            call_lines.append(f"{tool}: {call}")
        updates.append(
            {"range": f"{col_letter(c30_col)}{row_num}", "values": [["\n".join(c30_lines)]]}
        )
        updates.append(
            {"range": f"{col_letter(call_col)}{row_num}", "values": [["\n".join(call_lines)]]}
        )

    if updates:
        ws.batch_update(updates, value_input_option="USER_ENTERED")

    print(f"Updated {len(row_slugs)} row(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 9.8: Run all sync_clicks tests**

Run: `pytest yt-analysis/tests/test_sync_clicks.py -v`
Expected: 8 passed.

- [ ] **Step 9.9: Commit**

```bash
git add yt-analysis/sync_clicks.py yt-analysis/tests/test_sync_clicks.py
git commit -m "feat(yt-analysis): add sync_clicks.py to fill click counts in Analysis sheet"
```

---

## Task 10: Sheet schema setup + end-to-end smoke test

Final integration: add the new columns, register a real video, click the URL manually, run sync_clicks.py, verify the cells fill correctly.

- [ ] **Step 10.1: Add three new column headers to the Analysis sheet**

Open `https://docs.google.com/spreadsheets/d/13H88Z_4f58lHB0xsRXKPaZ7qagMyvXxZdJ1S-szH18c/edit#gid=0` (the `Per video cost,views and clicks` tab).

In row 1, after the existing rightmost column (`affiliate_link_clicks`), add three new headers in adjacent columns:
- `affiliate_links`
- `clicks_last_30d`
- `clicks_all_time`

(Don't rename or delete the existing `affiliate_link_clicks` column. We're keeping it untouched.)

- [ ] **Step 10.2: Register a real test video**

From repo root:
```bash
source venv/bin/activate
python3 yt-analysis/add_links.py "Affiliate tracker E2E test" heygen synthesia
```
Expected: prints YouTube description block with two URLs, e.g.:
```
✓ Created video qB7m — "Affiliate tracker E2E test"

YouTube description block:
  heygen → https://go.agrolloo.com/qB7m/heygen
  synthesia → https://go.agrolloo.com/qB7m/synthesia
```

Note the two URLs.

- [ ] **Step 10.3: Add a row to the Analysis sheet**

In the Analysis sheet, add a new row:
- `video_title`: `Affiliate tracker E2E test`
- `affiliate_links` (the column you added in step 10.1): paste both short URLs, one per line

Other columns can stay blank.

- [ ] **Step 10.4: Generate a few clicks**

In a terminal:
```bash
for i in 1 2 3; do curl -sI "https://go.agrolloo.com/qB7m/heygen" > /dev/null; sleep 1; done
curl -sI "https://go.agrolloo.com/qB7m/synthesia" > /dev/null
```
(Replace `qB7m` with the actual code from step 10.2.)

That's 3 clicks on heygen + 1 on synthesia. The 3 heygen clicks should dedupe to 1 (same IP+UA, same hour).

- [ ] **Step 10.5: Verify clicks logged**

Run from repo root:
```bash
wrangler d1 execute clicks-db --remote --command="SELECT slug, COUNT(*) FROM clicks GROUP BY slug;" --config workers/redirector/wrangler.toml
```
Expected: 3 rows for `qB7m/heygen`, 1 row for `qB7m/synthesia`.

- [ ] **Step 10.6: Run `sync_clicks.py`**

```bash
source venv/bin/activate
python3 yt-analysis/sync_clicks.py
```
Expected: prints `Querying 2 unique slug(s)...` and `Updated 1 row(s).`

- [ ] **Step 10.7: Verify the sheet was filled**

Refresh the Analysis sheet. The row for "Affiliate tracker E2E test":
- `clicks_last_30d` should show:
  ```
  heygen: 1
  synthesia: 1
  ```
  (3 heygen raw clicks dedupe to 1 because same IP+UA in same hour.)
- `clicks_all_time` should show the same 1 + 1.

- [ ] **Step 10.8: Clean up E2E test data**

```bash
cd workers/redirector
# Get the slugs to clean up
wrangler kv key delete --remote --binding=CLICKS_KV "qB7m/heygen"
wrangler kv key delete --remote --binding=CLICKS_KV "qB7m/synthesia"
wrangler d1 execute clicks-db --remote --command="DELETE FROM clicks WHERE slug LIKE 'qB7m/%';"
wrangler d1 execute clicks-db --remote --command="DELETE FROM links WHERE video_code='qB7m';"
wrangler d1 execute clicks-db --remote --command="DELETE FROM videos WHERE video_code='qB7m';"
```
(Replace `qB7m` with the actual code.)

In the sheet, delete the test row.

- [ ] **Step 10.9: Final commit**

If anything in earlier tasks was tweaked during E2E testing, commit it now. Otherwise:
```bash
cd /Users/kbtg/codebase/myproj
git status   # confirm clean
```

If clean, no commit needed. Done.

---

## Acceptance criteria

When all tasks above are complete and committed, you should be able to:

1. Run `python3 yt-analysis/add_links.py "<video title>" tool1 tool2` and get back working `https://go.agrolloo.com/<code>/<tool>` URLs that 302-redirect to the correct affiliate URLs.
2. Run `python3 yt-analysis/sync_clicks.py` and have the Analysis sheet's `clicks_last_30d` and `clicks_all_time` columns populated with per-tool, deduplicated click counts.
3. Have 100% test pass rate: `pytest yt-analysis/tests -v` shows ≥25 passed; `cd workers/redirector && npm test` shows 10 passed.
4. Worker logs every click to D1; redirects never block on D1.

## Troubleshooting (likely issues)

- **`wrangler whoami` shows nothing** → re-run `wrangler login`.
- **`wrangler d1 execute` returns 401** → API token missing scopes. Re-issue with D1:Edit + Workers KV Storage:Edit.
- **`go.agrolloo.com` returns the WP site, not the Worker** → DNS not propagated yet, or Worker route in `wrangler.toml` is wrong. Confirm zone status is "Active" in CF dashboard, then `wrangler deploy` again.
- **Python `ImportError: No module named common`** → you're running the script from a non-root cwd without the `sys.path.insert(...)` line. Always run from `myproj/` root, or use the script's built-in path-insertion.
- **`sync_clicks.py` prints "no slugs found"** → check that the `affiliate_links` cells contain URLs matching `https://go.agrolloo.com/<code>/<tool>` exactly. Trailing punctuation, query strings (`?utm=...`), etc., will fail the regex. Strip them.
