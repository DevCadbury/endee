# =============================================================================
# services/connection_manager.py — WebSocket Connection Registry
# =============================================================================
# Manages all active WebSocket connections for real-time chat.
#
# Room model
# ──────────
#   • conv:{conv_id}      — all participants in a specific conversation
#                           (one widget session + 0-N staff members)
#   • company:{company_id} — all staff/admin online for a company
#                            (used to broadcast new-conversation notifications)
#
# Lifecycle
# ─────────
#   Widget user:  connect_widget() → sends messages → disconnect()
#   Staff/Admin:  connect_staff()  → subscribe_to_conv() / unsubscribe_from_conv()
#                                  → sends messages → disconnect()
# =============================================================================

import asyncio
import logging
from collections import defaultdict
from typing import Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Thread-safe (asyncio) WebSocket connection registry."""

    def __init__(self):
        # conv_id → set of WebSocket connections (widget + subscribed staff)
        self._conv_rooms: Dict[str, Set[WebSocket]] = defaultdict(set)
        # company_id → set of staff/admin WebSockets (company-wide channel)
        self._company_staff: Dict[str, Set[WebSocket]] = defaultdict(set)
        # WebSocket → metadata dict
        self._meta: Dict[WebSocket, dict] = {}
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Connection – Widget (customer, no auth)
    # ------------------------------------------------------------------

    async def connect_widget(
        self,
        ws: WebSocket,
        conv_id: str,
        company_id: str,
        session_id: str,
    ) -> None:
        """Register a widget client to a conversation room."""
        async with self._lock:
            self._conv_rooms[conv_id].add(ws)
            self._meta[ws] = {
                "role": "customer",
                "conv_id": conv_id,
                "company_id": company_id,
                "session_id": session_id,
                "subscribed_convs": set(),
            }
        logger.info(
            f"[WS] Widget connected  session={session_id} conv={conv_id} company={company_id}"
        )

    # ------------------------------------------------------------------
    # Connection – Staff / Admin (JWT-authenticated)
    # ------------------------------------------------------------------

    async def connect_staff(
        self,
        ws: WebSocket,
        company_id: str,
        user_id: str,
        role: str,
    ) -> None:
        """Register a staff/admin client to the company-wide channel."""
        async with self._lock:
            self._company_staff[company_id].add(ws)
            self._meta[ws] = {
                "role": role,
                "company_id": company_id,
                "user_id": user_id,
                "conv_id": None,
                "subscribed_convs": set(),
            }
        logger.info(
            f"[WS] Staff connected   user={user_id} role={role} company={company_id}"
        )

    # ------------------------------------------------------------------
    # Conversation subscription (staff joining a specific room)
    # ------------------------------------------------------------------

    async def subscribe_to_conv(self, ws: WebSocket, conv_id: str) -> None:
        """Subscribe a staff connection to a specific conversation room."""
        async with self._lock:
            self._conv_rooms[conv_id].add(ws)
            meta = self._meta.get(ws)
            if meta:
                meta["subscribed_convs"].add(conv_id)
        logger.debug(f"[WS] Subscribed to conv={conv_id}")

    async def unsubscribe_from_conv(self, ws: WebSocket, conv_id: str) -> None:
        """Remove a staff connection from a conversation room."""
        async with self._lock:
            self._conv_rooms[conv_id].discard(ws)
            meta = self._meta.get(ws)
            if meta:
                meta["subscribed_convs"].discard(conv_id)

    # ------------------------------------------------------------------
    # Disconnect (any role)
    # ------------------------------------------------------------------

    async def disconnect(self, ws: WebSocket) -> None:
        """Remove a connection from every room it belongs to."""
        async with self._lock:
            meta = self._meta.pop(ws, {})
            role = meta.get("role", "customer")
            company_id = meta.get("company_id")

            # Remove from direct conversation room (widget)
            conv_id = meta.get("conv_id")
            if conv_id:
                self._conv_rooms[conv_id].discard(ws)

            # Remove from subscribed conversation rooms (staff)
            for subscribed_conv in meta.get("subscribed_convs", set()):
                self._conv_rooms[subscribed_conv].discard(ws)

            # Remove from company staff channel
            if company_id and role != "customer":
                self._company_staff[company_id].discard(ws)

            logger.info(
                f"[WS] Disconnected      role={role} "
                f"id={meta.get('user_id') or meta.get('session_id', '?')}"
            )
        return meta  # returned so caller can broadcast leave-presence

    # ------------------------------------------------------------------
    # Broadcast helpers
    # ------------------------------------------------------------------

    async def broadcast_to_conv(
        self,
        conv_id: str,
        payload: dict,
        exclude: Optional[WebSocket] = None,
    ) -> None:
        """Send a JSON payload to every participant in a conversation room."""
        async with self._lock:
            targets = list(self._conv_rooms.get(conv_id, set()))

        dead: list[WebSocket] = []
        for ws in targets:
            if ws is exclude:
                continue
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    async def broadcast_to_company_staff(
        self,
        company_id: str,
        payload: dict,
    ) -> None:
        """Send a JSON payload to ALL connected staff/admin for a company."""
        async with self._lock:
            targets = list(self._company_staff.get(company_id, set()))

        dead: list[WebSocket] = []
        for ws in targets:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            await self.disconnect(ws)

    # ------------------------------------------------------------------
    # Presence helpers
    # ------------------------------------------------------------------

    def get_conv_participants(self, conv_id: str) -> list[dict]:
        """Return lightweight participant info for a conversation room."""
        result = []
        for ws in list(self._conv_rooms.get(conv_id, set())):
            meta = self._meta.get(ws, {})
            result.append({
                "role": meta.get("role"),
                "id": meta.get("user_id") or meta.get("session_id"),
            })
        return result

    def company_staff_online(self, company_id: str) -> int:
        """Return count of staff/admin currently online for a company."""
        return len(self._company_staff.get(company_id, set()))

    def is_connected(self, ws: WebSocket) -> bool:
        return ws in self._meta


# Singleton — imported by api/ws.py, api/widget.py, api/conversations.py
manager = ConnectionManager()
