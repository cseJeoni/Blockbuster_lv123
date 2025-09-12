#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
블록 라벨링 (최종 패치판)
- 복셀 캐시(voxel_cache/*.json)에서 블록 가로/세로/면적 로드
- 자항선별 호환성 테스트(안전여백, 90° 회전 포함)
- VIP 정의 수정: **자항선1 전용([1]일 때만 VIP)**
- 문제 블록 사유 로깅(폭 초과/길이 초과/회전해도 초과/치수미확인 등)
- 결과 JSON: block_labeling_results.json

의존:
- placement_api 불필요 (라벨링은 LV1 호출 안 함)
- voxel_cache 디렉토리 또는 voxel_cache.zip (자동해제)
- (옵션) vessel_specs.json (없으면 기본 스펙 사용)
"""

from __future__ import annotations
import json, os, sys, zipfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple, Optional

# ---------------------------------------------------------
# 유틸
# ---------------------------------------------------------
def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ensure_voxel_cache_dir(cache_dir: Path) -> Path:
    """voxel_cache 디렉토리가 없고 voxel_cache.zip만 있을 때 자동 해제"""
    if cache_dir.exists():
        return cache_dir
    zip_path = cache_dir.with_suffix(".zip")
    if zip_path.exists():
        try:
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(cache_dir)
            print(f"[INFO] voxel_cache.zip → {cache_dir} 해제 완료")
        except Exception as e:
            print(f"[WARN] voxel_cache.zip 해제 실패: {e}")
    return cache_dir


# ---------------------------------------------------------
# 라벨러
# ---------------------------------------------------------
class BlockLabeler:
    def __init__(self,
                 voxel_cache_dir: str = "voxel_cache",
                 vessel_specs_file: str = "vessel_specs.json",
                 safety_margin: float = 2.0):
        self.voxel_cache_dir = Path(voxel_cache_dir)
        _ensure_voxel_cache_dir(self.voxel_cache_dir)

        self.vessel_specs_file = Path(vessel_specs_file)
        self.safety_margin = safety_margin

        self.vessel_specs: List[Dict] = self._load_vessel_specs()
        self.block_data: Dict[str, Dict] = {}             # block_id -> {width,height,area}
        self.labeling_results: Dict[str, Dict] = {}       # 상세 결과
        
        # [최적화] 블록 데이터 캐싱
        self._block_cache: Dict[str, Dict] = {}

        print("🚢 사용 자항선 스펙:")
        for v in self.vessel_specs:
            print(f"  - {v['name']}: {v['width']} x {v['height']} (id={v['id']})")
        print(f"📏 안전 여백: {self.safety_margin}")

    # ---------------- Vessel Specs ----------------
    def _load_vessel_specs(self) -> List[Dict]:
        if self.vessel_specs_file.exists():
            try:
                with open(self.vessel_specs_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                vessels = data.get("vessels")
                if isinstance(vessels, list):
                    return [{
                        "id": int(v.get("id")),
                        "name": v.get("name", f"자항선{v.get('id')}"),
                        "width": float(v.get("width")),
                        "height": float(v.get("height")),
                    } for v in vessels]
                # fallback: top-level list
                if isinstance(data, list):
                    return [{
                        "id": int(v.get("id")),
                        "name": v.get("name", f"자항선{v.get('id')}"),
                        "width": float(v.get("width")),
                        "height": float(v.get("height")),
                    } for v in data]
            except Exception as e:
                print(f"[WARN] vessel_specs.json 읽기 실패: {e}. 기본값 사용.")

        # 기본값(업무 공유 스펙)
        return [
            {"id": 1, "name": "자항선1", "width": 62, "height": 170},
            {"id": 2, "name": "자항선2", "width": 36, "height": 84},
            {"id": 3, "name": "자항선3", "width": 32, "height": 120},
            {"id": 4, "name": "자항선4", "width": 40, "height": 130},
            {"id": 5, "name": "자항선5", "width": 32, "height": 116},
        ]

    # ---------------- Voxel Cache Load ----------------
    def load_block_dimensions(self) -> Dict[str, Dict]:
        """voxel_cache/*.json 에서 블록 폭/높이/면적 로드 (resolution 반영)"""
        cache = self.voxel_cache_dir
        if not cache.exists():
            print(f"[ERROR] voxel_cache 디렉토리를 찾을 수 없습니다: {cache.resolve()}")
            return {}

        files = list(cache.glob("*.json"))
        print(f"[INFO] 복셀 캐시 JSON {len(files)}개 발견")

        loaded = 0
        for fp in files:
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    data = json.load(f)
                bid = data.get("block_id") or fp.stem

                vdata = (data.get("voxel_data") or {})
                res   = float(vdata.get("resolution", 1.0))  # ← 기본 1.0m/셀
                
                # 복셀 위치에서 그리드 크기 계산
                voxel_positions = vdata.get("voxel_positions", [])
                footprint_area = vdata.get("footprint_area")
                
                gw = gh = None
                if voxel_positions:
                    # voxel_positions에서 최대 x, y 좌표 찾기
                    max_x = max(pos[0] for pos in voxel_positions) if voxel_positions else 0
                    max_y = max(pos[1] for pos in voxel_positions) if voxel_positions else 0
                    gw = max_x + 1  # 0-based이므로 +1
                    gh = max_y + 1  # 0-based이므로 +1

                if gw is None or gh is None:
                    # 치수 미확인
                    self.block_data[bid] = {
                        "width": None, "height": None, "area": None,
                        "grid_width": None, "grid_height": None,
                        "resolution": res, "source": fp.name
                    }
                    continue

                # 미터 단위로 환산
                width_m  = float(gw) * res
                height_m = float(gh) * res
                
                # footprint_area가 있으면 사용, 없으면 직사각 근사
                if footprint_area is not None:
                    area_m2 = float(footprint_area) * (res * res)  # 복셀 개수 * 복셀 면적
                else:
                    area_m2 = width_m * height_m

                self.block_data[bid] = {
                    "width": width_m, "height": height_m, "area": area_m2,
                    "grid_width": float(gw), "grid_height": float(gh),
                    "resolution": res, "source": fp.name
                }
                loaded += 1

            except Exception as e:
                print(f"[WARN] {fp.name} 파싱 실패: {e}")

        print(f"[INFO] 블록 치수 로드 완료: {loaded}/{len(files)}")
        return self.block_data


    # ---------------- Compatibility ----------------
    @staticmethod
    def _fits(block_w: float, block_h: float, avail_w: float, avail_h: float) -> bool:
        return (block_w <= avail_w and block_h <= avail_h)

    def test_vessel_compatibility(self, block_w: float, block_h: float, vessel: Dict, safety_margin: float) -> Tuple[bool, str]:
        """회전 포함 호환성 테스트. 실패 사유를 함께 반환."""
        avail_w = vessel["width"]  - safety_margin
        avail_h = vessel["height"] - safety_margin

        if block_w is None or block_h is None:
            return False, "치수 미확인"

        # 원본 방향
        if self._fits(block_w, block_h, avail_w, avail_h):
            return True, ""

        # 90° 회전
        if self._fits(block_h, block_w, avail_w, avail_h):
            return True, ""

        # 실패 사유 디테일
        if block_w > avail_w and block_h > avail_h:
            return False, "폭/길이 모두 초과"
        if block_w > avail_w:
            return False, "폭 초과"
        if block_h > avail_h:
            return False, "길이 초과"
        # 회전해도 초과
        return False, "회전해도 초과"

    def analyze_block_compatibility(self, safety_margin: Optional[float] = None) -> Dict[str, Dict]:
        if safety_margin is None:
            safety_margin = self.safety_margin
        print(f"[INFO] 호환성 분석 시작 (안전여백={safety_margin})")

        if not self.block_data:
            self.load_block_dimensions()

        for bid, info in self.block_data.items():
            bw, bh = info.get("width"), info.get("height")
            comp: List[int] = []
            reasons: Dict[int, str] = {}

            for v in self.vessel_specs:
                ok, why = self.test_vessel_compatibility(bw, bh, v, safety_margin)
                if ok:
                    comp.append(int(v["id"]))
                else:
                    reasons[int(v["id"])] = why

            # VIP = 자항선1 전용([1]일 때만)
            is_vip = (len(comp) == 1 and comp[0] == 1)

            self.labeling_results[bid] = {
                "block_info": {"width": bw, "height": bh, "area": info.get("area"), "source": info.get("source")},
                "compatible_vessels": comp,
                "incompatible_reasons": reasons,   # {vessel_id: reason}
                "vessel_count": len(comp),
                "label": "VIP" if is_vip else ("일반" if len(comp) > 0 else "문제"),
                "is_vip": is_vip,
                "rotation_checked": True,
                "safety_margin_used": safety_margin
            }

        print(f"[INFO] 호환성 분석 완료: {len(self.labeling_results)}개")
        return self.labeling_results

    # ---------------- Summary & Save ----------------
    def get_classification_summary(self) -> Dict:
        if not self.labeling_results:
            self.analyze_block_compatibility()

        vip = [b for b, r in self.labeling_results.items() if r["is_vip"]]
        normal = [b for b, r in self.labeling_results.items() if (r["vessel_count"] > 0 and not r["is_vip"])]
        problematic = [b for b, r in self.labeling_results.items() if r["vessel_count"] == 0]

        total = len(self.labeling_results) or 1
        return {
            "vip_blocks": vip,
            "normal_blocks": normal,
            "problematic_blocks": problematic,
            "summary": {
                "total": len(self.labeling_results),
                "vip_count": len(vip),
                "normal_count": len(normal),
                "problematic_count": len(problematic),
                "vip_ratio": round(len(vip) / total * 100, 2),
            }
        }

    def save_results(self, output_file: str = "block_labeling_results.json") -> str:
        if not self.labeling_results:
            self.analyze_block_compatibility()

        out = {
            "analysis_info": {
                "timestamp": _now(),
                "safety_margin": self.safety_margin,
                "vessel_specs": self.vessel_specs,
                "voxel_cache_dir": str(self.voxel_cache_dir),
            },
            "classification": self.get_classification_summary(),
            "detailed_results": self.labeling_results,
        }
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"[SAVE] {output_file}")
        return output_file

# ---------------------------------------------------------
# 실행 스크립트
# ---------------------------------------------------------
def main():
    import argparse
    ap = argparse.ArgumentParser(description="블록 라벨링 (자항선 호환성 분석)")
    ap.add_argument("--voxel_cache", default="voxel_cache", help="복셀 캐시 폴더 또는 voxel_cache.zip 위치")
    ap.add_argument("--vessels", default="vessel_specs.json", help="자항선 스펙 JSON (없으면 기본값)")
    ap.add_argument("--safety", type=float, default=2.0, help="안전 여백(m)")
    ap.add_argument("--out", default="block_labeling_results.json", help="결과 JSON 경로")
    args = ap.parse_args()

    labeler = BlockLabeler(voxel_cache_dir=args.voxel_cache,
                           vessel_specs_file=args.vessels,
                           safety_margin=args.safety)
    labeler.analyze_block_compatibility()
    labeler.save_results(args.out)
    print("[DONE] 라벨링 완료")
    return 0

if __name__ == "__main__":
    sys.exit(main())
