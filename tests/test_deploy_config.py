"""Tests to catch deployment configuration inconsistencies.

These prevent regressions like:
- SPA 404 document pointing to wrong path (PR #81)
- Vite base path / MSAL redirectUri / workflow FRONTEND_PATH drift
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = ROOT / "frontend"


class TestDeployFrontendWorkflow:
    """Verify deploy-frontend.yml is internally consistent."""

    workflow_path = ROOT / ".github" / "workflows" / "deploy-frontend.yml"

    def _read(self) -> str:
        return self.workflow_path.read_text()

    def test_404_document_includes_frontend_path(self):
        """The 404 document must live under FRONTEND_PATH, not at the root.

        Azure Storage Static Website serves files from $web/<FRONTEND_PATH>/,
        so the fallback document for SPA routing must also be under that prefix.
        """
        text = self._read()
        assert "FRONTEND_PATH" in text

        m = re.search(r"--404-document\s+\"([^\"]+)\"", text)
        assert m, "--404-document not found in workflow"
        doc_path = m.group(1)

        assert "FRONTEND_PATH" in doc_path or doc_path.startswith("dashboard"), (
            f"404 document '{doc_path}' does not reference FRONTEND_PATH. "
            "SPA routes under /dashboard/* will return Azure 404 instead of index.html."
        )

    def test_destination_path_matches_frontend_path(self):
        text = self._read()
        assert "--destination-path" in text
        m = re.search(r"--destination-path\s+\"([^\"]+)\"", text)
        assert m
        assert "FRONTEND_PATH" in m.group(1)

    def test_index_document_is_index_html(self):
        text = self._read()
        m = re.search(r"--index-document\s+\"([^\"]+)\"", text)
        assert m
        assert m.group(1) == "index.html"


class TestViteBaseAndWorkflowConsistency:
    """Vite base path and workflow FRONTEND_PATH must agree."""

    def _vite_base(self) -> str:
        text = (FRONTEND_DIR / "vite.config.ts").read_text()
        m = re.search(r'base:\s*["\'](/[^"\']+)["\']', text)
        assert m, "Could not find base in vite.config.ts"
        return m.group(1).strip("/")

    def _workflow_frontend_path(self) -> str:
        text = (ROOT / ".github" / "workflows" / "deploy-frontend.yml").read_text()
        m = re.search(r"FRONTEND_PATH:\s*(\S+)", text)
        assert m, "FRONTEND_PATH not found in workflow"
        return m.group(1).strip("/")

    def test_vite_base_matches_frontend_path(self):
        """If these diverge, assets load from the wrong path after deploy."""
        assert self._vite_base() == self._workflow_frontend_path()


class TestMsalRedirectUri:
    """MSAL redirectUri must match the vite base path."""

    def test_redirect_uri_uses_vite_base(self):
        msal_text = (FRONTEND_DIR / "src" / "auth" / "msalConfig.ts").read_text()
        vite_text = (FRONTEND_DIR / "vite.config.ts").read_text()

        vite_base_m = re.search(r'base:\s*["\'](/[^"\']+)["\']', vite_text)
        assert vite_base_m
        vite_base = vite_base_m.group(1).rstrip("/")

        redirect_m = re.search(r'redirectUri:\s*(.+)', msal_text)
        assert redirect_m, "Could not parse redirectUri from msalConfig.ts"
        redirect_line = redirect_m.group(1).strip().rstrip(",")

        assert f'"{vite_base}"' in redirect_line or f"'{vite_base}'" in redirect_line or vite_base in redirect_line, (
            f"MSAL redirectUri '{redirect_line}' does not reference "
            f"vite base '{vite_base}'. SSO callback will hit the wrong path."
        )


class TestNoTopLevelDuplicates:
    """Catch duplicate top-level const/let/function declarations in key files.

    This prevents merge-conflict artifacts like duplicate PAGE_SIZE (PR #80).
    """

    def _find_duplicate_declarations(self, filepath: Path) -> list[str]:
        if not filepath.exists():
            return []
        text = filepath.read_text()
        pattern = re.compile(
            r"^(?:export\s+)?(?:const|let|var|function)\s+(\w+)",
            re.MULTILINE,
        )
        names = [m.group(1) for m in pattern.finditer(text)]
        seen: dict[str, int] = {}
        dupes = []
        for name in names:
            seen[name] = seen.get(name, 0) + 1
            if seen[name] == 2:
                dupes.append(name)
        return dupes

    def test_orders_page_no_duplicate_declarations(self):
        dupes = self._find_duplicate_declarations(
            FRONTEND_DIR / "src" / "pages" / "Orders.tsx"
        )
        assert dupes == [], f"Duplicate top-level declarations in Orders.tsx: {dupes}"

    def test_api_ts_no_duplicate_declarations(self):
        dupes = self._find_duplicate_declarations(
            FRONTEND_DIR / "src" / "lib" / "api.ts"
        )
        assert dupes == [], f"Duplicate top-level declarations in api.ts: {dupes}"

    def test_constants_no_duplicate_declarations(self):
        dupes = self._find_duplicate_declarations(
            FRONTEND_DIR / "src" / "lib" / "constants.ts"
        )
        assert dupes == [], f"Duplicate top-level declarations in constants.ts: {dupes}"
