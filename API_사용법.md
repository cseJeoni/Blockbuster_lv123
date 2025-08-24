# Blockbuster API 사용법

다른 프로젝트에서 자항선 블록 배치 시스템을 쉽게 사용할 수 있는 API입니다.

## 🚀 빠른 시작

### 1. API 모듈 import
```python
from placement_api import generate_config, run_placement, get_unplaced_blocks, get_available_blocks
```

### 2. 기본 사용 패턴
```python
# 1단계: 사용 가능한 블록 확인
available_blocks = get_available_blocks()

# 2단계: Config 파일 생성
config_path = generate_config("MyShip", 80, 40, ["2534_202_000", "2534_212_000"])

# 3단계: 배치 시뮬레이션
result = run_placement(config_path, max_time=10)

# 4단계: 배치 못한 블록 활용
unplaced_blocks = result['unplaced_blocks']
```

## 📚 API 함수 상세

### `get_available_blocks()`
사용 가능한 블록 목록 조회

**Returns:**
- `list`: 사용 가능한 블록 이름 리스트

```python
blocks = get_available_blocks()
print(f"총 {len(blocks)}개 블록 사용 가능")
print("예시:", blocks[:5])
```

### `generate_config(ship_name, width, height, block_list, ...)`
Config 파일 생성

**Parameters:**
- `ship_name` (str): 자항선 이름
- `width` (float): 자항선 너비 (미터)
- `height` (float): 자항선 높이 (미터)
- `block_list` (list): 배치할 블록 이름 리스트
- `bow_margin` (int, optional): 선수 여백 (기본값: 2)
- `stern_margin` (int, optional): 선미 여백 (기본값: 2)
- `block_clearance` (int, optional): 블록 간격 (기본값: 1)

**Returns:**
- `str`: 생성된 config 파일 경로

```python
# 기본 사용
config_path = generate_config("TestShip", 100, 50, ["2534_202_000", "4374_172_000"])

# 상세 옵션
config_path = generate_config(
    ship_name="LargeShip",
    width=120,
    height=60,
    block_list=my_blocks,
    bow_margin=1,        # 선수 여백 줄이기
    stern_margin=1,      # 선미 여백 줄이기
    block_clearance=2    # 블록 간격 늘리기
)
```

### `run_placement(config_path, max_time=5, enable_visualization=False)`
블록 배치 시뮬레이션 실행

**Parameters:**
- `config_path` (str): Config 파일 경로
- `max_time` (int, optional): 최대 실행 시간 초 (기본값: 5)
- `enable_visualization` (bool, optional): 시각화 활성화 (기본값: False)

**Returns:**
- `dict`: 배치 결과 정보

```python
# 기본 실행
result = run_placement(config_path)

# 시각화 포함 실행  
result = run_placement(config_path, max_time=30, enable_visualization=True)

# 결과 구조
{
    'success': True,                    # 배치 성공 여부
    'placed_count': 4,                  # 배치된 블록 수
    'total_count': 6,                   # 전체 블록 수
    'success_rate': 66.7,               # 배치 성공률 (%)
    'unplaced_blocks': ['block1', 'block2'],  # 배치 못한 블록 리스트
    'placement_time': 15.23,            # 소요 시간 (초)
    'config_name': 'TestShip_20250814'  # Config 이름
}
```

### `get_unplaced_blocks(config_path, max_time=5)`
배치 못한 블록 리스트만 간단히 반환

**Parameters:**
- `config_path` (str): Config 파일 경로  
- `max_time` (int, optional): 최대 실행 시간 초 (기본값: 5)

**Returns:**
- `list`: 배치 못한 블록 이름 리스트

```python
# 간단하게 배치 못한 블록만 얻기
unplaced = get_unplaced_blocks(config_path)
print(f"배치 실패: {unplaced}")
```

## 🔄 실전 사용 예제

### 예제 1: 기본 배치 및 재시도
```python
from placement_api import *

# 1차 배치 시도
blocks = ["2534_202_000", "2534_212_000", "4374_172_000", "2534_292_000"]
config1 = generate_config("Ship1", 80, 40, blocks)
result1 = run_placement(config1, max_time=10)

print(f"1차 결과: {result1['success_rate']:.1f}% 성공")
print(f"배치 못한 블록: {result1['unplaced_blocks']}")

# 2차 재시도 (더 큰 자항선, 여백 축소)
if result1['unplaced_blocks']:
    config2 = generate_config(
        "Ship2", 120, 60, 
        result1['unplaced_blocks'], 
        bow_margin=1, 
        stern_margin=1
    )
    result2 = run_placement(config2, max_time=15)
    print(f"2차 결과: {result2['success_rate']:.1f}% 성공")
```

### 예제 2: 반복적 최적화
```python
def optimize_placement(blocks, max_attempts=3):
    """여러 조건으로 반복 시도하여 최적화"""
    
    conditions = [
        {"width": 80, "height": 40, "bow_margin": 2, "stern_margin": 2},
        {"width": 100, "height": 50, "bow_margin": 1, "stern_margin": 1},
        {"width": 120, "height": 60, "bow_margin": 1, "stern_margin": 1},
    ]
    
    remaining_blocks = blocks.copy()
    all_results = []
    
    for i, condition in enumerate(conditions):
        if not remaining_blocks:
            break
            
        print(f"\n=== 시도 {i+1}: {condition['width']}×{condition['height']} ===")
        
        config = generate_config(
            f"Attempt{i+1}", 
            condition['width'], 
            condition['height'],
            remaining_blocks,
            condition['bow_margin'],
            condition['stern_margin']
        )
        
        result = run_placement(config, max_time=15)
        all_results.append(result)
        
        print(f"성공률: {result['success_rate']:.1f}%")
        
        # 다음 시도를 위해 배치 못한 블록만 남김
        remaining_blocks = result['unplaced_blocks']
    
    return all_results, remaining_blocks

# 사용
initial_blocks = ["2534_202_000", "2534_212_000", "4374_172_000", "2534_292_000"]
results, final_unplaced = optimize_placement(initial_blocks)

total_placed = sum(r['placed_count'] for r in results)
print(f"\n최종 결과: {len(initial_blocks) - len(final_unplaced)}/{len(initial_blocks)} 블록 배치 성공")
```

### 예제 3: 배치 결과 분석
```python
def analyze_placement(config_path):
    """배치 결과 상세 분석"""
    
    result = run_placement(config_path, enable_visualization=True)
    
    print(f"=== 배치 분석 결과 ===")
    print(f"전체 블록: {result['total_count']}개")
    print(f"배치 성공: {result['placed_count']}개 ({result['success_rate']:.1f}%)")
    print(f"배치 실패: {len(result['unplaced_blocks'])}개")
    print(f"소요 시간: {result['placement_time']:.2f}초")
    
    if result['unplaced_blocks']:
        print(f"\n배치 실패 블록:")
        for block in result['unplaced_blocks']:
            print(f"  - {block}")
        
        # 재시도 권장사항
        print(f"\n권장사항:")
        if result['success_rate'] < 50:
            print("  - 자항선 크기를 늘려보세요 (width, height 증가)")
            print("  - 여백을 줄여보세요 (bow_margin, stern_margin 감소)")
        else:
            print("  - 시간을 늘려서 재시도해보세요 (max_time 증가)")
    
    return result
```

## ⚠️ 주의사항

1. **voxel_cache 폴더 필요**: 블록 데이터가 미리 준비되어 있어야 함
2. **경로**: Blockbuster_Test 폴더에서 실행하거나 sys.path 설정 필요

## 🔧 문제 해결

**"voxel_cache 폴더에 블록 데이터가 없습니다"**
```bash
python batch_voxelizer.py  # 블록 데이터 생성
```

**"import 오류"**
- Blockbuster_Test 폴더에서 실행
- 또는 sys.path에 경로 추가
