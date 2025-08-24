"""
AUTO 자동 방향 최적화 기능이 추가된 3D → 2.5D 복셀 변환기 (선박 블록 최적화 버전)
- 바닥 접촉면을 최대화하는 자동 방향 최적화 기능 추가
- 선박 블록 배치에 최적화된 고정 해상도 (0.2m) 기본 사용
- 사용자가 원하면 해상도 임의 설정 가능
- 모든 블록에 동일한 해상도 적용으로 배치 정확성 보장
- 시각화 결과 자동 이미지 저장 기능 추가
"""
import trimesh
import numpy as np
import sys
import os
import time
from pathlib import Path
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import warnings

warnings.filterwarnings('ignore')

# 프로젝트 모듈 import
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

try:
    from models.voxel_block import VoxelBlock
    print(f"[INFO] Project modules loaded successfully")
except ImportError as e:
    print(f"[ERROR] Cannot find project modules: {e}")
    sys.exit(1)

# SHIP 선박 블록 배치 최적화 설정
SHIP_BLOCK_OPTIMAL_RESOLUTION = 0.5  # 0.5m - 선박 블록에 최적화된 해상도
GRID_UNIT = 0.5  # 자항선 격자 단위 (0.5m) - 해상도와 동일
RESOLUTION_FACTOR = GRID_UNIT / SHIP_BLOCK_OPTIMAL_RESOLUTION  # 1개 셀 = 0.5m

class OptimizedVoxelizer:
    """선박 블록 배치에 최적화된 3D 복셀화 클래스 (자동 방향 최적화 기능 포함)"""
    
    def __init__(self, fixed_resolution=SHIP_BLOCK_OPTIMAL_RESOLUTION, target_voxels=1000, enable_orientation_optimization=True):
        """
        Args:
            fixed_resolution (float): 고정 해상도 (기본: 0.5m - 선박 블록 최적화)
            target_voxels (int): 목표 복셀 수 (해상도 고정시에는 참고용)
            enable_orientation_optimization (bool): 자동 방향 최적화 활성화
        """
        self.fixed_resolution = fixed_resolution
        self.target_voxels = target_voxels
        self.enable_orientation_optimization = enable_orientation_optimization
        
        print(f"[INFO] SHIP 선박 블록 최적화 모드 (개선된 버전)")
        print(f"  - 고정 해상도: {self.fixed_resolution}m")
        print(f"  - 자항선 격자 호환성: {GRID_UNIT}m ÷ {self.fixed_resolution}m = {RESOLUTION_FACTOR:.0f}개 셀")
        print(f"  - AUTO 자동 방향 최적화: {'ON' if self.enable_orientation_optimization else 'OFF'}")
    
    def process_mesh_file(self, file_path):
        """메시 파일 처리 - 품질 개선"""
        print(f"[INFO] Processing mesh file: {Path(file_path).name}")
        
        # 1. 메시 로드
        mesh = trimesh.load(file_path)
        print(f"  - Loaded: {len(mesh.vertices):,} vertices, {len(mesh.faces):,} faces")
        
        # 2. 메시 품질 체크 및 개선
        print("  - Improving mesh quality...")
        original_watertight = mesh.is_watertight
        print(f"    Original watertight: {original_watertight}")
        
        # 메시 수리
        mesh.merge_vertices()
        mesh.remove_degenerate_faces()
        mesh.remove_duplicate_faces()
        mesh.remove_infinite_values()
        
        # 구멍 메우기 (watertight 만들기)
        if not mesh.is_watertight:
            print("    Filling holes...")
            try:
                mesh.fill_holes()
                print(f"    After repair watertight: {mesh.is_watertight}")
            except Exception as e:
                print(f"    Hole filling failed: {e}")
        
        # 3. 단위 자동 감지 및 스케일 조정
        bbox = mesh.bounds
        size = bbox[1] - bbox[0]
        max_dimension = max(size)
        
        print(f"  - Original size: {size[0]:.2f} x {size[1]:.2f} x {size[2]:.2f}")
        
        # 스마트 스케일 조정
        if max_dimension < 0.01:
            mesh.apply_scale(0.001)  # mm → m
            print("  - Unit conversion: mm → m")
        elif max_dimension < 1.0:
            mesh.apply_scale(0.01)   # cm → m  
            print("  - Unit conversion: cm → m")
        elif max_dimension > 100:
            mesh.apply_scale(0.01)   # 너무 큰 경우
            print("  - Size adjustment: downscale")
        
        # 최종 크기가 너무 작으면 강제 확대
        final_bbox = mesh.bounds
        final_size = final_bbox[1] - final_bbox[0]
        final_max = max(final_size)
        if final_max < 2.0:  # 2m 미만이면 확대
            scale_up = 5.0 / final_max
            mesh.apply_scale(scale_up)
            print(f"  - Additional scaling: x{scale_up:.2f}")
        
        # 4. 메시 중심화 (원점 기준)
        mesh.apply_translation(-mesh.centroid)
        mesh.apply_translation([0, 0, -mesh.bounds[0][2]])  # Z 바닥을 0으로
        
        print(f"  - Final size: {mesh.bounds[1] - mesh.bounds[0]}")
        print(f"  - Final watertight: {mesh.is_watertight}")
        
        return mesh
    
    def get_resolution(self, mesh=None):
        """
        해상도 반환 (고정 해상도 사용)
        
        Args:
            mesh: 메시 객체 (고정 해상도 모드에서는 사용 안함)
            
        Returns:
            float: 사용할 해상도
        """
        resolution = self.fixed_resolution
        
        if mesh is not None:
            bbox = mesh.bounds
            size = bbox[1] - bbox[0]
            volume = size[0] * size[1] * size[2]
            expected_voxels = volume / (resolution ** 3)
            
            print(f"  - Fixed resolution: {resolution}m")
            print(f"  - Expected voxel count: {expected_voxels:,.0f}")
            print(f"  - Grid size: {int(size[0]/resolution)} x {int(size[1]/resolution)} x {int(size[2]/resolution)}")
        
        return resolution
    
    def optimize_block_orientation(self, voxels_3d, bbox):
        """
        [AUTO] 블록을 바닥 접촉 면적이 최대가 되도록 자동 회전
        
        Args:
            voxels_3d (numpy.ndarray): 3D 복셀 배열
            bbox: 바운딩 박스
            
        Returns:
            tuple: (최적화된 voxels_3d, 업데이트된 bbox, 선택된 방향)
        """
        if not self.enable_orientation_optimization:
            return voxels_3d, bbox, "original"
        
        print(f"[INFO] AUTO 자동 방향 최적화 시작...")
        
        x_size, y_size, z_size = voxels_3d.shape
        
        # 3가지 방향의 바닥 면적 계산
        orientations = {
            'xy_plane': np.sum(np.any(voxels_3d, axis=2)),  # Z축 기본 (XY 평면이 바닥)
            'xz_plane': np.sum(np.any(voxels_3d, axis=1)),  # Y축 회전 (XZ 평면이 바닥)
            'yz_plane': np.sum(np.any(voxels_3d, axis=0))   # X축 회전 (YZ 평면이 바닥)
        }
        
        print(f"  - 방향별 바닥 면적:")
        print(f"    XY 평면 (기본): {orientations['xy_plane']} cells")
        print(f"    XZ 평면 (Y회전): {orientations['xz_plane']} cells") 
        print(f"    YZ 평면 (X회전): {orientations['yz_plane']} cells")
        
        # 가장 큰 바닥 면적을 가지는 방향 선택
        best_orientation = max(orientations, key=orientations.get)
        best_area = orientations[best_orientation]
        
        # 원본과의 개선 정도 계산
        improvement_xz = (orientations['xz_plane'] - orientations['xy_plane']) / orientations['xy_plane'] * 100
        improvement_yz = (orientations['yz_plane'] - orientations['xy_plane']) / orientations['xy_plane'] * 100
        
        print(f"  - 개선 정도: XZ방향 {improvement_xz:+.1f}%, YZ방향 {improvement_yz:+.1f}%")
        
        # 새로운 바운딩 박스 계산을 위한 크기 정보
        bbox_size = bbox[1] - bbox[0]
        bbox_center = (bbox[0] + bbox[1]) / 2
        
        if best_orientation == 'xz_plane':  # Y축 90도 회전 (얇은 판이 눕도록)
            voxels_optimized = np.transpose(voxels_3d, (0, 2, 1))
            # 바운딩 박스 업데이트: Y와 Z 축 교환
            new_size = [bbox_size[0], bbox_size[2], bbox_size[1]]
            new_bbox = [
                [bbox_center[0] - new_size[0]/2, bbox_center[1] - new_size[1]/2, bbox_center[2] - new_size[2]/2],
                [bbox_center[0] + new_size[0]/2, bbox_center[1] + new_size[1]/2, bbox_center[2] + new_size[2]/2]
            ]
            print(f"  [OK] 블록 회전 적용: Y→Z 축 교환 (바닥면적 {best_area} cells)")
            print(f"     크기 변화: {bbox_size[0]:.1f}×{bbox_size[1]:.1f}×{bbox_size[2]:.1f} → {new_size[0]:.1f}×{new_size[1]:.1f}×{new_size[2]:.1f}")
            return voxels_optimized, new_bbox, "Y_rotated"
            
        elif best_orientation == 'yz_plane':  # X축 90도 회전
            voxels_optimized = np.transpose(voxels_3d, (2, 1, 0))
            # 바운딩 박스 업데이트: X와 Z 축 교환  
            new_size = [bbox_size[2], bbox_size[1], bbox_size[0]]
            new_bbox = [
                [bbox_center[0] - new_size[0]/2, bbox_center[1] - new_size[1]/2, bbox_center[2] - new_size[2]/2],
                [bbox_center[0] + new_size[0]/2, bbox_center[1] + new_size[1]/2, bbox_center[2] + new_size[2]/2]
            ]
            print(f"  [OK] 블록 회전 적용: X→Z 축 교환 (바닥면적 {best_area} cells)")
            print(f"     크기 변화: {bbox_size[0]:.1f}×{bbox_size[1]:.1f}×{bbox_size[2]:.1f} → {new_size[0]:.1f}×{new_size[1]:.1f}×{new_size[2]:.1f}")
            return voxels_optimized, new_bbox, "X_rotated"
            
        else:
            print(f"  [OK] 원본 방향이 최적 (바닥면적 {best_area} cells)")
            return voxels_3d, bbox, "original"
    
    def voxelize_improved(self, mesh, resolution):
        """개선된 복셀화 - Trimesh 내장 + Multi-directional 보정 + 자동 방향 최적화"""
        print("  - Starting optimized voxelization with orientation optimization...")
        print(f"    Using fixed resolution: {resolution}m (ship block optimized)")
        
        # 방법 1: Trimesh 내장 복셀화 (가장 정확)
        try:
            print("    Method 1: Trimesh built-in voxelization")
            voxelized_mesh = mesh.voxelized(pitch=resolution)
            voxels_method1 = voxelized_mesh.matrix
            bbox = voxelized_mesh.bounds
            
            print(f"    - Built-in result: {np.sum(voxels_method1):,} voxels")
            
            # 성공했으면 자동 방향 최적화 적용
            if np.sum(voxels_method1) > 0:
                print("    - Using built-in voxelization as primary result")
                
                # [AUTO] 자동 방향 최적화 적용
                voxels_optimized, bbox_optimized, orientation = self.optimize_block_orientation(voxels_method1, bbox)
                
                return voxels_optimized, bbox_optimized, resolution, orientation
                
        except Exception as e:
            print(f"    - Built-in voxelization failed: {e}")
            voxels_method1 = None
        
        # 방법 2: Multi-directional Ray Casting (백업)
        print("    Method 2: Multi-directional ray casting")
        voxels_method2 = self._multi_directional_voxelize(mesh, resolution)
        
        if voxels_method2 is not None:
            bbox = mesh.bounds
            print(f"    - Multi-directional result: {np.sum(voxels_method2):,} voxels")
            
            # [AUTO] 자동 방향 최적화 적용
            voxels_optimized, bbox_optimized, orientation = self.optimize_block_orientation(voxels_method2, bbox)
            
            return voxels_optimized, bbox_optimized, resolution, orientation
        
        # 방법 3: 기존 Z-ray casting (최후 수단)
        print("    Method 3: Fallback Z-ray casting")
        voxels_method3 = self._fallback_voxelize(mesh, resolution)
        bbox = mesh.bounds
        print(f"    - Fallback result: {np.sum(voxels_method3):,} voxels")
        
        # [AUTO] 자동 방향 최적화 적용
        voxels_optimized, bbox_optimized, orientation = self.optimize_block_orientation(voxels_method3, bbox)
        
        return voxels_optimized, bbox_optimized, resolution, orientation
    
    def _multi_directional_voxelize(self, mesh, resolution):
        """다방향 레이캐스팅 복셀화"""
        bbox = mesh.bounds
        size = bbox[1] - bbox[0]
        
        x_voxels = max(1, int(np.ceil(size[0] / resolution)))
        y_voxels = max(1, int(np.ceil(size[1] / resolution)))
        z_voxels = max(1, int(np.ceil(size[2] / resolution)))
        
        print(f"      Grid: {x_voxels} x {y_voxels} x {z_voxels}")
        
        # 3방향에서 레이캐스팅
        voxels_x = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        voxels_y = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        voxels_z = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        
        try:
            # Z 방향 (기존)
            print("      - Z-direction ray casting...")
            voxels_z = self._ray_cast_z_direction(mesh, bbox, resolution, x_voxels, y_voxels, z_voxels)
            
            # X 방향
            print("      - X-direction ray casting...")
            voxels_x = self._ray_cast_x_direction(mesh, bbox, resolution, x_voxels, y_voxels, z_voxels)
            
            # Y 방향
            print("      - Y-direction ray casting...")
            voxels_y = self._ray_cast_y_direction(mesh, bbox, resolution, x_voxels, y_voxels, z_voxels)
            
            # 3방향 결과 통합 (합집합)
            voxels_combined = voxels_x | voxels_y | voxels_z
            
            print(f"      - X-dir: {np.sum(voxels_x):,}, Y-dir: {np.sum(voxels_y):,}, Z-dir: {np.sum(voxels_z):,}")
            print(f"      - Combined: {np.sum(voxels_combined):,} voxels")
            
            return voxels_combined
            
        except Exception as e:
            print(f"      - Multi-directional failed: {e}")
            return None
    
    def _ray_cast_z_direction(self, mesh, bbox, resolution, x_voxels, y_voxels, z_voxels):
        """Z방향 레이캐스팅"""
        voxels = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        
        for i in range(x_voxels):
            for j in range(y_voxels):
                x_pos = bbox[0][0] + (i + 0.5) * resolution
                y_pos = bbox[0][1] + (j + 0.5) * resolution
                
                ray_origin = [x_pos, y_pos, bbox[0][2] - resolution]
                ray_direction = [0, 0, 1]
                
                try:
                    locations, _, _ = mesh.ray.intersects_location([ray_origin], [ray_direction])
                    
                    if len(locations) >= 2:
                        z_coords = sorted([loc[2] for loc in locations])
                        for idx in range(0, len(z_coords) - 1, 2):
                            z_start = z_coords[idx]
                            z_end = z_coords[idx + 1] if idx + 1 < len(z_coords) else z_coords[idx]
                            
                            k_start = max(0, int((z_start - bbox[0][2]) / resolution))
                            k_end = min(z_voxels, int((z_end - bbox[0][2]) / resolution) + 1)
                            
                            for k in range(k_start, k_end):
                                voxels[i, j, k] = True
                    
                    elif len(locations) == 1:
                        z_pos = locations[0][2]
                        k = int((z_pos - bbox[0][2]) / resolution)
                        if 0 <= k < z_voxels:
                            voxels[i, j, k] = True
                except:
                    continue
        
        return voxels
    
    def _ray_cast_x_direction(self, mesh, bbox, resolution, x_voxels, y_voxels, z_voxels):
        """X방향 레이캐스팅"""
        voxels = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        
        for j in range(y_voxels):
            for k in range(z_voxels):
                y_pos = bbox[0][1] + (j + 0.5) * resolution
                z_pos = bbox[0][2] + (k + 0.5) * resolution
                
                ray_origin = [bbox[0][0] - resolution, y_pos, z_pos]
                ray_direction = [1, 0, 0]
                
                try:
                    locations, _, _ = mesh.ray.intersects_location([ray_origin], [ray_direction])
                    
                    if len(locations) >= 2:
                        x_coords = sorted([loc[0] for loc in locations])
                        for idx in range(0, len(x_coords) - 1, 2):
                            x_start = x_coords[idx]
                            x_end = x_coords[idx + 1] if idx + 1 < len(x_coords) else x_coords[idx]
                            
                            i_start = max(0, int((x_start - bbox[0][0]) / resolution))
                            i_end = min(x_voxels, int((x_end - bbox[0][0]) / resolution) + 1)
                            
                            for i in range(i_start, i_end):
                                voxels[i, j, k] = True
                    
                    elif len(locations) == 1:
                        x_pos_hit = locations[0][0]
                        i = int((x_pos_hit - bbox[0][0]) / resolution)
                        if 0 <= i < x_voxels:
                            voxels[i, j, k] = True
                except:
                    continue
        
        return voxels
    
    def _ray_cast_y_direction(self, mesh, bbox, resolution, x_voxels, y_voxels, z_voxels):
        """Y방향 레이캐스팅"""
        voxels = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        
        for i in range(x_voxels):
            for k in range(z_voxels):
                x_pos = bbox[0][0] + (i + 0.5) * resolution
                z_pos = bbox[0][2] + (k + 0.5) * resolution
                
                ray_origin = [x_pos, bbox[0][1] - resolution, z_pos]
                ray_direction = [0, 1, 0]
                
                try:
                    locations, _, _ = mesh.ray.intersects_location([ray_origin], [ray_direction])
                    
                    if len(locations) >= 2:
                        y_coords = sorted([loc[1] for loc in locations])
                        for idx in range(0, len(y_coords) - 1, 2):
                            y_start = y_coords[idx]
                            y_end = y_coords[idx + 1] if idx + 1 < len(y_coords) else y_coords[idx]
                            
                            j_start = max(0, int((y_start - bbox[0][1]) / resolution))
                            j_end = min(y_voxels, int((y_end - bbox[0][1]) / resolution) + 1)
                            
                            for j in range(j_start, j_end):
                                voxels[i, j, k] = True
                    
                    elif len(locations) == 1:
                        y_pos_hit = locations[0][1]
                        j = int((y_pos_hit - bbox[0][1]) / resolution)
                        if 0 <= j < y_voxels:
                            voxels[i, j, k] = True
                except:
                    continue
        
        return voxels
    
    def _fallback_voxelize(self, mesh, resolution):
        """기존 방식 (최후 수단)"""
        bbox = mesh.bounds
        size = bbox[1] - bbox[0]
        
        x_voxels = max(1, int(np.ceil(size[0] / resolution)))
        y_voxels = max(1, int(np.ceil(size[1] / resolution)))
        z_voxels = max(1, int(np.ceil(size[2] / resolution)))
        
        voxels = np.zeros((x_voxels, y_voxels, z_voxels), dtype=bool)
        
        for i in range(x_voxels):
            for j in range(y_voxels):
                x_pos = bbox[0][0] + (i + 0.5) * resolution
                y_pos = bbox[0][1] + (j + 0.5) * resolution
                
                ray_origin = [x_pos, y_pos, bbox[0][2] - resolution]
                ray_direction = [0, 0, 1]
                
                try:
                    locations, _, _ = mesh.ray.intersects_location([ray_origin], [ray_direction])
                    
                    if len(locations) >= 2:
                        z_coords = sorted([loc[2] for loc in locations])
                        for idx in range(0, len(z_coords) - 1, 2):
                            z_start = z_coords[idx]
                            z_end = z_coords[idx + 1] if idx + 1 < len(z_coords) else z_coords[idx]
                            
                            k_start = max(0, int((z_start - bbox[0][2]) / resolution))
                            k_end = min(z_voxels, int((z_end - bbox[0][2]) / resolution) + 1)
                            
                            for k in range(k_start, k_end):
                                voxels[i, j, k] = True
                    
                    elif len(locations) == 1:
                        z_pos = locations[0][2]
                        k = int((z_pos - bbox[0][2]) / resolution)
                        if 0 <= k < z_voxels:
                            voxels[i, j, k] = True
                except:
                    continue
        
        return voxels

class VoxelConverter25D:
    """3D → 2.5D 복셀 변환기"""
    
    def __init__(self):
        pass
    
    def convert_3d_to_25d(self, voxels_3d, bbox, resolution, method='footprint'):
        """3D 복셀을 2.5D 복셀로 변환"""
        print(f"[INFO] Converting 3D → 2.5D using '{method}' method...")
        
        if voxels_3d is None or np.sum(voxels_3d) == 0:
            print("[WARNING] No 3D voxels to convert")
            return []
        
        if method == 'footprint':
            return self._convert_footprint_method(voxels_3d, bbox, resolution)
        elif method == 'height_map':
            return self._convert_height_map_method(voxels_3d, bbox, resolution)
        elif method == 'outline':
            return self._convert_outline_method(voxels_3d, bbox, resolution)
        else:
            raise ValueError(f"Unknown method: {method}")
    
    def _convert_footprint_method(self, voxels_3d, bbox, resolution):
        """Footprint 방법: 외곽 윤곽선 기반 변환"""
        print("  - Using footprint method (외곽 윤곽선 기반)")
        
        x_size, y_size, z_size = voxels_3d.shape
        voxel_data_25d = []
        
        # 2D 바닥 면적(footprint) 계산: Z축을 따라 OR 연산
        footprint = np.any(voxels_3d, axis=2)
        print(f"  - Footprint calculated: {np.sum(footprint)} occupied positions")
        
        # 각 (x, y) 위치에서 높이 정보 계산
        for x in range(x_size):
            for y in range(y_size):
                if footprint[x, y]:
                    # Z 방향으로 복셀이 있는 층들 찾기
                    z_indices = np.where(voxels_3d[x, y, :])[0]
                    
                    if len(z_indices) > 0:
                        z_min = z_indices[0]
                        z_max = z_indices[-1]
                        
                        # 2.5D 형식: [empty_below, filled, empty_above]
                        empty_below = z_min
                        filled = z_max - z_min + 1
                        empty_above = z_size - z_max - 1
                        
                        voxel_data_25d.append((x, y, [empty_below, filled, empty_above]))
        
        print(f"  - 2.5D conversion complete: {len(voxel_data_25d)} voxel positions")
        return voxel_data_25d
    
    def _convert_height_map_method(self, voxels_3d, bbox, resolution):
        """Height Map 방법"""
        print("  - Using height map method (높이 맵 기반)")
        
        x_size, y_size, z_size = voxels_3d.shape
        voxel_data_25d = []
        
        for x in range(x_size):
            for y in range(y_size):
                z_indices = np.where(voxels_3d[x, y, :])[0]
                
                if len(z_indices) > 0:
                    max_height = np.max(z_indices) + 1
                    voxel_data_25d.append((x, y, [0, max_height, z_size - max_height]))
        
        print(f"  - 2.5D conversion complete: {len(voxel_data_25d)} voxel positions")
        return voxel_data_25d
    
    def _convert_outline_method(self, voxels_3d, bbox, resolution):
        """Outline 방법"""
        print("  - Using outline method (윤곽선만 추출)")
        
        x_size, y_size, z_size = voxels_3d.shape
        voxel_data_25d = []
        
        footprint = np.any(voxels_3d, axis=2)
        
        for x in range(x_size):
            for y in range(y_size):
                if footprint[x, y]:
                    # 경계 검사
                    is_boundary = False
                    for dx in [-1, 0, 1]:
                        for dy in [-1, 0, 1]:
                            if dx == 0 and dy == 0:
                                continue
                            
                            nx, ny = x + dx, y + dy
                            if (nx < 0 or nx >= x_size or 
                                ny < 0 or ny >= y_size or 
                                not footprint[nx, ny]):
                                is_boundary = True
                                break
                        if is_boundary:
                            break
                    
                    if is_boundary:
                        z_indices = np.where(voxels_3d[x, y, :])[0]
                        if len(z_indices) > 0:
                            z_min = z_indices[0]
                            z_max = z_indices[-1]
                            
                            empty_below = z_min
                            filled = z_max - z_min + 1
                            empty_above = z_size - z_max - 1
                            
                            voxel_data_25d.append((x, y, [empty_below, filled, empty_above]))
        
        print(f"  - 2.5D conversion complete: {len(voxel_data_25d)} boundary positions")
        return voxel_data_25d
    
    def create_voxel_block(self, voxel_data_25d, block_id="converted_block"):
        """2.5D 복셀 데이터로부터 VoxelBlock 객체 생성"""
        if not voxel_data_25d:
            print("[WARNING] No 2.5D voxel data to create block")
            return None
        
        print(f"[INFO] Creating VoxelBlock with {len(voxel_data_25d)} voxels...")
        voxel_block = VoxelBlock(block_id, voxel_data_25d)
        print(f"  - Block created: {voxel_block}")
        return voxel_block

class ImprovedVisualizer:
    """개선된 시각화 클래스 (이미지 저장 기능 포함)"""
    
    def __init__(self, output_dir="voxel_results_improved"):
        """
        Args:
            output_dir (str): 결과 이미지 저장 디렉토리
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        print(f"[INFO] [DIR] 개선된 시각화 결과 저장 디렉토리: {self.output_dir}")
    
    def visualize_improved_comparison(self, voxels_3d, voxel_data_25d_list, bbox, resolution, block_id):
        """자동 방향 최적화가 적용된 변환 결과 비교 시각화 + 이미지 저장"""
        print(f"[INFO] Creating orientation-optimized comparison visualization...")
        
        fig = plt.figure(figsize=(24, 16))
        fig.suptitle(f'[AUTO] Auto-Orientation Optimized 3D → 2.5D Conversion: {block_id}\nFixed Resolution: {resolution}m (Maximum Floor Contact)', 
                    fontsize=16, fontweight='bold')
        
        num_methods = len(voxel_data_25d_list)
        
        # 1행: 3D 원본 (여러 각도)
        ax_3d_1 = plt.subplot2grid((4, num_methods + 1), (0, 0), projection='3d')
        self.render_3d_voxels_smooth(ax_3d_1, voxels_3d, bbox, resolution, view='isometric')
        ax_3d_1.set_title('3D Optimized\n(Isometric)', fontsize=10, fontweight='bold')
        
        ax_3d_2 = plt.subplot2grid((4, num_methods + 1), (0, 1), projection='3d')
        self.render_3d_voxels_smooth(ax_3d_2, voxels_3d, bbox, resolution, view='top')
        ax_3d_2.set_title('3D Optimized\n(Top View)', fontsize=10, fontweight='bold')
        
        # 1행 나머지: 각 방법별 2.5D Top View
        for i, result_dict in enumerate(voxel_data_25d_list):
            if i < num_methods - 1:  # 공간이 있는 경우만
                method_name = result_dict['method']
                voxel_data_25d = result_dict['voxel_data']
                ax_25d_top = plt.subplot2grid((4, num_methods + 1), (0, i + 2))
                self.render_25d_top_view_improved(ax_25d_top, voxel_data_25d)
                ax_25d_top.set_title(f'2.5D {method_name}\n(Top View)', fontsize=10, fontweight='bold')
        
        # 2행: 각 방법별 2.5D 3D View
        for i, result_dict in enumerate(voxel_data_25d_list):
            method_name = result_dict['method']
            voxel_data_25d = result_dict['voxel_data']
            ax_25d_3d = plt.subplot2grid((4, num_methods + 1), (1, i), projection='3d')
            self.render_25d_3d_view_improved(ax_25d_3d, voxel_data_25d, bbox, resolution)
            ax_25d_3d.set_title(f'2.5D {method_name}\n(3D View)', fontsize=10)
        
        # 3행: 정확도 분석
        ax_accuracy = plt.subplot2grid((4, num_methods + 1), (2, 0), colspan=num_methods + 1)
        self.render_accuracy_analysis(ax_accuracy, voxels_3d, voxel_data_25d_list, bbox, resolution)
        
        # 4행: 외곽선 비교
        ax_outline = plt.subplot2grid((4, num_methods + 1), (3, 0), colspan=num_methods + 1)
        self.render_outline_comparison(ax_outline, voxels_3d, voxel_data_25d_list, bbox, resolution)
        
        plt.tight_layout()
        
        # [SAVE] 이미지 저장
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_path = self.output_dir / f"orientation_optimized_voxel_conversion_{block_id}_{timestamp}.png"
        
        print(f"[INFO] SAVE 개선된 시각화 결과 저장 중: {save_path}")
        fig.savefig(save_path, dpi=300, bbox_inches='tight', facecolor='white')
        print(f"[SUCCESS] [OK] 개선된 시각화 결과 저장 완료: {save_path}")
        
        # 개별 뷰별 저장
        self._save_individual_views(voxels_3d, voxel_data_25d_list, bbox, resolution, block_id, timestamp)
        
        plt.show()
        return fig
    
    def _save_individual_views(self, voxels_3d, voxel_data_25d_list, bbox, resolution, block_id, timestamp):
        """개별 뷰별 이미지 저장"""
        print(f"[INFO] [SAVE] 개별 뷰 이미지 저장 중...")
        
        # 1. 3D 최적화된 아이소메트릭 뷰
        fig_3d_iso = plt.figure(figsize=(10, 8))
        ax_3d_iso = fig_3d_iso.add_subplot(111, projection='3d')
        self.render_3d_voxels_smooth(ax_3d_iso, voxels_3d, bbox, resolution, view='isometric')
        ax_3d_iso.set_title(f'3D Orientation-Optimized: {block_id} (Isometric View)\nResolution: {resolution}m', fontsize=12, fontweight='bold')
        
        save_path_3d_iso = self.output_dir / f"3d_optimized_iso_{block_id}_{timestamp}.png"
        fig_3d_iso.savefig(save_path_3d_iso, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig_3d_iso)
        
        # 2. 3D 최적화된 탑 뷰
        fig_3d_top = plt.figure(figsize=(10, 8))
        ax_3d_top = fig_3d_top.add_subplot(111, projection='3d')
        self.render_3d_voxels_smooth(ax_3d_top, voxels_3d, bbox, resolution, view='top')
        ax_3d_top.set_title(f'3D Orientation-Optimized: {block_id} (Top View)\nResolution: {resolution}m', fontsize=12, fontweight='bold')
        
        save_path_3d_top = self.output_dir / f"3d_optimized_top_{block_id}_{timestamp}.png"
        fig_3d_top.savefig(save_path_3d_top, dpi=300, bbox_inches='tight', facecolor='white')
        plt.close(fig_3d_top)
        
        # 3. 각 방법별 2.5D 결과
        for result_dict in voxel_data_25d_list:
            method_name = result_dict['method']
            voxel_data_25d = result_dict['voxel_data']
            # 2.5D Top View
            fig_25d_top = plt.figure(figsize=(10, 8))
            ax_25d_top = fig_25d_top.add_subplot(111)
            self.render_25d_top_view_improved(ax_25d_top, voxel_data_25d)
            ax_25d_top.set_title(f'2.5D {method_name}: {block_id} (Top View - Optimized)\nResolution: {resolution}m', fontsize=12, fontweight='bold')
            
            save_path_25d_top = self.output_dir / f"25d_{method_name}_top_optimized_{block_id}_{timestamp}.png"
            fig_25d_top.savefig(save_path_25d_top, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig_25d_top)
            
            # 2.5D 3D View
            fig_25d_3d = plt.figure(figsize=(10, 8))
            ax_25d_3d = fig_25d_3d.add_subplot(111, projection='3d')
            self.render_25d_3d_view_improved(ax_25d_3d, voxel_data_25d, bbox, resolution)
            ax_25d_3d.set_title(f'2.5D {method_name}: {block_id} (3D View - Optimized)\nResolution: {resolution}m', fontsize=12, fontweight='bold')
            
            save_path_25d_3d = self.output_dir / f"25d_{method_name}_3d_optimized_{block_id}_{timestamp}.png"
            fig_25d_3d.savefig(save_path_25d_3d, dpi=300, bbox_inches='tight', facecolor='white')
            plt.close(fig_25d_3d)
        
        print(f"[SUCCESS] [OK] 개별 뷰 저장 완료: {len(voxel_data_25d_list) * 2 + 2}개 파일")
    
    def render_3d_voxels_smooth(self, ax, voxels_3d, bbox, resolution, view='isometric'):
        """부드러운 3D 복셀 렌더링"""
        if voxels_3d is None or np.sum(voxels_3d) == 0:
            ax.text(0.5, 0.5, 0.5, 'No 3D Voxels', ha='center', va='center', 
                   transform=ax.transAxes, fontsize=14)
            return
        
        filled_voxels = np.where(voxels_3d)
        total_filled = len(filled_voxels[0])
        
        # 적절한 샘플링
        if total_filled > 2000:
            sample_indices = np.random.choice(total_filled, 2000, replace=False)
            x_coords = filled_voxels[0][sample_indices]
            y_coords = filled_voxels[1][sample_indices]
            z_coords = filled_voxels[2][sample_indices]
        else:
            x_coords = filled_voxels[0]
            y_coords = filled_voxels[1]
            z_coords = filled_voxels[2]
        
        # 실제 좌표로 변환
        x_real = bbox[0][0] + x_coords * resolution
        y_real = bbox[0][1] + y_coords * resolution
        z_real = bbox[0][2] + z_coords * resolution
        
        # 층별 색상 설정 (더 부드럽게)
        colors = plt.cm.plasma(z_coords / voxels_3d.shape[2])
        
        # 점 크기를 해상도에 따라 조정
        point_size = max(10, min(50, 1000 / max(1, total_filled ** 0.5)))
        
        ax.scatter(x_real, y_real, z_real, s=point_size, alpha=0.8, c=colors, edgecolors='none')
        
        # 뷰 설정
        if view == 'top':
            ax.view_init(elev=90, azim=0)
        elif view == 'side':
            ax.view_init(elev=0, azim=0)
        elif view == 'front':
            ax.view_init(elev=0, azim=90)
        else:  # isometric
            ax.view_init(elev=30, azim=45)
        
        # 축 통일
        self.set_unified_3d_limits(ax, bbox)
    
    def render_25d_top_view_improved(self, ax, voxel_data_25d):
        """개선된 2.5D Top View 렌더링"""
        if not voxel_data_25d:
            ax.text(0.5, 0.5, 'No 2.5D Voxels', ha='center', va='center', 
                   transform=ax.transAxes, fontsize=14)
            return
        
        positions = []
        heights = []
        
        for x, y, height_info in voxel_data_25d:
            positions.append([x, y])
            heights.append(height_info[1])  # filled height
        
        positions = np.array(positions)
        heights = np.array(heights)
        
        if len(heights) > 0:
            # 높이에 따른 색상 및 크기 설정
            norm_heights = heights / np.max(heights) if np.max(heights) > 0 else heights
            colors = plt.cm.plasma(norm_heights)
            sizes = 20 + norm_heights * 80  # 높이에 따라 크기 조정
            
            # 복셀 표시
            scatter = ax.scatter(positions[:, 0], positions[:, 1], s=sizes, c=colors, 
                               alpha=0.8, cmap='plasma', edgecolors='black', linewidth=0.5)
            
            # 격자 표시 (옵션)
            for x, y in positions[:min(100, len(positions))]:  # 너무 많으면 제한
                rect = plt.Rectangle((x-0.4, y-0.4), 0.8, 0.8, 
                                   fill=False, edgecolor='gray', linewidth=0.3, alpha=0.3)
                ax.add_patch(rect)
            
            # 컬러바 추가
            if len(np.unique(heights)) > 1:
                cbar = plt.colorbar(scatter, ax=ax, shrink=0.8)
                cbar.set_label('Height', fontsize=8)
        
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
    
    def render_25d_3d_view_improved(self, ax, voxel_data_25d, bbox, resolution):
        """개선된 2.5D 3D View 렌더링"""
        if not voxel_data_25d:
            ax.text(0.5, 0.5, 0.5, 'No 2.5D Voxels', ha='center', va='center', 
                   transform=ax.transAxes, fontsize=14)
            return
        
        # 복셀 기둥들을 더 부드럽게 렌더링
        for x, y, height_info in voxel_data_25d:
            empty_below, filled, empty_above = height_info
            
            # 실제 좌표로 변환
            x_real = bbox[0][0] + x * resolution
            y_real = bbox[0][1] + y * resolution
            
            # 높이에 따른 색상
            color_intensity = min(1.0, filled / 10.0)
            color = plt.cm.plasma(color_intensity)
            
            # 기둥 형태로 렌더링 (더 효율적)
            z_positions = []
            for z in range(filled):
                z_real = bbox[0][2] + (empty_below + z) * resolution
                z_positions.append(z_real)
            
            if z_positions:
                # 기둥을 연결된 선으로 표시
                x_line = [x_real] * len(z_positions)
                y_line = [y_real] * len(z_positions)
                
                ax.plot(x_line, y_line, z_positions, color=color, alpha=0.8, linewidth=3)
                
                # 상단과 하단에 점 표시
                ax.scatter([x_real], [y_real], [z_positions[0]], s=30, c=[color], alpha=1.0)
                ax.scatter([x_real], [y_real], [z_positions[-1]], s=30, c=[color], alpha=1.0)
        
        ax.view_init(elev=30, azim=45)
        self.set_unified_3d_limits(ax, bbox)
    
    def render_accuracy_analysis(self, ax, voxels_3d, voxel_data_25d_list, bbox, resolution):
        """정확도 분석 렌더링 (자동 방향 최적화 정보 포함)"""
        original_3d_count = np.sum(voxels_3d) if voxels_3d is not None else 0
        
        method_names = []
        voxel_counts = []
        total_voxel_counts = []
        accuracy_scores = []
        
        for result_dict in voxel_data_25d_list:
            method_name = result_dict['method']
            voxel_data_25d = result_dict['voxel_data']
            method_names.append(method_name)
            
            # 2.5D 위치 수
            position_count = len(voxel_data_25d)
            voxel_counts.append(position_count)
            
            # 실제 복셀 수 (높이 합)
            total_voxels = sum(height_info[1] for _, _, height_info in voxel_data_25d)
            total_voxel_counts.append(total_voxels)
            
            # 정확도 점수 계산
            if original_3d_count > 0:
                accuracy = min(100, (total_voxels / original_3d_count) * 100)
            else:
                accuracy = 0
            accuracy_scores.append(accuracy)
        
        # 다중 막대 그래프
        x_pos = np.arange(len(method_names))
        width = 0.25
        
        bars1 = ax.bar(x_pos - width, [original_3d_count] * len(method_names), 
                      width, label='Original 3D', color='skyblue', alpha=0.7)
        bars2 = ax.bar(x_pos, total_voxel_counts, 
                      width, label='Converted 2.5D (Total)', color='orange', alpha=0.7)
        bars3 = ax.bar(x_pos + width, voxel_counts, 
                      width, label='2.5D Positions', color='green', alpha=0.7)
        
        # 정확도 점수 표시
        ax2 = ax.twinx()
        line = ax2.plot(x_pos, accuracy_scores, 'ro-', linewidth=2, markersize=8, 
                       label='Accuracy %', color='red')
        
        # 값 표시
        for i, (bar1, bar2, bar3, acc) in enumerate(zip(bars1, bars2, bars3, accuracy_scores)):
            # 원본 3D
            ax.text(bar1.get_x() + bar1.get_width()/2, bar1.get_height() + original_3d_count*0.02,
                   f'{original_3d_count:,}', ha='center', va='bottom', fontsize=8)
            
            # 2.5D 총 복셀
            ax.text(bar2.get_x() + bar2.get_width()/2, bar2.get_height() + original_3d_count*0.02,
                   f'{total_voxel_counts[i]:,}', ha='center', va='bottom', fontsize=8)
            
            # 2.5D 위치
            ax.text(bar3.get_x() + bar3.get_width()/2, bar3.get_height() + original_3d_count*0.02,
                   f'{voxel_counts[i]:,}', ha='center', va='bottom', fontsize=8)
            
            # 정확도
            ax2.text(x_pos[i], acc + 5, f'{acc:.1f}%', ha='center', va='bottom', 
                    fontsize=10, color='red', fontweight='bold')
        
        ax.set_xlabel('Conversion Method')
        ax.set_ylabel('Voxel Count')
        ax2.set_ylabel('Accuracy (%)', color='red')
        ax.set_title('[AUTO] Orientation-Optimized Block Conversion Accuracy Analysis')
        ax.set_xticks(x_pos)
        ax.set_xticklabels(method_names)
        ax.legend(loc='upper left')
        ax2.legend(loc='upper right')
        ax.grid(True, alpha=0.3)
        
        # 자동 방향 최적화 정보
        best_method_idx = np.argmax(accuracy_scores)
        best_method = method_names[best_method_idx]
        best_accuracy = accuracy_scores[best_method_idx]
        
        # 격자 호환성 계산
        grid_unit = 2.0  # 자항선 격자 단위
        grid_cells = grid_unit / resolution
        
        info_text = [
            f"🏆 Best Method: {best_method} ({best_accuracy:.1f}%)",
            f"📊 Original 3D: {original_3d_count:,} voxels",
            f"[AUTO] Auto-Orientation: Maximum floor contact optimized",
            f"🚢 Fixed Resolution: {resolution:.3f}m", 
            f"[GRID] Ship Grid Compatibility: {grid_unit}m ÷ {resolution:.3f}m = {grid_cells:.0f} cells"
        ]
        
        ax.text(0.02, 0.98, '\n'.join(info_text), transform=ax.transAxes, 
               fontsize=10, va='top', ha='left',
               bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen"))
    
    def render_outline_comparison(self, ax, voxels_3d, voxel_data_25d_list, bbox, resolution):
        """외곽선 비교 렌더링"""
        # 3D 원본의 footprint 계산
        if voxels_3d is not None:
            original_footprint = np.any(voxels_3d, axis=2)
            orig_positions = np.where(original_footprint)
            
            if len(orig_positions[0]) > 0:
                ax.scatter(orig_positions[0], orig_positions[1], s=20, alpha=0.5, 
                          c='lightblue', label='Optimized 3D Footprint', marker='s')
        
        # 각 방법별 2.5D footprint 표시
        colors = ['red', 'green', 'blue', 'purple', 'orange']
        markers = ['o', '^', 's', 'D', 'v']
        
        for i, result_dict in enumerate(voxel_data_25d_list):
            method_name = result_dict['method']
            voxel_data_25d = result_dict['voxel_data']
            if voxel_data_25d:
                positions = np.array([(x, y) for x, y, _ in voxel_data_25d])
                
                if len(positions) > 0:
                    color = colors[i % len(colors)]
                    marker = markers[i % len(markers)]
                    
                    ax.scatter(positions[:, 0], positions[:, 1], s=40, alpha=0.8,
                              c=color, label=f'2.5D {method_name}', marker=marker, edgecolors='black')
        
        ax.set_aspect('equal')
        ax.grid(True, alpha=0.3)
        ax.legend()
        ax.set_xlabel('X')
        ax.set_ylabel('Y')
        ax.set_title('[AUTO] Orientation-Optimized Block Footprint Comparison (Top View)')
        
        # 선박 블록 통계 정보
        if voxels_3d is not None:
            original_area = np.sum(original_footprint)
            
            coverage_info = [f"Optimized area: {original_area} cells"]
            for result_dict in voxel_data_25d_list:
                method_name = result_dict['method']
                voxel_data_25d = result_dict['voxel_data']
                area_25d = len(voxel_data_25d)
                coverage_ratio = (area_25d / original_area * 100) if original_area > 0 else 0
                coverage_info.append(f"{method_name}: {area_25d} cells ({coverage_ratio:.1f}%)")
            
            # 해상도 정보 추가
            coverage_info.append(f"Fixed resolution: {resolution}m")
            coverage_info.append(f"Auto-orientation: [OK]")
            
            ax.text(0.02, 0.98, '\n'.join(coverage_info), transform=ax.transAxes,
                   fontsize=9, va='top', ha='left',
                   bbox=dict(boxstyle="round,pad=0.3", facecolor="lightgreen"))
    
    def set_unified_3d_limits(self, ax, bbox):
        """3D 축 통일"""
        x_size = bbox[1][0] - bbox[0][0]
        y_size = bbox[1][1] - bbox[0][1]
        z_size = bbox[1][2] - bbox[0][2]
        
        max_size = max(x_size, y_size, z_size)
        
        x_center = (bbox[0][0] + bbox[1][0]) / 2
        y_center = (bbox[0][1] + bbox[1][1]) / 2
        z_center = (bbox[0][2] + bbox[1][2]) / 2
        
        half_max = max_size / 2
        
        ax.set_xlim(x_center - half_max, x_center + half_max)
        ax.set_ylim(y_center - half_max, y_center + half_max)
        ax.set_zlim(z_center - half_max, z_center + half_max)
        ax.set_box_aspect([1, 1, 1])
        
        ax.set_xlabel('X (m)')
        ax.set_ylabel('Y (m)')
        ax.set_zlabel('Z (m)')

def convert_mesh_to_25d_optimized(file_path, custom_resolution=None, 
                                 methods=['footprint', 'height_map', 'outline'],
                                 output_dir="voxel_results_improved",
                                 enable_orientation_optimization=True):
    """
    자동 방향 최적화 기능이 추가된 메시 → 3D → 2.5D 복셀 변환 (이미지 저장 포함)
    
    Args:
        file_path (str): 메시 파일 경로
        custom_resolution (float): 사용자 지정 해상도 (None이면 최적화된 고정값 사용)
        methods (list): 사용할 변환 방법들
        output_dir (str): 결과 이미지 저장 디렉토리
        enable_orientation_optimization (bool): 자동 방향 최적화 활성화
    
    Returns:
        list: [(method_name, voxel_data_25d), ...] 형태의 결과
    """
    print(f"[INFO] Starting ORIENTATION-OPTIMIZED 3D → 2.5D conversion: {Path(file_path).name}")
    
    # 해상도 결정
    if custom_resolution:
        resolution = custom_resolution
        print(f"[CONFIG] 사용자 지정 해상도: {resolution}m")
    else:
        resolution = SHIP_BLOCK_OPTIMAL_RESOLUTION
        print(f"🚢 선박 블록 최적화 해상도: {resolution}m")
        print(f"   (자항선 격자 호환: {GRID_UNIT}m ÷ {resolution}m = {RESOLUTION_FACTOR:.0f}개 셀)")
    
    try:
        # 1. 자동 방향 최적화된 3D 복셀화
        voxelizer = OptimizedVoxelizer(fixed_resolution=resolution, 
                                     enable_orientation_optimization=enable_orientation_optimization)
        mesh = voxelizer.process_mesh_file(file_path)
        
        final_resolution = voxelizer.get_resolution(mesh)
        voxels_3d, bbox, final_resolution, selected_orientation = voxelizer.voxelize_improved(mesh, final_resolution)
        
        if np.sum(voxels_3d) == 0:
            print("[WARNING] No 3D voxels generated!")
            return None
        
        print(f"[OK] Orientation-optimized 3D voxelization successful: {np.sum(voxels_3d):,} voxels")
        
        # 2. 3D → 2.5D 변환
        converter = VoxelConverter25D()
        voxel_data_25d_list = []
        
        for method in methods:
            print(f"\n[INFO] Converting using '{method}' method...")
            voxel_data_25d = converter.convert_3d_to_25d(voxels_3d, bbox, final_resolution, method)
            
            if voxel_data_25d:
                # VoxelBlock 객체 생성
                block_id = f"{Path(file_path).stem}_{method}_orientation_optimized"
                voxel_block = converter.create_voxel_block(voxel_data_25d, block_id)
                
                if voxel_block:
                    # VoxelBlock 객체와 함께 저장
                    voxel_data_25d_list.append({
                        'method': method,
                        'voxel_block': voxel_block,
                        'voxel_data': voxel_data_25d
                    })
                    print(f"  - VoxelBlock created: {voxel_block}")
                else:
                    print(f"  - VoxelBlock creation failed for '{method}' method")
            else:
                print(f"  - No 2.5D voxels generated for '{method}' method")
        
        if not voxel_data_25d_list:
            print("[WARNING] No 2.5D conversions succeeded!")
            return None
        
        # 3. 결과 분석
        print(f"\n[AUTO] === ORIENTATION-OPTIMIZED Results Analysis ===")
        original_count = np.sum(voxels_3d)
        
        for result_dict in voxel_data_25d_list:
            method_name = result_dict['method']
            voxel_data_25d = result_dict['voxel_data']
            position_count = len(voxel_data_25d)
            total_voxels = sum(height_info[1] for _, _, height_info in voxel_data_25d)
            accuracy = (total_voxels / original_count * 100) if original_count > 0 else 0
            reduction = (1 - total_voxels / original_count) * 100 if original_count > 0 else 0
            
            print(f"[RESULT] {method_name.upper()}:")
            print(f"  [STAT] Positions: {position_count:,}")
            print(f"  [VOXEL] Total voxels: {total_voxels:,}")
            print(f"  [TARGET] Accuracy: {accuracy:.1f}%")
            print(f"  [REDUCE] Data reduction: {reduction:.1f}%")
            print(f"  [AUTO] Orientation optimized: {'ENABLED' if enable_orientation_optimization else 'DISABLED'}")
            
            if method_name == 'footprint':
                print(f"  [RECOMMEND] 추천: 선박 블록 배치에 최적 (외곽 정확, 배치 호환성, 방향 최적화)")
            elif method_name == 'height_map':
                print(f"  [RECOMMEND] 추천: 높이가 중요한 구조 (방향 최적화)")
            elif method_name == 'outline':
                print(f"  [GRID] 추천: 경계선만 필요한 경우 (방향 최적화)")
        
        # 4. 배치 호환성 정보
        print(f"\n[CONFIG] === 배치 시스템 호환성 (개선된 버전) ===")
        print(f"  - 고정 해상도: {resolution}m")
        print(f"  - 자항선 격자 단위: {GRID_UNIT}m")
        print(f"  - 격자 호환성: {GRID_UNIT}m ÷ {resolution}m = {RESOLUTION_FACTOR:.0f}개 셀")
        print(f"  - [AUTO] 자동 방향 최적화: {'ON (바닥 접촉면 최대화)' if enable_orientation_optimization else 'OFF'}")
        print(f"  - 모든 블록 동일 해상도: [OK] 배치 정확성 보장")
        
        # 5. 시각화 및 이미지 저장 (output_dir이 None이 아닐 때만)
        if output_dir is not None:
            print(f"\n[INFO] Creating orientation-optimized comparison visualization with image saving...")
            visualizer = ImprovedVisualizer(output_dir=output_dir)
            visualizer.visualize_improved_comparison(
                voxels_3d, voxel_data_25d_list, bbox, final_resolution, Path(file_path).stem
            )
        else:
            print(f"\n[INFO] Skipping visualization (output_dir=None)")
        
        return voxel_data_25d_list, selected_orientation
        
    except Exception as e:
        print(f"[ERROR] Orientation-optimized conversion failed: {e}")
        import traceback
        traceback.print_exc()
        return None

def main():
    if len(sys.argv) < 2:
        print("[AUTO]" + "="*70)
        print("ORIENTATION-OPTIMIZED 3D → 2.5D Voxel Conversion Tool")
        print("WITH AUTOMATIC ORIENTATION OPTIMIZATION & IMAGE SAVING")
        print("[AUTO]" + "="*70)
        print("")
        print("[TARGET] 바닥 접촉면을 최대화하는 자동 방향 최적화 기능!")
        print(f"   기본 해상도: {SHIP_BLOCK_OPTIMAL_RESOLUTION}m (자항선 격자 호환)")
        print("")
        print("사용법:")
        print("  python Voxelizer_Improve.py <file.obj|fbx>                    # 최적화된 해상도 + 자동 방향 최적화")
        print("  python Voxelizer_Improve.py <file.obj> <custom_resolution>    # 사용자 지정 해상도 + 자동 방향 최적화")
        print("  python Voxelizer_Improve.py <file.obj> <resolution> <output_dir>  # 저장 디렉토리 지정")
        print("")
        print("예시:")
        print("  python Voxelizer_Improve.py 4386_183_000.obj                 # 0.5m 해상도 + 자동 최적화")
        print("  python Voxelizer_Improve.py 4386_183_000.obj 0.25            # 0.25m 해상도 + 자동 최적화")
        print("  python Voxelizer_Improve.py 4386_183_000.obj 1.0 results     # 1.0m 해상도 + 결과 폴더 지정")
        print("")
        print("[AUTO] 자동 방향 최적화 특징:")
        print("  [AUTO] 3가지 방향 (XY, XZ, YZ 평면) 중 바닥 면적 최대인 방향 자동 선택")
        print("  [AUTO] 얇고 긴 판형 블록이 서있으면 자동으로 눕혀서 최적화")  
        print("  [STABLE] 바닥 접촉면 최대화로 배치 안정성 향상")
        print("  [ACCURATE] 모든 블록에 동일한 해상도 적용으로 배치 정확성 보장")
        print("")
        print("[SAVE] 자동 이미지 저장 기능:")
        print("  [IMG] 방향 최적화 전후 비교 시각화 (24x16 고해상도)")
        print("  [IMG] 3D 최적화된 뷰 (아이소메트릭, 탑뷰)")
        print("  [IMG] 각 방법별 2.5D 결과 (탑뷰, 3D뷰)")
        print("  [DIR] 'voxel_results_improved' 폴더에 타임스탬프 포함 파일명으로 저장")
        print("")
        print("[TIP] 권장 해상도:")
        print("  - 0.25m: 고정밀 (0.5m ÷ 2개 셀)")
        print("  - 0.5m: 최적화 (0.5m ÷ 1개 셀) [DEFAULT] 기본값")
        print("  - 1.0m: 고속 (0.5m × 2배 크기)")
        print("  - 2.0m: 초고속 (0.5m × 4배 크기)")
        return
    
    file_path = sys.argv[1]
    custom_resolution = float(sys.argv[2]) if len(sys.argv) > 2 else None
    output_dir = sys.argv[3] if len(sys.argv) > 3 else "voxel_results_improved"
    
    if not os.path.exists(file_path):
        print(f"[ERROR] File not found: {file_path}")
        return
    
    try:
        print("[AUTO]" + "="*70)
        print("ORIENTATION-OPTIMIZED 3D → 2.5D Voxel Conversion Tool")
        print("WITH AUTOMATIC ORIENTATION OPTIMIZATION & IMAGE SAVING")
        print("[AUTO]" + "="*70)
        print("[TARGET] 바닥 접촉면 최대화 자동 방향 최적화 + 이미지 저장 버전!")
        print(f"[DIR] 결과 저장 디렉토리: {output_dir}")
        print("")
        
        result = convert_mesh_to_25d_optimized(file_path, custom_resolution, output_dir=output_dir)
        
        if result:
            print(f"\n[DONE] === 방향 최적화 변환 + 이미지 저장 완료! ===")
            print(f"[AUTO] 자동 방향 최적화로 바닥 접촉면 최대화!")
            print(f"[OK] 모든 블록 동일 해상도 적용으로 배치 정확성 보장!")
            print(f"🚢 자항선 격자 시스템과 완벽 호환!")
            print(f"📊 {len(result)}가지 방법으로 변환 완료")
            print(f"[SAVE] 시각화 결과 이미지 자동 저장 완료!")
            
            # 해상도 정보 표시
            used_resolution = custom_resolution if custom_resolution else SHIP_BLOCK_OPTIMAL_RESOLUTION
            grid_cells = GRID_UNIT / used_resolution
            print(f"[CONFIG] 사용된 해상도: {used_resolution}m")
            print(f"[GRID] 격자 호환성: {GRID_UNIT}m ÷ {used_resolution}m = {grid_cells:.0f}개 셀")
            
            print(f"\n[DIR] === 저장된 파일 목록 ===")
            output_path = Path(output_dir)
            if output_path.exists():
                saved_files = list(output_path.glob("*.png"))
                for i, file_path in enumerate(sorted(saved_files)[-10:], 1):  # 최근 10개 파일만 표시
                    print(f"  {i}. {file_path.name}")
                if len(saved_files) > 10:
                    print(f"  ... 총 {len(saved_files)}개 파일")
            
            print(f"\n[TIP] 이제 모든 블록을 바닥 접촉면 최대화 방향으로 최적화하여")
            print(f"   배치 알고리즘에서 더욱 안정적인 배치가 가능합니다!")
            print(f"🖼️ 방향 최적화 시각화 결과를 '{output_dir}' 폴더에서 확인하세요!")
        else:
            print(f"\n[TIP] 변환 실패 시 시도할 옵션:")
            print(f"  - 다른 해상도: python {sys.argv[0]} {file_path} 0.1")
            print(f"  - 더 큰 해상도: python {sys.argv[0]} {file_path} 0.5")
            print(f"  - 다른 저장 위치: python {sys.argv[0]} {file_path} 0.2 my_results")
        
        input("\n아무 키나 눌러서 종료...")
        
    except KeyboardInterrupt:
        print(f"\n[WARNING] 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n[ERROR] 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()