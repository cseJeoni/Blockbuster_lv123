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
    import multiprocessing as mp
    from multiprocessing import Pool
    print(f"[INFO] Traditional voxelizer and multiprocessing loaded successfully")
except ImportError as e:
    print(f"[ERROR] Cannot find required modules: {e}")
    sys.exit(1)

# multiprocessing용 전역 함수
def process_single_block_global(block_info):
    """multiprocessing.Pool용 전역 함수"""
    import os
    import sys
    from pathlib import Path
    
    # 필요한 모듈 재import (각 워커 프로세스에서)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, current_dir)
    
    try:
        from Voxelizer import convert_mesh_to_25d_optimized
    except ImportError as e:
        return {"status": "failed", "block_name": "unknown", "error": f"Import error: {e}"}
    
    obj_path, force_rebuild, output_dir, resolution = block_info
    block_name = Path(obj_path).stem
    output_file = Path(output_dir) / f"{block_name}.json"
    
    # 이미 있고 rebuild가 아니면 스킵
    if output_file.exists() and not force_rebuild:
        return {"status": "skipped", "block_name": block_name, "message": "Already exists"}
    
    start_time = time.time()
    
    try:
        # 기존 Trimesh 복셀화 수행 (정확도 우선)
        result, orientation = convert_mesh_to_25d_optimized(
            file_path=str(obj_path),
            custom_resolution=resolution,
            methods=['footprint'],  # footprint 방식 사용
            output_dir=None,  # 시각화 생략 (속도 향상)
            enable_orientation_optimization=True
        )
        
        if not result or len(result) == 0:
            return {"status": "failed", "block_name": block_name, "error": "Voxelization failed"}
        
        # 첫 번째 결과 사용 (footprint)
        voxel_result = result[0]
        voxel_data = voxel_result['voxel_data']
        
        # numpy 타입을 Python 기본 타입으로 변환
        def convert_numpy_types(obj):
            if isinstance(obj, list):
                return [convert_numpy_types(item) for item in obj]
            elif isinstance(obj, tuple):
                return tuple(convert_numpy_types(item) for item in obj)
            elif hasattr(obj, 'item'):  # numpy scalar
                return obj.item()
            elif hasattr(obj, 'tolist'):  # numpy array
                return obj.tolist()
            else:
                return obj
        
        # 블록 타입 판별 함수 (선박 블록 명명 규칙 기반)
        def determine_block_type(block_name):
            """블록 이름으로 타입 추정 - _ 뒤의 숫자 단위로 판별"""
            import re
            
            # _ 뒤의 패턴 추출
            parts = block_name.split('_')
            if len(parts) < 2:
                return 'unknown'
            
            suffix = parts[-1]  # _ 뒤의 마지막 부분
            
            # 10단위 패턴 (크레인): 숫자 2-3자리 + 알파벳 1자리 (예: 20A, 40B, 66B)
            if re.match(r'^\d{2,3}[A-Z]$', suffix.upper()):
                return 'crane'
            
            # 100단위 패턴 (트레슬): 숫자 3자리 + _000 (예: 123_000, 456_000)
            if suffix == '000' and len(parts) >= 3:
                # 앞부분이 3자리 숫자인지 확인
                if re.match(r'^\d{3}$', parts[-2]):
                    return 'trestle'
            
            # 기타 명시적 키워드 검사
            block_name_lower = block_name.lower()
            if 'crane' in block_name_lower:
                return 'crane'
            elif 'trestle' in block_name_lower:
                return 'trestle'
            
            return 'unknown'
        
        # 블록 타입 자동 추정
        detected_block_type = determine_block_type(block_name)
        
        # 디버그: orientation 값 확인
        print(f"    [DEBUG] Orientation value: '{orientation}' (type: {type(orientation)})")
        
        # 저장할 데이터 구성 (개선된 형식)
        voxel_cache_data = {
            "block_id": block_name,
            "block_type": detected_block_type,
            "source_file": str(obj_path),
            "voxel_data": {
                "method": "footprint_trimesh",
                "resolution": resolution,
                "orientation_optimized": True,
                "selected_orientation": orientation,
                "optimization_method": "area_maximization_with_flatness",
                "total_volume": len(voxel_data) * 10,  # 추정값
                "footprint_area": len(voxel_data),
                "voxel_positions": convert_numpy_types(voxel_data)  # numpy 타입 변환
            },
            "metadata": {
                "created_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                "processing_time": time.time() - start_time,
                "voxelizer_version": "trimesh_v3.0"
            }
        }
        
        # JSON으로 저장
        import json
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(voxel_cache_data, f, indent=2, ensure_ascii=False)
        
        processing_time = time.time() - start_time
        return {
            "status": "success", 
            "block_name": block_name, 
            "voxel_count": len(voxel_data),
            "processing_time": processing_time
        }
        
    except Exception as e:
        return {"status": "failed", "block_name": block_name, "error": str(e)}

class BatchVoxelizer:
    """Trimesh 기반 일괄 복셀화 처리기 (병렬처리 지원)"""
    
    def __init__(self, input_dir="fbx_blocks/converted_obj", output_dir="voxel_cache", resolution=0.5, enable_parallel=True, num_workers=4):
        """
        Args:
            input_dir (str): OBJ 파일들이 있는 디렉토리
            output_dir (str): 복셀화 결과 JSON 저장 디렉토리
            resolution (float): 복셀화 해상도 (기본값: 0.5m)
            enable_parallel (bool): 병렬처리 사용 여부
            num_workers (int): 병렬처리 워커 수
        """
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.resolution = resolution
        self.enable_parallel = enable_parallel
        self.num_workers = num_workers
        
        # 통계
        self.total_files = 0
        self.processed = 0
        self.skipped = 0
        self.failed = 0
        
    def voxelize_single_block(self, obj_path, force_rebuild=False):
        """단일 블록 복셀화 및 저장 (기존 Trimesh 방식)"""
        block_name = obj_path.stem
        output_file = self.output_dir / f"{block_name}.json"
        
        # 이미 있고 rebuild가 아니면 스킵
        if output_file.exists() and not force_rebuild:
            return {"status": "skipped", "block_name": block_name, "message": "Already exists"}
        
        start_time = time.time()
        
        try:
            # 기존 Trimesh 복셀화 수행 (정확도 우선)
            result, orientation = convert_mesh_to_25d_optimized(
                file_path=str(obj_path),
                custom_resolution=self.resolution,
                methods=['footprint'],  # footprint 방식 사용
                output_dir=None,  # 시각화 생략 (속도 향상)
                enable_orientation_optimization=True
            )
            
            if not result or len(result) == 0:
                return {"status": "failed", "block_name": block_name, "error": "Voxelization failed"}
            
            # 첫 번째 결과 사용 (footprint)
            voxel_result = result[0]
            voxel_data = voxel_result['voxel_data']
            
            # 블록 타입 추정
            block_type = self.determine_block_type(block_name)
            
            # numpy 타입을 Python 기본 타입으로 변환
            def convert_numpy_types(obj):
                if isinstance(obj, list):
                    return [convert_numpy_types(item) for item in obj]
                elif isinstance(obj, tuple):
                    return tuple(convert_numpy_types(item) for item in obj)
                elif hasattr(obj, 'item'):  # numpy scalar
                    return obj.item()
                elif hasattr(obj, 'tolist'):  # numpy array
                    return obj.tolist()
                else:
                    return obj
            
            # 저장할 데이터 구성 (기존 형식 호환)
            voxel_cache_data = {
                "block_id": block_name,
                "block_type": block_type,
                "source_file": str(obj_path),
                "voxel_data": {
                    "method": "footprint_trimesh",
                    "resolution": self.resolution,
                    "orientation_optimized": True,
                    "selected_orientation": orientation,
                    "optimization_method": "area_maximization_with_flatness",
                    "total_volume": len(voxel_data) * 10,  # 추정값
                    "footprint_area": len(voxel_data),
                    "voxel_positions": convert_numpy_types(voxel_data)  # numpy 타입 변환
                },
                "metadata": {
                    "created_date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "processing_time": time.time() - start_time,
                    "voxelizer_version": "trimesh_v3.0"
                }
            }
            
            # JSON으로 저장
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(voxel_cache_data, f, indent=2, ensure_ascii=False)
            
            processing_time = time.time() - start_time
            return {
                "status": "success", 
                "block_name": block_name, 
                "voxel_count": len(voxel_data),
                "processing_time": processing_time
            }
            
        except Exception as e:
            return {"status": "failed", "block_name": block_name, "error": str(e)}
    
    def determine_block_type(self, block_name):
        """블록 이름으로 타입 추정 - _ 뒤의 숫자 단위로 판별"""
        import re
        
        # _ 뒤의 패턴 추출
        parts = block_name.split('_')
        if len(parts) < 2:
            return 'unknown'
        
        suffix = parts[-1]  # _ 뒤의 마지막 부분
        
        # 10단위 패턴 (크레인): 숫자 2-3자리 + 알파벳 1자리 (예: 20A, 40B, 66B)
        if re.match(r'^\d{2,3}[A-Z]$', suffix.upper()):
            return 'crane'
        
        # 100단위 패턴 (트레슬): 숫자 3자리 + _000 (예: 123_000, 456_000)
        if suffix == '000' and len(parts) >= 3:
            # 앞부분이 3자리 숫자인지 확인
            if re.match(r'^\d{3}$', parts[-2]):
                return 'trestle'
        
        # 기타 명시적 키워드 검사
        block_name_lower = block_name.lower()
        if 'crane' in block_name_lower:
            return 'crane'
        elif 'trestle' in block_name_lower:
            return 'trestle'
        
        return 'unknown'
    
    def process_block_parallel(self, block_info):
        """병렬처리용 단일 블록 처리 함수 (multiprocessing용)"""
        obj_path, force_rebuild, output_dir, resolution = block_info
        
        # 자식 프로세스에서 경로 재설정
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.resolution = resolution
        
        import os
        worker_id = os.getpid()
        block_name = Path(obj_path).stem
        
        print(f"    [Worker {worker_id}] Processing {block_name}...")
        result = self.voxelize_single_block(Path(obj_path), force_rebuild)
        
        if result["status"] == "success":
            print(f"    [Worker {worker_id}] ✓ {block_name}: {result['voxel_count']} voxels ({result['processing_time']:.2f}s)")
        elif result["status"] == "skipped":
            print(f"    [Worker {worker_id}] - {block_name}: {result['message']}")
        else:
            print(f"    [Worker {worker_id}] ✗ {block_name}: {result.get('error', 'Unknown error')}")
        
        return result
    
    def process_batch_parallel(self, obj_files, force_rebuild=False, batch_size=50):
        """배치 단위 병렬처리"""
        all_results = []
        num_batches = (len(obj_files) + batch_size - 1) // batch_size
        
        for batch_idx in range(0, len(obj_files), batch_size):
            batch_files = obj_files[batch_idx:batch_idx + batch_size]
            batch_num = batch_idx // batch_size + 1
            
            print(f"\n[BATCH {batch_num}/{num_batches}] Processing {len(batch_files)} blocks with {self.num_workers} workers...")
            
            # 병렬처리용 데이터 준비
            block_info_list = [
                (str(obj_file), force_rebuild, str(self.output_dir), self.resolution) 
                for obj_file in batch_files
            ]
            
            # 병렬처리 실행
            batch_start = time.time()
            with Pool(processes=self.num_workers) as pool:
                batch_results = pool.map(process_single_block_global, block_info_list)
            
            batch_time = time.time() - batch_start
            
            # 배치 결과 집계
            batch_success = sum(1 for r in batch_results if r["status"] == "success")
            batch_skipped = sum(1 for r in batch_results if r["status"] == "skipped")
            batch_failed = sum(1 for r in batch_results if r["status"] == "failed")
            
            print(f"[BATCH {batch_num}] Completed in {batch_time:.1f}s - Success: {batch_success}, Skipped: {batch_skipped}, Failed: {batch_failed}")
            print(f"[BATCH {batch_num}] Speed: {batch_time/len(batch_files):.1f}s per block (avg)")
            
            all_results.extend(batch_results)
            
            # 전체 진행상황
            total_processed = len(all_results)
            print(f"[TOTAL PROGRESS] {total_processed}/{len(obj_files)} blocks completed")
        
        return all_results
    
    def process_all(self, force_rebuild=False, max_files=None):
        """모든 OBJ 파일 처리 (병렬/순차 선택 가능)"""
        if not self.input_dir.exists():
            print(f"[ERROR] Input directory not found: {self.input_dir}")
            return
        
        # OBJ 파일들 찾기
        obj_files = list(self.input_dir.glob("*.obj"))
        if max_files:
            obj_files = obj_files[:max_files]
        
        self.total_files = len(obj_files)
        
        print(f"[INFO] Batch voxelization started (Trimesh-based)")
        print(f"       Input dir: {self.input_dir}")
        print(f"       Output dir: {self.output_dir}")
        print(f"       Total files: {self.total_files}")
        print(f"       Resolution: {self.resolution}m")
        print(f"       Force rebuild: {force_rebuild}")
        print(f"       Parallel processing: {'ON' if self.enable_parallel else 'OFF'}")
        if self.enable_parallel:
            print(f"       Workers: {self.num_workers}")
        print("="*80)
        
        start_time = time.time()
        
        if self.enable_parallel and len(obj_files) > 1:
            # 병렬처리 모드
            print(f"[MODE] Parallel processing with {self.num_workers} workers")
            results = self.process_batch_parallel(obj_files, force_rebuild)
            
            # 결과 집계
            success_count = sum(1 for r in results if r["status"] == "success")
            skipped_count = sum(1 for r in results if r["status"] == "skipped")
            failed_count = sum(1 for r in results if r["status"] == "failed")
            
            self.processed = success_count
            self.skipped = skipped_count
            self.failed = failed_count
            
        else:
            # 순차처리 모드
            print(f"[MODE] Sequential processing")
            for i, obj_file in enumerate(obj_files, 1):
                print(f"[{i:3d}/{self.total_files:3d}] {obj_file.name}")
                result = self.voxelize_single_block(obj_file, force_rebuild)
                
                if result["status"] == "success":
                    print(f"    [OK] {result['voxel_count']} voxels ({result['processing_time']:.2f}s)")
                    self.processed += 1
                elif result["status"] == "skipped":
                    print(f"    [SKIP] {result['message']}")
                    self.skipped += 1
                else:
                    print(f"    [ERROR] {result.get('error', 'Unknown error')}")
                    self.failed += 1
        
        # 결과 요약
        total_time = time.time() - start_time
        print("="*80)
        print(f"[SUCCESS] Batch processing completed!")
        print(f"  Total files: {self.total_files}")
        print(f"  Processed: {self.processed}")
        print(f"  Skipped: {self.skipped}")
        print(f"  Failed: {self.failed}")
        print(f"  Total time: {total_time:.1f}s")
        
        if self.processed > 0:
            print(f"  Average time: {total_time/self.processed:.1f}s per processed file")
            if self.enable_parallel:
                print(f"  Theoretical speedup: ~{self.num_workers:.1f}x faster than sequential")
        
        print(f"  Cache directory: {self.output_dir}")
        
        return {
            "total": self.total_files,
            "processed": self.processed,
            "skipped": self.skipped,
            "failed": self.failed,
            "total_time": total_time
        }

def main():
    """메인 함수"""
    import argparse
    
    parser = argparse.ArgumentParser(description="일괄 복셀화 처리기 (Trimesh + 병렬처리)")
    parser.add_argument("--input-dir", default="fbx_blocks/converted_obj", 
                       help="OBJ 파일들이 있는 디렉토리 (기본값: fbx_blocks/converted_obj)")
    parser.add_argument("--output-dir", default="voxel_cache",
                       help="복셀화 결과 저장 디렉토리 (기본값: voxel_cache)")
    parser.add_argument("--resolution", type=float, default=0.5,
                       help="복셀화 해상도 (기본값: 0.5m)")
    parser.add_argument("--force-rebuild", action="store_true",
                       help="기존 캐시를 무시하고 다시 처리")
    parser.add_argument("--max-files", type=int,
                       help="처리할 최대 파일 수 (테스트용)")
    parser.add_argument("--disable-parallel", action="store_true",
                       help="병렬처리 비활성화 (순차 처리)")
    parser.add_argument("--workers", type=int, default=4,
                       help="병렬처리 워커 수 (기본값: 4)")
    
    args = parser.parse_args()
    
    print("TRIMESH" + "="*70)
    print("Trimesh Batch Voxelizer - High Quality 2.5D Cache with Parallel Processing")
    print("TRIMESH" + "="*70)
    
    try:
        voxelizer = BatchVoxelizer(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            resolution=args.resolution,
            enable_parallel=not args.disable_parallel,
            num_workers=args.workers
        )
        
        result = voxelizer.process_all(args.force_rebuild, args.max_files)
        
        print(f"\n[FINAL SUMMARY]")
        print(f"  Total processing time: {result['total_time']:.1f}s")
        print(f"  Success rate: {result['processed']/(result['total'] or 1)*100:.1f}%")
        if result['total_time'] > 0:
            print(f"  Overall throughput: {result['processed']/result['total_time']*60:.1f} blocks/minute")
        
    except KeyboardInterrupt:
        print(f"\n[WARNING] 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n[ERROR] 예상치 못한 오류: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    main()