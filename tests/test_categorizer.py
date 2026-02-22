"""
Tests for the Categorization Module.
Run with: python -m pytest tests/test_categorizer.py -v
"""

import pytest
from unittest.mock import patch

from src.categorization.categorizer import Categorizer, VALID_CATEGORIES


@pytest.fixture
def categorizer():
    c = Categorizer()
    # Verify it loaded rules (if this fails, run: python scripts/generate_categories.py)
    if c.app_rule_count == 0:
        pytest.skip("categories.json not loaded - run: python scripts/generate_categories.py")
    return c


class TestAppCategorization:
    """Test application classification."""

    def test_productivity_apps(self, categorizer):
        assert categorizer.categorize_app("VSCode") == "productivity"
        assert categorizer.categorize_app("vscode") == "productivity"
        assert categorizer.categorize_app("code") == "productivity"
        assert categorizer.categorize_app("notion") == "productivity"
        assert categorizer.categorize_app("figma") == "productivity"

    def test_productivity_apps_with_exe(self, categorizer):
        assert categorizer.categorize_app("code.exe") == "productivity"
        assert categorizer.categorize_app("notepad++.exe") == "productivity"

    def test_communication_apps(self, categorizer):
        assert categorizer.categorize_app("slack") == "communication"
        assert categorizer.categorize_app("teams") == "communication"
        assert categorizer.categorize_app("zoom") == "communication"
        assert categorizer.categorize_app("discord") == "communication"

    def test_entertainment_apps(self, categorizer):
        assert categorizer.categorize_app("spotify") == "entertainment"
        assert categorizer.categorize_app("vlc") == "entertainment"

    def test_unknown_app_returns_other(self, categorizer):
        assert categorizer.categorize_app("random_app_xyz") == "other"
        assert categorizer.categorize_app("myCustomTool") == "other"

    def test_empty_app_returns_other(self, categorizer):
        assert categorizer.categorize_app("") == "other"
        assert categorizer.categorize_app(None) == "other"

    def test_case_insensitive(self, categorizer):
        assert categorizer.categorize_app("SLACK") == "communication"
        assert categorizer.categorize_app("Slack") == "communication"
        assert categorizer.categorize_app("sLaCk") == "communication"

    def test_returns_valid_category(self, categorizer):
        apps = ["VSCode", "Slack", "Spotify", "random", "", None]
        for app in apps:
            result = categorizer.categorize_app(app)
            assert result in VALID_CATEGORIES


class TestDomainCategorization:
    """Test domain classification."""

    def test_productivity_domains(self, categorizer):
        assert categorizer.categorize_domain("github.com") == "productivity"
        assert categorizer.categorize_domain("stackoverflow.com") == "productivity"
        assert categorizer.categorize_domain("docs.google.com") == "productivity"

    def test_social_domains(self, categorizer):
        assert categorizer.categorize_domain("twitter.com") == "social"
        assert categorizer.categorize_domain("instagram.com") == "social"
        assert categorizer.categorize_domain("linkedin.com") == "social"
        assert categorizer.categorize_domain("reddit.com") == "social"

    def test_entertainment_domains(self, categorizer):
        assert categorizer.categorize_domain("youtube.com") == "entertainment"
        assert categorizer.categorize_domain("netflix.com") == "entertainment"
        assert categorizer.categorize_domain("twitch.tv") == "entertainment"
        assert categorizer.categorize_domain("spotify.com") == "entertainment"

    def test_communication_domains(self, categorizer):
        assert categorizer.categorize_domain("slack.com") == "communication"
        assert categorizer.categorize_domain("mail.google.com") == "communication"

    def test_unknown_domain_returns_other(self, categorizer):
        assert categorizer.categorize_domain("randomsite123.com") == "other"
        assert categorizer.categorize_domain("my-internal-tool.io") == "other"

    def test_empty_domain_returns_other(self, categorizer):
        assert categorizer.categorize_domain("") == "other"
        assert categorizer.categorize_domain(None) == "other"

    def test_www_prefix_stripped(self, categorizer):
        assert categorizer.categorize_domain("www.github.com") == "productivity"
        assert categorizer.categorize_domain("www.youtube.com") == "entertainment"

    def test_subdomain_matches_parent(self, categorizer):
        assert categorizer.categorize_domain("docs.google.com") == "productivity"
        assert categorizer.categorize_domain("api.github.com") == "productivity"

    def test_case_insensitive(self, categorizer):
        assert categorizer.categorize_domain("GitHub.com") == "productivity"
        assert categorizer.categorize_domain("YOUTUBE.COM") == "entertainment"

    def test_returns_valid_category(self, categorizer):
        domains = ["github.com", "twitter.com", "youtube.com", "random.xyz", "", None]
        for domain in domains:
            result = categorizer.categorize_domain(domain)
            assert result in VALID_CATEGORIES


class TestBrowserDetection:
    """Test browser identification."""

    def test_known_browsers(self, categorizer):
        assert categorizer.is_browser("chrome") is True
        assert categorizer.is_browser("Chrome") is True
        assert categorizer.is_browser("google chrome") is True
        assert categorizer.is_browser("firefox") is True
        assert categorizer.is_browser("msedge") is True
        assert categorizer.is_browser("safari") is True
        assert categorizer.is_browser("brave") is True

    def test_browsers_with_exe(self, categorizer):
        assert categorizer.is_browser("chrome.exe") is True
        assert categorizer.is_browser("firefox.exe") is True

    def test_non_browsers(self, categorizer):
        assert categorizer.is_browser("VSCode") is False
        assert categorizer.is_browser("Slack") is False
        assert categorizer.is_browser("Spotify") is False

    def test_empty_not_browser(self, categorizer):
        assert categorizer.is_browser("") is False
        assert categorizer.is_browser(None) is False


class TestIgnoredDomains:
    """Test ignored domain detection."""

    def test_localhost_ignored(self, categorizer):
        assert categorizer.is_ignored_domain("localhost") is True
        assert categorizer.is_ignored_domain("127.0.0.1") is True
        assert categorizer.is_ignored_domain("0.0.0.0") is True

    def test_system_domains_ignored(self, categorizer):
        assert categorizer.is_ignored_domain("ocsp.digicert.com") is True
        assert categorizer.is_ignored_domain("connectivitycheck.gstatic.com") is True

    def test_wildcard_ignored(self, categorizer):
        assert categorizer.is_ignored_domain("mypc.local") is True
        assert categorizer.is_ignored_domain("printer.local") is True

    def test_regular_domains_not_ignored(self, categorizer):
        assert categorizer.is_ignored_domain("github.com") is False
        assert categorizer.is_ignored_domain("google.com") is False
        assert categorizer.is_ignored_domain("youtube.com") is False

    def test_ip_addresses_ignored(self, categorizer):
        assert categorizer.is_ignored_domain("192.168.1.1") is True
        assert categorizer.is_ignored_domain("10.0.0.1") is True
        assert categorizer.is_ignored_domain("8.8.8.8") is True

    def test_empty_ignored(self, categorizer):
        assert categorizer.is_ignored_domain("") is True
        assert categorizer.is_ignored_domain(None) is True


class TestIgnoredApps:
    """Test ignored app detection."""

    def test_system_apps_ignored(self, categorizer):
        assert categorizer.is_ignored_app("explorer") is True
        assert categorizer.is_ignored_app("explorer.exe") is True
        assert categorizer.is_ignored_app("svchost") is True
        assert categorizer.is_ignored_app("dwm") is True

    def test_regular_apps_not_ignored(self, categorizer):
        assert categorizer.is_ignored_app("chrome") is False
        assert categorizer.is_ignored_app("VSCode") is False
        assert categorizer.is_ignored_app("Slack") is False

    def test_empty_ignored(self, categorizer):
        assert categorizer.is_ignored_app("") is True
        assert categorizer.is_ignored_app(None) is True


class TestDomainNormalization:
    """Test domain name cleanup."""

    def test_strips_www(self):
        c = Categorizer()
        assert c.normalize_domain("www.github.com") == "github.com"

    def test_lowercase(self):
        c = Categorizer()
        assert c.normalize_domain("GitHub.COM") == "github.com"

    def test_strips_trailing_dot(self):
        c = Categorizer()
        assert c.normalize_domain("github.com.") == "github.com"

    def test_strips_whitespace(self):
        c = Categorizer()
        assert c.normalize_domain("  github.com  ") == "github.com"

    def test_combined(self):
        c = Categorizer()
        assert c.normalize_domain("  WWW.GitHub.COM.  ") == "github.com"

    def test_empty_returns_empty(self):
        c = Categorizer()
        assert c.normalize_domain("") == ""
        assert c.normalize_domain(None) == "" # type: ignore


class TestRuleUpdates:
    """Test dynamic rule updates from backend."""

    @patch.object(Categorizer, "_save_rules")
    def test_update_adds_new_rules(self, mock_save, categorizer):
        categorizer.update_rules({
            "version": categorizer.version + 1,
            "apps": {
                "productivity": ["my_custom_tool", "another_tool"],
            },
            "domains": {
                "productivity": ["mycustomsite.com"],
            },
        })

        assert categorizer.categorize_app("my_custom_tool") == "productivity"
        assert categorizer.categorize_domain("mycustomsite.com") == "productivity"
        mock_save.assert_called_once()

    @patch.object(Categorizer, "_save_rules")
    def test_update_skips_old_version(self, mock_save, categorizer):
        old_count = categorizer.app_rule_count

        categorizer.update_rules({
            "version": 0,
            "apps": {
                "productivity": ["should_not_be_added"],
            },
        })

        assert categorizer.app_rule_count == old_count
        mock_save.assert_not_called()

    @patch.object(Categorizer, "_save_rules")
    def test_update_overrides_existing(self, mock_save, categorizer):
        categorizer.update_rules({
            "version": categorizer.version + 1,
            "apps": {
                "entertainment": ["special_app"],
            },
        })
        assert categorizer.categorize_app("special_app") == "entertainment"

        categorizer.update_rules({
            "version": categorizer.version + 1,
            "apps": {
                "productivity": ["special_app"],
            },
        })
        assert categorizer.categorize_app("special_app") == "productivity"

    @patch.object(Categorizer, "_save_rules")
    def test_version_updates(self, mock_save, categorizer):
        v1 = categorizer.version
        categorizer.update_rules({"version": v1 + 5})
        assert categorizer.version == v1 + 5


class TestIPDetection:
    """Test IP address detection helper."""

    def test_ipv4(self):
        assert Categorizer._is_ip_address("192.168.1.1") is True
        assert Categorizer._is_ip_address("10.0.0.1") is True
        assert Categorizer._is_ip_address("255.255.255.255") is True
        assert Categorizer._is_ip_address("0.0.0.0") is True

    def test_not_ipv4(self):
        assert Categorizer._is_ip_address("github.com") is False
        assert Categorizer._is_ip_address("not.an.ip.address") is False
        assert Categorizer._is_ip_address("999.999.999.999") is False

    def test_ipv6(self):
        assert Categorizer._is_ip_address("::1") is True
        assert Categorizer._is_ip_address("fe80::1") is True

    def test_empty(self):
        assert Categorizer._is_ip_address("") is False


class TestProperties:
    """Test categorizer properties."""

    def test_version(self, categorizer):
        assert isinstance(categorizer.version, int)
        assert categorizer.version >= 1

    def test_app_rule_count(self, categorizer):
        assert isinstance(categorizer.app_rule_count, int)
        assert categorizer.app_rule_count > 0

    def test_domain_rule_count(self, categorizer):
        assert isinstance(categorizer.domain_rule_count, int)
        assert categorizer.domain_rule_count > 0