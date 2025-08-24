"""
Ship Block Placement Config Generator
자항선 블록 배치를 위한 config.json 자동 생성기

사용법:
    python config_generator.py

기능:
    - 자항선 크기 설정
    - 여백 및 제약 조건 설정
    - 블록 정보 자동 수집 (복셀화 결과 포함)
    - config.json 파일 자동 생성
"""

import json
import os
import sys
from pathlib import Path
import numpy as np
from datetime import datetime

# 프로젝트 모듈 import
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    from Voxelizer import convert_mesh_to_25d_optimized
    from models.voxel_block import VoxelBlock
    print(f"[INFO] Required modules loaded successfully")
except ImportError as e:
    print(f"[ERROR] Cannot find required modules: {e}")
    print(f"[INFO] Make sure Voxelizer.py and models/voxel_block.py exist")

class ConfigGenerator:
    """Config.json 자동 생성기"""
    
    def __init__(self):
        self.config = {}
        self.blocks_directory = "fbx_blocks/converted_obj"
        self.supported_extensions = ['.obj', '.fbx']
        
    def get_user_input(self):
        """사용자로부터 설정 정보 입력 받기"""
        print("SHIP" + "="*60)
        print("Ship Block Placement Config Generator")
        print("SHIP" + "="*60)
        print()
        
        # 1. 자항선 기본 정보
        print("[INFO] 1. 자항선 기본 설정")
        ship_name = input("  자항선 이름 (기본값: Test_Ship): ").strip() or "Test_Ship"
        
        # 2. 자항선 크기 설정
        print("\n[INFO] 2. 자항선 크기 설정 (미터 단위)")
        try:
            width = float(input("  너비 (기본값: 80.0m): ").strip() or "80.0")
            height = float(input("  높이 (기본값: 40.0m): ").strip() or "40.0")
        except ValueError:
            print("  [WARNING] 잘못된 입력, 기본값 사용")
            width, height = 80.0, 40.0
        
        # 3. 여백 설정 (미터 단위)
        print(f"\n[INFO] 3. 여백 설정 (미터 단위)")
        print(f"  전체 자항선 크기: {width}m x {height}m")
        try:
            margin_bow = float(input("  선수 여백 (기본값: 2.5m): ").strip() or "2.5")
            margin_stern = float(input("  선미 여백 (기본값: 0.0m): ").strip() or "0.0") 
        except ValueError:
            print("  [WARNING] 잘못된 입력, 기본값 사용")
            margin_bow, margin_stern = 2.5, 0.0
        
        # 4. 블록 간 이격 거리
        print(f"\n[INFO] 4. 블록 간 이격 거리")
        try:
            min_clearance = float(input("  최소 이격 거리 (미터 단위, 기본값: 1.0m): ").strip() or "1.0")
        except ValueError:
            print("  [WARNING] 잘못된 입력, 기본값 사용")
            min_clearance = 1.0
        
        # 5. 배치할 블록들 선택
        print(f"\n[INFO] 5. 배치할 블록 선택")
        available_blocks = self.find_available_blocks()
        
        if not available_blocks:
            print(f"  [ERROR] {self.blocks_directory} 폴더에 블록 파일이 없습니다!")
            return None
        
        print(f"  사용 가능한 블록들 ({len(available_blocks)}개):")
        for i, (block_name, file_path) in enumerate(available_blocks, 1):
            print(f"    {i:2d}. {block_name}")
        
        print(f"\n  배치할 블록들을 선택하세요:")
        print(f"  - 숫자로 입력 (예: 1,3,5 또는 1-5)")
        print(f"  - 'all'로 모든 블록 선택")
        print(f"  - 빈 입력으로 처음 3개 블록 선택")
        
        selection = input("  선택: ").strip()
        selected_blocks = self.parse_block_selection(selection, available_blocks)
        
        if not selected_blocks:
            print("  [WARNING] 선택된 블록이 없어 처음 3개 블록을 사용합니다")
            selected_blocks = available_blocks[:3]
        
        print(f"\n  선택된 블록들 ({len(selected_blocks)}개):")
        for block_name, file_path in selected_blocks:
            print(f"    - {block_name}")
        
        return {
            'ship_name': ship_name,
            'width': width,
            'height': height,
            'margin_bow': margin_bow,
            'margin_stern': margin_stern,
            'min_clearance': min_clearance,
            'selected_blocks': selected_blocks
        }
    
    def find_available_blocks(self):
        """사용 가능한 블록 파일들 찾기 (OBJ 우선)"""
        blocks_path = Path(self.blocks_directory)
        available_blocks = []
        
        if not blocks_path.exists():
            print(f"  [WARNING] {self.blocks_directory} 폴더가 존재하지 않습니다")
            # Fallback to FBX directory
            blocks_path = Path("fbx_blocks")
            if not blocks_path.exists():
                return available_blocks
            print(f"  [INFO] Using fallback directory: fbx_blocks")
        
        # OBJ 파일 우선 수집
        obj_files = {}
        fbx_files = {}
        
        for file_path in blocks_path.rglob('*'):
            if file_path.is_file() and file_path.suffix.lower() in self.supported_extensions:
                block_name = file_path.stem
                if file_path.suffix.lower() == '.obj':
                    obj_files[block_name] = str(file_path)
                elif file_path.suffix.lower() == '.fbx':
                    fbx_files[block_name] = str(file_path)
        
        # OBJ 파일이 있으면 OBJ 사용, 없으면 FBX 사용
        all_block_names = set(obj_files.keys()) | set(fbx_files.keys())
        for block_name in sorted(all_block_names):
            if block_name in obj_files:
                available_blocks.append((block_name, obj_files[block_name]))
                print(f"  [DEBUG] Using OBJ: {block_name}")
            elif block_name in fbx_files:
                available_blocks.append((block_name, fbx_files[block_name]))
                print(f"  [DEBUG] Using FBX: {block_name}")
        
        print(f"  [INFO] Found {len(obj_files)} OBJ files, {len(fbx_files)} FBX files")
        return available_blocks
    
    def parse_block_selection(self, selection, available_blocks):
        """블록 선택 파싱"""
        if not selection:
            return available_blocks[:3]  # 기본값: 처음 3개
        
        if selection.lower() == 'all':
            return available_blocks
        
        selected_indices = set()
        
        try:
            for part in selection.split(','):
                part = part.strip()
                if '-' in part:
                    # 범위 선택 (예: 1-5)
                    start, end = map(int, part.split('-'))
                    selected_indices.update(range(start-1, end))
                else:
                    # 개별 선택 (예: 1, 3, 5)
                    selected_indices.add(int(part) - 1)
        except ValueError:
            print(f"  [ERROR] 잘못된 선택 형식: {selection}")
            return []
        
        # 유효한 인덱스만 필터링
        valid_indices = [i for i in selected_indices if 0 <= i < len(available_blocks)]
        return [available_blocks[i] for i in sorted(valid_indices)]
    
    def determine_block_type(self, block_name):
        """블록 이름으로 타입 추정"""
        block_name_lower = block_name.lower()
        
        if any(keyword in block_name_lower for keyword in ['crane', '20a', '20b', '20c', '20d', '20e', '20f', '20g', '20h', '20j', '20k', '20l', '20n', '20p', '20y']):
            return 'crane'
        elif any(keyword in block_name_lower for keyword in ['trestle', '_000']):
            return 'trestle'
        else:
            return 'unknown'
    
    def load_from_voxel_cache(self, block_name):
        """voxel_cache에서 기존 복셀화 데이터 로드"""
        cache_file = Path("voxel_cache") / f"{block_name}.json"
        
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                return cache_data['voxel_data']
            except Exception as e:
                print(f"  [WARNING] Cache load failed: {e}")
                return None
        return None
    
    def voxelize_block(self, block_name, file_path):
        """블록 복셀화 수행 (JSON 캐시 우선 사용)"""
        print(f"\n[INFO] 블록 정보 수집 중: {block_name}")
        
        # 먼저 voxel_cache에서 기존 JSON 데이터 확인
        voxel_data = self.load_from_voxel_cache(block_name)
        if voxel_data:
            print(f"  [CACHE] 캐시된 복셀 데이터 사용: {voxel_data['dimensions']['width']}x{voxel_data['dimensions']['height']}")
            return voxel_data
        
        # 캐시가 없으면 에러 (모든 블록은 이미 캐시됨)
        print(f"  [ERROR] 캐시에 {block_name} 데이터가 없습니다")
        return None
    
    def generate_config(self, user_inputs):
        """config.json 생성"""
        print(f"\n[INFO] config.json 생성 중...")
        
        # 현재 시간
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d_%H%M%S")
        
        # 미터 단위를 격자 단위로 변환
        grid_unit = 0.5  # 0.5m per grid
        margin_bow_grids = int(user_inputs['margin_bow'] / grid_unit)
        margin_stern_grids = int(user_inputs['margin_stern'] / grid_unit) 
        block_clearance_grids = int(user_inputs['min_clearance'] / grid_unit)
        
        config = {
            "ship_configuration": {
                "name": f"{user_inputs['ship_name']}_{timestamp}",
                "grid_size": {
                    "width": user_inputs['width'],
                    "height": user_inputs['height'],
                    "grid_unit": grid_unit
                },
                "constraints": {
                    "margin": {
                        "bow": margin_bow_grids,
                        "stern": margin_stern_grids
                    },
                    "block_clearance": block_clearance_grids
                }
            },
            
            "voxelization_settings": {
                "resolution": 0.5,
                "conversion_method": "footprint"
            },
            
            "blocks_to_place": {
                "total_blocks": len(user_inputs['selected_blocks']),
                "blocks": []
            }
        }
        
        # 각 블록 정보 생성
        print(f"[INFO] 블록 복셀화 및 정보 수집 시작...")
        for i, (block_name, file_path) in enumerate(user_inputs['selected_blocks'], 1):
            print(f"\n진행률: {i}/{len(user_inputs['selected_blocks'])}")
            
            # 블록 타입 결정
            block_type = self.determine_block_type(block_name)
            
            # 블록 복셀화
            voxel_data = self.voxelize_block(block_name, file_path)
            
            if voxel_data is None:
                print(f"  [WARNING] {block_name} 복셀화 실패, 기본값으로 추가")
                voxel_data = {
                    "dimensions": {"width": 10, "height": 10},
                    "footprint_positions": []
                }
            
            block_info = {
                "block_id": block_name,
                "block_type": block_type,
                "voxel_data": voxel_data
            }
            
            config["blocks_to_place"]["blocks"].append(block_info)
        
        return config
    
    def generate_config_from_blocks(self, ship_name, width, height, block_list, 
                                   bow_margin=2, stern_margin=2, block_clearance=1):
        """
        블록 이름 리스트로 직접 Config 생성 (API용)
        
        Args:
            ship_name: 자항선 이름
            width: 자항선 너비 (m)
            height: 자항선 높이 (m)
            block_list: 블록 이름 리스트
            bow_margin: 선수 여백 (격자)
            stern_margin: 선미 여백 (격자) 
            block_clearance: 블록 간격 (격자)
        
        Returns:
            dict: Config 딕셔너리
        """
        user_inputs = {
            'ship_name': ship_name,
            'width': width,
            'height': height,
            'margin_bow': bow_margin,
            'margin_stern': stern_margin,
            'min_clearance': block_clearance,
            'selected_blocks': [(block_name, f"voxel_cache/{block_name}.json") for block_name in block_list]
        }
        
        return self.generate_config(user_inputs)
    
    def save_config(self, config, filename=None):
        """config.json 파일 저장"""
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"config_{timestamp}.json"
        
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            
            print(f"\n[OK] Config 파일 생성 완료: {filename}")
            print(f"[INFO] 총 {config['blocks_to_place']['total_blocks']}개 블록 정보 포함")
            return filename
            
        except Exception as e:
            print(f"\n[ERROR] Config 파일 저장 실패: {e}")
            return None
    
    def run(self):
        """메인 실행 함수"""
        print("Config Generator 시작...")
        
        # 1. 사용자 입력 받기
        user_inputs = self.get_user_input()
        if user_inputs is None:
            print("[ERROR] 설정 입력 실패")
            return
        
        # 2. Config 생성
        try:
            config = self.generate_config(user_inputs)
        except Exception as e:
            print(f"[ERROR] Config 생성 실패: {e}")
            return
        
        # 3. 파일 저장
        config_filename = self.save_config(config)
        if config_filename is None:
            return
        
        # 4. 결과 요약
        print(f"\n[SUCCESS] === Config 생성 완료 ===")
        print(f"[INFO] 파일명: {config_filename}")
        print(f"[INFO] 자항선: {user_inputs['ship_name']} ({user_inputs['width']}m x {user_inputs['height']}m)")
        print(f"[INFO] 여백: 선수{user_inputs['margin_bow']}m 선미{user_inputs['margin_stern']}m (격자: {int(user_inputs['margin_bow']/0.5)}, {int(user_inputs['margin_stern']/0.5)})")
        print(f"[INFO] 블록 수: {len(user_inputs['selected_blocks'])}개")
        print(f"[SUCCESS] 이제 ship_placer에서 이 config 파일을 사용할 수 있습니다!")

def main():
    """메인 실행"""
    try:
        generator = ConfigGenerator()
        generator.run()
        
    except KeyboardInterrupt:
        print(f"\n[WARNING] 사용자에 의해 중단됨")
    except Exception as e:
        print(f"\n[ERROR] 예상치 못한 오류: {e}")
        import traceback
        traceback.print_exc()
    
    input("\n아무 키나 눌러서 종료...")

if __name__ == "__main__":
    main()