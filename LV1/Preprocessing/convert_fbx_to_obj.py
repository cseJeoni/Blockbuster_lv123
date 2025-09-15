"""
FBX → OBJ 변환기 (Blender 기반)
단일 파일 또는 폴더 전체 일괄 변환 지원
"""
import os
import sys
import argparse
import subprocess
from pathlib import Path
import time

# Blender 스크립트 (문자열로 저장)
BLENDER_SCRIPT = '''
import bpy
import sys
import os

def convert_fbx_to_obj(fbx_path, obj_path):
    """FBX 파일을 OBJ로 변환"""
    try:
        print(f"[INFO] 변환 시작: {os.path.basename(fbx_path)}")
        
        # 씬 초기화
        bpy.ops.wm.read_factory_settings(use_empty=True)
        
        # FBX 파일 import
        print(f"[INFO] FBX 로딩 중...")
        bpy.ops.import_scene.fbx(filepath=fbx_path)
        
        # 객체가 있는지 확인
        if len(bpy.context.scene.objects) == 0:
            print(f"[ERROR] 로드된 객체가 없습니다")
            return False
            
        print(f"[INFO] {len(bpy.context.scene.objects)}개 객체 로드됨")
        
        # 모든 객체 선택
        bpy.ops.object.select_all(action='SELECT')
        
        # OBJ 파일로 export
        print(f"[INFO] OBJ 내보내기 중...")
        bpy.ops.wm.obj_export(
            filepath=obj_path,
            export_selected_objects=True,
            export_uv=True,
            export_normals=True,
            export_materials=False,  # 재질은 제외 (기하학적 형태만)
            export_triangulated_mesh=True  # 삼각형으로 변환
        )
        
        print(f"[SUCCESS] 변환 완료: {os.path.basename(obj_path)}")
        return True
        
    except Exception as e:
        print(f"[ERROR] 변환 실패: {str(e)}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("[ERROR] 인수가 부족합니다")
        sys.exit(1)
    
    fbx_path = sys.argv[-2]
    obj_path = sys.argv[-1]
    
    print(f"[INFO] Blender 스크립트 실행")
    print(f"  - 입력: {fbx_path}")
    print(f"  - 출력: {obj_path}")
    
    success = convert_fbx_to_obj(fbx_path, obj_path)
    
    if success:
        print(f"[INFO] 스크립트 완료: 성공")
        sys.exit(0)
    else:
        print(f"[ERROR] 스크립트 완료: 실패")
        sys.exit(1)
'''

class FBXToOBJConverter:
    """FBX를 OBJ로 변환하는 클래스"""
    
    def __init__(self, blender_path=None):
        """
        Args:
            blender_path (str): Blender 실행 파일 경로 (None이면 자동 탐지)
        """
        self.blender_path = blender_path or self._find_blender()
        
        if not self.blender_path:
            raise RuntimeError("Blender를 찾을 수 없습니다. 설치되어 있는지 확인하세요.")
        
        print(f"[INFO] Blender 경로: {self.blender_path}")
    
    def _find_blender(self):
        """시스템에서 Blender 자동 탐지"""
        possible_paths = [
            # Windows
            r"C:\Program Files\Blender Foundation\Blender 4.0\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 3.6\blender.exe",
            r"C:\Program Files\Blender Foundation\Blender 3.5\blender.exe",
            # macOS
            "/Applications/Blender.app/Contents/MacOS/Blender",
            # Linux
            "/usr/bin/blender",
            "/snap/bin/blender",
            # PATH에서 찾기
            "blender"
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                return path
            
            # PATH에서 찾기
            try:
                result = subprocess.run(["which", path], capture_output=True, text=True)
                if result.returncode == 0:
                    return result.stdout.strip()
            except:
                continue
        
        return None
    
    def convert_single_file(self, fbx_path, obj_path=None):
        """단일 FBX 파일을 OBJ로 변환"""
        fbx_path = Path(fbx_path)
        
        if not fbx_path.exists():
            raise FileNotFoundError(f"FBX 파일을 찾을 수 없습니다: {fbx_path}")
        
        # 출력 경로 설정
        if obj_path is None:
            obj_path = fbx_path.with_suffix('.obj')
        else:
            obj_path = Path(obj_path)
        
        print(f"\n🔄 단일 파일 변환:")
        print(f"  📂 입력: {fbx_path.name}")
        print(f"  📄 출력: {obj_path.name}")
        
        # 임시 스크립트 파일 생성
        script_path = Path("temp_blender_script.py")
        try:
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(BLENDER_SCRIPT)
            
            # Blender 실행
            cmd = [
                str(self.blender_path),
                "--background",  # GUI 없이 실행
                "--python", str(script_path),
                "--",  # 이후 인수들은 Python 스크립트에 전달
                str(fbx_path.absolute()),
                str(obj_path.absolute())
            ]
            
            start_time = time.time()
            result = subprocess.run(cmd, capture_output=True, text=True)
            elapsed_time = time.time() - start_time
            
            if result.returncode == 0:
                file_size = obj_path.stat().st_size / 1024 / 1024  # MB
                print(f"  ✅ 성공! ({elapsed_time:.1f}초, {file_size:.1f}MB)")
                return True
            else:
                print(f"  ❌ 실패!")
                print(f"  오류: {result.stderr}")
                return False
                
        finally:
            # 임시 파일 정리
            if script_path.exists():
                script_path.unlink()
    
    def convert_batch(self, input_dir, output_dir=None):
        """폴더 내 모든 FBX 파일을 일괄 변환"""
        input_dir = Path(input_dir)
        
        if not input_dir.exists() or not input_dir.is_dir():
            raise FileNotFoundError(f"입력 디렉토리를 찾을 수 없습니다: {input_dir}")
        
        # 출력 디렉토리 설정
        if output_dir is None:
            output_dir = input_dir / "converted_obj"
        else:
            output_dir = Path(output_dir)
        
        output_dir.mkdir(exist_ok=True)
        
        # FBX 파일 찾기
        fbx_files = list(input_dir.glob("*.fbx")) + list(input_dir.glob("*.FBX"))
        
        if not fbx_files:
            print(f"❌ FBX 파일을 찾을 수 없습니다: {input_dir}")
            return
        
        print(f"\n🚀 일괄 변환 시작:")
        print(f"  📂 입력 디렉토리: {input_dir}")
        print(f"  📁 출력 디렉토리: {output_dir}")
        print(f"  📄 FBX 파일 수: {len(fbx_files)}개")
        
        successful = 0
        failed = 0
        total_start_time = time.time()
        
        for i, fbx_file in enumerate(fbx_files, 1):
            print(f"\n📋 진행률: {i}/{len(fbx_files)}")
            
            obj_file = output_dir / fbx_file.with_suffix('.obj').name
            
            try:
                if self.convert_single_file(fbx_file, obj_file):
                    successful += 1
                else:
                    failed += 1
                    
            except Exception as e:
                print(f"  ❌ 예외 발생: {e}")
                failed += 1
        
        total_elapsed = time.time() - total_start_time
        
        print(f"\n🎉 일괄 변환 완료!")
        print(f"  ✅ 성공: {successful}개")
        print(f"  ❌ 실패: {failed}개")
        print(f"  ⏱️ 총 시간: {total_elapsed:.1f}초")
        print(f"  📁 결과 위치: {output_dir}")

def main():
    parser = argparse.ArgumentParser(description='FBX를 OBJ로 변환 (Blender 기반)')
    
    parser.add_argument('input', help='입력 FBX 파일 또는 디렉토리')
    parser.add_argument('-o', '--output', help='출력 OBJ 파일 또는 디렉토리')
    parser.add_argument('-b', '--blender', help='Blender 실행 파일 경로')
    parser.add_argument('--batch', action='store_true', help='폴더 일괄 변환 모드')
    
    args = parser.parse_args()
    
    try:
        print("🔧 === FBX → OBJ 변환기 (Blender 기반) ===")
        
        # 변환기 초기화
        converter = FBXToOBJConverter(blender_path=args.blender)
        
        input_path = Path(args.input)
        
        if args.batch or input_path.is_dir():
            # 일괄 변환 모드
            converter.convert_batch(input_path, args.output)
        else:
            # 단일 파일 변환 모드
            converter.convert_single_file(input_path, args.output)
        
        print("\n✨ 모든 작업이 완료되었습니다!")
        
    except Exception as e:
        print(f"\n❌ 오류 발생: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()