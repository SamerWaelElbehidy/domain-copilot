from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime

from domain.value_objects.approval import ApprovalToken


class ApprovalAuthority:
    """Issues and verifies approval tokens (binding principle 2).

    A token is an HMAC over (work_order_id, approved_by, approved_at) with a
    secret that only this object holds. A caller cannot fabricate one, reuse
    it for a different work order, or alter who approved it. Only the
    orchestrator's decide() path holds the authority and calls issue()."""

    def __init__(self, secret: bytes | None = None) -> None:
        self._secret = secret or os.urandom(32)

    def _sign(self, work_order_id: str, approved_by: str, approved_at: datetime) -> str:
        message = f"{work_order_id}\n{approved_by}\n{approved_at.isoformat()}".encode()
        return hmac.new(self._secret, message, hashlib.sha256).hexdigest()

    def issue(self, work_order_id: str, approved_by: str, approved_at: datetime) -> ApprovalToken:
        return ApprovalToken(
            work_order_id, approved_by, approved_at,
            self._sign(work_order_id, approved_by, approved_at),
        )

    def verify(self, token: object, work_order_id: object) -> bool:
        if not isinstance(token, ApprovalToken) or not isinstance(work_order_id, str):
            return False
        if token.work_order_id != work_order_id:
            return False
        expected = self._sign(token.work_order_id, token.approved_by, token.approved_at)
        return hmac.compare_digest(expected, token.signature)
