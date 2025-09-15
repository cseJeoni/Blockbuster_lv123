#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
통합 배치 시각화기 - 일반 블록 + Stepped 블록 맞물림 배치 데모
기존 코드 수정 없이 독립적으로 동작
"""
import json
import sys
import os
import time
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from pathlib import Path
from collections import defaultdict
import warnings
from datetime import datetime

warnings.filterwarnings('ignore')
plt.rcParams['font.family'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
# 프로젝트 루트 디렉토리를 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 기존 모듈 import (수정하지 않음)
try:
    from models.voxel_block import VoxelBlock
    from models.placement_area import PlacementArea
    from algorithms.greedy_placer import GreedyPlacer
    from ship_placers.ship_placer import ShipPlacementAreaConfig, ShipPlacerConfig
    ALGORITHM_AVAILABLE = True
    print("[INFO] 기존 알고리즘 모듈 로드 성공")
except ImportError as e:
    print(f"[ERROR] 알고리즘 모듈 로드 실패: {e}")
    ALGORITHM_AVAILABLE = False

class HeightAwarePlacementVisualizer:
    """일반 블록과 높이 정보 블록을 통합 배치하는 시각화기"""
    
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self.load_config(config_path)
        self.ship_placer_config = ShipPlacerConfig(config_path) if ALGORITHM_AVAILABLE else None
        
        # 높이 정보 블록 파일 경로 (2x 스케일링된 버전 사용)
        self.height_blocks_data = {
            'block_A': 'stepped_block_A_wide_2x.json',
            'block_B': 'stepped_block_B_wide_fixed_2x.json'
        }
        
    def load_config(self, config_path):
        """설정 파일 로드"""
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def load_height_block_data(self, file_path):
        """높이 정보 블록 데이터 로드"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] 높이 정보 블록 로드 실패 ({file_path}): {e}")
            return None
    
    def separate_blocks(self, blocks):
        """블록을 일반 블록과 높이 정보 블록으로 분리"""
        regular_blocks = []
        height_block_ids = []
        
        for block in blocks:
            # 높이 정보 블록 식별 (블록 ID 또는 block_type으로 판단)
            block_id_lower = block.id.lower()
            if 'stepped' in block_id_lower or 'step' in block_id_lower or 'height' in block_id_lower:
                height_block_ids.append(block.id)
                print(f"[INFO] 높이 정보 블록 감지: {block.id}")
            else:
                regular_blocks.append(block)
                print(f"[INFO] 일반 블록: {block.id} ({getattr(block, 'block_type', 'unknown')})")
        
        return regular_blocks, height_block_ids
    
    def place_regular_blocks(self, regular_blocks, max_time=15):
        """일반 블록들을 기존 알고리즘으로 배치"""
        if not ALGORITHM_AVAILABLE or not regular_blocks:
            print("[INFO] 일반 블록이 없거나 알고리즘을 사용할 수 없습니다")
            return None
        
        print(f"[INFO] 일반 블록 {len(regular_blocks)}개를 GreedyPlacer로 배치 중...")
        
        # 기존 ship_placer의 place_blocks 메서드 사용
        result = self.ship_placer_config.place_blocks(regular_blocks, max_time=max_time)
        
        if result:
            placed_count = len(result.placed_blocks)
            total_count = placed_count + len(result.unplaced_blocks)
            print(f"[INFO] 일반 블록 배치 완료: {placed_count}/{total_count}개 성공")
        else:
            print("[ERROR] 일반 블록 배치 실패")
        
        return result
    
    def place_all_blocks_with_height_integration(self, placement_area, max_time=60):
        """일반 블록과 높이 정보 블록을 통합해서 GreedyPlacer로 배치"""
        # 기존 ship_placer에서 일반 블록들 가져오기
        all_blocks = self.ship_placer_config.create_blocks_from_config()
        regular_blocks, height_block_ids = self.separate_blocks(all_blocks)
        print(f"[INFO] 일반 블록 {len(regular_blocks)}개, 높이 정보 블록 ID {len(height_block_ids)}개 발견")
        
        # 높이 정보 블록들 생성
        height_blocks = []
        
        # Block B 먼저 추가 (B → A 순서로 배치되도록)
        block_b_data = self.load_height_block_data(self.height_blocks_data['block_B'])
        if block_b_data:
            block_b = self.create_height_block_voxels(block_b_data, "HEIGHT_BLOCK_B")
            if block_b:
                block_b.block_type = 'height_aware'
                height_blocks.append(block_b)
        
        # Block A 나중에 추가
        block_a_data = self.load_height_block_data(self.height_blocks_data['block_A'])
        if block_a_data:
            block_a = self.create_height_block_voxels(block_a_data, "HEIGHT_BLOCK_A") 
            if block_a:
                block_a.block_type = 'height_aware'
                height_blocks.append(block_a)
        
        # 통합 블록 리스트 생성 (일반 블록들 먼저, 높이 정보 블록들 나중에)
        all_blocks = regular_blocks + height_blocks
        
        if not all_blocks:
            print("[INFO] 배치할 블록이 없습니다")
            return None
            
        print(f"[INFO] 전체 블록 {len(all_blocks)}개 배치 중 (일반: {len(regular_blocks)}, 높이 정보: {len(height_blocks)})")
        
        # 특별한 GreedyPlacer 생성 (stepped 블록 맞물림 허용)
        from algorithms.greedy_placer import GreedyPlacer
        
        class SteppedAwareGreedyPlacer(GreedyPlacer):
            def __init__(self, placement_area, blocks, max_time=60):
                super().__init__(placement_area, blocks, max_time)
                # 원본 can_place_block 메서드 백업
                self.original_can_place = placement_area.can_place_block
                # 새로운 메서드로 교체
                placement_area.can_place_block = self.can_place_stepped_interlocking
            
            def can_place_stepped_interlocking(self, block, pos_x, pos_y):
                """stepped 블록끼리의 맞물림 허용 배치 검사"""
                if not hasattr(block, 'block_type') or block.block_type != 'stepped':
                    return self.original_can_place(block, pos_x, pos_y)
                
                # stepped 블록의 경우 다른 stepped 블록과는 맞물림 허용
                footprint = block.get_footprint()
                ref_x, ref_y = block.actual_reference
                
                for vx, vy in footprint:
                    cell_x = pos_x + vx - ref_x
                    cell_y = pos_y + vy - ref_y
                    
                    # 경계 체크
                    if (cell_x < 0 or cell_x >= self.placement_area.width or
                        cell_y < 0 or cell_y >= self.placement_area.height):
                        return False
                    
                    # 일반 블록과의 충돌만 체크 (stepped 블록끼리는 맞물림 허용)
                    existing_block_id = self.placement_area.grid[cell_y, cell_x]
                    if existing_block_id is not None:
                        # 기존 블록이 stepped인지 확인
                        if existing_block_id in self.placement_area.placed_blocks:
                            existing_block = self.placement_area.placed_blocks[existing_block_id]
                            if hasattr(existing_block, 'block_type') and existing_block.block_type == 'stepped':
                                continue  # stepped끼리는 맞물림 허용
                        return False  # 일반 블록과는 충돌 불허
                
                return True
        
        # Stepped-aware GreedyPlacer로 배치
        placer = SteppedAwareGreedyPlacer(placement_area, all_blocks, max_time)
        result = placer.place_all_blocks()
        
        if result:
            placed_count = len(placement_area.placed_blocks)
            total_count = len(all_blocks)
            print(f"[INFO] 통합 블록 배치 완료: {placed_count}/{total_count}개 성공")
        
        return placement_area

    def create_height_block_voxels(self, block_data, block_id):
        """높이 정보 블록 데이터를 VoxelBlock 형태로 변환"""
        if not block_data:
            return None
        
        voxel_data = []
        if 'voxel_positions' in block_data['voxel_data']:
            for pos in block_data['voxel_data']['voxel_positions']:
                x, y, height_info = pos[0], pos[1], pos[2]
                # 높이 데이터 정규화: [empty_below, filled, empty_above] → [empty_below, filled]
                if len(height_info) == 3:
                    height_info = [height_info[0], height_info[1]]
                voxel_data.append((x, y, height_info))
        
        # VoxelBlock 생성
        block = VoxelBlock(block_id, voxel_data)
        block.block_type = 'height_aware'
        return block
    
    def find_empty_space(self, placement_area, block_width, block_height):
        """빈 공간 찾기 (오른쪽 위쪽 우선, 기존 블록과만 이격거리 적용)"""
        area_width = placement_area.width
        area_height = placement_area.height
        block_spacing = getattr(placement_area, 'block_spacing', 4)
        
        # 기존 블록들이 차지하는 영역 구분
        regular_occupied = set()  # 일반 블록 + 이격거리
        stepped_occupied = set()  # Stepped 블록 (이격거리 없음)
        
        for block_id, block in placement_area.placed_blocks.items():
            if block.position is not None:
                pos_x, pos_y = block.position
                ref_x, ref_y = block.actual_reference
                
                for vx, vy in block.get_footprint():
                    cell_x = pos_x + vx - ref_x
                    cell_y = pos_y + vy - ref_y
                    
                    # Stepped 블록인지 확인
                    is_stepped = getattr(block, 'block_type', '') == 'stepped' or 'STEPPED' in block_id
                    
                    if is_stepped:
                        # Stepped 블록: 이격거리 없이 실제 점유 영역만
                        stepped_occupied.add((cell_x, cell_y))
                    else:
                        # 일반 블록: 이격거리 포함
                        for dx in range(-block_spacing, block_spacing + 1):
                            for dy in range(-block_spacing, block_spacing + 1):
                                regular_occupied.add((cell_x + dx, cell_y + dy))
        
        print(f"[INFO] 일반 블록 차지 영역 (이격거리 포함): {len(regular_occupied)} 셀")
        print(f"[INFO] Stepped 블록 차지 영역 (이격거리 없음): {len(stepped_occupied)} 셀")
        
        # 오른쪽 위쪽부터 검색 (x는 큰 값부터, y는 작은 값부터)
        for y in range(0, area_height - block_height + 1, 3):  # 위쪽부터 3칸씩
            for x in range(area_width - block_width, -1, -3):  # 오른쪽부터 3칸씩
                # 해당 영역 확인
                clear = True
                for check_x in range(x, x + block_width):
                    for check_y in range(y, y + block_height):
                        # 일반 블록과는 이격거리 적용 (겹침 금지)
                        if (check_x, check_y) in regular_occupied:
                            clear = False
                            break
                        # Stepped 블록과는 실제 점유만 확인 (겹침 금지하되 맞물림은 허용)
                        if (check_x, check_y) in stepped_occupied:
                            clear = False
                            break
                    if not clear:
                        break
                
                if clear:
                    return (x, y)
        
        return None
    
    def place_stepped_blocks_demo(self, placement_area):
        """Stepped 블록들을 빈 공간에 배치 (오른쪽 위쪽 우선)"""
        stepped_blocks = {}
        area_width = placement_area.width
        area_height = placement_area.height
        
        print(f"[INFO] 배치 영역: {area_width} x {area_height}")
        
        # 2x 스케일링된 블록 크기
        stepped_width = 36
        stepped_height = 20
        
        # Block B 위치 찾기 (B → A 순서)
        block_b_pos = self.find_empty_space(placement_area, stepped_width, stepped_height)
        
        if not block_b_pos:
            print("[ERROR] Block B를 배치할 빈 공간을 찾을 수 없습니다")
            return stepped_blocks
        
        print(f"[INFO] Block B 빈 공간 발견: {block_b_pos}")
        
        # Block B 배치
        block_b_data = self.load_stepped_block_data(self.stepped_blocks_data['block_B'])
        if block_b_data:
            block_b = self.create_stepped_block_voxels(block_b_data, "STEPPED_B")
            if block_b:
                block_b.position = block_b_pos
                stepped_blocks["STEPPED_B"] = block_b
                print(f"[INFO] Stepped Block B 배치: {block_b.position}")
        
        # Block B가 배치된 상태에서 Block A 위치 찾기
        # placement_area의 placed_blocks를 직접 참조 (clone 에러 방지)
        current_placed_blocks = placement_area.placed_blocks.copy()
        if "STEPPED_B" in stepped_blocks:
            current_placed_blocks["STEPPED_B"] = stepped_blocks["STEPPED_B"]
        
        # 맞물림 시도 (Block B 바로 오른쪽)
        block_a_pos = None
        interlocking_x = block_b_pos[0] + stepped_width
        
        if interlocking_x + stepped_width <= area_width:
            # 맞물림 위치에서 일반 블록과의 충돌만 확인 (stepped 블록끼리는 맞물림 허용)
            interlocking_clear = True
            
            # 일반 블록과의 이격거리만 확인
            regular_occupied = set()
            for block_id, block in current_placed_blocks.items():
                if block.position is not None and not ('STEPPED' in block_id or getattr(block, 'block_type', '') == 'stepped'):
                    pos_x, pos_y = block.position
                    ref_x, ref_y = block.actual_reference
                    block_spacing = getattr(placement_area, 'block_spacing', 4)
                    
                    for vx, vy in block.get_footprint():
                        cell_x = pos_x + vx - ref_x
                        cell_y = pos_y + vy - ref_y
                        for dx in range(-block_spacing, block_spacing + 1):
                            for dy in range(-block_spacing, block_spacing + 1):
                                regular_occupied.add((cell_x + dx, cell_y + dy))
            
            # 맞물림 위치에서 일반 블록과의 충돌 확인
            for check_x in range(interlocking_x, interlocking_x + stepped_width):
                for check_y in range(block_b_pos[1], block_b_pos[1] + stepped_height):
                    if (check_x, check_y) in regular_occupied:
                        interlocking_clear = False
                        break
                if not interlocking_clear:
                    break
            
            if interlocking_clear:
                block_a_pos = (interlocking_x, block_b_pos[1])
                print(f"[INFO] Block A 맞물림 배치 성공: {block_a_pos}")
            else:
                print(f"[INFO] 맞물림 위치에 일반 블록과 충돌, 개별 배치 시도")
        
        # 맞물림 실패시 개별 위치 찾기
        if not block_a_pos:
            block_a_pos = self.find_empty_space(placement_area, stepped_width, stepped_height)
            if block_a_pos:
                print(f"[INFO] Block A 개별 배치: {block_a_pos}")
            else:
                print(f"[WARNING] Block A 개별 배치 위치도 찾을 수 없음")
        
        # Block A 배치
        if block_a_pos:
            block_a_data = self.load_stepped_block_data(self.stepped_blocks_data['block_A'])
            if block_a_data:
                block_a = self.create_stepped_block_voxels(block_a_data, "STEPPED_A")
                if block_a:
                    block_a.position = block_a_pos
                    stepped_blocks["STEPPED_A"] = block_a
                    print(f"[INFO] Stepped Block A 배치: {block_a.position}")
                    
                    # 맞물림 여부 확인
                    if abs(block_a_pos[0] - block_b_pos[0] - stepped_width) <= 1 and block_a_pos[1] == block_b_pos[1]:
                        print(f"[INFO] B→A 맞물림 배치 성공!")
                    else:
                        print(f"[INFO] B→A 개별 배치")
        else:
            print("[WARNING] Block A를 배치할 빈 공간을 찾을 수 없습니다")
        
        return stepped_blocks
    
    def place_stepped_blocks_with_proper_spacing(self, placement_area):
        """Stepped 블록들을 기존 블록과는 적절한 이격거리, stepped끼리는 밀착 배치"""
        stepped_blocks = {}
        
        # Stepped 블록 크기 정보
        stepped_width = 36  # 2x scaled
        stepped_height = 20  # 2x scaled
        
        area_width = placement_area.width
        area_height = placement_area.height
        
        print(f"[INFO] Stepped 블록 배치 영역: {area_width}x{area_height}")
        
        # 1. Block B 위치 찾기 (기존 블록들과 적절한 이격거리 유지)
        block_b_pos = self.find_position_with_proper_spacing(placement_area, stepped_width, stepped_height)
        
        if not block_b_pos:
            print("[WARNING] Block B 적절한 배치 위치를 찾을 수 없음")
            return stepped_blocks
        
        # 2. Block B 생성 및 배치
        block_b_data = self.load_stepped_block_data(self.stepped_blocks_data['block_B'])
        if block_b_data:
            block_b = self.create_stepped_block_voxels(block_b_data, "STEPPED_B")
            if block_b:
                block_b.position = block_b_pos
                stepped_blocks["STEPPED_B"] = block_b
                print(f"[INFO] Stepped Block B 배치: {block_b_pos}")
        
        # 3. Block A를 Block B 바로 옆에 밀착 배치
        block_a_pos = None
        interlocking_x = block_b_pos[0] + stepped_width  # B 바로 옆
        interlocking_y = block_b_pos[1]  # 같은 Y 위치
        
        # 영역 경계 확인
        if interlocking_x + stepped_width <= area_width:
            block_a_pos = (interlocking_x, interlocking_y)
            print(f"[INFO] Block A를 Block B 바로 옆에 밀착 배치: {block_a_pos}")
        else:
            print("[WARNING] Block A 밀착 배치 위치가 영역을 벗어남")
            # 아래쪽에 배치 시도
            interlocking_y_below = block_b_pos[1] + stepped_height
            if interlocking_y_below + stepped_height <= area_height:
                block_a_pos = (block_b_pos[0], interlocking_y_below)
                print(f"[INFO] Block A를 Block B 아래에 밀착 배치: {block_a_pos}")
        
        # 4. Block A 생성 및 배치
        if block_a_pos:
            block_a_data = self.load_stepped_block_data(self.stepped_blocks_data['block_A'])
            if block_a_data:
                block_a = self.create_stepped_block_voxels(block_a_data, "STEPPED_A")
                if block_a:
                    block_a.position = block_a_pos
                    stepped_blocks["STEPPED_A"] = block_a
                    print(f"[INFO] Stepped Block A 배치: {block_a_pos}")
        else:
            print("[WARNING] Block A 배치 위치를 찾을 수 없음")
        
        return stepped_blocks
    
    def find_position_with_proper_spacing(self, placement_area, block_width, block_height):
        """기존 블록들과 적절한 이격거리를 유지하는 위치 찾기"""
        block_spacing = getattr(placement_area, 'block_spacing', 4)
        
        # 배치된 블록들로부터 금지된 영역 계산
        forbidden_area = set()
        for block_id, block in placement_area.placed_blocks.items():
            if block.position is not None:
                pos_x, pos_y = block.position
                ref_x, ref_y = block.actual_reference
                
                for vx, vy in block.get_footprint():
                    cell_x = pos_x + vx - ref_x
                    cell_y = pos_y + vy - ref_y
                    
                    # 블록 영역과 이격거리 영역 모두 금지
                    for dx in range(-block_spacing, block_spacing + 1):
                        for dy in range(-block_spacing, block_spacing + 1):
                            forbidden_x = cell_x + dx
                            forbidden_y = cell_y + dy
                            if (0 <= forbidden_x < placement_area.width and 
                                0 <= forbidden_y < placement_area.height):
                                forbidden_area.add((forbidden_x, forbidden_y))
        
        # 가능한 위치 찾기 (큰 x, 작은 y 우선)
        for y in range(placement_area.height - block_height + 1):
            for x in range(placement_area.width - block_width, -1, -1):  # 큰 x부터
                # 해당 위치에 블록을 배치할 수 있는지 확인
                can_place = True
                for bx in range(block_width):
                    for by in range(block_height):
                        if (x + bx, y + by) in forbidden_area:
                            can_place = False
                            break
                    if not can_place:
                        break
                
                if can_place:
                    return (x, y)
        
        return None
    
    def create_merged_height_block(self):
        """높이 정보 Block A와 B를 하나의 통합 VoxelBlock으로 결합"""
        # Block A와 B 데이터 로드
        block_a_data = self.load_height_block_data(self.height_blocks_data['block_A'])
        block_b_data = self.load_height_block_data(self.height_blocks_data['block_B'])
        
        if not block_a_data or not block_b_data:
            print("[ERROR] 높이 정보 블록 데이터를 로드할 수 없음")
            return None
        
        print("[INFO] 높이 정보 Block A+B 통합 시작...")
        
        # Block B의 voxel 데이터 (원점에서 시작)
        merged_voxels = []
        b_voxels = block_b_data['voxel_data']['voxel_positions']
        
        for voxel in b_voxels:
            x, y, height_info = voxel[0], voxel[1], voxel[2]
            if len(height_info) == 3:
                height_info = [height_info[0], height_info[1]]  # [empty_below, filled]
            merged_voxels.append((x, y, height_info))
        
        print(f"[INFO] Block B voxels: {len(merged_voxels)}개")
        
        # Block A의 voxel 데이터 (Block B 오른쪽에 붙여서 배치)
        a_voxels = block_a_data['voxel_data']['voxel_positions'] 
        b_width = 36  # 2x scaled width
        
        for voxel in a_voxels:
            x, y, height_info = voxel[0], voxel[1], voxel[2]
            if len(height_info) == 3:
                height_info = [height_info[0], height_info[1]]  # [empty_below, filled]
            # A를 B의 오른쪽에 붙임
            merged_voxels.append((x + b_width, y, height_info))
        
        print(f"[INFO] Block A voxels: {len(a_voxels)}개, 총 통합: {len(merged_voxels)}개")
        
        # VoxelBlock 생성
        from models.voxel_block import VoxelBlock
        merged_block = VoxelBlock("HEIGHT_MERGED", merged_voxels)
        
        # 메타데이터 설정
        merged_block.block_type = 'height_aware_merged'
        merged_block.component_blocks = {
            'block_A': {'offset_x': b_width, 'offset_y': 0},
            'block_B': {'offset_x': 0, 'offset_y': 0}
        }
        
        print(f"[INFO] 통합 높이 정보 블록 생성 완료: {merged_block.get_area()}개 셀")
        print(f"[INFO] 크기: {merged_block.width}x{merged_block.height}")
        
        return merged_block
    
    def visualize_height_aware_result(self, integrated_result, save_path=None, show=True):
        """통합 높이 정보 블록을 A와 B로 분리해서 시각화"""
        import matplotlib.pyplot as plt
        import matplotlib.patches as patches
        import os
        
        # save_path가 지정되지 않은 경우 기본 경로 생성
        if save_path is None:
            # LV1 내의 placement_results 디렉토리 사용
            current_dir = Path(__file__).parent
            lv1_dir = current_dir.parent
            results_dir = lv1_dir / "placement_results"
            results_dir.mkdir(exist_ok=True)
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = results_dir / f"height_aware_result_{timestamp}.png"
        
        fig, ax_main = plt.subplots(1, 1, figsize=(20, 12))
        
        placement_area = integrated_result['placement_area']
        merged_block = integrated_result['merged_height_block']
        regular_blocks = integrated_result['regular_blocks']
        
        # 전체 선박 영역
        total_width = placement_area.total_width
        total_height = placement_area.total_height
        ship_rect = patches.Rectangle((0, 0), total_width, total_height, 
                                    linewidth=3, edgecolor='navy', facecolor='lightblue', alpha=0.3)
        ax_main.add_patch(ship_rect)
        
        # 배치 가능 영역 표시
        placement_rect = patches.Rectangle((placement_area.stern_clearance, 0), 
                                         placement_area.width, placement_area.height, 
                                         linewidth=2, edgecolor='green', facecolor='lightgreen', alpha=0.2)
        ax_main.add_patch(placement_rect)
        
        # 일반 블록들 시각화 (색상 개선 적용)
        for block_id, block in regular_blocks.items():
            if block.position is not None:
                pos_x, pos_y = block.position
                ref_x, ref_y = block.actual_reference
                
                # 블록 타입에 따른 색상 선택  
                block_type = getattr(block, 'block_type', 'unknown')
                color = 'lime'  # 모든 일반 블록을 연두색으로
                
                for vx, vy in block.get_footprint():
                    cell_x = pos_x + vx - ref_x + placement_area.stern_clearance
                    cell_y = pos_y + vy - ref_y
                    
                    rect = patches.Rectangle((cell_x, cell_y), 1, 1, 
                                           linewidth=0.5, edgecolor='black', facecolor=color, alpha=0.7)
                    ax_main.add_patch(rect)
                
                # 블록 ID 표시 (ship_placer와 동일한 중심 계산 방식)
                footprint_coords = list(block.get_footprint())
                if footprint_coords:
                    min_vx = min(vx for vx, vy in footprint_coords)
                    max_vx = max(vx for vx, vy in footprint_coords)
                    min_vy = min(vy for vx, vy in footprint_coords)
                    max_vy = max(vy for vx, vy in footprint_coords)
                    
                    center_offset_x = (max_vx + min_vx) / 2 - ref_x
                    center_offset_y = (max_vy + min_vy) / 2 - ref_y
                    center_x = placement_area.stern_clearance + pos_x + center_offset_x
                    center_y = pos_y + center_offset_y
                    
                    ax_main.text(center_x, center_y, block_id, fontsize=9, fontweight='bold', 
                               color='black', ha='center', va='center',
                               bbox=dict(boxstyle='round,pad=0.4', facecolor='white', alpha=0.95, edgecolor='black', linewidth=1))
        
        # 통합 Stepped 블록을 A와 B로 분리해서 시각화
        if merged_block and merged_block.position is not None:
            pos_x, pos_y = merged_block.position
            ref_x, ref_y = merged_block.actual_reference
            
            # Block B 영역 (왼쪽)
            b_offset_x = merged_block.component_blocks['block_B']['offset_x']  # 0
            b_offset_y = merged_block.component_blocks['block_B']['offset_y']  # 0
            b_width = 36
            b_height = 20
            
            for bx in range(b_width):
                for by in range(b_height):
                    cell_x = pos_x + b_offset_x + bx - ref_x + placement_area.stern_clearance
                    cell_y = pos_y + b_offset_y + by - ref_y
                    
                    # Block B 셀이 실제로 존재하는지 확인
                    if self.is_cell_in_merged_block(merged_block, b_offset_x + bx, b_offset_y + by):
                        rect = patches.Rectangle((cell_x, cell_y), 1, 1, 
                                               linewidth=1.2, edgecolor='darkviolet', facecolor='purple', alpha=0.9)
                        ax_main.add_patch(rect)
            
            # Block A 영역 (오른쪽)
            a_offset_x = merged_block.component_blocks['block_A']['offset_x']  # 36
            a_offset_y = merged_block.component_blocks['block_A']['offset_y']  # 0
            a_width = 36
            a_height = 20
            
            for ax in range(a_width):
                for ay in range(a_height):
                    cell_x = pos_x + a_offset_x + ax - ref_x + placement_area.stern_clearance
                    cell_y = pos_y + a_offset_y + ay - ref_y
                    
                    # Block A 셀이 실제로 존재하는지 확인
                    if self.is_cell_in_merged_block(merged_block, a_offset_x + ax, a_offset_y + ay):
                        rect = patches.Rectangle((cell_x, cell_y), 1, 1, 
                                               linewidth=1.2, edgecolor='darkviolet', facecolor='purple', alpha=0.9)
                        ax_main.add_patch(rect)
            
            # 라벨 표시 (개선된 스타일)
            b_center_x = pos_x + b_offset_x + b_width//2 + placement_area.stern_clearance
            b_center_y = pos_y + b_offset_y + b_height//2
            ax_main.text(b_center_x, b_center_y, 'HEIGHT_BLOCK_B', fontsize=10, ha='center', va='center', 
                        fontweight='bold', color='white',
                        bbox=dict(boxstyle='round,pad=0.6', facecolor='darkviolet', alpha=1.0, edgecolor='white', linewidth=1))
            
            a_center_x = pos_x + a_offset_x + a_width//2 + placement_area.stern_clearance
            a_center_y = pos_y + a_offset_y + a_height//2
            ax_main.text(a_center_x, a_center_y, 'HEIGHT_BLOCK_A', fontsize=10, ha='center', va='center', 
                        fontweight='bold', color='white',
                        bbox=dict(boxstyle='round,pad=0.6', facecolor='darkviolet', alpha=1.0, edgecolor='white', linewidth=1))
        
        # 축 설정
        ax_main.set_xlim(-5, total_width + 5)
        ax_main.set_ylim(-5, total_height + 5)
        ax_main.set_xlabel('X (Grid)')
        ax_main.set_ylabel('Y (Grid)')
        ax_main.set_title('Height-Aware Block Placement Result (Height-Aware=Purple, Regular=Lime)', fontsize=16)
        ax_main.grid(True, alpha=0.3)
        ax_main.set_aspect('equal')
        
        plt.tight_layout()
        
        # 항상 저장 (save_path가 항상 설정되어 있음)
        plt.savefig(save_path, dpi=300, bbox_inches='tight')
        print(f"[INFO] 시각화 결과 저장: {save_path}")
        
        if show:
            plt.show()
    
    def is_cell_in_merged_block(self, merged_block, rel_x, rel_y):
        """통합 블록에서 상대 좌표 (rel_x, rel_y)에 실제 셀이 있는지 확인"""
        footprint = merged_block.get_footprint()
        ref_x, ref_y = merged_block.actual_reference
        
        for vx, vy in footprint:
            if (vx - ref_x) == rel_x and (vy - ref_y) == rel_y:
                return True
        return False
    
    def integrate_results(self, regular_result, stepped_blocks):
        """일반 블록 배치 결과와 stepped 블록을 통합"""
        if not regular_result:
            # 일반 블록이 없는 경우, 빈 결과 생성
            area = ShipPlacementAreaConfig(self.config)
            
            # PlacementResult 유사 객체 생성
            class EmptyResult:
                def __init__(self, area):
                    self.placed_blocks = {}
                    self.unplaced_blocks = []
                    self.placement_time = 0.0
                    self.placement_order = []
                    
                    # 영역 정보 복사
                    self.width = area.width
                    self.height = area.height
                    self.total_width = area.total_width  
                    self.total_height = area.total_height
                    self.bow_clearance = area.bow_clearance
                    self.stern_clearance = area.stern_clearance
                    self.block_spacing = area.block_spacing
                    self.grid_unit = area.grid_unit
                    self.grid_resolution = area.grid_resolution
            
            regular_result = EmptyResult(area)
        
        # Stepped 블록들을 결과에 추가
        for block_id, block in stepped_blocks.items():
            regular_result.placed_blocks[block_id] = block
        
        # 배치 순서에 stepped 블록들 추가
        next_order = len(regular_result.placement_order) + 1
        for block_id in stepped_blocks.keys():
            regular_result.placement_order.append((block_id, next_order))
            next_order += 1
        
        print(f"[INFO] 통합 결과: 총 {len(regular_result.placed_blocks)}개 블록")
        
        return regular_result
    
    def visualize_integrated_result(self, integrated_result, save_path=None, show=True):
        """통합 결과를 ship_placer 스타일로 시각화"""
        fig, ax_main = plt.subplots(1, 1, figsize=(20, 12))
        
        # 전체 선박 영역
        total_width = integrated_result.total_width
        total_height = integrated_result.total_height
        ship_rect = patches.Rectangle((0, 0), total_width, total_height, 
                                    linewidth=3, edgecolor='navy', facecolor='lightblue', alpha=0.3)
        ax_main.add_patch(ship_rect)
        
        # 배치 가능 영역 표시
        placement_rect = patches.Rectangle((integrated_result.stern_clearance, 0), 
                                         integrated_result.width, integrated_result.height, 
                                         linewidth=2, edgecolor='green', facecolor='lightgreen', alpha=0.2)
        ax_main.add_patch(placement_rect)
        
        # 여백 영역 표시
        if integrated_result.bow_clearance > 0:
            bow_rect = patches.Rectangle((total_width - integrated_result.bow_clearance, 0), 
                                       integrated_result.bow_clearance, total_height, 
                                       linewidth=2, edgecolor='red', facecolor='red', alpha=0.2)
            ax_main.add_patch(bow_rect)
        if integrated_result.stern_clearance > 0:
            stern_rect = patches.Rectangle((0, 0), integrated_result.stern_clearance, total_height, 
                                         linewidth=2, edgecolor='purple', facecolor='purple', alpha=0.2)
            ax_main.add_patch(stern_rect)
        
        # 블록 색상 매핑 (ship_placer와 동일 + 높이 정보 블록 추가)
        type_colors = {
            'crane': 'lime',         # 연두색으로 변경
            'trestle': 'lime',       # 연두색으로 변경  
            'height_aware': 'purple', # 높이 정보 블록을 자주색으로 변경 (더 구분되도록)
            'stepped': 'purple',     # 호환성을 위해 유지
            'unknown': 'lime'        # 기본값도 연두색으로
        }
        
        placed_blocks_list = list(integrated_result.placed_blocks.values())
        
        # 배치 순서 정보 딕셔너리
        placement_order_dict = {block_id: order_num for block_id, order_num in integrated_result.placement_order}
        
        # 블록 시각화
        for block in placed_blocks_list:
            if block.position is None:
                continue
                
            pos_x, pos_y = block.position
            block_type = getattr(block, 'block_type', 'unknown')
            color = type_colors.get(block_type, 'gray')
            
            # 실제 복셀 기준 좌표 변환 (ship_placer와 동일한 방식)
            ref_x, ref_y = block.actual_reference
            for rel_x, rel_y in block.get_footprint():
                abs_x = integrated_result.stern_clearance + pos_x + rel_x - ref_x
                abs_y = pos_y + rel_y - ref_y
                
                # Stepped 블록인 경우 특별한 시각적 스타일
                if block_type == 'stepped':
                    cell_rect = patches.Rectangle((abs_x, abs_y), 1, 1, 
                                                linewidth=1.2, edgecolor='darkviolet', 
                                                facecolor=color, alpha=0.9)
                else:
                    cell_rect = patches.Rectangle((abs_x, abs_y), 1, 1, 
                                                linewidth=0.5, edgecolor='black', 
                                                facecolor=color, alpha=0.7)
                ax_main.add_patch(cell_rect)
            
            # 블록 중심 위치 계산 (더 정확한 방식)
            # 블록의 실제 크기 기반 중심 계산
            block_width = getattr(block, 'width', 1)
            block_height = getattr(block, 'height', 1)
            
            # 블록의 절대 중심 위치 계산
            center_x = integrated_result.stern_clearance + pos_x + (block_width / 2.0)
            center_y = pos_y + (block_height / 2.0)
            
            # 배치 순서와 이름 표시
            order_num = placement_order_dict.get(block.id, 0)
            display_text = f"#{order_num}\n{block.id}" if order_num > 0 else block.id
            
            # Stepped 블록은 특별한 텍스트 스타일
            if block_type == 'stepped':
                ax_main.text(center_x, center_y, display_text, ha='center', va='center', 
                           fontsize=10, fontweight='bold', color='white',
                           bbox=dict(boxstyle='round,pad=0.6', facecolor='darkviolet', alpha=1.0, edgecolor='white', linewidth=1))
            else:
                ax_main.text(center_x, center_y, display_text, ha='center', va='center', 
                           fontsize=9, fontweight='bold', color='black',
                           bbox=dict(boxstyle='round,pad=0.5', facecolor='white', alpha=0.95, edgecolor='black', linewidth=1))
        
        # 축 설정
        ax_main.set_xlim(-2, total_width + 2)
        ax_main.set_ylim(-2, total_height + 2)
        ax_main.set_aspect('equal')
        ax_main.grid(True, alpha=0.3)
        
        # 통계 정보 계산
        total_blocks = len(placed_blocks_list)
        regular_count = sum(1 for b in placed_blocks_list if getattr(b, 'block_type', 'unknown') != 'stepped')
        stepped_count = sum(1 for b in placed_blocks_list if getattr(b, 'block_type', 'unknown') == 'stepped')
        used_area = sum(block.get_area() for block in placed_blocks_list)
        space_utilization = (used_area / (total_width * total_height)) * 100 if total_width * total_height > 0 else 0
        
        # 범례 (ship_placer와 유사 + stepped 블록 추가)
        legend_elements = []
        legend_elements.append(patches.Patch(color='lightgreen', alpha=0.5, label='Placement Area'))
        if integrated_result.bow_clearance > 0:
            legend_elements.append(patches.Patch(color='red', alpha=0.3, label=f'Bow Clearance ({integrated_result.bow_clearance} grids)'))
        if integrated_result.stern_clearance > 0:
            legend_elements.append(patches.Patch(color='purple', alpha=0.3, label=f'Stern Clearance ({integrated_result.stern_clearance} grids)'))
        
        # 실제 배치된 블록 타입에 따른 범례
        if regular_count > 0:
            has_crane = any(getattr(b, 'block_type', 'unknown') == 'crane' for b in placed_blocks_list)
            has_trestle = any(getattr(b, 'block_type', 'unknown') == 'trestle' for b in placed_blocks_list)
            if has_crane:
                legend_elements.append(patches.Patch(color='lime', alpha=0.7, label='Crane Blocks'))
            if has_trestle:
                legend_elements.append(patches.Patch(color='lime', alpha=0.7, label='Trestle Blocks'))
        
        if stepped_count > 0:
            legend_elements.append(patches.Patch(color='purple', alpha=0.85, label='Height-Aware Blocks (Multi-Level)'))
        
        ax_main.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=9)
        
        # 제목 (ship_placer와 유사한 형식)
        ship_name = self.config.get("ship_configuration", {}).get("name", "Unknown Ship")
        plt.title(f'Height-Aware Block Placement Demo: {ship_name}\n'
                 f'Regular Blocks: {regular_count} | Height-Aware Blocks: {stepped_count} (Multi-Level) | Space Utilization: {space_utilization:.1f}%', 
                 fontsize=16)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"[INFO] 시각화 저장: {save_path}")
            
        if show:
            plt.show()
    
    def run_height_aware_placement_demo(self, max_time=15, enable_visualization=True, save_path=None):
        """높이 정보 고려 배치 데모 실행"""
        print("=== 높이 정보 고려 블록 배치 시각화 데모 ===\n")
        
        # LV1 내의 placement_results 폴더 생성
        import os
        current_dir = Path(__file__).parent
        lv1_dir = current_dir.parent
        results_dir = lv1_dir / "placement_results"
        results_dir.mkdir(exist_ok=True)
        print(f"[INFO] {results_dir} 폴더 생성됨")

        # 기본 저장 경로 설정 (save_path가 지정되지 않은 경우)
        if save_path is None:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = results_dir / f"height_aware_placement_{timestamp}.png"
            print(f"[INFO] 시각화 결과 저장 경로: {save_path}")
        
        if not ALGORITHM_AVAILABLE:
            print("[ERROR] 기존 알고리즘 모듈을 사용할 수 없습니다")
            return None
        
        # 1. 설정에서 블록 생성 (기존 ship_placer 사용)
        print("1. 블록 데이터 로딩...")
        all_blocks = self.ship_placer_config.create_blocks_from_config()
        print(f"   총 {len(all_blocks)}개 블록 로드")
        
        # 2. 블록 분리
        print("\n2. 블록 타입 분석...")
        regular_blocks, height_block_ids = self.separate_blocks(all_blocks)
        print(f"   일반 블록: {len(regular_blocks)}개")
        print(f"   높이 정보 블록 ID: {len(height_block_ids)}개 (실제 파일에서 로드)")
        
        # 3. 높이 정보 블록 통합 생성
        print("\n3. 높이 정보 블록 A+B 통합...")
        merged_height_block = self.create_merged_height_block()
        
        if not merged_height_block:
            print("[ERROR] 높이 정보 블록 통합 실패")
            return None
        
        # 4. 모든 블록을 함께 GreedyPlacer로 배치
        all_blocks_for_placement = regular_blocks + [merged_height_block]
        print(f"\n4. 전체 블록 {len(all_blocks_for_placement)}개 배치 (일반: {len(regular_blocks)}, 통합 높이 정보: 1)")
        
        if not all_blocks_for_placement:
            print("[ERROR] 배치할 블록이 없음")
            return None
        
        # 기존 ship_placer의 place_blocks 메서드 사용
        result = self.ship_placer_config.place_blocks(all_blocks_for_placement, max_time=max_time)
        
        if not result:
            print("[ERROR] 블록 배치 실패")
            return None
        
        placed_count = len(result.placed_blocks)
        total_count = placed_count + len(result.unplaced_blocks)
        print(f"[INFO] 블록 배치 완료: {placed_count}/{total_count}개 성공")
        
        # 5. 통합 높이 정보 블록이 배치되었는지 확인
        merged_placed = None
        regular_placed = {}
        
        for block_id, block in result.placed_blocks.items():
            if block_id == "HEIGHT_MERGED":
                merged_placed = block
                print(f"[INFO] 통합 높이 정보 블록 배치됨: {block.position}")
            else:
                regular_placed[block_id] = block
        
        if not merged_placed:
            print("[WARNING] 통합 높이 정보 블록이 배치되지 않음")
            return result
        
        # 6. 시각화용 결과 준비 (통합 블록을 A와 B로 분리해서 표시)
        integrated_result = {
            'placement_area': result,
            'merged_height_block': merged_placed,
            'regular_blocks': regular_placed
        }
        
        # 7. 시각화
        if enable_visualization:
            print("\n7. 통합 결과 시각화...")
            self.visualize_height_aware_result(integrated_result, save_path=save_path, show=True)
            if save_path:
                print(f"[INFO] 시각화 결과가 {save_path}에 저장되었습니다")
        
        print("\n=== Height-Aware Placement Demo Complete! ===")
        print("Key Features:")
        print("- Merged Block: Combined Height-Aware A+B into a single VoxelBlock")
        print("- Natural Placement: Existing GreedyPlacer automatically selects optimal position")
        print("- Perfect Attachment: A and B are always placed together (as one block)")
        print("- Visual Distinction: Height-aware blocks displayed in purple, regular blocks in lime")
        print("- Algorithm Unchanged: Achieved height-aware block effect without modifying existing code")
        
        return integrated_result

def main():
    if len(sys.argv) < 2:
        print("사용법: python height_aware_placement_visualizer.py <config.json> [max_time] [options]")
        print("옵션:")
        print("  -v, --visualize    시각화 활성화 (기본값)")
        print("  -s, --save <path>  결과 이미지 저장 경로 지정 (기본: visualization_results 폴더에 자동 저장)")
        print()
        print("참고: 시각화 결과는 기본적으로 visualization_results 폴더에 타임스탬프와 함께 자동 저장됩니다.")
        return
    
    config_path = sys.argv[1]
    max_time = 15
    enable_visualization = True  # 기본적으로 시각화 활성화
    save_path = None
    
    # 저장 경로 추출
    if '-s' in sys.argv or '--save' in sys.argv:
        save_idx = sys.argv.index('-s') if '-s' in sys.argv else sys.argv.index('--save')
        if save_idx + 1 < len(sys.argv):
            save_path = sys.argv[save_idx + 1]
        else:
            # 기본 저장 경로를 LV1/placement_results 폴더에 설정
            import os
            current_dir = Path(__file__).parent
            lv1_dir = current_dir.parent
            results_dir = lv1_dir / "placement_results"
            results_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = results_dir / f"height_aware_placement_{timestamp}.png"
    else:
        # -s 옵션이 없어도 기본적으로 저장하도록 설정
        save_path = None  # run_height_aware_placement_demo에서 자동 설정됨
    
    # 시간 설정
    for arg in sys.argv[2:]:
        if arg.isdigit():
            max_time = int(arg)
    
    # 데모 실행
    try:
        visualizer = HeightAwarePlacementVisualizer(config_path)
        result = visualizer.run_height_aware_placement_demo(
            max_time=max_time, 
            enable_visualization=enable_visualization,
            save_path=save_path
        )
    except Exception as e:
        print(f"[ERROR] 데모 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()