"""
nginx config parser — extracts domain→IP mapping across proxy_pass chains.

Handles:
- Direct:     proxy_pass http://10.0.0.1:8080  → IP resolved immediately
- Conditional: multiple proxy_pass in if-blocks  → ALL IPs collected
- Chained:    proxy_pass http://other.domain   → resolve recursively
- Upstream:   proxy_pass http://upstream_name  → all server IPs from upstream block
- Comments:   #proxy_pass ...                  → ignored
- Multiple files: chains can span files
"""

import re
import ipaddress
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass
class ProxyTarget:
    original: str
    scheme: str
    host: str
    port: Optional[int]
    is_ip: bool


@dataclass
class ServerBlock:
    server_names: list
    listen_ports: list
    is_ssl: bool
    proxy_targets: list
    source_file: str
    source_project: str = ''


@dataclass
class ResolvedTarget:
    ip: Optional[str]
    port: Optional[int]
    chain: list              # ordered domain path leading to this IP
    upstream_name: Optional[str]


@dataclass
class DomainResolution:
    domain: str
    aliases: list
    targets: list            # list[ResolvedTarget] — all resolved backends
    source_file: str
    source_project: str


def _strip_comments(text):
    lines = []
    for line in text.splitlines():
        pos = line.find('#')
        if pos >= 0:
            line = line[:pos]
        lines.append(line)
    return '\n'.join(lines)


def _extract_blocks_of_type(config_text, keyword):
    """Extract content of each `keyword { ... }` block via brace counting."""
    blocks = []
    text = _strip_comments(config_text)
    n = len(text)
    pos = 0

    pattern = re.compile(r'\b' + re.escape(keyword) + r'\s*(\S+\s*)?\{')

    while pos < n:
        m = pattern.search(text[pos:])
        if not m:
            break

        name_group = (m.group(1) or '').strip()
        brace_pos = pos + m.end() - 1  # index of '{'
        depth = 1
        j = brace_pos + 1

        while j < n and depth > 0:
            if text[j] == '{':
                depth += 1
            elif text[j] == '}':
                depth -= 1
            j += 1

        if depth == 0:
            blocks.append((name_group, text[brace_pos + 1:j - 1]))

        pos = j

    return blocks


def _parse_proxy_pass_url(url):
    try:
        parsed = urlparse(url)
        host = parsed.hostname or ''
        port = parsed.port

        is_ip = False
        try:
            ipaddress.ip_address(host)
            is_ip = True
        except ValueError:
            pass

        return ProxyTarget(
            original=url,
            scheme=parsed.scheme or 'http',
            host=host,
            port=port,
            is_ip=is_ip,
        )
    except Exception:
        return None


def _parse_upstream_server_addr(addr):
    """Parse '10.0.0.1:8080' → (ip_str, port_int_or_None)."""
    if ':' in addr:
        host, _, port_str = addr.rpartition(':')
        try:
            return host, int(port_str)
        except ValueError:
            return addr, None
    return addr, None


def _extract_upstream_map(config_text):
    """Return {upstream_name: [(ip, port), ...]} for all upstream blocks in file."""
    result = {}
    for name, body in _extract_blocks_of_type(config_text, 'upstream'):
        if not name:
            continue
        server_addrs = re.findall(r'\bserver\s+(\S+?)(?:\s+\w[\w=]*)*\s*;', body)
        servers = []
        for addr in server_addrs:
            ip, port = _parse_upstream_server_addr(addr)
            try:
                ipaddress.ip_address(ip)
                servers.append((ip, port))
            except ValueError:
                pass  # non-IP upstream server (e.g. unix socket)
        result[name] = servers
    return result


def _parse_server_block(text, source_file, source_project):
    sn_match = re.search(r'\bserver_name\s+(.+?);', text, re.DOTALL)
    if not sn_match:
        return None
    raw = re.sub(r'\s+', ' ', sn_match.group(1)).strip()
    server_names = [n for n in raw.split() if n not in ('_', '""', "''")]
    if not server_names:
        return None

    is_ssl = bool(re.search(r'\blisten\s+[^;]*(?:443|ssl)', text))
    listen_ports = re.findall(r'\blisten\s+(?:\S+:)?(\d+)', text)

    proxy_targets = []
    for m in re.finditer(r'\bproxy_pass\s+(https?://[^\s;$]+);', text):
        target = _parse_proxy_pass_url(m.group(1))
        if target and target.host:
            proxy_targets.append(target)

    return ServerBlock(
        server_names=server_names,
        listen_ports=listen_ports,
        is_ssl=is_ssl,
        proxy_targets=proxy_targets,
        source_file=source_file,
        source_project=source_project,
    )


def _resolve_all(domain, domain_map, upstream_map, path=None, visited=None):
    """
    Recursively resolve ALL proxy_pass targets for a domain.

    Unlike a single-result resolver, collects every IP found across
    conditional branches (if-blocks), upstream groups, and proxy chains.

    Returns list[ResolvedTarget]. Empty list if domain not in domain_map.
    """
    if visited is None:
        visited = set()
    if path is None:
        path = []

    if domain in visited:
        return []  # cycle — skip

    visited = visited | {domain}
    current_path = path + [domain]

    if domain not in domain_map:
        return []

    results = []
    for target in domain_map[domain].proxy_targets:
        if target.is_ip:
            results.append(ResolvedTarget(
                ip=target.host,
                port=target.port,
                chain=current_path,
                upstream_name=None,
            ))
        elif target.host in upstream_map:
            servers = upstream_map[target.host]
            if servers:
                for ip, port in servers:
                    results.append(ResolvedTarget(
                        ip=ip,
                        port=port,
                        chain=current_path,
                        upstream_name=target.host,
                    ))
            else:
                results.append(ResolvedTarget(
                    ip=None,
                    port=None,
                    chain=current_path,
                    upstream_name=target.host,
                ))
        else:
            sub = _resolve_all(target.host, domain_map, upstream_map, current_path, visited)
            results.extend(sub)

    if not results:
        results.append(ResolvedTarget(ip=None, port=None, chain=current_path, upstream_name=None))

    return results


def parse_configs(configs):
    """
    Parse nginx configs and resolve all domains to ALL their backend IPs.

    Args:
        configs: list of (config_text: str, source_file: str, source_project: str)

    Returns:
        list of DomainResolution — one entry per unique primary domain.
        SSL (443) blocks take priority over HTTP-only blocks for same domain.
        Each DomainResolution.targets contains ALL resolved backends.
    """
    all_blocks = []
    upstream_map = {}

    for content, source_file, source_project in configs:
        upstream_map.update(_extract_upstream_map(content))

        for _, block_text in _extract_blocks_of_type(content, 'server'):
            block = _parse_server_block(block_text, source_file, source_project)
            if block:
                all_blocks.append(block)

    # Build domain → block map; SSL blocks override non-SSL for same domain
    domain_map = {}
    for block in all_blocks:
        for name in block.server_names:
            if name not in domain_map or block.is_ssl:
                domain_map[name] = block

    results = []
    seen = set()

    for block in all_blocks:
        primary = block.server_names[0]
        if primary in seen:
            continue
        seen.add(primary)

        targets = _resolve_all(primary, domain_map, upstream_map)
        if not targets:
            targets = [ResolvedTarget(ip=None, port=None, chain=[primary], upstream_name=None)]

        results.append(DomainResolution(
            domain=primary,
            aliases=block.server_names[1:],
            targets=targets,
            source_file=block.source_file,
            source_project=block.source_project,
        ))

    return results
