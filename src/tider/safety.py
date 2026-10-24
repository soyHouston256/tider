"""Límites con estado que el decisor puro no ve: deduplicación de alertas, enfriamiento por deployment, presupuesto
global de acciones automáticas e interruptor de apagado. En memoria y con un lock: vale para UNA réplica de Tider;
con varias, mover este estado a Postgres."""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Callable

from .config import autonomy_enabled


class Safety:
    def __init__(
        self,
        cooldown_minutes: float = 30,
        max_actions_per_hour: int = 3,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.cooldown = cooldown_minutes * 60
        self.max_per_hour = max_actions_per_hour
        self.clock = clock
        self._lock = threading.Lock()
        self._alerts: dict[str, float] = {}  # alerta -> cuándo se tomó
        self._targets: dict[str, float] = {}  # deployment -> última acción
        self._actions: deque[float] = deque()  # acciones de la última hora

    @classmethod
    def from_policy(cls, cfg: dict) -> "Safety":
        lim = cfg.get("limits", {})
        return cls(lim.get("cooldown_minutes", 30), lim.get("max_actions_per_hour", 3))

    def claim_alert(self, key: str) -> bool:
        """True si hay que procesar la alerta; False si ya se tomó dentro de la ventana (Alertmanager la reenvía)."""
        with self._lock:
            now = self.clock()
            if now - self._alerts.get(key, float("-inf")) < self.cooldown:
                return False
            self._alerts[key] = now
            return True

    def reserve_action(self, target: str) -> str | None:
        """Reserva una acción automática sobre target. None si se permite; si no, el motivo para escalar."""
        if not autonomy_enabled():
            return "Interruptor de apagado activo: acciones automáticas desactivadas."
        with self._lock:
            now = self.clock()
            while self._actions and now - self._actions[0] >= 3600:
                self._actions.popleft()
            last = self._targets.get(target)
            if last is not None and now - last < self.cooldown:
                return f"'{target}' tuvo una acción hace {int((now - last) // 60)} min (enfriamiento de {int(self.cooldown // 60)} min)."
            if len(self._actions) >= self.max_per_hour:
                return f"Presupuesto agotado: {self.max_per_hour} acciones automáticas en la última hora."
            self._targets[target] = now
            self._actions.append(now)
            return None
