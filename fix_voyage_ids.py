import json
import re
from datetime import datetime, timedelta

def fix_voyage_ids():
    """항차 ID를 종료일 기준에서 시작일 기준으로 변경"""
    
    # JSON 파일 로드
    with open('lv3_integrated_voyage_assignments.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 로그에서 시작일-종료일 매핑 생성
    logs = data.get('assignment_info', {}).get('logs', [])
    date_mapping = {}  # 종료일 기준 ID -> 시작일 기준 ID
    
    pattern = r'\[(자항선\d) (\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\]'
    
    for line in logs:
        match = re.match(pattern, line)
        if match:
            vessel = match.group(1)
            start_date = match.group(2)
            end_date = match.group(3)
            
            old_id = f"{vessel}_{end_date}"
            new_id = f"{vessel}_{start_date}"
            date_mapping[old_id] = new_id
    
    print(f"매핑 생성 완료: {len(date_mapping)}개 항차")
    
    # voyage_assignments 키 변경
    old_assignments = data.get('voyage_assignments', {})
    new_assignments = {}
    
    for old_key, blocks in old_assignments.items():
        if old_key in date_mapping:
            new_key = date_mapping[old_key]
            new_assignments[new_key] = blocks
            print(f"변경: {old_key} -> {new_key}")
        else:
            new_assignments[old_key] = blocks
            print(f"유지: {old_key} (매핑 없음)")
    
    data['voyage_assignments'] = new_assignments
    
    # used_voyages 리스트 업데이트
    if 'used_voyages' in data['assignment_info']:
        old_used = data['assignment_info']['used_voyages']
        new_used = []
        for old_id in old_used:
            new_id = date_mapping.get(old_id, old_id)
            new_used.append(new_id)
        data['assignment_info']['used_voyages'] = new_used
    
    # per_vessel의 voyages 리스트 업데이트
    if 'per_vessel' in data['assignment_info']:
        for vessel_name, vessel_data in data['assignment_info']['per_vessel'].items():
            if 'voyages' in vessel_data:
                old_voyages = vessel_data['voyages']
                new_voyages = []
                for old_id in old_voyages:
                    new_id = date_mapping.get(old_id, old_id)
                    new_voyages.append(new_id)
                vessel_data['voyages'] = new_voyages
    
    # 백업 파일 생성
    with open('lv3_integrated_voyage_assignments_backup.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    # 원본 파일 업데이트
    with open('lv3_integrated_voyage_assignments.json', 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print("✅ 항차 ID 변경 완료!")
    print("✅ 백업 파일 생성: lv3_integrated_voyage_assignments_backup.json")

if __name__ == "__main__":
    fix_voyage_ids()
