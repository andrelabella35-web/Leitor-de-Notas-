"""Limitador de uso em memória: por IP (janela deslizante de 1 h) e teto global por dia."""
import threading
import time
from collections import defaultdict, deque
from datetime import date


class Limitador:
    def __init__(self, por_ip_hora: int = 0, por_dia: int = 0, relogio=time.time):
        self.por_ip_hora, self.por_dia, self.relogio = por_ip_hora, por_dia, relogio
        self._ips = defaultdict(deque)
        self._dia, self._conta_dia = date.today(), 0
        self._lock = threading.Lock()

    def permitir(self, ip: str):
        """Devolve (ok, mensagem). Só consome cota quando permite."""
        with self._lock:
            agora = self.relogio()
            if date.today() != self._dia:
                self._dia, self._conta_dia = date.today(), 0
            if self.por_dia and self._conta_dia >= self.por_dia:
                return False, "O limite diário de leituras do demo foi atingido. Volte amanhã!"
            fila = self._ips[ip]
            while fila and agora - fila[0] > 3600:
                fila.popleft()
            if self.por_ip_hora and len(fila) >= self.por_ip_hora:
                return False, f"Limite de {self.por_ip_hora} leituras por hora atingido. Tente mais tarde."
            fila.append(agora)
            self._conta_dia += 1
            return True, ""
