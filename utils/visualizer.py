"""
한글 폰트 지원 개선된 Visualizer (기존 visualizer.py 대체)
utils/visualizer.py
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib.patches as patches
from matplotlib.colors import to_rgba
import random
import warnings

# 한글 폰트 설정
def setup_korean_font():
    """한글 폰트 자동 설정"""
    try:
        import platform
        import matplotlib.font_manager as fm
        
        system = platform.system()
        
        if system == "Windows":
            korean_fonts = ["Malgun Gothic", "맑은 고딕", "Gulim", "굴림"]
        elif system == "Darwin":  # macOS
            korean_fonts = ["AppleGothic", "Apple SD Gothic Neo", "Nanum Gothic"]
        else:  # Linux
            korean_fonts = ["Nanum Gothic", "나눔고딕", "UnDotum"]
        
        available_fonts = [f.name for f in fm.fontManager.ttflist]
        
        for font in korean_fonts:
            if font in available_fonts:
                plt.rcParams['font.family'] = font
                plt.rcParams['axes.unicode_minus'] = False
                return True
        
        return False
        
    except Exception:
        return False

# 폰트 경고 억제
warnings.filterwarnings('ignore', category=UserWarning, module='matplotlib')
warnings.filterwarnings('ignore', message='.*missing from font.*')
warnings.filterwarnings('ignore', message='.*Glyph.*missing.*')

# 한글 폰트 설정 시도
KOREAN_FONT_AVAILABLE = setup_korean_font()

class Visualizer:
    """
    한글 폰트 지원 개선된 블록 배치 시각화 도구
    """

    def __init__(self):
        """Visualizer 초기화"""
        self.block_colors = {}
        
        # 폰트 설정 확인
        if not KOREAN_FONT_AVAILABLE:
            print("⚠️ 한글 폰트를 찾을 수 없습니다. 영문으로 표시됩니다.")
    
    def _get_safe_text(self, text, fallback_text=None):
        """
        안전한 텍스트 반환 (한글 폰트 없을 때 영문 대체)
        
        Args:
            text (str): 원본 텍스트
            fallback_text (str): 대체 텍스트
            
        Returns:
            str: 표시할 텍스트
        """
        if KOREAN_FONT_AVAILABLE:
            return text
        else:
            return fallback_text if fallback_text else text

    def _get_block_color(self, block_id):
        """
        블록 ID에 대한 색상 반환 (일관성 유지)
        """
        if block_id not in self.block_colors:
            r = random.uniform(0.4, 0.8)
            g = random.uniform(0.4, 0.8)
            b = random.uniform(0.4, 0.8)
            self.block_colors[block_id] = (r, g, b, 0.8)
        return self.block_colors[block_id]

    def visualize_2d(self, placement_area, title="2D Block Placement", show=True, save_path=None):
        """
        2D 배치도 시각화 (한글 폰트 지원)
        """
        fig, ax = plt.subplots(figsize=(10, 10))

        # 배치 영역 경계 설정
        ax.set_xlim(0, placement_area.width)
        ax.set_ylim(0, placement_area.height)
        ax.grid(True, linestyle='--', alpha=0.7)
        ax.set_aspect('equal')

        # 배치된 블록 표시
        for block_id, block in placement_area.placed_blocks.items():
            color = self._get_block_color(block_id)
            footprint = block.get_positioned_footprint()

            # 각 복셀 표시
            for x, y in footprint:
                rect = patches.Rectangle(
                    (x, y), 1, 1,
                    linewidth=1,
                    edgecolor='black',
                    facecolor=color,
                    alpha=0.8
                )
                ax.add_patch(rect)

                # 블록 ID 표시 (첫 번째 복셀에만)
                if (x, y) == next(iter(footprint)):
                    ax.text(
                        x + 0.5, y + 0.5,
                        block_id,
                        ha='center', va='center',
                        fontsize=8, fontweight='bold'
                    )

        # 축 레이블 설정
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        
        # 제목 설정 (한글 폰트 고려)
        safe_title = self._get_safe_text(title, "2D Block Placement")
        ax.set_title(safe_title)

        # 배치 정보 표시
        placed_text = self._get_safe_text("배치됨", "Placed")
        unplaced_text = self._get_safe_text("미배치", "Unplaced")
        score_text = self._get_safe_text("점수", "Score")
        
        info_text = f"{placed_text}: {len(placement_area.placed_blocks)}, " \
                   f"{unplaced_text}: {len(placement_area.unplaced_blocks)}, " \
                   f"{score_text}: {placement_area.get_placement_score():.4f}"
        
        ax.text(
            0.5, -0.05,
            info_text,
            ha='center', va='center',
            transform=ax.transAxes,
            fontsize=10
        )

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        if show:
            plt.show()
        else:
            plt.close()

        return fig

    def visualize_3d(self, placement_area, title="3D Block Placement", show=True, save_path=None):
        """
        3D 배치 결과 시각화 (한글 폰트 지원)
        """
        fig = plt.figure(figsize=(12, 10))
        ax = fig.add_subplot(111, projection='3d')

        # 배치된 블록 표시
        for block_id, block in placement_area.placed_blocks.items():
            color = self._get_block_color(block_id)
            voxels = block.get_positioned_voxels()

            # 각 복셀 표시
            for x, y, heights in voxels:
                empty_below, filled, empty_above = heights

                # 채워진 공간 표시
                for z in range(empty_below, empty_below + filled):
                    ax.bar3d(
                        x, y, z,
                        1, 1, 1,
                        color=color,
                        alpha=0.8,
                        shade=True
                    )

        # 축 레이블 설정
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_zlabel('Z')
        
        # 제목 설정 (한글 폰트 고려)
        safe_title = self._get_safe_text(title, "3D Block Placement")
        ax.set_title(safe_title)

        # 축 범위 설정
        ax.set_xlim(0, placement_area.width)
        ax.set_ylim(0, placement_area.height)
        ax.set_zlim(0, 10)
        ax.set_box_aspect([placement_area.width, placement_area.height, 10])

        # 배치 정보 표시
        placed_text = self._get_safe_text("배치됨", "Placed")
        unplaced_text = self._get_safe_text("미배치", "Unplaced")
        score_text = self._get_safe_text("점수", "Score")
        
        info_text = f"{placed_text}: {len(placement_area.placed_blocks)}, " \
                   f"{unplaced_text}: {len(placement_area.unplaced_blocks)}, " \
                   f"{score_text}: {placement_area.get_placement_score():.4f}"
        
        ax.text2D(
            0.5, 0.05,
            info_text,
            ha='center', va='center',
            transform=ax.transAxes,
            fontsize=10
        )

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        if show:
            plt.show()
        else:
            plt.close()

        return fig

    def compare_blocks(self, original_blocks, placement_area, title="Block Placement Comparison", show=True, save_path=None):
        """
        원본 블록과 배치 결과 비교 시각화 (한글 폰트 지원)
        """
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(18, 9))
        plt.subplots_adjust(wspace=0.3)

        # 원본 블록 표시 (왼쪽)
        max_block_width = max(block.width for block in original_blocks)
        max_block_height = max(block.height for block in original_blocks)

        blocks_per_row = min(5, len(original_blocks))
        rows = (len(original_blocks) + blocks_per_row - 1) // blocks_per_row

        total_width = blocks_per_row * (max_block_width + 2)
        total_height = rows * (max_block_height + 2)

        ax1.set_xlim(0, total_width)
        ax1.set_ylim(0, total_height)
        ax1.grid(True, linestyle='--', alpha=0.7)
        ax1.set_aspect('equal')

        # 각 블록을 순서대로 나열
        for i, block in enumerate(original_blocks):
            color = self._get_block_color(block.id)

            row = i // blocks_per_row
            col = i % blocks_per_row

            start_x = col * (max_block_width + 2) + 1
            start_y = (rows - 1 - row) * (max_block_height + 2) + 1

            center_x = start_x + (max_block_width - block.width) // 2
            center_y = start_y + (max_block_height - block.height) // 2

            footprint = block.get_footprint()

            # 각 복셀 표시
            for vx, vy in footprint:
                grid_x = center_x + (vx - block.min_x)
                grid_y = center_y + (vy - block.min_y)

                rect = patches.Rectangle(
                    (grid_x, grid_y), 1, 1,
                    linewidth=1,
                    edgecolor='black',
                    facecolor=color,
                    alpha=0.8
                )
                ax1.add_patch(rect)

            # 블록 ID 표시
            ax1.text(
                center_x + block.width / 2,
                center_y + block.height / 2,
                block.id,
                ha='center', va='center',
                fontsize=10, fontweight='bold'
            )

        # 왼쪽 제목
        original_title = self._get_safe_text("원본 블록", "Original Blocks")
        ax1.set_title(original_title)

        # 배치 결과 표시 (오른쪽)
        ax2.set_xlim(0, placement_area.width)
        ax2.set_ylim(0, placement_area.height)
        ax2.grid(True, linestyle='--', alpha=0.7)
        ax2.set_aspect('equal')

        # 배치된 블록 표시
        for block_id, block in placement_area.placed_blocks.items():
            color = self._get_block_color(block_id)
            footprint = block.get_positioned_footprint()

            # 각 복셀 표시
            for x, y in footprint:
                rect = patches.Rectangle(
                    (x, y), 1, 1,
                    linewidth=1,
                    edgecolor='black',
                    facecolor=color,
                    alpha=0.8
                )
                ax2.add_patch(rect)

                # 블록 ID 표시 (첫 번째 복셀에만)
                if (x, y) == next(iter(footprint)):
                    ax2.text(
                        x + 0.5, y + 0.5,
                        block_id,
                        ha='center', va='center',
                        fontsize=8, fontweight='bold'
                    )

        # 미배치 블록 표시
        if placement_area.unplaced_blocks:
            unplaced_text = self._get_safe_text("미배치", "Unplaced")
            unplaced_ids = ", ".join(placement_area.unplaced_blocks.keys())
            unplaced_info = f"{unplaced_text}: {unplaced_ids}"
            ax2.text(
                0.5, -0.05,
                unplaced_info,
                ha='center', va='center',
                transform=ax2.transAxes,
                fontsize=10,
                color='red'
            )

        # 오른쪽 제목
        result_title = self._get_safe_text("배치 결과", "Placement Result")
        ax2.set_title(result_title)

        # 전체 제목 및 정보
        placed_text = self._get_safe_text("배치됨", "Placed")
        unplaced_text = self._get_safe_text("미배치", "Unplaced")
        score_text = self._get_safe_text("점수", "Score")
        
        info_text = f"{placed_text}: {len(placement_area.placed_blocks)}, " \
                   f"{unplaced_text}: {len(placement_area.unplaced_blocks)}, " \
                   f"{score_text}: {placement_area.get_placement_score():.4f}"
        
        safe_title = self._get_safe_text(title, "Block Placement Comparison")
        fig.suptitle(f"{safe_title}\n{info_text}", fontsize=14)

        plt.tight_layout()

        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')

        if show:
            plt.show()
        else:
            plt.close()

        return fig