import os
import csv

def clean_voxel_cache():
    """CSV 파일의 block_id와 매칭되지 않는 JSON 파일들을 삭제"""
    
    # 파일 경로 설정
    csv_path = "data/block_deadline_7.csv"
    voxel_cache_dir = "voxel_cache"
    
    try:
        print("CSV 파일에서 유효한 block_id 목록을 읽는 중...")
        
        # CSV 파일 읽기
        valid_block_ids = set()
        with open(csv_path, 'r', encoding='utf-8') as csvfile:
            # CSV 파일의 첫 줄을 읽어서 헤더 확인
            first_line = csvfile.readline().strip()
            print(f"CSV 파일 헤더: {first_line}")
            
            # 파일 포인터를 처음으로 되돌림
            csvfile.seek(0)
            
            # CSV 리더 생성
            csv_reader = csv.DictReader(csvfile)
            
            # 가능한 block_id 컬럼명들
            possible_columns = ['block_id', 'Block_ID', 'BlockID', 'ID', 'id']
            block_id_column = None
            
            # 헤더에서 block_id 컬럼 찾기
            for col in possible_columns:
                if col in csv_reader.fieldnames:
                    block_id_column = col
                    break
            
            if block_id_column is None:
                # 첫 번째 컬럼을 block_id로 사용
                block_id_column = csv_reader.fieldnames[0]
                print(f"block_id 컬럼을 찾을 수 없어서 첫 번째 컬럼 '{block_id_column}'을 사용합니다.")
            else:
                print(f"사용할 컬럼: {block_id_column}")
            
            # 모든 행을 읽어서 block_id 수집
            for row in csv_reader:
                if block_id_column in row and row[block_id_column]:
                    valid_block_ids.add(str(row[block_id_column]).strip())
        
        print(f"CSV에서 찾은 유효한 block_id 개수: {len(valid_block_ids)}")
        print(f"첫 10개 block_id 예시: {list(valid_block_ids)[:10]}")
        
        # voxel_cache 디렉토리의 JSON 파일들 확인
        if not os.path.exists(voxel_cache_dir):
            print(f"오류: {voxel_cache_dir} 디렉토리가 존재하지 않습니다.")
            return
        
        json_files = [f for f in os.listdir(voxel_cache_dir) if f.endswith('.json')]
        print(f"voxel_cache에서 찾은 JSON 파일 개수: {len(json_files)}")
        
        # JSON 파일명에서 block_id 추출 (확장자 제거)
        json_block_ids = [f.replace('.json', '') for f in json_files]
        
        # 매칭되지 않는 파일들 찾기
        files_to_delete = []
        for i, block_id in enumerate(json_block_ids):
            if block_id not in valid_block_ids:
                files_to_delete.append(json_files[i])
        
        print(f"삭제할 파일 개수: {len(files_to_delete)}")
        
        if files_to_delete:
            print("\n삭제할 파일들:")
            for file_name in files_to_delete:
                print(f"  - {file_name}")
            
            # 파일 삭제 실행
            deleted_count = 0
            for file_to_delete in files_to_delete:
                file_path = os.path.join(voxel_cache_dir, file_to_delete)
                try:
                    os.remove(file_path)
                    print(f"삭제 완료: {file_to_delete}")
                    deleted_count += 1
                except Exception as e:
                    print(f"삭제 실패 {file_to_delete}: {e}")
            
            print(f"\n정리 완료!")
            print(f"총 JSON 파일 수: {len(json_files)}")
            print(f"삭제된 파일 수: {deleted_count}")
            print(f"남은 파일 수: {len(json_files) - deleted_count}")
        else:
            print("삭제할 파일이 없습니다. 모든 JSON 파일이 CSV의 block_id와 매칭됩니다.")
        
    except Exception as e:
        print(f"오류 발생: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    clean_voxel_cache()
