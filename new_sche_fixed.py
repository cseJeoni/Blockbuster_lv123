import json
import pandas as pd
from datetime import datetime, timedelta
import webbrowser
import os
from typing import Tuple

# 자항선별 운항 사이클 기간 데이터
VESSEL_PHASE_DUR = {
    1: (3, 3, 3, 3),   # 자항선1: 12일
    2: (3, 1, 3, 1),   # 자항선2: 8일
    3: (3, 3, 3, 2),   # 자항선3: 11일
    4: (3, 3, 3, 2),   # 자항선4: 11일
    5: (3, 3, 3, 2),   # 자항선5: 11일
}

class VoyageScheduleVisualizer:
    def __init__(self, json_file_path: str):
        self.json_file_path = json_file_path
        self.voyage_data = None
        self.schedule_df = None
        self.assignment_info = None

    def load_and_prepare_data(self):
        """JSON 데이터 로드 및 간트 차트용 데이터 준비"""
        try:
            with open(self.json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self.voyage_data = data.get('voyage_assignments', {})
            self.assignment_info = data.get('assignment_info', {})
            print(f"✅ 데이터 로드 완료: {len(self.voyage_data)}개 항차")
        except Exception as e:
            print(f"❌ 데이터 로드 실패: {str(e)}")
            return False

        schedule_data = []
        for voyage_id, blocks in self.voyage_data.items():
            if not blocks: continue
            
            parts = voyage_id.split('_')
            vessel_name, start_date_str = parts[0], parts[1]  # 시작일 기준으로 변경
            vessel_id = int(vessel_name.replace("자항선", ""))
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d")
            
            cycle_days = sum(VESSEL_PHASE_DUR.get(vessel_id, (1,1,1,1)))
            end_date = start_date + timedelta(days=cycle_days - 1)

            schedule_data.append({
                'Vessel': vessel_name, 'Start': start_date, 'Finish': end_date,
                'Blocks': blocks, 'BlockCount': len(blocks), 'VoyageID': voyage_id
            })
        self.schedule_df = pd.DataFrame(schedule_data).sort_values(['Vessel', 'Start'])
        print(f"✅ 스케줄 데이터 준비 완료: {len(self.schedule_df)}개 항차")
        return True

    def _build_voyage_ranges(self):
        """로그에서 항차별 시작~종료 날짜 범위 추출"""
        ranges = {}
        logs = self.assignment_info.get('logs', [])
        import re
        pattern = r'\[(자항선\d)\s(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\]'
        
        for line in logs:
            match = re.match(pattern, line)
            if match:
                vessel = match.group(1)
                start_str = match.group(2)
                end_str = match.group(3)
                start_date = datetime.strptime(start_str, '%Y-%m-%d')
                end_date = datetime.strptime(end_str, '%Y-%m-%d')
                key = f"{vessel}_{start_str}"  # 시작일 기준으로 변경
                ranges[key] = {'start': start_date, 'end': end_date, 'vessel': vessel}
        
        return ranges

    def generate_html_dashboard(self, output_file='placement_results/dashboard_report.html'):
        """Canvas 기반 간트 차트로 HTML 대시보드 생성"""
        if not self.load_and_prepare_data(): return

        total_voyages = len(self.voyage_data)
        total_blocks = sum(len(b) for b in self.voyage_data.values())
        vessel_count = len(self.schedule_df['Vessel'].unique())
        
        voyage_json = json.dumps(self.voyage_data, ensure_ascii=False)
        assignment_info_json = json.dumps(self.assignment_info, ensure_ascii=False)

        html_template = f"""<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>자항선 운항 스케줄 대시보드</title>
  <style>
    :root {{
      --cell-w: 40px;
      --cell-h: 28px;
      --hdr-h: 72px;
      --left-w: 120px;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin:0; padding:16px; font-family: 'Malgun Gothic', Arial, sans-serif;
      background:#fafafa; color:#222;
      min-height:100vh; display:flex; flex-direction:column; gap:16px;
    }}
    .row {{
      width:100%;
    }}
    .row.chart-row {{
      flex:1; min-height:500px;
    }}
    .card {{
      background:#fff; border:1px solid #e5e7eb; border-radius:14px; padding:14px; box-shadow:0 2px 6px rgba(0,0,0,.05);
    }}
    .card h2 {{ margin:0 0 8px 0; font-size:16px; }}
    .stats {{ display: flex; justify-content: space-around; margin: 12px 0; }}
    .stat-box {{ text-align: center; }}
    .stat-value {{ font-size: 20px; font-weight: bold; }}
    .stat-label {{ font-size: 12px; color: #666; }}
    #info {{ font-size:13px; line-height:1.5; white-space:pre-line; }}
    #blocksList {{ max-height:200px; overflow:auto; border:1px solid #eee; border-radius:10px; padding:8px; font-size:12px; background:#fbfbfb; }}
    #placementImage {{ max-width:100%; height:auto; border:1px solid #eee; border-radius:8px; margin-top:8px; }}
    .detail-section {{ margin-bottom:12px; }}
    .detail-section h3 {{ margin:0 0 6px 0; font-size:14px; color:#374151; }}
    .clickable-detail {{ cursor:pointer; user-select:none; }}
    .clickable-detail:hover {{ background:#f9fafb; }}
    .detail-content {{ display:none; padding-top:8px; }}
    .detail-content.expanded {{ display:block; }}
    .muted {{ color:#6b7280; }}
    .divider {{ height:1px; background:#eee; margin:8px 0; }}
    #container {{
      position:relative;
      overflow:auto;
      background:#fff;
      border:1px solid #e5e7eb;
      border-radius:14px;
      height: 500px;
      cursor: grab;
      will-change: scroll-position;
    }}
    #container.dragging {{ cursor:grabbing; }}
    canvas {{ display:block; }}
    .leftStrip {{
      position:absolute; left:0; top:0; width:var(--left-w); height:100%;
      background:linear-gradient(90deg, #fafafa, #fff);
      border-right:1px solid #e5e7eb;
      pointer-events:none;
    }}
    #legend {{ display:flex; flex-wrap:wrap; gap:6px; }}
    #legend .chip {{ display:flex; align-items:center; gap:6px; padding:4px 8px; border:1px solid #eee; border-radius:999px; font-size:12px; }}
    #legend .sw {{ width:14px; height:10px; border-radius:3px; border:1px solid #ddd; }}
  </style>
</head>
<body>
  <!-- 1행: 운항 통계 -->
  <div class="row">
    <div class="card">
      <h2>운항 통계</h2>
      <div class="stats">
        <div class="stat-box"><div class="stat-value">{total_voyages}</div><div class="stat-label">총 항차 수</div></div>
        <div class="stat-box"><div class="stat-value">{total_blocks}</div><div class="stat-label">총 블록 수</div></div>
        <div class="stat-box"><div class="stat-value">{vessel_count}</div><div class="stat-label">운항 자항선 수</div></div>
      </div>
    </div>
  </div>

  <!-- 2행: 차트 -->
  <div class="row chart-row">
    <div class="card" style="flex:1; display:flex; flex-direction:column;">
      <div id="container" style="flex:1;">
        <div class="leftStrip"></div>
        <canvas id="gantt"></canvas>
      </div>
      <div id="legend"></div>
    </div>
  </div>

  <!-- 3행: 항차 상세 -->
  <div class="row">
    <div class="card">
      <div class="detail-section clickable-detail" onclick="toggleDetail('voyageDetail')">
        <h2>항차 상세 ▼</h2>
      </div>
      <div id="voyageDetail" class="detail-content">
        <div id="info" class="muted">차트에서 항차를 클릭하면 상세가 여기에 표시됩니다.</div>
        <div class="divider"></div>
        <div id="blocksList"></div>
        <div id="placementImageContainer" style="display:none;">
          <div class="divider"></div>
          <h3>배치 시각화</h3>
          <img id="placementImage" alt="배치 시각화" />
        </div>
      </div>
    </div>
  </div>

  <script>
    const DATA = {{
      voyage_assignments: {voyage_json},
      assignment_info: {assignment_info_json}
    }};
    let voyageBoxes = [];
    let canvas, ctx, container;
    const CELL_W = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--cell-w'));
    const CELL_H = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--cell-h'));
    const HDR_H  = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--hdr-h'));
    const LEFT_W = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--left-w'));

    const vesselOrder = ['자항선1','자항선2','자항선3','자항선4','자항선5'];
    const colors = {{
      '자항선1': '#4F46E5',
      '자항선2': '#16A34A',
      '자항선3': '#DC2626',
      '자항선4': '#0891B2',
      '자항선5': '#A855F7'
    }};

    function parseDate(str) {{
      if(/^\\d{{4}}-\\d{{2}}-\\d{{2}}$/.test(str)) {{
        return new Date(str + 'T00:00:00');
      }}
      return new Date(str);
    }}
    function formatISO(d) {{ return d.toISOString().slice(0,10); }}
    function daysDiff(a,b) {{ return Math.round((b - a) / 86400000); }}

    function buildVoyageRanges(json) {{
      const ranges = {{}};
      const logs = json?.assignment_info?.logs || [];
      const voyageAssignments = json?.voyage_assignments || {{}};
      
      // 로그에서 날짜 범위 추출
      const logRanges = {{}};
      const re = /\\[(자항선\\d) (\\d{{4}}-\\d{{2}}-\\d{{2}})_(\\d{{4}}-\\d{{2}}-\\d{{2}})\\]/;
      
      for(const line of logs) {{
        const m = line.match(re);
        if(!m) continue;
        const vessel = m[1];
        const s = parseDate(m[2]);
        const e = parseDate(m[3]);
        const key = `${{vessel}}_${{formatISO(s)}}`; // 시작일 기준으로 변경
        logRanges[key] = {{ start: s, end: e, vessel }};
      }}
      
      // voyage_assignments의 키들과 로그 범위 매칭
      for(const voyageKey of Object.keys(voyageAssignments)) {{
        if(logRanges[voyageKey]) {{
          ranges[voyageKey] = logRanges[voyageKey];
        }} else {{
          // 로그에서 찾을 수 없으면 키에서 날짜 추출해서 추정
          const parts = voyageKey.split('_');
          if(parts.length >= 2) {{
            const vessel = parts[0];
            const startDate = parseDate(parts[1]); // 시작일 기준
            // 12일 항차로 가정 (기본값)
            const endDate = new Date(startDate);
            endDate.setDate(endDate.getDate() + 11);
            ranges[voyageKey] = {{ start: startDate, end: endDate, vessel }};
          }}
        }}
      }}
      
      console.log('Total ranges built:', Object.keys(ranges).length);
      console.log('Sample ranges:', Object.keys(ranges).slice(0, 5));
      return ranges;
    }}

    function drawChart() {{
      const gantt = document.getElementById('gantt');
      canvas = gantt; ctx = gantt.getContext('2d'); container = document.getElementById('container');

      const ranges = buildVoyageRanges(DATA);
      const all = Object.values(ranges);
      if(all.length === 0) return;
      
      const minStart = new Date(Math.min(...all.map(r => r.start.getTime())));
      const maxEnd   = new Date(Math.max(...all.map(r => r.end.getTime())));

      const chartStart = new Date(minStart); chartStart.setDate(chartStart.getDate()-3);
      const chartEnd   = new Date(maxEnd);   chartEnd.setDate(chartEnd.getDate()+3);
      const totalDays  = daysDiff(chartStart, chartEnd) + 1;

      const rows = vesselOrder.length;
      canvas.width  = LEFT_W + totalDays * CELL_W + 2;
      canvas.height = HDR_H + rows * CELL_H + 1;

      ctx.fillStyle = '#fff'; ctx.fillRect(0,0,canvas.width,canvas.height);

      drawHeader(chartStart, totalDays);

      ctx.font = '12px Arial'; ctx.textBaseline = 'middle'; ctx.fillStyle = '#111827';
      voyageBoxes = [];
      vesselOrder.forEach((vessel, idx) => {{
        const y = HDR_H + idx * CELL_H;
        ctx.strokeStyle = '#e5e7eb';
        ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(canvas.width, y); ctx.stroke();
        ctx.fillText(vessel, 10, y + CELL_H/2);
      }});
      
      ctx.strokeStyle = '#e5e7eb'; ctx.beginPath();
      ctx.moveTo(0, HDR_H + rows*CELL_H); ctx.lineTo(canvas.width, HDR_H + rows*CELL_H); ctx.stroke();

      const perVessel = DATA?.voyage_assignments || {{}};
      const voyagesByVessel = {{}};
      Object.keys(perVessel).forEach(vid => {{
        const vessel = vid.split('_')[0];
        if (!voyagesByVessel[vessel]) voyagesByVessel[vessel] = [];
        voyagesByVessel[vessel].push(vid);
      }});

      vesselOrder.forEach((vessel, idx) => {{
        const list = voyagesByVessel[vessel] || [];
        const yTop = HDR_H + idx * CELL_H + 2;
        for(const vid of list) {{
          const r = ranges[vid];
          if(!r) continue;
          const x = LEFT_W + daysDiff(chartStart, r.start) * CELL_W;
          const w = daysDiff(r.start, r.end) * CELL_W; // 하루씩 앞당기기

          ctx.fillStyle = colors[vessel] || '#888';
          ctx.fillRect(x+1, yTop, w-2, CELL_H-4);
          ctx.strokeStyle = '#111827'; ctx.strokeRect(x+0.5, yTop-0.5, w-1, CELL_H-3);

          const blocks = (DATA.voyage_assignments || {{}})[vid] || [];
          const label = `${{blocks.length}}개`;
          ctx.fillStyle = '#fff'; ctx.font = 'bold 12px Arial';
          const tw = ctx.measureText(label).width;
          if(tw < w - 8) {{
            ctx.fillText(label, x + (w - tw)/2, yTop + (CELL_H-4)/2 + 1);
          }}

          voyageBoxes.push({{ x:x+1, y:yTop, w:w-2, h:CELL_H-4, vessel, vid, start:r.start, end:r.end, blocks }});
        }}
      }});

      const leg = document.getElementById('legend');
      leg.innerHTML = '';
      vesselOrder.forEach(v => {{
        const chip = document.createElement('div');
        chip.className = 'chip';
        const sw = document.createElement('div'); sw.className='sw'; sw.style.background = colors[v] || '#888';
        chip.appendChild(sw); chip.append(v);
        leg.appendChild(chip);
      }});

      container.scrollLeft = 0;
    }}

    function drawHeader(chartStart, totalDays) {{
      const dTmp = new Date(chartStart);
      const canvasW = LEFT_W + totalDays*CELL_W;
      const canvasH = HDR_H;

      const c = ctx;
      c.fillStyle = '#fafafa'; c.fillRect(0, 0, canvasW, canvasH);
      c.strokeStyle = '#e5e7eb'; c.beginPath(); c.moveTo(0, HDR_H); c.lineTo(canvasW, HDR_H); c.stroke();

      for(let i=0;i<=totalDays;i++) {{
        const x = LEFT_W + i * CELL_W;
        c.strokeStyle = '#f1f5f9';
        c.beginPath(); c.moveTo(x, 0); c.lineTo(x, canvas.height); c.stroke();
      }}

      c.fillStyle = '#fff'; c.fillRect(0,0,LEFT_W,canvasH);
      c.strokeStyle = '#e5e7eb'; c.beginPath(); c.moveTo(LEFT_W,0); c.lineTo(LEFT_W,canvasH); c.stroke();

      c.textBaseline = 'alphabetic';
      let lastYear = -1, lastMonth = -1;
      for(let i=0;i<totalDays;i++) {{
        const x = LEFT_W + i * CELL_W;
        const year = dTmp.getFullYear();
        const month = dTmp.getMonth()+1;
        const day = dTmp.getDate();

        if(year !== lastYear) {{
          c.fillStyle = '#111827'; c.font = 'bold 14px Arial';
          c.fillText(`${{year}}년`, x + 6, 20);
          lastYear = year;
          lastMonth = -1;
        }}
        if(month !== lastMonth) {{
          c.fillStyle = '#374151'; c.font = 'bold 12px Arial';
          c.fillText(`${{month}}월`, x + 6, 40);
          lastMonth = month;
        }}
        const dd = day.toString().padStart(2,'0');
        c.fillStyle = '#6b7280'; c.font = '12px Arial';
        const cx = x + CELL_W/2 - 4;
        c.fillText(dd[0], cx, 56);
        c.fillText(dd[1], cx, 68);

        dTmp.setDate(dTmp.getDate()+1);
      }}
    }}

    function toggleDetail(sectionId) {{
      const section = document.getElementById(sectionId);
      const isExpanded = section.classList.contains('expanded');
      section.classList.toggle('expanded');
      
      const header = section.previousElementSibling.querySelector('h2');
      header.textContent = header.textContent.replace(/[▼▲]/, isExpanded ? '▼' : '▲');
    }}

    function showDetail(box) {{
      const info = document.getElementById('info');
      const list = document.getElementById('blocksList');
      const imageContainer = document.getElementById('placementImageContainer');
      const image = document.getElementById('placementImage');
      
      // 항차 ID를 시작일 기준으로 표시
      const start = box.start.toISOString().slice(0,10);
      const end   = box.end.toISOString().slice(0,10);
      const vessel = box.vessel;
      
      info.classList.remove('muted');
      info.innerHTML =
        `• 항차: ${{box.vid}}\\n`+
        `• 기간: ${{start}} ~ ${{end}}\\n`+
        `• 실린 블록 개수: ${{box.blocks.length.toLocaleString()}}개`;

      // 블록 리스트 표시
      if(!box.blocks.length) {{ 
        list.innerHTML = '<span class="muted">배정된 블록 없음</span>'; 
      }} else {{
        const frag = document.createDocumentFragment();
        const ul = document.createElement('div');
        for(const bid of box.blocks) {{
          const row = document.createElement('div');
          row.textContent = `${{bid}}`;
          ul.appendChild(row);
        }}
        list.innerHTML = ''; list.appendChild(ul);
      }}

      // 배치 시각화 이미지 표시 (같은 디렉토리에 있으므로 파일명만 사용)
      const fileName = `${{vessel}} ${{start}}_${{end}}.png`;
      
      // 이미지 로드 시도
      image.src = fileName;
      image.onerror = function() {{
        console.log('이미지 로드 실패:', fileName);
        // 대체 텍스트 표시
        imageContainer.innerHTML = `
          <div class="divider"></div>
          <h3>배치 시각화</h3>
          <div style="padding:20px; text-align:center; border:1px dashed #ccc; border-radius:8px; color:#666; background:#f9f9f9;">
            <strong>이미지를 찾을 수 없습니다</strong><br>
            <code style="background:#eee; padding:2px 6px; border-radius:4px; font-size:12px;">${{fileName}}</code><br>
            <small style="color:#999; margin-top:8px; display:block;">
              • placement_results 폴더를 확인해주세요<br>
              • 브라우저 보안 정책으로 로컬 이미지 접근이 제한될 수 있습니다
            </small>
          </div>
        `;
        imageContainer.style.display = 'block';
      }};
      image.onload = function() {{
        console.log('이미지 로드 성공:', fileName);
        imageContainer.style.display = 'block';
      }};
      
      console.log('이미지 경로:', fileName);
      
      // 항차 상세 섹션 자동 확장
      const voyageDetail = document.getElementById('voyageDetail');
      if (!voyageDetail.classList.contains('expanded')) {{
        toggleDetail('voyageDetail');
      }}
    }}

    function hitTest(px, py) {{
      for(let i=0;i<voyageBoxes.length;i++) {{
        const b = voyageBoxes[i];
        if(px>=b.x && px<=b.x+b.w && py>=b.y && py<=b.y+b.h) return b;
      }}
      return null;
    }}

    (function setupInteractions() {{
      const cont = document.getElementById('container');
      let isDown=false, sx=0, sl=0;
      cont.addEventListener('mousedown', (e)=>{{
        isDown=true; sx=e.clientX; sl=cont.scrollLeft; cont.classList.add('dragging');
      }});
      cont.addEventListener('mouseleave', ()=>{{ isDown=false; cont.classList.remove('dragging'); }});
      cont.addEventListener('mouseup', ()=>{{ isDown=false; cont.classList.remove('dragging'); }});
      cont.addEventListener('mousemove', (e)=>{{
        if(!isDown) return;
        const dx = e.clientX - sx;
        cont.scrollLeft = sl - dx;
      }});
      cont.addEventListener('wheel', (e)=>{{
        if(e.ctrlKey) e.preventDefault();
      }}, {{passive:false}});

      cont.addEventListener('click', (e)=>{{
        const rect = canvas.getBoundingClientRect();
        const x = e.clientX - rect.left + cont.scrollLeft;
        const y = e.clientY - rect.top + cont.scrollTop;
        const box = hitTest(x,y);
        if(box) showDetail(box);
      }});
    }})();

    drawChart();

    window.addEventListener('resize', ()=>{{
      drawChart();
    }});
  </script>
</body>
</html>"""

        # placement_results 디렉토리가 없으면 생성
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(html_template)
        print(f"✅ 대시보드가 '{output_file}' 파일로 저장되었습니다.")
        print(f"✅ HTML 파일이 이미지와 같은 디렉토리에 위치하여 이미지 로드가 가능합니다.")
        webbrowser.open(f"file://{os.path.realpath(output_file)}")

# --- 스크립트 실행 ---
if __name__ == "__main__":
    visualizer = VoyageScheduleVisualizer(json_file_path="lv3_integrated_voyage_assignments.json")
    visualizer.generate_html_dashboard()
