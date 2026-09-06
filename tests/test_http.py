import socket

from statusboard import http

V4 = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))
V6 = (
    socket.AF_INET6,
    socket.SOCK_STREAM,
    6,
    "",
    ("2606:2800:220:1:248:1893:25c8:1946", 443, 0, 0),
)


def test_ipv4_first_drops_v6_when_v4_exists():
    assert http.ipv4_first([V6, V4]) == [V4]
    assert http.ipv4_first([V4, V6, V4]) == [V4, V4]


def test_ipv4_first_keeps_v6_only_hosts():
    assert http.ipv4_first([V6]) == [V6]
    assert http.ipv4_first([]) == []


def test_prefer_ipv4_installs_and_restores(monkeypatch):
    original = http._original_getaddrinfo
    try:
        http.prefer_ipv4(True)
        assert socket.getaddrinfo is http._getaddrinfo_ipv4_first
        http.prefer_ipv4(False)
        assert socket.getaddrinfo is original
    finally:
        socket.getaddrinfo = original


def test_env_switch(monkeypatch):
    original = http._original_getaddrinfo
    try:
        monkeypatch.setenv("STATUSBOARD_IPV6", "1")
        http.prefer_ipv4_from_env()
        assert socket.getaddrinfo is original
        monkeypatch.delenv("STATUSBOARD_IPV6")
        http.prefer_ipv4_from_env()
        assert socket.getaddrinfo is http._getaddrinfo_ipv4_first
    finally:
        socket.getaddrinfo = original


def test_filtered_lookup_resolves_localhost_to_v4(monkeypatch):
    original = http._original_getaddrinfo
    try:
        http.prefer_ipv4(True)
        results = socket.getaddrinfo("localhost", 80, proto=socket.IPPROTO_TCP)
        assert results
        assert all(r[0] == socket.AF_INET for r in results)
    finally:
        socket.getaddrinfo = original
