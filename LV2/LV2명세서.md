# LV2: 블록 배정 및 스케줄링 시스템
---

## 📋 목차

1. [시스템 개요](#1-시스템-개요)
2. [주요 구성 요소](#2-주요-구성-요소)
3. [블록 라벨링 시스템](#3-블록-라벨링-시스템)
4. [통합 배정 시스템](#4-통합-배정-시스템)
5. [데이터 구조](#5-데이터-구조)
6. [사용 가이드](#6-사용-가이드)
7. [출력 결과](#7-출력-결과)

---

## 1. 시스템 개요

### 1.1 프로젝트 목적
LV2는 **블록 분류 및 항차별 배정**을 담당하는 시스템입니다. 복셀 데이터를 기반으로 블록을 자항선별로 분류하고, 데드라인과 자항선 스케줄을 고려하여 최적의 배정을 수행합니다.

### 1.2 핵심 특징
- **블록 호환성 분석**: 자항선별 블록 적재 가능성 판단
- **VIP/Normal 분류**: 자항선1 전용 블록을 VIP로 분류
- **데드라인 기반 배정**: 블록 완성 기한을 고려한 스케줄링
- **Top-off 최적화**: 배치율 극대화를 위한 추가 배정
- **시각화 지원**: 배정 결과의 시각적 확인

### 1.3 시스템 아키텍처
```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│   복셀 캐시      │──▶│   블록 라벨링    │──▶│  호환성 결과     │
│ (voxel_cache)   │   │(block_labeling) │   │    (.json)     │
└─────────────────┘   └─────────────────┘   └─────────────────┘
                                                     │
┌─────────────────┐   ┌─────────────────┐            │
│  배정 결과 저장  │◀──│   통합 배정      │◀───────────┘
│   (.json)      │   │(lv2_assignment) │
└─────────────────┘   └─────────────────┘
                             ▲
                      ┌─────────────────┐
                      │ 블록 데드라인    │
                      │ 자항선 스케줄    │
                      └─────────────────┘
```

---

## 2. 주요 구성 요소

### 2.1 파일 구조
```
LV2/
├── block_labeling.py          # 블록 호환성 분석 및 라벨링
├── lv2_assignment.py          # 통합 배정 시스템
├── cleanup_voxel_cache.py     # 복셀 캐시 정리 유틸리티
├── block_labeling_results.json # 블록 라벨링 결과
└── README.md                  # 본 문서
```

### 2.2 의존성
- **LV1 시스템**: 복셀 캐시 및 배치 API
- **데이터 파일**: 
  - `../data/block_deadline_7.csv` (블록 데드라인)
  - `../data/vessel_schedule_7.csv` (자항선 스케줄)
  - `../vessel_specs.json` (자항선 사양)

---

## 3. 블록 라벨링 시스템

### 3.1 기능 개요
`block_labeling.py`는 복셀 캐시에서 블록 정보를 읽어 자항선별 호환성을 분석합니다.

### 3.2 주요 기능
- **블록 치수 분석**: 복셀 데이터에서 가로/세로/면적 계산
- **자항선 호환성 테스트**: 안전여백을 고려한 적재 가능성 판단
- **90도 회전 지원**: 회전 시 적재 가능성도 함께 검사
- **VIP 분류**: 자항선1에만 적재 가능한 블록을 VIP로 분류

### 3.3 사용법
```bash
# 기본 실행 (기본 경로 사용)
python block_labeling.py

# 사용자 지정 경로
python block_labeling.py --voxel_cache /path/to/voxel_cache --vessels /path/to/vessel_specs.json

# 안전여백 조정
python block_labeling.py --safety 3.0
```

### 3.4 출력 결과
```json
{
  "block_id": {
    "width": 50.0,
    "height": 30.0,
    "area": 1500.0,
    "compatible_vessels": [1, 2, 3],
    "is_vip": false,
    "issues": []
  }
}
```

---

## 4. 통합 배정 시스템

### 4.1 기능 개요
`lv2_assignment.py`는 블록 라벨링 결과와 스케줄 정보를 바탕으로 최적의 블록 배정을 수행합니다.

### 4.2 배정 알고리즘
1. **VIP 우선 배정**: 자항선1 전용 블록을 우선 처리
2. **데드라인 기반 정렬**: 완성 기한이 빠른 블록부터 배정
3. **용량 기반 필터링**: 자항선 적재 용량 내에서 후보 선별

4. **LV1 배치 검증**: 실제 배치 가능성 확인
5. **Top-off 최적화**: 남은 공간에 추가 블록 배정

### 4.3 사용법
```bash
# 기본 실행
python lv2_assignment.py

# 사용자 지정 파일
python lv2_assignment.py /path/to/deadline.csv /path/to/labeling.json /path/to/schedule.csv
```

### 4.4 핵심 클래스

#### 4.4.1 VoyageSchedule
- 자항선 스케줄 관리
- CSV 파일에서 항차 정보 로드
- 날짜 형식 변환 및 검증

#### 4.4.2 IntegratedVoyageAssigner
- 통합 배정 로직 수행
- VIP/Normal 블록 분리 처리
- Top-off 최적화 실행

---

## 5. 데이터 구조

### 5.1 입력 데이터

#### 5.1.1 블록 데드라인 (block_deadline_7.csv)
```csv
block_id,deadline
2534_212_000,241201
2534_221_000,241205
```

#### 5.1.2 자항선 스케줄 (vessel_schedule_7.csv)
```csv
voyage_id,vessel_id,departure_date,arrival_date
V001,1,241201,241203
V002,2,241202,241204
```

#### 5.1.3 자항선 사양 (vessel_specs.json)
```json
{
  "vessels": [
    {
      "id": 1,
      "name": "자항선1",
      "width": 170,
      "height": 62
    }
  ]
}
```

### 5.2 출력 데이터

#### 5.2.1 배정 결과 (lv2_voyage_assignments.json)
```json
{
  "voyage_assignments": {
    "V001": {
      "vessel_id": 1,
      "blocks": ["2534_212_000", "2534_221_000"],
      "placement_success": true,
      "placement_rate": 85.5
    }
  },
  "summary": {
    "total_blocks": 100,
    "assigned_blocks": 85,
    "assignment_rate": 85.0
  }
}
```

---

## 6. 사용 가이드

### 6.1 전체 워크플로우
```bash
# 0단계: 필요한 복셀 캐시만 남기고 삭제
cd LV2
python cleanup_voxel_cache.py

# 1단계: 블록 라벨링 실행
cd LV2
python block_labeling.py

# 2단계: 통합 배정 실행
python lv2_assignment.py

# 3단계: 결과 확인
# - block_labeling_results.json: 블록 호환성 결과
# - lv2_voyage_assignments.json: 배정 결과
# - placement_results/: 시각화 이미지
```

### 6.2 주요 매개변수

#### 6.2.1 block_labeling.py
- `--voxel_cache`: 복셀 캐시 디렉토리 (기본: ../voxel_cache)
- `--vessels`: 자항선 사양 파일 (기본: ../vessel_specs.json)
- `--safety`: 안전여백 (기본: 2.0m)
- `--out`: 출력 파일명 (기본: block_labeling_results.json)

#### 6.2.2 lv2_assignment.py
- 첫 번째 인자: 블록 데드라인 CSV 파일
- 두 번째 인자: 블록 라벨링 결과 JSON 파일
- 세 번째 인자: 자항선 스케줄 CSV 파일

### 6.3 문제 해결

#### 6.3.1 파일 경로 오류
```
FileNotFoundError: vessel_specs.json 파일이 없습니다
```
- `vessel_specs.json` 파일이 프로젝트 루트에 있는지 확인
- 파일 형식이 올바른지 검증

#### 6.3.2 복셀 캐시 오류
```
[ERROR] voxel_cache 디렉토리를 찾을 수 없습니다
```
- `voxel_cache` 디렉토리 또는 `voxel_cache.zip` 파일 존재 확인
- LV1 복셀화 전처리가 완료되었는지 확인

---

## 7. 출력 결과

### 7.1 블록 라벨링 결과
- **파일**: `block_labeling_results.json`
- **내용**: 각 블록의 호환 자항선 목록, VIP 여부, 문제점

### 7.2 배정 결과
- **파일**: `lv2_voyage_assignments.json`
- **내용**: 항차별 배정된 블록 목록, 배치 성공률

### 7.3 시각화 결과
- **디렉토리**: `placement_results/`
- **내용**: 각 항차별 블록 배치 이미지 (PNG)

### 7.4 성능 지표
- **배정률**: 전체 블록 대비 배정된 블록 비율
- **배치율**: 배정된 블록 중 실제 배치 성공 비율
- **VIP 우선도**: VIP 블록의 우선 배정 성공률

---

## 📞 지원 및 문의

시스템 사용 중 문제가 발생하거나 추가 기능이 필요한 경우, 개발팀에 문의하시기 바랍니다.

**주요 특징 요약**:
- ✅ 자동화된 블록 호환성 분석
- ✅ 데드라인 기반 스마트 배정
- ✅ VIP 블록 우선 처리
- ✅ Top-off 최적화로 배치율 극대화
- ✅ 실시간 시각화 지원
