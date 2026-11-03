"""Prevent accidental external I/O in the isolated test suite."""
import ipaddress
import socket

import pytest


def _is_loopback(host: object) -> bool:
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(str(host)).is_loopback
    except ValueError:
        return False


@pytest.fixture(autouse=True)
def no_external_network(monkeypatch: pytest.MonkeyPatch) -> None:
    # Windows event loops need local socket pairs. External DNS and direct-IP
    # connections are forbidden; CI additionally uses an empty network namespace.
    original_connect = socket.socket.connect
    original_connect_ex = socket.socket.connect_ex
    original_getaddrinfo = socket.getaddrinfo
    original_sendto = socket.socket.sendto

    def check_address(sock: socket.socket, address: object) -> None:
        if sock.family == getattr(socket, "AF_UNIX", None):
            return
        if not isinstance(address, tuple) or not _is_loopback(address[0]):
            raise AssertionError("External network access is disabled in tests")

    def connect(sock: socket.socket, address: object) -> None:
        check_address(sock, address)
        return original_connect(sock, address)

    def connect_ex(sock: socket.socket, address: object) -> int:
        check_address(sock, address)
        return original_connect_ex(sock, address)

    def getaddrinfo(host: object, *args: object, **kwargs: object) -> list:
        if not _is_loopback(host):
            raise AssertionError("External DNS access is disabled in tests")
        return original_getaddrinfo(host, *args, **kwargs)

    def sendto(sock: socket.socket, *args: object) -> int:
        check_address(sock, args[-1])
        return original_sendto(sock, *args)

    monkeypatch.setattr(socket.socket, "connect", connect)
    monkeypatch.setattr(socket.socket, "connect_ex", connect_ex)
    monkeypatch.setattr(socket.socket, "sendto", sendto)
    monkeypatch.setattr(socket, "getaddrinfo", getaddrinfo)
