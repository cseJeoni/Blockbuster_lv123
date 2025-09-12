"""
배치 영역 관리를 위한 모듈
"""
import numpy as np
import copy


class PlacementArea:
    """
    블록 배치 영역 관리 클래스

    Attributes:
        width (int): 배치 영역의 너비
        height (int): 배치 영역의 높이
        grid (numpy.ndarray): 배치 상태를 저장하는 그리드
        placed_blocks (dict): 배치된 블록 정보 {block_id: block}
        unplaced_blocks (dict): 미배치된 블록 정보 {block_id: block}
    """

    def __init__(self, width, height):
        """
        PlacementArea 초기화

        Args:
            width (int): 배치 영역의 너비
            height (int): 배치 영역의 높이
        """
        self.width = width
        self.height = height
        # 각 셀에는 해당 위치에 배치된 블록의 ID가 저장됨
        self.grid = np.full((height, width), None, dtype=object)
        self.placed_blocks = {}  # {block_id: block}
        self.unplaced_blocks = {}  # {block_id: block}
        
        # 배치 순서 추적
        self.placement_order = []  # [(block_id, order_number), ...]
        self.current_placement_number = 0

        # 트랜스포터 진입 경로 관리를 위한 그리드
        self.path_grid = np.zeros((height, width), dtype=int)

    def add_blocks(self, blocks):
        """
        배치할 블록 목록 추가

        Args:
            blocks (list): VoxelBlock 객체 목록
        """
        for block in blocks:
            self.unplaced_blocks[block.id] = block

    def can_place_block(self, block, pos_x, pos_y):
        """
        해당 위치에 블록 배치 가능 여부 확인

        Args:
            block (VoxelBlock): 배치할 블록
            pos_x (int): 배치 위치 x 좌표
            pos_y (int): 배치 위치 y 좌표

        Returns:
            bool: 배치 가능 여부
        """
        # 4391_643_000, 4391_653_000 블록에 대한 디버깅
        debug_target = block.id in ["4391_643_000", "4391_653_000"]
        
        # 블록의 바닥 면적 계산
        footprint = block.get_footprint()

        # 배치 영역 내에 있는지 확인
        ref_x, ref_y = block.actual_reference
        for vx, vy in footprint:
            # 블록 좌표를 배치 영역 좌표로 변환 (실제 복셀 기준)
            grid_x = pos_x + vx - ref_x
            grid_y = pos_y + vy - ref_y

            # 배치 영역을 벗어나는지 확인
            if grid_x < 0 or grid_x >= self.width or grid_y < 0 or grid_y >= self.height:
                if debug_target:
                    print(f"          영역 벗어남: 복셀({vx},{vy}) → 격자({grid_x},{grid_y}), 영역범위: 0~{self.width-1}, 0~{self.height-1}")
                return False

            # 다른 블록과 겹치는지 확인
            if self.grid[grid_y, grid_x] is not None:
                if debug_target:
                    print(f"          블록 겹침: 격자({grid_x},{grid_y})에 이미 {self.grid[grid_y, grid_x]} 존재")
                    print(f"            현재 블록 복셀: ({vx},{vy}) → 격자({grid_x},{grid_y})")
                    print(f"            기준점: {block.actual_reference}, 배치위치: ({pos_x},{pos_y})")
                return False

        # 트랜스포터 진입 가능성 확인
        if not self._check_transporter_access(block, pos_x, pos_y):
            if debug_target:
                print(f"          트랜스포터 접근성 실패")
            return False

        return True

    def _check_transporter_access(self, block, pos_x, pos_y):
        """
        블록 접근성 확인
        - 크레인 블록: 수직으로 내려놓을 수 있어서 경로 확보 불필요
        - 트레슬 블록: 오른쪽에서 Y길이만큼 경로 폭 확보 필요
        - 기타: 트레슬 블록과 동일한 조건

        Args:
            block (VoxelBlock): 배치할 블록
            pos_x (int): 배치 위치 x 좌표  
            pos_y (int): 배치 위치 y 좌표

        Returns:
            bool: 블록 접근 가능 여부
        """
        # 크레인 블록은 수직으로 내려놓을 수 있어서 경로 확보 불필요
        if hasattr(block, 'block_type') and block.block_type == 'crane':
            return True  # 크레인 블록은 항상 접근 가능
        
        # 트레슬 블록과 기타 블록은 트랜스포터 경로 확보 필요
        # 블록의 Y 범위만 체크 (어제 버전과 동일)
        block_y_start = pos_y
        block_y_end = pos_y + block.height
        
        # 배치 영역 왼쪽 끝에서 블록의 왼쪽 끝까지 경로 확인
        block_left_edge = pos_x
        
        # 왼쪽 끝에서 블록 위치까지 쭉 밀어넣을 수 있는지 확인 (Y 여유 포함)
        for x in range(0, block_left_edge):
            for y in range(block_y_start, block_y_end):
                if y < 0 or y >= self.height or self.grid[y, x] is not None:
                    return False
        
        return True

    def _has_path_to_edge(self, grid, start_x, start_y):
        """
        시작 위치에서 가장자리까지 경로가 있는지 확인 (BFS)

        Args:
            grid (numpy.ndarray): 배치 상태 그리드
            start_x (int): 시작 위치 x 좌표
            start_y (int): 시작 위치 y 좌표

        Returns:
            bool: 가장자리까지 경로 존재 여부
        """
        from collections import deque

        # 이미 가장자리인 경우
        if start_x == 0 or start_x == self.width - 1 or start_y == 0 or start_y == self.height - 1:
            return True

        # BFS를 위한 큐 초기화
        queue = deque([(start_x, start_y)])
        visited = np.zeros((self.height, self.width), dtype=bool)
        visited[start_y, start_x] = True

        while queue:
            x, y = queue.popleft()

            # 4방향 탐색
            for dx, dy in [(0, 1), (1, 0), (0, -1), (-1, 0)]:
                nx, ny = x + dx, y + dy

                # 배치 영역 내에 있는지 확인
                if 0 <= nx < self.width and 0 <= ny < self.height:
                    # 가장자리에 도달한 경우
                    if nx == 0 or nx == self.width - 1 or ny == 0 or ny == self.height - 1:
                        return True

                    # 빈 공간이고 방문하지 않은 경우
                    if grid[ny, nx] is None and not visited[ny, nx]:
                        queue.append((nx, ny))
                        visited[ny, nx] = True

        return False

    def place_block(self, block, pos_x, pos_y):
        """
        블록을 해당 위치에 배치

        Args:
            block (VoxelBlock): 배치할 블록
            pos_x (int): 배치 위치 x 좌표
            pos_y (int): 배치 위치 y 좌표

        Returns:
            bool: 배치 성공 여부
        """
        if not self.can_place_block(block, pos_x, pos_y):
            return False

        # 블록 위치 설정
        block.position = (pos_x, pos_y)

        # 그리드에 블록 배치
        footprint = block.get_footprint()
        ref_x, ref_y = block.actual_reference
        for vx, vy in footprint:
            grid_x = pos_x + vx - ref_x
            grid_y = pos_y + vy - ref_y
            self.grid[grid_y, grid_x] = block.id

        # 배치된 블록 목록 업데이트
        self.placed_blocks[block.id] = block
        if block.id in self.unplaced_blocks:
            del self.unplaced_blocks[block.id]
        
        # 배치 순서 기록 (새로 배치되는 경우만)
        if not any(order[0] == block.id for order in self.placement_order):
            self.current_placement_number += 1
            self.placement_order.append((block.id, self.current_placement_number))

        return True

    def remove_block(self, block_id):
        """
        배치된 블록 제거 (백트래킹용)

        Args:
            block_id (str): 제거할 블록 ID

        Returns:
            bool: 제거 성공 여부
        """
        if block_id not in self.placed_blocks:
            return False

        block = self.placed_blocks[block_id]

        # 그리드에서 블록 제거 (배치와 동일한 방식 사용)
        footprint = block.get_footprint()
        ref_x, ref_y = block.actual_reference
        pos_x, pos_y = block.position
        for vx, vy in footprint:
            grid_x = pos_x + vx - ref_x
            grid_y = pos_y + vy - ref_y
            if 0 <= grid_x < self.width and 0 <= grid_y < self.height:
                self.grid[grid_y, grid_x] = None

        # 블록 위치 초기화
        block.position = None

        # 배치된 블록 목록 업데이트
        del self.placed_blocks[block_id]
        self.unplaced_blocks[block_id] = block

        return True

    def get_placement_score(self):
        """
        현재 배치 상태의 점수 계산

        Returns:
            float: 배치 점수 (높을수록 좋음)
        """
        # 배치된 블록의 총 면적
        placed_area = sum(block.get_area() for block in self.placed_blocks.values())

        # 배치된 블록의 비율
        placement_ratio = len(self.placed_blocks) / (len(self.placed_blocks) + len(self.unplaced_blocks)) if self.placed_blocks or self.unplaced_blocks else 0

        # 공간 활용률
        space_utilization = placed_area / (self.width * self.height)

        # 가중치를 적용한 종합 점수
        score = 0.5 * placement_ratio + 0.5 * space_utilization

        return score

    def clone(self):
        """
        배치 영역의 복제본 생성

        Returns:
            PlacementArea: 현재 배치 영역의 복제본
        """
        new_area = PlacementArea(self.width, self.height)
        new_area.grid = np.copy(self.grid)

        # 블록 복제
        for block_id, block in self.placed_blocks.items():
            new_area.placed_blocks[block_id] = block.clone()

        for block_id, block in self.unplaced_blocks.items():
            new_area.unplaced_blocks[block_id] = block.clone()

        return new_area

    def calculate_cluster_dead_space(self):
        """
        덩어리 기반 Dead Space 지표 계산
        EXPERIMENTAL_DESIGN.md의 새로운 성능 지표 구현
        
        Returns:
            dict: Dead Space 분석 결과
                - cluster_efficiency: 덩어리 효율성 (0-1)
                - dead_space_ratio: 덩어리 내 빈공간 비율 (0-1)  
                - cluster_area: 덩어리 면적
                - actual_area: 실제 블록 면적
                - traditional_utilization: 기존 공간활용률
                - space_saving_ratio: 공간 절약 비율
        """
        if not self.placed_blocks:
            return {
                'cluster_efficiency': 0.0,
                'dead_space_ratio': 1.0,
                'cluster_area': 0,
                'actual_area': 0,
                'traditional_utilization': 0.0,
                'space_saving_ratio': 0.0,
                'cluster_bbox': (0, 0, 0, 0)
            }
        
        # Step 1: 배치된 블록들의 바운딩 박스(덩어리) 계산 (spacing 포함)
        all_cells_set = set()
        actual_area = 0
        spacing = getattr(self, 'block_spacing', 0)
        
        for block in self.placed_blocks.values():
            if block.position is not None:
                pos_x, pos_y = block.position
                ref_x, ref_y = block.actual_reference
                
                # 블록의 실제 셀들
                block_cells = set()
                for vx, vy in block.get_footprint():
                    cell_x = pos_x + vx - ref_x
                    cell_y = pos_y + vy - ref_y
                    block_cells.add((cell_x, cell_y))
                
                # spacing을 포함한 확장 영역 추가 (배치 공간 범위 내에서만)
                for cell_x, cell_y in block_cells:
                    for dx in range(-spacing, spacing + 1):
                        for dy in range(-spacing, spacing + 1):
                            expanded_x = cell_x + dx
                            expanded_y = cell_y + dy
                            # 배치 공간 범위 내에서만 추가
                            if (0 <= expanded_x < self.width and 
                                0 <= expanded_y < self.height):
                                all_cells_set.add((expanded_x, expanded_y))
                
                actual_area += block.get_area()
        
        all_cells = list(all_cells_set)  # 중복 제거된 셀 목록
        
        if not all_cells:
            return {
                'cluster_efficiency': 0.0,
                'dead_space_ratio': 1.0,
                'cluster_area': 0,
                'actual_area': 0,
                'traditional_utilization': 0.0,
                'space_saving_ratio': 0.0,
                'cluster_bbox': (0, 0, 0, 0)
            }
        
        # Step 2: 개선된 덩어리 바운딩 박스 계산 (왼쪽 경계 최적화)
        x_coords = [cell[0] for cell in all_cells]
        y_coords = [cell[1] for cell in all_cells]
        
        min_y, max_y = min(y_coords), max(y_coords)
        max_x = max(x_coords)  # 오른쪽은 기존 방식 유지
        
        # 왼쪽 경계: Y별로 가장 왼쪽 블록 찾기 (블록 모양 반영)
        cells_by_y = {}
        for cell_x, cell_y in all_cells:
            if cell_y not in cells_by_y:
                cells_by_y[cell_y] = []
            cells_by_y[cell_y].append(cell_x)
        
        # Y별 왼쪽 경계의 평균값 계산 (극단값 제외)
        left_boundaries = []
        for y in range(min_y, max_y + 1):
            if y in cells_by_y:
                left_boundaries.append(min(cells_by_y[y]))
        
        if left_boundaries:
            # 극단값 제거 후 평균 계산 (상위 20% 제거)
            left_boundaries.sort()
            trim_count = max(1, len(left_boundaries) // 5)  # 20% 제거
            trimmed_boundaries = left_boundaries[:-trim_count] if trim_count < len(left_boundaries) else left_boundaries
            min_x = int(sum(trimmed_boundaries) / len(trimmed_boundaries))
        else:
            min_x = min(x_coords)  # fallback
        
        cluster_width = max_x - min_x + 1
        cluster_height = max_y - min_y + 1
        cluster_area = cluster_width * cluster_height
        cluster_bbox = (min_x, min_y, max_x, max_y)
        
        # Step 3: 덩어리 효율성 계산
        cluster_efficiency = actual_area / cluster_area if cluster_area > 0 else 0.0
        dead_space_ratio = 1 - cluster_efficiency
        
        # Step 4: 기존 방식과 비교
        total_ship_area = self.width * self.height
        traditional_utilization = actual_area / total_ship_area if total_ship_area > 0 else 0.0
        space_saving_ratio = cluster_area / total_ship_area if total_ship_area > 0 else 0.0
        
        return {
            'cluster_efficiency': cluster_efficiency,
            'dead_space_ratio': dead_space_ratio,
            'cluster_area': cluster_area,
            'actual_area': actual_area,
            'traditional_utilization': traditional_utilization,
            'space_saving_ratio': space_saving_ratio,
            'cluster_bbox': cluster_bbox,
            'cluster_dimensions': (cluster_width, cluster_height),
            'left_boundary_by_y': cells_by_y  # Y별 블록 위치 정보 추가
        }
    
    def get_enhanced_placement_metrics(self):
        """
        확장된 배치 성능 지표 계산
        기존 지표 + Dead Space 지표 통합
        
        Returns:
            dict: 전체 성능 지표
        """
        # 기존 지표
        placed_blocks_count = len(self.placed_blocks)
        total_blocks_count = len(self.placed_blocks) + len(self.unplaced_blocks)
        placement_rate = placed_blocks_count / total_blocks_count if total_blocks_count > 0 else 0.0
        
        # Dead Space 지표
        dead_space_metrics = self.calculate_cluster_dead_space()
        
        # 통합 지표
        return {
            # 기본 지표
            'placement_rate': placement_rate,
            'placed_blocks_count': placed_blocks_count,
            'total_blocks_count': total_blocks_count,
            'unplaced_blocks_count': len(self.unplaced_blocks),
            
            # 새로운 지표 (EXPERIMENTAL_DESIGN.md 기준)
            'cluster_efficiency': dead_space_metrics['cluster_efficiency'],
            'dead_space_ratio': dead_space_metrics['dead_space_ratio'],
            'cluster_area': dead_space_metrics['cluster_area'],
            'actual_area': dead_space_metrics['actual_area'],
            
            # 비교 지표  
            'traditional_utilization': dead_space_metrics['traditional_utilization'],
            'space_saving_ratio': dead_space_metrics['space_saving_ratio'],
            
            # 상세 정보
            'cluster_bbox': dead_space_metrics['cluster_bbox'],
            'cluster_dimensions': dead_space_metrics['cluster_dimensions']
        }

    def __str__(self):
        """배치 영역 정보 문자열 표현"""
        return f"PlacementArea {self.width}x{self.height}: " \
               f"{len(self.placed_blocks)} placed, {len(self.unplaced_blocks)} unplaced"
