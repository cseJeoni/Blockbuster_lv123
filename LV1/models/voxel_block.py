"""
블록 및 복셀 데이터 구조를 정의하는 모듈
"""
import numpy as np
import copy


class VoxelBlock:
    """
    2.5D 복셀화 표현을 사용한 블록 클래스

    Attributes:
        id (str): 블록 식별자
        voxel_data (list): 복셀 데이터 [(x, y, [empty_below, filled]), ...] (개선된 형식)
        rotation (int): 블록 회전 각도 (0 또는 180)
        position (tuple): 배치된 위치 (x, y), 배치되지 않은 경우 None
    """

    def __init__(self, id, voxel_data):
        """
        VoxelBlock 초기화

        Args:
            id (str): 블록 식별자
            voxel_data (list): 복셀 데이터 [(x, y, [empty_below, filled]), ...] (개선된 형식)
        """
        self.id = id
        self.voxel_data = voxel_data  # [(x, y, [empty_below, filled]), ...] (개선된 형식)
        self.rotation = 0  # 0 또는 180
        self.position = None  # 배치된 위치 (x, y), 배치되지 않은 경우 None
        self.block_type = None  # 블록 타입 (crane, trestle 등)

        # 블록의 경계 계산
        self._calculate_bounds()

    def _calculate_bounds(self):
        """블록의 경계(width, height) 및 실제 복셀 기준 좌표 계산"""
        if not self.voxel_data:
            self.width = 0
            self.height = 0
            self.min_x = 0
            self.min_y = 0
            self.actual_reference = (0, 0)
            return

        x_coords = [voxel[0] for voxel in self.voxel_data]
        y_coords = [voxel[1] for voxel in self.voxel_data]

        self.min_x = min(x_coords)
        self.min_y = min(y_coords)
        self.max_x = max(x_coords)
        self.max_y = max(y_coords)

        self.width = self.max_x - self.min_x + 1
        self.height = self.max_y - self.min_y + 1
        
        # 실제 복셀이 존재하는 왼쪽 하단 기준점 계산
        self.actual_reference = self._calculate_actual_reference_point()

    def _calculate_actual_reference_point(self):
        """실제 복셀이 존재하는 왼쪽 하단 기준점 계산"""
        if not self.voxel_data:
            return (0, 0)
        
        # Y 좌표가 가장 작은 복셀들 찾기 (가장 아래쪽)
        min_y = min(voxel[1] for voxel in self.voxel_data)
        bottom_voxels = [voxel for voxel in self.voxel_data if voxel[1] == min_y]
        
        # 그 중에서 X 좌표가 가장 작은 복셀 (가장 왼쪽)
        leftmost_voxel = min(bottom_voxels, key=lambda v: v[0])
        
        return (leftmost_voxel[0], leftmost_voxel[1])

    def has_voxel_at_reference(self):
        """실제 기준점에 복셀이 존재하는지 확인"""
        if not self.voxel_data:
            return False
        
        ref_x, ref_y = self.actual_reference
        for voxel in self.voxel_data:
            if voxel[0] == ref_x and voxel[1] == ref_y:
                return True
        return False

    def rotate(self, angle=90):
        """
        블록을 지정된 각도만큼 시계방향 회전
        
        Args:
            angle (int): 회전 각도 (90, 180, 270도 지원)
        """
        # 회전 상태 업데이트
        self.rotation = (self.rotation + angle) % 360

        # 복셀 데이터 회전 처리
        rotated_data = []

        if angle == 90:
            # 90도 시계방향 회전: (x, y) -> (y, -x) 
            # 하지만 좌표를 양수로 유지하기 위해 보정 필요
            for x, y, heights in self.voxel_data:
                # 90도 회전: (x, y) -> (y, max_x - x)
                new_x = y
                new_y = self.max_x - x
                rotated_data.append((new_x, new_y, heights))
                
        elif angle == 180:
            # 180도 회전: (x, y) -> (max_x - x, max_y - y)
            for x, y, heights in self.voxel_data:
                new_x = self.max_x - x
                new_y = self.max_y - y
                rotated_data.append((new_x, new_y, heights))
                
        elif angle == 270:
            # 270도 시계방향 회전: (x, y) -> (-y, x) -> (max_y - y, x)
            for x, y, heights in self.voxel_data:
                new_x = self.max_y - y
                new_y = x
                rotated_data.append((new_x, new_y, heights))
        else:
            # 지원하지 않는 각도인 경우 변경하지 않음
            return

        self.voxel_data = rotated_data
        self._calculate_bounds()

    def get_footprint(self):
        """
        블록의 바닥 면적(발자국) 반환

        Returns:
            set: (x, y) 좌표 집합
        """
        return {(voxel[0], voxel[1]) for voxel in self.voxel_data}
    
    def get_boundary_footprint(self):
        """
        경계선 복셀만 추출 (성능 최적화용)
        
        Returns:
            set: 경계선 2D 좌표 집합 {(x, y), ...}
        """
        if not hasattr(self, '_boundary_cache') or self._boundary_cache is None:
            self._calculate_boundary_cache()
        return self._boundary_cache
    
    def _calculate_boundary_cache(self):
        """경계선 복셀 캐시 계산"""
        footprint = self.get_footprint()
        if not footprint:
            self._boundary_cache = set()
            return
        
        boundary = set()
        
        # 각 복셀에 대해 경계인지 확인
        for x, y in footprint:
            is_boundary = False
            
            # 8방향(상하좌우 대각선) 확인
            for dx in [-1, 0, 1]:
                for dy in [-1, 0, 1]:
                    if dx == 0 and dy == 0:
                        continue
                    
                    neighbor = (x + dx, y + dy)
                    if neighbor not in footprint:
                        # 인접한 셀이 비어있으면 경계선
                        is_boundary = True
                        break
                
                if is_boundary:
                    break
            
            if is_boundary:
                boundary.add((x, y))
        
        self._boundary_cache = boundary
        
        # 통계 출력 (디버깅용) - 비활성화
        # 성능 최적화: 경계선 복셀만 사용하여 계산량 대폭 감소

    def get_height_at(self, x, y):
        """
        지정된 (x, y) 위치에서의 블록 높이 반환

        Args:
            x (int): x 좌표
            y (int): y 좌표

        Returns:
            list or None: [empty_below, filled] 또는 해당 위치에 블록이 없는 경우 None
        """
        for vx, vy, heights in self.voxel_data:
            if vx == x and vy == y:
                return heights
        return None

    def get_total_volume(self):
        """
        블록의 총 부피 계산

        Returns:
            int: 블록의 총 부피 (채워진 공간의 합)
        """
        return sum(heights[1] for _, _, heights in self.voxel_data)

    def get_area(self):
        """
        블록의 바닥 면적 계산

        Returns:
            int: 블록의 바닥 면적 (복셀 수)
        """
        return len(self.voxel_data)

    def get_positioned_footprint(self):
        """
        배치된 위치를 고려한 블록의 바닥 면적 반환

        Returns:
            set: 배치된 위치에서의 (x, y) 좌표 집합, 배치되지 않은 경우 None
        """
        if self.position is None:
            return None

        pos_x, pos_y = self.position
        ref_x, ref_y = self.actual_reference
        return {(pos_x + voxel[0] - ref_x, pos_y + voxel[1] - ref_y)
                for voxel in self.voxel_data}

    def get_positioned_voxels(self):
        """
        배치된 위치를 고려한 블록의 복셀 데이터 반환

        Returns:
            list: 배치된 위치에서의 [(x, y, [empty_below, filled]), ...],
                  배치되지 않은 경우 None
        """
        if self.position is None:
            return None

        pos_x, pos_y = self.position
        ref_x, ref_y = self.actual_reference
        return [(pos_x + voxel[0] - ref_x, pos_y + voxel[1] - ref_y, voxel[2])
                for voxel in self.voxel_data]

    def clone(self):
        """
        블록의 복제본 생성

        Returns:
            VoxelBlock: 현재 블록의 복제본
        """
        # 깊은 복사를 사용하여 복셀 데이터 복제
        new_block = VoxelBlock(self.id, copy.deepcopy(self.voxel_data))

        # 회전 상태 복제
        new_block.rotation = self.rotation

        # 블록 타입 복제
        new_block.block_type = self.block_type

        # 위치 복제 (None이 아닌 경우에만)
        if self.position is not None:
            new_block.position = tuple(self.position)  # 튜플로 복제하여 불변성 보장
        else:
            new_block.position = None

        # 경계 계산 (이미 생성자에서 수행됨)

        return new_block

    def __str__(self):
        """블록 정보 문자열 표현"""
        return f"Block {self.id}: {len(self.voxel_data)} voxels, " \
               f"size: {self.width}x{self.height}, rotation: {self.rotation}°"
