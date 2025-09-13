#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Unity 시각화를 위한 ship_placer 결과 데이터 변환기
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 현재 디렉토리의 모듈들 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

from ship_placer import ShipPlacerConfig

class UnityDataExporter:
    """ship_placer 결과를 Unity에서 사용할 수 있는 형태로 변환"""
    
    def __init__(self):
        self.result_data = None
        
    def export_placement_result(self, config_path, output_path=None, max_time=30):
        """배치 결과를 Unity용 JSON으로 변환"""
        print(f"[INFO] Unity 데이터 변환 시작...")
        print(f"       Config: {config_path}")
        
        # ship_placer 실행
        placer = ShipPlacerConfig(config_path, verbose=False)
        result = placer.place_blocks(placer.create_blocks_from_config(), max_time)
        
        if not result:
            print("[ERROR] 배치 결과가 없습니다")
            return None
            
        # Unity용 데이터 생성
        unity_data = self._convert_to_unity_format(result, placer.config)
        
        # 출력 경로 설정
        if output_path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"unity_placement_data_{timestamp}.json"
            
        # JSON 저장
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(unity_data, f, indent=2, ensure_ascii=False)
            
        print(f"[SUCCESS] Unity 데이터 변환 완료: {output_path}")
        print(f"          배치된 블록: {len(unity_data['placed_blocks'])}/{unity_data['placement_stats']['total_blocks']}")
        
        return output_path
    
    def _convert_to_unity_format(self, result, config):
        """ship_placer 결과를 Unity 형식으로 변환"""
        
        # 선박 정보
        ship_info = {
            "name": config['ship_configuration']['name'],
            "dimensions": {
                "width_m": result.ship_width_m,
                "height_m": result.ship_height_m,
                "grid_unit": result.grid_resolution
            },
            "grid_size": {
                "width": result.width,
                "height": result.height
            },
            "constraints": {
                "bow_clearance": result.bow_clearance,
                "stern_clearance": result.stern_clearance,
                "block_spacing": result.block_spacing
            }
        }
        
        # 배치된 블록들 변환
        placed_blocks = []
        for block in result.placed_blocks.values():
            if block.position is None:
                continue
            
            # 복셀라이저 방향 정보 가져오기    
            voxelizer_orientation = self._get_voxelizer_orientation(block.id)
                
            block_data = {
                "id": block.id,
                "type": block.block_type,
                "position": {
                    "x": block.position[0],
                    "y": block.position[1],
                    "z": 0  # 2D 배치이므로 Z는 0
                },
                "dimensions": {
                    "width": block.width,
                    "height": block.height
                },
                "rotation": block.rotation,
                "voxel_footprint": self._get_block_footprint(block),
                "voxelizer_info": {
                    "selected_orientation": voxelizer_orientation,
                    "optimized_for_floor_contact": voxelizer_orientation != "original"
                },
                "unity_transform": self._calculate_unity_transform(block, result, voxelizer_orientation)
            }
            placed_blocks.append(block_data)
        
        # 배치되지 못한 블록들
        unplaced_blocks = []
        for block_id, block in result.unplaced_blocks.items():
            unplaced_data = {
                "id": block.id,
                "type": block.block_type,
                "dimensions": {
                    "width": block.width,
                    "height": block.height
                },
                "reason": "placement_failed"
            }
            unplaced_blocks.append(unplaced_data)
        
        # 애니메이션 순서 (배치 순서)
        animation_sequence = []
        for i, block_data in enumerate(placed_blocks):
            animation_sequence.append({
                "step": i,
                "block_id": block_data["id"],
                "delay": i * 0.5,  # 0.5초 간격
                "duration": 1.0    # 1초 배치 애니메이션
            })
        
        unity_data = {
            "export_info": {
                "timestamp": datetime.now().isoformat(),
                "source": "ship_placer_backtracking",
                "version": "1.0"
            },
            "ship_info": ship_info,
            "placement_stats": {
                "total_blocks": len(placed_blocks) + len(unplaced_blocks),
                "placed_count": len(placed_blocks),
                "unplaced_count": len(unplaced_blocks),
                "success_rate": len(placed_blocks) / (len(placed_blocks) + len(unplaced_blocks)) * 100,
                "placement_time": getattr(result, 'placement_time', 0)
            },
            "placed_blocks": placed_blocks,
            "unplaced_blocks": unplaced_blocks,
            "animation_sequence": animation_sequence
        }
        
        return unity_data
    
    def _get_voxelizer_orientation(self, block_id):
        """복셀라이저 캐시에서 선택된 방향 정보 가져오기"""
        try:
            import os
            cache_path = os.path.join("voxel_cache", f"{block_id}.json")
            
            if not os.path.exists(cache_path):
                print(f"[WARNING] 복셀 캐시 파일 없음: {cache_path}")
                return "original"
            
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # 복셀 데이터에서 방향 정보 추출
            if "voxel_data" in cache_data and "selected_orientation" in cache_data["voxel_data"]:
                orientation = cache_data["voxel_data"]["selected_orientation"]
                print(f"[INFO] 블록 {block_id} 복셀라이저 방향: {orientation}")
                return orientation
            else:
                print(f"[WARNING] 블록 {block_id} 방향 정보 없음 - 기본값 사용")
                return "original"
                
        except Exception as e:
            print(f"[ERROR] 블록 {block_id} 복셀라이저 방향 읽기 실패: {e}")
            return "original"
    
    def _get_block_footprint(self, block):
        """블록의 실제 복셀 형태 정보"""
        footprint = []
        for rel_x, rel_y in block.get_footprint():
            # 블록 내 상대 좌표로 변환
            local_x = rel_x - block.min_x
            local_y = rel_y - block.min_y
            footprint.append({"x": local_x, "y": local_y})
        return footprint
    
    def _calculate_unity_transform(self, block, result, voxelizer_orientation="original"):
        """Unity에서 사용할 Transform 정보 계산"""
        pos_x, pos_y = block.position
        
        # Unity 좌표계로 변환 (Unity는 Y가 위쪽)
        unity_x = pos_x * result.grid_resolution
        unity_z = pos_y * result.grid_resolution  # 2D의 Y -> Unity의 Z
        unity_y = 5.0  # 선박 갑판 높이 - 블록이 바닥에 잠기지 않도록
        
        # 블록 중심으로 위치 조정
        center_offset_x = (block.width * result.grid_resolution) / 2
        center_offset_z = (block.height * result.grid_resolution) / 2
        
        # 복셀라이저 방향 최적화에 따른 회전값 계산
        # ship_placer의 rotation (0,1,2,3)과 별개로 복셀라이저의 방향 최적화 적용
        voxelizer_rotation = self._get_voxelizer_rotation(voxelizer_orientation)
        
        # ship_placer 회전 + 복셀라이저 방향 최적화 결합
        # ship_placer 회전은 배치 공간에서의 회전, 복셀라이저는 메시 자체의 방향 최적화
        ship_rotation_y = block.rotation * 90  # ship_placer 회전 (90도 단위)
        
        return {
            "position": {
                "x": unity_x + center_offset_x,
                "y": unity_y,
                "z": unity_z + center_offset_z
            },
            "rotation": {
                "x": voxelizer_rotation["x"],
                "y": ship_rotation_y + voxelizer_rotation["y"],  # 회전 조합
                "z": voxelizer_rotation["z"]
            },
            "scale": {
                "x": 1.0,
                "y": 1.0,
                "z": 1.0
            },
            "voxelizer_rotation": voxelizer_rotation,
            "ship_placer_rotation": ship_rotation_y
        }
    
    def _get_voxelizer_rotation(self, orientation):
        """복셀라이저 방향에 따른 Unity 회전값 반환"""
        if orientation == "X_rotated" or orientation == "yz_plane":
            # YZ 평면을 바닥으로 (Z축 중심 90도 회전)
            return {"x": 0, "y": 0, "z": 90}
        elif orientation == "Y_rotated" or orientation == "xz_plane":
            # XZ 평면을 바닥으로 (X축 중심 90도 회전)  
            return {"x": 90, "y": 0, "z": 0}
        else:  # "original" or "xy_plane"
            # XY 평면을 바닥으로 (회전 없음)
            return {"x": 0, "y": 0, "z": 0}

def main():
    if len(sys.argv) < 2:
        print("Unity 데이터 변환기")
        print("="*40)
        print("\nUsage:")
        print("  python export_unity_data.py <config.json> [output.json] [max_time]")
        print("\nExamples:")
        print("  python export_unity_data.py config.json")
        print("  python export_unity_data.py config.json unity_data.json 60")
        return
    
    config_path = sys.argv[1]
    output_path = sys.argv[2] if len(sys.argv) > 2 else None
    max_time = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    
    if not Path(config_path).exists():
        print(f"[ERROR] Config 파일을 찾을 수 없습니다: {config_path}")
        return
    
    exporter = UnityDataExporter()
    result_path = exporter.export_placement_result(config_path, output_path, max_time)
    
    if result_path:
        print(f"\n[SUCCESS] Unity 데이터 변환 완료!")
        print(f"Unity에서 {result_path} 파일을 사용하세요.")

if __name__ == "__main__":
    main()