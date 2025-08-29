#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LV3 — 선박별 사이클(이동-선적-이동-하역) 시간 반영
- 블록 윈도우: [due-14, due-1]  (하역은 납기 하루 전까지)
- 선박별 사이클 길이 = 이동1+선적+이동2+하역
    자항선1: 3-3-3-3 => 12일
    자항선2: 3-1-3-1 =>  8일
    자항선3/4/5: 3-3-3-2 => 11일
- 날짜 집합 최적화(DP)의 간격, Rescue, 쿨다운 감사 모두 '선박별 사이클 길이' 사용
- 항차 실행 시 start_date = end_date - (cycle_len-1) 로 계산(LV2에 전달)
- LV1/배치 엔진은 변경 없음
"""

import json
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, Tuple, Set, Optional, List

from integrated_vip_normal_assignment import IntegratedVoyageAssigner

# ---- 정책 상수 ----
MAX_STOWAGE_DAYS = 14          # 조기 적치 허용(윈도우 앞쪽 범위)
TOP_K_PEAKS = 30               # 히스토그램 상위 피크 수
GRID_STEP_DAYS = 3             # 격자 샘플링 간격
MAX_ROUNDS = 3                 # 집합 최적화 + 실행 라운드 수

# ---- 선박별 단계시간 ----
# (move_to_load, load, move_to_unload, unload)
VESSEL_PHASE_DUR = {
    1: (3, 3, 3, 3),   # 12
    2: (3, 1, 3, 1),   # 8
    3: (3, 3, 3, 2),   # 11
    4: (3, 3, 3, 2),   # 11
    5: (3, 3, 3, 2),   # 11
}

def cycle_len(vessel_id: int) -> int:
    a, b, c, d = VESSEL_PHASE_DUR[vessel_id]
    return a + b + c + d

# ---- 날짜 유틸 ----
def _to_date(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d")

def _to_str(d: datetime) -> str:
    return d.strftime("%Y-%m-%d")

# ---- 윈도우 ----
def build_windows(deadlines: Dict[str, str], blocks: Set[str]) -> Dict[str, Tuple[datetime, datetime]]:
    """
    블록 도착일(하역 종료일) 허용 윈도우: [due-14, due-1]
    """
    win: Dict[str, Tuple[datetime, datetime]] = {}
    for b in blocks:
        due = deadlines.get(b)
        if not due:
            continue
        d_due = _to_date(due)
        start = d_due - timedelta(days=MAX_STOWAGE_DAYS)
        end   = d_due - timedelta(days=1)  # 하역은 납기 전날까지 완료
        win[b] = (start, end)
    return win

# ---- eligible ----
def eligible_for_vessel(assigner: IntegratedVoyageAssigner, vessel_id: int, b: str) -> bool:
    if b in assigner.vip_blocks and vessel_id != 1:
        return False
    comp = assigner._compatible_vessels(b)
    return (comp is None) or (vessel_id in comp)

def eligible_blocks(assigner: IntegratedVoyageAssigner, vessel_id: int,
                    wins: Dict[str, Tuple[datetime, datetime]],
                    remaining: Set[str]) -> Set[str]:
    out: Set[str] = set()
    for b in remaining:
        if eligible_for_vessel(assigner, vessel_id, b) and (b in wins):
            out.add(b)
    return out

# ---- 히스토그램 ----
def histogram_over_dates(wins: Dict[str, Tuple[datetime, datetime]],
                         subset: Optional[Set[str]] = None) -> Dict[str, int]:
    counter = Counter()
    for b, (s, e) in wins.items():
        if subset is not None and b not in subset:
            continue
        d = s
        while d <= e:
            counter[_to_str(d)] += 1
            d += timedelta(days=1)
    return dict(counter)

# ---- 후보 날짜 생성(도착일 후보) ----
def build_candidate_dates_for_vessel(assigner: IntegratedVoyageAssigner,
                                     vessel_id: int,
                                     wins: Dict[str, Tuple[datetime, datetime]],
                                     remaining: Set[str]) -> List[str]:
    elig = eligible_blocks(assigner, vessel_id, wins, remaining)
    if not elig:
        return []

    # 1) 윈도우 경계(각 블록의 시작/끝)
    edges: Set[str] = set()
    for b in elig:
        s, e = wins[b]
        edges.add(_to_str(s))
        edges.add(_to_str(e))

    # 2) 히스토그램 상위 피크
    hist = histogram_over_dates(wins, elig)
    if hist:
        top = sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_K_PEAKS]
        edges.update([d for d, _ in top])

    # 3) 격자 샘플(3일 간격)
    min_date = min(_to_date(d) for d in edges) if edges else None
    max_date = max(_to_date(d) for d in edges) if edges else None
    if min_date and max_date:
        cur = min_date
        while cur <= max_date:
            edges.add(_to_str(cur))
            cur += timedelta(days=GRID_STEP_DAYS)

    # 정렬 반환
    out = sorted(edges)
    return out

# ---- 날짜별 점수(가치 근사) ----
def score_date(assigner: IntegratedVoyageAssigner,
               vessel_id: int, date_str: str,
               wins: Dict[str, Tuple[datetime, datetime]],
               remaining: Set[str]) -> float:
    """
    그 날짜(도착일)에서 적재 가능한 후보의 '가치 합' 근사치.
    희소 블록/대형/ VIP 가중치.
    """
    d = _to_date(date_str)
    spec = assigner.vessel_specs[vessel_id]
    target_area = (spec["width"] * spec["height"]) * assigner.CAPACITY_RATIO

    cands: List[Tuple[str, float, float]] = []  # (bid, area, value_weight)
    for b in remaining:
        if b not in wins:
            continue
        if not eligible_for_vessel(assigner, vessel_id, b):
            continue
        s, e = wins[b]
        if not (s <= d <= e):
            continue
        area = assigner._area_of(b) or 1.0
        comp = assigner._compatible_vessels(b)
        ships = 1 if (b in assigner.vip_blocks) else (len(comp) if comp else 5)
        scarcity = 1.0 / ships
        vip_bonus = 1.6 if (vessel_id == 1 and b in assigner.vip_blocks) else 1.0
        value = area * scarcity * vip_bonus
        cands.append((b, area, value))

    if not cands:
        return 0.0

    # 단순 그리디: 가치/면적 비로 정렬해 target_area까지 누적
    cands.sort(key=lambda x: (x[2] / max(1e-6, x[1])), reverse=True)
    s_area = 0.0
    s_val = 0.0
    for _, area, val in cands:
        if s_area + area <= target_area:
            s_area += area
            s_val += val
        else:
            break
    return s_val

# ---- 날짜 집합 선택: '선박별 사이클 길이' 간격을 둔 가중 독립집합 DP ----
def select_dates_with_gap(dates: List[str], scores: List[float], gap_days: int) -> List[str]:
    if not dates:
        return []
    items = sorted(zip(dates, scores), key=lambda x: x[0])
    dates = [x[0] for x in items]
    scores = [x[1] for x in items]

    D = [_to_date(d) for d in dates]
    p = []
    for i in range(len(dates)):
        j = i - 1
        while j >= 0 and (D[i] - D[j]).days < gap_days:
            j -= 1
        p.append(j)

    n = len(dates)
    dp = [0.0] * (n + 1)
    take = [False] * n
    for i in range(1, n + 1):
        take_val = scores[i - 1] + (dp[p[i - 1] + 1] if p[i - 1] >= 0 else 0.0)
        skip_val = dp[i - 1]
        if take_val > skip_val:
            dp[i] = take_val
            take[i - 1] = True
        else:
            dp[i] = skip_val
            take[i - 1] = False

    sel = []
    i = n - 1
    while i >= 0:
        if take[i]:
            sel.append(dates[i])
            i = p[i]
        else:
            i -= 1
    sel.reverse()
    return sel

# ---- Rescue: 희소 블록 개별 구출(다중 날짜 후보, 선박별 사이클 반영) ----
def rescue_pass(assigner: IntegratedVoyageAssigner,
                wins: Dict[str, Tuple[datetime, datetime]],
                avail_vip: Set[str], avail_norm: Set[str],
                last_end: Dict[str, Optional[str]],
                k_dates: int = 5) -> bool:
    remaining = list(set(avail_vip) | set(avail_norm))
    if not remaining:
        return False

    def feasibility_score(b: str) -> int:
        w = wins.get(b)
        if not w:
            return 0
        ws, we = w
        days = (we - ws).days + 1
        ships = 0
        for vid in [1, 2, 3, 4, 5]:
            if b in assigner.vip_blocks and vid != 1:
                continue
            comp = assigner._compatible_vessels(b)
            if comp is not None and vid not in comp:
                continue
            ships += 1
        return ships * max(0, days)

    remaining.sort(key=lambda b: feasibility_score(b))  # 어려운 것 우선

    progressed = False
    for b in remaining:
        order = [1, 2, 3, 4, 5] if b not in assigner.vip_blocks else [1]
        ws, we = wins.get(b, (_to_date("2099-01-01"), _to_date("2099-12-31")))
        for vid in order:
            vname = f"자항선{vid}"
            if not eligible_for_vessel(assigner, vid, b):
                continue

            gap = cycle_len(vid)
            min_end = ws
            if last_end[vname]:
                min_end = max(min_end, _to_date(last_end[vname]) + timedelta(days=gap))

            # 다중 날짜 후보(+0,+2,+4,+7,+10,..., we)
            deltas = [0, 2, 4, 7, 10, gap, gap + 3]
            candidates: List[datetime] = []
            for dt in deltas:
                cand = min_end + timedelta(days=dt)
                if cand <= we:
                    candidates.append(cand)
            if we >= min_end:
                candidates.append(we)

            seen = set()
            cands = [c for c in sorted(candidates) if (c not in seen and not seen.add(c))]

            for end_dt in cands[:max(1, k_dates)]:
                start_dt = end_dt - timedelta(days=gap - 1)  # 처음 이동 시작일
                result = assigner.run_for_single_voyage(
                    vessel_name=vname,
                    end_date=_to_str(end_dt),
                    avail_vip=avail_vip,
                    avail_norm=avail_norm,
                    start_date=_to_str(start_dt),
                    cooldown_last_end=last_end[vname],
                    cooldown_gap_days=gap,  # 선박별 사이클 길이
                )
                if result["placed_blocks"]:
                    last_end[vname] = _to_str(end_dt)
                    progressed = True
                    print(f"[LV3-RESCUE] {vname} {last_end[vname]}: placed={len(result['placed_blocks'])} seed={b}")
                    break
            if progressed:
                break
        if progressed:
            break
    return progressed

# ---- 진단 요약 ----
def summarize_unassigned(assigner: IntegratedVoyageAssigner,
                         wins: Dict[str, Tuple[datetime, datetime]],
                         last_end: Dict[str, Optional[str]]) -> Dict:
    remain = set(assigner.vip_blocks) | set(assigner.normal_blocks)
    remain -= set(assigner.block_assignments.keys())

    reasons = {
        "total_unassigned": len(remain),
        "no_deadline": 0,
        "window_blocked_by_cooldown": 0,
        "vip_only_waiting_ship1": 0,
        "eligible_but_unscheduled": 0,
        "examples": {
            "no_deadline": [],
            "window_blocked_by_cooldown": [],
            "vip_only_waiting_ship1": [],
            "eligible_but_unscheduled": [],
        }
    }
    for b in sorted(remain):
        due = assigner.deadlines.get(b)
        if not due:
            reasons["no_deadline"] += 1
            if len(reasons["examples"]["no_deadline"]) < 5:
                reasons["examples"]["no_deadline"].append(b)
            continue

        ws, we = wins.get(b, (_to_date("2099-01-01"), _to_date("2099-12-31")))
        comp = assigner._compatible_vessels(b)
        candidates = [1, 2, 3, 4, 5] if (b not in assigner.vip_blocks) else [1]
        blocked_all = True
        for vid in candidates:
            if comp is not None and vid not in comp:
                continue
            vname = f"자항선{vid}"
            gap = cycle_len(vid)
            min_end = ws
            if last_end[vname]:
                min_end = max(min_end, _to_date(last_end[vname]) + timedelta(days=gap))
            if min_end <= we:
                blocked_all = False
                break
        if blocked_all:
            if b in assigner.vip_blocks:
                reasons["vip_only_waiting_ship1"] += 1
                if len(reasons["examples"]["vip_only_waiting_ship1"]) < 5:
                    reasons["examples"]["vip_only_waiting_ship1"].append(b)
            else:
                reasons["window_blocked_by_cooldown"] += 1
                if len(reasons["examples"]["window_blocked_by_cooldown"]) < 5:
                    reasons["examples"]["window_blocked_by_cooldown"].append(b)
        else:
            reasons["eligible_but_unscheduled"] += 1
            if len(reasons["examples"]["eligible_but_unscheduled"]) < 5:
                reasons["examples"]["eligible_but_unscheduled"].append(b)
    return reasons

# ---- 메인 루틴: 날짜 집합 최적화 → 실행 → Rescue → 반복 ----
def lv3_schedule(
    deadline_csv: str = "data/block_deadline_7.csv",
    labeling_results_file: str = "block_labeling_results.json",
    out_json: str = "lv3_integrated_voyage_assignments.json",
    vis_out_dir: str = "placement_results",
) -> IntegratedVoyageAssigner:

    assigner = IntegratedVoyageAssigner(
        schedule_csv=None,
        deadline_csv=deadline_csv,
        labeling_results_file=labeling_results_file,
        out_json=out_json,
        vis_out_dir=vis_out_dir,
    )

    # 남은 블록 집합
    avail_vip = set(assigner.vip_blocks)
    avail_norm = set(assigner.normal_blocks)

    # 선박별 직전 '하역 종료일'
    last_end: Dict[str, Optional[str]] = {f"자항선{i}": None for i in range(1, 6)}

    progress_any = True
    rounds = 0

    while rounds < MAX_ROUNDS and progress_any and (avail_vip or avail_norm):
        rounds += 1
        progress_any = False

        remaining = set(avail_vip) | set(avail_norm)
        wins = build_windows(assigner.deadlines, remaining)
        if not wins:
            break

        # --- 날짜 집합 최적화(선박별) ---
        for vessel_id in [1, 2, 3, 4, 5]:
            vname = f"자항선{vessel_id}"
            cand_dates = build_candidate_dates_for_vessel(assigner, vessel_id, wins, remaining)
            if not cand_dates:
                continue

            scores = [score_date(assigner, vessel_id, d, wins, remaining) for d in cand_dates]
            gap = cycle_len(vessel_id)  # 선박별 간격
            selected = select_dates_with_gap(cand_dates, scores, gap_days=gap)
            if not selected:
                continue

            # --- 실행(시간순), end_date 기준 쿨다운 하드가드 ---
            for end_date in selected:
                if last_end[vname]:
                    dmin = _to_date(last_end[vname]) + timedelta(days=gap)
                    if _to_date(end_date) < dmin:
                        continue

                # start_move = end_date - (cycle_len - 1)
                start_move = _to_date(end_date) - timedelta(days=gap - 1)

                result = assigner.run_for_single_voyage(
                    vessel_name=vname,
                    end_date=end_date,
                    avail_vip=avail_vip,
                    avail_norm=avail_norm,
                    start_date=_to_str(start_move),
                    cooldown_last_end=last_end[vname],
                    cooldown_gap_days=gap,
                )
                if result["placed_blocks"]:
                    last_end[vname] = end_date
                    progress_any = True
                    remaining = set(avail_vip) | set(avail_norm)  # 갱신
                    wins = build_windows(assigner.deadlines, remaining)

        # --- Rescue: 남은 블록 구출(다중 날짜) ---
        rescue_iters = 0
        while (avail_vip or avail_norm) and rescue_iters < 8:
            if rescue_pass(assigner, wins, avail_vip, avail_norm, last_end, k_dates=5):
                progress_any = True
                remaining = set(avail_vip) | set(avail_norm)
                wins = build_windows(assigner.deadlines, remaining)
                rescue_iters += 1
            else:
                break

    # 저장/감사/시각화/진단 병합
    remaining = set(avail_vip) | set(avail_norm)
    wins = build_windows(assigner.deadlines, remaining)
    assigner.save()

    # 간격 감사(선박별 사이클 길이)
    _audit_cooldown(assigner)

    assigner.export_visualizations(out_dir=vis_out_dir, max_time_per_voyage=15)

    diag = summarize_unassigned(assigner, wins, last_end)
    try:
        with open(assigner.out_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        data["unassigned_reason_summary"] = diag
        with open(assigner.out_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[LV3] unassigned_reason_summary 병합 완료")
    except Exception as e:
        print(f"[LV3] 진단 병합 실패: {e}")

    return assigner

def _audit_cooldown(assigner: IntegratedVoyageAssigner):
    """
    같은 선박의 하역 종료일(end_date) 사이의 간격이
    해당 선박의 사이클 길이보다 짧으면 경고.
    """
    bad = []
    for v in [f"자항선{i}" for i in range(1, 6)]:
        ends = sorted(
            [assigner.schedule.info(vid)["end_date"]
             for vid, blks in assigner.voyage_blocks.items()
             if blks and assigner.schedule.info(vid)["vessel_name"] == v]
        )
        # 선박 ID 추출
        vid_num = int(v.replace("자항선", ""))
        need_gap = cycle_len(vid_num)
        for a, b in zip(ends, ends[1:]):
            da = _to_date(a); db = _to_date(b)
            if (db - da).days < need_gap:
                bad.append((v, a, b, need_gap))
    if bad:
        print("[AUDIT] Cooldown violations:", bad)
    else:
        print("[AUDIT] Cooldown OK")

def main():
    _ = lv3_schedule(
        deadline_csv="data/block_deadline_7.csv",
        labeling_results_file="block_labeling_results.json",
        out_json="lv3_integrated_voyage_assignments.json",
        vis_out_dir="placement_results",
    )

if __name__ == "__main__":
    main()
