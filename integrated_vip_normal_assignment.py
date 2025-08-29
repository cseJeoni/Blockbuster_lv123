#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LV2 통합 배정 (합본 우선 → VIP-only 백업 → Top-off 재호출)
- VIP+Normal 합본 1회 시도 → VIP 일부 누락 시 VIP-only 백업 1회
- 이후 Top-off: 같은 항차에 대해 Normal 보강 합본을 2~3회 재호출해 적재율 상승(항차당)
- 용적률 패스 105% 고정
- 실행 단계에서도 '쿨다운' 하드가드는 상위(LV3)에서 선박별 사이클 길이로 처리
- JSON에 실행 시간/사용 항차 요약 포함
- 시각화 결과: placement_results/ "자항선N 시작이동일_하역종료일.png"
- LV1 파일(placement_api, ship_placer)은 수정하지 않음. (config는 lv1_configs/로 보관)

추가 변경(2025-08-30):
- 블록 적재 윈도우를 [due-14, due-1] 로 조정(하역은 납기 하루 전까지 완료).
- start_date는 LV3에서 실제 "처음 이동 시작" 날짜를 계산해 전달(없을 때만 보정).
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

# --- LV1 API (수정 금지) ---
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
                vid   = f'{row["vessel_name"]}_{end}'
                self.voyages[vid] = {
                    "voyage_id": vid,
                    "vessel_name": row["vessel_name"],
                    "start_date": start,
                    "end_date": end,
                }
                self.vessel_voyages[row["vessel_name"]].append(vid)

    def add_voyage(self, vessel_name: str, start_date: str, end_date: str) -> str:
        vid = f"{vessel_name}_{end_date}"
        self.voyages[vid] = {
            "voyage_id": vid,
            "vessel_name": vessel_name,
            "start_date": start_date,
            "end_date": end_date,
        }
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
    MAX_STOWAGE_DAYS = 14             # 조기 적치 허용일(2주)
    PAGE_SIZE = 18                    # (fallback) 기본 페이지 제한
    LV1_TIMEOUT = 8                  # 일반 합본 호출 타임아웃(초)
    LV1_TIMEOUT_SINGLE_WINDOW = 120   # VIP-only 등 단일창은 넉넉히
    CAPACITY_RATIO = 1.05             # 105% 고정
    TOPOFF_ROUNDS = 2                 # Top-off 재호출 라운드 수(2~3 권장)

    def __init__(self,
                 schedule_csv: Optional[str] = None,   # None이면 인메모리 스케줄
                 deadline_csv: str = "data/block_deadline_7.csv",
                 labeling_results_file: str = "block_labeling_results.json",
                 out_json: str = "integrated_voyage_assignments.json",
                 vis_out_dir: str = "placement_results"):
        self._t0 = time.time()
        self.out_json = out_json
        self.vis_out_dir = vis_out_dir
        self.schedule_source = "in_memory" if not schedule_csv else schedule_csv

        # 데이터 로드
        self.schedule = VoyageSchedule()
        if schedule_csv:
            self.schedule.load_from_csv(schedule_csv)
        else:
            print("[INFO] schedule_csv=None → 인메모리 스케줄 사용")

        self.deadlines = load_deadlines(deadline_csv)
        self.labeling  = load_labeling(labeling_results_file)

        if not isinstance(self.labeling.get("detailed_results"), dict):
            raise ValueError("[FATAL] block_labeling_results.json -> 'detailed_results'가 없습니다.")

        # VIP/Normal 분리
        vip_list = self.labeling.get("classification", {}).get("vip_blocks", [])
        all_blocks = set(self.labeling["detailed_results"].keys())
        self.vip_blocks: Set[str] = set(vip_list)
        self.normal_blocks: Set[str] = set(all_blocks - self.vip_blocks)

        # 선박 규격(파일 우선, 없으면 하드코딩)
        self.vessel_specs = self._load_vessel_specs()

        # 결과 컨테이너
        self.block_assignments: Dict[str, str] = {}          # block_id -> voyage_id
        self.voyage_blocks: Dict[str, List[str]] = defaultdict(list)
        self.logs: List[str] = []

        # 유효 항차 개수 캐시(현재는 미사용)
        self._voyage_count_cache: Dict[str, int] = {}
        self._precompute_voyage_counts()

        print("\n[DIAG] 입력 요약")
        print(f"  - VIP: {len(self.vip_blocks)}개, Normal: {len(self.normal_blocks)}개, All: {len(all_blocks)}개")

    def _load_vessel_specs(self) -> Dict[int, Dict[str, int]]:
        candidate = os.path.join(os.path.dirname(__file__), "vessel_specs.json")
        if os.path.exists(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                specs = {}
                for entry in data.get("vessels", []):
                    specs[int(entry["id"])] = {
                        "name": entry["name"],
                        "width": int(entry["width"]),
                        "height": int(entry["height"]),
                    }
                if specs:
                    return specs
            except Exception as e:
                print(f"[WARN] vessel_specs.json 로드 실패: {e}")
        # fallback
        return {
            1: {"name": "자항선1", "width": 62, "height": 170},
            2: {"name": "자항선2", "width": 36, "height": 84},
            3: {"name": "자항선3", "width": 32, "height": 120},
            4: {"name": "자항선4", "width": 40, "height": 130},
            5: {"name": "자항선5", "width": 32, "height": 116},
        }

    # ----- 메타 -----
    def _label_meta(self, block_id: str) -> Dict:
        meta = self.labeling["detailed_results"].get(block_id)
        if not isinstance(meta, dict):
            raise KeyError(f"[FATAL] 라벨 메타가 없습니다: {block_id}")
        return meta

    def _area_of(self, block_id: str) -> Optional[float]:
        meta = self._label_meta(block_id)
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
    def _window_ok(self, block_id: str, end_date: str) -> bool:
        """도착일(end_date)이 [due-14, due-1] 안이면 OK (하역은 납기 하루 전까지)"""
        due = self.deadlines.get(block_id)
        if not due:
            return False
        d_due = datetime.strptime(due, "%Y-%m-%d")
        d_end = datetime.strptime(end_date, "%Y-%m-%d")
        return (d_due - timedelta(days=self.MAX_STOWAGE_DAYS)) <= d_end <= (d_due - timedelta(days=1))

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
        all_blocks = list(self.vip_blocks | self.normal_blocks)
        for b in all_blocks:
            cnt = 0
            for vid in self.schedule.voyages.keys():
                if self._eligible_for_voyage(b, vid):
                    cnt += 1
            self._voyage_count_cache[b] = cnt

    def _count_compatible_voyages(self, block_id: str) -> int:
        return self._voyage_count_cache.get(block_id, 0)

    # ----- 선박별 페이지 제한(후보폭) -----
    def _page_limit_for_vessel(self, vessel_id: int) -> int:
        if vessel_id == 1:
            return 80   # 자항선1 넓게
        elif vessel_id in (2, 4):
            return 44
        else:
            return 40

    # ----- LV1 실행 -----
    def _move_config_to_lv1_configs(self, cfg_path: str) -> str:
        """LV1 config를 ./lv1_configs/로 이동시켜 보관."""
        try:
            os.makedirs("lv1_configs", exist_ok=True)
            dst = os.path.join("lv1_configs", os.path.basename(cfg_path))
            if os.path.abspath(cfg_path) != os.path.abspath(dst):
                shutil.move(cfg_path, dst)
                return dst
        except Exception as e:
            print(f"[WARN] config 이동 실패: {e}")
        return cfg_path

    def _run_lv1(self, block_list: List[str], voyage_id: str,
                 timeout: Optional[int] = None, enable_visual: bool = False) -> Tuple[List[str], List[str]]:
        if not block_list:
            return [], []
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]

        # 1) config 생성 → 2) lv1_configs로 이동 → 3) run_placement
        cfg_src = generate_config(
            ship_name=voyage_id, width=spec["width"], height=spec["height"], block_list=block_list
        )
        cfg = self._move_config_to_lv1_configs(cfg_src)

        result = run_placement(cfg, max_time=(timeout or self.LV1_TIMEOUT), enable_visualization=enable_visual)

        unplaced = list(result.get("unplaced_blocks", []))
        placed_count = int(result.get("placed_count", 0))
        total_count  = int(result.get("total_count", len(block_list)))
        if placed_count + len(unplaced) != total_count:
            # 안전하게 전부 미배치로 취급
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

    # ----- Top-off: 이미 배치된 집합을 유지한 채 Normal 보강 재호출 -----
    def _topoff(self, voyage_id: str, placed_seed: List[str],
                avail_vip: Set[str], avail_norm: Set[str],
                target_area: float, page_limit: int,
                rounds: int = None) -> Tuple[List[str], str]:
        rounds = rounds or self.TOPOFF_ROUNDS
        current = list(placed_seed)
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        has_vip_lock = any(b in self.vip_blocks for b in current)

        def _vip_ok(placed: List[str]) -> bool:
            if not has_vip_lock:
                return True
            vip_in_current = [b for b in current if b in self.vip_blocks]
            return set(vip_in_current).issubset(set(placed))

        for r in range(rounds):
            # 남은 Normal 후보 준비 (마감 임박/대형 우선)
            norm_pool_all = [b for b in avail_norm if self._eligible_for_voyage(b, voyage_id)]
            norm_pool_all.sort(key=lambda bid: (
                self.deadlines.get(bid, "2099-12-31"),
                -(self._area_of(bid) or 0.0)
            ))
            # 현재 배치에 없는 것만
            norm_pool = [b for b in norm_pool_all if b not in current]

            # 남은 용적 추정
            rem_area = None
            cur_area = self._sum_area(current)
            if cur_area is not None:
                rem_area = max(0.0, target_area - cur_area)

            page = self._page_limit_for_vessel(vessel_id)
            extra = self._cap_by_area_or_page(norm_pool, rem_area if rem_area is not None else target_area, page)
            if not extra:
                break  # 더 넣을 후보가 없음

            trial = current + extra
            placed_new, _ = self._run_lv1(trial, voyage_id, timeout=self.LV1_TIMEOUT)
            if _vip_ok(placed_new) and len(placed_new) > len(current):
                current = placed_new
                self.logs.append(f"[{voyage_id}] PATH=TOPOFF_R{r+1} gain=+{len(current)-len(placed_seed)}")
            else:
                # 개선이 없거나 VIP 탈락 → 이 라운드 종료
                break
        return current, ("TOPOFF" if len(current) > len(placed_seed) else "NO_TOPOFF")

    # ----- 핵심 배정 (합본 → VIP 보장 → Top-off) -----
    def _assign_for_voyage(self, voyage_id: str, avail_vip: Set[str], avail_norm: Set[str]) -> int:
        vinfo = self.schedule.info(voyage_id)
        vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
        spec = self.vessel_specs[vessel_id]
        vessel_area = spec["width"] * spec["height"]
        target_area = vessel_area * self.CAPACITY_RATIO

        page_limit = self._page_limit_for_vessel(vessel_id)

        vip_sorted  = self._sorted_candidates(voyage_id, list(avail_vip)) if vessel_id == 1 else []
        norm_sorted = self._sorted_candidates(voyage_id, list(avail_norm))

        if not vip_sorted and not norm_sorted:
            return 0

        vip_seed = self._cap_by_area_or_page(vip_sorted, target_area, page_limit)
        rem_area = None
        vip_area = self._sum_area(vip_seed)
        if vip_area is not None:
            rem_area = max(0.0, target_area - vip_area)
        normal_take = self._cap_by_area_or_page(norm_sorted, rem_area if rem_area is not None else target_area, page_limit)
        union = vip_seed + [b for b in normal_take if b not in vip_seed]

        if not union:
            return 0

        # 1) 합본 시도
        timeout_union = self.LV1_TIMEOUT_SINGLE_WINDOW if (len(vip_seed) > 0) else self.LV1_TIMEOUT
        placed_all, _ = self._run_lv1(union, voyage_id, timeout=timeout_union)
        placed_set = set(placed_all)
        vip_ok = set(vip_seed).issubset(placed_set)

        placed_final: List[str] = []
        path = "NONE"

        if placed_all and vip_ok:
            placed_final = placed_all[:]  # 합본 성공
            path = "COMBINED_OK"
        else:
            # 2) VIP-only 백업
            if vip_seed:
                placed_vip, _ = self._run_lv1(vip_seed, voyage_id, timeout=self.LV1_TIMEOUT_SINGLE_WINDOW)
                if placed_vip:
                    placed_final = placed_vip[:]
                    path = "FALLBACK_VIP_ONLY"
                else:
                    return 0
            else:
                # VIP 없고 합본도 전무 → 종료
                return 0

        # 3) Top-off 라운드 (Normal 보강 재호출)
        placed_topped, tag = self._topoff(
            voyage_id, placed_final, avail_vip, avail_norm, target_area, page_limit, rounds=self.TOPOFF_ROUNDS
        )
        if tag == "TOPOFF":
            path += "_TOPOFF"

        # 확정(여기서만 avail_* 제거)
        def confirm(blocks: List[str]) -> int:
            count = 0
            for b in blocks:
                self.block_assignments[b] = voyage_id
                self.voyage_blocks[voyage_id].append(b)
                if b in self.vip_blocks:
                    avail_vip.discard(b)
                else:
                    avail_norm.discard(b)
                count += 1
            return count

        placed_final = placed_topped
        cnt = confirm(placed_final)
        self.logs.append(f"[{voyage_id}] PATH={path} placed={cnt}")
        return cnt

    # ----- 공개: 단일 항차 실행 (LV3에서 호출) -----
    def run_for_single_voyage(self,
                              vessel_name: str,
                              end_date: str,
                              avail_vip: Set[str],
                              avail_norm: Set[str],
                              start_date: Optional[str] = None,
                              cooldown_last_end: Optional[str] = None,
                              cooldown_gap_days: int = 14) -> Dict:
        """
        지정 선박/도착일로 항차 1건을 인메모리 생성하고, 그 항차에 대해 배정을 수행.
        - avail_vip / avail_norm 은 '잔여 블록' 집합(가변 참조)
        - cooldown_last_end: 동일 선박의 직전 '하역 종료일'(end_date). 있으면 end_date >= last_end + gap 여야 허용
        - 반환: {"voyage_id", "placed_blocks", "vip_placed", "normal_placed", "path"}
        """
        # (A) 쿨다운 하드가드: end_date 기준 간격(상위에서 선박별 사이클 길이로 전달)
        if cooldown_last_end:
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            d_min = datetime.strptime(cooldown_last_end, "%Y-%m-%d") + timedelta(days=cooldown_gap_days)
            if d_end < d_min:
                return {
                    "voyage_id": f"{vessel_name}_{end_date}",
                    "placed_blocks": [],
                    "vip_placed": [],
                    "normal_placed": [],
                    "path": "SKIPPED_COOLDOWN",
                }

        # start_date 기본값(없을 때만): 보수적으로 due-14 기준
        if not start_date:
            d_end = datetime.strptime(end_date, "%Y-%m-%d")
            start_date = (d_end - timedelta(days=self.MAX_STOWAGE_DAYS)).strftime("%Y-%m-%d")

        vid = f"{vessel_name}_{end_date}"

        # 항차 등록(배치 0이면 롤백)
        new_added = False
        if vid not in self.schedule.voyages:
            self.schedule.add_voyage(vessel_name, start_date, end_date)
            new_added = True

        before_blocks = set(self.voyage_blocks.get(vid, []))
        before_vip = set(avail_vip)
        before_norm = set(avail_norm)

        _ = self._assign_for_voyage(vid, avail_vip, avail_norm)

        after_blocks = set(self.voyage_blocks.get(vid, []))
        placed_now = sorted(list(after_blocks - before_blocks))

        # 빈 배치면 롤백
        if not placed_now and new_added:
            info = self.schedule.info(vid)
            vname = info.get("vessel_name")
            self.schedule.voyages.pop(vid, None)
            if vname and vname in self.schedule.vessel_voyages:
                self.schedule.vessel_voyages[vname] = [x for x in self.schedule.vessel_voyages[vname] if x != vid]
            return {
                "voyage_id": vid,
                "placed_blocks": [],
                "vip_placed": [],
                "normal_placed": [],
                "path": "ROLLBACK_EMPTY",
            }

        vip_placed = sorted([b for b in placed_now if b in before_vip])
        normal_placed = sorted([b for b in placed_now if b in before_norm])

        # 경로 파악
        path = "UNKNOWN"
        for lg in reversed(self.logs[-3:]):  # 최근 로그만 스캔
            if lg.startswith(f"[{vid}]"):
                if "COMBINED_OK" in lg and "TOPOFF" in lg:
                    path = "COMBINED_OK_TOPOFF"
                elif "COMBINED_OK" in lg:
                    path = "COMBINED_OK"
                elif "FALLBACK_VIP_ONLY" in lg and "TOPOFF" in lg:
                    path = "FALLBACK_VIP_ONLY_TOPOFF"
                elif "FALLBACK_VIP_ONLY" in lg:
                    path = "FALLBACK_VIP_ONLY"
                break

        return {
            "voyage_id": vid,
            "placed_blocks": placed_now,
            "vip_placed": vip_placed,
            "normal_placed": normal_placed,
            "path": path,
        }

    # ----- 기존: 전체 스케줄 일괄(미사용 경로) -----
    def run(self):
        avail_vip = set(self.vip_blocks)
        avail_norm = set(self.normal_blocks)
        for vessel_id in [1, 2, 3, 4, 5]:
            vname = f"자항선{vessel_id}"
            for vid in self.schedule.vessel_voyages.get(vname, []):
                if not avail_vip and not avail_norm:
                    break
                _ = self._assign_for_voyage(vid, avail_vip, avail_norm)
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
        for vessel in [f"자항선{i}" for i in range(1, 6)]:
            vids = sorted(set(vessel_to_vids.get(vessel, [])))
            per_vessel[vessel] = {
                "voyage_count": len(vids),
                "block_count": sum(len(self.voyage_blocks[v]) for v in vids),
                "voyages": vids or ["없음"],
            }

        used_voyages_list = sorted(set(vid for vid, arr in self.voyage_blocks.items() if arr))
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
        # unassigned 계산
        all_blocks = set(self.vip_blocks) | set(self.normal_blocks)
        assigned_blocks = set(self.block_assignments.keys())
        self.unassigned_blocks = sorted(list(all_blocks - assigned_blocks))

        elapsed = time.time() - self._t0
        assigned = len(self.block_assignments)
        total = len(self.vip_blocks) + len(self.normal_blocks)
        info = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": round(elapsed, 3),
            "elapsed_hms": self._fmt_hms(elapsed),
            "schedule_source": self.schedule_source,
            "total_blocks": total,
            "assigned_blocks": assigned,
            "unassigned_blocks": len(self.unassigned_blocks),
            "assignment_rate": round(assigned / total * 100, 2) if total else 0.0,
            "logs": self.logs,
        }
        out = {
            "assignment_info": info,
            "usage_summary": self._build_usage_summary(),
            "voyage_assignments": self.voyage_blocks,
            "block_assignments": self.block_assignments,
            "unassigned_block_list": self.unassigned_blocks,
        }
        with open(self.out_json, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n[SAVE] 결과 저장: {self.out_json}")

    # ----- 시각화 생성 -----
    def _glob_pngs(self, directory: str) -> Set[str]:
        try:
            return set(glob.glob(os.path.join(directory, "*.png")))
        except Exception:
            return set()

    def export_visualizations(self, out_dir: str = None, max_time_per_voyage: int = 15):
        """
        ship_placer가 생성하는 원본(config_placement_*.png)을
        - 루트 placement_results/로 복사해 "자항선N 시작이동일_하역종료일.png"로 저장
        - 원본 config_placement_*.png는 삭제
        (원본은 루트 placement_results 또는 lv1_configs/placement_results 중 어디에든 있을 수 있음)
        """
        out_dir = out_dir or self.vis_out_dir
        os.makedirs(out_dir, exist_ok=True)
        alt_dir = os.path.join("lv1_configs", "placement_results")
        os.makedirs(alt_dir, exist_ok=True)

        used_voyages = [vid for vid, arr in self.voyage_blocks.items() if arr]
        for vid in used_voyages:
            blocks = self.voyage_blocks[vid]
            if not blocks:
                continue
            vinfo = self.schedule.info(vid)
            vessel_id = int(vinfo["vessel_name"].replace("자항선", ""))
            spec = self.vessel_specs[vessel_id]

            before = self._glob_pngs(out_dir) | self._glob_pngs(alt_dir)

            vis_name = f"{vid}_VIS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            cfg_src = generate_config(
                ship_name=vis_name, width=spec["width"], height=spec["height"], block_list=blocks
            )
            cfg_moved = self._move_config_to_lv1_configs(cfg_src)

            try:
                _ = run_placement(cfg_moved, max_time=max_time_per_voyage, enable_visualization=True)
                import time as _t; _t.sleep(0.4)
                after = self._glob_pngs(out_dir) | self._glob_pngs(alt_dir)
                new_files = list(after - before)
                if new_files:
                    newest = max(new_files, key=os.path.getmtime)
                    start = vinfo["start_date"]
                    end = vinfo["end_date"]
                    dst_name = f"{vinfo['vessel_name']} {start}_{end}.png"
                    dst = os.path.join(out_dir, dst_name)
                    if os.path.exists(dst):
                        os.remove(dst)
                    shutil.copy2(newest, dst)
                    try:
                        base = os.path.basename(newest)
                        if base.startswith("config_placement_"):
                            os.remove(newest)
                    except Exception as e:
                        print(f"[VIS] 원본 정리 실패: {e}")
                    print(f"[VIS] {os.path.basename(dst)} 생성")
            except Exception as e:
                print(f"[VIS] 실패: {vid} :: {e}")


def main():
    print("[WARN] 이 모듈은 LV3에서 import하여 사용하는 것이 권장됩니다.")
    print("      단독 실행 시 CSV 스케줄이 없으므로 아무 작업도 하지 않습니다.")


if __name__ == "__main__":
    main()
