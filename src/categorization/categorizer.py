"""
Categorization Module.
Classifies apps and domains into categories using rule-based matching.
Supports local rules file + backend-pushed overrides.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from src.config import config

logger = logging.getLogger("agent.categorization")


DEFAULT_CATEGORIES = {
    "version": 0,
    "apps": {},
    "domains": {},
    "ignored_domains": [],
    "ignored_apps": [],
}

VALID_CATEGORIES = {"productivity", "communication", "entertainment", "social", "other"}


class Categorizer:
    """
    Classifies apps and domains into categories.

    Priority order:
    1. Backend overrides (highest)
    2. Local rules file
    3. Default: "other"
    """

    def __init__(self):
        self._app_rules: dict[str, str] = {}
        self._domain_rules: dict[str, str] = {}
        self._ignored_domains: set[str] = set()
        self._ignored_apps: set[str] = set()
        self._browser_names: set[str] = set()
        self._version: int = 0

        self._load_rules()

    def _load_rules(self):
        """Load category rules from the categories JSON file."""
        categories_path = config.CATEGORIES_PATH
        logger.debug(f"Loading categories from: {categories_path}")
        logger.debug(f"File exists: {categories_path.exists()}")

        data = DEFAULT_CATEGORIES

        if categories_path.exists():
            try:
                raw = categories_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                logger.debug(f"Parsed JSON successfully, keys: {list(data.keys())}")
            except UnicodeDecodeError as e:
                logger.error(f"Encoding error reading {categories_path}: {e}")
                # Try with latin-1 fallback
                try:
                    raw = categories_path.read_text(encoding="latin-1")
                    data = json.loads(raw)
                    logger.warning("Loaded categories with latin-1 fallback encoding")
                except Exception as e2:
                    logger.error(f"Fallback encoding also failed: {e2}")
            except json.JSONDecodeError as e:
                logger.error(f"JSON parse error in {categories_path}: {e}")
            except Exception as e:
                logger.error(f"Failed to load categories file: {e}")
        else:
            logger.warning(f"Categories file not found: {categories_path}")

        self._version = data.get("version", 0)

        # Build app rules lookup
        apps = data.get("apps", {})
        for category, app_list in apps.items():
            if category == "browsers":
                for name in app_list:
                    self._browser_names.add(name.lower().strip())
                continue

            if category not in VALID_CATEGORIES:
                logger.warning(f"Unknown app category '{category}', skipping")
                continue

            for name in app_list:
                normalized = name.lower().strip()
                self._app_rules[normalized] = category

        # Build domain rules lookup
        domains = data.get("domains", {})
        for category, domain_list in domains.items():
            if category not in VALID_CATEGORIES:
                logger.warning(f"Unknown domain category '{category}', skipping")
                continue

            for domain in domain_list:
                normalized = domain.lower().strip()
                self._domain_rules[normalized] = category

        # Ignored lists
        for d in data.get("ignored_domains", []):
            self._ignored_domains.add(d.lower().strip())

        for a in data.get("ignored_apps", []):
            self._ignored_apps.add(a.lower().strip())

        logger.info(
            f"Categorizer loaded v{self._version}: "
            f"{len(self._app_rules)} app rules, "
            f"{len(self._domain_rules)} domain rules, "
            f"{len(self._browser_names)} browsers, "
            f"{len(self._ignored_domains)} ignored domains, "
            f"{len(self._ignored_apps)} ignored apps"
        )

    def categorize_app(self, app_name: str) -> str:
        """
        Classify an application by name.
        Returns: productivity, communication, entertainment, social, or other
        """
        if not app_name:
            return "other"

        lower = app_name.lower().strip()

        # Strip .exe for matching
        if lower.endswith(".exe"):
            lower = lower[:-4]

        # Exact match
        if lower in self._app_rules:
            return self._app_rules[lower]

        # Check if any rule is a substring of the app name
        for rule_name, category in self._app_rules.items():
            if rule_name in lower or lower in rule_name:
                return category

        return "other"

    def categorize_domain(self, domain: str) -> str:
        """
        Classify a domain name.
        Returns: productivity, communication, entertainment, social, or other
        """
        if not domain:
            return "other"

        lower = domain.lower().strip()

        # Remove www. prefix
        if lower.startswith("www."):
            lower = lower[4:]

        # Exact match
        if lower in self._domain_rules:
            return self._domain_rules[lower]

        # Check parent domain (e.g. "docs.google.com" -> "google.com")
        parts = lower.split(".")
        if len(parts) > 2:
            parent = ".".join(parts[-2:])
            if parent in self._domain_rules:
                return self._domain_rules[parent]

        # Check if any rule matches as suffix
        for rule_domain, category in self._domain_rules.items():
            if lower.endswith("." + rule_domain):
                return category

        return "other"

    def is_browser(self, app_name: str) -> bool:
        """Check if the given app name is a known browser."""
        if not app_name:
            return False

        lower = app_name.lower().strip()

        if lower.endswith(".exe"):
            lower = lower[:-4]

        if lower in self._browser_names:
            return True

        browser_keywords = {"chrome", "firefox", "edge", "safari", "brave", "opera", "vivaldi", "arc"}
        for keyword in browser_keywords:
            if keyword in lower:
                return True

        return False

    def is_ignored_domain(self, domain: str) -> bool:
        """Check if a domain should be ignored."""
        if not domain:
            return True

        lower = domain.lower().strip()

        if lower.startswith("www."):
            lower = lower[4:]

        # Exact match
        if lower in self._ignored_domains:
            return True

        # Wildcard matching
        for pattern in self._ignored_domains:
            if pattern.startswith("*."):
                suffix = pattern[1:]
                if lower.endswith(suffix):
                    return True

        # IP addresses are ignored
        if self._is_ip_address(lower):
            return True

        return False

    def is_ignored_app(self, app_name: str) -> bool:
        """Check if an app should be ignored."""
        if not app_name:
            return True

        lower = app_name.lower().strip()

        if lower in self._ignored_apps:
            return True

        if lower.endswith(".exe"):
            stripped = lower[:-4]
            if stripped in self._ignored_apps:
                return True

        return False

    def normalize_domain(self, domain: str) -> str:
        """Clean up a domain name for storage."""
        if not domain:
            return ""

        cleaned = domain.lower().strip().rstrip(".")

        if cleaned.startswith("www."):
            cleaned = cleaned[4:]

        return cleaned

    def update_rules(self, new_rules: dict):
        """Update category rules from backend config push."""
        new_version = new_rules.get("version", 0)
        if new_version <= self._version:
            logger.debug(
                f"Skipping rules update: received v{new_version}, "
                f"current v{self._version}"
            )
            return

        logger.info(f"Updating category rules from v{self._version} to v{new_version}")

        apps = new_rules.get("apps", {})
        for category, app_list in apps.items():
            if category == "browsers":
                for name in app_list:
                    self._browser_names.add(name.lower().strip())
                continue
            if category not in VALID_CATEGORIES:
                continue
            for name in app_list:
                self._app_rules[name.lower().strip()] = category

        domains = new_rules.get("domains", {})
        for category, domain_list in domains.items():
            if category not in VALID_CATEGORIES:
                continue
            for domain in domain_list:
                self._domain_rules[domain.lower().strip()] = category

        for d in new_rules.get("ignored_domains", []):
            self._ignored_domains.add(d.lower().strip())
        for a in new_rules.get("ignored_apps", []):
            self._ignored_apps.add(a.lower().strip())

        self._version = new_version
        self._save_rules(new_rules)

        logger.info(
            f"Rules updated to v{self._version}: "
            f"{len(self._app_rules)} app rules, "
            f"{len(self._domain_rules)} domain rules"
        )

    def _save_rules(self, rules: dict):
        """Save rules to the categories file."""
        try:
            with open(config.CATEGORIES_PATH, "w", encoding="utf-8") as f:
                json.dump(rules, f, indent=2, ensure_ascii=True)
            logger.debug(f"Rules saved to {config.CATEGORIES_PATH}")
        except Exception as e:
            logger.error(f"Failed to save rules: {e}")

    @staticmethod
    def _is_ip_address(value: str) -> bool:
        """Check if a string looks like an IP address."""
        parts = value.split(".")
        if len(parts) == 4:
            try:
                return all(0 <= int(p) <= 255 for p in parts)
            except ValueError:
                pass

        if ":" in value and all(c in "0123456789abcdef:" for c in value):
            return True

        return False

    @property
    def version(self) -> int:
        return self._version

    @property
    def app_rule_count(self) -> int:
        return len(self._app_rules)

    @property
    def domain_rule_count(self) -> int:
        return len(self._domain_rules)