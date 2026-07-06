from ipaddress import ip_address, ip_network

from fastapi import HTTPException, Request, WebSocket, status

from app.core.config import settings


ACCESS_DENIED_MESSAGE = "Dostęp działa tylko po połączeniu z WiFi Quera."


def _normalize_ip_value(value: str) -> str | None:
    candidate = value.strip().strip('"').strip("'")

    if not candidate or candidate.lower() in {"unknown", "null", "none"}:
        return None

    if candidate.startswith("[") and "]" in candidate:
        return candidate[1:candidate.index("]")]

    if candidate.count(":") == 1 and "." in candidate:
        host, port = candidate.rsplit(":", 1)

        if port.isdigit():
            return host

    return candidate


def _forwarded_for_values(value: str) -> list[str]:
    result = []

    for part in value.split(","):
        for segment in part.split(";"):
            key, separator, raw_value = segment.strip().partition("=")

            if separator and key.lower() == "for":
                result.append(raw_value)

    return result


def _candidate_ip_values(connection: Request | WebSocket) -> list[str]:
    headers = connection.headers
    values = []

    for header_name in (
        "cf-connecting-ip",
        "true-client-ip",
        "x-real-ip",
        "x-client-ip",
    ):
        header_value = headers.get(header_name)

        if header_value:
            values.append(header_value)

    forwarded_for = headers.get("x-forwarded-for")

    if forwarded_for:
        values.extend(forwarded_for.split(","))

    forwarded = headers.get("forwarded")

    if forwarded:
        values.extend(_forwarded_for_values(forwarded))

    if connection.client and connection.client.host:
        values.append(connection.client.host)

    return values


def get_client_ip(connection: Request | WebSocket) -> str | None:
    for value in _candidate_ip_values(connection):
        normalized = _normalize_ip_value(value)

        if not normalized:
            continue

        try:
            return str(ip_address(normalized))
        except ValueError:
            continue

    return None


def _allowed_networks():
    raw_cidrs = getattr(settings, "ALLOWED_WIFI_CIDRS", "") or ""
    networks = []

    for raw_cidr in raw_cidrs.split(","):
        cidr = raw_cidr.strip()

        if not cidr:
            continue

        try:
            networks.append(ip_network(cidr, strict=False))
        except ValueError:
            print(f"IP_ACCESS_INVALID_CIDR={cidr}")

    return networks


def allowed_cidrs() -> list[str]:
    return [str(network) for network in _allowed_networks()]


def is_ip_allowed(client_ip: str | None) -> bool:
    if not client_ip:
        return False

    try:
        parsed_ip = ip_address(client_ip)
    except ValueError:
        return False

    if getattr(settings, "IP_ACCESS_ALLOW_PRIVATE", False):
        if parsed_ip.is_private or parsed_ip.is_loopback:
            return True

    return any(parsed_ip in network for network in _allowed_networks())


def is_connection_allowed(connection: Request | WebSocket) -> bool:
    if not getattr(settings, "IP_ACCESS_CONTROL_ENABLED", False):
        return True

    return is_ip_allowed(get_client_ip(connection))


def require_allowed_network(request: Request) -> None:
    if is_connection_allowed(request):
        return

    client_ip = get_client_ip(request)

    print(
        "IP_ACCESS_DENIED:",
        {
            "client_ip": client_ip,
            "allowed_cidrs": allowed_cidrs(),
            "path": str(request.url.path),
        },
    )

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=ACCESS_DENIED_MESSAGE,
    )


def build_access_status(request: Request) -> dict:
    client_ip = get_client_ip(request)
    enabled = bool(getattr(settings, "IP_ACCESS_CONTROL_ENABLED", False))

    return {
        "enabled": enabled,
        "allowed": True if not enabled else is_ip_allowed(client_ip),
        "client_ip": client_ip,
        "allowed_cidrs": allowed_cidrs(),
    }