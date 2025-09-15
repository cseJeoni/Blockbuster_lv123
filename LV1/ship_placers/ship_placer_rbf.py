#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Config 기반 자항선 블록 배치 시스템 (RBF 알고리즘 사용)
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

try:
    from models.voxel_block import VoxelBlock
    from models.placement_area import PlacementArea
    from algorithms.bottom_right_placer import BottomRightPlacer  # Bottom-Right 배치 알고리즘 import
    ALGORITHM_AVAILABLE = True
except ImportError as e:
    ALGORITHM_AVAILABLE = False

class ShipPlacementAreaConfig(PlacementArea):
    """Config 기반 자항선 배치 영역 및 제약조건 검사"""
    
    def __init__(self, config):
        ship_config = config['ship_configuration']
        grid_size = ship_config['grid_size']
        constraints = ship_config['constraints']
        margin = constraints['margin']
        
        self.ship_width_m = grid_size['width']
        self.ship_height_m = grid_size['height']
        self.grid_unit = grid_size['grid_unit']
        
        width_grids = int(self.ship_width_m / self.grid_unit)
        height_grids = int(self.ship_height_m / self.grid_unit)
        
        # 여백 계산
        self.bow_clearance = int(margin['bow'])
        self.stern_clearance = int(margin['stern'])
        self.block_spacing = int(constraints.get('block_clearance', 1))
        self.ring_bow_clearance = int(constraints.get('ring_bow_clearance', 0))
        
        # 실제 배치 가능 영역 크기 (여백 제외)
        actual_width = width_grids - self.bow_clearance - self.stern_clearance
        actual_height = height_grids  # 높이는 여백 없음
        
        # 여백을 제외한 크기로 PlacementArea 생성
        super().__init__(actual_width, actual_height)
        
        self.grid_resolution = self.grid_unit
        # 전체 선박 크기 정보 보관 (시각화용)
        self.total_width = width_grids
        self.total_height = height_grids
        
    
    def can_place_block(self, block, pos_x, pos_y):
        
        # 블록 타입 한 번만 체크 (성능 최적화)
        is_crane = getattr(block, 'block_type', None) == 'crane'
        
        if is_crane:
            # 크레인 블록: 기본 경계 체크 + ring bow clearance만 적용 (일반 bow는 무시)
            # 부모 클래스의 경계/충돌 체크만 수행 (bow clearance 제외)
            if not self._check_basic_placement_only(block, pos_x, pos_y):
                return False
            # 크레인 전용 ring bow clearance 확인
            if not self._check_crane_ring_bow_clearance(block, pos_x, pos_y):
                return False
        else:
            # 트레슬/기타 블록: 기본 배치 가능성 검사 (일반 bow clearance 포함)
            if not super().can_place_block(block, pos_x, pos_y):
                return False
        
        # 운송 접근성 확인 (트레슬 블록용)
        if not self._check_transporter_access(block, pos_x, pos_y):
            return False
        
        # 여백은 이미 배치 영역 크기에서 제외되어 있으므로 별도 검사 불필요
        
        # 블록 간 이격거리 확인 (개선된 테두리 방식)
        new_footprint = block.get_footprint()
        
        # 새 블록의 모든 테두리 복셀 찾기
        new_boundary = set()
        footprint_set = set(new_footprint)
        
        for vx, vy in new_footprint:
            # 4방향 중 하나라도 인접 복셀이 없으면 테두리
            neighbors = [(vx+1, vy), (vx-1, vy), (vx, vy+1), (vx, vy-1)]
            if any(neighbor not in footprint_set for neighbor in neighbors):
                ref_x, ref_y = block.actual_reference
                grid_x = pos_x + vx - ref_x
                grid_y = pos_y + vy - ref_y
                new_boundary.add((grid_x, grid_y))
                
        
        # 인근 블록들과 이격거리 체크 (개선된 선별)
        for placed_block in self.placed_blocks.values():
            if placed_block.position is None: 
                continue
            
            # 자기 자신과는 이격거리 검사 안함
            if placed_block.id == block.id:
                continue
                
            px, py = placed_block.position
            
            # 빠른 바운딩박스 선별 (블록 크기 고려)
            max_distance = self.block_spacing + max(block.width, block.height) + max(placed_block.width, placed_block.height)
            if abs(pos_x - px) > max_distance or abs(pos_y - py) > max_distance:
                continue  # 확실히 멀리 있는 블록은 스킵
            
            # 기존 블록의 테두리 복셀 찾기
            placed_footprint = placed_block.get_footprint()
            placed_boundary = set()
            placed_set = set(placed_footprint)
            
            for vx, vy in placed_footprint:
                neighbors = [(vx+1, vy), (vx-1, vy), (vx, vy+1), (vx, vy-1)]
                if any(neighbor not in placed_set for neighbor in neighbors):
                    placed_ref_x, placed_ref_y = placed_block.actual_reference
                    grid_x = px + vx - placed_ref_x
                    grid_y = py + vy - placed_ref_y
                    placed_boundary.add((grid_x, grid_y))
            
            # 테두리 복셀들 간 최소 거리 계산
            for new_x, new_y in new_boundary:
                for placed_x, placed_y in placed_boundary:
                    dx = abs(new_x - placed_x)
                    dy = abs(new_y - placed_y)
                    
                    # 8방향(대각선 포함) 이격거리 체크
                    if dx == 0 and dy == 0:
                        distance = 0  # 겹침
                    elif (dx == 0 and dy == 1) or (dx == 1 and dy == 0):
                        distance = 1  # 상하좌우 인접
                    elif dx == 0:
                        distance = dy - 1  # 세로 직선 거리
                    elif dy == 0:
                        distance = dx - 1  # 가로 직선 거리
                    else:
                        # 대각선 거리: 체스보드 거리 (최대값)
                        distance = max(dx, dy) - 1
                    
                    if distance < self.block_spacing:
                        return False  # 이격거리 위반
        
        return True
    
    def _check_transporter_access(self, block, pos_x, pos_y):
        """트랜스포터 접근성 확인"""
        # 크레인 블록은 수직 접근 가능 (성능 최적화: getattr 사용)
        if getattr(block, 'block_type', None) == 'crane':
            return True
        
        # 트레슬 블록은 수평 접근로 필요
        block_y_start = pos_y
        block_y_end = pos_y + block.height
        block_left_edge = pos_x
        
        # 왼쪽 끝에서 블록까지 경로 확인
        for x in range(0, block_left_edge):
            for y in range(block_y_start, block_y_end):
                if y < 0 or y >= self.height or self.grid[y, x] is not None:
                    return False
        
        return True
    
    def _check_crane_ring_bow_clearance(self, block, pos_x, pos_y):
        """크레인 블록의 ring bow clearance 확인"""
        # 크레인 블록이 아니면 검사하지 않음 (성능 최적화: getattr 사용)
        if getattr(block, 'block_type', None) != 'crane':
            return True
        
        # ring_bow_clearance가 설정되지 않았으면 검사하지 않음
        if self.ring_bow_clearance <= 0:
            return True
        
        # 블록의 모든 복셀 위치 확인
        ref_x, ref_y = block.actual_reference
        for vx, vy in block.get_footprint():
            # 실제 배치 위치 계산 (배치 영역 내 좌표)
            grid_x = pos_x + vx - ref_x
            grid_y = pos_y + vy - ref_y
            
            # bow 쪽(오른쪽 끝)에서의 거리 확인
            # 크레인이 사용 가능한 전체 영역의 오른쪽 끝에서 ring_bow_clearance만큼 떨어져야 함
            total_available_width = self.width + self.bow_clearance
            distance_from_bow = total_available_width - grid_x - 1
            
            if distance_from_bow < self.ring_bow_clearance:
                return False  # ring bow clearance 위반
        
        return True
    
    def _check_basic_placement_only(self, block, pos_x, pos_y):
        """크레인 블록 전용: bow clearance 제외하고 기본 배치만 체크"""
        # 부모 클래스의 기본 체크 (경계, 충돌, stern clearance)를 수행하되
        # bow clearance는 제외하고 체크
        
        # 1. 경계 체크 (bow clearance 제외) - 배치 영역 + bow clearance 내에서 체크
        ref_x, ref_y = block.actual_reference
        for vx, vy in block.get_footprint():
            grid_x = pos_x + vx - ref_x
            grid_y = pos_y + vy - ref_y
            
            # 확장된 경계 체크 (bow clearance 추가하여 크레인이 사용 가능한 전체 영역)
            extended_width = self.width + self.bow_clearance
            if not (0 <= grid_x < extended_width and 0 <= grid_y < self.height):
                return False
        
        # 2. 기존 블록과 충돌 체크
        positioned_footprint = block.get_positioned_footprint()
        if positioned_footprint is None:
            # 임시로 위치 설정하여 footprint 계산
            block.position = (pos_x, pos_y)
            positioned_footprint = block.get_positioned_footprint()
            block.position = None
        
        if positioned_footprint:
            for placed_block in self.placed_blocks.values():
                placed_footprint = placed_block.get_positioned_footprint()
                if placed_footprint and positioned_footprint & placed_footprint:
                    return False
        
        return True
    
    def clone(self):
        """ShipPlacementAreaConfig의 복제본 생성 - 모든 속성 보존"""
        # 기본 PlacementArea 클론 생성
        new_area = super().clone()
        
        # ShipPlacementAreaConfig 전용 속성들 복사
        new_area.__class__ = ShipPlacementAreaConfig
        new_area.ship_width_m = self.ship_width_m
        new_area.ship_height_m = self.ship_height_m
        new_area.grid_unit = self.grid_unit
        new_area.grid_resolution = self.grid_resolution
        new_area.bow_clearance = self.bow_clearance
        new_area.stern_clearance = self.stern_clearance
        new_area.block_spacing = self.block_spacing
        new_area.ring_bow_clearance = self.ring_bow_clearance
        
        return new_area
    
    def _get_nearby_blocks(self, center_x, center_y, max_range):
        """중심점 기준 일정 범위 내 블록들만 반환 (성능 최적화)"""
        nearby = []
        for block in self.placed_blocks.values():
            if block.position is None:
                continue
            bx, by = block.position
            # 대략적 거리로 빠른 선별 (바운딩박스 기반)
            if abs(center_x - bx) <= max_range and abs(center_y - by) <= max_range:
                nearby.append(block)
        return nearby
    
    def _get_boundary_voxels(self, block, pos_x, pos_y, sides=['all']):
        """블록의 테두리 복셀들 추출 (실제 복셀 기준, 방향별 선택 가능)"""
        boundary = set()
        footprint = block.get_footprint()
        footprint_set = set(footprint)
        ref_x, ref_y = block.actual_reference
        
        for vx, vy in footprint:
            is_boundary = False
            
            # 방향별 테두리 체크
            if 'right' in sides and (vx + 1, vy) not in footprint_set:
                is_boundary = True
            if 'left' in sides and (vx - 1, vy) not in footprint_set:
                is_boundary = True
            if 'top' in sides and (vx, vy + 1) not in footprint_set:
                is_boundary = True
            if 'bottom' in sides and (vx, vy - 1) not in footprint_set:
                is_boundary = True
            if 'all' in sides:
                # 모든 방향 테두리 체크
                neighbors = [(vx+1, vy), (vx-1, vy), (vx, vy+1), (vx, vy-1)]
                if any(neighbor not in footprint_set for neighbor in neighbors):
                    is_boundary = True
            
            if is_boundary:
                grid_x = pos_x + vx - ref_x
                grid_y = pos_y + vy - ref_y
                boundary.add((grid_x, grid_y))
        
        return boundary

class ShipPlacerConfig:
    def __init__(self, config_path):
        self.config_path = config_path
        self.config = self.load_config(config_path)
    
    def load_config(self, config_path):
        with open(config_path, 'r', encoding='utf-8') as f: return json.load(f)
    
    def create_blocks_from_config(self):
        """Config에서 블록 생성 - voxel_positions와 voxel_array 둘 다 지원"""
        blocks = []
        
        for block_config in self.config['blocks_to_place']['blocks']:
            quantity = block_config.get('quantity', 1)
            for i in range(quantity):
                block_id = f"{block_config['block_id']}_{i+1}" if quantity > 1 else block_config['block_id']
                voxel_data_config = block_config['voxel_data']
                
                # VoxelBlock 데이터 처리 (voxel_positions 형식)
                print(f"       [VoxelBlock] Loading {block_id}")
                voxel_data = []
                
                if 'footprint_positions' in voxel_data_config:
                    for pos in voxel_data_config['footprint_positions']:
                        voxel_data.append((pos['x'], pos['y'], pos.get('height_info', [0, 1, 0])))
                elif 'voxel_positions' in voxel_data_config:
                    # voxel_positions에서 직접 변환: [x, y, [min_z, max_z, count]]
                    for pos in voxel_data_config['voxel_positions']:
                        x, y, height_info = pos[0], pos[1], pos[2]
                        voxel_data.append((x, y, height_info))
                else:
                    for x in range(10):
                        for y in range(10):
                            voxel_data.append((x, y, [0, 1, 0]))
                
                block = VoxelBlock(block_id, voxel_data)

                block.block_type = block_config['block_type']
                
                # 트레슬 블록 자동 회전
                if block.block_type == 'trestle' and block.height > block.width and hasattr(block, 'rotate'):
                    block.rotate(90)
                    
                blocks.append(block)
        
        
        return blocks
    
    def place_blocks(self, blocks, max_time=15):
        if not ALGORITHM_AVAILABLE or not blocks:
            return None
        area = ShipPlacementAreaConfig(self.config)
        try:
            start_time = time.time()
            # RBF 알고리즘 사용
            placer = BottomRightPlacer(area, blocks, max_time)
            result = placer.place_all_blocks()

            if result:
                blocks_by_id = {b.id: b for b in blocks}
                for block_id, placed_block in result.placed_blocks.items():
                    if not hasattr(placed_block, 'block_type') or not placed_block.block_type:
                         if block_id in blocks_by_id:
                            placed_block.block_type = blocks_by_id[block_id].block_type
            
            end_time = time.time()
            
            if result:
                result.placement_time = end_time - start_time
                for attr in ['bow_clearance', 'stern_clearance', 'block_spacing', 'ship_width_m', 'ship_height_m', 'grid_unit', 'grid_resolution']:
                    setattr(result, attr, getattr(area, attr))
                
                placed_count = len(result.placed_blocks)
                total_count = placed_count + len(result.unplaced_blocks)
                
            return result
        except Exception as e:
            return None
    
    def visualize(self, result, save_path=None, show=True, show_dead_space=False):
        fig, ax_main = plt.subplots(1, 1, figsize=(20, 12))
        
        # 전체 선박 영역 (여백 포함)
        total_width = result.total_width
        total_height = result.total_height
        ship_rect = patches.Rectangle((0, 0), total_width, total_height, linewidth=3, edgecolor='navy', facecolor='lightblue', alpha=0.3)
        ax_main.add_patch(ship_rect)
        
        # 배치 가능 영역 표시 (여백 제외된 실제 영역)
        placement_rect = patches.Rectangle((result.stern_clearance, 0), result.width, result.height, linewidth=2, edgecolor='green', facecolor='lightgreen', alpha=0.2)
        ax_main.add_patch(placement_rect)
        
        # 여백 영역 표시
        if result.bow_clearance > 0:
            bow_rect = patches.Rectangle((total_width - result.bow_clearance, 0), result.bow_clearance, total_height, linewidth=2, edgecolor='red', facecolor='red', alpha=0.2)
            ax_main.add_patch(bow_rect)
        if result.stern_clearance > 0:
            stern_rect = patches.Rectangle((0, 0), result.stern_clearance, total_height, linewidth=2, edgecolor='purple', facecolor='purple', alpha=0.2)
            ax_main.add_patch(stern_rect)
        
        # 크레인 전용 ring bow clearance 표시 (일반 bow clearance보다 더 안쪽)
        if hasattr(result, 'ring_bow_clearance') and result.ring_bow_clearance > 0:
            ring_bow_start = total_width - result.ring_bow_clearance
            ring_bow_rect = patches.Rectangle((ring_bow_start, 0), result.ring_bow_clearance, total_height, 
                                            linewidth=2, edgecolor='darkorange', facecolor='orange', alpha=0.15)
            ax_main.add_patch(ring_bow_rect)
        
        placed_blocks_list = list(result.placed_blocks.values())
        total_blocks = len(placed_blocks_list) + len(result.unplaced_blocks)
        placed_count = len(placed_blocks_list)
        success_rate = (placed_count / total_blocks) * 100 if total_blocks > 0 else 0
        type_colors = {'crane': 'orange', 'trestle': 'green', 'unknown': 'gray'}
        
        # RBF는 placement_order가 없으므로 기본값 사용
        placement_order_dict = {}
        
        for i, block in enumerate(placed_blocks_list, 1):
            if block.position is None: continue
            pos_x, pos_y = block.position
            color = type_colors.get(getattr(block, 'block_type', 'unknown'), 'gray')
            
            # 실제 복셀 기준 좌표 변환 + 선미 여백 오프셋 적용
            ref_x, ref_y = block.actual_reference
            for rel_x, rel_y in block.get_footprint():
                abs_x = result.stern_clearance + pos_x + rel_x - ref_x
                abs_y = pos_y + rel_y - ref_y
                cell_rect = patches.Rectangle((abs_x, abs_y), 1, 1, linewidth=0.5, edgecolor='black', facecolor=color, alpha=0.7)
                ax_main.add_patch(cell_rect)
            
            # 블록 이름 표시 (블록 중앙에)
            footprint_coords = list(block.get_footprint())
            if footprint_coords:
                min_vx = min(vx for vx, vy in footprint_coords)
                max_vx = max(vx for vx, vy in footprint_coords)
                min_vy = min(vy for vx, vy in footprint_coords)
                max_vy = max(vy for vx, vy in footprint_coords)
                
                actual_width = max_vx - min_vx + 1
                actual_height = max_vy - min_vy + 1
                center_offset_x = (max_vx + min_vx) / 2 - ref_x
                center_offset_y = (max_vy + min_vy) / 2 - ref_y
                center_x = result.stern_clearance + pos_x + center_offset_x
                center_y = pos_y + center_offset_y
            
            # RBF 순서 표시 (배치된 순서)
            display_text = f"#{i}\n{block.id}"
            
            ax_main.text(center_x, center_y, display_text, ha='center', va='center', 
                        fontsize=7, fontweight='bold', color='white',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.8))
        
        ax_main.set_xlim(-2, total_width + 2)
        ax_main.set_ylim(-2, total_height + 2)
        ax_main.set_aspect('equal')
        ax_main.grid(True, alpha=0.3)
        used_area = sum(block.get_area() for block in placed_blocks_list)
        space_utilization = (used_area / (total_width * total_height)) * 100 if total_width * total_height > 0 else 0
        
        # Dead Space 시각화 (옵션)
        if show_dead_space:
            dead_space_metrics = result.calculate_cluster_dead_space()
            if dead_space_metrics['cluster_area'] > 0:
                min_x, min_y, max_x, max_y = dead_space_metrics['cluster_bbox']
                left_boundary_by_y = dead_space_metrics['left_boundary_by_y']
                
                # 연속적인 왼쪽 윤곽선 생성 (실제 블록 테두리 따라가기)
                boundary_x = []
                boundary_y = []
                
                # 위에서 아래로 가면서 왼쪽 윤곽선 그리기
                current_x = None
                
                for y in sorted(range(min_y, max_y + 1), reverse=True):  # 위에서 아래로
                    if y in left_boundary_by_y:
                        left_x = min(left_boundary_by_y[y])
                        
                        if current_x is None:
                            # 첫 번째 점 (맨 위)
                            current_x = left_x
                            boundary_x.append(result.stern_clearance + current_x)
                            boundary_y.append(y + 1)  # 블록 위쪽 경계
                            
                        if left_x != current_x:
                            # X가 바뀌는 지점: 수평선으로 이동
                            boundary_x.append(result.stern_clearance + current_x)
                            boundary_y.append(y + 1)  # 현재 Y 레벨의 위쪽
                            boundary_x.append(result.stern_clearance + left_x)
                            boundary_y.append(y + 1)  # 새로운 X로 이동
                            current_x = left_x
                        
                        # 수직선으로 아래로 내려가기
                        boundary_x.append(result.stern_clearance + current_x)
                        boundary_y.append(y)  # 블록 아래쪽 경계
                
                # 왼쪽 윤곽선 그리기
                if len(boundary_x) > 1:
                    ax_main.plot(boundary_x, boundary_y, color='red', linewidth=3, 
                               linestyle='--', alpha=0.8, label='Left Block Contour')
                
                # 나머지 경계선들 (직선)
                # 위쪽 경계
                ax_main.plot([result.stern_clearance + min_x, result.stern_clearance + max_x + 1], 
                           [max_y + 1, max_y + 1], color='red', linewidth=3, 
                           linestyle='--', alpha=0.8)
                
                # 오른쪽 경계
                ax_main.plot([result.stern_clearance + max_x + 1, result.stern_clearance + max_x + 1], 
                           [max_y + 1, min_y], color='red', linewidth=3, 
                           linestyle='--', alpha=0.8)
                
                # 아래쪽 경계
                ax_main.plot([result.stern_clearance + max_x + 1, result.stern_clearance + min_x], 
                           [min_y, min_y], color='red', linewidth=3, 
                           linestyle='--', alpha=0.8)
                
                # 덩어리 내부의 Dead Space 셀들 찾아서 표시
                occupied_cells = set()
                for block in result.placed_blocks.values():
                    if block.position is not None:
                        pos_x, pos_y = block.position
                        ref_x, ref_y = block.actual_reference
                        for vx, vy in block.get_footprint():
                            cell_x = pos_x + vx - ref_x
                            cell_y = pos_y + vy - ref_y
                            occupied_cells.add((cell_x, cell_y))
                
                # Dead Space 계산: Y별로 왼쪽 경계부터 max_x까지 확인
                for y in range(min_y, max_y + 1):
                    if y in left_boundary_by_y:
                        left_x = min(left_boundary_by_y[y])
                        for x in range(left_x, max_x + 1):
                            if (x, y) not in occupied_cells:
                                # Dead Space 셀을 빨간색으로 표시
                                dead_rect = patches.Rectangle(
                                    (result.stern_clearance + x, y), 1, 1,
                                    facecolor='red', alpha=0.4, edgecolor='darkred', linewidth=0.5
                                )
                                ax_main.add_patch(dead_rect)

        # 범례 정보 준비 (영어로 변경)
        legend_elements = []
        legend_elements.append(patches.Patch(color='lightgreen', alpha=0.5, label='Placement Area'))
        if result.bow_clearance > 0:
            legend_elements.append(patches.Patch(color='red', alpha=0.3, label=f'Bow Clearance ({result.bow_clearance} grids)'))
        if hasattr(result, 'ring_bow_clearance') and result.ring_bow_clearance > 0:
            legend_elements.append(patches.Patch(color='orange', alpha=0.3, label=f'Crane Ring Bow ({result.ring_bow_clearance} grids)'))
        if result.stern_clearance > 0:
            legend_elements.append(patches.Patch(color='purple', alpha=0.3, label=f'Stern Clearance ({result.stern_clearance} grids)'))
        legend_elements.append(patches.Patch(color='orange', alpha=0.7, label='Crane Blocks'))
        legend_elements.append(patches.Patch(color='green', alpha=0.7, label='Trestle Blocks'))
        
        # Dead Space 범례 추가
        if show_dead_space:
            legend_elements.append(patches.Patch(color='red', alpha=0.4, label='Dead Space'))
            legend_elements.append(patches.Patch(color='red', linestyle='--', fill=False, label='Block Contour Boundary'))
        
        # 범례 추가
        ax_main.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=9)
        
        plt.title(f'Ship Block Placement (RBF): {self.config["ship_configuration"]["name"]}\nPlaced: {placed_count}/{total_blocks} ({success_rate:.1f}%) | Space Usage: {space_utilization:.1f}% | Time: {result.placement_time:.2f}s', fontsize=16)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
        if show:
            plt.show()

def main():
    if len(sys.argv) < 2:
        print("Usage: python ship_placer_rbf.py <config.json> [max_time] [options]")
        print("Options:")
        print("  -v, --visualize    Enable visualization")
        print("  --deadspace        Show dead space analysis in visualization")
        print("  -u, --unity        Export Unity data")
        return
    
    config_path = sys.argv[1]
    max_time = 15
    enable_visualization = '-v' in sys.argv or '--visualize' in sys.argv
    export_unity = '-u' in sys.argv or '--unity' in sys.argv
    show_dead_space = '--deadspace' in sys.argv or '--dead-space' in sys.argv
    
    for arg in sys.argv[2:]:
        if arg.isdigit():
            max_time = int(arg)
    
    placer_config = ShipPlacerConfig(config_path)
    blocks = placer_config.create_blocks_from_config()
    result = placer_config.place_blocks(blocks, max_time=max_time)
    
    if result:
        # 확장된 성능 지표 출력 (Dead Space 포함)
        print("\n=== RBF 배치 결과 분석 ===")
        metrics = result.get_enhanced_placement_metrics()
        
        print(f"배치율: {metrics['placement_rate']:.3f} ({metrics['placed_blocks_count']}/{metrics['total_blocks_count']})")
        print(f"기존 공간활용률: {metrics['traditional_utilization']:.3f}")
        print(f"덩어리 효율성: {metrics['cluster_efficiency']:.3f} (새로운 지표)")
        print(f"Dead Space 비율: {metrics['dead_space_ratio']:.3f}")
        print(f"공간 절약 비율: {metrics['space_saving_ratio']:.3f}")
        print(f"덩어리 크기: {metrics['cluster_dimensions'][0]}x{metrics['cluster_dimensions'][1]} ({metrics['cluster_area']} cells)")
        print(f"배치 시간: {result.placement_time:.2f}초")
        
        if enable_visualization:
            # LV1 내의 placement_results 디렉토리 사용
            current_dir = Path(__file__).parent
            lv1_dir = current_dir.parent
            output_dir = lv1_dir / "placement_results"
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config_name = Path(placer_config.config_path).stem
            deadspace_suffix = "_deadspace" if show_dead_space else ""
            viz_filename = f"placement_rbf_{config_name}_{timestamp}{deadspace_suffix}.png"
            placer_config.visualize(result, show=True, save_path=output_dir / viz_filename, show_dead_space=show_dead_space)

if __name__ == "__main__":
    main()