"""
nginx config parser — extracts domain→IP mapping across proxy_pass chains.

Handles:
- Direct:      proxy_pass http://10.0.0.1:8080  → IP resolved immediately
- Conditional: multiple proxy_pass in if-blocks  → ALL IPs collected
- Chained:     proxy_pass http://other.domain   → resolve recursively via domain_map
- Upstream:    proxy_pass http://upstream_name  → all server IPs from upstream block
- Loop:        proxy_pass http://same.domain    → detected, marked is_loop=True
- Comments:    #proxy_pass ...                  → ignored
- Multi-file:  each server block resolved independently; same domain in N files → N entries
"""

import re
import ipaddress
from dataclasses import dataclass, field
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
    chain: list              # ordered domain path leading to this result
    upstream_name: Optional[str]
    is_loop: bool = False    # proxy_pass points back to an already-visited domain


@dataclass
class DomainResolution:
    domain: str
    aliases: list
    targets: list            # list[ResolvedTarget] — one entry per server block
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
        brace_pos = pos + m.end() - 1
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
                pass
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


def _resolve_targets(proxy_targets, domain_map, upstream_map, current_path, visited):
    """
    Resolve a list of ProxyTargets to ResolvedTarget objects.

    current_path: ordered list of domains already in the resolution chain.
    visited:      set of domains already visited (cycle detection).
    """
    results = []

    for target in proxy_targets:
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

        elif target.host in visited:
            # proxy_pass loops back to a domain already in the chain
            results.append(ResolvedTarget(
                ip=None,
                port=target.port,
                chain=current_path + [target.host],
                upstream_name=None,
                is_loop=True,
            ))

        else:
            # Follow chain to another domain
            sub = _resolve_domain(target.host, domain_map, upstream_map, current_path, visited)
            results.extend(sub)

    if not results:
        results.append(ResolvedTarget(
            ip=None, port=None, chain=current_path, upstream_name=None,
        ))

    return results


def _resolve_domain(domain, domain_map, upstream_map, path, visited):
    """Follow proxy chain for a domain via domain_map (used for chained resolutions)."""
    if domain in visited or domain not in domain_map:
        return []

    new_visited = visited | {domain}
    new_path = path + [domain]
    return _resolve_targets(
        domain_map[domain].proxy_targets, domain_map, upstream_map, new_path, new_visited,
    )


def parse_configs(configs):
    """
    Parse nginx configs and resolve each server block independently.

    Each server block becomes its own DomainResolution — if the same domain
    appears in N files, there will be N entries (shown as N rows in the file
    view and N occurrences in the domain table).

    For chained resolutions (proxy_pass → another domain), the global
    domain_map (SSL-priority) is used to follow the chain.

    Args:
        configs: list of (config_text: str, source_file: str, source_project: str)

    Returns:
        list of DomainResolution — one per server block found.
    """
    all_blocks = []
    upstream_map = {}

    for content, source_file, source_project in configs:
        upstream_map.update(_extract_upstream_map(content))

        for _, block_text in _extract_blocks_of_type(content, 'server'):
            block = _parse_server_block(block_text, source_file, source_project)
            if block:
                all_blocks.append(block)

    # domain_map used only for following proxy chains to OTHER domains
    # SSL blocks take priority so chains resolve to the "real" backend
    domain_map = {}
    for block in all_blocks:
        for name in block.server_names:
            if name not in domain_map or block.is_ssl:
                domain_map[name] = block

    results = []

    for block in all_blocks:
        primary = block.server_names[0]
        # Resolve from THIS block's own proxy_targets, not domain_map
        targets = _resolve_targets(
            block.proxy_targets,
            domain_map,
            upstream_map,
            current_path=[primary],
            visited={primary},
        )

        results.append(DomainResolution(
            domain=primary,
            aliases=block.server_names[1:],
            targets=targets,
            source_file=block.source_file,
            source_project=block.source_project,
        ))

    return results
