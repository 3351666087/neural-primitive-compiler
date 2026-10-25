"""Simulated acceptance of the eight scenarios of MISSION_08_BRIEF.md section 10A.7. No instance is rented: the user's
replies are simulated strings, and the protocol must never reach GPU_RUNNING without the literal confirmation."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from m08.gpu_protocol import (STOP_TAIL, WAKE_TAIL, Evidence, ProtocolError, Session, choose_card)  # noqa: E402

FIELDS = {"科学目的": "x", "为什么现在需要": "x", "建议实例": "x", "预计开机占用": "x", "预计费用": "x",
          "启动前就绪": "x", "计划完成/放弃条件": "x"}
GOOD = Evidence(True, True, True, True, True, approved_budget_cny=20.0)


def confirmed_session():
    s = Session()
    assert s.decide(GOOD) == "REQUEST_GPU_EXPERIMENT"
    msg = s.send_wake(FIELDS)
    assert msg.startswith("🦁【需要你唤醒GPU｜Mission 08｜第1次会话】") and msg.endswith(WAKE_TAIL)
    s.user_reply("GPU已开机")
    return s


def test_1_no_gpu_need_no_request():
    s = Session()
    assert s.decide(Evidence()) == "CPU_CONTINUE"
    assert s.state == "CPU_ONLY" and s.messages == []


def test_2_need_but_user_does_not_confirm():
    s = Session()
    s.decide(GOOD)
    s.send_wake(FIELDS)
    for reply in ("", "好的", "开吧", "脚本已启动"):
        s.user_reply(reply)
    assert s.state == "WAIT_USER_ON"
    with pytest.raises(ProtocolError):
        s.run_batch(1.0)


def test_unknown_budget_is_zero():
    s = Session()
    ev = Evidence(True, True, True, True, True, approved_budget_cny=0.0)
    assert s.decide(ev) == "INCONCLUSIVE_RESOURCE_LIMIT" and s.state == "CPU_ONLY"


def test_3_compatibility_failure_requests_stop():
    s = confirmed_session()
    msg = s.verify(gpu_ok=False)
    assert s.state == "WAIT_USER_OFF" and msg.endswith(STOP_TAIL) and "兼容性" in msg


def test_4_budget_nearly_spent_no_new_batch():
    s = confirmed_session()
    s.verify(True)
    s.run_batch(15.0)
    msg = s.run_batch(10.0)                       # would exceed the 20 CNY approval
    assert s.batches_run == 1 and s.state == "WAIT_USER_OFF" and "预算将尽" in msg


def test_5_normal_completion_save_then_stop():
    s = confirmed_session()
    s.verify(True)
    s.run_batch(5.0)
    s.save_and_check()
    s.request_stop({"关机原因": "批次完成", "已完成": "1", "未完成与风险": "无", "当前费用": "估计 5 元"})
    s.user_reply("GPU已关机")
    assert s.state == "CPU_ONLY" and [x[1] for x in s.log][-4:] == ["GPU_SAVE_AND_CHECK", "WAIT_USER_OFF",
                                                                      "USER_OFF_CONFIRMED", "CPU_ONLY"]


def test_6_no_shutdown_reply_is_stop_unverified():
    s = confirmed_session()
    s.verify(True)
    s.run_batch(5.0)
    s.request_stop({"关机原因": "批次完成", "已完成": "1", "未完成与风险": "无", "当前费用": "估计"})
    for reply in ("ssh 断了", "nvidia-smi 失败", "命令已退出"):
        s.user_reply(reply)
    s.no_reply()
    assert s.state == "STOP_UNVERIFIED"


def test_7_no_upgrade_without_evidence():
    # measured relative throughput per hour and prices (CNY / h); 96 GB card no faster on this workload
    thr = {"24GB": 1.0, "32GB": 1.1, "96GB": 1.1}
    price = {"24GB": 1.6, "32GB": 2.2, "96GB": 6.98}
    vram = {"24GB": 24, "32GB": 32, "96GB": 96}
    assert choose_card(thr, price, needed_vram_gb=10, vram=vram) == "24GB"
    assert choose_card(thr, price, needed_vram_gb=40, vram=vram) == "96GB"


def test_8_mission_end_with_gpu_on_requires_stop_request():
    s = confirmed_session()
    s.verify(True)
    s.run_batch(5.0)
    out = s.end_of_session()
    assert s.messages[-1].startswith("🦁【需要你关闭GPU｜Mission 08｜第1次会话】")
    assert out["cost_handover_complete"] is False


def test_illegal_transition_rejected():
    s = Session()
    with pytest.raises(ProtocolError):
        s.run_batch(1.0)
    with pytest.raises(ProtocolError):
        s._go("GPU_RUNNING", "agent", "skip the gate")
