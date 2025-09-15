"""
그리디 기반 블록 배치 알고리즘
"""
import time


class GreedyPlacer:
    
    def __init__(self, placement_area, blocks, max_time=60):
        self.placement_area = placement_area
        self.blocks = blocks
        self.max_time = max_time
        self.start_time = 0
        self.placement_area.add_blocks(blocks)
    
    def place_all_blocks(self):
        self.start_time = time.time()
        sorted_blocks = sorted(self.blocks, key=lambda b: -b.get_area())
        
        placed_count = 0
        unplaced_blocks = []  # 배치 못한 블록들 기록
        
        try:
            # 첫 번째 패스: 모든 블록 배치 시도
            for i, block in enumerate(sorted_blocks):
                # 시간 초과 체크
                if time.time() - self.start_time > self.max_time:
                    break
                
                # 후보 위치 생성
                max_cands = min(25, len(self.placement_area.placed_blocks) * 6 + 15)
                candidates = self._get_tight_candidates(self.placement_area, block, max_candidates=max_cands)
                
                if not candidates:
                    unplaced_blocks.append(block)
                    continue
                
                # 첫 번째 가능한 위치에 배치 (그리디)
                placed = False
                for j, (pos_x, pos_y) in enumerate(candidates):
                    if self.placement_area.can_place_block(block, pos_x, pos_y):
                        self.placement_area.place_block(block, pos_x, pos_y)
                        placed_count += 1
                        
                        # 배치 후 2방향 이동 최적화 시도
                        try:
                            bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
                            spacing = getattr(self.placement_area, 'block_spacing', 4)
                            
                            # 오른쪽으로 이동 최적화
                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)

                            # 아래쪽으로 이동 최적화
                            self._compact_block_down(self.placement_area, block, spacing)

                            # 아래 이동 후 추가 오른쪽 이동 시도
                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                                
                        except Exception as move_error:
                            # 이동 실패해도 계속
                            pass
                        
                        placed = True
                        break  # 첫 번째 성공한 위치에 배치하고 다음 블록으로
                
                # 배치 실패한 블록에 대해 크레인인 경우 회전 시도
                if not placed:
                    if getattr(block, 'block_type', None) == 'crane':
                        # 크레인 블록인 경우 90도 회전 후 재시도
                        original_rotation = block.rotation
                        try:
                            block.rotate(90)
                            print(f"[INFO] 크레인 블록 {block.id} 90도 회전 후 재시도")

                            # 회전된 상태로 다시 후보 위치 생성
                            candidates_rotated = self._get_tight_candidates(self.placement_area, block, max_candidates=max_cands)

                            if candidates_rotated:
                                for pos_x, pos_y in candidates_rotated:
                                    if self.placement_area.can_place_block(block, pos_x, pos_y):
                                        self.placement_area.place_block(block, pos_x, pos_y)
                                        placed_count += 1

                                        # 배치 후 2방향 이동 최적화 시도
                                        try:
                                            bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
                                            spacing = getattr(self.placement_area, 'block_spacing', 4)

                                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                                            self._compact_block_down(self.placement_area, block, spacing)
                                            self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                                        except Exception:
                                            pass

                                        placed = True
                                        print(f"[SUCCESS] 크레인 블록 {block.id} 회전 후 배치 성공")
                                        break

                            # 회전 후에도 배치 실패하면 원래 회전 상태로 복구
                            if not placed:
                                # 현재 회전 상태에서 원래 상태로 복구하기 위한 역회전 계산
                                reverse_rotation = (360 - (block.rotation - original_rotation)) % 360
                                if reverse_rotation != 0:
                                    block.rotate(reverse_rotation)

                        except Exception as e:
                            # 회전 중 오류 발생 시 원래 상태로 복구 시도
                            try:
                                reverse_rotation = (360 - (block.rotation - original_rotation)) % 360
                                if reverse_rotation != 0:
                                    block.rotate(reverse_rotation)
                            except:
                                pass

                    # 배치 실패한 블록 기록 (회전 시도 후에도 실패한 경우)
                    if not placed:
                        unplaced_blocks.append(block)
            
            # 두 번째 패스: 배치 못한 블록들 재시도
            if unplaced_blocks and time.time() - self.start_time < self.max_time:
                print(f"[INFO] 재시도: {len(unplaced_blocks)}개 블록")
                retry_count = 0
                successfully_placed = []  # 재시도에서 성공한 블록들 추적
                
                # 작은 블록부터 재시도 (공간 활용 개선)
                unplaced_blocks.sort(key=lambda b: b.get_area())
                
                for block in unplaced_blocks:
                    if time.time() - self.start_time > self.max_time:
                        break
                    
                    # 더 많은 후보로 재시도
                    max_cands = min(50, len(self.placement_area.placed_blocks) * 10 + 30)
                    candidates = self._get_tight_candidates(self.placement_area, block, max_candidates=max_cands)

                    placed_in_retry = False
                    for pos_x, pos_y in candidates:
                        if self.placement_area.can_place_block(block, pos_x, pos_y):
                            self.placement_area.place_block(block, pos_x, pos_y)
                            retry_count += 1
                            successfully_placed.append(block)  # 성공한 블록 기록

                            # 재배치된 블록도 이동 최적화
                            try:
                                bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
                                spacing = getattr(self.placement_area, 'block_spacing', 4)
                                self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                                self._compact_block_down(self.placement_area, block, spacing)
                                self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                            except:
                                pass
                            placed_in_retry = True
                            break

                    # 재시도에서도 실패한 크레인 블록에 대해 회전 시도
                    if not placed_in_retry and getattr(block, 'block_type', None) == 'crane':
                        original_rotation = block.rotation
                        try:
                            block.rotate(90)
                            print(f"[INFO] 재시도에서 크레인 블록 {block.id} 90도 회전 후 재시도")

                            # 회전된 상태로 다시 후보 위치 생성
                            candidates_rotated = self._get_tight_candidates(self.placement_area, block, max_candidates=max_cands)

                            for pos_x, pos_y in candidates_rotated:
                                if self.placement_area.can_place_block(block, pos_x, pos_y):
                                    self.placement_area.place_block(block, pos_x, pos_y)
                                    retry_count += 1
                                    successfully_placed.append(block)

                                    # 재배치된 블록도 이동 최적화
                                    try:
                                        bow_clearance = getattr(self.placement_area, 'bow_clearance', 0)
                                        spacing = getattr(self.placement_area, 'block_spacing', 4)
                                        self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                                        self._compact_block_down(self.placement_area, block, spacing)
                                        self._compact_block_right(self.placement_area, block, spacing, bow_clearance)
                                    except:
                                        pass

                                    placed_in_retry = True
                                    print(f"[SUCCESS] 재시도에서 크레인 블록 {block.id} 회전 후 배치 성공")
                                    break

                            # 회전 후에도 배치 실패하면 원래 회전 상태로 복구
                            if not placed_in_retry:
                                reverse_rotation = (360 - (block.rotation - original_rotation)) % 360
                                if reverse_rotation != 0:
                                    block.rotate(reverse_rotation)

                        except Exception as e:
                            # 회전 중 오류 발생 시 원래 상태로 복구 시도
                            try:
                                reverse_rotation = (360 - (block.rotation - original_rotation)) % 360
                                if reverse_rotation != 0:
                                    block.rotate(reverse_rotation)
                            except:
                                pass
                
                # 성공적으로 배치된 블록들을 unplaced_blocks에서 제거
                for block in successfully_placed:
                    if block in unplaced_blocks:
                        unplaced_blocks.remove(block)
                
                if retry_count > 0:
                    print(f"[SUCCESS] 재시도로 {retry_count}개 블록 추가 배치")
                    placed_count += retry_count
        
        except Exception as e:
            return None
        
        # 실제로 배치된 블록 ID들 확인
        placed_block_ids = set(self.placement_area.placed_blocks.keys())
        
        # 전체 입력 블록에서 배치된 것을 제외하고 진짜 배치 못한 블록들만 계산
        all_block_ids = {block.id for block in self.blocks}
        actual_unplaced_ids = all_block_ids - placed_block_ids
        
        # 결과에 정확한 unplaced_blocks 설정
        self.placement_area.unplaced_blocks = list(actual_unplaced_ids)
        
        return self.placement_area
    
    def _get_tight_candidates(self, area, block, max_candidates=20):
        """컬럼별 수직 채우기 + 오른쪽 압축 전략"""
        candidates = []
        bow_clearance = getattr(area, 'bow_clearance', 0)
        stern_clearance = getattr(area, 'stern_clearance', 0)
        spacing = getattr(area, 'block_spacing', 4)
        
        if len(area.placed_blocks) == 0:
            # 첫 번째 블록: 오른쪽 아래 모서리 (실제 복셀 기준)
            ref_x, ref_y = block.actual_reference
            footprint_coords = list(block.get_footprint())
            if footprint_coords:
                max_vx = max(vx for vx, vy in footprint_coords)
                actual_width = max_vx - ref_x + 1
                
                # 크레인 블록은 ring bow clearance만 사용, 트레슬/기타는 일반 bow clearance 사용 (성능 최적화)
                if getattr(block, 'block_type', None) == 'crane':
                    # 크레인 블록: 일반 bow를 되돌리고 ring bow clearance만 사용
                    ring_bow_clearance = getattr(area, 'ring_bow_clearance', 0)
                    # area.width에서 일반 bow가 이미 제외되어 있으므로, bow를 되돌리고 ring_bow만 적용
                    available_width = area.width + bow_clearance  # 일반 bow clearance 되돌림
                    first_x = available_width - actual_width - ring_bow_clearance
                else:
                    # 트레슬/기타 블록: 일반 bow clearance 사용 (이미 area에서 제외됨)
                    first_x = area.width - actual_width
                first_y = 0
                if first_x >= 0:
                    if area.can_place_block(block, first_x, first_y):
                        candidates.append((first_x, first_y, False))
        else:
            # 컬럼별 수직 채우기 전략
            column_tops = self._get_column_tops(area, bow_clearance, stern_clearance)
            
            for x in sorted(column_tops.keys(), reverse=True):  # 오른쪽부터
                top_y = column_tops[x]
                
                # 해당 컬럼에서 위쪽에 쌓기
                candidate_y = top_y + spacing
                if candidate_y + block.height <= area.height:
                    if area.can_place_block(block, x, candidate_y):
                        candidates.append((x, candidate_y, False))
            
            # 새로운 컬럼 시작 (기존 컬럼들의 왼쪽) - 실제 복셀 기준
            if column_tops:
                leftmost_x = min(column_tops.keys())
                ref_x, ref_y = block.actual_reference
                footprint_coords = list(block.get_footprint())
                if footprint_coords:
                    max_vx = max(vx for vx, vy in footprint_coords)
                    actual_width = max_vx - ref_x + 1
                    new_x = leftmost_x - actual_width - spacing
                if new_x >= stern_clearance:
                    if area.can_place_block(block, new_x, 0):
                        candidates.append((new_x, 0, False))
        
        # 단순 위치 기준 정렬: 오른쪽 우선, 아래쪽 우선
        candidates.sort(key=lambda c: (-c[0], c[1]))  # -x (오른쪽 우선), y (아래쪽 우선)
        
        final_candidates = [(x, y) for x, y, _ in candidates[:max_candidates]]
        
        return final_candidates
    
    def _get_column_tops(self, area, bow_clearance, stern_clearance):
        """각 컬럼(X축)별 최상단 Y 위치 계산"""
        column_tops = {}
        
        for placed_block in area.placed_blocks.values():
            if not placed_block.position:
                continue
            
            px, py = placed_block.position
            # 블록이 차지하는 X 범위의 모든 컬럼 업데이트 (실제 복셀 기준)
            p_ref_x, p_ref_y = placed_block.actual_reference
            p_footprint = list(placed_block.get_footprint())
            
            if p_footprint:
                min_vx = min(vx for vx, vy in p_footprint)
                max_vx = max(vx for vx, vy in p_footprint)
                min_vy = min(vy for vx, vy in p_footprint)
                max_vy = max(vy for vx, vy in p_footprint)
                
                p_actual_width = max_vx - min_vx + 1
                p_actual_height = max_vy - min_vy + 1
                
                # 실제 블록이 시작하는 X 위치 (actual_reference 기준)
                block_start_x = px + min_vx - p_ref_x
                for x in range(block_start_x, block_start_x + p_actual_width):
                    if 0 <= x < area.width:  # 배치 영역 범위 내에서만
                        block_top = py + max_vy - p_ref_y + 1
                        if x not in column_tops or block_top > column_tops[x]:
                            column_tops[x] = block_top
        
        return column_tops
    
    def _compact_block_right(self, area, block, spacing, bow_clearance):
        """배치된 블록을 오른쪽으로 최대한 이동 (오른쪽 테두리 복셀별 정밀 계산)"""
        if not block.position:
            return False
        
        current_x, current_y = block.position
        
        # 4391_643_000, 4391_653_000 블록에 대한 디버깅 로그
        debug_target = False  # 디버그 로그 비활성화
        if debug_target:
            print(f"\n[DEBUG] {block.id} 우측 이동 시도 시작")
            print(f"  현재 위치: ({current_x}, {current_y})")
            print(f"  spacing: {spacing}, bow_clearance: {bow_clearance}")
        
        # 블록의 오른쪽 테두리 복셀들 찾기 (Y 좌표별 가장 오른쪽만, 성능 최적화)
        block_footprint = block.get_footprint()
        right_edge_voxels = []
        
        # Y 좌표별 가장 오른쪽 복셀 찾기 (원래 방식 복원)
        y_to_max_x = {}
        for vx, vy in block_footprint:
            if vy not in y_to_max_x or vx > y_to_max_x[vy]:
                y_to_max_x[vy] = vx
        
        # 각 Y의 오른쪽 테두리 복셀들 수집
        ref_x, ref_y = block.actual_reference
        for vy, max_vx in y_to_max_x.items():
            # 블록 좌표에서 격자 좌표로 변환 (actual_reference 기준)
            grid_x = current_x + max_vx - ref_x
            grid_y = current_y + vy - ref_y
            right_edge_voxels.append((grid_x, grid_y))
            
        # 디버깅: 계산된 테두리 복셀들이 유효한 범위인지 확인
        valid_edge_voxels = []
        for grid_x, grid_y in right_edge_voxels:
            if 0 <= grid_x < area.width and 0 <= grid_y < area.height:
                valid_edge_voxels.append((grid_x, grid_y))
        
        right_edge_voxels = valid_edge_voxels
        
        # 유효한 테두리 복셀이 없으면 이동 불가
        if not right_edge_voxels:
            return False
        
        # 각 오른쪽 테두리 복셀별로 이동 가능한 최대 거리 계산
        min_move_distance = float('inf')
        
        if debug_target:
            print(f"  오른쪽 테두리 복셀들: {len(right_edge_voxels)}개")
            for i, (gx, gy) in enumerate(right_edge_voxels):
                print(f"    [{i}] 격자좌표: ({gx}, {gy})")
        
        for edge_x, edge_y in right_edge_voxels:
            # 배치 영역 내 유효한 테두리 복셀만 처리
            if not (0 <= edge_y < area.height and 0 <= edge_x < area.width):
                if debug_target:
                    print(f"    테두리 ({edge_x}, {edge_y}) 영역 벗어남")
                continue
                
            # 격자 형태 확인
            if hasattr(area.grid, 'shape'):
                grid_height, grid_width = area.grid.shape
                if not (0 <= edge_y < grid_height and 0 <= edge_x < grid_width):
                    if debug_target:
                        print(f"    테두리 ({edge_x}, {edge_y}) 격자 범위 벗어남")
                    continue
                
            # 이 테두리 복셀에서 오른쪽으로 1칸씩 체크
            nearest_obstacle_x = area.width  # 기본값: 배치 영역 끝
            
            for test_x in range(edge_x + 1, area.width):
                try:
                    if area.grid[edge_y, test_x] is not None and area.grid[edge_y, test_x] != block.id:  # 자기 자신이 아닌 장애물만
                        nearest_obstacle_x = test_x
                        if debug_target:
                            print(f"    테두리 ({edge_x}, {edge_y})에서 장애물@X={test_x} 발견")
                        break
                except (IndexError, KeyError):
                    break
            
            # 이 테두리 복셀이 이동할 수 있는 최대 거리 계산
            possible_move = nearest_obstacle_x - edge_x - spacing
            
            if debug_target:
                print(f"    테두리 ({edge_x}, {edge_y}): 장애물@X={nearest_obstacle_x}, 가능거리={possible_move}")
            
            if possible_move > 0:  # 양수인 경우만 고려
                min_move_distance = min(min_move_distance, possible_move)
        
        # 영역 경계 제한 (실제 복셀 기준으로 계산)
        ref_x, ref_y = block.actual_reference
        footprint_coords = list(block.get_footprint())
        if footprint_coords:
            max_vx = max(vx for vx, vy in footprint_coords)
            # 블록의 가장 오른쪽 복셀이 배치될 수 있는 최대 격자 위치
            rightmost_voxel_grid_x = current_x + max_vx - ref_x
            # 배치 영역 경계까지 이동 가능한 거리
            boundary_limit_move = (area.width - 1) - rightmost_voxel_grid_x
            
            if boundary_limit_move >= 0:
                min_move_distance = min(min_move_distance, boundary_limit_move)
            else:
                # 이미 경계를 벗어났다면 이동 불가
                min_move_distance = 0
        
        # min_move_distance가 여전히 무한대면 이동 불가
        if min_move_distance == float('inf'):
            min_move_distance = 0
        
        # 이동 가능한 거리가 있으면 점진적으로 이동 시도
        if min_move_distance > 0:
            if debug_target:
                print(f"  최대 이동 가능 거리: {min_move_distance}칸")
            
            # 최대 거리부터 1칸씩 줄여가며 시도
            for distance in range(min_move_distance, 0, -1):
                target_x = current_x + distance
                
                if debug_target:
                    print(f"  {distance}칸 이동 시도 → 목표 위치: ({target_x}, {current_y})")
                
                # 목표 위치가 배치 영역을 벗어나지 않는지 확인
                if target_x >= 0 and target_x < area.width:
                    try:
                        # 블록 제거 후 새 위치에 배치 시도
                        removed_successfully = area.remove_block(block.id)
                        if not removed_successfully:
                            if debug_target:
                                print(f"    블록 제거 실패")
                            continue
                        
                        if area.can_place_block(block, target_x, current_y):
                            # 새 위치에 성공적으로 배치
                            placed_successfully = area.place_block(block, target_x, current_y)
                            if placed_successfully:
                                if debug_target:
                                    print(f"    [SUCCESS] {distance}칸 우측 이동 성공!")
                                return True
                        else:
                            if debug_target:
                                print(f"    can_place_block 실패 - 배치 조건 위반")
                                print(f"      목표 위치: ({target_x}, {current_y})")
                                print(f"      블록 크기: {block.width}x{block.height}")
                                print(f"      영역 크기: {area.width}x{area.height}")
                                
                                # 실패 원인 상세 분석을 위한 간단한 체크
                                print(f"      실패 원인 분석:")
                                footprint = block.get_footprint()
                                ref_x, ref_y = block.actual_reference
                                overlapping_cells = []
                                out_of_bounds_cells = []
                                
                                for vx, vy in footprint:
                                    grid_x = target_x + vx - ref_x
                                    grid_y = current_y + vy - ref_y
                                    
                                    if grid_x < 0 or grid_x >= area.width or grid_y < 0 or grid_y >= area.height:
                                        out_of_bounds_cells.append((vx, vy, grid_x, grid_y))
                                    elif area.grid[grid_y, grid_x] is not None:
                                        overlapping_cells.append((vx, vy, grid_x, grid_y, area.grid[grid_y, grid_x]))
                                
                                if out_of_bounds_cells:
                                    print(f"        영역 벗어남: {len(out_of_bounds_cells)}개 복셀")
                                    for vx, vy, gx, gy in out_of_bounds_cells[:3]:  # 처음 3개만
                                        print(f"          복셀({vx},{vy}) → 격자({gx},{gy})")
                                
                                if overlapping_cells:
                                    print(f"        블록 겹침: {len(overlapping_cells)}개 복셀")
                                    for vx, vy, gx, gy, existing_id in overlapping_cells[:3]:  # 처음 3개만
                                        print(f"          복셀({vx},{vy}) → 격자({gx},{gy}) with {existing_id}")
                                
                                if not out_of_bounds_cells and not overlapping_cells:
                                    print(f"        기타 조건 위반 (이격거리, 트랜스포터 접근성 등)")
                        
                        # 새 위치 배치 실패하거나 불가능한 경우, 원위치 복구
                        area.place_block(block, current_x, current_y)
                        
                    except Exception as e:
                        # 안전을 위해 원위치 복구 시도
                        try:
                            area.place_block(block, current_x, current_y)
                        except:
                            pass
            
            # 모든 거리에서 이동 실패
            if debug_target:
                print(f"  [FAIL] 모든 거리에서 우측 이동 실패")
            return False
        else:
            # 이동할 공간이 없는 경우
            if debug_target:
                print(f"  [FAIL] 이동 가능한 거리 없음 (min_move_distance: {min_move_distance})")
            return False
    
    def _compact_block_down(self, area, block, spacing):
        """배치된 블록을 아래쪽으로 최대한 이동"""
        if not block.position:
            return False
        
        current_x, current_y = block.position
        
        # 4391_643_000, 4391_653_000 블록에 대한 디버깅 로그
        debug_target = False  # 디버그 로그 비활성화
        if debug_target:
            print(f"\n[DEBUG] {block.id} 하단 이동 시도 시작")
            print(f"  현재 위치: ({current_x}, {current_y})")
            print(f"  spacing: {spacing}")
        
        # 블록의 아래쪽 테두리 복셀들 찾기 (X 좌표별 가장 아래쪽만)
        block_footprint = block.get_footprint()
        bottom_edge_voxels = []
        
        # X 좌표별 가장 아래쪽 복셀 찾기
        x_to_min_y = {}
        for vx, vy in block_footprint:
            if vx not in x_to_min_y or vy < x_to_min_y[vx]:
                x_to_min_y[vx] = vy
        
        # 각 X의 아래쪽 테두리 복셀들 수집
        ref_x, ref_y = block.actual_reference
        for vx, min_vy in x_to_min_y.items():
            # 블록 좌표에서 격자 좌표로 변환
            grid_x = current_x + vx - ref_x
            grid_y = current_y + min_vy - ref_y
            bottom_edge_voxels.append((grid_x, grid_y))
        
        # 유효한 테두리 복셀 확인
        valid_edge_voxels = []
        for grid_x, grid_y in bottom_edge_voxels:
            if 0 <= grid_x < area.width and 0 <= grid_y < area.height:
                valid_edge_voxels.append((grid_x, grid_y))
        
        if not valid_edge_voxels:
            return False
        
        # 각 아래쪽 테두리 복셀별로 이동 가능한 최대 거리 계산
        min_move_distance = float('inf')
        
        for edge_x, edge_y in valid_edge_voxels:
            # 이 테두리 복셀에서 아래쪽으로 1칸씩 체크
            nearest_obstacle_y = 0  # 기본값: 바닥
            
            for test_y in range(edge_y - 1, -1, -1):  # 아래쪽으로
                try:
                    if area.grid[test_y, edge_x] is not None and area.grid[test_y, edge_x] != block.id:  # 자기 자신이 아닌 장애물만
                        nearest_obstacle_y = test_y + 1  # 장애물 바로 위
                        break
                except (IndexError, KeyError):
                    break
            
            # 이 테두리 복셀이 이동할 수 있는 최대 거리 계산
            possible_move = edge_y - nearest_obstacle_y - spacing
            
            if possible_move > 0:  # 양수인 경우만 고려
                min_move_distance = min(min_move_distance, possible_move)
        
        # 영역 경계 제한
        if min_move_distance == float('inf'):
            min_move_distance = 0
        
        # 이동 가능한 거리가 있으면 점진적으로 이동 시도
        if min_move_distance > 0:
            if debug_target:
                print(f"  최대 하단 이동 가능 거리: {min_move_distance}칸")
            
            # 최대 거리부터 1칸씩 줄여가며 시도
            for distance in range(min_move_distance, 0, -1):
                target_y = current_y - distance  # 아래쪽으로 이동
                
                if debug_target:
                    print(f"  {distance}칸 하단 이동 시도 → 목표 위치: ({current_x}, {target_y})")
                
                if target_y >= 0:
                    try:
                        # 블록 제거 후 새 위치에 배치 시도
                        removed_successfully = area.remove_block(block.id)
                        if not removed_successfully:
                            if debug_target:
                                print(f"    블록 제거 실패")
                            continue
                        
                        if area.can_place_block(block, current_x, target_y):
                            # 새 위치에 성공적으로 배치
                            placed_successfully = area.place_block(block, current_x, target_y)
                            if placed_successfully:
                                if debug_target:
                                    print(f"    [SUCCESS] {distance}칸 하단 이동 성공!")
                                return True
                        else:
                            if debug_target:
                                print(f"    can_place_block 실패 - 배치 조건 위반")
                        
                        # 새 위치 배치 실패시 원위치 복구
                        area.place_block(block, current_x, current_y)
                        
                    except Exception as e:
                        # 안전을 위해 원위치 복구 시도
                        try:
                            area.place_block(block, current_x, current_y)
                        except:
                            pass
            
            # 모든 거리에서 이동 실패
            if debug_target:
                print(f"  [FAIL] 모든 거리에서 하단 이동 실패")
            return False
        else:
            # 이동할 공간이 없는 경우
            if debug_target:
                print(f"  [FAIL] 하단 이동 가능한 거리 없음 (min_move_distance: {min_move_distance})")
            return False
    
