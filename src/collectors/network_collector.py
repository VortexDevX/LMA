"""
Network / Domain Collector.
Monitors active network connections, resolves IPs to domain names,
and tracks per-domain bandwidth and duration.

Captures domain-level metadata only. No URLs, no content, no queries.
"""

import time
import socket
import subprocess
import threading
import logging
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

import psutil # type: ignore

from src.config import config
from src.platform import get_platform
from src.categorization.categorizer import Categorizer

logger = logging.getLogger("agent.collector.network")


# Ports to monitor (HTTP/HTTPS only)
MONITORED_PORTS = {80, 443, 8080, 8443}

# DNS cache limits
DNS_CACHE_MAX_SIZE = 2000
DNS_EVICTION_INTERVAL = 300  # seconds (5 minutes)


@dataclass
class DomainRecord:
    """Accumulated data for a single domain in one collection window."""
    domain: str
    app_name: str
    connection_count: int = 0
    first_seen: float = 0.0
    last_seen: float = 0.0
    active_connection_seconds: float = 0.0
    bytes_uploaded: int = 0
    bytes_downloaded: int = 0

    @property
    def duration_sec(self) -> int:
        if self.first_seen > 0 and self.last_seen > 0:
            return max(1, round(self.last_seen - self.first_seen))
        return 0

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "app_name": self.app_name,
            "bytes_uploaded": self.bytes_uploaded,
            "bytes_downloaded": self.bytes_downloaded,
            "duration_sec": self.duration_sec,
        }


@dataclass
class ConnectionSnapshot:
    """A snapshot of a single active connection."""
    pid: int
    process_name: str
    remote_ip: str
    remote_port: int
    protocol: str
    timestamp: float


class NetworkCollector:
    """
    Tracks domain-level network activity.

    Polls active TCP connections every NETWORK_POLL_INTERVAL seconds.
    Resolves destination IPs to domain names via DNS cache.
    Aggregates per-domain stats for each collection window.
    """

    def __init__(self):
        self._platform = get_platform()
        self._categorizer = Categorizer()
        self._lock = threading.Lock()

        # DNS resolution cache: ip -> domain
        self._dns_cache: dict[str, str] = {}
        self._dns_cache_ttl: dict[str, float] = {}
        self._dns_cache_duration = 600  # 10 minutes
        self._dns_cache_refresh_interval = 30  # seconds
        self._last_dns_cache_refresh_time = 0.0
        self._last_eviction_time = 0.0

        # Active connections tracking: (ip, port, pid) -> first_seen_time
        self._active_connections: dict[tuple, float] = {}

        # Domain accumulator: domain -> DomainRecord
        self._domains: dict[str, DomainRecord] = {}

        # Bandwidth tracking
        self._last_io_counters: Optional[tuple] = None
        self._last_io_time: float = 0.0

        # Thread control
        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Load ignored domains
        self._ignored_domains = set()
        categories = config.load_categories()
        for d in categories.get("ignored_domains", []):
            self._ignored_domains.add(d.lower().strip())

        # Populate DNS cache from system on startup
        self._load_system_dns_cache()

        logger.info(
            f"NetworkCollector initialized "
            f"(poll_interval={config.NETWORK_POLL_INTERVAL}s, "
            f"dns_cache_entries={len(self._dns_cache)})"
        )

    def start(self):
        """Start the collector polling thread."""
        if self._running:
            logger.warning("NetworkCollector already running")
            return

        self._running = True
        self._last_io_counters = self._get_io_counters()
        self._last_io_time = time.time()

        self._thread = threading.Thread(
            target=self._poll_loop,
            name="NetworkCollectorThread",
            daemon=True,
        )
        self._thread.start()
        logger.info("NetworkCollector started")

    def stop(self):
        """Stop the collector polling thread."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        logger.info("NetworkCollector stopped")

    def flush(self) -> list[dict]:
        """
        Return all accumulated domain records and reset.
        Called by the session manager every BATCH_SEND_INTERVAL.
        Returns list of domain dicts ready for the session manager.
        """
        with self._lock:
            records = []
            for domain_record in self._domains.values():
                if domain_record.duration_sec < config.MIN_DOMAIN_DURATION:
                    continue
                records.append(domain_record.to_dict())

            # Reset accumulator
            self._domains.clear()
            self._active_connections.clear()

        if records:
            logger.debug(f"Flushed {len(records)} domain records")

        return records

    # --------------------------------------------------
    # Polling loop
    # --------------------------------------------------

    def _poll_loop(self):
        """Main polling loop. Runs in a background thread."""
        logger.debug("Network poll loop started")

        while self._running:
            try:
                self._poll_once()
            except Exception as e:
                logger.error(f"Network poll error: {e}", exc_info=True)

            time.sleep(config.NETWORK_POLL_INTERVAL)

        logger.debug("Network poll loop ended")

    def _poll_once(self):
        """Single poll: snapshot connections, resolve domains, update stats."""
        now = time.time()
        self._refresh_dns_cache_if_needed(now)
        self._maybe_evict_dns_cache(now)

        # Get current connections
        snapshots = self._get_connection_snapshots()

        # Calculate bandwidth delta
        bytes_up_delta, bytes_down_delta = self._calculate_bandwidth_delta()

        # Track which connections are still active
        current_keys = set()

        with self._lock:
            for snap in snapshots:
                domain = self._resolve_ip(snap.remote_ip)
                if domain is None:
                    continue

                # Normalize domain
                domain = self._normalize_domain(domain)
                if not domain:
                    continue

                # Check if ignored
                if self._is_ignored(domain):
                    continue

                conn_key = (snap.remote_ip, snap.remote_port, snap.pid)
                current_keys.add(conn_key)

                # Track connection start time
                if conn_key not in self._active_connections:
                    self._active_connections[conn_key] = now

                # Update domain record
                app_name = self._platform.normalize_app_name(snap.process_name)
                record_key = domain

                if record_key not in self._domains:
                    self._domains[record_key] = DomainRecord(
                        domain=domain,
                        app_name=app_name,
                        first_seen=now,
                        last_seen=now,
                        connection_count=1,
                    )
                else:
                    self._domains[record_key].last_seen = now
                    self._domains[record_key].connection_count += 1
                    # Keep the most recent app name
                    self._domains[record_key].app_name = app_name

            # Distribute bandwidth proportionally across active domains
            if self._domains and (bytes_up_delta > 0 or bytes_down_delta > 0):
                self._distribute_bandwidth(bytes_up_delta, bytes_down_delta)

            # Clean up connections that are no longer active
            stale_keys = set(self._active_connections.keys()) - current_keys
            for key in stale_keys:
                del self._active_connections[key]

    # --------------------------------------------------
    # Connection snapshots
    # --------------------------------------------------

    def _get_connection_snapshots(self) -> list[ConnectionSnapshot]:
        """Get current TCP connections filtered to monitored ports."""
        snapshots = []
        now = time.time()

        try:
            connections = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError) as e:
            logger.debug(f"Permission denied reading connections: {e}")
            return snapshots
        except Exception as e:
            logger.error(f"Failed to get connections: {e}")
            return snapshots

        for conn in connections:
            if not conn.raddr:
                continue

            remote_port = conn.raddr.port
            if remote_port not in MONITORED_PORTS:
                continue

            is_tcp = conn.type == socket.SOCK_STREAM
            is_udp = conn.type == socket.SOCK_DGRAM
            if not is_tcp and not is_udp:
                continue

            # TCP: keep only established connections.
            # UDP (e.g. QUIC/HTTP3): no established state, keep if remote peer exists.
            if is_tcp and conn.status != psutil.CONN_ESTABLISHED:
                continue

            pid = conn.pid
            if pid is None or pid == 0:
                continue

            # Get process name
            proc_name = self._platform.get_process_name(pid)
            if proc_name is None:
                proc_name = "unknown"

            snapshots.append(ConnectionSnapshot(
                pid=pid,
                process_name=proc_name,
                remote_ip=conn.raddr.ip,
                remote_port=remote_port,
                protocol="tcp" if is_tcp else "udp",
                timestamp=now,
            ))

        return snapshots

    # --------------------------------------------------
    # DNS resolution
    # --------------------------------------------------

    def _resolve_ip(self, ip: str) -> Optional[str]:
        """Resolve an IP address to a domain name. Uses cache."""
        # Check cache first
        if ip in self._dns_cache:
            ttl = self._dns_cache_ttl.get(ip, 0)
            if time.time() - ttl < self._dns_cache_duration:
                cached = self._dns_cache[ip]
                return cached if cached else None

        # Try reverse DNS
        domain = self._reverse_dns(ip)

        if domain:
            self._dns_cache[ip] = domain
            self._dns_cache_ttl[ip] = time.time()
            return domain

        # Cache the miss too (avoid repeated lookups)
        self._dns_cache[ip] = ""
        self._dns_cache_ttl[ip] = time.time()
        return None

    def _reverse_dns(self, ip: str) -> Optional[str]:
        """Perform reverse DNS lookup for an IP."""
        try:
            hostname, _, _ = socket.gethostbyaddr(ip)
            if hostname and not self._is_ip_like(hostname):
                return hostname
        except (socket.herror, socket.gaierror, socket.timeout):
            pass
        except Exception:
            pass
        return None

    def _load_system_dns_cache(self):
        """Load the OS DNS cache to pre-populate our IP->domain mapping."""
        if sys.platform == "win32":
            self._load_windows_dns_cache()
        self._last_dns_cache_refresh_time = time.time()
        # macOS and Linux don't have easily accessible system DNS caches
        # They rely on runtime resolution

    def _refresh_dns_cache_if_needed(self, now: Optional[float] = None):
        """Refresh DNS cache periodically so recent browser lookups can be mapped."""
        if sys.platform != "win32":
            return

        ts = now if now is not None else time.time()
        if ts - self._last_dns_cache_refresh_time < self._dns_cache_refresh_interval:
            return

        self._load_windows_dns_cache()

    def _load_windows_dns_cache(self):
        """Parse Windows DNS cache from ipconfig /displaydns."""
        try:
            # CREATE_NO_WINDOW = 0x08000000 prevents console flash
            creation_flags = 0x08000000 if sys.platform == "win32" else 0
            result = subprocess.run(
                ["ipconfig", "/displaydns"],
                capture_output=True,
                text=True,
                timeout=10,
                encoding="utf-8",
                errors="ignore",
                creationflags=creation_flags,
            )

            if result.returncode != 0:
                return

            current_name = None
            for line in result.stdout.splitlines():
                line = line.strip()

                # Record Name line
                name_match = re.match(r"Record Name[\s.]*:\s*(.+)", line)
                if name_match:
                    current_name = name_match.group(1).strip().lower()
                    continue

                # A (Host) Record line with IP
                if current_name and ("A (Host)" in line or "Record Type" in line):
                    continue

                ip_match = re.match(
                    r"(?:A \(Host\) Record|AAAA Record|Data)[\s.]*:\s*([0-9a-fA-F:.]+)",
                    line,
                )
                if ip_match and current_name:
                    ip = ip_match.group(1)
                    # Only cache if domain looks valid
                    if "." in current_name and not self._is_ip_like(current_name):
                        self._dns_cache[ip] = current_name
                        self._dns_cache_ttl[ip] = time.time()
                    current_name = None

            logger.debug(
                f"Loaded {len(self._dns_cache)} entries from Windows DNS cache"
            )

        except subprocess.TimeoutExpired:
            logger.debug("Timeout reading Windows DNS cache")
        except FileNotFoundError:
            logger.debug("ipconfig not found")
        except Exception as e:
            logger.debug(f"Failed to load Windows DNS cache: {e}")

    # --------------------------------------------------
    # DNS cache management
    # --------------------------------------------------

    def _maybe_evict_dns_cache(self, now: float):
        """Periodically evict expired entries and enforce size cap."""
        if now - self._last_eviction_time < DNS_EVICTION_INTERVAL:
            return
        self._evict_expired_dns_entries()
        self._enforce_cache_limit()
        self._last_eviction_time = now

    def _evict_expired_dns_entries(self):
        """Remove DNS cache entries older than TTL."""
        now = time.time()
        expired_ips = [
            ip for ip, ttl in self._dns_cache_ttl.items()
            if now - ttl > self._dns_cache_duration
        ]
        for ip in expired_ips:
            self._dns_cache.pop(ip, None)
            self._dns_cache_ttl.pop(ip, None)
        if expired_ips:
            logger.debug(f"Evicted {len(expired_ips)} expired DNS cache entries")

    def _enforce_cache_limit(self):
        """If cache exceeds max size, evict oldest 25%."""
        if len(self._dns_cache) <= DNS_CACHE_MAX_SIZE:
            return
        evict_count = len(self._dns_cache) // 4
        if evict_count == 0:
            evict_count = 1
        sorted_by_ttl = sorted(self._dns_cache_ttl.items(), key=lambda x: x[1])
        for ip, _ in sorted_by_ttl[:evict_count]:
            self._dns_cache.pop(ip, None)
            self._dns_cache_ttl.pop(ip, None)
        logger.debug(
            f"DNS cache limit enforced: evicted {evict_count} oldest entries "
            f"(remaining={len(self._dns_cache)})"
        )

    # --------------------------------------------------
    # Bandwidth tracking
    # --------------------------------------------------

    def _get_io_counters(self) -> Optional[tuple]:
        """Get current network IO counters."""
        try:
            counters = psutil.net_io_counters()
            return (counters.bytes_sent, counters.bytes_recv)
        except Exception:
            return None

    def _calculate_bandwidth_delta(self) -> tuple[int, int]:
        """Calculate bytes sent/received since last poll."""
        current = self._get_io_counters()
        if current is None or self._last_io_counters is None:
            self._last_io_counters = current
            self._last_io_time = time.time()
            return 0, 0

        bytes_up = max(0, current[0] - self._last_io_counters[0])
        bytes_down = max(0, current[1] - self._last_io_counters[1])

        self._last_io_counters = current
        self._last_io_time = time.time()

        return bytes_up, bytes_down

    def _distribute_bandwidth(self, bytes_up: int, bytes_down: int):
        """
        Distribute total bandwidth delta proportionally across active domains.
        This is an approximation since per-connection byte tracking
        is not available without packet-level inspection.
        """
        if not self._domains:
            return

        # Weight by connection count (more connections = more traffic likely)
        total_connections = sum(
            d.connection_count for d in self._domains.values()
        )
        if total_connections == 0:
            return

        for domain_record in self._domains.values():
            weight = domain_record.connection_count / total_connections
            domain_record.bytes_uploaded += round(bytes_up * weight)
            domain_record.bytes_downloaded += round(bytes_down * weight)

    # --------------------------------------------------
    # Domain normalization and filtering
    # --------------------------------------------------

    def _normalize_domain(self, domain: str) -> str:
        """Clean up a domain name."""
        if not domain:
            return ""

        cleaned = domain.lower().strip().rstrip(".")

        # Remove www. prefix
        if cleaned.startswith("www."):
            cleaned = cleaned[4:]

        return cleaned

    def _is_ignored(self, domain: str) -> bool:
        """Check if a domain should be ignored."""
        if not domain:
            return True

        if self._is_ip_like(domain):
            return True

        # Exact match
        if domain in self._ignored_domains:
            return True

        # Wildcard matching
        for pattern in self._ignored_domains:
            if pattern.startswith("*."):
                suffix = pattern[1:]  # ".local"
                if domain.endswith(suffix):
                    return True

        return False

    @staticmethod
    def _is_ip_like(value: str) -> bool:
        """Check if a string looks like an IP address rather than a domain."""
        # IPv4
        parts = value.split(".")
        if len(parts) == 4:
            try:
                if all(0 <= int(p) <= 255 for p in parts):
                    return True
            except ValueError:
                pass

        # IPv6
        if ":" in value and all(c in "0123456789abcdef:." for c in value.lower()):
            return True

        return False

    # --------------------------------------------------
    # Status
    # --------------------------------------------------

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_thread_alive(self) -> bool:
        """Check if the collector thread is actually alive (not just flagged running)."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def current_domain_count(self) -> int:
        """Number of unique domains tracked in current window."""
        with self._lock:
            return len(self._domains)

    @property
    def dns_cache_size(self) -> int:
        return len(self._dns_cache)

    def get_active_domains(self) -> list[str]:
        """Get list of currently tracked domains (for debugging)."""
        with self._lock:
            return list(self._domains.keys())