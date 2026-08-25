"""IdentifierGenerator 的 UUID Adapter。"""

import uuid


class UuidIdentifierGenerator:
    def new_id(self) -> str:
        return str(uuid.uuid4())
