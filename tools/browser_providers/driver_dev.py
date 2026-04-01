"""Driver.dev cloud browser provider."""

import logging
import os
import uuid
from typing import Dict

import requests

from tools.browser_providers.base import CloudBrowserProvider

logger = logging.getLogger(__name__)

_BASE_URL = "https://api.driver.dev/v1"


class DriverDevProvider(CloudBrowserProvider):
    """Driver.dev (https://driver.dev) cloud browser backend."""

    def provider_name(self) -> str:
        return "Driver.dev"

    def is_configured(self) -> bool:
        return bool(os.environ.get("DRIVER_API_KEY"))

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------

    def _headers(self) -> Dict[str, str]:
        api_key = os.environ.get("DRIVER_API_KEY")
        if not api_key:
            raise ValueError(
                "DRIVER_API_KEY environment variable is required. "
                "Get your key at https://app.driver.dev"
            )
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }

    def create_session(self, task_id: str) -> Dict[str, object]:
        # Always-on defaults
        session_config: Dict[str, object] = {
            "type": "hosted",
            "captchaSolver": True,
        }

        # Optional env-var knobs
        window_size = os.environ.get("DRIVER_WINDOW_SIZE")
        if window_size:
            session_config["windowSize"] = window_size

        country = os.environ.get("DRIVER_COUNTRY")
        if country:
            session_config["country"] = country

        proxy_url = os.environ.get("DRIVER_PROXY_URL")
        if proxy_url:
            session_config["proxyUrl"] = proxy_url

        duration = os.environ.get("DRIVER_SESSION_DURATION")
        if duration:
            try:
                duration_val = int(duration)
                if 60 < duration_val <= 3600:
                    session_config["duration"] = duration_val
            except ValueError:
                logger.warning("Invalid DRIVER_SESSION_DURATION value: %s", duration)

        if os.environ.get("DRIVER_ADBLOCK", "false").lower() == "true":
            session_config["adblock"] = True

        if os.environ.get("DRIVER_FAST_MODE", "false").lower() == "true":
            session_config["fast"] = True

        # --- Create session via API ---
        response = requests.post(
            f"{_BASE_URL}/browser/session",
            headers=self._headers(),
            json=session_config,
            timeout=30,
        )

        if not response.ok:
            raise RuntimeError(
                f"Failed to create Driver.dev session: "
                f"{response.status_code} {response.text}"
            )

        session_data = response.json()
        session_name = f"hermes_{task_id}_{uuid.uuid4().hex[:8]}"

        features_enabled = {
            "hosted": True,
            "captcha_solver": True,
        }
        if window_size:
            features_enabled["window_size"] = True
        if country:
            features_enabled["country"] = True
        if proxy_url:
            features_enabled["proxy"] = True
        if session_config.get("adblock"):
            features_enabled["adblock"] = True

        feature_str = ", ".join(k for k, v in features_enabled.items() if v)
        logger.info("Created Driver.dev session %s with features: %s", session_name, feature_str)

        return {
            "session_name": session_name,
            "bb_session_id": session_data["sessionId"],
            "cdp_url": session_data["cdpUrl"],
            "features": features_enabled,
        }

    def close_session(self, session_id: str) -> bool:
        try:
            response = requests.delete(
                f"{_BASE_URL}/browser/session",
                headers=self._headers(),
                params={"sessionId": session_id},
                timeout=10,
            )
            if response.status_code in (200, 201, 204):
                logger.debug("Successfully closed Driver.dev session %s", session_id)
                return True
            else:
                logger.warning(
                    "Failed to close Driver.dev session %s: HTTP %s - %s",
                    session_id,
                    response.status_code,
                    response.text[:200],
                )
                return False
        except Exception as e:
            logger.error("Exception closing Driver.dev session %s: %s", session_id, e)
            return False

    def emergency_cleanup(self, session_id: str) -> None:
        api_key = os.environ.get("DRIVER_API_KEY")
        if not api_key:
            logger.warning("Cannot emergency-cleanup Driver.dev session %s — missing credentials", session_id)
            return
        try:
            requests.delete(
                f"{_BASE_URL}/browser/session",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
                params={"sessionId": session_id},
                timeout=5,
            )
        except Exception as e:
            logger.debug("Emergency cleanup failed for Driver.dev session %s: %s", session_id, e)
