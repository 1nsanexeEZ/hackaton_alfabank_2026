class FakeContractArchive:
    """In-memory archive that refuses to overwrite a file, like the locked bucket."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes) -> None:
        if key in self.objects:
            raise AssertionError(f"{key} is locked and cannot be overwritten")
        self.objects[key] = content

    async def read(self, key: str) -> bytes:
        return self.objects[key]
