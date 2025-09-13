import sys
import os

# ⚠️ 사전 준비: Blockbuster_Test 폴더가 파이썬 경로에 포함되어 있어야 합니다.
# 만약 다른 위치에서 실행한다면 아래 코드의 주석을 해제하고 경로를 맞게 수정하세요.
# sys.path.append('path/to/your/Blockbuster_Test')

try:
    # API 모듈 import
    from Placement_api import run_placement, get_unplaced_blocks
except ImportError:
    print("🚨 오류: 'placement_api' 모듈을 찾을 수 없습니다.")
    print("Blockbuster_Test 폴더에서 코드를 실행하거나 sys.path에 해당 폴더 경로를 추가해주세요.")
    sys.exit(1)

def test_with_existing_config(config_path):
    """
    주어진 config 파일을 사용하여 Blockbuster API를 테스트합니다.
    """
    print(f"🚀 제공된 '{config_path}' 파일로 테스트를 시작합니다.\n")

    # --- 파일 존재 여부 확인 ---
    if not os.path.exists(config_path):
        print(f"🚨 오류: '{config_path}' 파일을 찾을 수 없습니다.")
        print("스크립트와 동일한 폴더에 파일이 있는지 확인해주세요.")
        return

    # --- 1. run_placement()로 전체 배치 결과 확인 ---
    print("="*50)
    print("1. run_placement()로 전체 배치 결과 확인")
    print("="*50)
    try:
        # 제공된 config 파일로 배치 실행
        print("배치를 실행합니다... (최대 15초 소요)")
        result = run_placement(config_path, max_time=60, enable_visualization=False)

        print(result)
        
        print("\n--- 배치 결과 ---")
        print(f"Config 이름: {result.get('config_name')}")
        print(f"✅ 성공 여부: {result.get('success')}")
        print(f"📊 배치 성공률: {result.get('success_rate'):.1f}%")
        print(f"🔢 배치된 블록: {result.get('placed_count')} / {result.get('total_count')}")
        print(f"⏱️ 소요 시간: {result.get('placement_time'):.2f}초")

        

        if result.get('unplaced_blocks'):
            print(f"⚠️ 배치 실패 블록: {result.get('unplaced_blocks')}\n")
        else:
            print("✅ 모든 블록이 성공적으로 배치되었습니다.\n")

    except Exception as e:
        print(f"❌ run_placement() 테스트 중 오류 발생: {e}\n")


    # --- 2. get_unplaced_blocks()로 미배치 블록만 확인 ---
    print("="*50)
    print("2. get_unplaced_blocks()로 미배치 블록만 간단히 확인")
    print("="*50)
    try:
        print("미배치 블록을 확인합니다...")
        unplaced_blocks = get_unplaced_blocks(config_path, max_time=60)

        if unplaced_blocks:
            print(f"✅ 확인된 미배치 블록: {unplaced_blocks}\n")
        else:
            print("✅ 미배치 블록이 없습니다. 모든 블록이 배치 가능합니다.\n")

    except Exception as e:
        print(f"❌ get_unplaced_blocks() 테스트 중 오류 발생: {e}\n")


    print("🎉 테스트가 완료되었습니다.")


if __name__ == '__main__':
    # 업로드된 파일 이름을 여기에 지정합니다.
    user_config_file = "config_20250913_010747.json"
    
    # 함수 실행
    test_with_existing_config(user_config_file)