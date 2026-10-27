"""
System, Network, Linux File/Permission, and Defensive Security Utilities
for SoulShell Terminal (Section 7).
Uses standard Python libraries (`/proc`, `os`, `shutil`, `socket`, `urllib.parse`, `stat`)
and safe, read-only Linux commands with timeouts and input validation.
Never exposes environment secrets (API keys, passwords, tokens).
"""

from __future__ import annotations

import ipaddress
import os
import platform
import re
import shutil
import socket
import stat
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

SECRET_ENV_KEY_PATTERNS = re.compile(
    r"(PASS|PASSWORD|SECRET|TOKEN|KEY|CREDENTIAL|AUTH|PRIVATE|COOKIE|BEARER)",
    re.IGNORECASE,
)

# Defensive / Kali Linux & standard security/networking tools catalog
SECURITY_TOOLS_CATALOG: List[Tuple[str, str, str]] = [
    ("nmap", "Network discovery & port auditing", "Network Security"),
    ("ss", "Socket statistics & listening port inspection", "Network Diagnostics"),
    ("ip", "IP routing & network interface configuration", "Network Diagnostics"),
    ("ufw", "Uncomplicated Firewall management", "Host Firewall"),
    ("iptables", "IPv4 packet filter administration", "Host Firewall"),
    ("nft", "nftables packet filtering framework", "Host Firewall"),
    ("tcpdump", "Command-line packet analyzer", "Traffic Analysis"),
    ("wireshark", "Network protocol analyzer", "Traffic Analysis"),
    ("tshark", "Terminal-oriented Wireshark analyzer", "Traffic Analysis"),
    ("fail2ban-client", "Intrusion prevention log ban manager", "Defensive Hardening"),
    ("lynis", "Security auditing & hardening scanner", "System Auditing"),
    ("rkhunter", "Rootkit Hunter security scanner", "System Auditing"),
    ("chkrootkit", "Local rootkit check utility", "System Auditing"),
    ("clamscan", "ClamAV antivirus command-line scanner", "Malware Defense"),
    ("auditctl", "Linux Audit daemon control utility", "Kernel Auditing"),
    ("journalctl", "Systemd journal log viewer", "Log Analysis"),
    ("openssl", "Cryptography and TLS certificate toolkit", "Cryptography"),
    ("gpg", "GNU Privacy Guard encryption & signing", "Cryptography"),
    ("ssh", "OpenSSH remote login client", "Secure Access"),
    ("curl", "URL data transfer diagnostic tool", "Web Diagnostics"),
    ("dig", "DNS lookup utility", "DNS Diagnostics"),
]


@dataclass
class PermissionBreakdown:
    """Detailed explanation of a file path's or octal mode's Unix permissions."""

    target: str
    file_type: str
    octal_mode: str
    symbolic_mode: str
    owner_uid: Optional[int]
    group_gid: Optional[int]
    owner_perms: List[str]
    group_perms: List[str]
    other_perms: List[str]
    special_bits: List[str] = field(default_factory=list)
    security_notes: List[str] = field(default_factory=list)


@dataclass
class URLCheckReport:
    """Defensive heuristic inspection report for a URL (Section 7 `checkurl <url>`)."""

    url: str
    scheme: str
    hostname: str
    risk_indicator: str  # 'low', 'medium', 'elevated'
    findings: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Heuristic URL inspection checks only for structural suspicious patterns "
        "(such as cleartext HTTP, embedded credentials, raw IP hosts, punycode, or deceptive characters). "
        "It cannot prove whether a destination site is safe or malicious."
    )


class SystemInfoService:
    """Provides safe, read-only system, network, file, and security inspections."""

    DIGIT_MAP = {
        0: [],
        1: ["execute"],
        2: ["write"],
        3: ["write", "execute"],
        4: ["read"],
        5: ["read", "execute"],
        6: ["read", "write"],
        7: ["read", "write", "execute"],
    }
    SYMBOLIC_MAP = {
        0: "---",
        1: "--x",
        2: "-w-",
        3: "-wx",
        4: "r--",
        5: "r-x",
        6: "rw-",
        7: "rwx",
    }

    # -------------------------------------------------------------------------
    # System Information (`sysinfo`, `cpu`, `memory`, `disk`, `uptime`, `processes`, `environment`)
    # -------------------------------------------------------------------------

    @staticmethod
    def get_sysinfo() -> Dict[str, str]:
        """Collect general OS, kernel, architecture, hostname, and Python details."""
        distro_name = platform.system()
        os_release = Path("/etc/os-release")
        if os_release.exists():
            try:
                for line in os_release.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if line.startswith("PRETTY_NAME="):
                        distro_name = line.split("=", 1)[1].strip().strip('"')
                        break
            except OSError:
                pass
        return {
            "Distribution": distro_name,
            "Kernel": f"{platform.system()} {platform.release()}",
            "Architecture": platform.machine(),
            "Hostname": socket.gethostname(),
            "Python Version": sys.version.split()[0],
            "Working Directory": str(Path.cwd()),
        }

    @staticmethod
    def get_cpu_info() -> Dict[str, str]:
        """Gather CPU model, core count, and load averages."""
        cores = os.cpu_count() or 1
        model_name = platform.processor() or "Generic Processor"
        cpuinfo = Path("/proc/cpuinfo")
        if cpuinfo.exists():
            try:
                for line in cpuinfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if "model name" in line.lower() and ":" in line:
                        model_name = line.split(":", 1)[1].strip()
                        break
            except OSError:
                pass
        try:
            load1, load5, load15 = os.getloadavg()
            load_str = f"{load1:.2f} (1m), {load5:.2f} (5m), {load15:.2f} (15m)"
        except OSError:
            load_str = "N/A"
        return {
            "Model": model_name,
            "Logical Cores": str(cores),
            "Load Average": load_str,
        }

    @staticmethod
    def get_memory_info() -> Dict[str, str]:
        """Read system RAM and Swap statistics from /proc/meminfo."""
        meminfo = Path("/proc/meminfo")
        data: Dict[str, int] = {}
        if meminfo.exists():
            try:
                for line in meminfo.read_text(encoding="utf-8", errors="ignore").splitlines():
                    if ":" in line:
                        k, v = line.split(":", 1)
                        parts = v.strip().split()
                        if parts and parts[0].isdigit():
                            data[k.strip()] = int(parts[0]) * 1024
            except OSError:
                pass

        def _fmt_gb(val: int) -> str:
            return f"{val / (1024**3):.2f} GB" if val > 0 else "0.00 GB"

        total = data.get("MemTotal", 0)
        avail = data.get("MemAvailable", data.get("MemFree", 0))
        used = max(0, total - avail)
        pct = f"{(used / total * 100):.1f}%" if total > 0 else "N/A"
        swap_total = data.get("SwapTotal", 0)
        swap_free = data.get("SwapFree", 0)
        return {
            "Total RAM": _fmt_gb(total),
            "Used RAM": f"{_fmt_gb(used)} ({pct})",
            "Available RAM": _fmt_gb(avail),
            "Swap Total": _fmt_gb(swap_total),
            "Swap Free": _fmt_gb(swap_free),
        }

    @staticmethod
    def get_disk_info(target_path: str = "/") -> Dict[str, str]:
        """Return disk space usage for target_path using shutil.disk_usage."""
        usage = shutil.disk_usage(target_path)
        pct = (usage.used / usage.total * 100.0) if usage.total else 0.0
        return {
            "Mount / Path": str(target_path),
            "Total Capacity": f"{usage.total / (1024**3):.2f} GB",
            "Used Space": f"{usage.used / (1024**3):.2f} GB ({pct:.1f}%)",
            "Free Space": f"{usage.free / (1024**3):.2f} GB",
        }

    @staticmethod
    def get_uptime_info() -> str:
        """Read system uptime from /proc/uptime."""
        uptime_path = Path("/proc/uptime")
        if uptime_path.exists():
            try:
                raw = uptime_path.read_text(encoding="utf-8").split()[0]
                seconds = int(float(raw))
                days, rem = divmod(seconds, 86400)
                hours, rem = divmod(rem, 3600)
                minutes, secs = divmod(rem, 60)
                return f"{days}d {hours}h {minutes}m {secs}s (Total: {seconds:,} seconds)"
            except (OSError, ValueError):
                pass
        return "Uptime unavailable on this platform"

    @staticmethod
    def get_processes(limit: int = 15) -> List[Dict[str, str]]:
        """List running processes safely using `ps` or `/proc` fallback."""
        ps_bin = shutil.which("ps")
        if ps_bin:
            try:
                res = subprocess.run(
                    [ps_bin, "-eo", "pid,user,%cpu,%mem,comm", "--sort=-%mem"],
                    capture_output=True,
                    text=True,
                    timeout=4.0,
                    check=False,
                )
                lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
                out: List[Dict[str, str]] = []
                for ln in lines[1 : limit + 1]:
                    parts = ln.split(None, 4)
                    if len(parts) == 5:
                        out.append(
                            {
                                "PID": parts[0],
                                "USER": parts[1],
                                "CPU%": parts[2],
                                "MEM%": parts[3],
                                "COMMAND": parts[4],
                            }
                        )
                if out:
                    return out
            except Exception:
                pass

        # Fallback: scan numeric directories in /proc
        proc_list: List[Dict[str, str]] = []
        proc_dir = Path("/proc")
        if proc_dir.exists():
            for entry in sorted(proc_dir.iterdir()):
                if entry.name.isdigit():
                    comm_file = entry / "comm"
                    try:
                        cmd_name = comm_file.read_text(encoding="utf-8").strip()
                    except OSError:
                        cmd_name = "unknown"
                    proc_list.append(
                        {
                            "PID": entry.name,
                            "USER": "local",
                            "CPU%": "-",
                            "MEM%": "-",
                            "COMMAND": cmd_name,
                        }
                    )
                    if len(proc_list) >= limit:
                        break
        return proc_list

    @staticmethod
    def get_sanitized_environment() -> Dict[str, str]:
        """
        Return environment variables with all sensitive keys (passwords, tokens, API keys, secrets)
        automatically redacted.
        """
        sanitized: Dict[str, str] = {}
        for k in sorted(os.environ.keys()):
            val = os.environ.get(k, "")
            if SECRET_ENV_KEY_PATTERNS.search(k):
                sanitized[k] = "[REDACTED_SECRET]"
            else:
                sanitized[k] = val[:120] + ("..." if len(val) > 120 else "")
        return sanitized

    # -------------------------------------------------------------------------
    # Linux Assistance Helpers (`permissions <path>`, `findfile <filename>`)
    # -------------------------------------------------------------------------

    @classmethod
    def inspect_permissions(cls, path_or_octal: str) -> PermissionBreakdown:
        """Inspect a filesystem path (read-only os.lstat) or explain a 3/4-digit octal mode."""
        raw = (path_or_octal or "").strip()
        if not raw:
            raise ValueError("Please provide a path (e.g., `permissions ~/Documents`) or octal mode (`755`).")

        target_path = Path(raw).expanduser()
        if target_path.exists() or target_path.is_symlink():
            st = os.lstat(target_path)
            mode = st.st_mode
            perms = stat.S_IMODE(mode)
            special = (perms >> 9) & 0b111
            u_d = (perms >> 6) & 0b111
            g_d = (perms >> 3) & 0b111
            o_d = perms & 0b111
            if stat.S_ISDIR(mode):
                ftype = "Directory"
            elif stat.S_ISLNK(mode):
                ftype = "Symbolic Link"
            elif stat.S_ISREG(mode):
                ftype = "Regular File"
            else:
                ftype = "Special File"
            return cls._build_perm_breakdown(
                target=str(target_path),
                file_type=ftype,
                special=special,
                u_d=u_d,
                g_d=g_d,
                o_d=o_d,
                uid=st.st_uid,
                gid=st.st_gid,
            )

        # Otherwise check if it's an octal mode like 755 or 0644
        clean_oct = raw[2:] if raw.lower().startswith("0o") else raw
        if clean_oct.isdigit() and len(clean_oct) in (3, 4) and all(c in "01234567" for c in clean_oct):
            if len(clean_oct) == 3:
                special = 0
                u_d, g_d, o_d = (int(c) for c in clean_oct)
            else:
                special = int(clean_oct[0])
                u_d, g_d, o_d = (int(c) for c in clean_oct[1:])
            return cls._build_perm_breakdown(
                target=f"Octal Mode {raw}",
                file_type="Permission Mode",
                special=special,
                u_d=u_d,
                g_d=g_d,
                o_d=o_d,
                uid=None,
                gid=None,
            )

        raise FileNotFoundError(f"Path not found (and not a valid octal mode): {raw}")

    @classmethod
    def _build_perm_breakdown(
        cls,
        target: str,
        file_type: str,
        special: int,
        u_d: int,
        g_d: int,
        o_d: int,
        uid: Optional[int],
        gid: Optional[int],
    ) -> PermissionBreakdown:
        octal_str = f"{special}{u_d}{g_d}{o_d}" if special > 0 else f"{u_d}{g_d}{o_d}"
        u_sym = list(cls.SYMBOLIC_MAP[u_d])
        g_sym = list(cls.SYMBOLIC_MAP[g_d])
        o_sym = list(cls.SYMBOLIC_MAP[o_d])

        special_bits: List[str] = []
        notes: List[str] = []
        if special & 4:
            special_bits.append("SUID (4000)")
            u_sym[2] = "s" if (u_d & 1) else "S"
            notes.append("SUID active: executes with file owner privileges.")
        if special & 2:
            special_bits.append("SGID (2000)")
            g_sym[2] = "s" if (g_d & 1) else "S"
            notes.append("SGID active: executes with group privileges or inherits directory group.")
        if special & 1:
            special_bits.append("Sticky Bit (1000)")
            o_sym[2] = "t" if (o_d & 1) else "T"
            notes.append("Sticky bit active: restricts file deletion inside shared directories.")

        if o_d & 2:
            notes.append("WARNING: World-writable ('Others' has write permission). Consider restricting with `chmod o-w`.")
        elif octal_str in ("755", "644"):
            notes.append(f"Standard Linux permission mode ({octal_str}).")
        elif octal_str in ("600", "700"):
            notes.append(f"Private owner-only mode ({octal_str}) — well-suited for credentials or SSH keys.")

        return PermissionBreakdown(
            target=target,
            file_type=file_type,
            octal_mode=octal_str,
            symbolic_mode="".join(u_sym + g_sym + o_sym),
            owner_uid=uid,
            group_gid=gid,
            owner_perms=list(cls.DIGIT_MAP[u_d]),
            group_perms=list(cls.DIGIT_MAP[g_d]),
            other_perms=list(cls.DIGIT_MAP[o_d]),
            special_bits=special_bits,
            security_notes=notes,
        )

    @staticmethod
    def find_files(
        pattern: str,
        search_root: Optional[Path] = None,
        max_results: int = 50,
    ) -> List[Path]:
        """Safely search for files matching pattern (case-insensitive substring or glob) under search_root."""
        clean = (pattern or "").strip()
        if not clean:
            raise ValueError("Please specify a filename or pattern to search for.")

        root = (search_root or Path.cwd()).expanduser().resolve()
        matches: List[Path] = []
        needle = clean.lower()

        for current_root, dirs, files in os.walk(root):
            # Skip noisy virtual/hidden system directories when searching broad trees
            dirs[:] = [
                d
                for d in dirs
                if d not in (".git", "__pycache__", "node_modules", ".venv", "proc", "sys")
            ]
            for fname in files:
                if needle in fname.lower() or Path(fname).match(clean):
                    matches.append(Path(current_root) / fname)
                    if len(matches) >= max_results:
                        return matches
        return matches

    # -------------------------------------------------------------------------
    # Network Utilities (`netinfo`, `interfaces`, `connections`, `dns`, `ping`)
    # -------------------------------------------------------------------------

    @classmethod
    def get_netinfo(cls) -> Dict[str, str]:
        hostname = socket.gethostname()
        try:
            fqdn = socket.getfqdn()
        except Exception:
            fqdn = hostname
        ifaces = cls.get_interfaces()
        iface_names = ", ".join(i["Interface"] for i in ifaces) if ifaces else "lo"
        return {
            "Hostname": hostname,
            "FQDN": fqdn,
            "Detected Interfaces": iface_names,
        }

    @staticmethod
    def get_interfaces() -> List[Dict[str, str]]:
        """List network interfaces and basic operational status via `/sys/class/net` or `ip`."""
        ip_bin = shutil.which("ip")
        if ip_bin:
            try:
                res = subprocess.run(
                    [ip_bin, "-brief", "address", "show"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    check=False,
                )
                out: List[Dict[str, str]] = []
                for line in res.stdout.splitlines():
                    parts = line.split()
                    if len(parts) >= 2:
                        out.append(
                            {
                                "Interface": parts[0],
                                "State": parts[1],
                                "Addresses": " ".join(parts[2:]) or "None",
                            }
                        )
                if out:
                    return out
            except Exception:
                pass

        sys_net = Path("/sys/class/net")
        fallback: List[Dict[str, str]] = []
        if sys_net.exists():
            for iface in sorted(sys_net.iterdir()):
                state_file = iface / "operstate"
                try:
                    state = state_file.read_text(encoding="utf-8").strip().upper()
                except OSError:
                    state = "UNKNOWN"
                fallback.append(
                    {
                        "Interface": iface.name,
                        "State": state,
                        "Addresses": "127.0.0.1" if iface.name == "lo" else "Local interface",
                    }
                )
        return fallback

    @staticmethod
    def get_connections(limit: int = 25) -> List[Dict[str, str]]:
        """List active/listening TCP/UDP sockets via `ss -tuln` or `/proc/net/tcp` fallback."""
        ss_bin = shutil.which("ss")
        if ss_bin:
            try:
                res = subprocess.run(
                    [ss_bin, "-tuln"],
                    capture_output=True,
                    text=True,
                    timeout=3.0,
                    check=False,
                )
                lines = [ln.strip() for ln in res.stdout.splitlines() if ln.strip()]
                rows: List[Dict[str, str]] = []
                for ln in lines[1 : limit + 1]:
                    parts = ln.split()
                    if len(parts) >= 5:
                        rows.append(
                            {
                                "Netid": parts[0],
                                "State": parts[1],
                                "Local Address:Port": parts[4],
                                "Peer Address:Port": parts[5] if len(parts) > 5 else "*",
                            }
                        )
                if rows:
                    return rows
            except Exception:
                pass

        # Fallback: parse /proc/net/tcp for listening sockets
        proc_tcp = Path("/proc/net/tcp")
        fallback_rows: List[Dict[str, str]] = []
        if proc_tcp.exists():
            try:
                for ln in proc_tcp.read_text(encoding="utf-8").splitlines()[1 : limit + 1]:
                    parts = ln.split()
                    if len(parts) >= 4:
                        local_hex = parts[1]
                        state_hex = parts[3]
                        if ":" in local_hex:
                            ip_h, port_h = local_hex.split(":", 1)
                            port = int(port_h, 16)
                            ip_int = int(ip_h, 16)
                            ip_str = socket.inet_ntoa(ip_int.to_bytes(4, "little"))
                            state_label = "LISTEN" if state_hex == "0A" else f"0x{state_hex}"
                            fallback_rows.append(
                                {
                                    "Netid": "tcp",
                                    "State": state_label,
                                    "Local Address:Port": f"{ip_str}:{port}",
                                    "Peer Address:Port": "*:*",
                                }
                            )
            except Exception:
                pass
        return fallback_rows

    @staticmethod
    def resolve_dns(domain: str) -> List[str]:
        """Validate domain/hostname and resolve A/AAAA records using socket.getaddrinfo."""
        clean = (domain or "").strip()
        if not clean or not re.match(r"^[a-zA-Z0-9._-]+$", clean):
            raise ValueError(
                f"Invalid domain or hostname '{domain}'. Use letters, digits, dots, or hyphens."
            )
        results: List[str] = []
        infos = socket.getaddrinfo(clean, None)
        for family, _, _, _, sockaddr in infos:
            addr = str(sockaddr[0])
            fam_label = "IPv6" if family == socket.AF_INET6 else "IPv4"
            entry = f"{fam_label}: {addr}"
            if entry not in results:
                results.append(entry)
        return results

    @staticmethod
    def ping_host(host: str, count: int = 2, timeout_sec: int = 3) -> Dict[str, Any]:
        """
        Validate host input and perform a bounded connectivity check using `ping`
        (or a TCP socket probe fallback if `ping` binary or ICMP capability is absent).
        """
        clean = (host or "").strip()
        if not clean or not re.match(r"^[a-zA-Z0-9._:-]+$", clean):
            raise ValueError(
                f"Invalid host '{host}'. Only valid hostnames or IPv4/IPv6 addresses are allowed."
            )

        ping_bin = shutil.which("ping")
        if ping_bin:
            try:
                res = subprocess.run(
                    [ping_bin, "-c", str(max(1, min(4, count))), "-W", str(timeout_sec), clean],
                    capture_output=True,
                    text=True,
                    timeout=float(timeout_sec * count + 3),
                    check=False,
                )
                return {
                    "host": clean,
                    "method": "ICMP ping",
                    "reachable": res.returncode == 0,
                    "output": (res.stdout or res.stderr).strip(),
                }
            except Exception as exc:
                return {
                    "host": clean,
                    "method": "ICMP ping",
                    "reachable": False,
                    "output": f"Ping failed: {exc}",
                }

        # Fallback when ICMP `ping` binary is not installed in minimal container
        start = time.monotonic()
        try:
            infos = socket.getaddrinfo(clean, 80, proto=socket.IPPROTO_TCP)
            elapsed_ms = (time.monotonic() - start) * 1000.0
            resolved_ip = infos[0][4][0] if infos else clean
            return {
                "host": clean,
                "method": "Socket resolution check (`ping` binary not installed)",
                "reachable": True,
                "output": f"Resolved {clean} -> {resolved_ip} in {elapsed_ms:.1f} ms (Install `iputils-ping` for ICMP echo).",
            }
        except Exception as exc:
            return {
                "host": clean,
                "method": "Socket resolution check (`ping` binary not installed)",
                "reachable": False,
                "output": f"Host unreachable / unresolvable ({exc}).",
            }

    # -------------------------------------------------------------------------
    # Defensive Security Utilities (`tools`, `checkurl`, authorized `scan`)
    # -------------------------------------------------------------------------

    @staticmethod
    def detect_security_tools() -> List[Dict[str, str]]:
        """Detect which security and networking tools are installed on the system."""
        rows: List[Dict[str, str]] = []
        for binary, purpose, category in SECURITY_TOOLS_CATALOG:
            path = shutil.which(binary)
            rows.append(
                {
                    "Tool": binary,
                    "Category": category,
                    "Status": "Installed" if path else "Not Found",
                    "Path": path or "-",
                    "Purpose": purpose,
                }
            )
        return rows

    @staticmethod
    def check_url_heuristics(url: str) -> URLCheckReport:
        """
        Inspect a URL for suspicious structural patterns without claiming to prove
        whether a site is safe or malicious.
        """
        raw = (url or "").strip()
        if not raw:
            raise ValueError("Please provide a URL to inspect (e.g., `checkurl https://example.com`).")

        parsed = urlparse(raw if "://" in raw else f"http://{raw}")
        scheme = (parsed.scheme or "").lower()
        hostname = (parsed.hostname or "").lower()
        findings: List[str] = []
        risk = "low"

        if scheme not in ("http", "https"):
            findings.append(f"Non-standard URL scheme '{scheme}://'.")
            risk = "elevated"
        elif scheme == "http":
            findings.append("Uses unencrypted HTTP (`http://`) instead of HTTPS (`https://`).")
            risk = "medium"

        if parsed.username or parsed.password or "@" in parsed.netloc:
            findings.append(
                "Contains `@` userinfo segment in authority (`user@host`), a common phishing technique used to disguise the true destination domain."
            )
            risk = "elevated"

        if hostname:
            try:
                ipaddress.ip_address(hostname)
                findings.append(
                    f"Hostname is a raw IP address (`{hostname}`) rather than a domain name."
                )
                if risk == "low":
                    risk = "medium"
            except ValueError:
                pass

            if "xn--" in hostname:
                findings.append(
                    "Hostname contains Punycode (`xn--`), which can be used in IDN homograph lookalike domains."
                )
                risk = "elevated"

            if hostname.count(".") >= 4 or len(hostname) > 55:
                findings.append(
                    f"Unusually long or deeply nested subdomain structure ({len(hostname)} chars)."
                )
                if risk == "low":
                    risk = "medium"

        suspicious_ext = (".exe", ".scr", ".bat", ".ps1", ".apk", ".msi")
        if any(parsed.path.lower().endswith(ext) for ext in suspicious_ext):
            findings.append(
                f"URL path points directly to an executable file (`{parsed.path}`)."
            )
            risk = "elevated"

        if not findings:
            findings.append(
                "No obvious structural red flags detected in URL syntax."
            )

        return URLCheckReport(
            url=raw,
            scheme=scheme,
            hostname=hostname or "(none)",
            risk_indicator=risk,
            findings=findings,
        )

    @staticmethod
    def is_authorized_scan_target(target: str) -> bool:
        """
        Verify whether a scan target is restricted to loopback/private/lab addresses
        (`localhost`, `127.0.0.1`, `::1`, RFC1918 private IPs, or `scanme.nmap.org`).
        """
        clean = (target or "").strip().lower()
        if clean in ("localhost", "scanme.nmap.org"):
            return True
        try:
            ip = ipaddress.ip_address(clean)
            return ip.is_loopback or ip.is_private
        except ValueError:
            return False
