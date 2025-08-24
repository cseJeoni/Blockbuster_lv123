"""
물리엔진 기반 자항선 블록 배치 시스템
- 중력 드롭 시뮬레이션
- 자석 흡착 효과
- 충돌 검사 및 안정화
"""

import time
import copy
import random
import math
from typing import List, Tuple, Optional


class PhysicsBlock:
    """물리 속성을 가진 블록"""
    
    def __init__(self, voxel_block):
        self.voxel_block = voxel_block
        self.id = voxel_block.id
        self.width = voxel_block.width
        self.height = voxel_block.height
        
        # 물리 속성
        self.pos_x = 0.0
        self.pos_y = 0.0
        self.vel_x = 0.0
        self.vel_y = 0.0
        self.mass = self.width * self.height  # 면적 비례
        self.settled = False  # 안정화 여부
        
        # 자석 포인트 (블록 모서리)
        self.magnetic_points = [
            (0, 0), (self.width, 0),  # 하단 모서리
            (0, self.height), (self.width, self.height)  # 상단 모서리
        ]


class PhysicsEngine:
    """간단한 2D 물리엔진"""
    
    def __init__(self, ship_area):
        self.ship_area = ship_area
        self.gravity = 9.8  # 중력 가속도
        self.friction = 0.8  # 마찰 계수
        self.magnetic_force = 50.0  # 자석 힘
        self.dt = 0.1  # 시간 간격
        self.settled_threshold = 0.1  # 안정화 속도 임계값
        
    def simulate_drop(self, physics_blocks: List[PhysicsBlock], max_time=2.0):
        """중력 드롭 시뮬레이션"""
        start_time = time.time()
        
        while time.time() - start_time < max_time:
            all_settled = True
            
            for block in physics_blocks:
                if not block.settled:
                    self._update_physics(block, physics_blocks)
                    
                    # 안정화 체크
                    if abs(block.vel_x) < self.settled_threshold and abs(block.vel_y) < self.settled_threshold:
                        block.settled = True
                        block.vel_x = 0
                        block.vel_y = 0
                        # 그리드 정렬
                        block.pos_x = round(block.pos_x)
                        block.pos_y = round(block.pos_y)
                    else:
                        all_settled = False
            
            if all_settled:
                break
                
            time.sleep(0.01)  # 시뮬레이션 딜레이
    
    def _update_physics(self, block: PhysicsBlock, other_blocks: List[PhysicsBlock]):
        """블록의 물리 상태 업데이트"""
        # 중력 적용
        block.vel_y -= self.gravity * self.dt
        
        # 자석 힘 계산
        mag_force_x, mag_force_y = self._calculate_magnetic_forces(block, other_blocks)
        block.vel_x += mag_force_x * self.dt / block.mass
        block.vel_y += mag_force_y * self.dt / block.mass
        
        # 위치 업데이트
        new_x = block.pos_x + block.vel_x * self.dt
        new_y = block.pos_y + block.vel_y * self.dt
        
        # 충돌 검사 및 위치 보정
        new_x, new_y, collision = self._check_collisions(block, new_x, new_y, other_blocks)
        
        if collision:
            # 충돌시 속도 감소
            block.vel_x *= self.friction
            block.vel_y *= self.friction
        
        block.pos_x = new_x
        block.pos_y = new_y
    
    def _calculate_magnetic_forces(self, block: PhysicsBlock, other_blocks: List[PhysicsBlock]) -> Tuple[float, float]:
        """자석 흡착력 계산"""
        total_force_x = 0.0
        total_force_y = 0.0
        
        for other in other_blocks:
            if other.settled and other != block:
                # 블록간 자석 포인트 간 힘 계산
                for mag_point in block.magnetic_points:
                    for other_point in other.magnetic_points:
                        # 현재 블록의 자석 포인트 절대 위치
                        point_x = block.pos_x + mag_point[0]
                        point_y = block.pos_y + mag_point[1]
                        
                        # 상대 블록의 자석 포인트 절대 위치
                        other_point_x = other.pos_x + other_point[0]
                        other_point_y = other.pos_y + other_point[1]
                        
                        # 거리 계산
                        dx = other_point_x - point_x
                        dy = other_point_y - point_y
                        distance = math.sqrt(dx*dx + dy*dy) + 0.1  # 0으로 나누기 방지
                        
                        # 적절한 거리에서만 자석 효과 (너무 가깝거나 멀면 무시)
                        if 2 < distance < 20:
                            # 자석력은 거리의 제곱에 반비례
                            force_magnitude = self.magnetic_force / (distance * distance)
                            
                            # 정규화된 방향 벡터
                            force_x = (dx / distance) * force_magnitude
                            force_y = (dy / distance) * force_magnitude
                            
                            total_force_x += force_x
                            total_force_y += force_y
        
        return total_force_x, total_force_y
    
    def _check_collisions(self, block: PhysicsBlock, new_x: float, new_y: float, other_blocks: List[PhysicsBlock]) -> Tuple[float, float, bool]:
        """충돌 검사 및 위치 보정"""
        collision = False
        
        # 경계 충돌 검사
        if new_x < self.ship_area.stern_clearance:
            new_x = self.ship_area.stern_clearance
            collision = True
        elif new_x + block.width > self.ship_area.width - self.ship_area.bow_clearance:
            new_x = self.ship_area.width - self.ship_area.bow_clearance - block.width
            collision = True
            
        if new_y < 0:
            new_y = 0
            collision = True
        elif new_y + block.height > self.ship_area.height:
            new_y = self.ship_area.height - block.height
            collision = True
        
        # 다른 블록들과의 충돌 검사
        for other in other_blocks:
            if other != block and other.settled:
                if self._blocks_overlap(new_x, new_y, block, other.pos_x, other.pos_y, other):
                    # 충돌 회피를 위한 위치 조정
                    new_x, new_y = self._resolve_collision(block, new_x, new_y, other)
                    collision = True
        
        return new_x, new_y, collision
    
    def _blocks_overlap(self, x1: float, y1: float, block1: PhysicsBlock, 
                       x2: float, y2: float, block2: PhysicsBlock) -> bool:
        """두 블록이 겹치는지 확인 (spacing 포함)"""
        spacing = getattr(self.ship_area, 'block_spacing', 1)
        
        # 확장된 경계 상자로 겹침 검사
        left1, right1 = x1 - spacing, x1 + block1.width + spacing
        bottom1, top1 = y1 - spacing, y1 + block1.height + spacing
        
        left2, right2 = x2, x2 + block2.width
        bottom2, top2 = y2, y2 + block2.height
        
        return not (right1 <= left2 or left1 >= right2 or top1 <= bottom2 or bottom1 >= top2)
    
    def _resolve_collision(self, block: PhysicsBlock, x: float, y: float, other: PhysicsBlock) -> Tuple[float, float]:
        """충돌 해결을 위한 위치 조정"""
        spacing = getattr(self.ship_area, 'block_spacing', 1)
        
        # 4방향 중 가장 가까운 충돌 회피 위치 찾기
        positions = [
            # 왼쪽에 배치
            (other.pos_x - block.width - spacing, y),
            # 오른쪽에 배치  
            (other.pos_x + other.width + spacing, y),
            # 아래쪽에 배치
            (x, other.pos_y - block.height - spacing),
            # 위쪽에 배치
            (x, other.pos_y + other.height + spacing)
        ]
        
        # 현재 위치에서 가장 가까운 유효한 위치 선택
        best_pos = (x, y)
        min_distance = float('inf')
        
        for pos_x, pos_y in positions:
            # 경계 체크
            if (pos_x >= self.ship_area.stern_clearance and 
                pos_x + block.width <= self.ship_area.width - self.ship_area.bow_clearance and
                pos_y >= 0 and pos_y + block.height <= self.ship_area.height):
                
                distance = math.sqrt((pos_x - x)**2 + (pos_y - y)**2)
                if distance < min_distance:
                    min_distance = distance
                    best_pos = (pos_x, pos_y)
        
        return best_pos


class PhysicsBasedPlacer:
    """물리엔진 기반 배치 시스템"""
    
    def __init__(self, placement_area, blocks, max_time=10):
        self.placement_area = placement_area
        self.blocks = blocks
        self.max_time = max_time
        self.physics_engine = PhysicsEngine(placement_area)
        self.placement_area.add_blocks(blocks)
    
    def optimize(self):
        """물리 기반 최적화 배치"""
        print(f"[INFO] Physics-based placement started with {len(self.blocks)} blocks")
        start_time = time.time()
        
        # 블록을 크기 순으로 정렬 (큰 블록부터)
        sorted_blocks = sorted(self.blocks, key=lambda b: -b.get_area())
        
        # 물리 블록으로 변환
        physics_blocks = [PhysicsBlock(block) for block in sorted_blocks]
        
        # 초기 위치 설정 (상공에서 드롭)
        self._set_initial_positions(physics_blocks)
        
        # 물리 시뮬레이션 실행
        self.physics_engine.simulate_drop(physics_blocks, max_time=self.max_time * 0.8)
        
        # 결과를 placement_area에 적용
        success_count = 0
        for physics_block in physics_blocks:
            pos_x = int(physics_block.pos_x)
            pos_y = int(physics_block.pos_y)
            
            # 유효한 위치인지 확인
            if self.placement_area.can_place_block(physics_block.voxel_block, pos_x, pos_y):
                self.placement_area.place_block(physics_block.voxel_block, pos_x, pos_y)
                success_count += 1
            else:
                print(f"[WARNING] Physics block {physics_block.id} settled at invalid position ({pos_x}, {pos_y})")
        
        elapsed_time = time.time() - start_time
        print(f"[INFO] Physics placement completed in {elapsed_time:.2f}s")
        print(f"       Successfully placed: {success_count}/{len(self.blocks)} blocks")
        
        return self.placement_area
    
    def _set_initial_positions(self, physics_blocks: List[PhysicsBlock]):
        """블록들의 초기 드롭 위치 설정"""
        ship_width = self.placement_area.width
        ship_height = self.placement_area.height
        
        # 오른쪽부터 배치하되, 약간의 랜덤성 추가
        for i, block in enumerate(physics_blocks):
            # 오른쪽 끝에서 시작, 약간의 변동
            base_x = ship_width - self.placement_area.bow_clearance - block.width
            offset_x = random.uniform(-5, 2)  # 약간 왼쪽으로 변동 가능
            block.pos_x = max(self.placement_area.stern_clearance, base_x + offset_x)
            
            # 상공에서 드롭 (높이 차이로 순서 제어)
            block.pos_y = ship_height + 20 + i * 10
            
            # 초기 속도 (약간의 수평 속도)
            block.vel_x = random.uniform(-2, 1)  # 왼쪽으로 약간 이동
            block.vel_y = 0