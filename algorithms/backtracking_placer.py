"""
실용적인 백트래킹 배치 알고리즘
"""
import time
import copy


class PracticalBacktracking:
    
    def __init__(self, placement_area, blocks, max_time=60):
        self.placement_area = placement_area
        self.blocks = blocks
        self.best_solution = None
        self.best_score = 0
        self.max_time = max_time
        self.start_time = 0
        self.placement_area.add_blocks(blocks)
    
    def optimize(self):
        self.start_time = time.time()
        self.best_solution = None
        self.best_score = 0
        sorted_blocks = sorted(self.blocks, key=lambda b: -b.get_area())
        print(f"[DEBUG] Starting backtrack with {len(sorted_blocks)} blocks")
        initial_area = copy.deepcopy(self.placement_area)
        try:
            self._backtrack(initial_area, sorted_blocks, 0)
        except Exception as e:
            print(f"[DEBUG] Backtrack failed with error: {e}")
            import traceback
            traceback.print_exc()
            return None
        
        # 부분 배치라도 최선의 결과를 반환
        if self.best_solution is None:
            # 아무것도 배치되지 않았다면 초기 상태라도 반환
            self.best_solution = initial_area
        
        placed_count = len(self.best_solution.placed_blocks) if self.best_solution else 0
        print(f"[DEBUG] Backtrack completed: {placed_count} blocks placed")
        return self.best_solution
    
    def _backtrack(self, current_area, blocks, depth):
        if time.time() - self.start_time > self.max_time:
            return False
        
        # 현재 상태가 최선인지 확인 (블록 개수 우선, 점수 보조)
        current_placed = len(current_area.placed_blocks)
        current_score = current_area.get_placement_score()
        best_placed = len(self.best_solution.placed_blocks) if self.best_solution else 0
        
        # 더 많은 블록이 배치되었거나, 같은 개수에서 더 좋은 점수면 업데이트
        if (current_placed > best_placed or 
            (current_placed == best_placed and current_score > self.best_score)):
            self.best_score = current_score
            self.best_solution = copy.deepcopy(current_area)
            if current_placed > 0:  # 0개 배치는 출력 안 함
                print(f"[DEBUG] New best: {current_placed} blocks placed")
        
        if depth >= len(blocks):
            return True
        block = blocks[depth]
        max_cands = min(25, len(current_area.placed_blocks) * 6 + 15)
        candidates = self._get_simple_candidates(current_area, block, max_candidates=max_cands)
        found_any_solution = False
        
        # 첫 번째 블록에서 후보가 없으면 알림
        if depth == 0 and len(candidates) == 0:
            print(f"[DEBUG] No candidates for first block {block.id} ({block.width}x{block.height})")
        
        if not candidates:
            return False
        for i, (pos_x, pos_y) in enumerate(candidates):
            if time.time() - self.start_time > self.max_time:
                return found_any_solution
            
            # 변경사항 2: 회전 고려 대신 무조건 긴쪽이 Y가 되도록 이미 처리됨
            if current_area.can_place_block(block, pos_x, pos_y):
                current_area.place_block(block, pos_x, pos_y)
                if self._backtrack(current_area, blocks, depth + 1):
                    found_any_solution = True
                    if depth + 1 >= len(blocks):
                        current_area.remove_block(block.id)
                        return True
                current_area.remove_block(block.id)
                
        # 현재 블록을 건너뛰고 다음 블록으로 진행 (부분 배치 허용)
        if self._backtrack(current_area, blocks, depth + 1):
            found_any_solution = True
        return found_any_solution
    
    def _get_simple_candidates(self, area, block, max_candidates=20):
        candidates = []
        placed_count = len(area.placed_blocks)
        density_factor = min(2.0, 1.0 + placed_count * 0.1)
        step_x = max(1, int(area.width // (12 * density_factor)))
        step_y = max(1, int(area.height // (8 * density_factor)))
        
        base_positions = []
        # 변경사항 2: 원본 방향만 (긴쪽이 Y가 되도록 이미 처리됨)
        for x in range(area.width - block.width, -1, -step_x):
            for y in range(0, area.height - block.height + 1, step_y):
                base_positions.append((x, y))
        
        base_positions.sort(key=lambda pos: (-pos[0], pos[1]))
        strategic_positions = []
        placed_blocks = list(area.placed_blocks.values())
        is_first_block = len(placed_blocks) == 0
        
        bow_clearance = getattr(area, 'bow_clearance', 0)
        stern_clearance = getattr(area, 'stern_clearance', 0)
        
        if is_first_block:
            # 원본 방향만 시도
            first_x = area.width - bow_clearance - block.width
            first_y = 0
            if first_x >= 0 and first_y >= 0 and first_y + block.height <= area.height:
                strategic_positions.append((first_x, first_y))
        
        # 간단한 테스트 위치들도 추가
        simple_positions = []
        for test_x in [0, 5, 10, 20, 30]:
            for test_y in [0, 5, 10]:
                # 원본 방향만
                if (test_x + block.width <= area.width and 
                    test_y + block.height <= area.height):
                    simple_positions.append((test_x, test_y))
        
        all_positions = strategic_positions + base_positions + simple_positions
        seen = set()
        unique_positions = []
        for pos in all_positions:
            if pos not in seen:
                seen.add(pos)
                unique_positions.append(pos)
        
        candidates = []
        for i, (x, y) in enumerate(unique_positions):
            # 원본 방향만 시도 (회전 제거)
            if area.can_place_block(block, x, y):
                score = self._calculate_quick_score(area, block, x, y)
                candidates.append((x, y, False, score))
            
        candidates.sort(key=lambda c: (c[3], c[0], -c[1]), reverse=True)
        final_candidates = [(x, y) for x, y, _, score in candidates[:max_candidates]]
        return final_candidates
    
    def _calculate_quick_score(self, area, block, x, y):
        score = 0
        bow_clearance = getattr(area, 'bow_clearance', 0)
        stern_clearance = getattr(area, 'stern_clearance', 0)
        
        right_preference = (x - stern_clearance) / (area.width - bow_clearance - stern_clearance)
        score += right_preference * 100
        bottom_preference = (area.height - y) / area.height
        score += bottom_preference * 30
        if x + block.width == area.width - bow_clearance:
            score += 40
        if y == 0:
            score += 30
        placed_blocks = list(area.placed_blocks.values())
        if placed_blocks:
            closest_distance = float('inf')
            for placed_block in placed_blocks:
                if placed_block.position:
                    px, py = placed_block.position
                    distance = abs(x - px) + abs(y - py)
                    closest_distance = min(closest_distance, distance)
            if closest_distance != float('inf'):
                score += max(0, 20 - closest_distance * 2)
        return score