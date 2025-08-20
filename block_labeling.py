#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VIP/일반 블록 라벨링 알고리즘
- 복셀 캐시 데이터 기반으로 블록 크기 분석
- 자항선별 호환성 테스트
- VIP(1척 전용) vs 일반 블록 분류
"""

import json
import os
from pathlib import Path
from placement_api import generate_config, run_placement, get_unplaced_blocks, get_available_blocks


class BlockLabeler:
    """블록 라벨링 시스템"""
    
    def __init__(self, vessel_specs=None, use_vessel_config=True):
        """
        블록 라벨러 초기화
        
        Args:
            vessel_specs: 자항선 스펙 리스트 (None이면 vessel_specs.json 사용)
            use_vessel_config: vessel_specs.json 파일 사용 여부
        """
        self.voxel_cache_dir = Path("voxel_cache")
        self.block_dimensions = {}
        self.block_data = {}
        self.compatibility_matrix = {}
        self.vip_blocks = []
        self.normal_blocks = []
        self.labeling_results = {}
        
        # 자항선 스펙 설정
        if vessel_specs is not None:
            # 사용자 정의 스펙 사용
            self.vessel_specs = vessel_specs
            print("🚢 사용자 정의 자항선 스펙 사용:")
        elif use_vessel_config:
            # vessel_specs.json 파일에서 로드
            self.vessel_specs = self._load_vessel_specs_from_file()
            print("🚢 vessel_specs.json에서 자항선 스펙 로드:")
        else:
            # 기본값 사용
            self.vessel_specs = [
                {"id": 1, "width": 100, "height": 50, "name": "대형자항선"},
                {"id": 2, "width": 80, "height": 40, "name": "중형자항선"},
                {"id": 3, "width": 60, "height": 30, "name": "소형자항선"},
            ]
            print("🚢 기본 자항선 스펙 사용:")
        
        for spec in self.vessel_specs:
            print(f"  - {spec['name']}: {spec['width']}m x {spec['height']}m")
        
        self.safety_margin = 2  # 안전 여백 (미터)
    
    def _load_vessel_specs_from_file(self, filename="vessel_specs.json"):
        """
        vessel_specs.json 파일에서 자항선 스펙 정보 로드
        
        Args:
            filename: 자항선 스펙 파일명
        
        Returns:
            list: 자항선 스펙 리스트
        """
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            vessels = data.get('vessels', [])
            vessel_specs = []
            
            for vessel in vessels:
                vessel_spec = {
                    "id": vessel.get('id'),
                    "width": vessel.get('width'),
                    "height": vessel.get('height'),
                    "name": vessel.get('name')
                }
                vessel_specs.append(vessel_spec)
                print(f"  ✅ {vessel_spec['name']}: {vessel_spec['width']}m x {vessel_spec['height']}m")
            
            metadata = data.get('metadata', {})
            if 'safety_margin' in metadata:
                self.safety_margin = metadata['safety_margin']
                print(f"  📏 안전 여백: {self.safety_margin}m")
            
            return vessel_specs
            
        except FileNotFoundError:
            print(f"  ❌ {filename} 파일을 찾을 수 없습니다. 기본값을 사용합니다.")
            return [
                {"id": 1, "width": 100, "height": 50, "name": "기본자항선"},
            ]
        except Exception as e:
            print(f"  ❌ {filename} 로드 실패: {e}. 기본값을 사용합니다.")
            return [
                {"id": 1, "width": 100, "height": 50, "name": "기본자항선"},
            ]
    
    def _load_vessel_specs_from_configs(self, config_files):
        """
        Level 1 config 파일들에서 자항선 스펙 정보 추출
        
        Args:
            config_files: config 파일 경로 리스트
        
        Returns:
            list: 자항선 스펙 리스트
        """
        vessel_specs = []
        
        for i, config_file in enumerate(config_files):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                ship_config = config.get('ship_configuration', {})
                grid_size = ship_config.get('grid_size', {})
                
                vessel_spec = {
                    "id": i + 1,
                    "width": grid_size.get('width', 80),
                    "height": grid_size.get('height', 40),
                    "name": ship_config.get('name', f'Ship_{i+1}')
                }
                
                vessel_specs.append(vessel_spec)
                print(f"  ✅ {config_file}: {vessel_spec['name']} ({vessel_spec['width']}x{vessel_spec['height']})")
                
            except Exception as e:
                print(f"  ❌ {config_file} 로드 실패: {e}")
                continue
        
        if not vessel_specs:
            print("  ⚠️ Config 파일에서 자항선 정보를 로드할 수 없어 기본값을 사용합니다.")
            return [
                {"id": 1, "width": 100, "height": 50, "name": "기본자항선"},
            ]
        
        return vessel_specs
    
    def load_block_dimensions(self):
        """복셀 캐시에서 블록 크기 정보 로드"""
        print(f"[INFO] 복셀 캐시에서 블록 크기 정보 로드 중...")
        
        json_files = list(self.voxel_cache_dir.glob("*.json"))
        print(f"[INFO] {len(json_files)}개 블록 파일 발견")
        
        for json_file in json_files:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                block_id = data["block_id"]
                dimensions = data["voxel_data"]["dimensions"]
                
                self.block_data[block_id] = {
                    "width": dimensions["width"],
                    "height": dimensions["height"],
                    "area": dimensions["width"] * dimensions["height"]
                }
                
            except Exception as e:
                print(f"[WARNING] {json_file} 로드 실패: {e}")
        
        print(f"[INFO] {len(self.block_data)}개 블록 정보 로드 완료")
        return self.block_data
    
    def test_vessel_compatibility(self, block_width, block_height, vessel_spec, safety_margin=2):
        """
        블록이 자항선에 들어갈 수 있는지 테스트 (회전 고려)
        
        Args:
            block_width: 블록 너비 (m)
            block_height: 블록 높이 (m)
            vessel_spec: 자항선 스펙 {"width": 80, "height": 40, "name": "Ship1"}
            safety_margin: 안전 여백 (m)
        
        Returns:
            bool: 호환 가능 여부
        """
        vessel_width = vessel_spec["width"]
        vessel_height = vessel_spec["height"]
        
        # 안전 여백을 고려한 실제 사용 가능 공간
        available_width = vessel_width - safety_margin
        available_height = vessel_height - safety_margin
        
        # 블록이 자항선에 들어갈 수 있는지 확인 (회전 고려)
        # 1. 원래 방향: block_width x block_height
        fits_original = (block_width <= available_width and block_height <= available_height)
        
        # 2. 90도 회전: block_height x block_width
        fits_rotated = (block_height <= available_width and block_width <= available_height)
        
        # 둘 중 하나라도 가능하면 호환
        return fits_original or fits_rotated
    
    def analyze_block_compatibility(self, safety_margin=2):
        """모든 블록의 자항선 호환성 분석"""
        print(f"[INFO] 블록-자항선 호환성 분석 중 (안전여백: {safety_margin}m)")
        
        if not self.block_data:
            self.load_block_dimensions()
        
        for block_id, block_info in self.block_data.items():
            compatible_vessels = []
            
            # 각 자항선별 호환성 테스트
            for vessel in self.vessel_specs:
                if self.test_vessel_compatibility(
                    block_info["width"], 
                    block_info["height"], 
                    vessel, 
                    safety_margin
                ):
                    compatible_vessels.append(vessel["id"])
            
            # 라벨링 결과 저장
            self.labeling_results[block_id] = {
                "block_info": block_info,
                "compatible_vessels": compatible_vessels,
                "vessel_count": len(compatible_vessels),
                "label": "VIP" if len(compatible_vessels) == 1 else "일반",
                "is_vip": len(compatible_vessels) == 1
            }
        
        print(f"[INFO] {len(self.labeling_results)}개 블록 호환성 분석 완료")
        return self.labeling_results
    
    def get_classification_summary(self):
        """분류 결과 요약"""
        if not self.labeling_results:
            self.analyze_block_compatibility()
        
        vip_blocks = []
        normal_blocks = []
        problematic_blocks = []
        
        for block_id, result in self.labeling_results.items():
            if result["vessel_count"] == 0:
                problematic_blocks.append(block_id)
            elif result["is_vip"]:
                vip_blocks.append(block_id)
            else:
                normal_blocks.append(block_id)
        
        return {
            "vip_blocks": vip_blocks,
            "normal_blocks": normal_blocks,
            "problematic_blocks": problematic_blocks,
            "summary": {
                "total": len(self.labeling_results),
                "vip_count": len(vip_blocks),
                "normal_count": len(normal_blocks),
                "problematic_count": len(problematic_blocks),
                "vip_ratio": len(vip_blocks) / len(self.labeling_results) * 100 if self.labeling_results else 0
            }
        }
    
    def print_labeling_results(self):
        """라벨링 결과 출력"""
        classification = self.get_classification_summary()
        
        print("\n" + "="*60)
        print("🏷️  블록 라벨링 결과")
        print("="*60)
        
        summary = classification["summary"]
        print(f"총 블록 수: {summary['total']}")
        print(f"VIP 블록: {summary['vip_count']}개 ({summary['vip_ratio']:.1f}%)")
        print(f"일반 블록: {summary['normal_count']}개")
        print(f"문제 블록: {summary['problematic_count']}개")
        
        # 자항선별 호환 블록 수 통계
        vessel_stats = {vessel["id"]: 0 for vessel in self.vessel_specs}
        for result in self.labeling_results.values():
            for vessel_id in result["compatible_vessels"]:
                vessel_stats[vessel_id] += 1
        
        print("\n🚢 자항선별 호환 블록 수:")
        for vessel in self.vessel_specs:
            vessel_id = vessel["id"]
            count = vessel_stats[vessel_id]
            print(f"  {vessel['name']}: {count}개")
        
        # VIP 블록 상세 (면적 순 내림차순)
        print("\n🔥 VIP 블록 상세 (자항선 1척 전용, 면적 순):")
        vip_blocks = classification["vip_blocks"]
        if vip_blocks:
            # 면적 순으로 내림차순 정렬
            vip_blocks_sorted = sorted(vip_blocks, 
                                     key=lambda x: self.labeling_results[x]["block_info"]["area"], 
                                     reverse=True)
            
            for block_id in vip_blocks_sorted[:10]:
                result = self.labeling_results[block_id]
                vessel_id = result["compatible_vessels"][0]
                vessel_name = next(v["name"] for v in self.vessel_specs if v["id"] == vessel_id)
                block_info = result["block_info"]
                area = block_info["area"]
                width = block_info["width"]
                height = block_info["height"]
                print(f"  {block_id}: {vessel_name} 전용 (크기: {width}×{height}mm, 면적: {area}㎡)")
            
            if len(vip_blocks) > 10:
                print(f"  ... 외 {len(vip_blocks)-10}개")
        else:
            print("  VIP 블록 없음")
                
    
    def save_labeling_results(self, output_file="block_labeling_results.json"):
        """라벨링 결과 저장"""
        if not self.labeling_results:
            self.analyze_block_compatibility()
        
        classification = self.get_classification_summary()
        
        output_data = {
            "analysis_info": {
                "timestamp": "2025-08-15T19:50:26+09:00",
                "total_blocks_analyzed": len(self.labeling_results),
                "vessel_specs": self.vessel_specs
            },
            "classification": classification,
            "detailed_results": self.labeling_results
        }
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
        
        print(f"\n💾 라벨링 결과 저장: {output_file}")
        return output_file
    
    def get_vip_blocks(self):
        """VIP 블록 리스트만 반환"""
        if not self.labeling_results:
            self.analyze_block_compatibility()
        
        return [block_id for block_id, result in self.labeling_results.items() if result["is_vip"]]
    
    def get_normal_blocks(self):
        """일반 블록 리스트만 반환"""
        if not self.labeling_results:
            self.analyze_block_compatibility()
        
        return [block_id for block_id, result in self.labeling_results.items() if not result["is_vip"] and result["vessel_count"] > 0]

def main():
    """메인 실행 함수"""
    print("=== VIP/일반 블록 라벨링 시스템 ===")
    
    # vessel_specs.json 파일을 사용하여 블록 라벨러 초기화
    print("\n🚢 자항선 스펙 파일(vessel_specs.json) 사용")
    labeler = BlockLabeler()
    
    # 블록 크기 정보 로드
    labeler.load_block_dimensions()
    
    # 호환성 분석 및 라벨링
    labeler.analyze_block_compatibility()
    
    # 결과 출력
    labeler.print_labeling_results()
    
    # 결과 저장
    output_file = labeler.save_labeling_results()
    
    # 간단한 활용 예제
    print("\n" + "="*60)
    print("📋 활용 예제")
    print("="*60)
    
    vip_blocks = labeler.get_vip_blocks()
    normal_blocks = labeler.get_normal_blocks()
    
    print(f"VIP 블록 개수: {len(vip_blocks)}")
    print(f"일반 블록 개수: {len(normal_blocks)}")
    

    
    print(f"\n✅ 블록 라벨링 완료!")
    print(f"📄 상세 결과: {output_file}")
    
    # 사용법 안내
    print(f"\n" + "="*60)
    print("🔧 사용법 안내")
    print("="*60)
    print("# 기본 사용법:")
    print("labeler = BlockLabeler()")
    print("labeler.analyze_block_compatibility()")
    print("vip_blocks = labeler.get_vip_blocks()")
    print("")

    
    return labeler

if __name__ == "__main__":
    labeler = main()
