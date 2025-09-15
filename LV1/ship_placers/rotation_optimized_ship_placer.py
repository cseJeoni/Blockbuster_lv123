"""
회전 최적화 선박 블록 배치 시스템
기존 ship_placer에 회전 최적화 그리디 알고리즘을 적용
"""

import sys
import json
import time
from pathlib import Path
from datetime import datetime
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import os

# 프로젝트 루트 디렉토리를 sys.path에 추가
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# 기존 모듈들 import
from ship_placers.ship_placer import ShipPlacerConfig, ShipPlacementAreaConfig
from algorithms.rotation_optimized_greedy_placer import RotationOptimizedGreedyPlacer


class RotationOptimizedShipPlacerConfig(ShipPlacerConfig):
    """회전 최적화 선박 배치 설정 클래스"""
    
    def __init__(self, config_path, enable_rotation_optimization=True, save_deadspace_visualization=False):
        super().__init__(config_path)
        self.enable_rotation_optimization = enable_rotation_optimization
        self.save_deadspace_visualization = save_deadspace_visualization
        
    def place_blocks(self, blocks=None, max_time=60):
        """
        회전 최적화 그리디 알고리즘을 사용한 블록 배치
        
        Args:
            blocks: 배치할 블록 리스트 (None이면 설정에서 생성)
            max_time: 최대 실행 시간 (초)
            
        Returns:
            PlacementArea: 배치 결과
        """
        try:
            # 블록 생성 (기본값 사용)
            if blocks is None:
                blocks = self.create_blocks_from_config()
            
            if not blocks:
                print("[ERROR] 배치할 블록이 없습니다")
                return None
            
            # 배치 영역 생성
            placement_area = ShipPlacementAreaConfig(self.config)
            
            print(f"[INFO] 회전 최적화 배치 시작: {len(blocks)}개 블록")
            print(f"[INFO] 배치 영역: {placement_area.width}x{placement_area.height}")
            print(f"[INFO] 회전 최적화 활성화: {self.enable_rotation_optimization}")
            
            # 회전 최적화 그리디 배치기 생성 및 실행
            placer = RotationOptimizedGreedyPlacer(
                placement_area, 
                blocks, 
                max_time=max_time,
                enable_rotation_optimization=self.enable_rotation_optimization,
                save_deadspace_visualization=self.save_deadspace_visualization
            )
            
            result = placer.place_all_blocks()
            
            if result:
                # 배치 순서 정보 설정 (기존과 동일)
                placement_order = []
                for i, block_id in enumerate(result.placed_blocks.keys(), 1):
                    placement_order.append((block_id, i))
                result.placement_order = placement_order
                
                # 회전 최적화 통계 출력
                if self.enable_rotation_optimization:
                    stats = placer.get_rotation_statistics()
                    print(f"[INFO] 회전 최적화 통계:")
                    print(f"  - 시도 횟수: {stats['rotation_attempts']}")
                    print(f"  - 개선 횟수: {stats['rotation_improvements']}")
                    print(f"  - 개선률: {stats['improvement_rate']:.1f}%")
                
                print(f"[SUCCESS] 배치 완료: {len(result.placed_blocks)}/{len(blocks)}개")
            else:
                print("[ERROR] 배치 실패")
            
            return result
            
        except Exception as e:
            print(f"[ERROR] 배치 중 오류 발생: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def visualize(self, result, save_path=None, show=True, show_dead_space=False, placement_duration=None):
        """
        배치 결과 시각화 (기존 ship_placer와 동일, 회전 정보 추가)
        """
        fig, ax_main = plt.subplots(1, 1, figsize=(20, 12))
        
        # 전체 선박 영역 (여백 포함)
        total_width = result.total_width
        total_height = result.total_height
        ship_rect = patches.Rectangle((0, 0), total_width, total_height, 
                                    linewidth=3, edgecolor='navy', facecolor='lightblue', alpha=0.3)
        ax_main.add_patch(ship_rect)
        
        # 배치 가능 영역 표시 (여백 제외된 실제 영역)
        placement_rect = patches.Rectangle((result.stern_clearance, 0), result.width, result.height, 
                                         linewidth=2, edgecolor='green', facecolor='lightgreen', alpha=0.2)
        ax_main.add_patch(placement_rect)
        
        # 여백 영역 표시
        if result.bow_clearance > 0:
            bow_rect = patches.Rectangle((total_width - result.bow_clearance, 0), result.bow_clearance, total_height, 
                                       linewidth=2, edgecolor='red', facecolor='red', alpha=0.2)
            ax_main.add_patch(bow_rect)
        if result.stern_clearance > 0:
            stern_rect = patches.Rectangle((0, 0), result.stern_clearance, total_height, 
                                         linewidth=2, edgecolor='purple', facecolor='purple', alpha=0.2)
            ax_main.add_patch(stern_rect)
        
        # 크레인 전용 ring bow clearance 표시
        if hasattr(result, 'ring_bow_clearance') and result.ring_bow_clearance > 0:
            ring_bow_start = total_width - result.ring_bow_clearance
            ring_bow_rect = patches.Rectangle((ring_bow_start, 0), result.ring_bow_clearance, total_height, 
                                            linewidth=2, edgecolor='darkorange', facecolor='orange', alpha=0.15)
            ax_main.add_patch(ring_bow_rect)
        
        placed_blocks_list = list(result.placed_blocks.values())
        total_blocks = len(placed_blocks_list) + len(result.unplaced_blocks)
        placed_count = len(placed_blocks_list)
        success_rate = (placed_count / total_blocks) * 100 if total_blocks > 0 else 0
        
        # 블록 타입별 색상 (회전된 트레슬 블록 구분)
        type_colors = {'crane': 'orange', 'trestle': 'green', 'trestle_rotated': 'darkgreen', 'unknown': 'gray'}
        
        # 배치 순서 정보를 딕셔너리로 변환
        placement_order_dict = {block_id: order_num for block_id, order_num in result.placement_order}
        
        # 블록들을 시각화
        for block in placed_blocks_list:
            if block.position is None: 
                continue
                
            pos_x, pos_y = block.position
            block_type = getattr(block, 'block_type', 'unknown')
            
            # 회전된 블록인지 확인 (디버깅 로그 추가)
            rotation_angle = getattr(block, 'rotation', 0)
            if block_type == 'trestle' and rotation_angle == 180:
                color = type_colors.get('trestle_rotated', 'darkgreen')
                print(f"[DEBUG] {block.id} 회전된 트레슬 블록: rotation={rotation_angle}, color=darkgreen")
            else:
                color = type_colors.get(block_type, 'gray')
                if block_type == 'trestle':
                    print(f"[DEBUG] {block.id} 일반 트레슬 블록: rotation={rotation_angle}, color=green")
                elif color == 'gray':
                    print(f"[DEBUG] {block.id} 기타 블록: block_type={block_type}, rotation={rotation_angle}, color=gray")
            
            # 실제 복셀 기준 좌표 변환 + 선미 여백 오프셋 적용
            ref_x, ref_y = block.actual_reference
            for rel_x, rel_y in block.get_footprint():
                abs_x = result.stern_clearance + pos_x + rel_x - ref_x
                abs_y = pos_y + rel_y - ref_y
                cell_rect = patches.Rectangle((abs_x, abs_y), 1, 1, 
                                            linewidth=0.5, edgecolor='black', facecolor=color, alpha=0.7)
                ax_main.add_patch(cell_rect)
            
            # 블록 이름 표시 (회전 정보 포함)
            footprint_coords = list(block.get_footprint())
            if footprint_coords:
                min_vx = min(vx for vx, vy in footprint_coords)
                max_vx = max(vx for vx, vy in footprint_coords)
                min_vy = min(vy for vx, vy in footprint_coords)
                max_vy = max(vy for vx, vy in footprint_coords)
                
                center_offset_x = (max_vx + min_vx) / 2 - ref_x
                center_offset_y = (max_vy + min_vy) / 2 - ref_y
                center_x = result.stern_clearance + pos_x + center_offset_x
                center_y = pos_y + center_offset_y
            
            # 배치 순서 번호와 블록 이름 함께 표시
            order_num = placement_order_dict.get(block.id, 0)
            rotation = getattr(block, 'rotation', 0)
            
            if rotation != 0:
                display_text = f"#{order_num}\n{block.id}\n(R{rotation}°)"
            else:
                display_text = f"#{order_num}\n{block.id}"
            
            ax_main.text(center_x, center_y, display_text, ha='center', va='center', 
                        fontsize=7, fontweight='bold', color='white',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='black', alpha=0.8))
        
        ax_main.set_xlim(-2, total_width + 2)
        ax_main.set_ylim(-2, total_height + 2)
        ax_main.set_aspect('equal')
        ax_main.grid(True, alpha=0.3)
        used_area = sum(block.get_area() for block in placed_blocks_list)
        space_utilization = (used_area / (total_width * total_height)) * 100 if total_width * total_height > 0 else 0
        
        # Dead Space 시각화 (기존과 동일)
        if show_dead_space:
            dead_space_metrics = result.calculate_cluster_dead_space()
            if dead_space_metrics['cluster_area'] > 0:
                min_x, min_y, max_x, max_y = dead_space_metrics['cluster_bbox']
                left_boundary_by_y = dead_space_metrics['left_boundary_by_y']
                
                # Dead Space 표시 로직 (기존과 동일)
                boundary_x = []
                boundary_y = []
                
                for y in range(min_y, max_y + 1):
                    if y in left_boundary_by_y and left_boundary_by_y[y]:
                        leftmost_x = min(left_boundary_by_y[y]) + result.stern_clearance
                        boundary_x.append(leftmost_x)
                        boundary_y.append(y + 0.5)  # 셀 중앙
                
                if len(boundary_x) > 1:
                    ax_main.plot(boundary_x, boundary_y, color='red', linewidth=3, 
                               linestyle='--', alpha=0.8, label='Left Block Contour')
                
                # 나머지 경계선들 그리기 (기존과 동일)
                ax_main.plot([result.stern_clearance + min_x, result.stern_clearance + max_x + 1], 
                           [max_y + 1, max_y + 1], color='red', linewidth=3, 
                           linestyle='--', alpha=0.8)
                
                ax_main.plot([result.stern_clearance + max_x + 1, result.stern_clearance + max_x + 1], 
                           [max_y + 1, min_y], color='red', linewidth=3, 
                           linestyle='--', alpha=0.8)
                
                ax_main.plot([result.stern_clearance + max_x + 1, result.stern_clearance + min_x], 
                           [min_y, min_y], color='red', linewidth=3, 
                           linestyle='--', alpha=0.8)
                
                # 덩어리 내부의 Dead Space 셀들 찾아서 표시 (ship_placer와 동일한 방식)
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

        # 범례 정보 준비
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
        legend_elements.append(patches.Patch(color='darkgreen', alpha=0.7, label='Trestle Blocks (Rotated 180°)'))
        
        # Dead Space 범례 추가
        if show_dead_space:
            legend_elements.append(patches.Patch(color='red', alpha=0.4, label='Dead Space'))
            legend_elements.append(patches.Patch(color='red', linestyle='--', fill=False, label='Block Contour Boundary'))
        
        # 범례 추가
        ax_main.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1.02, 1), fontsize=9)
        
        # 제목에 배치 시간 포함 (기존과 동일한 방식)
        title_text = f'Rotation-Optimized Ship Block Placement: {self.config["ship_configuration"]["name"]}\n'
        title_text += f'Placed: {placed_count}/{total_blocks} ({success_rate:.1f}%) | Space Usage: {space_utilization:.1f}%'
        
        # result 객체에서 placement_time 사용 (기존과 동일)
        if hasattr(result, 'placement_time'):
            title_text += f' | Time: {result.placement_time:.2f}s'
        elif placement_duration is not None:
            title_text += f' | Time: {placement_duration:.2f}s'
            
        title_text += f' | Rotation Optimization: {"ON" if self.enable_rotation_optimization else "OFF"}'
        
        plt.title(title_text, fontsize=16)
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"[INFO] 시각화 저장: {save_path}")
            
        if show:
            plt.show()


def main():
    if len(sys.argv) < 2:
        print("사용법: python rotation_optimized_ship_placer.py <config.json> [max_time] [options]")
        print("옵션:")
        print("  -v, --visualize    시각화 활성화")
        print("  --deadspace        deadspace 분석 표시")
        print("  --save-deadspace-viz  회전 시 deadspace 비교 시각화 저장")
        print("  --no-rotation      회전 최적화 비활성화")
        print("  -u, --unity        Unity 데이터 내보내기")
        return
    
    config_path = sys.argv[1]
    max_time = 15
    enable_visualization = '-v' in sys.argv or '--visualize' in sys.argv
    export_unity = '-u' in sys.argv or '--unity' in sys.argv
    show_dead_space = '--deadspace' in sys.argv or '--dead-space' in sys.argv
    save_deadspace_viz = '--save-deadspace-viz' in sys.argv
    enable_rotation = not ('--no-rotation' in sys.argv)
    
    for arg in sys.argv[2:]:
        if arg.isdigit():
            max_time = int(arg)
    
    try:
        # 회전 최적화 배치기 생성 및 실행
        placer_config = RotationOptimizedShipPlacerConfig(
            config_path, 
            enable_rotation_optimization=enable_rotation, 
            save_deadspace_visualization=save_deadspace_viz
        )
        
        # 배치 시간 측정
        placement_start_time = time.time()
        result = placer_config.place_blocks(max_time=max_time)
        placement_end_time = time.time()
        placement_duration = placement_end_time - placement_start_time
        
        if not result:
            print("[ERROR] 배치 실패")
            return
        
        # 배치 시간을 result 객체에 저장 (기존과 동일한 방식)
        result.placement_time = placement_duration
        
        # 성능 지표 출력 (deadspace 포함)
        metrics = result.get_enhanced_placement_metrics()
        
        print(f"\n=== 회전 최적화 배치 결과 ===")
        print(f"배치율: {metrics['placement_rate']:.3f} ({metrics['placed_blocks_count']}/{metrics['total_blocks_count']})")
        print(f"기존 공간활용률: {metrics['traditional_utilization']:.3f}")
        print(f"덩어리 효율성: {metrics['cluster_efficiency']:.3f}")
        print(f"Dead Space 비율: {metrics['dead_space_ratio']:.3f}")
        print(f"공간 절약 비율: {metrics['space_saving_ratio']:.3f}")
        print(f"덩어리 크기: {metrics['cluster_dimensions'][0]}x{metrics['cluster_dimensions'][1]} ({metrics['cluster_area']} cells)")
        print(f"배치 시간: {placement_duration:.2f}초")
        print(f"회전 최적화: {'활성화' if enable_rotation else '비활성화'}")
        
        # 시각화
        if enable_visualization:
            # LV1 내의 placement_results 디렉토리 사용
            current_dir = Path(__file__).parent
            lv1_dir = current_dir.parent
            output_dir = lv1_dir / "placement_results"
            output_dir.mkdir(exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            config_name = Path(placer_config.config_path).stem
            rotation_suffix = "_rotation" if enable_rotation else "_no_rotation"
            deadspace_suffix = "_deadspace" if show_dead_space else ""
            viz_filename = f"placement_{config_name}_{timestamp}{rotation_suffix}{deadspace_suffix}.png"
            placer_config.visualize(result, show=True, save_path=output_dir / viz_filename, 
                                  show_dead_space=show_dead_space, placement_duration=placement_duration)
        
        # Unity 데이터 내보내기 (기존과 동일)
        if export_unity:
            try:
                from export_unity_data import export_unity_placement_data
                unity_output_dir = Path(placer_config.config_path).parent / "unity_exports"
                unity_output_dir.mkdir(exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                config_name = Path(placer_config.config_path).stem
                unity_filename = f"unity_{config_name}_{timestamp}.json"
                export_unity_placement_data(result, placer_config.config, 
                                           unity_output_dir / unity_filename)
                print(f"[INFO] Unity 데이터 내보내기 완료: {unity_filename}")
            except ImportError:
                print("[WARNING] Unity 내보내기 모듈을 찾을 수 없습니다")
            except Exception as e:
                print(f"[ERROR] Unity 내보내기 실패: {e}")
    
    except Exception as e:
        print(f"[ERROR] 실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()