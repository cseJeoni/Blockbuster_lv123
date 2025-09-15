# LV3: 통합 항차 스케줄링 및 최적화 시스템
---

## 📋 목차

1. [시스템 개요](#1-시스템-개요)
2. [주요 구성 요소](#2-주요-구성-요소)
3. [Peak Scheduler 시스템](#3-peak-scheduler-시스템)
4. [스케줄 시각화 시스템](#4-스케줄-시각화-시스템)
5. [배치 이미지 생성 시스템](#5-배치-이미지-생성-시스템)
6. [데이터 구조](#6-데이터-구조)
7. [사용 가이드](#7-사용-가이드)
8. [출력 결과](#8-출력-결과)

---

## 1. 시스템 개요

### 1.1 프로젝트 목적
LV3는 **통합 항차 스케줄링 및 최적화**를 담당하는 최상위 시스템입니다. 자항선별 운항 사이클을 고려하여 자동으로 항차를 생성하고, LV2 배정 시스템과 연동하여 전체 블록 운송 계획을 최적화합니다.

### 1.2 핵심 특징
- **자동 항차 생성**: 블록 데드라인 기반 스마트 스케줄링
- **사이클 시간 반영**: 자항선별 운항 사이클 고려
- **통합 최적화**: LV1/LV2 시스템과 완전 연동
- **Rescue Pass**: 미배정 블록 구제를 위한 추가 최적화
- **실시간 시각화**: 간트 차트 및 배치 이미지 생성
- **결정론적 실행**: Hash randomization 문제 해결

### 1.3 시스템 아키텍처
```
┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐
│  블록 데드라인   │──▶│  Peak Scheduler │──▶│  통합 배정 결과  │
│ (block_deadline) │   │ (lv3_peak_...)  │   │     (.json)    │
└─────────────────┘   └─────────────────┘   └─────────────────┘
                             │                        │
┌─────────────────┐          │               ┌─────────────────┐
│  자항선 사양     │──────────┘               │  시각화 결과     │
│(vessel_specs)   │                          │ (HTML/PNG)     │
└─────────────────┘                          └─────────────────┘
                                                     ▲
                      ┌─────────────────┐            │
                      │  LV2 배정 시스템 │────────────┘
                      │ (lv2_assignment)│
                      └─────────────────┘
                             ▲
                      ┌─────────────────┐
                      │  LV1 배치 시스템 │
                      │ (placement_api) │
                      └─────────────────┘
```

---

## 2. 주요 구성 요소

### 2.1 파일 구조
```
LV3/
├── lv3_peak_scheduler.py          # 핵심 스케줄링 엔진
├── schedule_visualizer.py         # 간트 차트 시각화
├── generate_placement_images.py   # 배치 이미지 생성
├── lv3_integrated_voyage_assignments.json  # 최종 결과
└── README.md                      # 본 문서
```

### 2.2 의존성
- **LV2 시스템**: 블록 배정 및 라벨링
- **LV1 시스템**: 실제 블록 배치 검증
- **데이터 파일**: 
  - `../data/block_deadline_7.csv` (블록 데드라인)
  - `../vessel_specs.json` (자항선 사양 및 사이클)

---

## 3. Peak Scheduler 시스템

### 3.1 기능 개요
`lv3_peak_scheduler.py`는 LV3의 핵심 엔진으로, 블록 데드라인을 분석하여 최적의 항차 스케줄을 자동 생성합니다.

### 3.2 스케줄링 알고리즘

#### 3.2.1 메인 알고리즘 흐름
1. **데드라인 분석**: 블록별 완성 기한 파악
2. **후보 날짜 생성**: 데드라인 기반 항차 출발일 후보 생성
3. **날짜별 스코어링**: 각 후보 날짜의 효율성 평가
4. **최적 날짜 선택**: 스코어가 가장 높은 날짜 선택
5. **LV2 배정 실행**: 선택된 날짜로 블록 배정 수행
6. **Rescue Pass**: 미배정 블록 구제를 위한 추가 라운드

#### 3.2.2 스코어링 함수
```python
def score_date(self, date_str: str, remaining: Set[str]) -> float:
    """
    날짜별 스코어 계산:
    - 배정 가능한 블록 수 (가중치 높음)
    - 데드라인 여유도
    - 자항선 가용성
    """
```

#### 3.2.3 Rescue Pass 메커니즘
- 각 라운드 종료 후 실행
- 미배정 블록을 대상으로 추가 배정 시도
- 배치율 극대화를 위한 최후 수단

### 3.3 사용법
```bash
# 기본 실행
python lv3_peak_scheduler.py

# 디버그 모드 (상세 로그 출력)
python lv3_peak_scheduler.py --debug

# 사용자 지정 데드라인 파일
python lv3_peak_scheduler.py --deadline /path/to/deadline.csv
```

### 3.4 핵심 클래스

#### 3.4.1 PeakScheduler
- 메인 스케줄링 로직 담당
- 후보 날짜 생성 및 평가
- LV2 시스템과의 연동

#### 3.4.2 주요 메서드
- `generate_candidate_dates()`: 후보 날짜 생성
- `score_date()`: 날짜별 효율성 평가
- `rescue_pass()`: 미배정 블록 구제
- `run_scheduling()`: 전체 스케줄링 실행

---

## 4. 스케줄 시각화 시스템

### 4.1 기능 개요
`schedule_visualizer.py`는 생성된 항차 스케줄을 직관적인 간트 차트로 시각화합니다.

### 4.2 주요 기능
- **간트 차트 생성**: 자항선별 운항 스케줄 시각화
- **블록 정보 표시**: 각 항차에 배정된 블록 수 표시
- **사이클 단계 구분**: 적재/운항/하역/복귀 단계별 색상 구분
- **대화형 HTML**: 마우스 오버로 상세 정보 확인

### 4.3 사용법
```bash
# 기본 실행 (결과 JSON 파일 자동 감지)
python schedule_visualizer.py

# 사용자 지정 파일
python schedule_visualizer.py --input lv3_result.json --output schedule.html
```

### 4.4 시각화 요소

#### 4.4.1 색상 코딩
- **적재 단계**: 파란색 (Loading)
- **운항 단계**: 초록색 (Transit)
- **하역 단계**: 주황색 (Unloading)
- **복귀 단계**: 빨간색 (Return)

#### 4.4.2 정보 표시
- 항차 ID 및 기간
- 배정된 블록 수
- 자항선 ID
- 각 단계별 소요 시간

---

## 5. 배치 이미지 생성 시스템

### 5.1 기능 개요
`generate_placement_images.py`는 LV3 결과를 바탕으로 각 항차별 실제 블록 배치 이미지를 생성합니다.

### 5.2 주요 기능
- **자동 이미지 생성**: 모든 항차에 대해 배치 이미지 생성
- **LV1 연동**: 실제 배치 알고리즘 사용
- **배치 검증**: 배치 성공/실패 여부 확인
- **결과 정리**: 생성된 이미지 자동 정리

### 5.3 사용법
```bash
# 기본 실행
python generate_placement_images.py

# 사용자 지정 설정
python generate_placement_images.py --input lv3_result.json --output_dir images/
```

### 5.4 출력 결과
- **이미지 파일**: 각 항차별 PNG 이미지
- **로그 정보**: 배치 성공률 및 오류 정보
- **자동 정리**: 임시 파일 자동 삭제

---

## 6. 데이터 구조

### 6.1 입력 데이터

#### 6.1.1 블록 데드라인 (block_deadline_7.csv)
```csv
block_id,deadline
2534_212_000,241201
2534_221_000,241205
```

#### 6.1.2 자항선 사양 (vessel_specs.json)
```json
{
  "vessels": [
    {
      "id": 1,
      "name": "자항선1",
      "width": 170,
      "height": 62,
      "cycle_phases": [3, 3, 3, 3]
    }
  ]
}
```

### 6.2 출력 데이터

#### 6.2.1 통합 배정 결과 (lv3_integrated_voyage_assignments.json)
```json
{
  "voyage_assignments": {
    "V_20241201_1": {
      "vessel_id": 1,
      "departure_date": "2024-12-01",
      "arrival_date": "2024-12-07",
      "blocks": ["2534_212_000", "2534_221_000"],
      "placement_success": true,
      "placement_rate": 87.5,
      "cycle_phases": {
        "loading": "2024-12-01 to 2024-12-04",
        "transit": "2024-12-04 to 2024-12-07",
        "unloading": "2024-12-07 to 2024-12-10",
        "return": "2024-12-10 to 2024-12-13"
      }
    }
  },
  "summary": {
    "total_blocks": 100,
    "assigned_blocks": 87,
    "assignment_rate": 87.0,
    "total_voyages": 15,
    "scheduling_duration": "2024-12-01 to 2024-12-31"
  }
}
```

---

## 7. 사용 가이드

### 7.1 전체 워크플로우
```bash
# 1단계: LV3 스케줄링 실행
cd LV3
python lv3_peak_scheduler.py

# 2단계: 스케줄 시각화
python schedule_visualizer.py

# 3단계: 배치 이미지 생성
python generate_placement_images.py

# 4단계: 결과 확인
# - lv3_integrated_voyage_assignments.json: 최종 배정 결과
# - schedule_gantt.html: 간트 차트
# - placement_images/: 배치 이미지들
```

### 7.2 주요 매개변수

#### 7.2.1 lv3_peak_scheduler.py
- `--deadline`: 블록 데드라인 CSV 파일 경로
- `--debug`: 디버그 모드 활성화
- `--output`: 결과 JSON 파일명

#### 7.2.2 schedule_visualizer.py
- `--input`: 입력 JSON 파일 경로
- `--output`: 출력 HTML 파일명
- `--title`: 차트 제목

#### 7.2.3 generate_placement_images.py
- `--input`: LV3 결과 JSON 파일
- `--output_dir`: 이미지 출력 디렉토리
- `--cleanup`: 임시 파일 자동 정리 여부

### 7.3 성능 튜닝

#### 7.3.1 스케줄링 정책 상수
```python
# lv3_peak_scheduler.py 내부
CANDIDATE_DAYS_BEFORE = 7    # 데드라인 이전 후보일 수
CANDIDATE_DAYS_AFTER = 3     # 데드라인 이후 후보일 수
MIN_BLOCKS_THRESHOLD = 5     # 최소 블록 수 임계값
```

#### 7.3.2 메모리 최적화
- `@lru_cache` 데코레이터로 스코어링 함수 캐싱
- 불필요한 중간 결과 즉시 해제
- 대용량 데이터 스트리밍 처리

### 7.4 문제 해결

#### 7.4.1 스케줄링 실패
```
[ERROR] 후보 날짜를 찾을 수 없습니다
```
- 블록 데드라인이 너무 촉박한지 확인
- 자항선 사양이 올바른지 검증
- `CANDIDATE_DAYS_BEFORE` 값 증가 고려

#### 7.4.2 시각화 오류
```
[ERROR] vessel_specs.json에서 사이클 데이터 로드 실패
```
- `vessel_specs.json` 파일의 `cycle_phases` 필드 확인
- JSON 형식 유효성 검증

#### 7.4.3 배치 이미지 생성 실패
```
[ERROR] Placement_api 모듈을 찾을 수 없습니다
```
- LV1 시스템이 올바르게 설치되었는지 확인
- Python 경로 설정 확인

---

## 8. 출력 결과

### 8.1 스케줄링 결과
- **파일**: `lv3_integrated_voyage_assignments.json`
- **내용**: 자동 생성된 항차별 블록 배정 결과

### 8.2 시각화 결과
- **파일**: `schedule_gantt.html`
- **내용**: 대화형 간트 차트 (웹 브라우저에서 열기)

### 8.3 배치 이미지
- **디렉토리**: `placement_images/`
- **내용**: 각 항차별 실제 블록 배치 PNG 이미지

### 8.4 성능 지표
- **전체 배정률**: 모든 블록 대비 배정 성공률
- **항차 효율성**: 항차당 평균 블록 수
- **데드라인 준수율**: 기한 내 완성 가능한 블록 비율
- **자항선 활용률**: 각 자항선의 가동 시간 비율

---

## 9. 고급 기능

### 9.1 결정론적 실행
LV3는 Python의 hash randomization 문제를 해결하여 동일한 입력에 대해 항상 동일한 결과를 보장합니다.

```python
# 해결된 문제들:
# - Set 순회 순서 고정
# - 후보 날짜 생성 순서 결정론적 처리
# - 블록 선택 순서 일관성 보장
```

### 9.2 확장성
- **새로운 자항선 추가**: `vessel_specs.json`에 사양 추가만으로 지원
- **사용자 정의 스코어링**: 스코어링 함수 커스터마이징 가능
- **다양한 시각화**: 새로운 차트 타입 쉽게 추가 가능

### 9.3 모니터링
- **실시간 로그**: 스케줄링 진행 상황 실시간 확인
- **성능 메트릭**: 각 단계별 소요 시간 측정
- **오류 추적**: 상세한 오류 정보 및 해결 방안 제시

---

## 📞 지원 및 문의

LV3 시스템 사용 중 문제가 발생하거나 추가 기능이 필요한 경우, 개발팀에 문의하시기 바랍니다.

**주요 특징 요약**:
- ✅ 완전 자동화된 항차 스케줄링
- ✅ 자항선 사이클 시간 정확 반영
- ✅ LV1/LV2 시스템과 완벽 연동
- ✅ 결정론적 실행 보장
- ✅ 실시간 시각화 및 모니터링
- ✅ Rescue Pass로 배치율 극대화
- ✅ 확장 가능한 아키텍처
