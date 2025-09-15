"""
Bottom-Right-Decreasing (BRD) 블록 배치 알고리즘
전통적인 Bottom-Left-Fill의 Right 우선 변형
"""
import time


class BottomRightPlacer:
    def __init__(self, placement_area, blocks, max_time=60):
        self.placement_area = placement_area
        self.blocks = blocks
        self.max_time = max_time
        self.start_time = 0
        self.placement_area.add_blocks(blocks)
    
    def place_all_blocks(self):
        """전통적인 BRD 실행"""
        self.start_time = time.time()
        sorted_blocks = sorted(self.blocks, key=lambda b: -b.get_area())
        
        placed_count = 0
        
        try:
            # 순수 전통 BRD: 단일 패스, 단순 스캔
            for block in sorted_blocks:
                if time.time() - self.start_time > self.max_time:
                    break
                
                # 전통적인 Bottom-Right-Fill 스캔
                candidate_pos = self._find_bottom_right_position(self.placement_area, block)
                
                if candidate_pos:
                    pos_x, pos_y = candidate_pos
                    if self.placement_area.can_place_block(block, pos_x, pos_y):
                        self.placement_area.place_block(block, pos_x, pos_y)
                        placed_count += 1
        
        except Exception as e:
            return None
        
        # 배치 완료
        return self.placement_area
    
    def _find_bottom_right_position(self, area, block):
        """크레인 블록 제약조건을 고려한 Bottom-Right-Fill 스캔"""
        # 아래부터 위로, 같은 Y에서는 오른쪽부터 왼쪽으로 스캔 (기존 알고리즘 유지)
        for y in range(area.height):                # 아래(Bottom) 우선
            for x in range(area.width - 1, -1, -1):  # 오른쪽(Right) 우선
                if area.can_place_block(block, x, y):
                    # 크레인 블록인 경우 추가 ring_bow_clearance 제약조건 확인
                    if self._check_crane_constraints(area, block, x, y):
                        return (x, y)
        return None

    def _check_crane_constraints(self, area, block, x, y):
        """크레인 블록의 ring_bow_clearance 제약조건 확인"""
        # 일반 블록은 항상 통과
        if getattr(block, 'block_type', None) != 'crane':
            return True

        # 크레인 블록의 경우 ring_bow_clearance 확인
        footprint_coords = block.get_footprint()
        if not footprint_coords:
            return True

        ref_x, ref_y = block.actual_reference
        max_vx = max(vx for vx, vy in footprint_coords)

        # 블록이 배치될 때의 실제 우측 끝 위치
        actual_right_edge = x + max_vx - ref_x

        # ring_bow_clearance와 bow_clearance 적용
        ring_bow_clearance = getattr(area, 'ring_bow_clearance', 0)
        bow_clearance = getattr(area, 'bow_clearance', 0)

        # 크레인 블록은 ring_bow_clearance를 지켜야 함
        # area.width는 이미 일반 bow_clearance가 제외된 상태이므로 되돌린 후 ring_bow 적용
        available_width = area.width + bow_clearance  # 원래 전체 너비
        max_allowed_right = available_width - ring_bow_clearance - 1

        return actual_right_edge <= max_allowed_right