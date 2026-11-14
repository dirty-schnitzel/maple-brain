"""Keys into a VMware guest over VNC (maplebrain/vnc.py) against a fake RFB server on localhost."""
import socket
import struct
import threading

import pytest

import maplebrain.keyboard as keyboard
from maplebrain.config import Humanize
from maplebrain.keyboard import EXTENDED, SCAN
from maplebrain.vnc import KEYSYM, VncError, VncKeys, _des_response


class FakeServer:
    """RFB 3.8 server: security None (or VNC auth with `password`), then records every client message."""

    def __init__(self, password=None, version=b"RFB 003.008\n"):
        self.password, self.version = password, version
        self.lsock = socket.socket()
        self.lsock.bind(("127.0.0.1", 0))
        self.lsock.listen()
        self.addr = f"127.0.0.1:{self.lsock.getsockname()[1]}"
        self.got, self.conns, self.shared = [], [], []
        self.done = threading.Event()
        threading.Thread(target=self._serve, daemon=True).start()

    def _serve(self):
        while True:
            try:
                c, _ = self.lsock.accept()
            except OSError:
                return
            self.conns.append(c)
            threading.Thread(target=self._client, args=(c,), daemon=True).start()

    def _read(self, c, n):
        b = b""
        while len(b) < n:
            part = c.recv(n - len(b))
            if not part:
                raise EOFError
            b += part
        return b

    def _client(self, c):
        try:
            c.sendall(self.version)
            assert self._read(c, 12) == self.version
            if self.password is None:
                c.sendall(b"\x01\x01")
                assert self._read(c, 1) == b"\x01"
                c.sendall(b"\0\0\0\0")
            else:
                c.sendall(b"\x01\x02")
                assert self._read(c, 1) == b"\x02"
                challenge = bytes(range(16))
                c.sendall(challenge)
                ok = self._read(c, 16) == _des_response(self.password, challenge)
                if not ok:
                    c.sendall(b"\0\0\0\1" + struct.pack(">I", 3) + b"bad")
                    return
                c.sendall(b"\0\0\0\0")
            self.shared.append(self._read(c, 1))
            c.sendall(struct.pack(">HH", 1920, 1080) + bytes(16) + struct.pack(">I", 2) + b"vm")
            c.sendall(b"\x02")                                  # a Bell: the client must just swallow it
            while True:
                self.got.append(self._read(c, 8))
                self.done.set()
        except (EOFError, OSError):
            pass

    def keys(self):
        return [(m[0], m[1], struct.unpack(">I", m[4:])[0]) for m in self.got]

    def wait(self, n):
        for _ in range(200):
            if len(self.got) >= n:
                return
            self.done.wait(0.01)
            self.done.clear()

    def drop_clients(self):
        for c in self.conns:
            c.close()


def test_every_bot_key_has_a_keysym():
    assert set(SCAN) | set(EXTENDED) <= set(KEYSYM)
    assert KEYSYM["shift"] == 0xFFE1 and KEYSYM["left"] == 0xFF51 and KEYSYM["q"] == ord("q")


def test_key_events_are_plain_rfb_key_events_and_nothing_else():
    srv = FakeServer()
    v = VncKeys(srv.addr, log=lambda m: None)
    assert v.connect() == "vm"
    v.send("q", False)
    v.send("q", True)
    v.send("left", False)
    srv.wait(3)
    assert srv.shared == [b"\x01"]                          # shared: VMware's own console stays connected
    assert srv.keys() == [(4, 1, ord("q")), (4, 0, ord("q")), (4, 1, 0xFF51)]
    assert all(m[2:4] == b"\0\0" for m in srv.got)          # KeyEvent: type, down-flag, padding, keysym - no more


def test_never_a_key_up_for_a_key_that_is_not_down():
    """A real keyboard never releases a key it didn't press: release_all's safety net only lets go of ours."""
    srv = FakeServer()
    v = VncKeys(srv.addr, log=lambda m: None)
    kb = keyboard.Keyboard(hwnd=1, hcfg=Humanize(seed=3), out=v)
    kb.send("right", False)
    kb.release_all()                                         # would be ~8 key-ups via SendInput
    srv.wait(2)
    assert srv.keys() == [(4, 1, 0xFF53), (4, 0, 0xFF53)]
    assert not v.down


def test_over_vnc_the_host_window_in_front_does_not_matter(monkeypatch):
    """2026-11-10: no focus guard over VNC - the keys land in the guest whatever is in front on this PC."""
    srv = FakeServer()
    v = VncKeys(srv.addr, log=lambda m: None)
    v.connect()
    monkeypatch.setattr(keyboard.user32, "GetForegroundWindow", lambda: 999)    # some other host window
    kb = keyboard.Keyboard(hwnd=1, hcfg=Humanize(seed=3, react_min_s=0, react_max_s=0), out=v)
    assert kb.focused()
    kb.down("left")
    srv.wait(1)
    assert srv.keys() == [(4, 1, 0xFF51)]
    assert not keyboard.Keyboard(hwnd=1, hcfg=Humanize(seed=3)).focused()         # SendInput: still guarded


def test_password_auth():
    pytest.importorskip("cryptography", reason="VNC passwords need the vm extra: pip install -e .[vm]")
    srv = FakeServer(password="secret12")
    assert VncKeys(srv.addr, password="secret12", log=lambda m: None).connect() == "vm"
    with pytest.raises(VncError, match="authentication failed: bad"):
        VncKeys(srv.addr, password="wrong", log=lambda m: None).connect()
    with pytest.raises(VncError, match="password"):
        VncKeys(FakeServer(password="x").addr, password=None, log=lambda m: None).connect()


def test_rfb_3_3_server():
    class Old(FakeServer):
        def _client(self, c):
            c.sendall(b"RFB 003.003\n")
            assert self._read(c, 12) == b"RFB 003.003\n"
            c.sendall(b"\0\0\0\1")                          # 3.3: the server picks None, no result word
            self.shared.append(self._read(c, 1))
            c.sendall(struct.pack(">HH", 8, 8) + bytes(16) + struct.pack(">I", 0))
            self.got.append(self._read(c, 8))
    srv = Old()
    v = VncKeys(srv.addr, log=lambda m: None)
    assert v.connect() == ""
    v.send("z", False)
    srv.wait(1)
    assert srv.keys() == [(4, 1, ord("z"))]


def test_a_lost_link_pauses_like_lost_focus_and_comes_back(monkeypatch):
    srv = FakeServer()
    t = [0.0]
    v = VncKeys(srv.addr, clock=lambda: t[0], log=lambda m: None)
    v.connect()
    v.send("left", False)
    srv.wait(1)
    srv.lsock.close()                                        # the VM goes away: no reconnect possible
    srv.drop_clients()
    for _ in range(50):                                      # the dead socket shows on a later write
        v.send("x", False)
        if v.failed_at is not None:
            break
    assert v.failed_at is not None and not v.ok()
    assert "left" in v.down                                  # it was down when the link died
    monkeypatch.setattr(keyboard.user32, "GetForegroundWindow", lambda: 1)
    kb = keyboard.Keyboard(hwnd=1, hcfg=Humanize(seed=3), out=v)
    assert not kb.focused()                                  # the hunt pauses, as on focus loss
    srv2 = FakeServer()
    v.port = int(srv2.addr.rsplit(":", 1)[1])
    assert not v.ok()                                        # retries are spaced out
    t[0] += 2.5
    assert v.ok() and kb.focused()
    held = set(v.down)
    kb.release_all()                                         # what was down is let go, nothing else
    srv2.wait(len(held))
    assert sorted(srv2.keys()) == sorted((4, 0, KEYSYM[k]) for k in held) and not v.down
