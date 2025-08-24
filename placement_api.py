"""
자항선 블록 배치 시스템 API
기존 config_generator.py와 ship_placer.py를 활용한 간단한 인터페이스
"""

import json
import os
import sys
import subprocess
from pathlib import Path

# 프로젝트 모듈 import
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from ship_placer import ShipPlacerConfig
    from config_generator import ConfigGenerator
except ImportError as e:
    print(f"[ERROR] 필요한 모듈을 찾을 수 없습니다: {e}")
    print(f"[INFO] Blockbuster_Test 폴더에서 실행해주세요")


def generate_config(ship_name, width, height, block_list, bow_margin=2, stern_margin=2, block_clearance=1):
    """
    Config 파일 생성 (ConfigGenerator 활용)
    
    Args:
        ship_name (str): 자항선 이름
        width (float): 자항선 너비 (m)
        height (float): 자항선 높이 (m)
        block_list (list): 블록 이름 리스트
        bow_margin (int): 선수 여백 (기본값 2)
        stern_margin (int): 선미 여백 (기본값 2)
        block_clearance (int): 블록 간격 (기본값 1)
    
    Returns:
        str: 생성된 config 파일 경로
    
    Example:
        config_path = generate_config("TestShip", 80, 40, ["2534_202_000", "2534_212_000"])
    """
    generator = ConfigGenerator()
    
    # 블록 이름 리스트로 Config 생성
    config = generator.generate_config_from_blocks(
        ship_name=ship_name,
        width=width,
        height=height,
        block_list=block_list,
        bow_margin=bow_margin,
        stern_margin=stern_margin,
        block_clearance=block_clearance
    )
    
    # Config 파일 저장
    config_filename = generator.save_config(config)
    
    return config_filename


def run_placement(config_path, max_time=5, enable_visualization=False):
    """
    블록 배치 실행 (ShipPlacer 활용)
    
    Args:
        config_path (str): Config 파일 경로
        max_time (int): 최대 실행 시간 (초, 기본값 5)
        enable_visualization (bool): 시각화 활성화 여부 (기본값 False)
    
    Returns:
        dict: {
            'success': bool,
            'placed_count': int,
            'total_count': int,
            'success_rate': float,
            'unplaced_blocks': list,
            'placement_time': float,
            'config_name': str
        }
    
    Example:
        result = run_placement("config_20250814_161004.json", max_time=10)
        print(f"배치 못한 블록: {result['unplaced_blocks']}")
    """
    try:
        # ShipPlacerConfig로 배치 실행
        placer = ShipPlacerConfig(config_path, verbose=False)
        placement_result = placer.run(max_time=max_time, save_visualization=enable_visualization)
        
        if placement_result:
            placed_count = len(placement_result.placed_blocks)
            total_count = placed_count + len(placement_result.unplaced_blocks)
            unplaced_names = [block.id for block_id, block in placement_result.unplaced_blocks.items()]
            success_rate = (placed_count / total_count * 100) if total_count > 0 else 0
            placement_time = getattr(placement_result, 'placement_time', 0)
            
            return {
                'success': True,
                'placed_count': placed_count,
                'total_count': total_count,
                'success_rate': success_rate,
                'unplaced_blocks': unplaced_names,
                'placement_time': placement_time,
                'config_name': placer.config['ship_configuration']['name']
            }
        else:
            return {
                'success': False,
                'placed_count': 0,
                'total_count': 0,
                'success_rate': 0.0,
                'unplaced_blocks': [],
                'placement_time': 0.0,
                'config_name': 'Unknown'
            }
            
    except Exception as e:
        print(f"[ERROR] 배치 실행 실패: {e}")
        return {
            'success': False,
            'placed_count': 0,
            'total_count': 0,
            'success_rate': 0.0,
            'unplaced_blocks': [],
            'placement_time': 0.0,
            'config_name': 'Error'
        }


def get_unplaced_blocks(config_path, max_time=5):
    """
    배치 못한 블록 리스트만 반환
    
    Args:
        config_path (str): Config 파일 경로
        max_time (int): 최대 실행 시간 (초, 기본값 5)
    
    Returns:
        list: 배치 못한 블록 이름 리스트
    
    Example:
        unplaced = get_unplaced_blocks("config_20250814_161004.json")
    """
    result = run_placement(config_path, max_time=max_time, enable_visualization=False)
    return result['unplaced_blocks']


def get_available_blocks():
    """
    사용 가능한 블록 이름 리스트 반환
    
    Returns:
        list: 사용 가능한 블록 이름 리스트
    """
    voxel_cache_dir = Path("voxel_cache")
    if not voxel_cache_dir.exists():
        return []
    
    block_names = []
    for json_file in voxel_cache_dir.glob("*.json"):
        block_names.append(json_file.stem)
    
    return sorted(block_names)


# 사용 예제
if __name__ == "__main__":
    print("=== 자항선 블록 배치 API 사용 예제 ===")
    
    # 1. 사용 가능한 블록 확인
    available_blocks = get_available_blocks()
    print(f"사용 가능한 블록: {len(available_blocks)}개")
    
    if not available_blocks:
        print("voxel_cache 폴더에 블록 데이터가 없습니다!")
        exit()
    
    # 2. Config 생성
    test_blocks = available_blocks[:3]  # 처음 3개 블록으로 테스트
    print(f"\nConfig 생성 중... (블록: {test_blocks})")
    
    config_path = generate_config(
        ship_name="TestShip",
        width=80,
        height=40,
        block_list=test_blocks
    )
    print(f"Config 파일 생성: {config_path}")
    
    # 3. 배치 실행
    print(f"\n배치 실행 중...")
    result = run_placement(config_path, max_time=5)
    
    # 4. 결과 출력
    print(f"\n=== 배치 결과 ===")
    print(f"성공률: {result['success_rate']:.1f}% ({result['placed_count']}/{result['total_count']})")
    print(f"소요 시간: {result['placement_time']:.2f}초")
    
    if result['unplaced_blocks']:
        print(f"배치 못한 블록: {result['unplaced_blocks']}")
    else:
        print("모든 블록이 성공적으로 배치되었습니다!")