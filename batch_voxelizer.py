#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
일괄 복셀화 및 JSON 저장 스크립트
- 모든 OBJ 파일을 복셀화하여 JSON으로 저장
- config_generator에서 즉시 사용 가능
"""

import json
import os
import sys
from pathlib import Path
import time
from datetime import datetime
import traceback

# 프로젝트 모듈 import
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from Voxelizer import convert_mesh_to_25d_optimized
    from models.voxel_block import VoxelBlock
    print(f"[INFO] Required modules loaded successfully")
except ImportError as e:
    print(f"[ERROR] Cannot find required modules: {e}")
    sys.exit(1)

class BatchVoxelizer:
    """일괄 복셀화 처리기"""
    
    def __init__(self, input_dir="fbx_blocks/converted_obj", output_dir="voxel_cache"):
        """
        Args:
            input_dir (str): OBJ 파일들이 있는 디렉토리
            output_dir (str): 복셀화 결과 JSON 저장 디렉토리
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        
        # 통계
        self.total_files = 0
        self.processed = 0
        self.skipped = 0
        self.failed = 0
        
    def voxelize_single_block(self, obj_path, force_rebuild=False):
        """단일 블록 복셀화 및 저장"""
        block_name = obj_path.stem
        output_file = self.output_dir / f"{block_name}.json"
        
        # 이미 있고 rebuild가 아니면 스킵
        if output_file.exists() and not force_rebuild:
            print(f"  [SKIP] Already exists: {block_name}")
            self.skipped += 1
            return True
        
        print(f"  [WORK] Processing: {block_name}")
        start_time = time.time()
        
        try:
            # 복셀화 수행 (시각화 비활성화로 속도 향상)
            result, selected_orientation = convert_mesh_to_25d_optimized(
                file_path=str(obj_path),
                custom_resolution=0.5,  # 0.5m 해상도로 변경!
                methods=['footprint'],
                output_dir=None,  # 시각화 비활성화!
                enable_orientation_optimization=True
            )
            
            if not result or len(result) == 0:
                print(f"    [ERROR] No voxelization result")
                self.failed += 1
                return False
            
            # footprint 결과 사용 (딕셔너리 형태로 반환됨)
            result_dict = result[0]
            method_name = result_dict['method']
            voxel_data_25d = result_dict['voxel_data']
            
            if not voxel_data_25d:
                print(f"    [ERROR] Empty voxel data")
                self.failed += 1
                return False
            
            # VoxelBlock 생성하여 메타데이터 추출
            voxel_block = VoxelBlock(block_name, voxel_data_25d)
            
            # 긴쪽이 Y가 되도록 자동 조정 (배치 성능 향상)
            if voxel_block.width > voxel_block.height:
                old_width, old_height = voxel_block.width, voxel_block.height
                print(f"    [AUTO] Rotating block {block_name}: {old_width}x{old_height}", end="")
                voxel_block.rotate(90)
                print(f" -> {voxel_block.width}x{voxel_block.height}")
                # 회전된 복셀 데이터로 업데이트
                voxel_data_25d = voxel_block.voxel_data
            
            # 블록 타입 추정
            block_type = self.determine_block_type(block_name)
            
            # 저장할 데이터 구성
            voxel_cache_data = {
                "block_id": block_name,
                "block_type": block_type,
                "source_file": str(obj_path),
                "voxel_data": {
                    "method": method_name,
                    "resolution": 0.5,  # 0.5m 해상도로 변경!
                    "orientation_optimized": True,
                    "selected_orientation": selected_orientation,
                    "dimensions": {
                        "width": int(voxel_block.width),
                        "height": int(voxel_block.height),
                        "min_x": int(voxel_block.min_x),
                        "min_y": int(voxel_block.min_y),
                        "max_x": int(voxel_block.max_x),
                        "max_y": int(voxel_block.max_y)
                    },
                    "total_volume": int(voxel_block.get_total_volume()),
                    "footprint_area": int(voxel_block.get_area()),
                    "footprint_positions": [
                        {
                            "x": int(x),
                            "y": int(y),
                            "height_info": [int(h) for h in height_info]
                        }
                        for x, y, height_info in voxel_data_25d
                    ]
                },
                "metadata": {
                    "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "processing_time": time.time() - start_time,
                    "total_voxels": len(voxel_data_25d)
                }
            }
            
            # JSON으로 저장
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(voxel_cache_data, f, indent=2, ensure_ascii=False)
            
            processing_time = time.time() - start_time
            print(f"    [OK] Saved: {voxel_block.width}x{voxel_block.height}, {len(voxel_data_25d)} voxels ({processing_time:.2f}s)")
            self.processed += 1
            return True
            
        except Exception as e:
            print(f"    [ERROR] Failed: {e}")
            print(f"    [DEBUG] {traceback.format_exc()}")
            self.failed += 1
            return False
    
    def determine_block_type(self, block_name):
        """블록 이름으로 타입 추정"""
        block_name_lower = block_name.lower()
        
        if any(keyword in block_name_lower for keyword in ['crane', '20a', '20b', '20c', '20d', '20e', '20f', '20g', '20h', '20j', '20k', '20l', '20n', '20p', '20y']):
            return 'crane'
        elif any(keyword in block_name_lower for keyword in ['trestle', '_000']):
            return 'trestle'
        else:
            return 'unknown'
    
    def process_all(self, force_rebuild=False, max_files=None):
        """모든 OBJ 파일 처리"""
        if not self.input_dir.exists():
            print(f"[ERROR] Input directory not found: {self.input_dir}")
            return
        
        # OBJ 파일들 찾기
        obj_files = list(self.input_dir.glob("*.obj"))
        if max_files:
            obj_files = obj_files[:max_files]
        
        self.total_files = len(obj_files)
        
        print(f"[INFO] Batch voxelization started")
        print(f"       Input dir: {self.input_dir}")
        print(f"       Output dir: {self.output_dir}")
        print(f"       Total files: {self.total_files}")
        print(f"       Force rebuild: {force_rebuild}")
        print("="*80)
        
        start_time = time.time()
        
        for i, obj_file in enumerate(obj_files, 1):
            print(f"[{i:3d}/{self.total_files:3d}] {obj_file.name}")
            self.voxelize_single_block(obj_file, force_rebuild)
        
        # 결과 요약
        total_time = time.time() - start_time
        print("="*80)
        print(f"[SUCCESS] Batch processing completed!")
        print(f"  Total files: {self.total_files}")
        print(f"  Processed: {self.processed}")
        print(f"  Skipped: {self.skipped}")
        print(f"  Failed: {self.failed}")
        print(f"  Total time: {total_time:.1f}s")
        print(f"  Average time: {total_time/max(1, self.processed):.1f}s per file")
        print(f"  Cache directory: {self.output_dir}")

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="일괄 복셀화 처리기")
    parser.add_argument("--input-dir", default="fbx_blocks/converted_obj", 
                       help="OBJ 파일들이 있는 디렉토리 (기본값: fbx_blocks/converted_obj)")
    parser.add_argument("--output-dir", default="voxel_cache",
                       help="복셀화 결과 저장 디렉토리 (기본값: voxel_cache)")
    parser.add_argument("--force-rebuild", action="store_true",
                       help="기존 캐시를 무시하고 다시 처리")
    parser.add_argument("--max-files", type=int,
                       help="처리할 최대 파일 수 (테스트용)")
    
    args = parser.parse_args()
    
    print("VOXEL" + "="*70)
    print("Batch Voxelizer - Pre-compute Voxel Data Cache")
    print("VOXEL" + "="*70)
    
    try:
        voxelizer = BatchVoxelizer(args.input_dir, args.output_dir)
        voxelizer.process_all(args.force_rebuild, args.max_files)
        
    except KeyboardInterrupt:
        print(f"\n[WARNING] 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n[ERROR] 예상치 못한 오류: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()