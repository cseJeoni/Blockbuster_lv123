"""
회전 최적화 그리디 기반 블록 배치 알고리즘
트레슬 블록의 경우 180도 회전을 고려하여 deadspace가 적은 방향으로 배치
"""
import time
import copy
import os
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from datetime import datetime
from .greedy_placer import GreedyPlacer


class RotationOptimizedGreedyPlacer(GreedyPlacer):
    """
    회전 최적화 그리디 배치기
    
    기존 GreedyPlacer를 상속받아 트레슬 블록에 대해 180도 회전 최적화를 추가
    """
    
    def __init__(self, placement_area, blocks, max_time=60, enable_rotation_optimization=True, save_deadspace_visualization=False):
        super().__init__(placement_area, blocks, max_time)
        self.enable_rotation_optimization = enable_rotation_optimization
        self.save_deadspace_visualization = save_deadspace_visualization
        self.rotation_attempts = 0
        self.rotation_improvements = 0
        self.deadspace_visualizations = []
        
        # 강제 회전 블록 리스트 (현재 비활성화)
        self.force_rotation_blocks = set()  # {'4391_293_000', '4391_283_000'}
        
    def place_all_blocks(self):
        """메인 최적화 프로세스 (회전 최적화 포함)"""
        self.start_time = time.time()
        sorted_blocks = sorted(self.blocks, key=lambda b: -b.get_area())
        
        placed_count = 0
        unplaced_blocks = []
        
        try:
            # 첫 번째 패스: 모든 블록 배치 시도 (회전 최적화 포함)
            for i, block in enumerate(sorted_blocks):
                if time.time() - self.start_time > self.max_time:
                    break
                
                # 후보 위치 생성
                max_cands = min(25, len(self.placement_area.placed_blocks) * 6 + 15)
                candidates = self._get_tight_candidates(self.placement_area, block, max_candidates=max_cands)
                
                if not candidates:
                    unplaced_blocks.append(block)
                    continue
                
                # 회전 최적화 배치 시도
                placed = self._place_with_rotation_check(block, candidates)
                
                if placed:
                    placed_count += 1
                    
                    # 트레슬 블록은 이미 좁히기가 완료됨, 일반 블록만 좁히기 적용
                    if not self._is_trestle_block(block) or not self.enable_rotation_optimization:
                        try:
                            bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
                            spacing = getattr(self.placement_area, 'block_spacing', 4)
                            
                            # 일반 블록 좁히기 적용
                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                            self._compact_block_down(self.placement_area, block, spacing)
                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                        except Exception as e:
                            print(f"[ERROR] {block.id} 좁히기 로직 실행 중 오류: {e}")
                    else:
                        # 트레슬 블록은 회전 최적화시 이미 좁히기 적용됨
                        pass
                else:
                    unplaced_blocks.append(block)
            
            # 두 번째 패스: 배치 못한 블록들 재시도 (기존과 동일)
            if unplaced_blocks and time.time() - self.start_time < self.max_time:
                # 배치 못한 블록들 재시도
                retry_count = 0
                successfully_placed = []
                
                unplaced_blocks.sort(key=lambda b: b.get_area())
                
                for block in unplaced_blocks:
                    if time.time() - self.start_time > self.max_time:
                        break
                    
                    max_cands = min(50, len(self.placement_area.placed_blocks) * 10 + 30)
                    candidates = self._get_tight_candidates(self.placement_area, block, max_candidates=max_cands)
                    
                    # 재시도에서도 회전 최적화 적용
                    placed = self._place_with_rotation_check(block, candidates)
                    
                    if placed:
                        retry_count += 1
                        successfully_placed.append(block)
                        
                        try:
                            bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
                            spacing = getattr(self.placement_area, 'block_spacing', 4)
                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                            self._compact_block_down(self.placement_area, block, spacing)
                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                        except:
                            pass
                
                for block in successfully_placed:
                    if block in unplaced_blocks:
                        unplaced_blocks.remove(block)
                
                if retry_count > 0:
                    # 재시도 배치 완료
                    placed_count += retry_count
        
        except Exception as e:
            return None
        
        # 결과 정리 (기존과 동일)
        placed_block_ids = set(self.placement_area.placed_blocks.keys())
        all_block_ids = {block.id for block in self.blocks}
        actual_unplaced_ids = all_block_ids - placed_block_ids
        self.placement_area.unplaced_blocks = list(actual_unplaced_ids)
        
        # 회전 최적화 통계 출력
        if self.enable_rotation_optimization and self.rotation_attempts > 0:
            improvement_rate = (self.rotation_improvements / self.rotation_attempts) * 100
            print(f"[INFO] 회전 최적화: {self.rotation_improvements}/{self.rotation_attempts}회 개선 ({improvement_rate:.1f}%)")
        
        return self.placement_area
    
    def _place_with_rotation_check(self, block, candidates):
        """
        회전 최적화를 적용한 블록 배치
        
        Args:
            block: 배치할 블록
            candidates: 후보 위치 리스트
            
        Returns:
            bool: 배치 성공 여부
        """
        # 강제 회전 블록인지 확인
        if self._is_force_rotation_block(block):
            return self._place_block_force_rotation(block, candidates)
        
        # 트레슬 블록이 아니면 기존 방식으로 배치
        if not self._is_trestle_block(block) or not self.enable_rotation_optimization:
            return self._place_block_simple(block, candidates)
        
        # 트레슬 블록의 경우 원본과 180도 회전 두 방향 모두 시도 (좁히기 후 비교)
        best_placement = None
        best_deadspace = float('inf')
        
        # 원본 블록으로 시도 (좁히기 포함)
        original_result = self._test_placement_with_compaction(block, candidates, rotation=0)
        if original_result:
            best_placement = original_result
            best_deadspace = original_result['final_deadspace']
            print(f"[DEBUG] {block.id} 원본 (좁히기 후): deadspace={best_deadspace:.4f} at {original_result['final_position']}")
        
        # 180도 회전 블록으로 시도 (좁히기 포함)
        rotated_block = self._create_rotated_block(block, 180)
        if rotated_block:
            # 제자리 회전을 위한 위치 보정된 후보들 생성
            adjusted_candidates = self._adjust_candidates_for_rotation(block, rotated_block, candidates)
            rotated_result = self._test_placement_with_compaction(rotated_block, adjusted_candidates, rotation=180)
            if rotated_result:
                print(f"[DEBUG] {block.id} 회전 (좁히기 후): deadspace={rotated_result['final_deadspace']:.4f} at {rotated_result['final_position']}")
                if rotated_result['final_deadspace'] < best_deadspace:
                    best_placement = rotated_result
                    best_deadspace = rotated_result['final_deadspace']
                    self.rotation_improvements += 1
                    print(f"[DEBUG] {block.id} 회전이 더 좋음! (좁히기 후 개선: {best_deadspace:.4f})")
                else:
                    print(f"[DEBUG] {block.id} 원본이 더 좋음 (좁히기 후)")
        
        self.rotation_attempts += 1
        
        # 최적 배치 적용 (좁히기 포함)
        if best_placement:
            # 최종 위치에 배치
            success = self.placement_area.place_block(best_placement['block'], 
                                                    best_placement['final_position'][0], 
                                                    best_placement['final_position'][1])
            if success:
                print(f"[INFO] {block.id} 회전 최적화 배치 (좁히기 후): rotation={best_placement['rotation']}°, "
                      f"initial={best_placement['initial_position']} → final={best_placement['final_position']}, "
                      f"deadspace={best_placement['final_deadspace']:.4f}")
                return True
        
        return False
    
    def _is_trestle_block(self, block):
        """블록이 트레슬 블록인지 확인"""
        block_type = getattr(block, 'block_type', 'unknown')
        return block_type == 'trestle'
    
    def _is_force_rotation_block(self, block):
        """블록이 강제 회전 대상인지 확인"""
        return block.id in self.force_rotation_blocks
    
    def _get_placed_block(self, block_id):
        """배치된 블록 객체 가져오기"""
        if block_id in self.placement_area.placed_blocks:
            placed_item = self.placement_area.placed_blocks[block_id]
            # placed_blocks 구조 확인: 딕셔너리인지 VoxelBlock 객체인지
            if isinstance(placed_item, dict):
                return placed_item['block']
            else:
                # 직접 VoxelBlock 객체인 경우
                return placed_item
        return None
    
    def _place_block_force_rotation(self, block, candidates):
        """
        강제 180도 회전 배치 (데드스페이스 고려 없이, 제약 조건 무시)
        
        Args:
            block: 배치할 블록
            candidates: 후보 위치 리스트
            
        Returns:
            bool: 배치 성공 여부
        """
        print(f"[INFO] {block.id} 강제 180도 회전 배치 시도")
        
        # 회전된 블록 생성
        rotated_block = self._create_rotated_block(block, 180)
        if not rotated_block:
            print(f"[ERROR] {block.id} 회전 블록 생성 실패")
            return False
        
        # 제자리 회전을 위한 위치 보정
        adjusted_candidates = self._adjust_candidates_for_rotation(block, rotated_block, candidates)
        
        # 강제 배치 시도 (제약 조건 무시)
        for pos_x, pos_y in adjusted_candidates:
            # 일반 제약 조건 체크
            if self.placement_area.can_place_block(rotated_block, pos_x, pos_y):
                # 제약 조건을 만족하는 경우 정상 배치
                if self.placement_area.place_block(rotated_block, pos_x, pos_y):
                    print(f"[SUCCESS] {block.id} 강제 회전 배치 성공 (제약조건 만족): ({pos_x}, {pos_y})")
                    return True
            else:
                # 제약 조건 위배 시 강제 배치 시도
                print(f"[WARNING] {block.id} 제약조건 위배 at ({pos_x}, {pos_y}) - 강제 배치 시도")
                
                # 제약 조건 무시하고 강제 배치
                if self._force_place_block_ignoring_constraints(rotated_block, pos_x, pos_y):
                    print(f"[SUCCESS] {block.id} 강제 회전 배치 성공 (제약조건 무시): ({pos_x}, {pos_y})")
                    return True
                else:
                    print(f"[ERROR] {block.id} 강제 배치도 실패 at ({pos_x}, {pos_y})")
        
        print(f"[ERROR] {block.id} 모든 후보 위치에서 강제 배치 실패")
        return False
    
    def _force_place_block_ignoring_constraints(self, block, pos_x, pos_y):
        """
        제약 조건을 무시하고 블록을 강제 배치
        
        Args:
            block: 배치할 블록
            pos_x, pos_y: 배치 위치
            
        Returns:
            bool: 배치 성공 여부
        """
        try:
            # 블록 위치 설정
            block.position = (pos_x, pos_y)
            
            # 배치 영역의 placed_blocks에 직접 추가
            self.placement_area.placed_blocks[block.id] = {
                'block': block,
                'position': (pos_x, pos_y)
            }
            
            # 그리드에 블록 표시 (충돌 무시)
            ref_x, ref_y = block.actual_reference
            for vx, vy in block.get_footprint():
                grid_x = pos_x + vx - ref_x
                grid_y = pos_y + vy - ref_y
                
                # 배치 영역 범위 내에만 표시
                if (0 <= grid_x < self.placement_area.width and 
                    0 <= grid_y < self.placement_area.height):
                    self.placement_area.grid[grid_y][grid_x] = 1
                else:
                    print(f"[WARNING] {block.id} 복셀 ({grid_x}, {grid_y})이 배치 영역을 벗어남")
            
            print(f"[INFO] {block.id} 강제 배치 완료 - 제약 조건 무시됨")
            return True
            
        except Exception as e:
            print(f"[ERROR] {block.id} 강제 배치 중 오류: {e}")
            return False
    
    def _track_force_rotation_block_movement(self, block, spacing, bow_clearance):
        """
        강제 회전 블록의 좁히기 이동을 추적하고 로그 출력
        
        Args:
            block: 강제 회전 블록
            spacing: 블록 간격
            bow_clearance: 선수 여백
        """
        print(f"\n[TRACK] {block.id} 강제 회전 블록 좁히기 이동 추적 시작")
        
        # 초기 위치 기록
        initial_pos = block.position
        print(f"[TRACK] {block.id} 초기 위치: {initial_pos}")
        
        # position이 None인 경우 오류 처리
        if initial_pos is None:
            print(f"[ERROR] {block.id} 블록의 position이 None입니다 - 배치가 제대로 되지 않았음")
            print(f"[DEBUG] {block.id} placed_blocks 상태: {block.id in self.placement_area.placed_blocks}")
            if block.id in self.placement_area.placed_blocks:
                placed_info = self.placement_area.placed_blocks[block.id]
                print(f"[DEBUG] {block.id} 배치 정보: {placed_info}")
            return
        
        total_moved_x = 0
        total_moved_y = 0
        
        # 1단계: 오른쪽으로 이동
        try:
            pos_before = block.position
            moved_right = self._compact_block_right_with_tracking(self.placement_area, block, spacing, bow_clearance)
            pos_after = block.position
            
            if moved_right > 0:
                total_moved_x += moved_right
                print(f"[TRACK] {block.id} 1단계 오른쪽 이동: {moved_right}칸 ({pos_before} -> {pos_after})")
            else:
                print(f"[TRACK] {block.id} 1단계 오른쪽 이동 불가: {self._get_movement_failure_reason(block, 'right', spacing, bow_clearance)}")
        except Exception as e:
            print(f"[TRACK] {block.id} 1단계 오른쪽 이동 오류: {e}")
        
        # 2단계: 아래로 이동
        try:
            pos_before = block.position
            moved_down = self._compact_block_down_with_tracking(self.placement_area, block, spacing)
            pos_after = block.position
            
            if moved_down > 0:
                total_moved_y += moved_down
                print(f"[TRACK] {block.id} 2단계 아래 이동: {moved_down}칸 ({pos_before} -> {pos_after})")
            else:
                print(f"[TRACK] {block.id} 2단계 아래 이동 불가: {self._get_movement_failure_reason(block, 'down', spacing)}")
        except Exception as e:
            print(f"[TRACK] {block.id} 2단계 아래 이동 오류: {e}")
        
        # 3단계: 다시 오른쪽으로 이동
        try:
            pos_before = block.position
            moved_right2 = self._compact_block_right_with_tracking(self.placement_area, block, spacing, bow_clearance)
            pos_after = block.position
            
            if moved_right2 > 0:
                total_moved_x += moved_right2
                print(f"[TRACK] {block.id} 3단계 오른쪽 이동: {moved_right2}칸 ({pos_before} -> {pos_after})")
            else:
                print(f"[TRACK] {block.id} 3단계 오른쪽 이동 불가: {self._get_movement_failure_reason(block, 'right', spacing, bow_clearance)}")
        except Exception as e:
            print(f"[TRACK] {block.id} 3단계 오른쪽 이동 오류: {e}")
        
        # 총 이동 결과
        final_pos = block.position
        print(f"[TRACK] {block.id} 좁히기 완료: {initial_pos} -> {final_pos}")
        print(f"[TRACK] {block.id} 총 이동: 오른쪽 {total_moved_x}칸, 아래 {total_moved_y}칸")
        print(f"[TRACK] {block.id} 강제 회전 블록 좁히기 추적 완료\n")
    
    def _compact_block_right_with_tracking(self, area, block, spacing, bow_clearance):
        """오른쪽 이동을 추적하는 버전"""
        original_pos = block.position
        if original_pos is None:
            print(f"[ERROR] {block.id} 오른쪽 이동 추적 실패: position이 None")
            return 0
        
        self._compact_block_right(area, block, spacing, bow_clearance)
        new_pos = block.position
        
        if new_pos is None:
            print(f"[ERROR] {block.id} 오른쪽 이동 후 position이 None이 됨")
            return 0
            
        return new_pos[0] - original_pos[0]  # 이동한 X 거리
    
    def _compact_block_down_with_tracking(self, area, block, spacing):
        """아래 이동을 추적하는 버전"""
        original_pos = block.position
        if original_pos is None:
            print(f"[ERROR] {block.id} 아래 이동 추적 실패: position이 None")
            return 0
        
        self._compact_block_down(area, block, spacing)
        new_pos = block.position
        
        if new_pos is None:
            print(f"[ERROR] {block.id} 아래 이동 후 position이 None이 됨")
            return 0
            
        return new_pos[1] - original_pos[1]  # 이동한 Y 거리
    
    def _get_movement_failure_reason(self, block, direction, spacing, bow_clearance=0):
        """이동 실패 원인 분석"""
        current_pos = block.position
        
        if direction == 'right':
            # 오른쪽 이동 실패 원인
            reasons = []
            
            # 경계 체크
            ref_x, ref_y = block.actual_reference
            max_block_x = current_pos[0] + max(vx for vx, vy in block.get_footprint()) - ref_x
            if max_block_x >= self.placement_area.width - bow_clearance:
                reasons.append(f"배치영역 경계 도달 (현재 최대X: {max_block_x}, 한계: {self.placement_area.width - bow_clearance})")
            
            # 다른 블록과의 충돌 체크
            test_pos = (current_pos[0] + 1, current_pos[1])
            if not self.placement_area.can_place_block(block, test_pos[0], test_pos[1]):
                reasons.append("오른쪽에 다른 블록 또는 장애물")
            
            return "; ".join(reasons) if reasons else "알 수 없는 이유"
            
        elif direction == 'down':
            # 아래 이동 실패 원인
            reasons = []
            
            # 경계 체크
            ref_x, ref_y = block.actual_reference
            max_block_y = current_pos[1] + max(vy for vx, vy in block.get_footprint()) - ref_y
            if max_block_y >= self.placement_area.height:
                reasons.append(f"배치영역 하단 경계 도달 (현재 최대Y: {max_block_y}, 한계: {self.placement_area.height})")
            
            # 다른 블록과의 충돌 체크
            test_pos = (current_pos[0], current_pos[1] + 1)
            if not self.placement_area.can_place_block(block, test_pos[0], test_pos[1]):
                reasons.append("아래에 다른 블록 또는 장애물")
                
            return "; ".join(reasons) if reasons else "알 수 없는 이유"
        
        return "방향 오류"
    
    def _create_rotated_block(self, block, angle):
        """블록의 회전된 복사본 생성"""
        try:
            rotated_block = block.clone()
            rotated_block.rotate(angle)
            
            # block_type 속성 명시적 복사 (시각화에서 올바른 색상 표시를 위해)
            if hasattr(block, 'block_type'):
                rotated_block.block_type = block.block_type
                print(f"[DEBUG] {block.id} 회전 블록 생성: block_type={block.block_type} → {rotated_block.block_type}")
            
            return rotated_block
        except Exception as e:
            print(f"[WARNING] 블록 {block.id} 회전 실패: {e}")
            return None
    
    def _adjust_candidates_for_rotation(self, original_block, rotated_block, candidates):
        """
        제자리 회전을 위해 후보 위치들을 보정
        
        Args:
            original_block: 원본 블록
            rotated_block: 회전된 블록
            candidates: 원본 블록 기준 후보 위치들
            
        Returns:
            list: 회전된 블록이 동일한 실제 위치에 배치되도록 보정된 후보 위치들
        """
        try:
            # reference point 차이 계산
            orig_ref_x, orig_ref_y = original_block.actual_reference
            rot_ref_x, rot_ref_y = rotated_block.actual_reference
            
            ref_diff_x = orig_ref_x - rot_ref_x
            ref_diff_y = orig_ref_y - rot_ref_y
            
            print(f"[DEBUG] {original_block.id} reference 차이: ({ref_diff_x}, {ref_diff_y})")
            
            # 후보 위치들을 보정하여 제자리 회전 효과 구현
            adjusted_candidates = []
            for pos_x, pos_y in candidates:
                adjusted_x = pos_x + ref_diff_x
                adjusted_y = pos_y + ref_diff_y
                
                # 배치 영역 범위 내에 있는 경우만 추가
                if (0 <= adjusted_x < self.placement_area.width and 
                    0 <= adjusted_y < self.placement_area.height):
                    adjusted_candidates.append((adjusted_x, adjusted_y))
            
            print(f"[DEBUG] {original_block.id} 보정된 후보 위치: {len(adjusted_candidates)}/{len(candidates)}개")
            return adjusted_candidates
            
        except Exception as e:
            print(f"[WARNING] 후보 위치 보정 실패: {e}")
            return candidates  # 실패 시 원본 후보 위치 그대로 사용
    
    def _test_placement_with_compaction(self, block, candidates, rotation=0):
        """
        배치 → 좁히기 → 데드스페이스 계산까지 모두 수행하여 최적의 결과 찾기
        
        Args:
            block: 배치할 블록
            candidates: 후보 위치 리스트
            rotation: 회전 각도 (로그용)
            
        Returns:
            dict: 최적 배치 정보 (block, initial_position, final_position, final_deadspace, rotation) 또는 None
        """
        best_result = None
        best_deadspace = float('inf')
        
        # 성능을 위해 처음 몇 개 후보 위치만 확인 (최대 3개)
        max_candidates_to_check = min(3, len(candidates))
        candidates_to_check = candidates[:max_candidates_to_check]
        
        for pos_x, pos_y in candidates_to_check:
            if self.placement_area.can_place_block(block, pos_x, pos_y):
                # 임시 배치 후 좁히기 및 데드스페이스 계산
                result = self._simulate_placement_with_compaction(block, pos_x, pos_y, rotation)
                
                if result and result['final_deadspace'] < best_deadspace:
                    best_deadspace = result['final_deadspace']
                    best_result = result
        
        return best_result
    
    def _simulate_placement_with_compaction(self, block, pos_x, pos_y, rotation=0):
        """
        블록 배치 → 좁히기 → 데드스페이스 계산을 시뮬레이션
        
        Returns:
            dict: 시뮬레이션 결과 또는 None
        """
        try:
            # 1단계: 임시 배치
            if not self.placement_area.place_block(block, pos_x, pos_y):
                return None
            
            initial_position = block.position
            
            # 2단계: 좁히기 적용
            bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
            spacing = getattr(self.placement_area, 'block_spacing', 4)
            
            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
            self._compact_block_down(self.placement_area, block, spacing)
            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
            
            final_position = block.position
            
            # 3단계: 데드스페이스 계산
            deadspace_metrics = self.placement_area.calculate_cluster_dead_space()
            final_deadspace = deadspace_metrics['dead_space_ratio']
            
            # 4단계: 블록 제거하여 원상복구
            self.placement_area.remove_block(block.id)
            
            return {
                'block': block,
                'initial_position': initial_position,
                'final_position': final_position,
                'final_deadspace': final_deadspace,
                'rotation': rotation
            }
            
        except Exception as e:
            # 오류 발생시 안전하게 원상복구 시도
            try:
                self.placement_area.remove_block(block.id)
            except:
                pass
            return None
    
    def _try_placement_with_deadspace(self, block, candidates, rotation=0):
        """
        주어진 블록과 후보 위치들에 대해 배치를 시도하고 최적의 deadspace 위치 찾기
        
        Args:
            block: 배치할 블록
            candidates: 후보 위치 리스트
            rotation: 회전 각도 (로그용)
            
        Returns:
            dict: 최적 배치 정보 (position, deadspace, block, rotation) 또는 None
        """
        best_placement = None
        best_deadspace = float('inf')
        
        # 성능을 위해 처음 몇 개 후보 위치만 확인 (최대 5개)
        max_candidates_to_check = min(5, len(candidates))
        candidates_to_check = candidates[:max_candidates_to_check]
        
        for pos_x, pos_y in candidates_to_check:
            if self.placement_area.can_place_block(block, pos_x, pos_y):
                # 임시 배치하여 deadspace 계산
                deadspace_ratio = self._calculate_deadspace_for_position(block, pos_x, pos_y)
                
                if deadspace_ratio is not None and deadspace_ratio < best_deadspace:
                    best_deadspace = deadspace_ratio
                    best_placement = {
                        'position': (pos_x, pos_y),
                        'deadspace': deadspace_ratio,
                        'block': block,
                        'rotation': rotation
                    }
        
        return best_placement
    
    def _calculate_deadspace_for_position(self, block, pos_x, pos_y):
        """
        특정 위치에 블록을 배치했을 때의 deadspace 비율 계산 (효율적 버전)
        
        Args:
            block: 배치할 블록
            pos_x, pos_y: 배치 위치
            
        Returns:
            float: deadspace 비율 (0.0-1.0) 또는 None (실패시)
        """
        try:
            # 임시로 블록을 배치하여 deadspace 계산
            if self.placement_area.place_block(block, pos_x, pos_y):
                # deadspace 계산
                deadspace_metrics = self.placement_area.calculate_cluster_dead_space()
                deadspace_ratio = deadspace_metrics['dead_space_ratio']
                
                # 블록 제거하여 원상복구
                self.placement_area.remove_block(block.id)
                
                return deadspace_ratio
            else:
                return None
                
        except Exception as e:
            # 오류 발생시 안전하게 원상복구 시도
            try:
                self.placement_area.remove_block(block.id)
            except:
                pass
            return None
    
    def _create_temp_placement_area(self):
        """deadspace 계산을 위한 임시 배치 영역 생성 (사용 안함 - 성능 문제로 삭제)"""
        # 더 이상 사용하지 않음 - _calculate_deadspace_for_position 사용
        temp_area = copy.deepcopy(self.placement_area)
        return temp_area
    
    def _place_block_simple(self, block, candidates):
        """기존 방식의 단순 배치 (첫 번째 가능한 위치에 배치)"""
        for pos_x, pos_y in candidates:
            if self.placement_area.can_place_block(block, pos_x, pos_y):
                if self.placement_area.place_block(block, pos_x, pos_y):
                    return True
        return False
    
    def get_rotation_statistics(self):
        """회전 최적화 통계 반환"""
        return {
            'rotation_attempts': self.rotation_attempts,
            'rotation_improvements': self.rotation_improvements,
            'improvement_rate': (self.rotation_improvements / self.rotation_attempts * 100) if self.rotation_attempts > 0 else 0
        }
    
    def _save_deadspace_comparison_visualization(self, block, original_placement, rotated_placement):
        """
        회전 최적화 시 deadspace 비교 시각화를 저장
        
        Args:
            block: 배치된 블록
            original_placement: 원본 배치 정보 
            rotated_placement: 회전된 배치 정보
        """
        try:
            # visualization_results 폴더 생성
            vis_dir = "visualization_results"
            os.makedirs(vis_dir, exist_ok=True)
            
            fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 8))
            
            # 원본 배치와 회전된 배치 각각 시각화
            self._visualize_deadspace_state(ax1, original_placement, "Original (0°)")
            self._visualize_deadspace_state(ax2, rotated_placement, "Rotated (180°)")
            
            # 제목과 메타데이터
            fig.suptitle(f"Deadspace Comparison - Block {block.id}", fontsize=16, fontweight='bold')
            
            # 개선 정보 텍스트
            improvement = original_placement['deadspace'] - rotated_placement['deadspace']
            improvement_pct = (improvement / original_placement['deadspace']) * 100
            
            fig.text(0.5, 0.02, 
                    f"Deadspace Improvement: {improvement:.4f} ({improvement_pct:+.1f}%) | "
                    f"Original: {original_placement['deadspace']:.4f} -> Rotated: {rotated_placement['deadspace']:.4f}",
                    ha='center', fontsize=12, bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen"))
            
            plt.tight_layout()
            
            # 타임스탬프와 블록 ID로 파일명 생성
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
            filename = f"deadspace_comparison_{block.id}_{timestamp}.png"
            filepath = os.path.join(vis_dir, filename)
            
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            plt.close()
            
            print(f"[INFO] Deadspace 비교 시각화 저장: {filename}")
            self.deadspace_visualizations.append(filepath)
            
        except Exception as e:
            print(f"[WARNING] Deadspace 시각화 저장 실패: {e}")
    
    def _visualize_deadspace_state(self, ax, placement_info, title):
        """
        특정 배치 상태의 deadspace를 시각화
        
        Args:
            ax: matplotlib 축
            placement_info: 배치 정보 dict
            title: 서브플롯 제목
        """
        try:
            # 임시로 블록을 배치하여 현재 상태 재현
            temp_block = placement_info['block']
            pos_x, pos_y = placement_info['position']
            
            # 임시 배치
            if self.placement_area.place_block(temp_block, pos_x, pos_y):
                # 현재 상태 시각화
                self._draw_placement_state(ax, title, placement_info['deadspace'])
                
                # 블록 제거하여 원상복구
                self.placement_area.remove_block(temp_block.id)
            else:
                ax.text(0.5, 0.5, "Placement Failed", ha='center', va='center', transform=ax.transAxes)
                ax.set_title(f"{title} - FAILED")
                
        except Exception as e:
            ax.text(0.5, 0.5, f"Error: {str(e)}", ha='center', va='center', transform=ax.transAxes)
            ax.set_title(f"{title} - ERROR")
    
    def _draw_placement_state(self, ax, title, deadspace_ratio):
        """
        현재 배치 상태를 그리기
        
        Args:
            ax: matplotlib 축
            title: 제목
            deadspace_ratio: deadspace 비율
        """
        # 배치 영역 그리기
        ship_rect = patches.Rectangle(
            (0, 0), self.placement_area.width, self.placement_area.height,
            linewidth=2, edgecolor='black', facecolor='lightblue', alpha=0.3
        )
        ax.add_patch(ship_rect)
        
        # 배치된 블록들 그리기
        for block_id, placed_block in self.placement_area.placed_blocks.items():
            block = placed_block['block']
            pos_x = placed_block['position'][0]
            pos_y = placed_block['position'][1]
            
            # 블록 타입에 따른 색상
            if hasattr(block, 'block_type') and block.block_type == 'trestle':
                color = 'red' if getattr(block, 'rotation_angle', 0) == 180 else 'orange'
            else:
                color = 'lime'
            
            # 블록의 실제 점유 영역 그리기
            if hasattr(block, 'footprint'):
                for dx, dy in block.footprint:
                    cell_rect = patches.Rectangle(
                        (pos_x + dx, pos_y + dy), 1, 1,
                        facecolor=color, edgecolor='black', linewidth=0.5, alpha=0.8
                    )
                    ax.add_patch(cell_rect)
            
            # 블록 ID 표시
            if hasattr(block, 'footprint') and block.footprint:
                # footprint의 중심 계산
                footprint_xs = [pos_x + dx + 0.5 for dx, dy in block.footprint]
                footprint_ys = [pos_y + dy + 0.5 for dx, dy in block.footprint]
                center_x = sum(footprint_xs) / len(footprint_xs)
                center_y = sum(footprint_ys) / len(footprint_ys)
            else:
                center_x = pos_x + block.width / 2
                center_y = pos_y + block.height / 2
            
            ax.text(center_x, center_y, block.id, ha='center', va='center',
                   fontsize=8, fontweight='bold', color='white',
                   bbox=dict(boxstyle="round,pad=0.2", facecolor="black", alpha=0.7))
        
        # deadspace 영역 계산 및 표시
        try:
            deadspace_metrics = self.placement_area.calculate_cluster_dead_space()
            if 'dead_spaces' in deadspace_metrics:
                for dead_space in deadspace_metrics['dead_spaces']:
                    if 'coordinates' in dead_space:
                        for coord in dead_space['coordinates']:
                            dead_rect = patches.Rectangle(
                                coord, 1, 1,
                                facecolor='red', alpha=0.5, edgecolor='darkred', linewidth=1
                            )
                            ax.add_patch(dead_rect)
        except:
            pass
        
        # 축 설정
        ax.set_xlim(-5, self.placement_area.width + 5)
        ax.set_ylim(-5, self.placement_area.height + 5)
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_title(f"{title}\nDeadspace Ratio: {deadspace_ratio:.4f} ({deadspace_ratio*100:.2f}%)")
        ax.set_xlabel("X (meters)")
        ax.set_ylabel("Y (meters)")