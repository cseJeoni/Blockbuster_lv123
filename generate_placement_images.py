#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
배치 이미지 생성 스크립트
LV3 결과 JSON 파일을 읽어서 각 항차별 배치 이미지를 생성합니다.
"""
import json
import os
import glob
import shutil
import time
from datetime import datetime
from typing import Dict, List

# Placement_api가 없는 경우를 대비한 임포트
try:
    from Placement_api import generate_config, run_placement
except ImportError:
    print("[ERROR] Placement_api 모듈을 찾을 수 없습니다. 배치 이미지 생성을 위해 필요합니다.")
    exit(1)


class PlacementImageGenerator:
    def __init__(self, json_file_path: str = "lv3_integrated_voyage_assignments.json", 
                 output_dir: str = "placement_results"):
        self.json_file_path = json_file_path
        self.output_dir = output_dir
        self.vessel_specs = self._load_vessel_specs()
        
    def _load_vessel_specs(self) -> Dict[int, Dict]:
        """vessel_specs.json에서 자항선 스펙 로드"""
        vessel_specs_file = os.path.join(os.path.dirname(__file__), "vessel_specs.json")
        if os.path.exists(vessel_specs_file):
            try:
                with open(vessel_specs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                specs = {}
                for entry in data.get("vessels", []):
                    specs[int(entry["id"])] = {
                        "name": entry["name"],
                        "width": int(entry["width"]),
                        "height": int(entry["height"])
                    }
                if specs:
                    return specs
            except Exception as e:
                print(f"[ERROR] vessel_specs.json 로드 실패: {e}")
                raise ValueError("vessel_specs.json 파일이 필요합니다. 파일을 확인해주세요.")
        
        raise ValueError("vessel_specs.json 파일을 찾을 수 없습니다.")
    
    def _move_config_to_lv1_configs(self, cfg_path: str) -> str:
        """설정 파일을 lv1_configs 디렉토리로 이동"""
        try:
            os.makedirs("lv1_configs", exist_ok=True)
            dst = os.path.join("lv1_configs", os.path.basename(cfg_path))
            if os.path.abspath(cfg_path) != os.path.abspath(dst):
                shutil.move(cfg_path, dst)
                return dst
        except Exception as e:
            print(f"[WARN] config 이동 실패: {e}")
        return cfg_path
    
    def _parse_voyage_info(self, voyage_id: str, logs: List[str]) -> Dict:
        """항차 ID에서 항차 정보 추출"""
        # voyage_id 형식: "자항선1_2025-03-30_2025-04-10"
        parts = voyage_id.split('_')
        if len(parts) < 3:
            return None
            
        vessel_name = parts[0]
        start_date = parts[1]
        end_date = parts[2]
        
        return {
            "vessel_name": vessel_name,
            "start_date": start_date,
            "end_date": end_date
        }
    
    def generate_images(self, max_time_per_voyage: int = 60):
        """배치 이미지 생성"""
        # JSON 파일 로드
        if not os.path.exists(self.json_file_path):
            print(f"[ERROR] JSON 파일을 찾을 수 없습니다: {self.json_file_path}")
            return
        
        try:
            with open(self.json_file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] JSON 파일 로드 실패: {e}")
            return
        
        voyage_assignments = data.get("voyage_assignments", {})
        logs = data.get("assignment_info", {}).get("logs", [])
        
        if not voyage_assignments:
            print("[WARN] 항차 배정 데이터가 없습니다.")
            return
        
        # 출력 디렉토리 생성
        os.makedirs(self.output_dir, exist_ok=True)
        alt_dir = os.path.join("lv1_configs", "placement_results")
        os.makedirs(alt_dir, exist_ok=True)
        
        # 블록이 배정된 항차만 필터링
        used_voyages = [(vid, blocks) for vid, blocks in voyage_assignments.items() if blocks]
        
        if not used_voyages:
            print("[WARN] 블록이 배정된 항차가 없습니다.")
            return
        
        print(f"[INFO] {len(used_voyages)}개 항차의 배치 이미지를 생성합니다...")
        
        success_count = 0
        for vid, blocks in used_voyages:
            print(f"[INFO] 처리 중: {vid} ({len(blocks)}개 블록)")
            
            # 항차 정보 파싱
            voyage_info = self._parse_voyage_info(vid, logs)
            if not voyage_info:
                print(f"[WARN] 항차 정보 파싱 실패: {vid}")
                continue
            
            vessel_name = voyage_info["vessel_name"]
            vessel_id = int(vessel_name.replace("자항선", ""))
            
            if vessel_id not in self.vessel_specs:
                print(f"[WARN] 자항선 스펙을 찾을 수 없습니다: {vessel_name}")
                continue
            
            spec = self.vessel_specs[vessel_id]
            
            # 기존 이미지 파일 목록 저장
            before = set(glob.glob(os.path.join(self.output_dir, "*.png"))) | \
                    set(glob.glob(os.path.join(alt_dir, "*.png")))
            
            # 배치 실행
            vis_name = f"{vid}_VIS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            try:
                cfg_src = generate_config(
                    ship_name=vis_name,
                    width=spec["width"],
                    height=spec["height"],
                    block_list=blocks
                )
                cfg_moved = self._move_config_to_lv1_configs(cfg_src)
                
                run_placement(cfg_moved, max_time=max_time_per_voyage, enable_visualization=True)
                time.sleep(0.4)  # 파일 생성 대기
                
                # 새로 생성된 이미지 파일 찾기
                after = set(glob.glob(os.path.join(self.output_dir, "*.png"))) | \
                       set(glob.glob(os.path.join(alt_dir, "*.png")))
                new_files = list(after - before)
                
                if new_files:
                    # 가장 최근 파일 선택
                    newest = max(new_files, key=os.path.getmtime)
                    
                    # 목적지 파일명 생성
                    dst_name = f"{vessel_name} {voyage_info['start_date']}_{voyage_info['end_date']}.png"
                    dst_path = os.path.join(self.output_dir, dst_name)
                    
                    # 기존 파일 삭제 후 복사
                    if os.path.exists(dst_path):
                        os.remove(dst_path)
                    shutil.copy2(newest, dst_path)
                    
                    # 임시 파일 정리
                    if os.path.basename(newest).startswith("config_placement_"):
                        os.remove(newest)
                    
                    print(f"[SUCCESS] {dst_name} 생성 완료")
                    success_count += 1
                else:
                    print(f"[WARN] 이미지 파일이 생성되지 않았습니다: {vid}")
                    
            except Exception as e:
                print(f"[ERROR] 배치 이미지 생성 실패: {vid} - {e}")
        
        print(f"\n[COMPLETE] 배치 이미지 생성 완료: {success_count}/{len(used_voyages)}개 성공")
        print(f"[INFO] 이미지 저장 위치: {os.path.abspath(self.output_dir)}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="LV3 결과에서 배치 이미지 생성")
    parser.add_argument("--json", default="lv3_integrated_voyage_assignments.json", 
                       help="LV3 결과 JSON 파일 경로")
    parser.add_argument("--output", default="placement_results", 
                       help="이미지 출력 디렉토리")
    parser.add_argument("--timeout", type=int, default=60, 
                       help="항차당 최대 처리 시간(초)")
    
    args = parser.parse_args()
    
    generator = PlacementImageGenerator(
        json_file_path=args.json,
        output_dir=args.output
    )
    
    generator.generate_images(max_time_per_voyage=args.timeout)


if __name__ == "__main__":
    main()
