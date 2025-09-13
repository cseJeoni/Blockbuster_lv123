"""
자항선 스펙 관리 유틸리티
vessel_specs.json 파일을 읽어서 자항선 정보를 제공하는 모듈
"""

import json
import os
from typing import Dict, List, Optional, Tuple

class VesselSpecManager:
    """자항선 스펙 관리 클래스"""
    
    def __init__(self, specs_file: str = "vessel_specs.json"):
        self.specs_file = specs_file
        self._specs = None
        self._load_specs()
    
    def _load_specs(self):
        """vessel_specs.json 파일 로드"""
        try:
            if os.path.exists(self.specs_file):
                with open(self.specs_file, 'r', encoding='utf-8') as f:
                    self._specs = json.load(f)
            else:
                print(f"[WARNING] {self.specs_file} 파일이 없습니다. 기본값을 사용합니다.")
                self._specs = self._get_default_specs()
        except Exception as e:
            print(f"[ERROR] vessel_specs.json 로드 실패: {e}")
            self._specs = self._get_default_specs()
    
    def _get_default_specs(self) -> Dict:
        """기본 자항선 스펙 (fallback)"""
        return {
            "vessels": [
                {
                    "id": 1, "name": "자항선1", "width": 62, "height": 170,
                    "cycle": {"departure_days": 3, "loading_days": 3, "unloading_days": 3, "return_days": 3, "total_days": 12},
                    "rest_period_days": 2, "color": "#4F46E5"
                },
                {
                    "id": 2, "name": "자항선2", "width": 36, "height": 84,
                    "cycle": {"departure_days": 3, "loading_days": 1, "unloading_days": 3, "return_days": 1, "total_days": 8},
                    "rest_period_days": 1, "color": "#16A34A"
                },
                {
                    "id": 3, "name": "자항선3", "width": 32, "height": 120,
                    "cycle": {"departure_days": 3, "loading_days": 3, "unloading_days": 3, "return_days": 2, "total_days": 11},
                    "rest_period_days": 1, "color": "#DC2626"
                },
                {
                    "id": 4, "name": "자항선4", "width": 40, "height": 130,
                    "cycle": {"departure_days": 3, "loading_days": 3, "unloading_days": 3, "return_days": 2, "total_days": 11},
                    "rest_period_days": 1, "color": "#0891B2"
                },
                {
                    "id": 5, "name": "자항선5", "width": 32, "height": 116,
                    "cycle": {"departure_days": 3, "loading_days": 3, "unloading_days": 3, "return_days": 2, "total_days": 11},
                    "rest_period_days": 1, "color": "#A855F7"
                }
            ]
        }
    
    def get_all_vessels(self) -> List[Dict]:
        """모든 자항선 정보 반환"""
        return self._specs.get("vessels", [])
    
    def get_vessel_by_id(self, vessel_id: int) -> Optional[Dict]:
        """ID로 자항선 정보 조회"""
        for vessel in self._specs.get("vessels", []):
            if vessel["id"] == vessel_id:
                return vessel
        return None
    
    def get_vessel_by_name(self, vessel_name: str) -> Optional[Dict]:
        """이름으로 자항선 정보 조회"""
        for vessel in self._specs.get("vessels", []):
            if vessel["name"] == vessel_name:
                return vessel
        return None
    
    def get_vessel_dimensions(self, vessel_id: int) -> Tuple[int, int]:
        """자항선 크기 반환 (width, height)"""
        vessel = self.get_vessel_by_id(vessel_id)
        if vessel:
            return vessel["width"], vessel["height"]
        return 80, 40  # 기본값
    
    def get_vessel_cycle_days(self, vessel_id: int) -> int:
        """자항선 사이클 총 일수 반환"""
        vessel = self.get_vessel_by_id(vessel_id)
        if vessel and "cycle" in vessel:
            return vessel["cycle"]["total_days"]
        return 12  # 기본값
    
    def get_vessel_cycle_phases(self, vessel_id: int) -> Tuple[int, int, int, int]:
        """자항선 사이클 단계별 일수 반환 (departure, loading, unloading, return)"""
        vessel = self.get_vessel_by_id(vessel_id)
        if vessel and "cycle" in vessel:
            cycle = vessel["cycle"]
            return (
                cycle["departure_days"],
                cycle["loading_days"], 
                cycle["unloading_days"],
                cycle["return_days"]
            )
        return (3, 3, 3, 3)  # 기본값
    
    def get_vessel_rest_period(self, vessel_id: int) -> int:
        """자항선 휴식기 일수 반환"""
        vessel = self.get_vessel_by_id(vessel_id)
        if vessel:
            return vessel.get("rest_period_days", 1)
        return 1  # 기본값
    
    def get_vessel_color(self, vessel_name: str) -> str:
        """자항선 색상 반환"""
        vessel = self.get_vessel_by_name(vessel_name)
        if vessel:
            return vessel.get("color", "#4F46E5")
        return "#4F46E5"  # 기본값
    
    def get_vessel_colors_dict(self) -> Dict[str, str]:
        """모든 자항선의 색상 딕셔너리 반환"""
        colors = {}
        for vessel in self._specs.get("vessels", []):
            colors[vessel["name"]] = vessel.get("color", "#4F46E5")
        return colors
    
    def get_vessel_phase_duration_dict(self) -> Dict[int, Tuple[int, int, int, int]]:
        """VESSEL_PHASE_DUR 형태의 딕셔너리 반환 (하위 호환성)"""
        phase_dur = {}
        for vessel in self._specs.get("vessels", []):
            vessel_id = vessel["id"]
            if "cycle" in vessel:
                cycle = vessel["cycle"]
                phase_dur[vessel_id] = (
                    cycle["departure_days"],
                    cycle["loading_days"],
                    cycle["unloading_days"], 
                    cycle["return_days"]
                )
            else:
                phase_dur[vessel_id] = (3, 3, 3, 3)  # 기본값
        return phase_dur

# 전역 인스턴스 생성
_vessel_manager = None

def get_vessel_manager() -> VesselSpecManager:
    """VesselSpecManager 싱글톤 인스턴스 반환"""
    global _vessel_manager
    if _vessel_manager is None:
        _vessel_manager = VesselSpecManager()
    return _vessel_manager

# 편의 함수들
def get_vessel_specs() -> Dict:
    """자항선 스펙 딕셔너리 반환"""
    return get_vessel_manager()._specs

def get_vessel_dimensions(vessel_id: int) -> Tuple[int, int]:
    """자항선 크기 반환"""
    return get_vessel_manager().get_vessel_dimensions(vessel_id)

def get_vessel_cycle_days(vessel_id: int) -> int:
    """자항선 사이클 총 일수 반환"""
    return get_vessel_manager().get_vessel_cycle_days(vessel_id)

def get_vessel_phase_duration() -> Dict[int, Tuple[int, int, int, int]]:
    """VESSEL_PHASE_DUR 딕셔너리 반환"""
    return get_vessel_manager().get_vessel_phase_duration_dict()

def get_vessel_colors() -> Dict[str, str]:
    """자항선 색상 딕셔너리 반환"""
    return get_vessel_manager().get_vessel_colors_dict()

def get_vessel_rest_period(vessel_id: int) -> int:
    """자항선 휴식기 일수 반환"""
    return get_vessel_manager().get_vessel_rest_period(vessel_id)
