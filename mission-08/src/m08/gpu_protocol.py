"""The two-way human gate of MISSION_08_BRIEF.md section 10A as a state machine, for the simulated acceptance
scenarios of section 10A.7 (tests/test_gpu_protocol.py). It never touches a real instance: the agent can only emit
the two request messages; every lifecycle change of a paid instance is an event that only the user's reply causes.

States (section 10A.4): CPU_ONLY -> GPU_REQUEST_PREPARED -> WAIT_USER_ON -> USER_ON_CONFIRMED -> GPU_VERIFY ->
GPU_RUNNING -> GPU_SAVE_AND_CHECK -> WAIT_USER_OFF -> USER_OFF_CONFIRMED -> CPU_ONLY, plus STOP_UNVERIFIED.
"""

from __future__ import annotations

from dataclasses import dataclass, field

WAKE = "🦁【需要你唤醒GPU｜Mission 08｜第{n}次会话】"
STOP = "🦁【需要你关闭GPU｜Mission 08｜第{n}次会话】"
WAKE_FIELDS = ("科学目的", "为什么现在需要", "建议实例", "预计开机占用", "预计费用", "启动前就绪", "计划完成/放弃条件")
STOP_FIELDS = ("关机原因", "已完成", "未完成与风险", "当前费用")
WAKE_TAIL = "请你现在到AutoDL完成开机；完成后回复“GPU已开机”，并提供非敏感的连接方式/实例信息。**在你确认前，我不会开始GPU任务。**"
STOP_TAIL = "请你**立即在AutoDL控制台关闭实例**，然后回复“GPU已关机”。**停止脚本不代表停止计费；在确认关机之前不宣称费用已停止。**"

ALLOWED = {
    "CPU_ONLY": {"GPU_REQUEST_PREPARED"},
    "GPU_REQUEST_PREPARED": {"WAIT_USER_ON", "CPU_ONLY"},
    "WAIT_USER_ON": {"USER_ON_CONFIRMED", "CPU_ONLY"},
    "USER_ON_CONFIRMED": {"GPU_VERIFY"},
    "GPU_VERIFY": {"GPU_RUNNING", "WAIT_USER_OFF"},
    "GPU_RUNNING": {"GPU_SAVE_AND_CHECK", "WAIT_USER_OFF"},
    "GPU_SAVE_AND_CHECK": {"WAIT_USER_OFF"},
    "WAIT_USER_OFF": {"USER_OFF_CONFIRMED", "STOP_UNVERIFIED"},
    "USER_OFF_CONFIRMED": {"CPU_ONLY"},
    "STOP_UNVERIFIED": {"USER_OFF_CONFIRMED"},
}
ON_STATES = {"USER_ON_CONFIRMED", "GPU_VERIFY", "GPU_RUNNING", "GPU_SAVE_AND_CHECK", "WAIT_USER_OFF", "STOP_UNVERIFIED"}


class ProtocolError(RuntimeError):
    pass


@dataclass
class Evidence:
    """Section 10A.2: every item must hold before a wake request may be prepared."""
    scientific_need: bool = False          # named gate / hypothesis / metric that needs the compute
    cpu_reference_profiled: bool = False   # CPU reference run, fixed seed, measured profile
    cheapest_option_checked: bool = False  # CPU vs cheap GPU vs 96 GB compared on measured throughput
    compatibility_planned: bool = False
    benefit_criterion: bool = False        # CPU infeasible / cost clearly worse / power insufficient, with numbers
    approved_budget_cny: float = 0.0       # the user's explicit budget; unknown budget = 0

    def ok(self):
        return all([self.scientific_need, self.cpu_reference_profiled, self.cheapest_option_checked,
                    self.compatibility_planned, self.benefit_criterion]) and self.approved_budget_cny > 0


@dataclass
class Session:
    n: int = 1
    state: str = "CPU_ONLY"
    log: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    spent_cny: float = 0.0
    budget_cny: float = 0.0
    batches_run: int = 0

    def _go(self, new, who, why):
        if new not in ALLOWED[self.state]:
            raise ProtocolError(f"{self.state} -> {new} not allowed")
        self.log.append((self.state, new, who, why))
        self.state = new

    # --- agent actions -----------------------------------------------------------------------------------
    def decide(self, ev: Evidence):
        """Return the decision of section 10A.2 and prepare a wake request only when the evidence gate passes."""
        if not ev.scientific_need:
            return "CPU_CONTINUE"
        if not ev.ok():
            return "INCONCLUSIVE_RESOURCE_LIMIT" if ev.scientific_need and ev.approved_budget_cny <= 0 else "CPU_CONTINUE"
        self.budget_cny = ev.approved_budget_cny
        self._go("GPU_REQUEST_PREPARED", "agent", "evidence gate passed")
        return "REQUEST_GPU_EXPERIMENT"

    def send_wake(self, fields: dict):
        missing = [f for f in WAKE_FIELDS if f not in fields]
        if missing:
            raise ProtocolError(f"wake request missing {missing}")
        msg = "\n".join([WAKE.format(n=self.n)] + [f"{k}：{fields[k]}" for k in WAKE_FIELDS] + [WAKE_TAIL])
        self.messages.append(msg)
        self._go("WAIT_USER_ON", "agent", "wake request sent")
        return msg

    def verify(self, gpu_ok: bool):
        self._go("GPU_VERIFY", "agent", "checking GPU")
        if not gpu_ok:
            return self.request_stop({"关机原因": "兼容性或连接失败", "已完成": "无", "未完成与风险": "全部批次未运行",
                                      "当前费用": "按开机时长估计，未核实"})
        return None

    def run_batch(self, cost_cny: float):
        if self.state not in ("GPU_VERIFY", "GPU_RUNNING"):
            raise ProtocolError("no confirmed, verified GPU")
        if self.spent_cny + cost_cny > self.budget_cny:
            return self.request_stop({"关机原因": "预算将尽，不开始新批次", "已完成": f"{self.batches_run} 个批次",
                                      "未完成与风险": "剩余批次未运行", "当前费用": f"估计 {self.spent_cny:.2f} 元"})
        if self.state == "GPU_VERIFY":
            self._go("GPU_RUNNING", "agent", "first batch")
        self.spent_cny += cost_cny
        self.batches_run += 1
        return None

    def save_and_check(self):
        self._go("GPU_SAVE_AND_CHECK", "agent", "outputs saved, hashes checked")

    def request_stop(self, fields: dict):
        missing = [f for f in STOP_FIELDS if f not in fields]
        if missing:
            raise ProtocolError(f"stop request missing {missing}")
        msg = "\n".join([STOP.format(n=self.n)] + [f"{k}：{fields[k]}" for k in STOP_FIELDS] + [STOP_TAIL])
        self.messages.append(msg)
        self._go("WAIT_USER_OFF", "agent", "stop request sent")
        return msg

    def end_of_session(self):
        """Before ending a turn / the mission: a running or unconfirmed instance needs an explicit stop request, and
        cost cannot be declared stopped."""
        if self.state in ("USER_ON_CONFIRMED", "GPU_VERIFY", "GPU_RUNNING", "GPU_SAVE_AND_CHECK"):
            if self.state == "USER_ON_CONFIRMED":
                self._go("GPU_VERIFY", "agent", "ending")
            self.request_stop({"关机原因": "准备停工", "已完成": f"{self.batches_run} 个批次", "未完成与风险": "见账本",
                               "当前费用": "估计，未核实"})
        return {"state": self.state, "cost_handover_complete": self.state in ("CPU_ONLY", "USER_OFF_CONFIRMED")}

    def no_reply(self):
        if self.state == "WAIT_USER_OFF":
            self._go("STOP_UNVERIFIED", "agent", "no shutdown confirmation")

    # --- user events -------------------------------------------------------------------------------------
    def user_reply(self, text: str):
        if text.strip() == "GPU已开机" and self.state == "WAIT_USER_ON":
            self._go("USER_ON_CONFIRMED", "user", text)
        elif text.strip() == "GPU已关机" and self.state in ("WAIT_USER_OFF", "STOP_UNVERIFIED"):
            self._go("USER_OFF_CONFIRMED", "user", text)
            self._go("CPU_ONLY", "agent", "session closed")
            self.n += 1
        # anything else (silence, "script stopped", "ssh dropped") changes nothing


def choose_card(throughput: dict, price: dict, needed_vram_gb: float, vram: dict):
    """Cheapest card meeting the memory need, by measured cost per unit of work; never chosen from core count."""
    ok = [c for c in throughput if vram[c] >= needed_vram_gb and throughput[c] > 0]
    return min(ok, key=lambda c: price[c] / throughput[c]) if ok else None
