import uuid
from ios_bridge import command


class MediaPlayer:
    def __init__(self):
        self.token = str(uuid.uuid4())
        self.path = None
        self.listener = None
        self.released = False

    def setDataSource(self, path):
        self.path = str(path)

    def prepare(self):
        if not self.path or self.released:
            raise RuntimeError("MediaPlayer has no source or was released")
        command("audio_prepare", token=self.token, path=self.path)

    def prepareAsync(self):
        self.prepare()
        if self.listener:
            self.listener(self)

    def setOnPreparedListener(self, listener):
        self.listener = listener

    def seekTo(self, milliseconds):
        command("audio_seek", token=self.token, seconds=milliseconds / 1000)

    def start(self):
        if self.released:
            raise RuntimeError("MediaPlayer was released")
        command("audio_play", token=self.token)

    def release(self):
        self.released = True
        command("audio_release", token=self.token)
