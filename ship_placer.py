#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Config 기반 자항선 블록 배치 시스템
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

# 폰트 설정
plt.rcParams['font.family'] = ['DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from models.voxel_block import VoxelBlock
    from models.placement_area import PlacementArea
    from algorithms.backtracking_placer import PracticalBacktracking
    ORIGINAL_ALGORITHM_AVAILABLE = True
    print(f"[INFO] Algorithm modules loaded successfully")
    print(f"       - PracticalBacktracking: 백트래킹 (완전 탐색)")
except ImportError as e:
    print(f"[INFO] Algorithm modules not found: {e}")
    ORIGINAL_ALGORITHM_AVAILABLE = False

class ShipPlacementAreaConfig(PlacementArea):
    """Config 기반 자항선 배치 영역"""
    
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
        
        super().__init__(width_grids, height_grids)
        
        self.grid_resolution = self.grid_unit
        
        # 제약조건 (그리드 단위)
        self.bow_clearance = int(margin['bow'])
        self.stern_clearance = int(margin['stern'])
        self.block_spacing = int(constraints.get('block_clearance', 1))
        
        print(f"[INFO] ShipPlacementAreaConfig initialized:")
        print(f"       Ship size: {self.ship_width_m}m × {self.ship_height_m}m")
        print(f"       Grid size: {self.width} × {self.height} (unit: {self.grid_unit}m)")
        print(f"       Bow clearance: {self.bow_clearance} grids")
        print(f"       Stern clearance: {self.stern_clearance} grids")
        print(f"       Block spacing: {self.block_spacing} grids")
    
    def can_place_block(self, block, pos_x, pos_y):
        """블록 배치 가능 여부 확인 (이격거리 적용)"""
        # 기본 배치 가능성 확인
        if not super().can_place_block(block, pos_x, pos_y):
            return False
        
        # 선수 여백 확인
        block_right_edge = pos_x + block.width
        if block_right_edge > self.width - self.bow_clearance:
            return False
        
        # 선미 여백 확인
        block_left_edge = pos_x
        if block_left_edge < self.stern_clearance:
            return False
        
        # 블록간 간격 확인
        for placed_block in self.placed_blocks.values():
            if placed_block.position is None:
                continue
                
            px, py = placed_block.position
            
            # 경계 상자 간 최소 거리 계산
            new_left = pos_x
            new_right = pos_x + block.width - 1
            new_bottom = pos_y 
            new_top = pos_y + block.height - 1
            
            placed_left = px
            placed_right = px + placed_block.width - 1
            placed_bottom = py
            placed_top = py + placed_block.height - 1
            
            # X축 거리 계산
            if new_right < placed_left:
                x_distance = placed_left - new_right - 1
            elif placed_right < new_left:
                x_distance = new_left - placed_right - 1
            else:
                x_distance = -1  # 겹침
            
            # Y축 거리 계산
            if new_top < placed_bottom:
                y_distance = placed_bottom - new_top - 1
            elif placed_top < new_bottom:
                y_distance = new_bottom - placed_top - 1
            else:
                y_distance = -1  # 겹침
            
            # 간격 확인
            if x_distance < 0 and y_distance < 0:
                return False  # 겹침
            elif x_distance >= 0 and y_distance < 0:
                if x_distance < self.block_spacing:
                    return False
            elif x_distance < 0 and y_distance >= 0:
                if y_distance < self.block_spacing:
                    return False
            else:
                min_distance = min(x_distance, y_distance)
                if min_distance < self.block_spacing:
                    return False
        
        return True

class ShipPlacerConfig:
    """Config 기반 자항선 배치 시스템"""
    
    def __init__(self, config_path=None, config_dict=None, verbose=True):
        self.verbose = verbose
        if config_dict:
            self.config = config_dict
            self.config_path = None
        elif config_path:
            self.config_path = config_path
            self.config = self.load_config(config_path)
        else:
            raise ValueError("Either config_path or config_dict must be provided")
        
        if self.verbose:
            print(f"[INFO] ShipPlacerConfig initialized")
            if self.config_path:
                print(f"       Config: {config_path}")
            print(f"       Ship: {self.config['ship_configuration']['name']}")
    
    def load_config(self, config_path):
        print(f"[INFO] Loading config from: {config_path}")
        
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            print(f"       Ship: {config['ship_configuration']['name']}")
            print(f"       Blocks: {config['blocks_to_place']['total_blocks']} blocks")
            print(f"       Resolution: {config['voxelization_settings']['resolution']}m")
            
            return config
        except Exception as e:
            print(f"[ERROR] Failed to load config: {e}")
            raise
    
    def create_blocks_from_config(self):
        blocks = []
        blocks_config = self.config['blocks_to_place']['blocks']
        
        print(f"[INFO] Creating blocks from config...")
        
        for block_config in blocks_config:
            quantity = block_config.get('quantity', 1)
            
            for i in range(quantity):
                # 블록 ID 생성 (수량이 여러 개인 경우 번호 추가)
                block_id = block_config['block_id']
                if quantity > 1:
                    block_id = f"{block_config['block_id']}_{i+1}"
                
                # 실제 복셀 형태 데이터를 VoxelBlock 형식으로 변환
                voxel_data_config = block_config['voxel_data']
                voxel_data = []
                
                if 'footprint_positions' in voxel_data_config:
                    for pos in voxel_data_config['footprint_positions']:
                        height_info = pos.get('height_info', [0, 1, 0])
                        voxel_data.append((pos['x'], pos['y'], height_info))
                else:
                    width = voxel_data_config['dimensions']['width'] 
                    height = voxel_data_config['dimensions']['height']
                    for x in range(width):
                        for y in range(height):
                            voxel_data.append((x, y, [0, 1, 0]))
                
                # VoxelBlock 생성
                block = VoxelBlock(block_id, voxel_data)
                block.block_type = block_config['block_type']
                blocks.append(block)
        
        type_counts = defaultdict(int)
        for block in blocks:
            type_counts[block.block_type] += 1
        
        print(f"       Successfully created {len(blocks)} blocks:")
        for block_type, count in type_counts.items():
            print(f"         {block_type}: {count}")
        
        return blocks
    
    def place_blocks(self, blocks, max_time=60):
        if not ORIGINAL_ALGORITHM_AVAILABLE:
            print("[ERROR] Algorithm modules not available")
            return None
            
        print(f"[INFO] Block placement started...")
        print(f"       Blocks to place: {len(blocks)}")
        print(f"       Max time: {max_time} seconds")
        print(f"       Algorithm: backtracking")
        print("="*80)
        
        area = ShipPlacementAreaConfig(self.config)
        
        try:
            start_time = time.time()
            
            print(f"Using practical backtracking algorithm (full search)...")
            placer = PracticalBacktracking(area, blocks, max_time)
            
            result = placer.optimize()
            end_time = time.time()
            
            print(f"[DEBUG] Placer returned result: {result is not None}")
            if result is None:
                print(f"[DEBUG] No solution found within {max_time} seconds")
            
            if result:
                result.placement_time = end_time - start_time
                placed_count = len(result.placed_blocks)
                total_count = placed_count + len(result.unplaced_blocks)
                
                print(f"[INFO] Backtracking placement completed in {result.placement_time:.2f}s")
                print(f"       Placed: {placed_count}/{total_count} ({placed_count/total_count*100:.1f}%)")
                print(f"       Unplaced: {len(result.unplaced_blocks)}")
                
                if result.unplaced_blocks:
                    print(f"\n[INFO] Unplaced blocks details:")
                    unplaced_names = []
                    for i, (block_id, block) in enumerate(result.unplaced_blocks.items(), 1):
                        block_area = block.get_area()
                        print(f"       {i}. {block.id}: {block.width}x{block.height} ({block_area} cells)")
                        unplaced_names.append(block.id)
                    
                    # 간편한 접근을 위해 배치되지 못한 블록 이름 리스트 저장
                    result.unplaced_block_names = unplaced_names
            
            return result
            
        except Exception as e:
            print(f"[ERROR] Backtracking algorithm failed: {e}")
            import traceback
            traceback.print_exc()  # 전체 스택 트레이스 출력
            return None
    
    def visualize(self, result, save_path=None, show=True):
        print(f"[INFO] Generating placement result visualization...")
        
        plt.rcParams['font.family'] = ['DejaVu Sans']
        fig, ax_main = plt.subplots(1, 1, figsize=(20, 12))
        
        # 자항선 경계 그리기
        ship_rect = patches.Rectangle(
            (0, 0), result.width, result.height,
            linewidth=3, edgecolor='navy', facecolor='lightblue', alpha=0.3
        )
        ax_main.add_patch(ship_rect)
        
        # 선수 여백
        if result.bow_clearance > 0:
            bow_rect = patches.Rectangle(
                (result.width - result.bow_clearance, 0), 
                result.bow_clearance, result.height,
                linewidth=2, edgecolor='red', facecolor='red', alpha=0.2
            )
            ax_main.add_patch(bow_rect)
        
        # 선미 여백
        if result.stern_clearance > 0:
            stern_rect = patches.Rectangle(
                (0, 0), result.stern_clearance, result.height,
                linewidth=2, edgecolor='purple', facecolor='purple', alpha=0.2
            )
            ax_main.add_patch(stern_rect)
        
        # 배치된 블록들 그리기
        placed_blocks_list = list(result.placed_blocks.values())
        total_blocks = len(placed_blocks_list) + len(result.unplaced_blocks)
        placed_count = len(placed_blocks_list)
        success_rate = (placed_count / total_blocks) * 100 if total_blocks > 0 else 0
        
        type_colors = {
            'crane': 'orange',
            'trestle': 'green',
            'unknown': 'gray'
        }
        
        type_counts = defaultdict(int)
        
        for block in placed_blocks_list:
            if block.position is None:
                continue
            
            type_counts[block.block_type] += 1
            pos_x, pos_y = block.position
            
            color = type_colors.get(block.block_type, 'gray')
            block_footprint = list(block.get_footprint())
            
            for rel_x, rel_y in block_footprint:
                abs_x = pos_x + rel_x - block.min_x
                abs_y = pos_y + rel_y - block.min_y
                
                cell_rect = patches.Rectangle(
                    (abs_x, abs_y), 1, 1,
                    linewidth=0.5, edgecolor='black', 
                    facecolor=color, alpha=0.7
                )
                ax_main.add_patch(cell_rect)
            
            # 블록 ID 표시
            center_x = pos_x + (block.max_x - block.min_x) / 2
            center_y = pos_y + (block.max_y - block.min_y) / 2
            ax_main.text(center_x, center_y, block.id, 
                        ha='center', va='center', fontsize=8, 
                        fontweight='bold', color='white')
        
        
        # 축 설정
        ax_main.set_xlim(-2, result.width + 2)
        ax_main.set_ylim(-2, result.height + 2)
        ax_main.set_xlabel(f'X (grids) | 1 grid = {result.grid_resolution}m', fontsize=12)
        ax_main.set_ylabel(f'Y (grids) | 1 grid = {result.grid_resolution}m', fontsize=12)
        ax_main.set_aspect('equal')
        ax_main.grid(True, alpha=0.3)
        
        total_area = result.width * result.height
        used_area = sum(block.get_area() for block in placed_blocks_list)
        space_utilization = (used_area / total_area) * 100
        
        # 제목
        config_name = self.config['ship_configuration']['name']
        plt.title(f'Config-Based Ship Block Placement Result: {config_name}\\n'
                 f'Ship: {result.ship_width_m}m × {result.ship_height_m}m | '
                 f'Resolution: {result.grid_resolution}m/grid | '
                 f'Placed: {placed_count}/{total_blocks} ({success_rate:.1f}%) | '
                 f'Space Usage: {space_utilization:.1f}% | '
                 f'Time: {result.placement_time:.2f}s',
                 fontsize=16, pad=20)
        
        clearance_m = result.block_spacing * result.grid_resolution
        legend_elements = [
            patches.Patch(color='orange', alpha=0.7, label=f'Crane ({type_counts["crane"]})'),
            patches.Patch(color='green', alpha=0.7, label=f'Trestle ({type_counts["trestle"]})'),
            patches.Patch(color='red', alpha=0.2, label=f'Bow Margin ({result.bow_clearance} grids)'),
            patches.Patch(color='purple', alpha=0.2, label=f'Stern Margin ({result.stern_clearance} grids)'),
            patches.Patch(color='white', alpha=0.0, label=f'Block Clearance: {clearance_m}m'),
            patches.Patch(color='lightblue', alpha=0.3, label='Ship Area')
        ]
        
        if result.unplaced_blocks:
            legend_elements.append(
                patches.Patch(color='red', alpha=0.5, linestyle='--', 
                            label=f'Unplaced ({len(result.unplaced_blocks)})'))
        
        ax_main.legend(handles=legend_elements, loc='upper left', bbox_to_anchor=(1, 1))
        voxel_resolution = self.config['voxelization_settings']['resolution']
        stats_text = f"""Placement Statistics:
Ship: {result.ship_width_m}m × {result.ship_height_m}m
Grid: {result.width} × {result.height} ({result.grid_resolution}m/grid)
Voxel Resolution: {voxel_resolution}m

Blocks:
  Total: {total_blocks}
  Placed: {placed_count}
  Unplaced: {len(result.unplaced_blocks)}
  Success: {success_rate:.1f}%

Block Types (Placed):
  Crane: {type_counts['crane']}
  Trestle: {type_counts['trestle']}
  Unknown: {type_counts['unknown']}

Space Utilization:
  Used: {used_area:,} cells
  Total: {total_area:,} cells
  Ratio: {space_utilization:.1f}%

Performance:
  Time: {result.placement_time:.2f}s
  Method: Backtracking + Real Voxel Shape
"""
        
        ax_main.text(0.02, 0.98, stats_text, transform=ax_main.transAxes, 
                    fontsize=10, va='top', ha='left', fontfamily='monospace',
                    bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", alpha=0.9))
        
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f"       Visualization saved: {save_path}")
        
        if show:
            plt.show()
        
        return fig
    
    def run(self, max_time=60, save_visualization=False):
        print(f"[INFO] Starting config-based ship placement with backtracking...")
        
        try:
            blocks = self.create_blocks_from_config()
            if not blocks:
                print("[ERROR] No blocks to place")
                return None
            
            result = self.place_blocks(blocks, max_time)
            
            if result and save_visualization:
                output_dir = Path(self.config_path).parent / "placement_results"
                output_dir.mkdir(exist_ok=True)
                
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                config_name = Path(self.config_path).stem
                viz_filename = f"config_placement_{config_name}_{timestamp}.png"
                viz_path = output_dir / viz_filename
                
                self.visualize(result, save_path=viz_path, show=True)
            elif not result:
                print("[WARNING] No placement result to visualize")
            
            return result
            
        except Exception as e:
            print(f"[ERROR] Placement failed: {e}")
            return None

def main():
    if len(sys.argv) < 2:
        print("Config-Based Ship Block Placement System")
        print("="*50)
        print("\nUsage:")
        print("  python ship_placer.py <config.json> [max_time] [options]")
        print("\nOptions:")
        print("  -v, --visualize    Enable visualization (default: disabled)")
        print("  --no-viz          Disable visualization (explicit)")
        print("\nAlgorithm:")
        print("  backtracking - Precise placement with rotation support")
        print("\nExamples:")
        print("  python ship_placer.py config.json 60")
        print("  python ship_placer.py config.json 60 -v")
        print("  python ship_placer.py config.json 60 --visualize")
        return
    
    config_path = sys.argv[1]
    max_time = 5
    enable_visualization = False
    
    # 인자 파싱
    for i, arg in enumerate(sys.argv[2:], start=2):
        if arg.isdigit():
            max_time = int(arg)
        elif arg in ['-v', '--visualize']:
            enable_visualization = True
        elif arg == '--no-viz':
            enable_visualization = False
    
    if not Path(config_path).exists():
        print(f"[ERROR] Config file not found: {config_path}")
        return
    
    try:
        print("Config-Based Ship Block Placement")
        print("="*40)
        print(f"Config: {config_path}")
        print(f"Max time: {max_time}s")
        print(f"Algorithm: backtracking")
        print(f"Visualization: {'enabled' if enable_visualization else 'disabled'}")
        print("")
        
        # 배치 시스템 실행
        placer = ShipPlacerConfig(config_path)
        result = placer.run(max_time=max_time, save_visualization=enable_visualization)
        
        if result:
            placed_count = len(result.placed_blocks)
            total_count = placed_count + len(result.unplaced_blocks)
            success_rate = (placed_count / total_count) * 100 if total_count > 0 else 0
            
            print(f"\\n[SUCCESS] Config-Based Placement Complete!")
            print(f"Config: {placer.config['ship_configuration']['name']}")
            print(f"Result: {placed_count}/{total_count} blocks ({success_rate:.1f}%)")
            print(f"Time: {result.placement_time:.2f}s")
            
            # 배치되지 못한 블록 리스트 출력
            if result.unplaced_blocks:
                unplaced_names = [block.id for block_id, block in result.unplaced_blocks.items()]
                print(f"\\nUnplaced blocks: {unplaced_names}")
            
            if enable_visualization:
                print(f"Visualization saved in placement_results/")
        else:
            print("[ERROR] Placement failed")
    
    except Exception as e:
        print(f"[ERROR] {e}")

if __name__ == "__main__":
    main()