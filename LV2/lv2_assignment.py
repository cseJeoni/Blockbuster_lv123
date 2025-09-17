#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LV2 통합 배정 (개선 적용 버전)
- Top-off: 배치율 극대화를 위해 항상 실행하도록 조건 제거
- 미사용 _precompute_voyage_counts 함수 호출 제거
- save: 총 운항 비용 계산 로직 추가
"""
import os
import json
import csv
import glob
import shutil
import time
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Set, Optional

os.environ.setdefault("MPLBACKEND", "Agg")

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from LV1.placement_api import generate_config, run_placement

class VoyageSchedule:
    def __init__(self):
        self.voyages: Dict[str, Dict] = {}
        self.vessel_voyages: Dict[str, List[str]] = defaultdict(list)

    @staticmethod
    def _to_iso(d: str) -> str:
        d = (d or "").strip()
        if len(d) == 6:
            yy, mm, dd = d[:2], d[2:4], d[4:]
            return f"20{yy}-{mm}-{dd}"
        return d

    def load_from_csv(self, csv_file: str):
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                start = self._to_iso(row["start_date"])
                end   = self._to_iso(row["end_date"])
                vid   = f'{row["vessel_name"]}_{start}_{end}'
                self.voyages[vid] = { "voyage_id": vid, "vessel_name": row["vessel_name"], "start_date": start, "end_date": end }
                self.vessel_voyages[row["vessel_name"]].append(vid)

    def add_voyage(self, vessel_name: str, start_date: str, end_date: str) -> str:
        vid = f"{vessel_name}_{start_date}_{end_date}"
        self.voyages[vid] = { "voyage_id": vid, "vessel_name": vessel_name, "start_date": start_date, "end_date": end_date }
        if vid not in self.vessel_voyages[vessel_name]:
            self.vessel_voyages[vessel_name].append(vid)
        return vid

    def info(self, voyage_id: str) -> Dict:
        return self.voyages.get(voyage_id, {})

def load_deadlines(file_path: str) -> Dict[str, str]:
    out = {}
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row["deadline"] or "").strip()
            if len(d) == 6: out[row["block_id"]] = f"20{d[:2]}-{d[2:4]}-{d[4:]}"
            else: out[row["block_id"]] = d
    return out

def load_labeling(file_path: str) -> Dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)

class IntegratedVoyageAssigner:
    MAX_STOWAGE_DAYS = 14
    PAGE_SIZE = 18
    LV1_TIMEOUT = 60
    LV1_TIMEOUT_SINGLE_WINDOW = 180
    CAPACITY_RATIO = 1.05

    def __init__(self,
                 schedule_csv: Optional[str] = None,
                 deadline_csv: str = "../data/block_deadline_7.csv",
                 labeling_results_file: str = "block_labeling_results.json",
                 out_json: str = "lv2_voyage_assignments.json",
                 vis_out_dir: str = "../placement_results"):
        self._t0 = time.time()
        self.out_json = out_json
        self.vis_out_dir = vis_out_dir
        self.schedule_source = "in_memory" if not schedule_csv else schedule_csv

        self.schedule = VoyageSchedule()
        if schedule_csv: self.schedule.load_from_csv(schedule_csv)
        else: print("[INFO] schedule_csv=None → 인메모리 스케줄 사용")

        self.deadlines = load_deadlines(deadline_csv)
        self.labeling  = load_labeling(labeling_results_file)

        if not isinstance(self.labeling.get("detailed_results"), dict):
            raise ValueError("[FATAL] block_labeling_results.json -> 'detailed_results'가 없습니다.")

        vip_list = self.labeling.get("classification", {}).get("vip_blocks", [])
        all_blocks = set(self.labeling["detailed_results"].keys())
        self.vip_blocks: Set[str] = set(vip_list)
        self.normal_blocks: Set[str] = set(all_blocks - self.vip_blocks)

        self.vessel_specs = self._load_vessel_specs()

        self.block_assignments: Dict[str, str] = {}
        self.voyage_blocks: Dict[str, List[str]] = defaultdict(list)
        self.logs: List[str] = []

        self._voyage_count_cache: Dict[str, int] = {}
        # self._precompute_voyage_counts() # <- 미사용 및 성능 저하로 제거

        print("\n[DIAG] 입력 요약")
        print(f"  - VIP: {len(self.vip_blocks)}개, Normal: {len(self.normal_blocks)}개, All: {len(all_blocks)}개")

    def _load_vessel_specs(self) -> Dict[int, Dict[str, int]]:
        # ... (이하 모든 헬퍼 함수들은 이전과 동일)
        candidate = os.path.join(os.path.dirname(__file__), "../vessel_specs.json")
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f: data = json.load(f)
                specs = {}
                for entry in data.get("vessels", []):
                    specs[int(entry["id"])] = { 
                        "name": entry["name"], 
                        "width": int(entry["width"]), 
                        "height": int(entry["height"]),
                        "voyage_cost": int(entry.get("voyage_cost", 350000000))  # 기본값 3.5억
                    }
                if specs: return specs
            except Exception as e: 
                print(f"[ERROR] vessel_specs.json 로드 실패: {e}")
                raise ValueError("vessel_specs.json 파일이 필요합니다. 파일을 확인해주세요.")
        
        raise ValueError("vessel_specs.json 파일을 찾을 수 없습니다.")

    def _label_meta(self, block_id: str) -> Dict:
        meta = self.labeling["detailed_results"].get(block_id)
        if not isinstance(meta, dict): raise KeyError(f"[FATAL] 라벨 메타가 없습니다: {block_id}")
        return meta

    def _area_of(self, block_id: str) -> Optional[float]:
        meta = self._label_meta(block_id)
        a = meta.get("block_info", {}).get("area")
        if a is not None:
            try: return float(a)
            except Exception: pass
        w, h = meta.get("block_info", {}).get("width"), meta.get("block_info", {}).get("height")
        try:
            if w is not None and h is not None: return float(w) * float(h)
        except Exception: pass
        gw, gh = meta.get("grid_width") or meta.get("width"), meta.get("grid_height") or meta.get("height")
        try:
            if gw is not None and gh is not None: return float(gw) * float(gh)
        except Exception: pass
        return None

    def _compatible_vessels(self, block_id: str) -> Optional[List[int]]:
        comp = self._label_meta(block_id).get("compatible_vessels")
        if isinstance(comp, list) and all(isinstance(x, int) for x in comp): return comp
        return None

    def _window_ok(self, block_id: str, end_date: str) -> bool:
        due = self.deadlines.get(block_id)
        if not due: return False
        d_due = datetime.strptime(due, "%Y-%m-%d")
        d_end = datetime.strptime(end_date, "%Y-%m-%d")
        return (d_due - timedelta(days=self.MAX_STOWAGE_DAYS)) <= d_end <= (d_due - timedelta(days=1))

    def _eligible_for_voyage(self, block_id: str, voyage_id: str) -> bool:
        vinfo = self.schedule.info(voyage_id)
        if not vinfo: return False
        if not self._window_ok(block_id, vinfo["end_date"]): return False
        comp = self._compatible_vessels(block_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        if block_id in self.vip_blocks and vessel_id != 1: return False
        if comp is not None and vessel_id not in comp: return False
        return True

    def _sorted_candidates(self, voyage_id: str, pool: List[str]) -> List[str]:
        def key(bid: str):
            d = self.deadlines.get(bid, "2099-12-31")
            area = self._area_of(bid)
            # 3차 정렬 기준으로 블록 ID(bid)를 추가
            return (d, -(area if area is not None else 0.0), bid)
        cands = [b for b in pool if self._eligible_for_voyage(b, voyage_id)]
        cands.sort(key=key)
        return cands

    def _page_limit_for_vessel(self, vessel_id: int) -> int:
        if vessel_id == 1: return 80
        elif vessel_id in (2, 4): return 44
        else: return 40

    def _move_config_to_lv1_configs(self, cfg_path: str) -> str:
        try:
            os.makedirs("lv1_configs", exist_ok=True)
            dst = os.path.join("lv1_configs", os.path.basename(cfg_path))
            if os.path.abspath(cfg_path) != os.path.abspath(dst):
                shutil.move(cfg_path, dst)
                return dst
        except Exception as e: print(f"[WARN] config 이동 실패: {e}")
        return cfg_path

    def _run_lv1(self, block_list: List[str], voyage_id: str, timeout: Optional[int] = None, enable_visual: bool = False) -> Tuple[List[str], List[str]]:
        if not block_list: return [], []
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]
        cfg_src = generate_config(ship_name=voyage_id, width=spec["width"], height=spec["height"], block_list=block_list)
        cfg = self._move_config_to_lv1_configs(cfg_src)
        result = run_placement(cfg, max_time=(timeout or self.LV1_TIMEOUT), enable_visualization=enable_visual)
        unplaced = list(result.get("unplaced_blocks", []))
        placed_count = int(result.get("placed_count", 0))
        total_count = int(result.get("total_count", len(block_list)))
        if placed_count + len(unplaced) != total_count: unplaced = list(block_list)
        
        unplaced_set = set(unplaced)
        placed = [b for b in block_list if b not in unplaced_set]
        return placed, unplaced

    def _sum_area(self, blocks: List[str]) -> Optional[float]:
        areas = [self._area_of(b) for b in blocks]
        if any(a is None for a in areas): return None
        # 부동소수점 정밀도 일관성을 위해 반올림 적용
        return round(sum(areas), 6)

    def _cap_by_area_or_page(self, blocks: List[str], target_area: float, page_limit: int) -> List[str]:
        acc, s = [], 0.0
        all_have_area = all(self._area_of(b) is not None for b in blocks)
        if all_have_area:
            # 부동소수점 정밀도 문제를 해결하기 위해 반올림 적용
            for b in blocks:
                a = self._area_of(b) or 0.0
                # 소수점 6자리로 반올림하여 정밀도 차이 제거
                rounded_sum = round(s + a, 6)
                rounded_target = round(target_area, 6)
                if rounded_sum <= rounded_target:
                    acc.append(b)
                    s = rounded_sum
                else: break
        else: acc = blocks[:page_limit]
        return acc


    def _assign_for_voyage(self, voyage_id: str, avail_vip: Set[str], avail_norm: Set[str]) -> int:
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]
        target_area = (spec["width"] * spec["height"]) * self.CAPACITY_RATIO
        page_limit = self._page_limit_for_vessel(vessel_id)

        vip_sorted  = self._sorted_candidates(voyage_id, sorted(list(avail_vip))) if vessel_id == 1 else []
        norm_sorted = self._sorted_candidates(voyage_id, sorted(list(avail_norm)))

        if not vip_sorted and not norm_sorted: return 0

        vip_seed = self._cap_by_area_or_page(vip_sorted, target_area, page_limit)
        vip_area = self._sum_area(vip_seed)
        rem_area = max(0.0, target_area - vip_area) if vip_area is not None else None
        normal_take = self._cap_by_area_or_page(norm_sorted, rem_area if rem_area is not None else target_area, page_limit)
        union = vip_seed + [b for b in normal_take if b not in vip_seed]

        if not union: return 0

        # Debug: union 리스트 길이 추적을 위한 로깅
        print(f"DEBUG: voyage_id={voyage_id}, vip_seed={len(vip_seed)}, normal_take={len(normal_take)}, union={len(union)}")

        timeout_union = self.LV1_TIMEOUT_SINGLE_WINDOW if vip_seed else self.LV1_TIMEOUT
        placed_all, _ = self._run_lv1(union, voyage_id, timeout=timeout_union)
        vip_ok = set(vip_seed).issubset(set(placed_all))
        
        placed_final, path = [], "NONE"

        if placed_all and vip_ok:
            placed_final = placed_all[:]
            path = "COMBINED_OK"
        elif vip_seed:
            placed_vip, _ = self._run_lv1(vip_seed, voyage_id, timeout=self.LV1_TIMEOUT_SINGLE_WINDOW)
            if placed_vip:
                placed_final = placed_vip[:]
                path = "FALLBACK_VIP_ONLY"
            else: return 0
        else: return 0
        
        
        def confirm(blocks: List[str]) -> int:
            count = 0
            for b in blocks:
                self.block_assignments[b] = voyage_id
                self.voyage_blocks[voyage_id].append(b)
                if b in self.vip_blocks: avail_vip.discard(b)
                else: avail_norm.discard(b)
                count += 1
            return count
            
        cnt = confirm(placed_final)
        # [최적화] 로그에 시작일_종료일 형식으로 표시
        vinfo = self.schedule.info(voyage_id)
        log_id = f"{vinfo['vessel_name']} {vinfo['start_date']}_{vinfo['end_date']}"
        self.logs.append(f"[{log_id}] PATH={path} placed={cnt}")
        return cnt

    def run_for_single_voyage(self, vessel_name: str, end_date: str, avail_vip: Set[str], avail_norm: Set[str], start_date: Optional[str] = None, cooldown_last_end: Optional[str] = None, cooldown_gap_days: int = 14) -> Dict:
        if cooldown_last_end:
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            d_min = datetime.strptime(cooldown_last_end, "%Y-%m-%d") + timedelta(days=cooldown_gap_days)
            if d_end < d_min: return {"voyage_id": f"{vessel_name}_{start_date}_{end_date}", "placed_blocks": [], "vip_placed": [], "normal_placed": [], "path": "SKIPPED_COOLDOWN"}

        if not start_date:
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            start_date = (d_end - timedelta(days=self.MAX_STOWAGE_DAYS)).strftime("%Y-%m-%d")

        vid = f"{vessel_name}_{start_date}_{end_date}"
        new_added = False
        if vid not in self.schedule.voyages:
            self.schedule.add_voyage(vessel_name, start_date, end_date)
            new_added = True

        before_blocks = set(self.voyage_blocks.get(vid, []))
        before_vip, before_norm = sorted(list(avail_vip)), sorted(list(avail_norm))
        self._assign_for_voyage(vid, avail_vip, avail_norm)
        after_blocks = set(self.voyage_blocks.get(vid, []))
        placed_now = sorted(list(after_blocks - set(before_blocks)))

        if not placed_now and new_added:
            vname = self.schedule.info(vid).get("vessel_name")
            self.schedule.voyages.pop(vid, None)
            if vname in self.schedule.vessel_voyages:
                self.schedule.vessel_voyages[vname] = [x for x in self.schedule.vessel_voyages[vname] if x != vid]
            return {"voyage_id": vid, "placed_blocks": [], "vip_placed": [], "normal_placed": [], "path": "ROLLBACK_EMPTY"}

        vip_placed = sorted([b for b in placed_now if b in before_vip])
        normal_placed = sorted([b for b in placed_now if b in before_norm])
        path = "UNKNOWN"
        for lg in reversed(self.logs[-5:]):
            if lg.startswith(f"[{vid}]"):
                path_info = lg.split("PATH=")[1].split(" ")[0]
                path = path_info
                break
        return {"voyage_id": vid, "placed_blocks": placed_now, "vip_placed": vip_placed, "normal_placed": normal_placed, "path": path}

    @staticmethod
    def _fmt_hms(seconds: float) -> str:
        s = int(round(seconds))
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"

    def _build_usage_summary(self) -> Dict:
        vessel_to_vids = defaultdict(list)
        for vid, blocks in self.voyage_blocks.items():
            if blocks: vessel_to_vids[self.schedule.info(vid)["vessel_name"]].append(vid)
        per_vessel = {}
        for vessel in [f"자항선{i}" for i in range(1, 6)]:
            vids = sorted(set(vessel_to_vids.get(vessel, [])))
            per_vessel[vessel] = { "voyage_count": len(vids), "block_count": sum(len(self.voyage_blocks[v]) for v in vids), "voyages": vids or ["없음"] }
        used_voyages_list = sorted([vid for vid, arr in self.voyage_blocks.items() if arr])
        unused_voyages_list = sorted([vid for vid in self.schedule.voyages if not self.voyage_blocks.get(vid)])
        return { "total_voyages": len(self.schedule.voyages), "used_voyages_count": len(used_voyages_list), "used_voyages_list": used_voyages_list, "unused_voyages_count": len(unused_voyages_list), "unused_voyages_list": unused_voyages_list, "per_vessel": per_vessel }

    def save(self):
        all_blocks = self.vip_blocks | self.normal_blocks
        assigned_blocks = set(self.block_assignments.keys())
        self.unassigned_blocks = sorted(list(all_blocks - assigned_blocks))
        
        # [해결] 비용 계산 로직 추가 - vessel_specs에서 운항 비용 읽어오기
        total_cost = 0
        used_voyages = [vid for vid, blocks in self.voyage_blocks.items() if blocks]
        
        for vid in used_voyages:
            vessel_name = self.schedule.info(vid).get("vessel_name", "")
            vessel_id = int(vessel_name.replace("자항선", "")) if vessel_name.startswith("자항선") else 1
            voyage_cost = self.vessel_specs.get(vessel_id, {}).get("voyage_cost", 350000000)  # 기본값 3.5억
            total_cost += voyage_cost
        
        elapsed = time.time() - self._t0
        assigned = len(self.block_assignments)
        total = len(all_blocks)
        info = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "elapsed_hms": self._fmt_hms(elapsed),
            "total_cost_krw": f"{total_cost:,.0f} KRW", # 비용 추가
            "schedule_source": self.schedule_source,
            "total_blocks": total,
            "assigned_blocks": assigned,
            "unassigned_blocks": len(self.unassigned_blocks),
            "assignment_rate": round(assigned / total * 100, 2) if total else 0.0,
            "logs": self.logs,
        }
        out = { "assignment_info": info, "usage_summary": self._build_usage_summary(), "voyage_assignments": self.voyage_blocks, "block_assignments": self.block_assignments, "unassigned_block_list": self.unassigned_blocks }
        with open(self.out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[SAVE] 결과 저장: {self.out_json}")

    def export_visualizations(self, out_dir: str = None, max_time_per_voyage: int = 15):
        out_dir = out_dir or self.vis_out_dir
        os.makedirs(out_dir, exist_ok=True)
        alt_dir = os.path.join("lv1_configs", "placement_results")
        os.makedirs(alt_dir, exist_ok=True)
        used_voyages = [vid for vid, arr in self.voyage_blocks.items() if arr]
        for vid in used_voyages:
            blocks = self.voyage_blocks[vid]
            if not blocks: continue
            vinfo = self.schedule.info(vid)
            spec = self.vessel_specs[int(vinfo["vessel_name"].replace("자항선", ""))]
            before = set(glob.glob(os.path.join(out_dir, "*.png"))) | set(glob.glob(os.path.join(alt_dir, "*.png")))
            vis_name = f"{vid}_VIS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            cfg_src = generate_config(ship_name=vis_name, width=spec["width"], height=spec["height"], block_list=blocks)
            cfg_moved = self._move_config_to_lv1_configs(cfg_src)
            try:
                run_placement(cfg_moved, max_time=max_time_per_voyage, enable_visualization=True)
                time.sleep(0.4)
                after = set(glob.glob(os.path.join(out_dir, "*.png"))) | set(glob.glob(os.path.join(alt_dir, "*.png")))
                new_files = sorted(list(after - before))
                if new_files:
                    newest = max(new_files, key=os.path.getmtime)
                    dst_name = f"{vinfo['vessel_name']} {vinfo['start_date']}_{vinfo['end_date']}.png"
                    dst = os.path.join(out_dir, dst_name)
                    if os.path.exists(dst): os.remove(dst)
                    shutil.copy2(newest, dst)
                    if os.path.basename(newest).startswith("config_placement_"): os.remove(newest)
                    print(f"[VIS] {os.path.basename(dst)} 생성")
            except Exception as e: print(f"[VIS] 실패: {vid} :: {e}")

if __name__ == "__main__":
    # LV2 단독 실행: 기존 항차 스케줄에 대해 블록 배정 수행
    import sys
    
    # 기본 파라미터 (절대 경로로 설정)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.dirname(script_dir)
    deadline_csv = os.path.join(project_root, "data", "block_deadline_7.csv")
    labeling_results_file = os.path.join(script_dir, "block_labeling_results.json")
    vessel_schedule_csv = os.path.join(project_root, "data", "vessel_schedule_7.csv")
    out_json = "lv2_voyage_assignments.json"
    vis_out_dir = "placement_results"
    
    # 명령행 인자 처리
    if len(sys.argv) > 1:
        deadline_csv = sys.argv[1]
    if len(sys.argv) > 2:
        labeling_results_file = sys.argv[2]
    if len(sys.argv) > 3:
        vessel_schedule_csv = sys.argv[3]
    
    print(f"[LV2] Starting LV2 Assignment...")
    print(f"[LV2] Deadline CSV: {deadline_csv}")
    print(f"[LV2] Labeling Results: {labeling_results_file}")
    print(f"[LV2] Vessel Schedule: {vessel_schedule_csv}")
    
    # LV2 배정 실행
    assigner = IntegratedVoyageAssigner(
        deadline_csv=deadline_csv,
        labeling_results_file=labeling_results_file,
        out_json=out_json,
        vis_out_dir=vis_out_dir
    )
    
    # 기존 항차 스케줄 로드
    assigner.schedule.load_from_csv(vessel_schedule_csv)
    print(f"[LV2] Loaded {len(assigner.schedule.voyages)} voyages from schedule")
    
    # 모든 블록을 가용 상태로 설정
    avail_vip = set(assigner.vip_blocks)
    avail_norm = set(assigner.normal_blocks)
    
    print(f"[LV2] Total blocks: VIP={len(avail_vip)}, Normal={len(avail_norm)}")
    
    # 각 항차에 대해 블록 배정 수행
    total_assigned = 0
    for voyage_id in sorted(assigner.schedule.voyages.keys()):
        if not avail_vip and not avail_norm:
            break
            
        print(f"\n[LV2] Processing voyage: {voyage_id}")
        assigned_count = assigner._assign_for_voyage(voyage_id, avail_vip, avail_norm)
        
        if assigned_count > 0:
            # 배정된 블록들을 가용 목록에서 제거
            assigned_blocks = assigner.voyage_blocks.get(voyage_id, [])
            for block_id in assigned_blocks:
                if block_id in avail_vip:
                    avail_vip.discard(block_id)
                elif block_id in avail_norm:
                    avail_norm.discard(block_id)
            
            total_assigned += assigned_count
            print(f"[LV2] Assigned {assigned_count} blocks to {voyage_id}")
        else:
            print(f"[LV2] No blocks assigned to {voyage_id}")
    
    # 결과 저장
    assigner.save()
    
    # 최종 통계
    total_blocks = len(assigner.vip_blocks) + len(assigner.normal_blocks)
    assignment_rate = (total_assigned / total_blocks * 100) if total_blocks > 0 else 0
    
    print(f"\n[LV2] === LV2 Assignment Complete ===")
    print(f"[LV2] Total blocks: {total_blocks}")
    print(f"[LV2] Assigned blocks: {total_assigned}")
    print(f"[LV2] Unassigned blocks: {total_blocks - total_assigned}")
    print(f"[LV2] Assignment rate: {assignment_rate:.2f}%")
    print(f"[LV2] Results saved to: {out_json}")
    
    # 시각화 코드 제거 (LV3에서 처리)