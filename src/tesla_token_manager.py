"""Tesla OAuth token store and automatic refresh helpers (Wave 11A.1)."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv


class TeslaTokenManagerError(Exception):
    """Base token manager error."""


class TeslaReauthorizationRequiredError(TeslaTokenManagerError):
    """Raised when refresh token flow cannot recover authentication."""


@dataclass(frozen=True, slots=True)
class TeslaTokenRecord:
    """Token payload stored on local disk."""

    access_token: str
    refresh_token: str
    expires_at: str | None
    updated_at: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def _parse_iso_utc(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_error_text(response: requests.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:160] if hasattr(response, "text") else "non-json error"

    if isinstance(payload, dict):
        return str(
            payload.get("error_description")
            or payload.get("error")
            or payload.get("message")
            or "oauth_error"
        )[:160]
    return str(payload)[:160]


class TeslaTokenManager:
    """Manages Tesla OAuth tokens in a local gitignored store."""

    def __init__(
        self,
        *,
        client_id: str,
        client_secret: str,
        access_token: str,
        refresh_token: str,
        auth_base_url: str = "https://auth.tesla.com/oauth2/v3",
        store_path: str | Path = "data/tesla_token_store.json",
        request_timeout_seconds: float = 15.0,
        request_verify_tls: bool = True,
        session: requests.Session | Any | None = None,
    ) -> None:
        self.client_id = client_id.strip()
        self.client_secret = client_secret.strip()
        self.auth_base_url = auth_base_url.strip() or "https://auth.tesla.com/oauth2/v3"
        self.request_timeout_seconds = float(request_timeout_seconds)
        self.request_verify_tls = bool(request_verify_tls)
        self.store_path = Path(store_path)
        self.session = session or requests.Session()
        self._seed_access_token = access_token.strip()
        self._seed_refresh_token = refresh_token.strip()
        self._ensure_seed_record()

    @staticmethod
    def from_env(env_file: str | None = None) -> "TeslaTokenManager":
        """Create token manager from local `.env`/environment variables."""

        load_dotenv(dotenv_path=env_file, override=False)
        return TeslaTokenManager(
            client_id=os.getenv("TESLA_CLIENT_ID", ""),
            client_secret=os.getenv("TESLA_CLIENT_SECRET", ""),
            access_token=os.getenv("TESLA_ACCESS_TOKEN", ""),
            refresh_token=os.getenv("TESLA_REFRESH_TOKEN", ""),
            auth_base_url=os.getenv("TESLA_AUTH_BASE_URL", "https://auth.tesla.com/oauth2/v3"),
            store_path=os.getenv("TESLA_TOKEN_STORE_PATH", "data/tesla_token_store.json"),
            request_verify_tls=_parse_bool_env("TESLA_API_VERIFY_TLS", True),
        )

    def _token_endpoint(self) -> str:
        base = self.auth_base_url.rstrip("/")
        if base.endswith("/token"):
            return base
        return f"{base}/token"

    def _ensure_seed_record(self) -> None:
        """Initialize token store from env seeds when missing."""

        current = self.load_record()
        if current is None:
            if not self._seed_access_token and not self._seed_refresh_token:
                return
            self.save_record(
                TeslaTokenRecord(
                    access_token=self._seed_access_token,
                    refresh_token=self._seed_refresh_token,
                    expires_at=None,
                    updated_at=_iso_utc(_utc_now()),
                )
            )
            return

        if current.refresh_token:
            return
        if not self._seed_refresh_token:
            return
        self.save_record(
            TeslaTokenRecord(
                access_token=current.access_token,
                refresh_token=self._seed_refresh_token,
                expires_at=current.expires_at,
                updated_at=_iso_utc(_utc_now()),
            )
        )

    def load_record(self) -> TeslaTokenRecord | None:
        if not self.store_path.exists():
            return None
        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise TeslaTokenManagerError(f"Unable to read token store: {exc}") from exc

        if not isinstance(raw, dict):
            raise TeslaTokenManagerError("Token store has invalid format")

        return TeslaTokenRecord(
            access_token=str(raw.get("access_token") or "").strip(),
            refresh_token=str(raw.get("refresh_token") or "").strip(),
            expires_at=(str(raw.get("expires_at")).strip() if raw.get("expires_at") else None),
            updated_at=str(raw.get("updated_at") or "").strip(),
        )

    def save_record(self, record: TeslaTokenRecord) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.store_path.with_suffix(f"{self.store_path.suffix}.tmp")
        payload = {
            "access_token": record.access_token,
            "refresh_token": record.refresh_token,
            "expires_at": record.expires_at,
            "updated_at": record.updated_at,
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        try:
            temp_path.write_text(text, encoding="utf-8")
            os.replace(temp_path, self.store_path)
        except OSError as exc:
            raise TeslaTokenManagerError(f"Unable to write token store: {exc}") from exc
        finally:
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass

    def get_access_token(self) -> str:
        record = self.load_record()
        token = ""
        if record is not None:
            token = record.access_token
        if not token:
            token = self._seed_access_token
        if not token:
            raise TeslaReauthorizationRequiredError("Tesla re-authorization required")
        return token

    def get_refresh_token(self) -> str:
        record = self.load_record()
        token = ""
        if record is not None:
            token = record.refresh_token
        if not token:
            token = self._seed_refresh_token
        if not token:
            raise TeslaReauthorizationRequiredError("Tesla re-authorization required")
        return token

    def is_access_token_expiring(self, *, leeway_seconds: int = 120) -> bool:
        record = self.load_record()
        if record is None:
            return False
        expiry = _parse_iso_utc(record.expires_at)
        if expiry is None:
            return False
        return _utc_now() + timedelta(seconds=max(leeway_seconds, 0)) >= expiry

    def ensure_fresh_access_token(self, *, leeway_seconds: int = 120) -> None:
        if self.is_access_token_expiring(leeway_seconds=leeway_seconds):
            self.refresh_now()

    def refresh_now(self) -> TeslaTokenRecord:
        if not self.client_id or not self.client_secret:
            raise TeslaReauthorizationRequiredError("Tesla re-authorization required")

        refresh_token = self.get_refresh_token()
        try:
            response = self.session.request(
                method="POST",
                url=self._token_endpoint(),
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                },
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                },
                timeout=self.request_timeout_seconds,
                verify=self.request_verify_tls,
            )
        except requests.RequestException as exc:
            raise TeslaTokenManagerError(f"Tesla token refresh network error: {exc}") from exc

        if response.status_code >= 400:
            _safe_error_text(response)
            raise TeslaReauthorizationRequiredError("Tesla re-authorization required")

        try:
            payload = response.json()
        except ValueError as exc:
            raise TeslaTokenManagerError("Tesla token refresh returned non-JSON response") from exc

        if not isinstance(payload, dict):
            raise TeslaTokenManagerError("Tesla token refresh returned unexpected payload")

        access_token = str(payload.get("access_token") or "").strip()
        new_refresh_token = str(payload.get("refresh_token") or "").strip()
        expires_in_raw = payload.get("expires_in")
        try:
            expires_in = int(expires_in_raw)
        except (TypeError, ValueError):
            expires_in = 3600

        if not access_token or not new_refresh_token:
            raise TeslaReauthorizationRequiredError("Tesla re-authorization required")

        now = _utc_now()
        record = TeslaTokenRecord(
            access_token=access_token,
            refresh_token=new_refresh_token,
            expires_at=_iso_utc(now + timedelta(seconds=max(1, expires_in))),
            updated_at=_iso_utc(now),
        )
        self.save_record(record)
        self._seed_access_token = access_token
        self._seed_refresh_token = new_refresh_token
        return record

    def status(self) -> dict[str, Any]:
        record = self.load_record()
        access_token = ""
        refresh_token = ""
        expires_at = None
        updated_at = None
        if record is not None:
            access_token = record.access_token
            refresh_token = record.refresh_token
            expires_at = record.expires_at
            updated_at = record.updated_at
        else:
            access_token = self._seed_access_token
            refresh_token = self._seed_refresh_token

        expiry_dt = _parse_iso_utc(expires_at) if expires_at else None
        expires_in_seconds: int | None = None
        if expiry_dt is not None:
            expires_in_seconds = int((expiry_dt - _utc_now()).total_seconds())

        return {
            "store_path": str(self.store_path),
            "store_exists": self.store_path.exists(),
            "access_token_present": bool(access_token),
            "refresh_token_present": bool(refresh_token),
            "expires_at": expires_at,
            "updated_at": updated_at,
            "expires_in_seconds": expires_in_seconds,
        }

    def close(self) -> None:
        close_method = getattr(self.session, "close", None)
        if callable(close_method):
            close_method()


def _parse_bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    value = raw.strip().lower()
    if value in {"1", "true", "yes", "y", "on"}:
        return True
    if value in {"0", "false", "no", "n", "off"}:
        return False
    return default


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage local Tesla OAuth token store (Wave 11A.1)."
    )
    parser.add_argument("--status", action="store_true", help="Show token store status.")
    parser.add_argument(
        "--refresh-now",
        action="store_true",
        help="Force immediate OAuth refresh using refresh_token.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not args.status and not args.refresh_now:
        args.status = True

    manager = TeslaTokenManager.from_env()
    try:
        if args.refresh_now:
            manager.refresh_now()
            print("refresh_result: ok")

        if args.status:
            status = manager.status()
            print(f"store_path          : {status['store_path']}")
            print(f"store_exists        : {status['store_exists']}")
            print(f"access_token_present: {status['access_token_present']}")
            print(f"refresh_token_present: {status['refresh_token_present']}")
            print(f"expires_at          : {status['expires_at']}")
            print(f"updated_at          : {status['updated_at']}")
            print(f"expires_in_seconds  : {status['expires_in_seconds']}")
    except TeslaReauthorizationRequiredError as exc:
        print(str(exc))
        return 1
    except TeslaTokenManagerError as exc:
        print(f"token_manager_error: {exc}")
        return 1
    finally:
        manager.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
