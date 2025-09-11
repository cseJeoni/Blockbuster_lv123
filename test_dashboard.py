#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import os
import webbrowser

# 간단한 테스트용 대시보드 생성
def create_test_dashboard():
    # JSON 데이터 로드
    with open('lv3_integrated_voyage_assignments.json', 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    voyage_assignments = data.get('voyage_assignments', {})
    assignment_info = data.get('assignment_info', {})
    
    print(f"총 항차 수: {len(voyage_assignments)}")
    print(f"첫 5개 항차: {list(voyage_assignments.keys())[:5]}")
    
    voyage_json = json.dumps(voyage_assignments, ensure_ascii=False)
    assignment_info_json = json.dumps(assignment_info, ensure_ascii=False)
    
    html_content = f"""
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <title>항차 테스트 대시보드</title>
    <style>
        body {{ font-family: 'Malgun Gothic', Arial, sans-serif; margin: 20px; }}
        #info {{ background: #f0f0f0; padding: 10px; margin: 10px 0; }}
        canvas {{ border: 1px solid #ccc; }}
    </style>
</head>
<body>
    <h1>항차 테스트 대시보드</h1>
    <div id="info">로딩 중...</div>
    <canvas id="testCanvas" width="800" height="400"></canvas>
    
    <script>
        const DATA = {{
            voyage_assignments: {voyage_json},
            assignment_info: {assignment_info_json}
        }};
        
        const info = document.getElementById('info');
        const canvas = document.getElementById('testCanvas');
        const ctx = canvas.getContext('2d');
        
        // 데이터 확인
        const voyageKeys = Object.keys(DATA.voyage_assignments);
        info.innerHTML = `
            <strong>데이터 로드 완료!</strong><br>
            총 항차 수: ${{voyageKeys.length}}<br>
            첫 5개 항차: ${{voyageKeys.slice(0, 5).join(', ')}}<br>
            로그 수: ${{DATA.assignment_info.logs ? DATA.assignment_info.logs.length : 0}}
        `;
        
        // 간단한 테스트 차트 그리기
        ctx.fillStyle = '#f0f0f0';
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        
        ctx.fillStyle = '#333';
        ctx.font = '16px Arial';
        ctx.fillText('항차 데이터 테스트', 20, 30);
        
        // 첫 몇 개 항차를 간단한 막대로 표시
        let y = 60;
        voyageKeys.slice(0, 10).forEach((voyage, i) => {{
            const blocks = DATA.voyage_assignments[voyage];
            const blockCount = blocks ? blocks.length : 0;
            
            ctx.fillStyle = '#4F46E5';
            ctx.fillRect(20, y, blockCount * 10, 20);
            
            ctx.fillStyle = '#333';
            ctx.font = '12px Arial';
            ctx.fillText(`${{voyage}} (${{blockCount}}개)`, 20, y + 35);
            
            y += 40;
        }});
        
        console.log('데이터 확인:', DATA);
        console.log('항차 키들:', voyageKeys);
    </script>
</body>
</html>
"""
    
    with open('test_dashboard.html', 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print("테스트 대시보드가 'test_dashboard.html'로 생성되었습니다.")

if __name__ == "__main__":
    create_test_dashboard()
