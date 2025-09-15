#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LV3 — 선박별 사이클 시간 반영 (개선 적용 버전)
- last_end 상태 즉시 업데이트 로직 추가하여 쿨다운 오류 수정
- rescue_pass: 각 라운드 종료 시 실행하여 배치율 우선
- 후보 날짜 생성 파라미터 원복 (배치율 우선)
- score_date: lru_cache 유지
"""
import json
import os
from datetime import datetime, timedelta
from collections import Counter
from typing import Dict, Tuple, Set, Optional, List
from functools import lru_cache

# Import handling for both direct execution and module import
try:
    from ..LV2.lv2_assignment import IntegratedVoyageAssigner
except ImportError:
    # Add parent directory to path for direct execution
    import sys
    sys.path.append(os.path.join(os.path.dirname(__file__), '..'))
    from LV2.lv2_assignment import IntegratedVoyageAssigner

# 디버깅용 전역 변수
DEBUG_OUTPUT_DIR = None
DEBUG_VOYAGE_COUNTER = 0

# ---- 정책 상수 (배치율 우선을 위해 원복) ----
MAX_STOWAGE_DAYS = 14
TOP_K_PEAKS = 30
GRID_STEP_DAYS = 3
MAX_ROUNDS = 3

# vessel_specs.json에서 사이클 데이터 로드
def load_vessel_cycle_data() -> Dict[int, Tuple]:
    """vessel_specs.json에서 자항선별 사이클 데이터 로드"""
    vessel_specs_file = os.path.join(os.path.dirname(__file__), "../vessel_specs.json")
    if not os.path.exists(vessel_specs_file):
        raise FileNotFoundError(f"vessel_specs.json 파일을 찾을 수 없습니다: {vessel_specs_file}")
    
    try:
        with open(vessel_specs_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        cycle_data = {}
        for vessel in data.get("vessels", []):
            vessel_id = int(vessel["id"])
            phases = vessel.get("cycle_phases")
            if phases is None:
                raise ValueError(f"선박 ID {vessel_id}의 cycle_phases 데이터가 없습니다")
            cycle_data[vessel_id] = tuple(phases)
        
        if not cycle_data:
            raise ValueError("vessel_specs.json에서 선박 데이터를 찾을 수 없습니다")
        
        return cycle_data
    except Exception as e:
        raise RuntimeError(f"vessel_specs.json에서 사이클 데이터 로드 실패: {e}")

VESSEL_PHASE_DUR = load_vessel_cycle_data()

def cycle_len(vessel_id: int) -> int:
    if vessel_id not in VESSEL_PHASE_DUR:
        raise ValueError(f"선박 ID {vessel_id}의 사이클 데이터를 찾을 수 없습니다")
    return sum(VESSEL_PHASE_DUR[vessel_id])

def _to_date(s: str) -> datetime: return datetime.strptime(s, "%Y-%m-%d")
def _to_str(d: datetime) -> str: return d.strftime("%Y-%m-%d")

def save_voyage_debug_info(vessel_name: str, end_date: str, round_num: int, 
                          eligible_blocks: Set[str], candidate_blocks: Set[str], 
                          result: Dict = None):
    """각 항차별 디버깅 정보를 JSON 파일로 저장"""
    global DEBUG_OUTPUT_DIR, DEBUG_VOYAGE_COUNTER
    
    if DEBUG_OUTPUT_DIR is None:
        return
    
    DEBUG_VOYAGE_COUNTER += 1
    
    start_date = _to_str(_to_date(end_date) - timedelta(days=cycle_len(int(vessel_name[-1])) - 1))
    voyage_name = f"{vessel_name}_{start_date}_{end_date}"
    
    debug_info = {
        "name": voyage_name,
        "eligible_blocks": sorted(list(eligible_blocks)),
        "candidate_blocks": sorted(list(candidate_blocks))
    }
    
    filename = f"{voyage_name}.json"
    filepath = os.path.join(DEBUG_OUTPUT_DIR, filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(debug_info, f, ensure_ascii=False, indent=2)
    
    print(f"[DEBUG] Saved voyage debug info: {filename}")

def build_windows(deadlines: Dict[str, str], blocks: Set[str]) -> Dict[str, Tuple[datetime, datetime]]:
    win = {}
    for b in blocks:
        due = deadlines.get(b)
        if not due: continue
        d_due = _to_date(due)
        win[b] = (d_due - timedelta(days=MAX_STOWAGE_DAYS), d_due - timedelta(days=1))
    return win

def eligible_for_vessel(assigner: IntegratedVoyageAssigner, vessel_id: int, b: str) -> bool:
    if b in assigner.vip_blocks and vessel_id != 1: return False
    comp = assigner._compatible_vessels(b)
    return comp is None or (vessel_id in comp)

def eligible_blocks(assigner: IntegratedVoyageAssigner, vessel_id: int, wins: Dict[str, Tuple[datetime, datetime]], remaining: Set[str]) -> Set[str]:
    # 결정적 순서를 위해 정렬된 리스트로 처리
    return {b for b in sorted(remaining) if eligible_for_vessel(assigner, vessel_id, b) and (b in wins)}

def histogram_over_dates(wins: Dict[str, Tuple[datetime, datetime]], subset: Optional[Set[str]] = None) -> Dict[str, int]:
    counter = Counter()
    for b, (s, e) in sorted(wins.items()):
        if subset is not None and b not in subset: continue
        d = s
        while d <= e:
            counter[_to_str(d)] += 1
            d += timedelta(days=1)
    return dict(counter)

def build_candidate_dates_for_vessel(assigner: IntegratedVoyageAssigner, vessel_id: int, wins: Dict[str, Tuple[datetime, datetime]], remaining: Set[str]) -> List[str]:
    elig = eligible_blocks(assigner, vessel_id, wins, remaining)
    if not elig: return []
    
    # 결정적 순서를 위해 정렬된 블록 순서로 처리
    edges_list = []
    for b in sorted(elig):  # 정렬로 순서 고정
        edges_list.extend([_to_str(wins[b][0]), _to_str(wins[b][1])])
    edges = set(edges_list)  # 중복 제거
    
    hist = histogram_over_dates(wins, elig)
    if hist:
        top = sorted(hist.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_K_PEAKS]
        edges.update([d for d, _ in top])
    if edges:
        min_date, max_date = min(_to_date(d) for d in edges), max(_to_date(d) for d in edges)
        cur = min_date
        while cur <= max_date:
            edges.add(_to_str(cur))
            cur += timedelta(days=GRID_STEP_DAYS)
    return sorted(edges)

def get_candidate_blocks_for_date(assigner: IntegratedVoyageAssigner, vessel_id: int, date_str: str, wins: Dict[str, Tuple[datetime, datetime]], remaining: frozenset[str]) -> Set[str]:
    """특정 날짜에 대해 105% 내 선발된 candidate 블록들을 반환"""
    d = _to_date(date_str)
    spec = assigner.vessel_specs[vessel_id]
    target_area = (spec["width"] * spec["height"]) * assigner.CAPACITY_RATIO
    cands = []
    for b in sorted(remaining):  # 결정적 순서를 위해 정렬
        if b not in wins or not eligible_for_vessel(assigner, vessel_id, b): continue
        s, e = wins[b]
        if not (s <= d <= e): continue
        area = assigner._area_of(b) or 1.0
        comp = assigner._compatible_vessels(b)
        ships = 1 if b in assigner.vip_blocks else (len(comp) if comp else 5)
        scarcity = 1.0 / ships
        vip_bonus = 1.6 if vessel_id == 1 and b in assigner.vip_blocks else 1.0
        value = area * scarcity * vip_bonus
        cands.append((b, area, value))
    if not cands: return set()
    cands.sort(key=lambda x: (x[2] / max(1e-6, x[1])), reverse=True)
    
    # 105% 내 선발된 블록들 추출
    selected_blocks = set()
    s_area = 0.0
    for b, area, val in cands:
        if s_area + area <= target_area * 1.05:  # 105% 허용
            selected_blocks.add(b)
            s_area += area
        else: break
    return selected_blocks

@lru_cache(maxsize=1000)
def score_date(assigner: IntegratedVoyageAssigner, vessel_id: int, date_str: str, wins: Tuple[Tuple[str, Tuple[datetime, datetime]], ...], remaining: frozenset[str]) -> float:
    d = _to_date(date_str)
    wins_dict = dict(wins)
    spec = assigner.vessel_specs[vessel_id]
    target_area = (spec["width"] * spec["height"]) * assigner.CAPACITY_RATIO
    cands = []
    for b in sorted(remaining):
        if b not in wins_dict or not eligible_for_vessel(assigner, vessel_id, b): continue
        s, e = wins_dict[b]
        if not (s <= d <= e): continue
        area = assigner._area_of(b) or 1.0
        comp = assigner._compatible_vessels(b)
        ships = 1 if b in assigner.vip_blocks else (len(comp) if comp else 5)
        scarcity = 1.0 / ships
        vip_bonus = 1.6 if vessel_id == 1 and b in assigner.vip_blocks else 1.0
        value = area * scarcity * vip_bonus
        cands.append((b, area, value))
    if not cands: return 0.0
    cands.sort(key=lambda x: (x[2] / max(1e-6, x[1])), reverse=True)
    s_area, s_val = 0.0, 0.0
    for _, area, val in cands:
        if s_area + area <= target_area:
            s_area += area
            s_val += val
        else: break
    return s_val

def select_dates_with_gap(dates: List[str], scores: List[float], gap_days: int) -> List[str]:
    if not dates: return []
    items = sorted(zip(dates, scores), key=lambda x: x[0])
    dates, scores = [x[0] for x in items], [x[1] for x in items]
    D = [_to_date(d) for d in dates]
    p = [-1] * len(dates)
    for i in range(len(dates)):
        for j in range(i - 1, -1, -1):
            if (D[i] - D[j]).days >= gap_days:
                p[i] = j
                break
    n = len(dates)
    dp = [0.0] * (n + 1)
    for i in range(1, n + 1):
        take_val = scores[i-1] + (dp[p[i-1] + 1] if p[i-1] != -1 else 0.0)
        skip_val = dp[i-1]
        dp[i] = max(take_val, skip_val)
    sel = []
    i = n
    while i > 0:
        take_val = scores[i-1] + (dp[p[i-1] + 1] if p[i-1] != -1 else 0.0)
        skip_val = dp[i-1]
        if take_val > skip_val:
            sel.append(dates[i-1])
            i = p[i-1] + 1
        else:
            i -= 1
    sel.reverse()
    return sel

def rescue_pass(assigner: IntegratedVoyageAssigner, wins: Dict[str, Tuple[datetime, datetime]], avail_vip: Set[str], avail_norm: Set[str], last_end: Dict[str, Optional[str]], k_dates: int = 5) -> bool:
    remaining = sorted(list(avail_vip | avail_norm))
    if not remaining: return False

    def feasibility_score(b: str) -> int:
        w = wins.get(b)
        if not w: return 0
        days = (w[1] - w[0]).days + 1
        ships = 0
        for vid in range(1, 6):
            if b in assigner.vip_blocks and vid != 1: continue
            comp = assigner._compatible_vessels(b)
            if comp and vid not in comp: continue
            ships += 1
        return ships * max(0, days)

    remaining.sort(key=feasibility_score)
    progressed = False
    for b in sorted(remaining):
        if b not in (avail_vip | avail_norm): continue
        order = [1] if b in assigner.vip_blocks else [1, 2, 3, 4, 5]
        ws, we = wins.get(b, (_to_date("2099-01-01"), _to_date("2099-12-31")))
        for vid in order:
            vname = f"자항선{vid}"
            if not eligible_for_vessel(assigner, vid, b): continue
            gap = cycle_len(vid)
            min_end = ws
            if last_end[vname]: min_end = max(min_end, _to_date(last_end[vname]) + timedelta(days=gap))
            
            deltas = [0, 2, 4, 7, 10, gap, gap + 3]
            # 결정적 순서를 위해 리스트로 처리 후 정렬
            candidates_list = [min_end + timedelta(days=dt) for dt in deltas if min_end + timedelta(days=dt) <= we]
            if we >= min_end: candidates_list.append(we)
            candidates = sorted(list(set(candidates_list)))  # 중복 제거 후 정렬
            
            for end_dt in candidates[:k_dates]:
                start_dt = end_dt - timedelta(days=gap - 1)
                result = assigner.run_for_single_voyage(vessel_name=vname, end_date=_to_str(end_dt), avail_vip=avail_vip, avail_norm=avail_norm, start_date=_to_str(start_dt), cooldown_last_end=last_end[vname], cooldown_gap_days=gap)
                if result["placed_blocks"]:
                    last_end[vname] = _to_str(end_dt)
                    progressed = True
                    print(f"[LV3-RESCUE] {vname} on {last_end[vname]}: placed {len(result['placed_blocks'])} blocks (seed: {b})")
                    break
            if progressed: break
        if progressed: break
    return progressed

def summarize_unassigned(assigner: IntegratedVoyageAssigner, wins: Dict[str, Tuple[datetime, datetime]], last_end: Dict[str, Optional[str]]) -> Dict:
    remain = (assigner.vip_blocks | assigner.normal_blocks) - set(assigner.block_assignments.keys())
    reasons = { "total_unassigned": len(remain), "no_deadline": 0, "window_blocked_by_cooldown": 0, "vip_only_waiting_ship1": 0, "eligible_but_unscheduled": 0, "examples": { "no_deadline": [], "window_blocked_by_cooldown": [], "vip_only_waiting_ship1": [], "eligible_but_unscheduled": [] } }
    for b in sorted(remain):
        if not assigner.deadlines.get(b):
            reasons["no_deadline"] += 1
            if len(reasons["examples"]["no_deadline"]) < 5: reasons["examples"]["no_deadline"].append(b)
            continue
        ws, we = wins.get(b, (_to_date("2099-01-01"), _to_date("2099-12-31")))
        comp, candidates = assigner._compatible_vessels(b), [1] if b in assigner.vip_blocks else [1, 2, 3, 4, 5]
        blocked_all = True
        for vid in candidates:
            if comp and vid not in comp: continue
            vname = f"자항선{vid}"
            min_end = ws
            if last_end[vname]: min_end = max(min_end, _to_date(last_end[vname]) + timedelta(days=cycle_len(vid)))
            if min_end <= we:
                blocked_all = False
                break
        if blocked_all:
            if b in assigner.vip_blocks:
                reasons["vip_only_waiting_ship1"] += 1
                if len(reasons["examples"]["vip_only_waiting_ship1"]) < 5: reasons["examples"]["vip_only_waiting_ship1"].append(b)
            else:
                reasons["window_blocked_by_cooldown"] += 1
                if len(reasons["examples"]["window_blocked_by_cooldown"]) < 5: reasons["examples"]["window_blocked_by_cooldown"].append(b)
        else:
            reasons["eligible_but_unscheduled"] += 1
            if len(reasons["examples"]["eligible_but_unscheduled"]) < 5: reasons["examples"]["eligible_but_unscheduled"].append(b)
    return reasons

def lv3_schedule(deadline_csv: str = None, labeling_results_file: str = None, out_json: str = "lv3_integrated_voyage_assignments.json", vis_out_dir: str = None) -> IntegratedVoyageAssigner:
    # 절대 경로로 기본값 설정
    if deadline_csv is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        deadline_csv = os.path.join(project_root, "data", "block_deadline_7.csv")
    
    if labeling_results_file is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        labeling_results_file = os.path.join(project_root, "LV2", "block_labeling_results.json")
    
    if vis_out_dir is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(script_dir)
        vis_out_dir = os.path.join(project_root, "placement_results")
    global DEBUG_OUTPUT_DIR, DEBUG_VOYAGE_COUNTER
    
    # 디버깅 폴더 생성
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    DEBUG_OUTPUT_DIR = f"lv3_debug_{timestamp}"
    os.makedirs(DEBUG_OUTPUT_DIR, exist_ok=True)
    DEBUG_VOYAGE_COUNTER = 0
    print(f"[DEBUG] Created debug output directory: {DEBUG_OUTPUT_DIR}")
    
    assigner = IntegratedVoyageAssigner(deadline_csv=deadline_csv, labeling_results_file=labeling_results_file, out_json=out_json, vis_out_dir=vis_out_dir)
    # 결정적 순서를 위해 정렬된 set 생성
    avail_vip, avail_norm = set(sorted(assigner.vip_blocks)), set(sorted(assigner.normal_blocks))
    last_end: Dict[str, Optional[str]] = {f"자항선{i}": None for i in range(1, 6)}

    # [최적화] 윈도우 캐싱
    windows_cache: Dict[frozenset, Dict[str, Tuple[datetime, datetime]]] = {}

    rounds = 0
    while rounds < MAX_ROUNDS and (avail_vip or avail_norm):
        rounds += 1
        print(f"\n[LV3] Starting Main Scheduling Round {rounds}/{MAX_ROUNDS}...")
        remaining = set(sorted(avail_vip | avail_norm))
        remaining_frozen = frozenset(sorted(avail_vip | avail_norm))
        
        # [최적화] 윈도우 캐싱 사용
        remaining_key = remaining_frozen
        if remaining_key in windows_cache:
            wins = windows_cache[remaining_key]
        else:
            wins = build_windows(assigner.deadlines, remaining)
            windows_cache[remaining_key] = wins
        
        if not wins: break
        
        wins_tuple = tuple(sorted(wins.items()))
        
        for vessel_id in [1, 2, 3, 4, 5]:
            vname = f"자항선{vessel_id}"
            remaining_frozen = frozenset(sorted(avail_vip | avail_norm))
            cand_dates = build_candidate_dates_for_vessel(assigner, vessel_id, wins, remaining_frozen)
            if not cand_dates: continue
            
            scores = [score_date(assigner, vessel_id, d, wins_tuple, remaining_frozen) for d in cand_dates]
            gap = cycle_len(vessel_id)
            selected = select_dates_with_gap(cand_dates, scores, gap_days=gap)
            
            for end_date in selected:
                start_move = _to_date(end_date) - timedelta(days=gap - 1)
                
                # --- [수정] ---
                # run_for_single_voyage의 결과를 받아 처리
                result = assigner.run_for_single_voyage(
                    vessel_name=vname,
                    end_date=end_date,
                    avail_vip=avail_vip,
                    avail_norm=avail_norm,
                    start_date=_to_str(start_move),
                    cooldown_last_end=last_end[vname],
                    cooldown_gap_days=gap
                )

                # 디버깅 정보 저장
                elig_blocks = eligible_blocks(assigner, vessel_id, wins, remaining_frozen)
                candidate_blocks = get_candidate_blocks_for_date(assigner, vessel_id, end_date, wins, remaining_frozen)
                save_voyage_debug_info(
                    vessel_name=vname,
                    end_date=end_date,
                    round_num=rounds,
                    eligible_blocks=elig_blocks,
                    candidate_blocks=candidate_blocks,
                    result=result
                )

                # 항차 생성이 성공한 경우(배치된 블록이 있는 경우)에만 last_end를 즉시 업데이트
                if result and result.get("placed_blocks"):
                    last_end[vname] = end_date
        
        print(f"[LV3] Round {rounds} Main scheduling finished. Attempting rescue pass...")
        rescue_pass(assigner, wins, avail_vip, avail_norm, last_end)

    assigner.save()
    _audit_cooldown(assigner)
    wins = build_windows(assigner.deadlines, avail_vip | avail_norm)
    diag = summarize_unassigned(assigner, wins, last_end)
    try:
        with open(assigner.out_json, "r", encoding="utf-8") as f: data = json.load(f)
        data["unassigned_reason_summary"] = diag
        with open(assigner.out_json, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print("[LV3] unassigned_reason_summary 병합 완료")
    except Exception as e: print(f"[LV3] 진단 병합 실패: {e}")
    return assigner

def _audit_cooldown(assigner: IntegratedVoyageAssigner):
    bad = []
    for v_id in range(1, 6):
        v = f"자항선{v_id}"
        ends = sorted([assigner.schedule.info(vid)["end_date"] for vid, blks in assigner.voyage_blocks.items() if blks and assigner.schedule.info(vid)["vessel_name"] == v])
        need_gap = cycle_len(v_id)
        for a, b in zip(ends, ends[1:]):
            if (_to_date(b) - _to_date(a)).days < need_gap:
                bad.append((v, a, b, need_gap))
    if bad: print("[AUDIT] Cooldown violations:", bad)
    else: print("[AUDIT] Cooldown OK")

if __name__ == "__main__":
    lv3_schedule()