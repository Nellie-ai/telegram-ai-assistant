import socket

import pytest


def test_external_dns_is_rejected_before_resolution() -> None:
    with pytest.raises(AssertionError, match="External DNS"):
        socket.getaddrinfo("example.invalid", 443)


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
def test_direct_external_ip_is_rejected(method: str) -> None:
    with socket.socket() as sock:
        with pytest.raises(AssertionError, match="External network"):
            getattr(sock, method)(("192.0.2.1", 443))


def test_unconnected_udp_is_rejected() -> None:
    with socket.socket(type=socket.SOCK_DGRAM) as sock:
        with pytest.raises(AssertionError, match="External network"):
            sock.sendto(b"synthetic", ("192.0.2.1", 53))
