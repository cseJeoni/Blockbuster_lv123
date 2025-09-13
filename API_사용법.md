# Blockbuster API 사용법

다른 프로젝트에서 자항선 블록 배치 시스템을 쉽게 사용할 수 있는 API입니다.

## 🚀 빠른 시작

### 1. API 모듈 import
```python
from Placement_api import generate_config, run_placement, get_unplaced_blocks, get_available_blocks
```

### 2. 기본 사용 패턴 (배치 못한 블록 확인)
```python
# 1단계: Config 파일 생성
config_path = generate_config("MyShip", 80, 40, ["2534_202_000", "2534_212_000"])

# 2단계: 배치 못한 블록 확인
unplaced_blocks = get_unplaced_blocks(config_path)
print("배치 못한 블록:", unplaced_blocks)
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
- `ring_bow_clearance` (int, optional): 크레인 링 선수 여백 (기본값: 10)

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

### `run_placement(config_path, max_time=10, enable_visualization=False)`
블록 배치 시뮬레이션 실행

**Parameters:**
- `config_path` (str): Config 파일 경로
- `max_time` (int, optional): 최대 실행 시간 초 (기본값: 10)
- `enable_visualization` (bool, optional): 시각화 활성화 (기본값: False)

**Returns:**
- `dict`: 배치 결과 정보

```python
# 기본 실행
result = run_placement(config_path)

# 시각화 포함 실행  
result = run_placement(config_path, max_time=15, enable_visualization=True)

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

### `get_unplaced_blocks(config_path, max_time=10)`
배치를 실행하고 배치 못한 블록 리스트만 간단히 반환

**Parameters:**
- `config_path` (str): Config 파일 경로  
- `max_time` (int, optional): 최대 실행 시간 초 (기본값: 10)

**Returns:**
- `list`: 배치 못한 블록 이름 리스트

```python
# 배치를 실행하고 배치 못한 블록만 얻기
unplaced = get_unplaced_blocks(config_path)
print(f"배치 실패: {unplaced}")
```

## 🔄 실전 사용 예제

### 예제 1: 기본 배치
```python
from placement_api import *

# 블록 배치 시도
blocks = ["2534_202_000", "2534_212_000", "4374_172_000", "2534_292_000"]
config = generate_config("TestShip", 80, 40, blocks)
result = run_placement(config, max_time=15)

print(f"배치 결과: {result['success_rate']:.1f}% 성공")
print(f"배치 완료: {result['placed_count']}/{result['total_count']} 블록")
if result['unplaced_blocks']:
    print(f"배치 실패 블록: {result['unplaced_blocks']}")
```

### 예제 2: 배치 못한 블록 확인 (핵심 사용법)
```python
from placement_api import *

# 배치 못한 블록만 간단히 확인
blocks = ["2534_202_000", "2534_212_000", "4374_172_000", "2534_292_000"]
config = generate_config("MyShip", 80, 40, blocks)

# 방법 1: 배치 못한 블록만 반환
unplaced_blocks = get_unplaced_blocks(config)
print("배치 실패 블록:", unplaced_blocks)

# 방법 2: 전체 결과에서 확인
result = run_placement(config)
print("배치 실패 블록:", result['unplaced_blocks'])
print("성공률:", f"{result['success_rate']:.1f}%")
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
