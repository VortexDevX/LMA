"""
Generate the categories.json file with proper UTF-8 encoding.
Run: python scripts/generate_categories.py
"""

import json
from pathlib import Path

data = {
    "version": 1,
    "updated_at": "2025-01-01T00:00:00Z",
    "apps": {
        "productivity": [
            "code", "vscode", "visual studio code",
            "intellij", "pycharm", "webstorm", "goland", "rider",
            "sublime_text", "sublime text",
            "atom",
            "notepad++", "notepad",
            "vim", "nvim", "neovim",
            "emacs",
            "figma",
            "notion",
            "obsidian",
            "excel", "word", "powerpoint",
            "libreoffice",
            "terminal", "cmd", "powershell", "wt", "iterm",
            "postman", "insomnia",
            "pgadmin", "dbeaver", "datagrip",
            "docker", "docker desktop",
            "git", "gitkraken", "sourcetree",
            "filezilla", "winscp",
        ],
        "communication": [
            "slack",
            "teams", "microsoft teams",
            "zoom", "zoom.us",
            "discord",
            "skype",
            "thunderbird",
            "outlook",
            "telegram", "telegram desktop",
            "whatsapp",
            "signal",
        ],
        "entertainment": [
            "spotify",
            "vlc", "vlc media player",
            "itunes", "music",
            "netflix",
            "steam",
            "epicgameslauncher",
            "battle.net",
        ],
        "social": [
            "tweetdeck",
        ],
        "browsers": [
            "chrome", "google chrome",
            "firefox", "mozilla firefox",
            "msedge", "microsoft edge", "edge",
            "safari",
            "brave", "brave browser",
            "opera", "opera gx",
            "vivaldi",
            "arc",
        ],
    },
    "domains": {
        "productivity": [
            "github.com", "gitlab.com", "bitbucket.org",
            "stackoverflow.com", "stackexchange.com",
            "docs.google.com", "sheets.google.com",
            "slides.google.com", "drive.google.com",
            "notion.so", "figma.com",
            "vercel.com", "netlify.com", "heroku.com",
            "aws.amazon.com", "console.cloud.google.com",
            "portal.azure.com",
            "docker.com", "hub.docker.com",
            "npmjs.com", "pypi.org", "readthedocs.io",
            "dev.to", "medium.com", "hashnode.dev",
            "jira.atlassian.com", "trello.com", "asana.com",
            "linear.app", "confluence.atlassian.com", "miro.com",
        ],
        "communication": [
            "slack.com", "teams.microsoft.com",
            "zoom.us", "discord.com",
            "meet.google.com", "mail.google.com",
            "outlook.live.com", "outlook.office365.com",
            "web.whatsapp.com", "web.telegram.org",
        ],
        "social": [
            "twitter.com", "x.com", "facebook.com",
            "instagram.com", "linkedin.com", "reddit.com",
            "tiktok.com", "pinterest.com", "snapchat.com",
            "threads.net", "mastodon.social",
        ],
        "entertainment": [
            "youtube.com", "netflix.com", "twitch.tv",
            "spotify.com", "primevideo.com", "disneyplus.com",
            "hotstar.com", "hulu.com", "crunchyroll.com",
            "soundcloud.com", "music.youtube.com",
            "music.apple.com",
        ],
    },
    "ignored_domains": [
        "localhost", "127.0.0.1", "0.0.0.0",
        "*.local", "*.internal",
        "ocsp.digicert.com", "crl.microsoft.com",
        "update.googleapis.com", "safebrowsing.googleapis.com",
        "fonts.googleapis.com", "fonts.gstatic.com",
        "cdn.jsdelivr.net", "cdnjs.cloudflare.com",
        "ajax.googleapis.com", "connectivitycheck.gstatic.com",
        "detectportal.firefox.com", "msftconnecttest.com",
    ],
    "ignored_apps": [
        "explorer", "explorer.exe",
        "finder", "systemd", "loginwindow",
        "dwm", "dwm.exe",
        "csrss", "csrss.exe",
        "svchost", "svchost.exe",
        "system", "idle",
        "taskmgr", "task manager",
        "searchhost", "searchui",
        "shellexperiencehost", "startmenuexperiencehost",
        "runtimebroker", "applicationframehost",
        "lockapp", "screenclippinghost",
    ],
}


def main():
    project_root = Path(__file__).parent.parent
    out_path = project_root / "data" / "categories.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)
        f.write("\n")

    print(f"Written to: {out_path}")
    print(f"File size: {out_path.stat().st_size} bytes")

    # Verify
    with open(out_path, "r", encoding="utf-8") as f:
        loaded = json.load(f)

    app_count = sum(len(v) for v in loaded["apps"].values())
    domain_count = sum(len(v) for v in loaded["domains"].values())
    print(f"App entries: {app_count}")
    print(f"Domain entries: {domain_count}")
    print(f"Ignored domains: {len(loaded['ignored_domains'])}")
    print(f"Ignored apps: {len(loaded['ignored_apps'])}")


if __name__ == "__main__":
    main()