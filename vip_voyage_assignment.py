#!/usr/bin/env python3
"""
VIP 블록 항차 배정 시스템
- VIP 블록을 적재일 기준으로 최적 항차에 배정
- 묶음 배치 시도 후 Level 1 시뮬레이션으로 검증
"""

import json
import csv
from datetime import datetime
from typing import Dict, List, Tuple
from collections import defaultdict

from placement_api import generate_config, run_placement, get_unplaced_blocks


class VoyageSchedule:
    def __init__(self):
        self.voyages = {}
        self.vessel_schedules = defaultdict(list)

    def load_from_csv(self, csv_file: str):
        with open(csv_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                start_date = self._convert_date_format(row['start_date'])
                end_date = self._convert_date_format(row['end_date'])
                voyage_id = f"{row['vessel_name']}_{row['end_date']}"
                self.voyages[voyage_id] = {
                    "voyage_id": voyage_id,
                    "vessel_name": row['vessel_name'],
                    "start_date": start_date,
                    "end_date": end_date,
                    "assigned_blocks": [],
                    "total_area": 0
                }
                self.vessel_schedules[row['vessel_name']].append(voyage_id)
        print(f"📅 항차 스케줄 로드 완료: {len(self.voyages)}개 항차")

    def _convert_date_format(self, date_str: str) -> str:
        if len(date_str) == 6:
            year = int('20' + date_str[:2])
            month = int(date_str[2:4])
            day = int(date_str[4:6])
            return f"{year:04d}-{month:02d}-{day:02d}"
        return date_str

    def get_voyage_info(self, voyage_id: str) -> Dict:
        return self.voyages.get(voyage_id, {})

    def get_vessel_voyages(self, vessel_name: str) -> List[str]:
        return self.vessel_schedules.get(vessel_name, [])


class VIPVoyageAssigner:
    def __init__(self,
                 labeling_results_file: str = "block_labeling_results.json",
                 schedule_file: str = "data/vessel_schedule_7.csv",
                 deadline_file: str = "data/block_deadline_7.csv"):
        self.labeling_results = self._load_labeling_results(labeling_results_file)
        self.voyage_schedule = VoyageSchedule()
        self.voyage_schedule.load_from_csv(schedule_file)
        self.block_deadlines = self._load_block_deadlines(deadline_file)
        self.vip_blocks = self._extract_vip_blocks()
        self.vessel_id_to_name = {1: "자항선1", 2: "자항선2", 3: "자항선3", 4: "자항선4", 5: "자항선5"}
        self.vessel_specs = {
            1: {'name': '자항선1', 'width': 62, 'height': 170},
            2: {'name': '자항선2', 'width': 36, 'height': 84},
            3: {'name': '자항선3', 'width': 32, 'height': 120},
            4: {'name': '자항선4', 'width': 40, 'height': 130},
            5: {'name': '자항선5', 'width': 32, 'height': 116}
        }
        self.voyage_assignments = {}
        self.block_assignments = {}
        self.unassigned_vip_blocks = []

        print(f"🎯 VIP 블록 {len(self.vip_blocks)}개 로드 완료")
        print(f"📅 총 {len(self.voyage_schedule.voyages)}개 항차 로드 완료")

    def _load_labeling_results(self, file_path: str) -> Dict:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _load_block_deadlines(self, file_path: str) -> Dict:
        deadlines = {}
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                d = row['deadline']
                if len(d) == 6:
                    year = int('20' + d[:2])
                    month = int(d[2:4])
                    day = int(d[4:6])
                    d = datetime(year, month, day).strftime('%Y-%m-%d')
                deadlines[row['block_id']] = d
        return deadlines

    def _extract_vip_blocks(self) -> List[str]:
        vip_blocks = self.labeling_results.get("classification", {}).get("vip_blocks", [])
        if vip_blocks:
            return vip_blocks
        return [bid for bid, r in self.labeling_results.items()
                if isinstance(r, dict) and r.get("vessel_count") == 1]

    def calculate_loading_days(self, block_id: str, voyage_id: str) -> float:
        try:
            deadline = datetime.strptime(self.block_deadlines[block_id], '%Y-%m-%d')
            voyage = self.voyage_schedule.get_voyage_info(voyage_id)
            end = datetime.strptime(voyage['end_date'], '%Y-%m-%d')
            diff = (deadline - end).days
            return diff if diff >= 0 else float('inf')
        except:
            return float('inf')

    def get_valid_voyages_for_block(self, block_id: str) -> List[Tuple[str, float]]:
        block = self.labeling_results.get(block_id, {})
        vessel_ids = block.get("compatible_vessels", [])
        if not vessel_ids and block_id in self.vip_blocks:
            vessel_ids = [1]

        valid_voyages = []
        for vid in vessel_ids:
            vname = self.vessel_id_to_name.get(vid)
            for voyage_id in self.voyage_schedule.get_vessel_voyages(vname):
                days = self.calculate_loading_days(block_id, voyage_id)
                if 0 <= days <= 14:
                    valid_voyages.append((voyage_id, days))
        valid_voyages.sort(key=lambda x: x[1])
        return valid_voyages

    def simulate_placement(self, block_ids: List[str], voyage_id: str) -> bool:
        if len(block_ids) == 1:
            return True
        try:
            vessel_name = self.voyage_schedule.get_voyage_info(voyage_id)['vessel_name']
            vessel_id = int(vessel_name.replace("자항선", ""))
            spec = self.vessel_specs[vessel_id]
            config = generate_config(spec['name'], spec['width'], spec['height'], block_ids)
            result = run_placement(config)
            return len(get_unplaced_blocks(result)) == 0
        except:
            return False

    def assign_vip_blocks(self):
        print("\n🚀 VIP 블록 항차 배정 시작")
        block_voyages = {}
        for b in self.vip_blocks:
            v = self.get_valid_voyages_for_block(b)
            if v:
                block_voyages[b] = v
                print(f"📋 {b}: {len(v)}개 유효 항차 → {[vid for vid, _ in v]}")
            else:
                self.unassigned_vip_blocks.append(b)
                print(f"⚠️ {b}: 유효 항차 없음")

        remaining = list(block_voyages.keys())
        while remaining:
            best_map = {b: block_voyages[b][0][0] for b in remaining if block_voyages[b]}
            voyage_groups = defaultdict(list)
            for b, v in best_map.items():
                voyage_groups[v].append(b)

            assigned = set()
            for v, blocks in voyage_groups.items():
                if self.simulate_placement(blocks, v):
                    for b in blocks:
                        self.voyage_assignments.setdefault(v, []).append(b)
                        self.block_assignments[b] = v
                        assigned.add(b)
                else:
                    for b in blocks:
                        if self.simulate_placement([b], v):
                            self.voyage_assignments.setdefault(v, []).append(b)
                            self.block_assignments[b] = v
                            assigned.add(b)

            next_remaining = []
            for b in remaining:
                if b in assigned:
                    continue
                block_voyages[b].pop(0)
                if block_voyages[b]:
                    next_remaining.append(b)
                else:
                    self.unassigned_vip_blocks.append(b)
            remaining = next_remaining

        print(f"\n✅ VIP 블록 배정 완료")
        print(f"배정 성공: {len(self.block_assignments)}개")
        print(f"배정 실패: {len(self.unassigned_vip_blocks)}개")

    def save_results(self, filename="vip_voyage_assignments.json"):
        result = {
            "voyage_assignments": self.voyage_assignments,
            "block_assignments": self.block_assignments,
            "unassigned_blocks": self.unassigned_vip_blocks,
        }
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"💾 VIP 블록 배정 결과 저장: {filename}")

    def print_summary(self):
        print("\n📊 VIP 블록 배정 요약")
        print(f"총 VIP 블록 수: {len(self.vip_blocks)}")
        print(f"배정 성공: {len(self.block_assignments)}")
        print(f"배정 실패: {len(self.unassigned_vip_blocks)}")
        print(f"📅 활용된 항차 수: {len(self.voyage_assignments)}")
        for b, v in self.block_assignments.items():
            print(f"  {b} → {v}")


def main():
    assigner = VIPVoyageAssigner()
    assigner.assign_vip_blocks()
    assigner.save_results()
    assigner.print_summary()


if __name__ == "__main__":
    main()
