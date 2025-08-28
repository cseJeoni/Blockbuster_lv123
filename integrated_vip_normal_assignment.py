#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LV2 통합 배정 (합본 우선 → VIP-only 백업)
- VIP+Normal 합본 1회 → VIP 일부 누락 시 VIP-only 백업 1회
- 용적률 패스 105% 고정
- JSON에 실행 시간/사용 항차 요약 포함
- placement_results/ 에 확정 항차 시각화 저장 (파일명: "자항선N 선적일-하역일.png")
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

os.environ.setdefault("MPLBACKEND", "Agg")  # 시각화 팝업 방지

# --- LV1 API ---
from placement_api import generate_config, run_placement


# --------------------------
# 스케줄/데이터 로딩 유틸
# --------------------------
class VoyageSchedule:
    def __init__(self):
        self.voyages: Dict[str, Dict] = {}
        self.vessel_voyages: Dict[str, List[str]] = defaultdict(list)

    @staticmethod
    def _to_iso(d: str) -> str:
        d = (d or "").strip()
        if len(d) == 6:  # YYMMDD
            yy, mm, dd = d[:2], d[2:4], d[4:]
            return f"20{yy}-{mm}-{dd}"
        return d

    def load_from_csv(self, csv_file: str):
        with open(csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                start = self._to_iso(row["start_date"])
                end   = self._to_iso(row["end_date"])
                vid   = f'{row["vessel_name"]}_{row["end_date"]}'
                self.voyages[vid] = {
                    "voyage_id": vid,
                    "vessel_name": row["vessel_name"],
                    "start_date": start,
                    "end_date": end,
                }
                self.vessel_voyages[row["vessel_name"]].append(vid)
        print(f"[INFO] 스케줄 로드: {len(self.voyages)} 항차")

    def info(self, voyage_id: str) -> Dict:
        return self.voyages.get(voyage_id, {})


def load_deadlines(file_path: str) -> Dict[str, str]:
    out = {}
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            d = (row["deadline"] or "").strip()
            if len(d) == 6:
                out[row["block_id"]] = f"20{d[:2]}-{d[2:4]}-{d[4:]}"
            else:
                out[row["block_id"]] = d
    return out


def load_labeling(file_path: str) -> Dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------
# 통합 어사이너
# --------------------------
class IntegratedVoyageAssigner:
    MAX_STOWAGE_DAYS = 14           # 조기 적치 허용일(2주)
    PAGE_SIZE = 18                  # 면적 정보가 없을 때 한 번에 넣을 최대 블록 수
    LV1_TIMEOUT = 10                # 초
    LV1_TIMEOUT_SINGLE_WINDOW = 180 # 유효 창이 1개뿐인 블록 포함 시
    CAPACITY_RATIO = 1.05           # 105% 고정

    def __init__(self,
                 schedule_csv: str = "data/vessel_schedule_7.csv",
                 deadline_csv: str = "data/block_deadline_7.csv",
                 labeling_results_file: str = "block_labeling_results.json",
                 out_json: str = "integrated_voyage_assignments.json",
                 vis_out_dir: str = "placement_results"):
        self._t0 = time.time()
        self.out_json = out_json
        self.vis_out_dir = vis_out_dir

        # 데이터 로드
        self.schedule = VoyageSchedule()
        self.schedule.load_from_csv(schedule_csv)
        self.deadlines = load_deadlines(deadline_csv)
        self.labeling  = load_labeling(labeling_results_file)

        # 라벨 구조 검사
        if not isinstance(self.labeling.get("detailed_results"), dict):
            raise ValueError("[FATAL] block_labeling_results.json -> 'detailed_results'가 없습니다.")

        # VIP/Normal 분리
        vip_list = self.labeling.get("classification", {}).get("vip_blocks", [])
        all_blocks = set(self.labeling["detailed_results"].keys())
        self.vip_blocks: Set[str] = set(vip_list)
        self.normal_blocks: Set[str] = set(all_blocks - self.vip_blocks)

        # 선박 규격(필요 시 수정)
        self.vessel_specs = {
            1: {"name": "자항선1", "width": 62, "height": 170},
            2: {"name": "자항선2", "width": 36, "height": 84},
            3: {"name": "자항선3", "width": 32, "height": 120},
            4: {"name": "자항선4", "width": 40, "height": 130},
            5: {"name": "자항선5", "width": 32, "height": 116},
        }

        # 결과 컨테이너
        self.block_assignments: Dict[str, str] = {}          # block_id -> voyage_id
        self.voyage_blocks: Dict[str, List[str]] = defaultdict(list)
        self.logs: List[str] = []

        # 유효 항차 개수 캐시(타임아웃 가중 용도)
        self._voyage_count_cache: Dict[str, int] = {}
        self._precompute_voyage_counts()

        # 입력 요약
        print("\n[DIAG] 입력 요약")
        print(f"  - VIP: {len(self.vip_blocks)}개, Normal: {len(self.normal_blocks)}개, All: {len(all_blocks)}개")

    # ----- 메타 -----
    def _label_meta(self, block_id: str) -> Dict:
        meta = self.labeling["detailed_results"].get(block_id)
        if not isinstance(meta, dict):
            raise KeyError(f"[FATAL] 라벨 메타가 없습니다: {block_id}")
        return meta

    def _area_of(self, block_id: str) -> Optional[float]:
        meta = self._label_meta(block_id)
        # 우선 미터 단위 면적/치수 사용
        a = meta.get("block_info", {}).get("area")
        if a is not None:
            try:
                return float(a)
            except Exception:
                pass
        w = meta.get("block_info", {}).get("width")
        h = meta.get("block_info", {}).get("height")
        try:
            if w is not None and h is not None:
                return float(w) * float(h)
        except Exception:
            pass
        # 백업: grid_width/height (해상도 곱 필요) — 라벨러가 환산해줬다면 여기 안 옴
        gw = meta.get("grid_width") or meta.get("width")
        gh = meta.get("grid_height") or meta.get("height")
        try:
            if gw is not None and gh is not None:
                return float(gw) * float(gh)
        except Exception:
            pass
        return None

    def _compatible_vessels(self, block_id: str) -> Optional[List[int]]:
        comp = self._label_meta(block_id).get("compatible_vessels")
        if isinstance(comp, list) and all(isinstance(x, int) for x in comp):
            return comp
        return None

    # ----- 적합성/윈도우 -----
    def _window_ok(self, block_id: str, depart_date: str) -> bool:
        """도착일(depart_date=항차 end_date)이 [due-14, due] 안이면 OK"""
        due = self.deadlines.get(block_id)
        if not due:
            return False
        d_due = datetime.strptime(due, "%Y-%m-%d")
        d_dep = datetime.strptime(depart_date, "%Y-%m-%d")
        return (d_due - timedelta(days=self.MAX_STOWAGE_DAYS)) <= d_dep <= d_due

    def _eligible_for_voyage(self, block_id: str, voyage_id: str) -> bool:
        vinfo = self.schedule.info(voyage_id)
        if not vinfo:
            return False
        if not self._window_ok(block_id, vinfo["end_date"]):
            return False
        comp = self._compatible_vessels(block_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        if block_id in self.vip_blocks and vessel_id != 1:
            return False
        if comp is not None and vessel_id not in comp:
            return False
        return True

    def _sorted_candidates(self, voyage_id: str, pool: List[str]) -> List[str]:
        def key(bid: str):
            d = self.deadlines.get(bid, "2099-12-31")
            area = self._area_of(bid)
            return (d, -(area if area is not None else 0.0))
        cands = [b for b in pool if self._eligible_for_voyage(b, voyage_id)]
        cands.sort(key=key)  # EDD → 대형 우선
        return cands

    def _precompute_voyage_counts(self):
        # 각 블록이 가질 수 있는 유효 항차 개수 (타임아웃 가중치)
        all_blocks = list(self.vip_blocks | self.normal_blocks)
        for b in all_blocks:
            cnt = 0
            for vid in self.schedule.voyages.keys():
                if self._eligible_for_voyage(b, vid):
                    cnt += 1
            self._voyage_count_cache[b] = cnt

    def _count_compatible_voyages(self, block_id: str) -> int:
        return self._voyage_count_cache.get(block_id, 0)

    # ----- LV1 실행 -----
    def _run_lv1(self, block_list: List[str], voyage_id: str,
                 timeout: Optional[int] = None, enable_visual: bool = False) -> Tuple[List[str], List[str]]:
        if not block_list:
            return [], []
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]
        cfg = generate_config(ship_name=voyage_id, width=spec["width"], height=spec["height"], block_list=block_list)
        result = run_placement(cfg, max_time=(timeout or self.LV1_TIMEOUT), enable_visualization=enable_visual)

        unplaced = list(result.get("unplaced_blocks", []))
        placed_count = int(result.get("placed_count", 0))
        total_count  = int(result.get("total_count", len(block_list)))
        if placed_count + len(unplaced) != total_count:
            # 안전하게 전부 미배치로 취급 (LV1 결과 불일치 방어)
            unplaced = list(block_list)
        unplaced_set = set(unplaced)
        placed = [b for b in block_list if b not in unplaced_set]
        return placed, unplaced

    # ----- 유틸 -----
    def _sum_area(self, blocks: List[str]) -> Optional[float]:
        areas = []
        for b in blocks:
            a = self._area_of(b)
            if a is None:
                return None
            areas.append(a)
        return sum(areas)

    def _cap_by_area_or_page(self, blocks: List[str], target_area: float, page_limit: int) -> List[str]:
        """면적 정보가 모두 있으면 target_area까지 누적, 아니면 페이지 제한"""
        acc = []
        s = 0.0
        all_have_area = all(self._area_of(b) is not None for b in blocks)
        if all_have_area:
            for b in blocks:
                a = self._area_of(b) or 0.0
                if s + a <= target_area:
                    acc.append(b)
                    s += a
                else:
                    break
        else:
            acc = blocks[:page_limit]
        return acc

    # ----- 핵심: 항차 1건 배정 (합본 우선 → VIP-only 백업) -----
    def _assign_for_voyage(self, voyage_id: str, avail_vip: Set[str], avail_norm: Set[str]) -> int:
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]
        vessel_area = spec["width"] * spec["height"]
        target_area = vessel_area * self.CAPACITY_RATIO

        # 1) 후보 정렬
        vip_sorted  = self._sorted_candidates(voyage_id, list(avail_vip)) if vessel_id == 1 else []
        norm_sorted = self._sorted_candidates(voyage_id, list(avail_norm))

        if not vip_sorted and not norm_sorted:
            return 0

        # 2) 합본 1회 시도: VIP 먼저 채우고, 남는 용적만 Normal 넣기
        vip_seed = self._cap_by_area_or_page(vip_sorted, target_area, self.PAGE_SIZE)
        rem_area = None
        vip_area = self._sum_area(vip_seed)
        if vip_area is not None:
            rem_area = max(0.0, target_area - vip_area)
        normal_take = self._cap_by_area_or_page(norm_sorted, rem_area if rem_area is not None else target_area, self.PAGE_SIZE)
        union = vip_seed + [b for b in normal_take if b not in vip_seed]

        timeout_union = self.LV1_TIMEOUT_SINGLE_WINDOW if any(self._count_compatible_voyages(b) == 1 for b in union) else self.LV1_TIMEOUT
        placed_all, _ = self._run_lv1(union, voyage_id, timeout=timeout_union)
        placed_set = set(placed_all)

        def confirm(blocks: List[str]) -> int:
            count = 0
            for b in blocks:
                self.block_assignments[b] = voyage_id
                self.voyage_blocks[voyage_id].append(b)
                if b in avail_vip:  avail_vip.remove(b)
                if b in avail_norm: avail_norm.remove(b)
                count += 1
            return count

        if set(vip_seed).issubset(placed_set):
            # VIP 전원 유지 → 합본 확정
            self.logs.append(f"[{voyage_id}] PATH=COMBINED_OK vip={len(vip_seed)} norm={len([b for b in placed_all if b not in vip_seed])}")
            return confirm(placed_all)

        # 3) VIP-only 백업 1회
        timeout_vip = self.LV1_TIMEOUT_SINGLE_WINDOW if any(self._count_compatible_voyages(b) == 1 for b in vip_seed) else self.LV1_TIMEOUT
        placed_vip, _ = self._run_lv1(vip_seed, voyage_id, timeout=timeout_vip)
        self.logs.append(f"[{voyage_id}] PATH=FALLBACK_VIP_ONLY vip={len(placed_vip)}")
        return confirm(placed_vip)

    # ----- 전체 배정 루프 -----
    def run(self):
        avail_vip = set(self.vip_blocks)
        avail_norm = set(self.normal_blocks)

        # 선박 우선순위: 1 → 2 → 3 → 4 → 5
        for vessel_id in [1, 2, 3, 4, 5]:
            vname = f"자항선{vessel_id}"
            for vid in self.schedule.vessel_voyages.get(vname, []):
                if not avail_vip and not avail_norm:
                    break
                _ = self._assign_for_voyage(vid, avail_vip, avail_norm)

        # 남은 블록 집계
        self.unassigned_blocks = sorted(list(avail_vip | avail_norm))

    # ----- 요약/저장 -----
    @staticmethod
    def _fmt_hms(seconds: float) -> str:
        s = int(round(seconds))
        h = s // 3600
        m = (s % 3600) // 60
        sec = s % 60
        return f"{h:02d}:{m:02d}:{sec:02d}"

    def _build_usage_summary(self) -> Dict:
        vessel_to_vids = defaultdict(list)
        for vid, blocks in self.voyage_blocks.items():
            if blocks:
                vessel_to_vids[self.schedule.info(vid)["vessel_name"]].append(vid)

        per_vessel = {}
        used_count = 0
        for vessel in [f"자항선{i}" for i in range(1, 6)]:
            vids = sorted(vessel_to_vids.get(vessel, []))
            used = len(vids)
            used_count += used
            per_vessel[vessel] = {
                "voyage_count": used,
                "block_count": sum(len(self.voyage_blocks[v]) for v in vids),
                "voyages": vids or ["없음"],
            }

        used_voyages_list = sorted([vid for vid, arr in self.voyage_blocks.items() if arr])
        unused_voyages_list = sorted([vid for vid in self.schedule.voyages if not self.voyage_blocks.get(vid)])

        return {
            "total_voyages": len(self.schedule.voyages),
            "used_voyages_count": len(used_voyages_list),
            "used_voyages_list": used_voyages_list,
            "unused_voyages_count": len(unused_voyages_list),
            "unused_voyages_list": unused_voyages_list,
            "per_vessel": per_vessel,
        }

    def save(self):
        elapsed = time.time() - self._t0
        usage = self._build_usage_summary()
        assigned = len(self.block_assignments)
        total = len(self.vip_blocks) + len(self.normal_blocks)
        info = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "elapsed_hms": self._fmt_hms(elapsed),
            "total_blocks": total,
            "assigned_blocks": assigned,
            "unassigned_blocks": len(self.unassigned_blocks),
            "assignment_rate": round(assigned / total * 100, 2) if total else 0.0,
            "logs": self.logs,
        }
        out = {
            "assignment_info": info,
            "usage_summary": usage,
            "voyage_assignments": self.voyage_blocks,
            "block_assignments": self.block_assignments,
            "unassigned_block_list": self.unassigned_blocks,
        }
        with open(self.out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[SAVE] 결과 저장: {self.out_json}")

    # ----- 시각화 생성 (파일명: 자항선N 선적일-하역일.png) -----
    def export_visualizations(self, out_dir: str = None, max_time_per_voyage: int = 15):
        out_dir = out_dir or self.vis_out_dir
        os.makedirs(out_dir, exist_ok=True)
        used_voyages = [vid for vid, arr in self.voyage_blocks.items() if arr]
        for vid in used_voyages:
            blocks = self.voyage_blocks[vid]
            if not blocks:
                continue
            vinfo = self.schedule.info(vid)
            vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
            spec = self.vessel_specs[vessel_id]

            # 시각화를 위해 한 번 더 실행
            before = set(glob.glob(os.path.join(out_dir, "*.png")))
            vis_name = f"{vid}_VIS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            cfg = generate_config(
                ship_name=vis_name, width=spec["width"], height=spec["height"], block_list=blocks
            )
            try:
                _ = run_placement(cfg, max_time=max_time_per_voyage, enable_visualization=True)
                import time as _t; _t.sleep(0.4)
                after = set(glob.glob(os.path.join(out_dir, "*.png")))
                new_files = list(after - before)
                if new_files:
                    newest = max(new_files, key=os.path.getmtime)
                    # 파일명: 자항선N 선적일-하역일.png
                    start = vinfo["start_date"]
                    end = vinfo["end_date"]
                    dst_name = f"{vinfo['vessel_name']} {start}-{end}.png"
                    dst = os.path.join(out_dir, dst_name)
                    # 동명 파일 있으면 덮어씀
                    if os.path.exists(dst):
                        os.remove(dst)
                    shutil.copy2(newest, dst)
                    print(f"[VIS] {os.path.basename(dst)} 생성")
            except Exception as e:
                print(f"[VIS] 실패: {vid} :: {e}")


def main():
    assigner = IntegratedVoyageAssigner(
        schedule_csv="data/vessel_schedule_7.csv",
        deadline_csv="data/block_deadline_7.csv",
        labeling_results_file="block_labeling_results.json",
        out_json="integrated_voyage_assignments.json",
        vis_out_dir="placement_results",
    )
    assigner.run()
    assigner.save()
    # 시각화 생성 (확정된 항차만)
    assigner.export_visualizations(out_dir="placement_results", max_time_per_voyage=15)


if __name__ == "__main__":
    main()
