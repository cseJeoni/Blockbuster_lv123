"""
블록 배치 후보 위치 생성기 모듈 (Y축 우선으로 수정)
"""
import numpy as np


class CandidateGenerator:
    """
    블록 배치 후보 위치 생성기 클래스 (Y축 우선)
    BinPacking 기반 후보 위치 생성 및 휴리스틱 점수 계산

    Attributes:
        placement_area (PlacementArea): 배치 영역
    """

    def __init__(self, placement_area):
        """
        CandidateGenerator 초기화

        Args:
            placement_area (PlacementArea): 배치 영역
        """
        self.placement_area = placement_area

    def generate_candidates(self, block, consider_rotation=True, max_candidates=20):
        """
        Y축을 최대한 채우기 위한 개선된 후보 위치 생성 (최적화됨)
        가로 긴 블록은 회전해서 Y축 활용도를 높임

        Args:
            block (VoxelBlock): 배치할 블록
            consider_rotation (bool): 회전 고려 여부
            max_candidates (int): 최대 후보 위치 수 (성능 최적화)

        Returns:
            list: (pos_x, pos_y, rotation, score) 형태의 후보 위치 목록
        """
        candidates = []

        if not consider_rotation:
            # 회전 고려 안 하는 경우: 기존 로직
            candidates = self._generate_candidates_for_orientation(block, max_candidates)
        else:
            # 🎯 Y축 최대 활용을 위한 회전 우선순위 결정
            original_width = block.width
            original_height = block.height
            
            # 회전 후 크기 계산
            rotated_width = original_height  
            rotated_height = original_width
            
            # Y축 활용도 비교 (높이가 클수록 Y축을 더 많이 활용)
            original_y_utilization = original_height / self.placement_area.height
            rotated_y_utilization = rotated_height / self.placement_area.height
            
            # 회전 후 배치 가능한지 확인
            can_rotate = (rotated_width <= self.placement_area.width and 
                         rotated_height <= self.placement_area.height)
            
            print(f"[DEBUG] 블록 {block.id}: {original_width}x{original_height}")
            print(f"        원본 Y활용도: {original_y_utilization:.2f}, 회전 Y활용도: {rotated_y_utilization:.2f}")
            print(f"        회전 가능: {can_rotate}")
            
            if can_rotate and rotated_y_utilization > original_y_utilization:
                # 🟢 회전했을 때 Y축을 더 많이 활용할 수 있는 경우: 회전 우선
                print(f"        → 회전 우선 시도 (Y축 활용도 향상: {original_y_utilization:.2f} → {rotated_y_utilization:.2f})")
                
                # 1. 회전된 방향 먼저 시도
                original_rotation = block.rotation
                block.rotate()
                
                rotated_candidates = self._generate_candidates_for_orientation(block, max_candidates//2)
                if rotated_candidates:  # 회전해서 배치 가능한 위치가 있는 경우
                    # Y축 활용도 향상 보너스
                    improvement_bonus = (rotated_y_utilization - original_y_utilization) * 0.5
                    for x, y, rotation, score in rotated_candidates:
                        bonus_score = score * (1.0 + improvement_bonus)
                        candidates.append((x, y, rotation, bonus_score))
                
                # 2. 원본 방향 (낮은 우선순위)
                block.rotation = original_rotation
                original_candidates = self._generate_candidates_for_orientation(block, max_candidates//2)
                candidates.extend(original_candidates)
                
            else:
                # 🔵 원본 방향이 Y축 활용도가 더 좋거나 회전 불가능한 경우: 원본 우선
                if not can_rotate:
                    print(f"        → 회전 불가능 (크기 초과)")
                else:
                    print(f"        → 원본 우선 (Y축 활용도 더 좋음)")
                
                # 1. 원본 방향 먼저 시도
                original_candidates = self._generate_candidates_for_orientation(block, max_candidates//2)
                candidates.extend(original_candidates)
                
                # 2. 회전 방향 (가능한 경우만)
                if can_rotate:
                    original_rotation = block.rotation
                    block.rotate()
                    rotated_candidates = self._generate_candidates_for_orientation(block, max_candidates//2)
                    candidates.extend(rotated_candidates)
                    block.rotation = original_rotation

        # 중복 제거
        unique_candidates = []
        seen = set()
        for x, y, rotation, score in candidates:
            key = (x, y, rotation)
            if key not in seen:
                seen.add(key)
                unique_candidates.append((x, y, rotation, score))

        # 점수에 따라 후보 위치 정렬 (내림차순)
        unique_candidates.sort(key=lambda x: x[3], reverse=True)

        return unique_candidates

    def _generate_candidates_for_orientation(self, block, max_candidates=20):
        """
        현재 블록 방향에 대한 후보 위치 생성 (최적화됨)

        Args:
            block (VoxelBlock): 배치할 블록
            max_candidates (int): 최대 후보 위치 수

        Returns:
            list: (pos_x, pos_y, rotation, score) 형태의 후보 위치 목록
        """
        candidates = []

        # 성능 최적화: 전체 탐색 대신 매우 적극적인 샘플링 방식 사용 (120x80 대응)
        step_x = max(3, self.placement_area.width // 10)  # 최대 10개 X 위치 (매우 성능 중시)
        step_y = max(3, self.placement_area.height // 6)  # 최대 6개 Y 위치 (매우 성능 중시)
        
        # 1. 기본 후보 위치들 (샘플링)
        for x in range(0, self.placement_area.width - block.width + 1, step_x):
            for y in range(0, self.placement_area.height - block.height + 1, step_y):
                if self.placement_area.can_place_block(block, x, y):
                    score = self._calculate_heuristic_score(block, x, y)
                    x_bonus = 1.0 - (x / self.placement_area.width)
                    score *= (1.0 + x_bonus)
                    candidates.append((x, y, block.rotation, score))
        
        # 2. 특별 위치들 (모서리, 기존 블록 인접)
        special_positions = [
            (0, 0),  # 왼쪽 위
            (0, self.placement_area.height - block.height),  # 왼쪽 아래
            (self.placement_area.width - block.width, 0),  # 오른쪽 위
        ]
        
        for x, y in special_positions:
            if (0 <= x <= self.placement_area.width - block.width and 
                0 <= y <= self.placement_area.height - block.height and
                self.placement_area.can_place_block(block, x, y)):
                score = self._calculate_heuristic_score(block, x, y)
                x_bonus = 1.0 - (x / self.placement_area.width)
                score *= (1.0 + x_bonus)
                candidates.append((x, y, block.rotation, score))

        # 특별한 위치 추가: 이미 배치된 블록에 인접한 위치
        for placed_block_id, placed_block in self.placement_area.placed_blocks.items():
            if placed_block.position is None:
                continue

            placed_x, placed_y = placed_block.position
            footprint = placed_block.get_positioned_footprint()

            # 배치된 블록 주변 위치 탐색
            for x, y in footprint:
                # 8방향 확인 (대각선 포함)
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0), (1, 1), (1, -1), (-1, 1), (-1, -1)]:
                    nx, ny = x + dx, y + dy

                    # 배치 영역 내에 있고 비어있는 위치인 경우
                    if (0 <= nx < self.placement_area.width and
                        0 <= ny < self.placement_area.height and
                        self.placement_area.grid[ny, nx] is None):

                        # 해당 위치에 블록 배치 가능 여부 확인
                        if self.placement_area.can_place_block(block, nx, ny):
                            # 휴리스틱 점수 계산 (인접성 가중치 증가)
                            score = self._calculate_heuristic_score(block, nx, ny) * 1.2  # 인접 위치 가중치 20% 증가
                            candidates.append((nx, ny, block.rotation, score))

        # 특별한 위치 추가: 빈 공간 채우기
        # 배치 영역의 빈 공간을 찾아 블록 배치 시도
        empty_spaces = self._find_empty_spaces()
        for space_x, space_y, space_width, space_height in empty_spaces:
            # 빈 공간에 블록 배치 가능 여부 확인
            if (space_width >= block.width and space_height >= block.height and
                self.placement_area.can_place_block(block, space_x, space_y)):
                # 휴리스틱 점수 계산 (빈 공간 채우기 가중치 증가)
                score = self._calculate_heuristic_score(block, space_x, space_y) * 1.5  # 빈 공간 채우기 가중치 50% 증가
                candidates.append((space_x, space_y, block.rotation, score))

        # 중복 제거
        unique_candidates = []
        seen = set()
        for x, y, rotation, score in candidates:
            key = (x, y, rotation)
            if key not in seen:
                seen.add(key)
                unique_candidates.append((x, y, rotation, score))

        return unique_candidates

    def _find_empty_spaces(self):
        """
        배치 영역의 빈 공간 찾기 (Y축 우선으로 수정)

        Returns:
            list: (x, y, width, height) 형태의 빈 공간 목록
        """
        empty_spaces = []
        grid = self.placement_area.grid
        width = self.placement_area.width
        height = self.placement_area.height

        # 빈 공간 찾기 (Y축 우선 순서로)
        for x in range(width):
            for y in range(height):
                # 이미 블록이 배치된 위치는 건너뜀
                if grid[y, x] is not None:
                    continue

                # 빈 공간의 너비와 높이 계산
                max_width = 1
                max_height = 1

                # 너비 계산
                for w in range(1, width - x):
                    if x + w < width and grid[y, x + w] is None:
                        max_width = w + 1
                    else:
                        break

                # 높이 계산
                for h in range(1, height - y):
                    is_empty_row = True
                    for w in range(max_width):
                        if y + h < height and x + w < width and grid[y + h, x + w] is None:
                            continue
                        else:
                            is_empty_row = False
                            break

                    if is_empty_row:
                        max_height = h + 1
                    else:
                        break

                # 빈 공간 추가
                if max_width > 1 or max_height > 1:
                    # Y축 방향 우선 배치를 위해 X값이 작은 빈 공간 우선
                    # X값이 같은 경우 Y값이 작은 빈 공간 우선

                    # 새로운 빈 공간 정보
                    new_space = (x, y, max_width, max_height)

                    # 빈 공간 목록에 삽입 (X값 오름차순, X값이 같으면 Y값 오름차순)
                    inserted = False
                    for i, (sx, sy, sw, sh) in enumerate(empty_spaces):
                        if x < sx or (x == sx and y < sy):
                            empty_spaces.insert(i, new_space)
                            inserted = True
                            break

                    if not inserted:
                        empty_spaces.append(new_space)

        return empty_spaces

    def _calculate_heuristic_score(self, block, pos_x, pos_y):
        """
        Y축 우선 배치를 위한 개선된 휴리스틱 점수 계산

        Args:
            block (VoxelBlock): 배치할 블록
            pos_x (int): 배치 위치 x 좌표
            pos_y (int): 배치 위치 y 좌표

        Returns:
            float: 휴리스틱 점수 (높을수록 좋음)
        """
        
        # 🎯 Y축 우선 점수 (기존 X축 우선에서 Y축 우선으로 수정)
        y_first_score = 1.0 - (pos_x / self.placement_area.width)  # 왼쪽부터 채우기
        
        # 위쪽 정렬 점수 
        top_alignment_score = 1.0 - (pos_y / self.placement_area.height)
        
        # Y축 활용도 점수 (블록이 Y축을 얼마나 활용하는가)
        y_utilization_score = block.height / self.placement_area.height
        
        # Y축 끝까지 채우기 보너스
        y_edge_bonus = 0
        if pos_y == 0:  # 위쪽 끝에서 시작
            y_edge_bonus += 0.1
        if pos_y + block.height == self.placement_area.height:  # 아래쪽 끝까지 채움
            y_edge_bonus += 0.2
        
        # 인접성 점수
        adjacency_score = self._calculate_adjacency_score(block, pos_x, pos_y)
        
        # 면적 활용 점수
        area_score = block.get_area() / (self.placement_area.width * self.placement_area.height)
        
        # 경계 활용 점수
        boundary_score = self._calculate_boundary_score(block, pos_x, pos_y)
        
        # 🎯 Y축 우선을 위한 가중치 (Y축 관련 점수에 높은 가중치)
        weights = {
            'y_first': 0.3,           # 왼쪽부터 채우기
            'top_align': 0.2,         # 위쪽 정렬
            'y_utilization': 0.25,    # Y축 활용도 (새로 추가!)
            'y_edge_bonus': 0.1,      # Y축 끝까지 채우기 보너스 (새로 추가!)
            'adjacency': 0.1,         # 인접성 (가중치 감소)
            'area': 0.03,             # 면적 (가중치 감소)
            'boundary': 0.02          # 경계 활용 (가중치 감소)
        }
        
        # 최종 점수 계산
        final_score = (
            weights['y_first'] * y_first_score +
            weights['top_align'] * top_alignment_score +
            weights['y_utilization'] * y_utilization_score +
            weights['y_edge_bonus'] * y_edge_bonus +
            weights['adjacency'] * adjacency_score +
            weights['area'] * area_score +
            weights['boundary'] * boundary_score
        )
        
        return final_score

    def _calculate_adjacency_score(self, block, pos_x, pos_y):
        """
        인접성 점수 계산

        Args:
            block (VoxelBlock): 배치할 블록
            pos_x (int): 배치 위치 x 좌표
            pos_y (int): 배치 위치 y 좌표

        Returns:
            float: 인접성 점수 (0~1, 높을수록 좋음)
        """
        adjacent_count = 0
        total_perimeter = 0

        # 블록의 바닥 면적 계산
        footprint = block.get_footprint()

        for vx, vy in footprint:
            # 블록 좌표를 배치 영역 좌표로 변환
            grid_x = pos_x + vx - block.min_x
            grid_y = pos_y + vy - block.min_y

            # 배치 영역 내에 있는지 확인
            if 0 <= grid_x < self.placement_area.width and 0 <= grid_y < self.placement_area.height:
                # 4방향 확인
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    nx, ny = grid_x + dx, grid_y + dy

                    # 배치 영역 내에 있고 다른 블록과 인접한 경우
                    if 0 <= nx < self.placement_area.width and 0 <= ny < self.placement_area.height:
                        total_perimeter += 1
                        if self.placement_area.grid[ny, nx] is not None:
                            adjacent_count += 1

        # 인접성 점수 계산
        return adjacent_count / total_perimeter if total_perimeter > 0 else 0

    def _calculate_boundary_score(self, block, pos_x, pos_y):
        """
        경계 활용 점수 계산

        Args:
            block (VoxelBlock): 배치할 블록
            pos_x (int): 배치 위치 x 좌표
            pos_y (int): 배치 위치 y 좌표

        Returns:
            float: 경계 활용 점수 (0~1, 높을수록 좋음)
        """
        boundary_count = 0
        total_perimeter = 0

        # 블록의 바닥 면적 계산
        footprint = block.get_footprint()

        for vx, vy in footprint:
            # 블록 좌표를 배치 영역 좌표로 변환
            grid_x = pos_x + vx - block.min_x
            grid_y = pos_y + vy - block.min_y

            # 배치 영역 내에 있는지 확인
            if 0 <= grid_x < self.placement_area.width and 0 <= grid_y < self.placement_area.height:
                # 4방향 확인
                for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                    nx, ny = grid_x + dx, grid_y + dy

                    total_perimeter += 1

                    # 배치 영역 경계에 인접한 경우
                    if nx < 0 or nx >= self.placement_area.width or ny < 0 or ny >= self.placement_area.height:
                        boundary_count += 1

        # 경계 활용 점수 계산
        return boundary_count / total_perimeter if total_perimeter > 0 else 0