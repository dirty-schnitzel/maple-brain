"""Keys into a VMware guest through VMware's own VNC server (`--window vmware`, 2026-11-10, a private server).

Host SendInput never reaches the guest (tools/vm/keytest.py). VMware Workstation's built-in VNC server
(VM > Settings > Options > VNC Connections) does: it turns each RFB KeyEvent into a key on the guest's virtual
keyboard, so the game in the guest sees an ordinary keyboard key - no injected-input flag, nothing added. Measured
2026-11-10: text sent over VNC showed up in the guest's Notepad.

Natural input (the user: "look like human input from within the vmware"): a KeyEvent is just (down/up, keysym),
nothing can be attached to it, and nothing else is ever sent - no pointer, no clipboard, no screen requests. The
timing is the caller's (Keyboard / KeyDriver humanize it). One thing a real keyboard never does is let go of a
key that isn't down, so a key-up for a key this link didn't press is dropped (Keyboard.release_all's safety net
would otherwise send key-ups for every usual key).

Only the keyboard part of RFB (RFC 6143) is used: handshake, then KeyEvents. No framebuffer is asked for, so the
server sends next to nothing back; a reader thread throws away whatever comes (bell, guest clipboard).
If the link drops, key events are dropped and ok() is False (Keyboard.focused() -> the hunt pauses as on focus
loss) until a reconnect works (tried at most every ~2 s).
Password (if the VM has one): env MAPLEBRAIN_VNC_PASSWORD - not a command-line flag, that shows in the process list.
"""
import os
import socket
import struct
import threading
import time

# bot key names (keyboard.SCAN / EXTENDED) -> X11 keysyms (what RFB KeyEvents carry)
KEYSYM = {"shift": 0xFFE1, "ctrl": 0xFFE3, "alt": 0xFFE9, "space": 0x20, "enter": 0xFF0D, "esc": 0xFF1B,
          "left": 0xFF51, "up": 0xFF52, "right": 0xFF53, "down": 0xFF54, "home": 0xFF50, "end": 0xFF57,
          "pageup": 0xFF55, "pagedown": 0xFF56, "insert": 0xFF63, "delete": 0xFFFF}
KEYSYM.update({c: ord(c) for c in "abcdefghijklmnopqrstuvwxyz0123456789"})
KEYSYM.update({f"f{i}": 0xFFBE + i - 1 for i in range(1, 13)})

PASSWORD_ENV = "MAPLEBRAIN_VNC_PASSWORD"
RETRY_S = 2.0


class VncError(ConnectionError):
    pass


def _des_response(password: str, challenge: bytes) -> bytes:
    """VNC authentication: the 16-byte challenge DES-encrypted with the password (8 chars, zero padded, each
    byte's bits reversed - RFB's quirk). Single DES = triple DES with the key three times."""
    try:
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except ImportError:
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    key = bytes(int(f"{b:08b}"[::-1], 2) for b in password.encode("latin-1")[:8].ljust(8, b"\0"))
    enc = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return enc.update(challenge) + enc.finalize()


def _recv(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        part = sock.recv(n - len(buf))
        if not part:
            raise VncError("the VNC server closed the connection")
        buf += part
    return buf


def handshake(sock, password: str | None) -> str:
    """RFB 3.3 / 3.7 / 3.8 up to ServerInit; returns the desktop name. Raises VncError with the server's reason."""
    server = _recv(sock, 12)
    if not server.startswith(b"RFB "):
        raise VncError(f"not a VNC server ({server!r})")
    minor = 8 if server >= b"RFB 003.008\n" else 7 if server >= b"RFB 003.007\n" else 3
    sock.sendall(b"RFB 003.%03d\n" % minor)

    def reason() -> str:
        return _recv(sock, struct.unpack(">I", _recv(sock, 4))[0]).decode("utf-8", "replace")

    if minor == 3:
        sec = struct.unpack(">I", _recv(sock, 4))[0]
        if sec == 0:
            raise VncError(reason())
    else:
        types = _recv(sock, _recv(sock, 1)[0])
        if not types:
            raise VncError(reason())
        sec = 2 if password and 2 in types else 1 if 1 in types else 2 if 2 in types else None
        if sec is None:
            raise VncError(f"no supported VNC security type (server offers {list(types)})")
        sock.sendall(bytes([sec]))
    if sec == 2:
        if not password:
            raise VncError(f"the VNC server wants a password: set {PASSWORD_ENV}")
        sock.sendall(_des_response(password, _recv(sock, 16)))
    elif sec != 1:
        raise VncError(f"unsupported VNC security type {sec}")
    if sec == 2 or minor == 8:
        if struct.unpack(">I", _recv(sock, 4))[0] != 0:
            raise VncError("VNC authentication failed" + (f": {reason()}" if minor == 8 else ""))
    sock.sendall(b"\x01")                                       # ClientInit: shared, don't kick other viewers
    _w, _h = struct.unpack(">HH", _recv(sock, 4))
    _recv(sock, 16)                                             # pixel format: unused, no screen is requested
    return reason()


class VncKeys:
    """`send(key, up)` = one key event into the guest, like keyboard._send is for this PC."""

    def __init__(self, addr: str = "127.0.0.1:5900", password: str | None = None, connect=socket.create_connection,
                 clock=time.monotonic, log=print):
        host, _, port = addr.rpartition(":")
        self.host, self.port = host or "127.0.0.1", int(port)
        self.password = password if password is not None else os.environ.get(PASSWORD_ENV) or None
        self._connect_fn, self.clock, self.log = connect, clock, log
        self.lock = threading.Lock()
        self.sock = None
        self.down: set[str] = set()              # keys this link has pressed and not let go
        self.failed_at = None                    # when the link was lost (None = fine / never tried)

    def connect(self) -> str:
        """Open the link now (raises VncError / OSError); returns the guest's desktop name."""
        with self.lock:
            return self._open()

    def _open(self) -> str:
        self._close()
        sock = self._connect_fn((self.host, self.port), 5)
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)     # each key out at once, not batched
            name = handshake(sock, self.password)
            sock.settimeout(5)
        except BaseException:
            sock.close()
            raise
        self.sock, self.failed_at = sock, None
        threading.Thread(target=self._drain, args=(sock,), name="vnc-drain", daemon=True).start()
        return name

    def _drain(self, sock) -> None:
        try:
            sock.settimeout(None)
            while sock.recv(4096):
                pass
        except OSError:
            pass

    def _close(self) -> None:
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def close(self) -> None:
        with self.lock:
            self._close()

    def ok(self) -> bool:
        """The link works (or was never needed yet). After a loss: try again, at most every RETRY_S."""
        with self.lock:
            if self.failed_at is None:
                return True
            if self.clock() - self.failed_at < RETRY_S:
                return False
            try:
                self._open()
                self.log(f"VNC: reconnected to {self.host}:{self.port}")
                return True
            except OSError as e:
                self.failed_at = self.clock()
                self.log(f"VNC: still no link ({e})")
                return False

    def send(self, key: str, up: bool) -> None:
        sym = KEYSYM[key]
        with self.lock:
            if up and key not in self.down:
                return                                          # never a key-up for a key that isn't down
            if self.failed_at is not None:
                return                                          # link lost: dropped until ok() reconnects
            msg = struct.pack(">BBxxI", 4, 0 if up else 1, sym)
            for attempt in (0, 1):
                try:
                    if self.sock is None:
                        self._open()
                    self.sock.sendall(msg)
                    break
                except OSError as e:
                    self._close()
                    if attempt:
                        self.failed_at = self.clock()
                        self.log(f"VNC: link lost ({e}): keys paused")
                        return
            (self.down.discard if up else self.down.add)(key)
