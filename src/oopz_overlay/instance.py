"""One application per Windows user; repeat launches open its settings."""

import hashlib
from pathlib import Path

from PySide6.QtCore import QObject, QLockFile, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket


class SingleInstance(QObject):
    activated = Signal()

    def __init__(self, state_root: Path):
        super().__init__()
        state_root.mkdir(parents=True, exist_ok=True)
        self.name = (
            "oopz-overlay-" + hashlib.sha256(str(state_root).encode()).hexdigest()[:16]
        )
        self.lock = QLockFile(str(state_root / "application.lock"))
        self.lock.setStaleLockTime(0)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._connected)

    def acquire(self) -> bool:
        if not self.lock.tryLock(0):
            client = QLocalSocket(self)
            client.connectToServer(self.name)
            if client.waitForConnected(1000):
                client.write(b"settings")
                client.waitForBytesWritten(1000)
                client.disconnectFromServer()
            return False
        QLocalServer.removeServer(self.name)
        if not self.server.listen(self.name):
            self.lock.unlock()
            raise OSError("无法创建程序入口，请关闭旧进程后重试。")
        return True

    def _connected(self) -> None:
        while self.server.hasPendingConnections():
            client = self.server.nextPendingConnection()
            client.disconnected.connect(client.deleteLater)
            client.readyRead.connect(lambda connection=client: connection.readAll())
            self.activated.emit()

    def close(self) -> None:
        self.server.close()
        self.lock.unlock()
