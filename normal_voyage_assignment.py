# --- 파일: normal_voyage_assignment.py ---
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LEVEL 2 - Normal 블록 항차 배정 (근본 수정판)
- run_placement 결과(dict)의 'unplaced_blocks'만 사용 (get_unplaced_blocks 미사용)
- 항차별 다회전(패스) × 다중 페이지 스윕으로 LV1 반복 호출
- 면적 메타가 없으면 용적 제한 대신 page_size로만 페이징
- 시각화는 저장만(팝업 없음), 항차명으로 PNG 리네임
- 선박/항차 사용 현황 요약 및 JSON 저장
"""

import os
import re
import json
import csv
import glob
import shutil
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple, Set, Optional

# 시각화 팝업 방지
os.environ.setdefault("MPLBACKEND", "Agg")

# LV1 API
from placement_api import generate_config, run_placement  # get_unplaced_blocks 사용 안 함


# --------------------------
# 스케줄/데이터 로딩 유틸
# --------------------------
class VoyageSchedule:
    def __init__(self):
        self.voyages: Dict[str, Dict] = {}
        self.vessel_voyages: Dict[str, List[str]] = defaultdict(list)

    @staticmethod
    def _to_iso(yyyymmdd: str) -> str:
        if len(yyyymmdd) == 6:
            yy, mm, dd = yyyymmdd[:2], yyyymmdd[2:4], yyyymmdd[4:]
            return f"20{yy}-{mm}-{dd}"
        return yyyymmdd

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
            d = row["deadline"]
            if len(d) == 6:
                out[row["block_id"]] = f"20{d[:2]}-{d[2:4]}-{d[4:]}"
            else:
                out[row["block_id"]] = d
    return out


def load_labeling(file_path: str) -> Dict:
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


# --------------------------
# 메인 어사이너
# --------------------------
class NormalVoyageAssigner:
    MAX_STOWAGE_DAYS = 14          # 적치 허용일 (2주)
    PAGE_SIZE = 18                 # LV1 한 번에 투입할 최대 블록 수
    MAX_PAGES_PER_PASS = 50        # 패스당 최대 페이지 시도 수
    LV1_TIMEOUT = 60               # 초
    LV1_TIMEOUT_SINGLE_WINDOW = 180  # 유효 창이 1개뿐인 블록용 타임아웃

    # 다회전 패스별 용적 비율 (항차 면적 대비)
    PASS_CAPACITY_RATIOS = [1.05, 0.65, 0.45, 0.30]  # 105%, 65%, 45%, 30%

    def __init__(self,
                 schedule_csv: str = "data/vessel_schedule_7.csv",
                 deadline_csv: str = "data/block_deadline_7.csv",
                 labeling_results_file: str = "block_labeling_results.json",
                 vip_assign_file: str = "vip_voyage_assignments.json"):

        # 스케줄/데이터
        self.schedule = VoyageSchedule()
        self.schedule.load_from_csv(schedule_csv)
        self.deadlines = load_deadlines(deadline_csv)
        self.labeling  = load_labeling(labeling_results_file)

        # 필수 구조 검사 (정확한 데이터 전제)
        if not isinstance(self.labeling.get("detailed_results"), dict):
            raise ValueError("[FATAL] block_labeling_results.json -> 'detailed_results'가 없습니다.")
        if not isinstance(self.labeling.get("classification", {}).get("vip_blocks", []), list):
            raise ValueError("[FATAL] block_labeling_results.json -> 'classification.vip_blocks'가 리스트가 아닙니다.")

        # VIP로 이미 배정된 블록 제외
        vip_assigned: Set[str] = set()
        if os.path.exists(vip_assign_file):
            with open(vip_assign_file, "r", encoding="utf-8") as f:
                vip_json = json.load(f)
                vip_assigned = set(vip_json.get("block_assignments", {}).keys())

        # 선박 규격
        self.vessel_specs = {
            1: {"name": "자항선1", "width": 62, "height": 170},
            2: {"name": "자항선2", "width": 36, "height": 84},
            3: {"name": "자항선3", "width": 32, "height": 120},
            4: {"name": "자항선4", "width": 40, "height": 130},
            5: {"name": "자항선5", "width": 32, "height": 116},
        }

        # Normal 블록 수집 (엄격: detailed_results 기준)
        self.normal_blocks = self._collect_normal_blocks_strict(vip_assigned)
        print(f"[INFO] Normal 블록 수집: {len(self.normal_blocks)}개")

        # 결과 컨테이너
        self.block_assignments: Dict[str, str] = {}          # block_id -> voyage_id
        self._voyage_blocks_set: Dict[str, Set[str]] = defaultdict(set)  # voyage_id -> placed blocks
        self.unassigned_blocks: List[str] = []
        self.logs: List[str] = []

        # 진단 출력
        self._print_input_diagnostics(vip_assigned)

    # ----- 입력 진단 -----
    def _print_input_diagnostics(self, vip_assigned: Set[str]):
        vip_list = set(self.labeling.get("classification", {}).get("vip_blocks", []))
        print("\n[DIAG] 입력 진단")
        print(f"  - labeling keys(상위): {len(self.labeling.keys())} -> 샘플: {list(self.labeling.keys())[:6]}")
        print(f"  - deadlines: {len(self.deadlines)}")
        print(f"  - classification.vip_blocks: {len(vip_list)}")
        print(f"  - vip_file.block_assignments(참고): {len(vip_assigned)}")
        print(f"  - normal_blocks: {len(self.normal_blocks)}\n")

    # ----- 블록 수집 (엄격 모드) -----
    def _collect_normal_blocks_strict(self, vip_assigned: Set[str]) -> List[str]:
        """
        Normal 블록 = detailed_results의 모든 키 - VIP(분류) - VIP파일에서 이미 배정된 것
        (기본값/섞인 구조/유도 탐색 없음)
        """
        detailed = self.labeling["detailed_results"]
        all_blocks = set(detailed.keys())
        vip_list = set(self.labeling.get("classification", {}).get("vip_blocks", []))
        normal = sorted(list(all_blocks - vip_list - vip_assigned))
        return normal

    # ----- 라벨 메타 접근 -----
    def _label_meta(self, block_id: str) -> Dict:
        meta = self.labeling["detailed_results"].get(block_id)
        if not isinstance(meta, dict):
            raise KeyError(f"[FATAL] 라벨 메타가 없습니다: {block_id}")
        return meta

    # ----- 우선순위/필터 -----
    def _area_of(self, block_id: str) -> Optional[float]:
        """블록 면적. 없으면 None (용적 제한 미사용)"""
        meta = self._label_meta(block_id)
        if "area" in meta:
            try:
                return float(meta["area"])
            except Exception:
                return None
        w = meta.get("grid_width", meta.get("width"))
        h = meta.get("grid_height", meta.get("height"))
        try:
            if w is not None and h is not None:
                return float(w) * float(h)
        except Exception:
            pass
        return None  # 면적 정보를 확실히 알 수 없으면 None

    def _compatible_vessels(self, block_id: str) -> Optional[List[int]]:
        meta = self._label_meta(block_id)
        comp = meta.get("compatible_vessels")
        if isinstance(comp, list) and all(isinstance(x, int) for x in comp):
            return comp
        return None  # 정보 없으면 전 선박 허용

    def _eligible_for_voyage(self, block_id: str, voyage_id: str) -> bool:
        """납기-적치(0~14일) & compatible_vessels 조건 검사"""
        vinfo = self.schedule.info(voyage_id)
        if not vinfo:
            return False
        # 납기/적치
        end = vinfo["end_date"]
        dline = self.deadlines.get(block_id)
        if not dline:
            return False
        try:
            end_dt = datetime.strptime(end, "%Y-%m-%d")
            dl_dt  = datetime.strptime(dline, "%Y-%m-%d")
        except Exception:
            return False
        days = (dl_dt - end_dt).days
        if not (0 <= days <= self.MAX_STOWAGE_DAYS):
            return False
        # 호환 선박
        comp = self._compatible_vessels(block_id)
        if comp is not None:
            vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
            if vessel_id not in comp:
                return False
        return True


    def _sorted_candidates(self, voyage_id: str, pool: List[str]) -> List[str]:
        """
        ✨ 개선된 우선순위 적용: 1.긴급성(유효 항차 수) 2.납기일 3.면적
        """
        def key(bid):
            # 1. 긴급성: 이 블록을 실을 수 있는 유효 항차의 총 개수
            urgency = self._count_compatible_voyages(bid)
            
            # 2. 납기일
            d = self.deadlines.get(bid, "2099-12-31")

            # 3. 면적
            area = self._area_of(bid)

            # 튜플의 앞 순서일수록 우선순위가 높습니다.
            return (urgency, d, -(area if area is not None else 0.0))

        cands = [b for b in pool if self._eligible_for_voyage(b, voyage_id)]
        cands.sort(key=key)
        return cands

    def _count_compatible_voyages(self, block_id: str) -> int:
        """블록이 적치/납기/선박조건을 만족하는 항차(창) 개수"""
        cnt = 0
        for vid in self.schedule.voyages.keys():
            if self._eligible_for_voyage(block_id, vid):
                cnt += 1
        return cnt

    # ----- LV1 실행 래퍼 -----
    def _run_lv1(self, block_list: List[str], voyage_id: str,
                 timeout: int = None, enable_visual: bool = False) -> Tuple[List[str], List[str], str]:
        """
        LV1 호출: run_placement 결과(dict)의 'unplaced_blocks'만 사용.
        get_unplaced_blocks는 호출하지 않는다(오해석/에러 방지).
        """
        if not block_list:
            return [], [], ""

        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]

        cfg_path = generate_config(
            ship_name=voyage_id,
            width=spec["width"],
            height=spec["height"],
            block_list=block_list
        )
        result = run_placement(
            cfg_path,
            max_time=(timeout or self.LV1_TIMEOUT),
            enable_visualization=enable_visual
        )

        # --- 결과 해석(유일한 근거는 result['unplaced_blocks']) ---
        unplaced = list(result.get("unplaced_blocks", []))

        # 방어적 처리: placed_count/total_count와 모순이면 "전부 미배치"로 안전하게 간주
        placed_count = int(result.get("placed_count", 0))
        total_count  = int(result.get("total_count", len(block_list)))
        if placed_count + len(unplaced) != total_count:
            self.logs.append(f"[WARN] LV1 count mismatch on {voyage_id}: "
                             f"placed_count({placed_count}) + unplaced({len(unplaced)}) != total({total_count}). "
                             "Treating as all unplaced for safety.")
            unplaced = list(block_list)

        unplaced_set = set(unplaced)
        placed = [b for b in block_list if b not in unplaced_set]

        print(f"[LV1] {voyage_id} → placed {len(placed)}/{len(block_list)}, unplaced {len(unplaced)}")
        return placed, list(unplaced), cfg_path



    def _sweep_voyage(self, voyage_id: str, remaining: Set[str],
                      page_size: int = PAGE_SIZE) -> int:
        """
        하나의 항차에 대해 최적의 블록 조합을 찾습니다.
        여러 패스(용적률)에 걸쳐 후보군을 만들고 LV1을 실행하여,
        가장 많은 블록을 배치하는 단일 성공 케이스를 최종 결과로 선택합니다.
        ✨ 조기 탈출 로직이 추가되었습니다.
        """
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        vessel_area = self.vessel_specs[vessel_id]["width"] * self.vessel_specs[vessel_id]["height"]

        print(f"\n[SWEEP] {voyage_id} 시작 - 후보 {len(remaining)}개(전체 풀 기준)")

        all_cands_for_voyage = self._sorted_candidates(voyage_id, list(remaining))
        if not all_cands_for_voyage:
            print(f"  [SWEEP] {voyage_id}에 대한 유효 후보 없음.")
            return 0

        best_placed_for_voyage: List[str] = []

        for pass_idx, capacity_ratio in enumerate(self.PASS_CAPACITY_RATIOS):
            target_area = vessel_area * capacity_ratio
            
            pass_candidates = []
            cumulative_area = 0.0
            use_area_limit = all(self._area_of(b) is not None for b in all_cands_for_voyage)

            for block_id in all_cands_for_voyage:
                if use_area_limit:
                    area = self._area_of(block_id)
                    if cumulative_area + (area or 0) <= target_area:
                        pass_candidates.append(block_id)
                        cumulative_area += (area or 0)
                else:
                    if len(pass_candidates) < page_size:
                        pass_candidates.append(block_id)

            if not pass_candidates:
                continue
            
            area_msg = f"면적 {cumulative_area:.0f}/{target_area:.0f}" if use_area_limit else f"{len(pass_candidates)}개"
            print(f"  [PASS {pass_idx+1}] LV1 시도 ({capacity_ratio*100:.0f}% 기준): 후보 {area_msg}")

            single_window_blocks = [b for b in pass_candidates if self._count_compatible_voyages(b) == 1]
            timeout = self.LV1_TIMEOUT_SINGLE_WINDOW if single_window_blocks else self.LV1_TIMEOUT
            if single_window_blocks:
                print(f"    [INFO] 유효창 1개 블록 {len(single_window_blocks)}개 포함 -> 타임아웃 {timeout}초 적용")
            
            placed, unplaced, _ = self._run_lv1(pass_candidates, voyage_id, timeout=timeout, enable_visual=False)

            if len(placed) > len(best_placed_for_voyage):
                print(f"  [SWEEP] 🌟 새 최적 배치 발견: {len(placed)}개 블록 (이전 최적: {len(best_placed_for_voyage)}개)")
                best_placed_for_voyage = placed

            # ✨ 조기 탈출 로직: 첫 Pass에서 성공한 블록이 없다면, 추가 시도를 중단합니다.
            if pass_idx == 0 and not placed:
                print(f"  [SKIP] 초기 패스에서 배치 성공 블록이 없어 {voyage_id} 탐색을 중단합니다.")
                break
        
        #--- 모든 패스가 끝난 후, 최종 결과를 반영합니다.
        if best_placed_for_voyage:
            print(f"  [SWEEP] ✅ {voyage_id} 최종 확정: {len(best_placed_for_voyage)}개 블록")
            # `remaining` 집합은 수정하지 않고, 배치된 블록의 개수만 반환합니다.
            # 실제 `remaining` 업데이트는 이 함수를 호출한 루프에서 처리합니다.
            
            # 확정된 블록들을 클래스 변수에 기록
            for b in best_placed_for_voyage:
                self.block_assignments[b] = voyage_id
                self._voyage_blocks_set[voyage_id].add(b)
            return len(best_placed_for_voyage)
        
        print(f"  [SWEEP] ❌ {voyage_id}에는 최종 배치할 블록을 찾지 못함.")
        return 0

    def assign_on_vessel1(self):
        """자항선1 전 항차 스윕"""
        remaining = set(self.normal_blocks)
        # 항차 순서를 날짜순으로 정렬하여 처리
        voyage_ids = sorted(self.schedule.vessel_voyages.get("자항선1", []), 
                            key=lambda vid: self.schedule.info(vid).get("end_date"))
        
        for vid in voyage_ids:
            if not remaining:
                break
            
            # _sweep_voyage 내에서 self.block_assignments와 self._voyage_blocks_set이 업데이트됨
            self._sweep_voyage(vid, remaining)
            
            # 배치된 블록들을 remaining 세트에서 제거
            placed_blocks = {b for b, v in self.block_assignments.items() if v == vid}
            remaining.difference_update(placed_blocks)
            
        self.unassigned_blocks = sorted(list(remaining))

    def assign_on_other_vessels(self, leftover: List[str]):
        """남은 블록을 자항선2~5 항차로 확장 스윕"""
        remaining = set(leftover)
        
        # 모든 2-5번 선박의 항차를 모아 날짜순으로 정렬
        other_voyages = []
        for vessel_id in [2, 3, 4, 5]:
            vname = f"자항선{vessel_id}"
            other_voyages.extend(self.schedule.vessel_voyages.get(vname, []))
        
        voyage_ids = sorted(other_voyages, key=lambda vid: self.schedule.info(vid).get("end_date"))

        for vid in voyage_ids:
            if not remaining:
                break
            
            self._sweep_voyage(vid, remaining)
            
            placed_blocks = {b for b, v in self.block_assignments.items() if v == vid}
            remaining.difference_update(placed_blocks)
            
        self.unassigned_blocks = sorted(list(remaining))

    # ----- 시각화 내보내기 (항차별 확정본) -----
    def export_visualizations(self, out_dir: str = "placement_results", max_time_per_voyage: int = 15):
        """
        이미 확정된 항차만 대상으로, 시각화 PNG 생성/복제.
        - ship_placer가 out_dir에 만든 PNG를 항차별로 정확히 매칭/리네임
        - 팝업 없음
        """
        os.makedirs(out_dir, exist_ok=True)
        used_voyages = [vid for vid, s in self._voyage_blocks_set.items() if s]

        print(f"\n[INFO] 항차별 최종 시각화 생성 시작 ({len(used_voyages)}개 항차)")

        for i, vid in enumerate(used_voyages):
            blocks = sorted(list(self._voyage_blocks_set[vid]))
            if not blocks:
                continue

            print(f"[VIS {i+1}/{len(used_voyages)}] {vid} - {len(blocks)}개 블록")

            vinfo = self.schedule.info(vid)
            vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
            spec = self.vessel_specs[vessel_id]

            # 기존 PNG 파일들 스냅샷
            before_files = set(glob.glob(os.path.join(out_dir, "*.png")))

            # LV1 실행 (시각화 포함)
            vis_name = f"{vid}_VIS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            cfg_path = generate_config(
                ship_name=vis_name,
                width=spec["width"],
                height=spec["height"],
                block_list=blocks
            )

            try:
                _ = run_placement(cfg_path, max_time=max_time_per_voyage, enable_visualization=True)

                # 새로 생성된 PNG 파일 탐지
                import time
                time.sleep(0.5)  # 파일 생성 완료 대기

                after_files = set(glob.glob(os.path.join(out_dir, "*.png")))
                new_files = after_files - before_files

                if new_files:
                    newest_file = max(new_files, key=os.path.getmtime)
                    target_path = os.path.join(out_dir, f"{vid}.png")

                    if os.path.exists(target_path):
                        os.remove(target_path)

                    shutil.copy2(newest_file, target_path)
                    print(f"[VIS] {vid}.png 생성 완료")

                else:
                    self.logs.append(f"[VIS] PNG 생성 실패: {vid} - 새 파일 탐지되지 않음")
                    print(f"[VIS] {vid} PNG 생성 실패")

            except Exception as e:
                self.logs.append(f"[VIS] 시각화 실행 실패: {vid} :: {e}")
                print(f"[VIS] {vid} 시각화 실행 실패: {e}")

        final_pngs = glob.glob(os.path.join(out_dir, "*.png"))
        voyage_pngs = [f for f in final_pngs if any(vid in os.path.basename(f) for vid in used_voyages)]

        print(f"[INFO] 시각화 생성 완료 - 총 {len(voyage_pngs)}개 PNG 파일 생성")
        print(f"[INFO] 저장 위치: {os.path.abspath(out_dir)}")

    # ----- 요약/저장 -----
    def _build_usage_summary(self) -> Dict:
        vessel_to_vids = defaultdict(list)
        for vid, blocks in self._voyage_blocks_set.items():
            if blocks:
                vessel_to_vids[self.schedule.info(vid)["vessel_name"]].append(vid)

        lines = []
        used_count = 0
        per_vessel_stats = {}
        for vessel in [f"자항선{i}" for i in range(1, 6)]:
            vids = sorted(vessel_to_vids.get(vessel, []))
            cnt_blocks = sum(len(self._voyage_blocks_set[v]) for v in vids)
            used = len(vids)
            used_count += used
            per_vessel_stats[vessel] = {
                "voyage_count": used,
                "block_count": cnt_blocks,
                "voyages": vids or ["없음"]
            }
            vline = f"{vessel}: {used}개 항차, 총 {cnt_blocks}블록\n사용 항차:\n" + (", ".join(vids) if vids else "없음")
            lines.append(vline)

        all_lines = ["\n🗂️  항차별 사용 여부(O/X)"]
        for vessel in [f"자항선{i}" for i in range(1, 6)]:
            marks = []
            for vid in self.schedule.vessel_voyages.get(vessel, []):
                marks.append(f"{vid}[{'O' if self._voyage_blocks_set.get(vid) else 'X'}]")
            all_lines.append(f"{vessel}: " + ", ".join(marks))

        usage_summary = {
            "total_voyages": len(self.schedule.voyages),
            "used_voyages": used_count,
            "unused_voyages": len(self.schedule.voyages) - used_count,
            "per_vessel": per_vessel_stats,
            "used_list_pretty": "\n\n".join(lines),
            "used_marks_pretty": "\n".join(all_lines),
        }
        return usage_summary

    def print_and_save(self, out_json="normal_voyage_assignments.json"):
        total = len(self.normal_blocks)
        assigned = len(self.block_assignments)
        unassigned = len(self.unassigned_blocks)
        rate = (assigned / total * 100.0) if total else 0.0

        usage = self._build_usage_summary()

        print("\n==================================================")
        print("📊 Normal 블록 배정 요약")
        print("==================================================")
        print(f"총 Normal 블록: {total}")
        print(f"배정 성공: {assigned}")
        print(f"미배정: {unassigned}")
        print(f"배정률: {rate:.1f}%")
        print(f"활용된 항차 수: {usage['used_voyages']}")

        print("\n==================================================")
        print("📊 선박별 항차 사용 요약")
        print("==================================================")
        print(usage["used_list_pretty"])
        print("\n전체 항차 수 :", usage["total_voyages"])
        print("활용된 항차 수:", usage["used_voyages"])
        print("\n" + usage["used_marks_pretty"])

        payload = {
            "assignment_info": {
                "timestamp": datetime.now().isoformat(timespec="seconds"),
                "total_normal_blocks": total,
                "assigned_blocks": assigned,
                "unassigned_blocks": unassigned,
                "assignment_rate": rate,
            },
            "voyage_assignments": {vid: sorted(list(blks)) for vid, blks in self._voyage_blocks_set.items() if blks},
            "block_assignments": dict(self.block_assignments),
            "unassigned_block_list": sorted(self.unassigned_blocks),
            "usage_summary": usage,
            "voyage_used_flags": {vid: bool(self._voyage_blocks_set.get(vid)) for vid in self.schedule.voyages.keys()},
            "logs": self.logs,
        }
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"💾 저장 완료: {out_json}")

    # ----- 실행 -----
    def run(self):
        print("🚀 Normal 블록 자항선1 배정 시작")
        self.assign_on_vessel1()
        leftover = list(self.unassigned_blocks)
        print(f"   ⮑ 자항선1 미처리: {len(leftover)}개")

        print("🚀 Normal 블록 자항선2~5 배정 시작")
        if leftover:
            self.assign_on_other_vessels(leftover)

        # 요약 출력 및 JSON 저장
        self.print_and_save()
        # 최종 시각화 (확정 항차만)
        self.export_visualizations(out_dir="placement_results", max_time_per_voyage=15)


if __name__ == "__main__":
    assigner = NormalVoyageAssigner(
        schedule_csv="data/vessel_schedule_7.csv",
        deadline_csv="data/block_deadline_7.csv",
        labeling_results_file="block_labeling_results.json",
        vip_assign_file="vip_voyage_assignments.json"
    )
    assigner.run()
